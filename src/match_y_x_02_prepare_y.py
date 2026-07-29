"""Prepare ICIO or AMNE dependent-variable data without matching controls."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    Y_KEY,
    load_matching_specs,
    normalize_iso_series,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
)


DEPENDENT_CORE_REQUIRED = [
    "iso_o",
    "iso_d",
    "sector_amne",
    "value",
]
DEPENDENT_IDENTITY_COLUMNS = [
    "country_o",
    "country_d",
    "iso_o1",
    "iso_d1",
]


def add_missing_identity_columns(
    data: pd.DataFrame,
    project_dir: Path,
    specs: dict[str, Any],
    source: Path,
) -> pd.DataFrame:
    missing = [
        column for column in DEPENDENT_IDENTITY_COLUMNS if column not in data
    ]
    if not missing:
        return data
    crosswalk_text = specs.get("dependent_identity_crosswalk")
    if not crosswalk_text:
        raise ValueError(
            f"{source} is missing identity columns {missing}, but "
            "dependent_identity_crosswalk is not configured"
        )
    crosswalk_path = resolve_config_path(project_dir, str(crosswalk_text))
    if not crosswalk_path.exists():
        raise FileNotFoundError(
            f"Dependent-variable identity crosswalk not found: {crosswalk_path}"
        )
    suffix = crosswalk_path.suffix.lower()
    if suffix == ".dta":
        crosswalk = pd.read_stata(
            crosswalk_path, convert_categoricals=False
        )
    elif suffix == ".csv":
        crosswalk = pd.read_csv(crosswalk_path, low_memory=False)
    else:
        raise ValueError(
            f"Unsupported identity crosswalk format: {crosswalk_path.suffix}"
        )
    required = ["iso3_o", "country_o", "iso_o"]
    require_columns(crosswalk.columns, required, str(crosswalk_path))
    validate_unique(crosswalk, ["iso3_o"], str(crosswalk_path))
    country_map = crosswalk.set_index("iso3_o")["country_o"]
    numeric_map = crosswalk.set_index("iso3_o")["iso_o"]
    out = data.copy()
    derived = {
        "country_o": out["iso_o"].map(country_map),
        "country_d": out["iso_d"].map(country_map),
        "iso_o1": out["iso_o"].map(numeric_map),
        "iso_d1": out["iso_d"].map(numeric_map),
    }
    for column in missing:
        out[column] = derived[column]
        if out[column].isna().any():
            code_column = (
                "iso_o"
                if column in {"country_o", "iso_o1"}
                else "iso_d"
            )
            codes = (
                out.loc[out[column].isna(), code_column]
                .drop_duplicates()
                .head(10)
                .tolist()
            )
            raise ValueError(
                f"Could not derive {column} from {crosswalk_path}; "
                f"unmatched codes={codes}"
            )
    return out


def prepare_y(
    project_dir: Path,
    specs: dict[str, Any],
    equation: str,
    year: int,
) -> pd.DataFrame:
    if equation not in specs["equations"]:
        raise ValueError(f"Unknown equation: {equation}")
    equation_spec = specs["equations"][equation]
    path = resolve_config_path(
        project_dir,
        equation_spec["dependent_path_template"],
        year=year,
    )
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {equation.upper()} dependent-variable file for {year}: {path}"
        )
    data = pd.read_stata(path, convert_categoricals=False)
    require_columns(data.columns, DEPENDENT_CORE_REQUIRED, str(path))
    data = add_missing_identity_columns(data, project_dir, specs, path)
    require_columns(
        data.columns,
        DEPENDENT_CORE_REQUIRED + DEPENDENT_IDENTITY_COLUMNS,
        str(path),
    )
    validate_unique(
        data,
        ["iso_o", "iso_d", "sector_amne"],
        f"{equation.upper()} source {year}",
    )
    value_column = equation_spec["dependent_column"]
    values = pd.to_numeric(data[value_column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{path.name} contains missing {value_column} values")
    if values.lt(0).any():
        raise ValueError(f"{path.name} contains negative {value_column} values")

    out = data[
        DEPENDENT_CORE_REQUIRED + DEPENDENT_IDENTITY_COLUMNS
    ].copy()
    out.insert(0, "year", np.int16(year))
    out[value_column] = values
    aliases = specs["iso_aliases"]
    out["iso_o_match"] = normalize_iso_series(out["iso_o"], aliases)
    out["iso_d_match"] = normalize_iso_series(out["iso_d"], aliases)
    out["is_domestic_pair"] = out["iso_o"].eq(out["iso_d"]).astype(np.int8)
    out["is_row_pair"] = (
        out["iso_o"].eq("ROW") | out["iso_d"].eq("ROW")
    ).astype(np.int8)
    if specs["row_policy"].get("drop_row", True):
        out = out.loc[out["is_row_pair"].eq(0)].copy()
    if not specs["row_policy"].get("keep_domestic", True):
        out = out.loc[out["is_domestic_pair"].eq(0)].copy()
    out["positive_value"] = out[value_column].gt(0).astype(np.int8)
    ordered = [
        "year",
        "iso_o",
        "iso_d",
        "iso_o_match",
        "iso_d_match",
        "country_o",
        "country_d",
        "iso_o1",
        "iso_d1",
        "sector_amne",
        value_column,
        "positive_value",
        "is_domestic_pair",
        "is_row_pair",
    ]
    out = out[ordered].reset_index(drop=True)
    validate_unique(out, Y_KEY, f"prepared {equation.upper()} {year}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("equation", choices=["trade", "mp"])
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    data = prepare_y(root, specs, args.equation, args.year)
    print(
        f"{args.equation} {args.year}: rows={len(data)}, "
        f"columns={list(data.columns)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
