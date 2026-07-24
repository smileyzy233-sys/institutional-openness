"""Migrate legacy Stage 2 ``mp/tr`` labels to ``trade/mp`` safely.

The legacy category codes were:

* ``mp``: trade channel
* ``tr``: investment channel

The current contract is:

* ``trade``: trade channel, fixed weight ``(1, 0)``
* ``mp``: multinational-production/investment channel, fixed weight ``(0, 1)``

The migration deliberately uses simultaneous dictionary mappings.  It never
performs chained global string replacements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPACT_LABEL_SCHEMA_VERSION = "trade_mp_v1"
MIGRATION_VERSION = "trade_mp_reason_v2"
CATEGORY_VALUE_MAP = {"mp": "trade", "tr": "mp"}
LEGACY_MAIN_PROMPT_NAME = "stage2_trade_investment.txt"
LEGACY_ARBITRATION_PROMPT_NAME = "stage2_type_arbitration.txt"
PREFLIGHT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "migration_backups"
    / "20260724_pre_trade_mp"
    / "preflight_manifest.json"
)

EXACT_COLUMN_MAP = {
    "final_impact_type_mp_count": "final_impact_type_trade_count",
    "final_impact_type_tr_count": "final_impact_type_mp_count",
    "quality_mp_fixed_1_0": "quality_trade_fixed_1_0",
    "quality_tr_fixed_0_1": "quality_mp_fixed_0_1",
}

PRIMARY_KEY_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("provision_id", "model_role", "model_provider", "model_name"),
    ("provision_id",),
    ("agreement_id",),
    ("iso1", "iso2", "year"),
    ("exporter", "importer", "year"),
    ("reporter", "partner", "year"),
    ("icio_reporter", "icio_partner", "year", "sector"),
    ("country_code", "partner_code", "year"),
)

REASON_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(mp|tr)(?![A-Za-z0-9_])")
REASON_VALUE_MAP = {"mp": "trade", "tr": "mp"}

RENAMEABLE_WEIGHT_TOKENS = (
    ("investment_weight", "mp_weight"),
    ("investment_related_provisions", "mp_related_provisions"),
    ("investment_related_provision", "mp_related_provision"),
)


@dataclass
class MigrationAudit:
    path: str
    changed: bool
    dry_run: bool
    sha256_before: str
    sha256_after: str
    rows_before: int
    rows_after: int
    columns_before: int
    columns_after: int
    primary_key_columns: str
    primary_key_hash_before: str
    primary_key_hash_after: str
    old_mp_to_trade_count: int
    old_tr_to_mp_count: int
    renamed_column_count: int
    raw_response_json_count: int
    reason_review_count: int
    metadata_columns_added: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_sha_or_empty(path: Path | None) -> str:
    return sha256_file(path) if path is not None and path.exists() else ""


def is_category_column(column: str) -> bool:
    lowered = column.lower()
    return "impact_type" in lowered and not lowered.endswith("_count")


def is_raw_response_column(column: str) -> bool:
    return "raw_response" in column.lower()


def has_reason_data(columns: Sequence[str]) -> bool:
    return any(
        "reason" in column.lower() or is_raw_response_column(column)
        for column in columns
    )


def rename_column(column: str) -> str:
    if column in EXACT_COLUMN_MAP:
        return EXACT_COLUMN_MAP[column]
    if column == "raw_investment_score":
        return "raw_mp_score"
    renamed = column
    for old, new in RENAMEABLE_WEIGHT_TOKENS:
        renamed = renamed.replace(old, new)
    return renamed


def simultaneous_column_mapping(
    columns: Sequence[str],
    *,
    already_migrated: bool = False,
) -> dict[str, str]:
    if already_migrated:
        return {column: column for column in columns}
    mapping = {column: rename_column(column) for column in columns}
    targets: dict[str, list[str]] = {}
    for source, target in mapping.items():
        targets.setdefault(target, []).append(source)
    collisions = {target: sources for target, sources in targets.items() if len(sources) > 1}
    if collisions:
        details = "; ".join(
            f"{target} <- {sources}" for target, sources in sorted(collisions.items())
        )
        raise ValueError(f"Column rename collision would lose data: {details}")
    return mapping


def migrate_json_value(
    value: Any,
    *,
    map_categories: bool = True,
    map_reasons: bool = True,
) -> tuple[Any, int, int, int, list[dict[str, str]]]:
    """Recursively migrate structured JSON keys and recognized category values."""

    mp_count = 0
    tr_count = 0
    renamed_keys = 0
    reason_reviews: list[dict[str, str]] = []
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"investment_weight", "raw_investment_weight"}:
                new_key = "raw_mp_weight"
            elif key in {"trade_weight", "raw_trade_weight"}:
                new_key = "raw_trade_weight"
            else:
                new_key = rename_column(str(key))
            if new_key != key:
                renamed_keys += 1
            if map_reasons and "reason" in str(key).lower() and isinstance(item, str):
                new_item, child_reviews = migrate_reason_text(item)
                child_mp = child_tr = child_keys = 0
            else:
                (
                    new_item,
                    child_mp,
                    child_tr,
                    child_keys,
                    child_reviews,
                ) = migrate_json_value(
                    item,
                    map_categories=map_categories,
                    map_reasons=map_reasons,
                )
            if (
                map_categories
                and str(key).lower() in {"impact_type", "final_impact_type"}
                and isinstance(new_item, str)
            ):
                lowered = new_item.strip().lower()
                if lowered in CATEGORY_VALUE_MAP:
                    new_item = CATEGORY_VALUE_MAP[lowered]
                    if lowered == "mp":
                        mp_count += 1
                    else:
                        tr_count += 1
            if new_key in out:
                raise ValueError(f"JSON key collision while renaming {key!r} to {new_key!r}")
            out[new_key] = new_item
            mp_count += child_mp
            tr_count += child_tr
            renamed_keys += child_keys
            reason_reviews.extend(child_reviews)
        return out, mp_count, tr_count, renamed_keys, reason_reviews
    if isinstance(value, list):
        out_list = []
        for item in value:
            (
                new_item,
                child_mp,
                child_tr,
                child_keys,
                child_reviews,
            ) = migrate_json_value(
                item,
                map_categories=map_categories,
                map_reasons=map_reasons,
            )
            out_list.append(new_item)
            mp_count += child_mp
            tr_count += child_tr
            renamed_keys += child_keys
            reason_reviews.extend(child_reviews)
        return out_list, mp_count, tr_count, renamed_keys, reason_reviews
    return value, 0, 0, 0, reason_reviews


def migrate_raw_response(
    raw: str,
    *,
    map_categories: bool = True,
    map_reasons: bool = True,
) -> tuple[str, int, int, bool, list[dict[str, str]]]:
    if not raw.strip():
        return raw, 0, 0, False, []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw, 0, 0, False, []
    if not isinstance(parsed, (dict, list)):
        return raw, 0, 0, False, []
    migrated, mp_count, tr_count, renamed_keys, reason_reviews = migrate_json_value(
        parsed,
        map_categories=map_categories,
        map_reasons=map_reasons,
    )
    if migrated == parsed and not renamed_keys:
        return raw, 0, 0, False, reason_reviews
    return (
        json.dumps(migrated, ensure_ascii=False, separators=(",", ":")),
        mp_count,
        tr_count,
        True,
        reason_reviews,
    )


def migrate_reason_text(text: str) -> tuple[str, list[dict[str, str]]]:
    reviews = []
    for match in REASON_TOKEN_RE.finditer(text):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        token = match.group(1)
        reviews.append(
            {
                "token": token,
                "context": text[start:end].replace("\r", " ").replace("\n", " "),
                "status": f"context_migrated_to_{REASON_VALUE_MAP[token]}",
            }
        )
    migrated = REASON_TOKEN_RE.sub(
        lambda match: REASON_VALUE_MAP[match.group(1)],
        text,
    )
    return migrated, reviews


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        rows = [{column: row.get(column, "") for column in columns} for row in reader]
    return columns, rows


def select_primary_key(columns: Sequence[str]) -> tuple[str, ...]:
    column_set = set(columns)
    for candidate in PRIMARY_KEY_CANDIDATES:
        if set(candidate).issubset(column_set):
            return candidate
    return (columns[0],) if columns else ()


def primary_key_hash(rows: Sequence[dict[str, str]], keys: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for index, row in enumerate(rows):
        values = [row.get(key, "") for key in keys]
        payload = json.dumps([index, values], ensure_ascii=False, separators=(",", ":"))
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def preflight_hashes() -> dict[str, str]:
    if not PREFLIGHT_MANIFEST_PATH.exists():
        return {}
    payload = json.loads(PREFLIGHT_MANIFEST_PATH.read_text(encoding="utf-8"))
    return {
        str(item["path"]): str(item["sha256"])
        for item in payload.get("files", [])
        if "path" in item and "sha256" in item
    }


def legacy_prompt_sha_for_csv(csv_path: Path, prompt_name: str) -> str:
    hashes = preflight_hashes()
    relative = csv_path.resolve().relative_to(PROJECT_ROOT)
    for parent in (relative.parent, *relative.parents):
        candidate = (parent / "prompts" / prompt_name).as_posix()
        if candidate in hashes:
            return hashes[candidate]
        if parent == Path("."):
            break
    return hashes.get((Path("prompts") / prompt_name).as_posix(), "")


def is_stage2_dataset(columns: Sequence[str]) -> bool:
    return any(
        is_category_column(column)
        or "investment_weight" in column
        or "mp_weight" in column
        or column in {"raw_investment_score", "raw_mp_score"}
        or "investment_related_provision" in column
        or "mp_related_provision" in column
        or column in EXACT_COLUMN_MAP
        or column in EXACT_COLUMN_MAP.values()
        for column in columns
    )


def has_current_schema(
    columns: Sequence[str],
    rows: Sequence[dict[str, str]],
) -> bool:
    if "impact_label_schema_version" not in columns:
        return False
    if not rows:
        return True
    versions = {
        (row.get("impact_label_schema_version") or "").strip()
        for row in rows
    }
    if versions != {IMPACT_LABEL_SCHEMA_VERSION}:
        raise ValueError(
            "impact_label_schema_version exists but does not consistently equal "
            f"{IMPACT_LABEL_SCHEMA_VERSION}"
        )
    return True


def needs_migration(path: Path) -> bool:
    columns, rows = read_csv_rows(path)
    if has_current_schema(columns, rows):
        legacy_columns = [
            column
            for column in columns
            if "investment_weight" in column
            or column == "raw_investment_score"
            or "investment_related_provision" in column
            or column in {
                "final_impact_type_tr_count",
                "quality_tr_fixed_0_1",
                "quality_mp_fixed_1_0",
            }
        ]
        if legacy_columns:
            raise ValueError(
                f"{path} claims the current schema but retains legacy columns: "
                f"{legacy_columns}"
            )
        if any(
            (row.get(column) or "").strip().lower() == "tr"
            for row in rows
            for column in columns
            if is_category_column(column)
        ):
            raise ValueError(f"{path} claims the current schema but retains category tr")
        if rows and has_reason_data(columns):
            migration_versions = {
                (row.get("migration_version") or "").strip()
                for row in rows
            }
            if migration_versions != {MIGRATION_VERSION}:
                return True
        return False
    if any(rename_column(column) != column for column in columns):
        return True
    for row in rows:
        for column in columns:
            value = (row.get(column) or "").strip().lower()
            if is_category_column(column) and value in CATEGORY_VALUE_MAP:
                return True
            if is_raw_response_column(column) and value:
                migrated, _mp, _tr, changed, _reviews = migrate_raw_response(row[column])
                if changed and migrated != row[column]:
                    return True
            if "reason" in column.lower() and REASON_TOKEN_RE.search(row[column] or ""):
                return True
    if is_stage2_dataset(columns) and (
        "impact_label_schema_version" not in columns
        or "normalization_version" not in columns
    ):
        return True
    return False


def discover_csvs(roots: Iterable[Path]) -> list[Path]:
    matches: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.csv")):
            if needs_migration(path):
                matches.append(path.resolve())
    return matches


def preflight_additional_targets() -> list[Path]:
    relative_paths = [
        "README.md",
        "run_pipeline.py",
        "src/config.py",
        "src/utils.py",
        "src/07_stage2_llm_code_trade_investment.py",
        "src/08_stage2_compare_dual_model_results.py",
        "src/09_stage2_llm_review_conflicts.py",
        "src/10_finalize_weights.py",
        "src/10_finalize_weights_single_stage2_model.py",
        "src/11_compute_agreement_indices.py",
        "src/12_compute_country_pair_indices.py",
        "src/13_diagnostics.py",
        "src/14_build_trade_agreement_dummy.py",
        "src/15_merge_chatgpt55_stage2_review.py",
        "src/16_build_method_flowcharts.py",
        "src/17_build_nature_method_flowcharts.py",
        "src/build_regression_2019.py",
        "prompts/stage2_trade_investment.txt",
        "prompts/stage2_trade_investment_compact.txt",
        "prompts/stage2_trade_investment_compact_v4.txt.txt",
        "prompts/stage2_type_arbitration.txt",
        "docs/DTA测算方法.docx",
        "docs/例子.docx",
        "docs/DTA制度型成本变化测度.pdf",
        "docs/流程图_v0.pdf",
        "result/例子.docx",
        "result/流程图.pdf",
        "result/中间产物/中间产物_CSV字段说明.xlsx",
        "result/国家对得分和理想点/两份国家对数据_字段说明.xlsx",
        "result/regression_2019/mp_cost_2019_matched.csv",
        "result/regression_2019/mp_cost_2019_matched.dta",
        "result/regression_2019/matching_audit_2019.ipynb",
        "control__variable/贸易成本.png",
        "control__variable/跨国投资.png",
        "control__variable/微信图片_20260722170312_48_507.png",
        "tests/conftest.py",
        "tests/test_pipeline_integration.py",
        "tests/test_finalization.py",
        "tests/test_fractional_coverage.py",
        "tests/test_stage2_comparison.py",
        "tests/test_stage2_validation.py",
        "tests/test_stage2_weight_resolution.py",
    ]
    targets = [PROJECT_ROOT / path for path in relative_paths]
    targets.extend(
        path
        for path in (PROJECT_ROOT / "old data").rglob("*.txt")
        if path.name in {LEGACY_MAIN_PROMPT_NAME, LEGACY_ARBITRATION_PROMPT_NAME}
    )
    return sorted({path.resolve() for path in targets if path.exists()})


def prepare_backup(
    paths: Sequence[Path],
    backup_dir: Path,
    *,
    git_commit: str,
    git_status: Sequence[str],
) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    files_dir = backup_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted({item.resolve() for item in paths}):
        relative = path.relative_to(PROJECT_ROOT)
        destination = files_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        records.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )

    ppt_records = []
    for pattern in ("*.ppt", "*.pptx"):
        for path in sorted((PROJECT_ROOT / "docs").glob(pattern)):
            ppt_records.append(
                {
                    "path": path.relative_to(PROJECT_ROOT).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )

    manifest = {
        "created_at": utc_now(),
        "git_commit": git_commit,
        "git_status_short": list(git_status),
        "baseline_tests": "33 passed",
        "files": records,
        "docs_ppt_hashes": ppt_records,
    }
    manifest_path = backup_dir / "preflight_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (backup_dir / "git_status_short.txt").write_text(
        "\n".join(git_status) + ("\n" if git_status else ""),
        encoding="utf-8",
    )
    (backup_dir / "git_commit.txt").write_text(
        git_commit + ("\n" if git_commit else ""),
        encoding="utf-8",
    )

    archive_path = backup_dir / "trade_mp_pre_migration_files.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for record in records:
            source = files_dir / record["path"]
            archive.write(source, arcname=record["path"])
        archive.write(manifest_path, arcname="preflight_manifest.json")
    manifest["archive"] = {
        "path": archive_path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def migrate_rows(
    path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]], dict[str, int], list[dict[str, str]]]:
    already_migrated = has_current_schema(columns, rows)
    column_map = simultaneous_column_mapping(
        columns,
        already_migrated=already_migrated,
    )
    new_columns = [column_map[column] for column in columns]
    stage2 = is_stage2_dataset(columns)
    reason_schema_current = (
        already_migrated
        and (
            not has_reason_data(columns)
            or not rows
            or {
                (row.get("migration_version") or "").strip()
                for row in rows
            }
            == {MIGRATION_VERSION}
        )
    )
    map_reasons = not reason_schema_current
    metadata_columns = []
    if stage2:
        for column in (
            "impact_label_schema_version",
            "normalization_version",
            "migration_version",
        ):
            if column not in new_columns:
                new_columns.append(column)
                metadata_columns.append(column)

    direct_prompt = "prompt_version" in columns
    if stage2 and direct_prompt and "source_prompt_version" not in new_columns:
        new_columns.append("source_prompt_version")
        metadata_columns.append("source_prompt_version")
    if stage2 and direct_prompt and "prompt_sha256" not in new_columns:
        new_columns.append("prompt_sha256")
        metadata_columns.append("prompt_sha256")

    prompt_name = (
        LEGACY_ARBITRATION_PROMPT_NAME
        if "final_impact_type" in columns
        else LEGACY_MAIN_PROMPT_NAME
    )
    legacy_prompt_sha = legacy_prompt_sha_for_csv(path, prompt_name)

    counts = {
        "old_mp_to_trade_count": 0,
        "old_tr_to_mp_count": 0,
        "renamed_column_count": sum(
            1 for source, target in column_map.items() if source != target
        ),
        "raw_response_json_count": 0,
        "metadata_columns_added": len(metadata_columns),
    }
    reason_reviews: list[dict[str, str]] = []
    migrated_rows: list[dict[str, str]] = []

    for row_number, row in enumerate(rows, start=2):
        new_row: dict[str, str] = {}
        for column in columns:
            target_column = column_map[column]
            value = row.get(column, "")
            if is_category_column(column) and not already_migrated:
                lowered = value.strip().lower()
                if lowered in CATEGORY_VALUE_MAP:
                    value = CATEGORY_VALUE_MAP[lowered]
                    if lowered == "mp":
                        counts["old_mp_to_trade_count"] += 1
                    else:
                        counts["old_tr_to_mp_count"] += 1
            elif is_raw_response_column(column):
                value, mp_count, tr_count, changed, reviews = migrate_raw_response(
                    value,
                    map_categories=not already_migrated,
                    map_reasons=map_reasons,
                )
                counts["old_mp_to_trade_count"] += mp_count
                counts["old_tr_to_mp_count"] += tr_count
                counts["raw_response_json_count"] += int(changed)
                for review in reviews:
                    reason_reviews.append(
                        {
                            "path": path.relative_to(PROJECT_ROOT).as_posix(),
                            "row_number": str(row_number),
                            "column": target_column,
                            **review,
                        }
                    )
            elif "reason" in column.lower() and value and map_reasons:
                value, reviews = migrate_reason_text(value)
                for review in reviews:
                    reason_reviews.append(
                        {
                            "path": path.relative_to(PROJECT_ROOT).as_posix(),
                            "row_number": str(row_number),
                            "column": target_column,
                            **review,
                        }
                    )
            new_row[target_column] = value

        if stage2:
            new_row["impact_label_schema_version"] = IMPACT_LABEL_SCHEMA_VERSION
            new_row["normalization_version"] = IMPACT_LABEL_SCHEMA_VERSION
            new_row["migration_version"] = MIGRATION_VERSION
            if direct_prompt:
                new_row["source_prompt_version"] = row.get("prompt_version", "")
                new_row["prompt_sha256"] = row.get("prompt_sha256", "") or legacy_prompt_sha
        migrated_rows.append(new_row)
    return new_columns, migrated_rows, counts, reason_reviews


def validate_fixed_weights(columns: Sequence[str], rows: Sequence[dict[str, str]]) -> None:
    prefixes: list[tuple[str, str, str]] = []
    for column in columns:
        if is_category_column(column):
            prefix = column[: -len("impact_type")]
            candidates = [(f"{prefix}trade_weight", f"{prefix}mp_weight")]
            if not prefix:
                candidates.insert(
                    0,
                    ("normalized_trade_weight", "normalized_mp_weight"),
                )
            for trade_column, mp_column in candidates:
                if trade_column in columns and mp_column in columns:
                    prefixes.append((column, trade_column, mp_column))
                    break
    for row_number, row in enumerate(rows, start=2):
        for type_column, trade_column, mp_column in prefixes:
            impact_type = (row.get(type_column) or "").strip().lower()
            trade = (row.get(trade_column) or "").strip()
            mp = (row.get(mp_column) or "").strip()
            if impact_type not in {"trade", "mp", "both", "none"}:
                continue
            if not trade or not mp:
                continue
            trade_value = float(trade)
            mp_value = float(mp)
            expected = {
                "trade": (1.0, 0.0),
                "mp": (0.0, 1.0),
                "none": (0.0, 0.0),
            }
            if impact_type in expected and (trade_value, mp_value) != expected[impact_type]:
                raise ValueError(
                    f"{type_column} row {row_number} violates fixed weights: "
                    f"{impact_type}=({trade_value}, {mp_value})"
                )
            if impact_type == "both" and abs(trade_value + mp_value - 1.0) > 1e-6:
                raise ValueError(
                    f"{type_column} row {row_number} both weights do not sum to one"
                )


def write_csv_atomic(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[dict[str, str]],
) -> str:
    handle, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(columns),
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        check_columns, check_rows = read_csv_rows(temp_path)
        if check_columns != list(columns) or len(check_rows) != len(rows):
            raise RuntimeError(f"Temporary CSV validation failed for {path}")
        validate_fixed_weights(check_columns, check_rows)
        after_sha = sha256_file(temp_path)
        os.replace(temp_path, path)
        return after_sha
    finally:
        if temp_path.exists():
            temp_path.unlink()


def migrate_file(
    path: Path,
    *,
    dry_run: bool,
) -> tuple[MigrationAudit, list[dict[str, str]]]:
    before_bytes = path.read_bytes()
    sha_before = sha256_bytes(before_bytes)
    columns, rows = read_csv_rows(path)
    key_columns = select_primary_key(columns)
    key_hash_before = primary_key_hash(rows, key_columns)
    new_columns, new_rows, counts, reason_reviews = migrate_rows(path, columns, rows)
    validate_fixed_weights(new_columns, new_rows)

    new_key_columns = tuple(rename_column(column) for column in key_columns)
    key_hash_after = primary_key_hash(new_rows, new_key_columns)
    if key_hash_after != key_hash_before:
        raise ValueError(f"Primary-key hash changed for {path}")

    transformed_columns = {
        column
        for column in columns
        if is_category_column(column)
        or is_raw_response_column(column)
        or "reason" in column.lower()
        or rename_column(column) != column
    }
    for source_column in columns:
        if source_column in transformed_columns:
            continue
        target_column = rename_column(source_column)
        before_values = [row.get(source_column, "") for row in rows]
        after_values = [row.get(target_column, "") for row in new_rows]
        if before_values != after_values:
            raise ValueError(f"Non-schema field changed: {path}:{source_column}")

    if len(rows) != len(new_rows):
        raise ValueError(f"Row count changed for {path}")

    changed = columns != new_columns or rows != new_rows
    sha_after = sha_before
    if changed:
        if dry_run:
            buffer = []
            buffer.append(",".join(new_columns))
            buffer.extend(
                ",".join(row.get(column, "") for column in new_columns) for row in new_rows
            )
            sha_after = sha256_bytes("\n".join(buffer).encode("utf-8"))
        else:
            sha_after = write_csv_atomic(path, new_columns, new_rows)

    audit = MigrationAudit(
        path=path.relative_to(PROJECT_ROOT).as_posix(),
        changed=changed,
        dry_run=dry_run,
        sha256_before=sha_before,
        sha256_after=sha_after,
        rows_before=len(rows),
        rows_after=len(new_rows),
        columns_before=len(columns),
        columns_after=len(new_columns),
        primary_key_columns="|".join(key_columns),
        primary_key_hash_before=key_hash_before,
        primary_key_hash_after=key_hash_after,
        reason_review_count=len(reason_reviews),
        **counts,
    )
    return audit, reason_reviews


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        json.loads(temp_path.read_text(encoding="utf-8"))
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_dicts_csv_atomic(
    path: Path,
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(columns), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def run_migration(
    paths: Sequence[Path],
    *,
    dry_run: bool,
    manifest_path: Path,
    audit_path: Path,
    reason_review_path: Path,
) -> dict[str, Any]:
    audits: list[MigrationAudit] = []
    reason_reviews: list[dict[str, str]] = []
    for path in paths:
        audit, reviews = migrate_file(path, dry_run=dry_run)
        audits.append(audit)
        reason_reviews.extend(reviews)

    payload = {
        "generated_at": utc_now(),
        "impact_label_schema_version": IMPACT_LABEL_SCHEMA_VERSION,
        "migration_version": MIGRATION_VERSION,
        "category_value_map": CATEGORY_VALUE_MAP,
        "dry_run": dry_run,
        "file_count": len(audits),
        "changed_file_count": sum(audit.changed for audit in audits),
        "files": [asdict(audit) for audit in audits],
        "reason_review_count": len(reason_reviews),
    }
    if not dry_run:
        write_json_atomic(manifest_path, payload)
        audit_rows = [asdict(audit) for audit in audits]
        write_dicts_csv_atomic(
            audit_path,
            audit_rows,
            list(MigrationAudit.__dataclass_fields__),
        )
        write_dicts_csv_atomic(
            reason_review_path,
            reason_reviews,
            ["path", "row_number", "column", "token", "context", "status"],
        )
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy Stage 2 mp/tr labels to trade/mp."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        default=[
            PROJECT_ROOT / "data",
            PROJECT_ROOT / "result",
            PROJECT_ROOT / "old data",
        ],
    )
    parser.add_argument("--paths", nargs="*", type=Path, default=None)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "manifests" / "trade_mp_schema_migration.json",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=PROJECT_ROOT / "logs" / "trade_mp_migration_audit.csv",
    )
    parser.add_argument(
        "--reason-review",
        type=Path,
        default=PROJECT_ROOT / "logs" / "trade_mp_reason_review.csv",
    )
    parser.add_argument("--prepare-backup", action="store_true")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=PROJECT_ROOT / "migration_backups" / "20260724_pre_trade_mp",
    )
    parser.add_argument("--git-commit", default="")
    parser.add_argument("--git-status-file", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roots = [
        path if path.is_absolute() else (PROJECT_ROOT / path)
        for path in args.roots
    ]
    if args.paths:
        paths = [
            (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
            for path in args.paths
        ]
    else:
        paths = discover_csvs(roots)

    if args.prepare_backup:
        status_lines: list[str] = []
        if args.git_status_file:
            status_path = (
                args.git_status_file
                if args.git_status_file.is_absolute()
                else PROJECT_ROOT / args.git_status_file
            )
            status_lines = status_path.read_text(encoding="utf-8").splitlines()
        else:
            completed = subprocess.run(
                ["git", "-c", "core.quotepath=false", "status", "--short"],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            status_lines = [
                line
                for line in completed.stdout.splitlines()
                if line != "?? src/migrate_trade_mp_schema.py"
            ]
        git_commit = args.git_commit
        if not git_commit:
            git_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
        backup_targets = sorted({*paths, *preflight_additional_targets()})
        backup = prepare_backup(
            backup_targets,
            args.backup_dir,
            git_commit=git_commit,
            git_status=status_lines,
        )
        print(
            json.dumps(
                {
                    "backup_dir": str(args.backup_dir),
                    "backup_file_count": len(backup["files"]),
                    "ppt_hash_count": len(backup["docs_ppt_hashes"]),
                    "archive": backup["archive"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    result = run_migration(
        paths,
        dry_run=args.dry_run,
        manifest_path=args.manifest,
        audit_path=args.audit,
        reason_review_path=args.reason_review,
    )
    print(
        json.dumps(
            {
                "dry_run": result["dry_run"],
                "file_count": result["file_count"],
                "changed_file_count": result["changed_file_count"],
                "reason_review_count": result["reason_review_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
