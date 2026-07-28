"""Preflight source validation for the dependent-variable/explanatory-variable match."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from match_y_x_common import (
    base_cli_parser,
    load_matching_specs,
    parse_year_arguments,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
    y_x_output_paths,
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
PAIR_REQUIRED = [
    "iso_o",
    "iso_d",
    "year",
    "raw_trade_score",
    "raw_mp_score",
]


def validate_sources(
    project_dir: Path,
    specs: dict[str, Any],
    years: list[int],
    *,
    output_root: Path | str | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "years": years,
        "config_path": specs["_config_path"],
        "row_policy": specs["row_policy"],
        "iso_aliases": specs["iso_aliases"],
        "sources": [],
        "outputs": [],
    }
    for year in years:
        for equation, equation_spec in specs["equations"].items():
            path = resolve_config_path(
                project_dir,
                equation_spec["dependent_path_template"],
                year=year,
            )
            if not path.exists():
                raise FileNotFoundError(
                    f"Missing {equation.upper()} dependent-variable file for "
                    f"{year}: {path}"
                )
            data = pd.read_stata(path, convert_categoricals=False)
            require_columns(data.columns, DEPENDENT_REQUIRED, str(path))
            validate_unique(
                data,
                ["iso_o", "iso_d", "sector_amne"],
                f"{equation.upper()} {year}",
            )
            report["sources"].append(
                {
                    "equation": equation,
                    "year": year,
                    "path": str(path),
                    "rows": len(data),
                    "columns": list(data.columns),
                    "duplicate_keys": 0,
                }
            )
        paths = y_x_output_paths(project_dir, specs, year, output_root)
        report["outputs"].extend(
            str(paths[name])
            for name in [
                "trade_csv",
                "trade_dta",
                "mp_csv",
                "mp_dta",
                "diagnostics",
                "manifest",
            ]
        )

    pair_path = resolve_config_path(project_dir, specs["pair_year_source"])
    if not pair_path.exists():
        raise FileNotFoundError(f"Missing country-pair score file: {pair_path}")
    pair = pd.read_csv(pair_path, usecols=PAIR_REQUIRED, low_memory=False)
    pair = pair.loc[pair["year"].isin(years)].copy()
    observed_years = sorted(int(value) for value in pair["year"].dropna().unique())
    missing_years = sorted(set(years).difference(observed_years))
    if missing_years:
        raise ValueError(
            f"Requested years are absent from {pair_path}: {missing_years}"
        )
    validate_unique(pair, ["iso_o", "iso_d", "year"], pair_path.name)
    expected = int(specs.get("expected_pairs_per_year", 0))
    rows_by_year = {
        int(year): int(count)
        for year, count in pair.groupby("year", sort=True).size().items()
    }
    if expected:
        bad = {year: count for year, count in rows_by_year.items() if count != expected}
        if bad:
            raise ValueError(
                f"Country-pair score rows must equal {expected} per year; observed={bad}"
            )
    report["sources"].append(
        {
            "source": "pair_year_scores",
            "path": str(pair_path),
            "years": observed_years,
            "rows_by_year": rows_by_year,
            "columns": PAIR_REQUIRED,
            "duplicate_keys": 0,
        }
    )
    return report


def main() -> int:
    parser = base_cli_parser("Validate sources for the Y-X matching pipeline.")
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    years = resolve_years(specs, parse_year_arguments(args.years))
    report = validate_sources(root, specs, years, output_root=args.output_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
