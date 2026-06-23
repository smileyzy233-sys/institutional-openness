import pandas as pd
import pytest

import config
from conftest import write_stage1_success_manifest
from utils import check_stage1_gate, write_csv


def test_stage1_gate_rejects_missing_success(temp_pipeline):
    write_csv(pd.DataFrame([{"provision_id": "P1"}]), config.PROVISIONS_MASTER_PATH)
    with pytest.raises(RuntimeError, match="缺少"):
        check_stage1_gate()


def test_stage1_gate_rejects_unresolved_record(temp_pipeline):
    write_csv(pd.DataFrame([{"provision_id": "P1"}]), config.PROVISIONS_MASTER_PATH)
    stage1_final = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "final_is_institutional_opening": 1,
                "final_dominant_dimension": "rules",
                "stage1_unresolved": True,
                "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            }
        ]
    )
    write_stage1_success_manifest(stage1_final)
    with pytest.raises(RuntimeError, match="未解决"):
        check_stage1_gate()
