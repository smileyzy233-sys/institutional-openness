"""Merge tariff, pair controls, and Gravity candidates onto trade Y-X."""

from __future__ import annotations

import argparse

import pandas as pd

from match_y_x_common import (
    X_KEY,
    Y_KEY,
    load_matching_specs,
    load_sibling_script,
    project_directory,
    resolve_years,
    validate_unique,
)
from match_y_x_cons_common import left_merge_checked, read_y_x_base


def merge_trade_controls(
    trade_y_x: pd.DataFrame,
    tariff: pd.DataFrame,
    pair_controls: pd.DataFrame,
    gravity: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    diagnostics: list[dict] = []
    data, diagnostic = left_merge_checked(
        trade_y_x,
        tariff.drop(columns=["match_tariff"]),
        keys=["year", "iso_o1", "iso_d1", "sector_amne"],
        source="tariff",
        match_flag="match_tariff",
    )
    diagnostics.append(diagnostic)
    pair_fields = [
        "year",
        "iso_o_match",
        "iso_d_match",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "match_trade_agreement",
        "match_idealpoint",
    ]
    data, diagnostic = left_merge_checked(
        data,
        pair_controls[pair_fields],
        keys=X_KEY,
        source="pair_controls",
        match_flag="match_pair_controls",
    )
    diagnostics.append(diagnostic)
    data, diagnostic = left_merge_checked(
        data,
        gravity,
        keys=X_KEY,
        source="gravity_candidates",
        match_flag="match_gravity",
    )
    diagnostics.append(diagnostic)
    validate_unique(data, Y_KEY, "trade Y-X-controls")
    return data, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    trade_y_x, _ = read_y_x_base(root, specs, "trade", args.year)
    pair_module = load_sibling_script(
        "match_y_x_cons_01_prepare_pair_controls.py"
    )
    tariff_module = load_sibling_script("match_y_x_cons_02_prepare_tariff.py")
    gravity_module = load_sibling_script("match_y_x_cons_03_prepare_gravity.py")
    pair, _ = pair_module.prepare_pair_controls(root, specs, args.year)
    tariff, _ = tariff_module.prepare_tariff(root, specs, args.year)
    codes = set(trade_y_x["iso_o_match"]) | set(trade_y_x["iso_d_match"])
    gravity, _ = gravity_module.prepare_gravity(
        root, specs, [args.year], codes
    )
    data, diagnostics = merge_trade_controls(
        trade_y_x, tariff, pair, gravity
    )
    print(
        {
            "year": args.year,
            "rows": len(data),
            "merges": diagnostics,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
