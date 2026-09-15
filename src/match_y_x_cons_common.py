"""Shared helpers for matching controls onto already-built Y-X datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    GRAVITY_TRADE_CONTROL_COLUMNS,
    X_KEY,
    Y_KEY,
    country_pair_masks,
    effective_row_policy,
    file_sha256,
    require_columns,
    resolve_output_root,
    validate_unique,
    y_x_output_paths,
)


TRADE_EXCLUSIVE_CONTROLS = {"tariff"} | GRAVITY_TRADE_CONTROL_COLUMNS
FINAL_SAMPLE_FLAGS = {"sample_trade_main", "sample_mp_main"}


def get_control_spec(
    specs: dict[str, Any], control_spec: str
) -> dict[str, Any]:
    available = specs["control_specs"]
    if control_spec not in available:
        raise ValueError(
            f"Unknown control spec '{control_spec}'. "
            f"Available specs: {sorted(available)}"
        )
    selected = available[control_spec]
    equations = selected.get("equations", [])
    if not equations or not set(equations).issubset({"trade", "mp"}):
        raise ValueError(f"Invalid equations in control spec {control_spec}: {equations}")
    for equation in equations:
        equation_spec = selected.get(equation)
        if not isinstance(equation_spec, dict):
            raise ValueError(f"{control_spec} is missing an {equation} configuration")
        for field in ["selected_controls", "candidate_controls"]:
            if field not in equation_spec:
                raise ValueError(f"{control_spec}.{equation} is missing {field}")
    return selected


def control_output_paths(
    project_dir: Path,
    specs: dict[str, Any],
    control_spec: str,
    year: int,
    output_root: Path | str | None = None,
) -> dict[str, Path]:
    root = resolve_output_root(project_dir, specs, output_root)
    directory = root / "match_y_x_cons" / control_spec / str(year)
    return {
        "directory": directory,
        "trade_csv": directory / f"trade_y_x_cons_{year}.csv",
        "trade_dta": directory / f"trade_y_x_cons_{year}.dta",
        "mp_csv": directory / f"mp_y_x_cons_{year}.csv",
        "mp_dta": directory / f"mp_y_x_cons_{year}.dta",
        "diagnostics": directory / f"matching_diagnostics_{year}.csv",
        "dictionary": directory / f"variable_dictionary_{year}.csv",
        "manifest": directory / "build_manifest.json",
        "readme": directory / "README.md",
    }


def validate_y_x_policy(
    project_dir: Path,
    specs: dict[str, Any],
    equation: str,
    year: int,
    output_root: Path | str | None = None,
) -> dict[str, Any]:
    """Require evidence that an existing Y-X base uses the requested sample policy."""
    paths = y_x_output_paths(project_dir, specs, year, output_root)
    path = paths[f"{equation}_csv"]
    manifest_path = paths["manifest"]
    rebuild = (
        "Rebuild required / 需要重新构建 Y-X：先运行 `python run_pipeline.py "
        f"match-y-x --years {year} --output-root <new-version-root>`，"
        "再以同一 output-root 匹配控制变量。不会自动覆盖旧数据；--force 不能绕过配置检查。"
    )
    if not path.exists():
        raise FileNotFoundError(f"Missing {equation} Y-X input: {path}. {rebuild}")
    if not manifest_path.exists():
        raise ValueError(f"Y-X build manifest is missing: {manifest_path}. {rebuild}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise ValueError(f"Cannot read Y-X manifest: {manifest_path}. {rebuild}") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"Y-X manifest must be an object: {manifest_path}. {rebuild}")
    recorded = manifest.get("row_policy", {})
    if not isinstance(recorded, dict) or any(
        type(recorded.get(key)) is not bool for key in ("drop_row", "keep_domestic")
    ):
        raise ValueError(f"Y-X manifest lacks an explicit row_policy. {rebuild}")
    requested = effective_row_policy(specs)
    if effective_row_policy(manifest) != requested:
        raise ValueError(
            f"Y-X row_policy mismatch: recorded={recorded}, requested={requested}; "
            f"input={path}. {rebuild}"
        )
    if manifest.get("year") != year or manifest.get("iso_aliases") != specs["iso_aliases"]:
        raise ValueError(f"Y-X year or ISO alias configuration mismatch: {path}. {rebuild}")
    if manifest.get("output_sha256", {}).get(f"{equation}_csv") != file_sha256(path):
        raise ValueError(f"Y-X CSV SHA256 does not match its manifest: {path}. {rebuild}")
    return manifest


def read_y_x_base(
    project_dir: Path,
    specs: dict[str, Any],
    equation: str,
    year: int,
    output_root: Path | str | None = None,
) -> tuple[pd.DataFrame, Path]:
    manifest = validate_y_x_policy(project_dir, specs, equation, year, output_root)
    paths = y_x_output_paths(project_dir, specs, year, output_root)
    path = paths[f"{equation}_csv"]
    data = pd.read_csv(path, low_memory=False)
    require_columns(
        data.columns,
        Y_KEY
        + X_KEY
        + ["value", f"raw_{'trade' if equation == 'trade' else 'mp'}_score"],
        str(path),
    )
    validate_unique(data, Y_KEY, path.name)
    row, domestic = country_pair_masks(data)
    policy = effective_row_policy(specs)
    if (policy["drop_row"] and row.any()) or (
        not policy["keep_domestic"] and domestic.any()
    ):
        raise ValueError(
            f"Y-X data violates its row_policy: {path}. Rebuild required / "
            "需要重新构建 Y-X；控制变量步骤不补删基表行。"
        )
    if manifest.get("output_rows", {}).get(equation) != len(data):
        raise ValueError(f"Y-X row count differs from its manifest: {path}. Rebuild required")
    return data, path


def left_merge_checked(
    base: pd.DataFrame,
    right: pd.DataFrame,
    *,
    keys: list[str],
    source: str,
    match_flag: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    validate_unique(right, keys, source)
    before = len(base)
    right_data = right.copy()
    right_data["_source_row_matched"] = np.int8(1)
    merged = base.merge(
        right_data,
        on=keys,
        how="left",
        validate="many_to_one",
        indicator="_control_merge",
    )
    after = len(merged)
    if after != before:
        raise AssertionError(
            f"{source} merge changed row count: before={before}, after={after}"
        )
    merged[match_flag] = (
        merged["_source_row_matched"].fillna(0).astype(np.int8)
    )
    match_rate = float(merged[match_flag].mean())
    new_columns = [
        column
        for column in right.columns
        if column not in keys
    ]
    missing_rates = {
        column: float(merged[column].isna().mean()) for column in new_columns
    }
    merged = merged.drop(columns=["_source_row_matched", "_control_merge"])
    return merged, {
        "source": source,
        "merge_keys": keys,
        "rows_before": before,
        "rows_after": after,
        "right_rows": len(right),
        "right_key_duplicates": 0,
        "match_flag": match_flag,
        "match_rate": match_rate,
        "missing_rates": missing_rates,
    }


def assert_mp_has_no_trade_controls(data: pd.DataFrame) -> None:
    present = sorted(TRADE_EXCLUSIVE_CONTROLS.intersection(data.columns))
    if present:
        raise ValueError(f"MP output contains trade-only controls: {present}")


def assert_no_final_sample_flags(data: pd.DataFrame) -> None:
    present = sorted(FINAL_SAMPLE_FLAGS.intersection(data.columns))
    if present:
        raise ValueError(
            "Candidate-control outputs must not assert a final research sample: "
            f"{present}"
        )
