from __future__ import annotations

import pandas as pd

from conftest import load_script


def test_tariff_sector_20_remains_missing_after_left_join(tmp_path):
    path = tmp_path / "control__variable" / "tariff_2019.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "iso_o": [1],
            "iso_d": [2],
            "sector_amne": [1],
            "tariff": [0.05],
        }
    ).to_csv(path, index=False)
    specs = {
        "tariff_path_template": "control__variable/tariff_{year}.csv",
        "acceptance": {},
    }
    tariff_module = load_script("match_y_x_cons_02_prepare_tariff.py")
    tariff, _ = tariff_module.prepare_tariff(tmp_path, specs, 2019)
    base = pd.DataFrame(
        {
            "year": [2019, 2019],
            "iso_o1": [1, 1],
            "iso_d1": [2, 2],
            "sector_amne": [1, 20],
        }
    )
    common = load_script("match_y_x_cons_common.py")
    merged, diagnostic = common.left_merge_checked(
        base,
        tariff.drop(columns=["match_tariff"]),
        keys=["year", "iso_o1", "iso_d1", "sector_amne"],
        source="tariff",
        match_flag="match_tariff",
    )
    assert len(merged) == 2
    sector20 = merged["sector_amne"].eq(20)
    assert merged.loc[sector20, "tariff"].isna().all()
    assert merged.loc[sector20, "match_tariff"].eq(0).all()
    assert diagnostic["rows_before"] == diagnostic["rows_after"]


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
    specs = {
        "tariff_path_template": "control__variable/tariff_{year}.csv",
        "acceptance": {},
    }
    module = load_script("match_y_x_cons_02_prepare_tariff.py")
    try:
        module.prepare_tariff(tmp_path, specs, 2020)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative tariffs must be rejected")
