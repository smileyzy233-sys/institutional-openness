import pandas as pd

import config
from conftest import load_script, write_stage1_success_manifest
from utils import write_csv


def test_finalize_marks_non_institutional_not_applicable_and_averages_both(temp_pipeline):
    write_csv(
        pd.DataFrame(
            [
                {"provision_id": "P1", "provision_text": "trade investment"},
                {"provision_id": "P2", "provision_text": "cooperation"},
            ]
        ),
        config.PROVISIONS_MASTER_PATH,
    )
    stage1_final = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "provision_text": "trade investment",
                "chapter_name": "",
                "section_name": "",
                "final_is_institutional_opening": 1,
                "final_dominant_dimension": "rules",
                "stage1_decision_source": "dual_model_consensus",
                "stage1_resolution_method": "dual_model_consensus",
                "stage1_unresolved": False,
            },
            {
                "provision_id": "P2",
                "provision_text": "cooperation",
                "chapter_name": "",
                "section_name": "",
                "final_is_institutional_opening": 0,
                "final_dominant_dimension": "none",
                "stage1_decision_source": "dual_model_consensus",
                "stage1_resolution_method": "dual_model_consensus",
                "stage1_unresolved": False,
            },
        ]
    )
    stage1_hash = write_stage1_success_manifest(stage1_final)
    write_csv(
        pd.DataFrame(
            [
                {
                    "provision_id": "P1",
                    "model_a_impact_type": "both",
                    "model_b_impact_type": "both",
                    "type_match": True,
                    "needs_arbitration": False,
                    "model_a_trade_weight": 0.7,
                    "model_a_investment_weight": 0.3,
                    "model_b_trade_weight": 0.5,
                    "model_b_investment_weight": 0.5,
                    "both_trade_weight_abs_diff": 0.2,
                    "both_investment_weight_abs_diff": 0.2,
                    "stage1_final_sha256": stage1_hash,
                    "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
                }
            ]
        ),
        config.STAGE2_COMPARISON_PATH,
    )
    load_script("10_finalize_weights.py").run()
    final = pd.read_csv(config.FINAL_PROVISION_WEIGHTS_PATH, encoding=config.CSV_ENCODING).set_index("provision_id")
    assert final.loc["P2", "final_impact_type"] == "not_applicable"
    assert final.loc["P2", "effective_trade_weight"] == 0
    assert final.loc["P1", "final_impact_type"] == "both"
    assert final.loc["P1", "final_trade_weight"] == 0.6
    assert final.loc["P1", "final_investment_weight"] == 0.4
