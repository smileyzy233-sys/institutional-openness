from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd

from match_y_x_common import (
    GRAVITY_TRADE_CONTROL_COLUMNS,
    _stata_ready,
    forbidden_y_x_columns,
    load_matching_specs,
    project_directory,
    resolve_years,
)
from match_y_x_cons_common import get_control_spec


def test_matching_config_defines_three_control_versions():
    root = project_directory()
    specs = load_matching_specs(root)
    assert set(specs["control_specs"]) == {
        "legacy_2019_v1",
        "trade_candidate_pool_v1",
        "mp_controls_v1",
    }
    trade = get_control_spec(specs, "trade_candidate_pool_v1")
    assert trade["trade"]["selected_controls"] == [
        "tariff",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
    ]
    assert "sample_trade_main" not in trade["trade"]["selected_controls"]
    candidates = trade["trade"]["candidate_controls"]
    assert len(candidates) == len(set(candidates))
    assert set(candidates) == GRAVITY_TRADE_CONTROL_COLUMNS
    assert {
        "both_gatt",
        "both_wto",
        "both_eu",
        "fta_wto",
        "rta_type",
        "comlang_ethno",
        "comleg_posttrans",
        "scaled_sci_2021",
        "diplo_disagreement",
    }.issubset(candidates)
    derived = specs["gravity"]["derived_candidates"]
    assert set(derived).issubset(candidates)
    direct_candidates = set(candidates).difference(derived)
    assert direct_candidates.issubset(specs["gravity"]["read_columns"])
    assert specs["iso_aliases"] == {"ROM": "ROU"}


def test_candidate_list_can_change_without_matching_code_change():
    specs = load_matching_specs(project_directory())
    modified = copy.deepcopy(specs)
    candidates = modified["control_specs"]["trade_candidate_pool_v1"]["trade"][
        "candidate_controls"
    ]
    candidates.remove("entry_tp_o")
    candidates.append("test_candidate")
    resolved = get_control_spec(modified, "trade_candidate_pool_v1")
    assert "entry_tp_o" not in resolved["trade"]["candidate_controls"]
    assert "test_candidate" in resolved["trade"]["candidate_controls"]


def test_y_x_forbidden_control_detection():
    found = forbidden_y_x_columns(
        [
            "value",
            "raw_trade_score",
            "tariff",
            "entry_time_o",
            "gatt_o",
            "scaled_sci_2021",
        ]
    )
    assert found == ["entry_time_o", "gatt_o", "scaled_sci_2021", "tariff"]


def test_year_must_be_enabled_in_configuration():
    specs = load_matching_specs(project_directory())
    try:
        resolve_years(specs, [2020])
    except ValueError as exc:
        assert "not enabled" in str(exc)
    else:
        raise AssertionError("unconfigured years must be rejected")


def test_stata_ready_converts_all_missing_object_column_to_numeric_missing():
    data = pd.DataFrame(
        {"empire": pd.Series([None, None], dtype=object), "value": [1.0, 2.0]}
    )
    ready = _stata_ready(data)
    assert pd.api.types.is_float_dtype(ready["empire"])
    assert ready["empire"].isna().all()
    assert np.allclose(ready["value"], data["value"])
