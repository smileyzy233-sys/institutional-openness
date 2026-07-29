"""Shared configuration, validation, and export helpers for Y-X matching."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


MATCHING_CONFIG_PATH = Path("configs") / "matching_specs.json"
Y_KEY = ["year", "iso_o", "iso_d", "sector_amne"]
X_KEY = ["year", "iso_o_match", "iso_d_match"]
FORBIDDEN_Y_X_COLUMNS = {
    "tariff",
    "trade_agreement_dummy",
    "idealpoint_abs_distance",
    "comlang_off",
    "comrelig",
    "cultural_distance_religion",
    "sample_trade_main",
    "sample_mp_main",
}


def project_directory() -> Path:
    return Path(__file__).resolve().parents[1]


def load_sibling_script(filename: str):
    path = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load matching module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_iso3(
    value: object, aliases: dict[str, str] | None = None
) -> str:
    """Normalize an ISO-like code and apply only explicitly configured aliases."""
    if pd.isna(value):
        return ""
    code = str(value).strip().upper()
    if code in {"", "NAN", "NONE", "<NA>"}:
        return ""
    return (aliases or {}).get(code, code)


def normalize_iso_series(
    series: pd.Series, aliases: dict[str, str]
) -> pd.Series:
    return series.map(lambda value: normalize_iso3(value, aliases))


def _assert_project_relative(path_text: str, field: str) -> None:
    path = Path(path_text)
    if path.is_absolute():
        raise ValueError(f"{field} must be relative to the project root: {path_text}")
    if ".." in path.parts:
        raise ValueError(f"{field} must not escape the project root: {path_text}")


def load_matching_specs(
    project_dir: Path | str | None = None,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(project_dir).resolve() if project_dir is not None else project_directory()
    path = (
        Path(config_path).resolve()
        if config_path is not None
        else root / MATCHING_CONFIG_PATH
    )
    if not path.exists():
        raise FileNotFoundError(f"Matching configuration not found: {path}")
    specs = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "years",
        "row_policy",
        "iso_aliases",
        "equations",
        "pair_year_source",
        "gravity_path",
        "output_root",
        "control_specs",
    }
    missing = required.difference(specs)
    if missing:
        raise ValueError(f"Matching configuration is missing keys: {sorted(missing)}")
    for field in [
        "pair_year_source",
        "gravity_path",
        "output_root",
    ]:
        _assert_project_relative(str(specs[field]), field)
    tariff_template = specs.get("tariff_path_template")
    tariff_paths = specs.get("tariff_paths", {})
    if tariff_template is None and not tariff_paths:
        raise ValueError(
            "Matching configuration requires tariff_path_template or tariff_paths"
        )
    if tariff_template is not None:
        _assert_project_relative(str(tariff_template), "tariff_path_template")
    for year, path_text in tariff_paths.items():
        _assert_project_relative(str(path_text), f"tariff_paths.{year}")
    identity_crosswalk = specs.get("dependent_identity_crosswalk")
    if identity_crosswalk is not None:
        _assert_project_relative(
            str(identity_crosswalk), "dependent_identity_crosswalk"
        )
    for equation, equation_spec in specs["equations"].items():
        if equation not in {"trade", "mp"}:
            raise ValueError(f"Unsupported equation in configuration: {equation}")
        for field in ["dependent_path_template", "dependent_column", "x_column"]:
            if field not in equation_spec:
                raise ValueError(f"equations.{equation} is missing {field}")
        _assert_project_relative(
            str(equation_spec["dependent_path_template"]),
            f"equations.{equation}.dependent_path_template",
        )
    configured_years = [int(year) for year in specs["years"]]
    if len(set(configured_years)) != len(configured_years):
        raise ValueError("Configured matching years contain duplicates")
    specs["years"] = configured_years
    specs["_config_path"] = str(path)
    return specs


def resolve_years(
    specs: dict[str, Any], requested_years: Iterable[int] | None
) -> list[int]:
    configured = [int(year) for year in specs["years"]]
    years = (
        configured
        if requested_years is None
        else list(dict.fromkeys(int(year) for year in requested_years))
    )
    unavailable = sorted(set(years).difference(configured))
    if unavailable:
        raise ValueError(
            "Requested years are not enabled in configs/matching_specs.json: "
            f"{unavailable}"
        )
    if not years:
        raise ValueError("At least one matching year is required")
    return years


def resolve_config_path(
    project_dir: Path,
    path_template: str,
    *,
    year: int | None = None,
) -> Path:
    rendered = path_template.format(year=year) if year is not None else path_template
    _assert_project_relative(rendered, "configured path")
    return (project_dir / rendered).resolve()


def resolve_tariff_path(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
) -> Path:
    """Resolve a year-specific tariff override, falling back to the template."""
    override = specs.get("tariff_paths", {}).get(str(year))
    if override is not None:
        return resolve_config_path(project_dir, str(override))
    template = specs.get("tariff_path_template")
    if template is None:
        raise ValueError(f"No tariff path is configured for {year}")
    return resolve_config_path(project_dir, str(template), year=year)


def resolve_output_root(
    project_dir: Path,
    specs: dict[str, Any],
    output_root: Path | str | None,
) -> Path:
    if output_root is None:
        return resolve_config_path(project_dir, str(specs["output_root"]))
    path = Path(output_root)
    return path.resolve() if path.is_absolute() else (project_dir / path).resolve()


def validate_unique(data: pd.DataFrame, keys: list[str], source: str) -> int:
    missing = sorted(set(keys).difference(data.columns))
    if missing:
        raise ValueError(f"{source} is missing key columns: {missing}")
    duplicate_count = int(data.duplicated(keys).sum())
    if duplicate_count:
        examples = (
            data.loc[data.duplicated(keys, keep=False), keys]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"{source} is not unique on {keys}; duplicates={duplicate_count}; "
            f"examples={examples}"
        )
    return duplicate_count


def require_columns(
    columns: Iterable[str], required: Iterable[str], source: str
) -> None:
    missing = sorted(set(required).difference(columns))
    if missing:
        raise ValueError(f"{source} is missing required columns: {missing}")


def forbidden_y_x_columns(columns: Iterable[str]) -> list[str]:
    forbidden: list[str] = []
    for column in columns:
        if (
            column in FORBIDDEN_Y_X_COLUMNS
            or column.startswith("entry_")
            or column.startswith("available_")
        ):
            forbidden.append(column)
    return sorted(forbidden)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_git_commit(project_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def y_x_output_paths(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
    output_root: Path | str | None = None,
) -> dict[str, Path]:
    root = resolve_output_root(project_dir, specs, output_root)
    directory = root / "match_y_x" / str(year)
    return {
        "directory": directory,
        "trade_csv": directory / f"trade_y_x_{year}.csv",
        "trade_dta": directory / f"trade_y_x_{year}.dta",
        "mp_csv": directory / f"mp_y_x_{year}.csv",
        "mp_dta": directory / f"mp_y_x_{year}.dta",
        "diagnostics": directory / "matching_diagnostics.json",
        "manifest": directory / "build_manifest.json",
    }


def check_output_collisions(paths: Iterable[Path], force: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        rendered = "\n".join(f"  - {path}" for path in existing)
        raise FileExistsError(
            "Refusing to overwrite existing matching outputs without --force:\n"
            f"{rendered}"
        )


def assert_stata_columns(columns: Iterable[str]) -> None:
    too_long = [column for column in columns if len(column) > 32]
    if too_long:
        raise ValueError(f"Stata variable names exceed 32 characters: {too_long}")


def _stata_ready(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    assert_stata_columns(out.columns)
    for column in out.columns:
        series = out[column]
        if pd.api.types.is_bool_dtype(series.dtype):
            out[column] = series.astype(np.int8)
        elif isinstance(series.dtype, pd.StringDtype):
            out[column] = series.astype(object)
        elif str(series.dtype).startswith(("Int", "UInt")):
            out[column] = (
                series.astype(float)
                if series.isna().any()
                else series.astype(np.int64)
            )
    return out


def write_csv_dta(data: pd.DataFrame, csv_path: Path, dta_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(csv_path, index=False, encoding="utf-8-sig")
    _stata_ready(data).to_stata(
        dta_path,
        write_index=False,
        version=118,
    )


def validate_csv_dta_pair(
    csv_path: Path,
    dta_path: Path,
    core_columns: list[str],
) -> dict[str, Any]:
    csv_data = pd.read_csv(csv_path, low_memory=False)
    dta_data = pd.read_stata(dta_path, convert_categoricals=False)
    require_columns(csv_data.columns, core_columns, csv_path.name)
    require_columns(dta_data.columns, core_columns, dta_path.name)
    if len(csv_data) != len(dta_data):
        raise AssertionError(
            f"CSV/DTA row mismatch: {csv_path.name}={len(csv_data)}, "
            f"{dta_path.name}={len(dta_data)}"
        )
    for column in core_columns:
        left = csv_data[column]
        right = dta_data[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            equal = np.isclose(
                pd.to_numeric(left, errors="coerce"),
                pd.to_numeric(right, errors="coerce"),
                rtol=1e-7,
                atol=1e-7,
                equal_nan=True,
            )
        else:
            equal = left.fillna("").astype(str).eq(right.fillna("").astype(str))
        if not bool(np.asarray(equal).all()):
            raise AssertionError(
                f"CSV/DTA core column mismatch in {column}: {csv_path} vs {dta_path}"
            )
    return {
        "rows": len(csv_data),
        "csv_sha256": file_sha256(csv_path),
        "dta_sha256": file_sha256(dta_path),
    }


def parse_year_arguments(values: list[str] | None) -> list[int] | None:
    if values is None:
        return None
    years: list[int] = []
    for value in values:
        for token in str(value).split(","):
            token = token.strip()
            if token:
                years.append(int(token))
    return years


def base_cli_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--years", nargs="+", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser
