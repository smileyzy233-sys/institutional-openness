"""Prepare agreement and political-distance controls separately from raw scores."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    X_KEY,
    load_matching_specs,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
)


PAIR_CONTROL_COLUMNS = [
    "iso_o",
    "iso_d",
    "year",
    "trade_agreement_dummy",
    "idealpoint_abs_distance",
]


def prepare_pair_controls(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_config_path(project_dir, specs["pair_year_source"])
    data = pd.read_csv(path, usecols=PAIR_CONTROL_COLUMNS, low_memory=False)
    require_columns(data.columns, PAIR_CONTROL_COLUMNS, str(path))
    data = data.loc[data["year"].eq(year)].copy()
    if data.empty:
        raise ValueError(f"Year {year} is absent from pair controls: {path}")
    data = data.rename(
        columns={"iso_o": "iso_o_match", "iso_d": "iso_d_match"}
    )
    validate_unique(data, X_KEY, f"pair controls {year}")
    dummy = pd.to_numeric(data["trade_agreement_dummy"], errors="coerce")
    invalid_dummy = dummy.notna() & ~dummy.isin([0, 1])
    if invalid_dummy.any():
        raise ValueError("trade_agreement_dummy must contain only 0, 1, or missing")
    data["trade_agreement_dummy"] = dummy
    domestic = data["iso_o_match"].eq(data["iso_d_match"])
    if data.loc[domestic, "trade_agreement_dummy"].ne(0).any():
        raise ValueError("Domestic trade_agreement_dummy values must be zero")
    data["match_trade_agreement"] = (
        data["trade_agreement_dummy"].notna().astype(np.int8)
    )
    data["match_idealpoint"] = (
        data["idealpoint_abs_distance"].notna().astype(np.int8)
    )
    diagnostics = {
        "source": str(path),
        "year": year,
        "rows": len(data),
        "trade_agreement_coverage": float(
            data["trade_agreement_dummy"].notna().mean()
        ),
        "idealpoint_coverage": float(
            data["idealpoint_abs_distance"].notna().mean()
        ),
        "idealpoint_missing": int(
            data["idealpoint_abs_distance"].isna().sum()
        ),
    }
    return data[X_KEY + PAIR_CONTROL_COLUMNS[3:] + [
        "match_trade_agreement",
        "match_idealpoint",
    ]], diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    data, diagnostics = prepare_pair_controls(root, specs, args.year)
    print({**diagnostics, "columns": list(data.columns)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
