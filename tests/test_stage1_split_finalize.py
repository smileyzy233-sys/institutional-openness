import pandas as pd
import pytest

import config
from conftest import load_script, write_stage1_success_manifest
from utils import write_csv


def test_stage1_final_merge_assigns_none_for_non_institutional(temp_pipeline):
    provisions = pd.DataFrame(
        [
            {"provision_id": "P1", "provision_text": "trade rules"},
            {"provision_id": "P2", "provision_text": "dialogue"},
        ]
    )
    write_csv(provisions, config.PROVISIONS_MASTER_PATH)
    stage1_seed = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "final_is_institutional_opening": 1,
                "final_dominant_dimension": "rules",
                "stage1_unresolved": False,
            },
            {
                "provision_id": "P2",
                "final_is_institutional_opening": 0,
                "final_dominant_dimension": "none",
                "stage1_unresolved": False,
            },
        ]
    )
    write_stage1_success_manifest(stage1_seed)
    load_script("06_stage1_finalize.py").run()
    final = pd.read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH, encoding=config.CSV_ENCODING)
    by_id = final.set_index("provision_id")
    assert by_id.loc["P2", "final_dominant_dimension"] == "none"
    assert by_id.loc["P1", "final_dominant_dimension"] == "rules"


def test_stage1_final_merge_rejects_missing_or_extra_stage1b_ids(temp_pipeline):
    provisions = pd.DataFrame(
        [
            {"provision_id": "P1", "provision_text": "trade rules"},
            {"provision_id": "P2", "provision_text": "dialogue"},
        ]
    )
    write_csv(provisions, config.PROVISIONS_MASTER_PATH)
    stage1_seed = pd.DataFrame(
        [
            {"provision_id": "P1", "final_is_institutional_opening": 1, "final_dominant_dimension": "rules"},
            {"provision_id": "P2", "final_is_institutional_opening": 0, "final_dominant_dimension": "none"},
        ]
    )
    write_stage1_success_manifest(stage1_seed)
    stage1b = pd.read_csv(config.STAGE1B_FINAL_CLASSIFICATION_PATH, encoding=config.CSV_ENCODING)
    write_csv(stage1b.iloc[0:0], config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    with pytest.raises(RuntimeError, match="Stage 1B"):
        load_script("06_stage1_finalize.py").run()

    write_stage1_success_manifest(stage1_seed)
    stage1b = pd.read_csv(config.STAGE1B_FINAL_CLASSIFICATION_PATH, encoding=config.CSV_ENCODING)
    extra = stage1b.iloc[[0]].copy()
    extra["provision_id"] = "P2"
    write_csv(pd.concat([stage1b, extra], ignore_index=True), config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    with pytest.raises(RuntimeError, match="Stage 1B"):
        load_script("06_stage1_finalize.py").run()
