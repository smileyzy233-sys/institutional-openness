from __future__ import annotations

import copy
from pathlib import Path

from match_y_x_common import (
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
    assert "sample_trade_main" not in trade["trade"]["selected_controls"]
    assert "comlang_off" in trade["trade"]["candidate_controls"]
    assert "cultural_distance_religion" in trade["trade"]["candidate_controls"]
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
        ["value", "raw_trade_score", "tariff", "entry_time_o"]
    )
    assert found == ["entry_time_o", "tariff"]


def test_year_must_be_enabled_in_configuration():
    specs = load_matching_specs(project_directory())
    try:
        resolve_years(specs, [2020])
    except ValueError as exc:
        assert "not enabled" in str(exc)
    else:
        raise AssertionError("unconfigured years must be rejected")
