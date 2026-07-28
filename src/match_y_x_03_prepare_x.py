"""Prepare only the raw trade and MP explanatory scores needed for Y-X matching."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from match_y_x_common import (
    X_KEY,
    forbidden_y_x_columns,
    load_matching_specs,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
)


X_SOURCE_COLUMNS = [
    "iso_o",
    "iso_d",
    "year",
    "raw_trade_score",
    "raw_mp_score",
]


def prepare_x(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
) -> pd.DataFrame:
    path = resolve_config_path(project_dir, specs["pair_year_source"])
    if not path.exists():
        raise FileNotFoundError(f"Missing country-pair score file: {path}")
    data = pd.read_csv(path, usecols=X_SOURCE_COLUMNS, low_memory=False)
    require_columns(data.columns, X_SOURCE_COLUMNS, str(path))
    data = data.loc[data["year"].eq(year)].copy()
    if data.empty:
        raise ValueError(f"Year {year} is absent from country-pair scores: {path}")
    data = data.rename(
        columns={"iso_o": "iso_o_match", "iso_d": "iso_d_match"}
    )
    validate_unique(data, X_KEY, f"X scores {year}")
    expected = int(specs.get("expected_pairs_per_year", 0))
    if expected and len(data) != expected:
        raise ValueError(
            f"X scores for {year} must contain {expected} directed pairs; "
            f"observed={len(data)}"
        )
    score_columns = ["raw_trade_score", "raw_mp_score"]
    if data[score_columns].isna().any().any():
        missing = data[score_columns].isna().sum().to_dict()
        raise ValueError(f"X scores contain missing values for {year}: {missing}")
    domestic = data["iso_o_match"].eq(data["iso_d_match"])
    nonzero_domestic = data.loc[
        domestic
        & (
            data["raw_trade_score"].ne(0)
            | data["raw_mp_score"].ne(0)
        ),
        X_KEY + score_columns,
    ]
    if not nonzero_domestic.empty:
        raise ValueError(
            "Domestic raw trade/MP scores must be zero; examples="
            f"{nonzero_domestic.head(10).to_dict('records')}"
        )
    out = data[X_KEY + score_columns].reset_index(drop=True)
    forbidden = forbidden_y_x_columns(out.columns)
    if forbidden:
        raise AssertionError(f"Prepared X unexpectedly contains controls: {forbidden}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    data = prepare_x(root, specs, args.year)
    print(f"X {args.year}: rows={len(data)}, columns={list(data.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
