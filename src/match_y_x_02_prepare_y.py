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


DEPENDENT_REQUIRED = [
    "iso_o",
    "iso_d",
    "sector_amne",
    "value",
    "country_o",
    "country_d",
    "iso_o1",
    "iso_d1",
]


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
    require_columns(data.columns, DEPENDENT_REQUIRED, str(path))
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

    out = data[DEPENDENT_REQUIRED].copy()
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
