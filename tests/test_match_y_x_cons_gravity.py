from __future__ import annotations

import numpy as np
import pandas as pd

from conftest import load_script


GRAVITY_COLUMNS = [
    "year",
    "iso3_o",
    "iso3_d",
    "country_exists_o",
    "country_exists_d",
    "gatt_o",
    "gatt_d",
    "fta_wto",
    "entry_cost_o",
    "entry_cost_d",
    "entry_proc_o",
    "entry_proc_d",
    "entry_time_o",
    "entry_time_d",
    "entry_tp_o",
    "entry_tp_d",
    "comlang_off",
    "comlang_ethno",
    "comrelig",
    "scaled_sci_2021",
]


def test_gravity_chunk_filter_unique_and_derived_missing_preserved(tmp_path):
    path = tmp_path / "control__variable" / "gravity.csv"
    path.parent.mkdir(parents=True)
    rows = []
    for origin in ["AAA", "BBB"]:
        for destination in ["AAA", "BBB"]:
            rows.append(
                {
                    "year": 2020,
                    "iso3_o": origin,
                    "iso3_d": destination,
                    "country_exists_o": 1,
                    "country_exists_d": 1,
                    "gatt_o": 1,
                    "gatt_d": np.nan if destination == "BBB" else 1,
                    "fta_wto": 0,
                    "entry_cost_o": 1.0,
                    "entry_cost_d": np.nan if destination == "BBB" else 2.0,
                    "entry_proc_o": 3.0,
                    "entry_proc_d": 4.0,
                    "entry_time_o": 5.0,
                    "entry_time_d": 6.0,
                    "entry_tp_o": 8.0,
                    "entry_tp_d": 10.0,
                    "comlang_off": 0,
                    "comlang_ethno": 0,
                    "comrelig": np.nan if origin == "BBB" else 0.25,
                    "scaled_sci_2021": 10.0,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)
    candidates = GRAVITY_COLUMNS[5:] + [
        "both_gatt",
        "cultural_distance_religion",
    ]
    specs = {
        "gravity_path": "control__variable/gravity.csv",
        "gravity": {
            "chunksize": 2,
            "read_columns": GRAVITY_COLUMNS,
            "candidate_controls": candidates,
            "derived_candidates": {
                "both_gatt": "gatt_o * gatt_d",
                "cultural_distance_religion": "1 - comrelig",
            },
        },
    }
    module = load_script("match_y_x_cons_03_prepare_gravity.py")
    data, diagnostics = module.prepare_gravity(
        tmp_path, specs, [2020], {"AAA", "BBB"}
    )
    assert len(data) == 4
    assert data.duplicated(["year", "iso_o_match", "iso_d_match"]).sum() == 0
    assert data.loc[data["comrelig"].eq(0.25), "cultural_distance_religion"].eq(
        0.75
    ).all()
    assert data.loc[data["comrelig"].isna(), "cultural_distance_religion"].isna().all()
    assert data.loc[data["entry_cost_d"].isna(), "entry_cost_d"].isna().all()
    assert data.loc[data["gatt_d"].eq(1), "both_gatt"].eq(1).all()
    assert data.loc[data["gatt_d"].isna(), "both_gatt"].isna().all()
    assert diagnostics["rows_selected"] == 4


def test_unsupported_derived_candidate_expression_is_rejected():
    module = load_script("match_y_x_cons_03_prepare_gravity.py")
    try:
        module.materialize_derived_candidates(
            pd.DataFrame({"gatt_o": [1], "gatt_d": [1]}),
            {"unsafe": "gatt_o / gatt_d"},
        )
    except ValueError as exc:
        assert "Unsupported derived Gravity candidate expression" in str(exc)
    else:
        raise AssertionError("unsupported derived expressions must be rejected")
