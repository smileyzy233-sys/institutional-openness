"""Merge only agreement and political-distance controls onto MP Y-X."""

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
from match_y_x_cons_common import (
    assert_mp_has_no_trade_controls,
    left_merge_checked,
    read_y_x_base,
)


def merge_mp_controls(
    mp_y_x: pd.DataFrame,
    pair_controls: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
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
        mp_y_x,
        pair_controls[pair_fields],
        keys=X_KEY,
        source="pair_controls",
        match_flag="match_pair_controls",
    )
    validate_unique(data, Y_KEY, "MP Y-X-controls")
    assert_mp_has_no_trade_controls(data)
    return data, [diagnostic]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    mp_y_x, _ = read_y_x_base(root, specs, "mp", args.year)
    pair_module = load_sibling_script(
        "match_y_x_cons_01_prepare_pair_controls.py"
    )
    pair, _ = pair_module.prepare_pair_controls(root, specs, args.year)
    data, diagnostics = merge_mp_controls(mp_y_x, pair)
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
