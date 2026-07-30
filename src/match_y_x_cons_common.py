"""Shared helpers for matching controls onto already-built Y-X datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    GRAVITY_TRADE_CONTROL_COLUMNS,
    X_KEY,
    Y_KEY,
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


def read_y_x_base(
    project_dir: Path,
    specs: dict[str, Any],
    equation: str,
    year: int,
    output_root: Path | str | None = None,
) -> tuple[pd.DataFrame, Path]:
    paths = y_x_output_paths(project_dir, specs, year, output_root)
    path = paths[f"{equation}_csv"]
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {equation} Y-X input for {year}: {path}. "
            "Run `python run_pipeline.py match-y-x --years "
            f"{year}` first."
        )
    data = pd.read_csv(path, low_memory=False)
    require_columns(
        data.columns,
        Y_KEY
        + X_KEY
        + ["value", f"raw_{'trade' if equation == 'trade' else 'mp'}_score"],
        str(path),
    )
    validate_unique(data, Y_KEY, path.name)
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
