from __future__ import annotations

import pandas as pd
import pytest

from conftest import load_script


def _write_crosswalk(tmp_path) -> None:
    path = tmp_path / "Explained_variable" / "iso_o.dta"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "iso3_o": ["ARG", "AUS", "ROM"],
            "iso_o": [1, 2, 61],
            "country_o": ["Argentina", "Australia", "Romania"],
        }
    ).to_stata(path, write_index=False, version=118)


def _tariff_specs(*, dta_2000: bool = False) -> dict:
    specs = {
        "tariff_path_template": "control__variable/tariff_{year}.csv",
        "dependent_identity_crosswalk": "Explained_variable/iso_o.dta",
        "iso_aliases": {"ROM": "ROU"},
        "acceptance": {},
    }
    if dta_2000:
        specs["tariff_paths"] = {
            "2000": "control__variable/tariff2000.dta",
        }
    return specs


def test_numeric_csv_tariff_still_reads_and_matches(tmp_path):
    path = tmp_path / "control__variable" / "tariff_2019.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": [1, 1],
            "iso_d": [2, 1],
            "sector_amne": [1, 1],
            "tariff": [0.05, 0.0],
        }
    ).to_csv(path, index=False)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")

    tariff, diagnostics = module.prepare_tariff(
        tmp_path, _tariff_specs(), 2019
    )

    assert diagnostics["source_format"] == "csv"
    assert diagnostics["source_key_type"] == "numeric"
    assert diagnostics["output_key_type"] == "numeric_country_id"
    assert diagnostics["origin_unmapped"] == 0
    assert diagnostics["destination_unmapped"] == 0
    assert pd.api.types.is_integer_dtype(tariff["iso_o1"])
    assert pd.api.types.is_integer_dtype(tariff["iso_d1"])


def test_iso3_stata_tariff_converts_to_numeric_country_ids(tmp_path):
    _write_crosswalk(tmp_path)
    path = tmp_path / "control__variable" / "tariff2000.dta"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": ["ARG"],
            "iso_d": ["AUS"],
            "sector_amne": [1],
            "tariff": [0.05],
        }
    ).to_stata(path, write_index=False, version=118)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")

    tariff, diagnostics = module.prepare_tariff(
        tmp_path, _tariff_specs(dta_2000=True), 2000
    )

    assert tariff.loc[0, "iso_o1"] == 1
    assert tariff.loc[0, "iso_d1"] == 2
    assert diagnostics["source_format"] == "dta"
    assert diagnostics["source_key_type"] == "iso3_string"
    assert diagnostics["duplicate_keys"] == 0


def test_rom_and_rou_bridge_to_same_numeric_country_id(tmp_path):
    _write_crosswalk(tmp_path)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")
    tariff = pd.DataFrame(
        {
            "iso_o": ["ROM", "ROU"],
            "iso_d": ["ARG", "ARG"],
            "sector_amne": [1, 2],
            "tariff": [0.1, 0.2],
        }
    )

    normalized, diagnostics = module.normalize_tariff_country_keys(
        tariff, tmp_path, _tariff_specs(dta_2000=True)
    )

    assert normalized["iso_o1"].tolist() == [61, 61]
    assert normalized["iso_d1"].tolist() == [1, 1]
    assert diagnostics["origin_unmapped"] == 0


def test_unknown_iso3_tariff_code_is_rejected(tmp_path):
    _write_crosswalk(tmp_path)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")
    tariff = pd.DataFrame(
        {
            "iso_o": ["XXX"],
            "iso_d": ["AUS"],
            "sector_amne": [1],
            "tariff": [0.1],
        }
    )

    with pytest.raises(
        ValueError, match=r"Unmapped tariff origin ISO codes: \['XXX'\]"
    ):
        module.normalize_tariff_country_keys(
            tariff, tmp_path, _tariff_specs(dta_2000=True)
        )


def test_mixed_iso3_and_numeric_tariff_codes_are_rejected(tmp_path):
    _write_crosswalk(tmp_path)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")
    tariff = pd.DataFrame(
        {
            "iso_o": ["ARG", 1],
            "iso_d": ["AUS", "AUS"],
            "sector_amne": [1, 2],
            "tariff": [0.1, 0.2],
        }
    )

    with pytest.raises(
        ValueError, match="Mixed tariff country code types in iso_o"
    ):
        module.normalize_tariff_country_keys(
            tariff, tmp_path, _tariff_specs(dta_2000=True)
        )


def test_duplicate_normalized_tariff_key_is_rejected(tmp_path):
    path = tmp_path / "control__variable" / "tariff_2019.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": [1, 1],
            "iso_d": [2, 2],
            "sector_amne": [1, 1],
            "tariff": [0.05, 0.05],
        }
    ).to_csv(path, index=False)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")

    with pytest.raises(ValueError, match="not unique"):
        module.prepare_tariff(tmp_path, _tariff_specs(), 2019)


def test_tariff_left_join_preserves_rows_domestic_scores_and_missingness(
    tmp_path,
):
    path = tmp_path / "control__variable" / "tariff_2019.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": [1, 1],
            "iso_d": [2, 1],
            "sector_amne": [1, 1],
            "tariff": [0.05, 0.0],
        }
    ).to_csv(path, index=False)
    tariff_module = load_script("match_y_x_cons_02_prepare_tariff.py")
    tariff, _ = tariff_module.prepare_tariff(
        tmp_path, _tariff_specs(), 2019
    )
    base = pd.DataFrame(
        {
            "year": [2019, 2019, 2019],
            "iso_o": ["ARG", "ARG", "ARG"],
            "iso_d": ["AUS", "ARG", "AUS"],
            "iso_o1": [1.0, 1.0, 1.0],
            "iso_d1": [2.0, 1.0, 2.0],
            "sector_amne": [1, 1, 20],
            "raw_trade_score": [0.3, 0.0, 0.4],
        }
    )
    original_scores = base["raw_trade_score"].copy()
    common = load_script("match_y_x_cons_common.py")

    merged, diagnostic = common.left_merge_checked(
        base,
        tariff.drop(columns=["match_tariff"]),
        keys=["year", "iso_o1", "iso_d1", "sector_amne"],
        source="tariff",
        match_flag="match_tariff",
    )

    assert len(merged) == len(base)
    assert diagnostic["rows_before"] == diagnostic["rows_after"]
    assert merged.loc[0, "tariff"] == 0.05
    assert merged.loc[1, "tariff"] == 0.0
    assert merged.loc[2, "match_tariff"] == 0
    assert pd.isna(merged.loc[2, "tariff"])
    pd.testing.assert_series_equal(
        merged["raw_trade_score"], original_scores
    )


def test_tariff_rejects_negative_values(tmp_path):
    path = tmp_path / "control__variable" / "tariff_2020.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": [1],
            "iso_d": [2],
            "sector_amne": [1],
            "tariff": [-0.01],
        }
    ).to_csv(path, index=False)
    module = load_script("match_y_x_cons_02_prepare_tariff.py")

    with pytest.raises(ValueError, match="negative"):
        module.prepare_tariff(tmp_path, _tariff_specs(), 2020)
