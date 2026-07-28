from __future__ import annotations

import pandas as pd

from conftest import load_script
from match_y_x_common import resolve_years


def test_prepare_x_handles_new_year_via_data_and_config_only(tmp_path):
    path = tmp_path / "data" / "processed" / "pairs.csv"
    path.parent.mkdir(parents=True)
    rows = []
    for year in [2020, 2021]:
        for origin in ["AAA", "BBB"]:
            for destination in ["AAA", "BBB"]:
                domestic = origin == destination
                rows.append(
                    {
                        "iso_o": origin,
                        "iso_d": destination,
                        "year": year,
                        "raw_trade_score": 0.0 if domestic else 0.2,
                        "raw_mp_score": 0.0 if domestic else 0.3,
                    }
                )
    pd.DataFrame(rows).to_csv(path, index=False)
    specs = {
        "years": [2020, 2021],
        "pair_year_source": "data/processed/pairs.csv",
        "expected_pairs_per_year": 4,
    }
    assert resolve_years(specs, [2021]) == [2021]
    out = load_script("match_y_x_03_prepare_x.py").prepare_x(
        tmp_path, specs, 2021
    )
    assert len(out) == 4
    assert out["year"].eq(2021).all()
    assert out.duplicated(["year", "iso_o_match", "iso_d_match"]).sum() == 0


def test_duplicate_pair_year_is_rejected(tmp_path):
    path = tmp_path / "pairs.csv"
    pd.DataFrame(
        {
            "iso_o": ["AAA", "AAA"],
            "iso_d": ["BBB", "BBB"],
            "year": [2020, 2020],
            "raw_trade_score": [0.2, 0.2],
            "raw_mp_score": [0.3, 0.3],
        }
    ).to_csv(path, index=False)
    specs = {
        "years": [2020],
        "pair_year_source": "pairs.csv",
        "expected_pairs_per_year": 0,
    }
    module = load_script("match_y_x_03_prepare_x.py")
    try:
        module.prepare_x(tmp_path, specs, 2020)
    except ValueError as exc:
        assert "not unique" in str(exc)
    else:
        raise AssertionError("duplicate X keys must be rejected")
