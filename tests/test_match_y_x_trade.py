from __future__ import annotations

import pandas as pd

from conftest import load_script


def test_trade_left_join_retains_y_rows_and_has_no_controls():
    y = pd.DataFrame(
        {
            "year": [2019, 2019],
            "iso_o": ["ROM", "FRA"],
            "iso_d": ["FRA", "FRA"],
            "iso_o_match": ["ROU", "FRA"],
            "iso_d_match": ["FRA", "FRA"],
            "sector_amne": [1, 1],
            "value": [2.0, 0.0],
        }
    )
    x = pd.DataFrame(
        {
            "year": [2019, 2019],
            "iso_o_match": ["ROU", "FRA"],
            "iso_d_match": ["FRA", "FRA"],
            "raw_trade_score": [0.25, 0.0],
            "raw_mp_score": [0.5, 0.0],
        }
    )
    module = load_script("match_y_x_04_build_trade.py")
    out = module.build_trade(y, x)
    assert len(out) == len(y)
    assert out["matched_x"].eq(1).all()
    assert out.loc[out["iso_o"].eq("ROM"), "uses_iso_bridge"].eq(1).all()
    assert "raw_mp_score" not in out
    assert "trade_agreement_dummy" not in out
    assert "tariff" not in out


def test_trade_left_join_preserves_unmatched_y_row():
    y = pd.DataFrame(
        {
            "year": [2019],
            "iso_o": ["AAA"],
            "iso_d": ["BBB"],
            "iso_o_match": ["AAA"],
            "iso_d_match": ["BBB"],
            "sector_amne": [1],
            "value": [1.0],
        }
    )
    x = pd.DataFrame(
        columns=[
            "year",
            "iso_o_match",
            "iso_d_match",
            "raw_trade_score",
        ]
    )
    out = load_script("match_y_x_04_build_trade.py").build_trade(y, x)
    assert len(out) == 1
    assert out["matched_x"].eq(0).all()
    assert out["raw_trade_score"].isna().all()
