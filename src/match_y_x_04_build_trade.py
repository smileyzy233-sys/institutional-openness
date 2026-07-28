"""Left-join ICIO Y to raw_trade_score without adding controls."""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from match_y_x_common import (
    X_KEY,
    Y_KEY,
    forbidden_y_x_columns,
    load_matching_specs,
    load_sibling_script,
    project_directory,
    resolve_years,
    validate_unique,
)


def build_trade(y_data: pd.DataFrame, x_data: pd.DataFrame) -> pd.DataFrame:
    before = len(y_data)
    merged = y_data.merge(
        x_data[X_KEY + ["raw_trade_score"]],
        on=X_KEY,
        how="left",
        validate="many_to_one",
        indicator="_x_merge",
    )
    if len(merged) != before:
        raise AssertionError("Trade Y-X merge changed the ICIO row count")
    merged["matched_x"] = merged["_x_merge"].eq("both").astype(np.int8)
    merged["uses_iso_bridge"] = (
        merged["iso_o"].ne(merged["iso_o_match"])
        | merged["iso_d"].ne(merged["iso_d_match"])
    ).astype(np.int8)
    merged = merged.drop(columns="_x_merge")
    forbidden = forbidden_y_x_columns(merged.columns)
    if forbidden:
        raise AssertionError(f"Trade Y-X output contains controls: {forbidden}")
    validate_unique(merged, Y_KEY, "trade Y-X output")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    prepare_y = load_sibling_script("match_y_x_02_prepare_y.py")
    prepare_x = load_sibling_script("match_y_x_03_prepare_x.py")
    data = build_trade(
        prepare_y.prepare_y(root, specs, "trade", args.year),
        prepare_x.prepare_x(root, specs, args.year),
    )
    print(
        f"trade Y-X {args.year}: rows={len(data)}, "
        f"match_rate={data['matched_x'].mean():.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
