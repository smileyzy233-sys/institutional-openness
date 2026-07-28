from __future__ import annotations

import pandas as pd

from conftest import load_script


def test_prepare_y_preserves_original_iso_and_filters_row(tmp_path):
    source = tmp_path / "Explained_variable" / "icio2020.dta"
    source.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "iso_o": "ROM",
                "iso_d": "FRA",
                "sector_amne": 1,
                "value": 2.0,
                "country_o": "Romania",
                "country_d": "France",
                "iso_o1": 1,
                "iso_d1": 2,
            },
            {
                "iso_o": "ROW",
                "iso_d": "FRA",
                "sector_amne": 1,
                "value": 3.0,
                "country_o": "Rest of world",
                "country_d": "France",
                "iso_o1": 99,
                "iso_d1": 2,
            },
            {
                "iso_o": "FRA",
                "iso_d": "FRA",
                "sector_amne": 1,
                "value": 0.0,
                "country_o": "France",
                "country_d": "France",
                "iso_o1": 2,
                "iso_d1": 2,
            },
        ]
    ).to_stata(source, write_index=False, version=118)
    specs = {
        "equations": {
            "trade": {
                "dependent_path_template": "Explained_variable/icio{year}.dta",
                "dependent_column": "value",
                "x_column": "raw_trade_score",
            }
        },
        "iso_aliases": {"ROM": "ROU"},
        "row_policy": {"drop_row": True, "keep_domestic": True},
    }
    module = load_script("match_y_x_02_prepare_y.py")
    out = module.prepare_y(tmp_path, specs, "trade", 2020)
    assert len(out) == 2
    rom = out.loc[out["iso_o"].eq("ROM")].iloc[0]
    assert rom["iso_o"] == "ROM"
    assert rom["iso_o_match"] == "ROU"
    assert not out[["iso_o", "iso_d"]].isin(["ROW"]).any().any()
    assert out.loc[out["iso_o"].eq("FRA"), "is_domestic_pair"].eq(1).all()
    assert out.duplicated(["year", "iso_o", "iso_d", "sector_amne"]).sum() == 0


def test_prepare_y_rejects_negative_value(tmp_path):
    source = tmp_path / "Explained_variable" / "amne2020.dta"
    source.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": ["FRA"],
            "iso_d": ["DEU"],
            "sector_amne": [1],
            "value": [-1.0],
            "country_o": ["France"],
            "country_d": ["Germany"],
            "iso_o1": [1],
            "iso_d1": [2],
        }
    ).to_stata(source, write_index=False, version=118)
    specs = {
        "equations": {
            "mp": {
                "dependent_path_template": "Explained_variable/amne{year}.dta",
                "dependent_column": "value",
                "x_column": "raw_mp_score",
            }
        },
        "iso_aliases": {"ROM": "ROU"},
        "row_policy": {"drop_row": True, "keep_domestic": True},
    }
    module = load_script("match_y_x_02_prepare_y.py")
    try:
        module.prepare_y(tmp_path, specs, "mp", 2020)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative dependent values must be rejected")
