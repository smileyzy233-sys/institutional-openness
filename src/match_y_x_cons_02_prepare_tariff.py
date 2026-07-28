"""Prepare directional sector tariffs without zero-filling structural gaps."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    load_matching_specs,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
)


TARIFF_SOURCE_COLUMNS = ["iso_o", "iso_d", "sector_amne", "tariff"]
TARIFF_KEY = ["year", "iso_o1", "iso_d1", "sector_amne"]


def prepare_tariff(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_config_path(
        project_dir, specs["tariff_path_template"], year=year
    )
    if not path.exists():
        raise FileNotFoundError(f"Missing tariff file for {year}: {path}")
    tariff = pd.read_csv(path, usecols=TARIFF_SOURCE_COLUMNS, low_memory=False)
    require_columns(tariff.columns, TARIFF_SOURCE_COLUMNS, str(path))
    tariff = tariff.rename(columns={"iso_o": "iso_o1", "iso_d": "iso_d1"})
    tariff.insert(0, "year", np.int16(year))
    validate_unique(tariff, TARIFF_KEY, f"tariff {year}")
    values = pd.to_numeric(tariff["tariff"], errors="coerce")
    if values.lt(0).any():
        raise ValueError(f"Tariff file contains negative values: {path}")
    tariff["tariff"] = values
    tariff["match_tariff"] = np.int8(1)
    acceptance = specs.get("acceptance", {}).get(str(year), {})
    expected_range = acceptance.get("tariff_sectors")
    observed = sorted(int(value) for value in tariff["sector_amne"].unique())
    if expected_range:
        expected = list(range(int(expected_range[0]), int(expected_range[1]) + 1))
        if observed != expected:
            raise ValueError(
                f"Tariff sectors for {year} must be {expected_range[0]}-"
                f"{expected_range[1]}; observed={observed}"
            )
    if 20 in observed:
        raise ValueError("Tariff sector 20 must remain structurally absent")
    diagnostics = {
        "source": str(path),
        "year": year,
        "rows": len(tariff),
        "sectors": observed,
        "missing_tariff": int(tariff["tariff"].isna().sum()),
        "negative_tariff": int(tariff["tariff"].lt(0).sum()),
    }
    return tariff[TARIFF_KEY + ["tariff", "match_tariff"]], diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    data, diagnostics = prepare_tariff(root, specs, args.year)
    print({**diagnostics, "columns": list(data.columns)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
