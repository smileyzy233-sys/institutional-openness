from __future__ import annotations

import pandas as pd

from conftest import load_script


def test_mp_output_contains_only_mp_score_and_no_trade_controls():
    y = pd.DataFrame(
        {
            "year": [2019],
            "iso_o": ["FRA"],
            "iso_d": ["DEU"],
            "iso_o_match": ["FRA"],
            "iso_d_match": ["DEU"],
            "sector_amne": [1],
            "value": [4.0],
        }
    )
    x = pd.DataFrame(
        {
            "year": [2019],
            "iso_o_match": ["FRA"],
            "iso_d_match": ["DEU"],
            "raw_trade_score": [0.2],
            "raw_mp_score": [0.3],
        }
    )
    out = load_script("match_y_x_05_build_mp.py").build_mp(y, x)
    assert out["raw_mp_score"].tolist() == [0.3]
    assert "raw_trade_score" not in out
    assert "tariff" not in out
    assert "comlang_off" not in out
    assert "entry_cost_o" not in out
