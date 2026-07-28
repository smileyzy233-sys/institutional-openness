from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = (
    PROJECT_ROOT
    / "result"
    / "model_inputs"
    / "match_y_x_cons"
    / "legacy_2019_v1"
    / "2019"
)
LEGACY_ARTIFACTS_AVAILABLE = all(
    path.exists()
    for path in [
        PROJECT_ROOT
        / "result"
        / "refactor_baseline"
        / "baseline_manifest_2019.json",
        LEGACY_ROOT / "build_manifest.json",
        LEGACY_ROOT / "trade_y_x_cons_2019.csv",
        LEGACY_ROOT / "mp_y_x_cons_2019.csv",
    ]
)
pytestmark = pytest.mark.skipif(
    not LEGACY_ARTIFACTS_AVAILABLE,
    reason=(
        "2019 legacy integration artifacts are intentionally gitignored; "
        "generate them with the documented matching commands."
    ),
)


def test_legacy_manifest_reports_zero_overlap_mismatches():
    path = LEGACY_ROOT / "build_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    comparison = manifest["legacy_overlap_validation"]
    assert comparison["trade"]["rows"] == 115520
    assert comparison["mp"]["rows"] == 236816
    assert not any(comparison["trade"]["mismatch_counts"].values())
    assert not any(comparison["mp"]["mismatch_counts"].values())


def test_legacy_raw_scores_are_rowwise_equal_to_delivered_results():
    old_root = PROJECT_ROOT / "result" / "regression_2019"
    new_root = LEGACY_ROOT
    for equation, old_name, score in [
        ("trade", "trade_cost_2019_matched.csv", "raw_trade_score"),
        ("mp", "mp_cost_2019_matched.csv", "raw_mp_score"),
    ]:
        keys = ["year", "iso_o", "iso_d", "sector_amne", score]
        old = pd.read_csv(old_root / old_name, usecols=keys, low_memory=False)
        new = pd.read_csv(
            new_root / f"{equation}_y_x_cons_2019.csv",
            usecols=keys,
            low_memory=False,
        )
        pd.testing.assert_frame_equal(old, new, check_dtype=False, check_exact=True)


def test_baseline_manifest_exists_and_does_not_copy_inputs():
    path = (
        PROJECT_ROOT
        / "result"
        / "refactor_baseline"
        / "baseline_manifest_2019.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 13
    assert all("sha256" in item and "rows" in item for item in manifest["files"])
