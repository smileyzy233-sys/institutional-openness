import pandas as pd

import config
from conftest import load_script, write_stage1_success_manifest
from utils import write_csv


def stage2_row(pid, impact, t, i, role, stage1_hash):
    return {
        "provision_id": pid,
        "final_dominant_dimension": "rules",
        "impact_type": impact,
        "raw_trade_weight": t,
        "raw_investment_weight": i,
        "normalized_trade_weight": t,
        "normalized_investment_weight": i,
        "reason": "r",
        "confidence": 0.8,
        "parse_status": "ok",
        "validation_status": "ok",
        "model_role": role,
        "model_provider": "mock",
        "model_name": f"mock_{role}",
        "prompt_version": config.STAGE2_PROMPT_VERSION,
        "stage1_final_sha256": stage1_hash,
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": "test",
        "raw_response": "{}",
    }


def test_stage2_compare_only_type_triggers_arbitration(temp_pipeline):
    write_csv(
        pd.DataFrame(
            [
                {"provision_id": "P1", "provision_text": "trade investment"},
                {"provision_id": "P2", "provision_text": "trade"},
            ]
        ),
        config.PROVISIONS_MASTER_PATH,
    )
    stage1_final = pd.DataFrame(
        [
            {"provision_id": "P1", "final_is_institutional_opening": 1, "final_dominant_dimension": "rules", "stage1_unresolved": False},
            {"provision_id": "P2", "final_is_institutional_opening": 1, "final_dominant_dimension": "rules", "stage1_unresolved": False},
        ]
    )
    stage1_hash = write_stage1_success_manifest(stage1_final)
    write_csv(
        pd.DataFrame([stage2_row("P1", "both", 0.7, 0.3, "A", stage1_hash), stage2_row("P2", "mp", 1.0, 0.0, "A", stage1_hash)]),
        config.STAGE2_MODEL_A_RESULTS_PATH,
    )
    write_csv(
        pd.DataFrame([stage2_row("P1", "both", 0.2, 0.8, "B", stage1_hash), stage2_row("P2", "tr", 0.0, 1.0, "B", stage1_hash)]),
        config.STAGE2_MODEL_B_RESULTS_PATH,
    )
    load_script("08_stage2_compare_dual_model_results.py").run()
    comparison = pd.read_csv(config.STAGE2_COMPARISON_PATH, encoding=config.CSV_ENCODING)
    by_id = comparison.set_index("provision_id")
    assert not bool(by_id.loc["P1", "needs_arbitration"])
    assert bool(by_id.loc["P2", "needs_arbitration"])
    assert by_id.loc["P1", "both_trade_weight_abs_diff"] == 0.5
