import pandas as pd
import pytest

import config
from conftest import write_stage1_success_manifest
from utils import check_stage1b_gate, write_csv


def test_stage1b_gate_rejects_changed_stage1a_hash(temp_pipeline):
    write_csv(pd.DataFrame([{"provision_id": "P1"}]), config.PROVISIONS_MASTER_PATH)
    write_stage1_success_manifest(
        pd.DataFrame(
            [
                {
                    "provision_id": "P1",
                    "final_is_institutional_opening": 1,
                    "final_dominant_dimension": "rules",
                    "stage1_unresolved": False,
                }
            ]
        )
    )
    stage1a = pd.read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH, encoding=config.CSV_ENCODING)
    stage1a.loc[0, "final_is_institutional_opening"] = 0
    write_csv(stage1a, config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    with pytest.raises(RuntimeError, match="Stage 1A|stage1a"):
        check_stage1b_gate()
