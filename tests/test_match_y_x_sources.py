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


def test_prepare_y_derives_missing_identity_columns_from_crosswalk(tmp_path):
    source = tmp_path / "Explained_variable" / "icio2000.dta"
    source.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": ["ROM"],
            "iso_d": ["FRA"],
            "sector_amne": [1],
            "value": [2.0],
        }
    ).to_stata(source, write_index=False, version=118)
    crosswalk = tmp_path / "Explained_variable" / "iso_o.dta"
    pd.DataFrame(
        {
            "country_o": ["Romania", "France"],
            "iso3_o": ["ROM", "FRA"],
            "iso_o": [1, 2],
        }
    ).to_stata(crosswalk, write_index=False, version=118)
    specs = {
        "equations": {
            "trade": {
                "dependent_path_template": "Explained_variable/icio{year}.dta",
                "dependent_column": "value",
                "x_column": "raw_trade_score",
            }
        },
        "dependent_identity_crosswalk": "Explained_variable/iso_o.dta",
        "iso_aliases": {"ROM": "ROU"},
        "row_policy": {"drop_row": True, "keep_domestic": True},
    }

    module = load_script("match_y_x_02_prepare_y.py")
    out = module.prepare_y(tmp_path, specs, "trade", 2000)

    assert out.iloc[0]["country_o"] == "Romania"
    assert out.iloc[0]["country_d"] == "France"
    assert out.iloc[0]["iso_o1"] == 1
    assert out.iloc[0]["iso_d1"] == 2
    assert out.iloc[0]["iso_o"] == "ROM"
    assert out.iloc[0]["iso_o_match"] == "ROU"


def test_tariff_preflight_recognizes_normalized_stata_key_types(tmp_path):
    trade_path = tmp_path / "trade_y_x_2000.csv"
    pd.DataFrame(
        {
            "year": [2000, 2000],
            "iso_o1": [1.0, 1.0],
            "iso_d1": [2.0, 2.0],
            "sector_amne": [1, 20],
        }
    ).to_csv(trade_path, index=False)
    crosswalk = tmp_path / "Explained_variable" / "iso_o.dta"
    crosswalk.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso3_o": ["ARG", "AUS"],
            "iso_o": [1, 2],
            "country_o": ["Argentina", "Australia"],
        }
    ).to_stata(crosswalk, write_index=False, version=118)
    tariff_path = tmp_path / "control__variable" / "tariff2000.dta"
    tariff_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": ["ARG"],
            "iso_d": ["AUS"],
            "sector_amne": [1],
            "tariff": [0.05],
        }
    ).to_stata(tariff_path, write_index=False, version=118)
    specs = {
        "tariff_path_template": "control__variable/tariff_{year}.csv",
        "tariff_paths": {
            "2000": "control__variable/tariff2000.dta",
        },
        "dependent_identity_crosswalk": "Explained_variable/iso_o.dta",
        "iso_aliases": {"ROM": "ROU"},
        "acceptance": {},
    }
    tariff_module = load_script("match_y_x_cons_02_prepare_tariff.py")
    export_module = load_script("match_y_x_cons_07_validate_export.py")

    preflight = export_module._preflight_tariff_keys(
        tmp_path,
        specs,
        2000,
        trade_path,
        tariff_module,
    )

    assert preflight["source_format"] == "dta"
    assert preflight["source_key_type"] == "iso3_string"
    assert preflight["normalized_key_type"] == "numeric"
    assert preflight["unmapped_origin_codes"] == 0
    assert preflight["unmapped_destination_codes"] == 0
    assert preflight["duplicate_keys"] == 0
    assert preflight["key_dtype_compatible"] is True
