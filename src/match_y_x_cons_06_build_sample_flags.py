"""Build diagnostic completeness flags without choosing a final research sample."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from match_y_x_cons_common import assert_no_final_sample_flags


def build_trade_sample_flags(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    out["sample_trade_y_x"] = (
        out[["value", "raw_trade_score"]].notna().all(axis=1).astype(np.int8)
    )
    out["sample_trade_base_controls"] = (
        out[
            [
                "value",
                "raw_trade_score",
                "tariff",
                "trade_agreement_dummy",
                "idealpoint_abs_distance",
            ]
        ]
        .notna()
        .all(axis=1)
        .astype(np.int8)
    )
    for family in ["entry_cost", "entry_proc", "entry_time", "entry_tp"]:
        out[f"available_{family}"] = (
            out[[f"{family}_o", f"{family}_d"]]
            .notna()
            .all(axis=1)
            .astype(np.int8)
        )
    out["available_comlang"] = out["comlang_off"].notna().astype(np.int8)
    out["available_comrelig"] = out["comrelig"].notna().astype(np.int8)
    assert_no_final_sample_flags(out)
    return out


def build_mp_sample_flags(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    out["sample_mp_y_x"] = (
        out[["value", "raw_mp_score"]].notna().all(axis=1).astype(np.int8)
    )
    out["sample_mp_controls"] = (
        out[
            [
                "value",
                "raw_mp_score",
                "trade_agreement_dummy",
                "idealpoint_abs_distance",
            ]
        ]
        .notna()
        .all(axis=1)
        .astype(np.int8)
    )
    assert_no_final_sample_flags(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("equation", choices=["trade", "mp"])
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    data = pd.read_csv(args.input, low_memory=False)
    out = (
        build_trade_sample_flags(data)
        if args.equation == "trade"
        else build_mp_sample_flags(data)
    )
    flags = [
        column
        for column in out.columns
        if column.startswith(("sample_", "available_"))
    ]
    print(
        {
            "equation": args.equation,
            "rows": len(out),
            "flags": {column: int(out[column].sum()) for column in flags},
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
