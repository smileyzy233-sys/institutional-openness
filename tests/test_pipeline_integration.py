import pandas as pd

import config
from conftest import load_script
from utils import check_stage1_gate, write_csv


def test_heuristic_split_pipeline_to_final_weights(temp_pipeline):
    provisions = pd.DataFrame(
        [
            {"provision_id": "P1", "provision_text": "trade rules and market access"},
            {"provision_id": "P2", "provision_text": "dialogue and cooperation"},
            {"provision_id": "P3", "provision_text": "customs procedure and facilitation"},
        ]
    )
    write_csv(provisions, config.PROVISIONS_MASTER_PATH)

    stage1a_model = load_script("03_stage1a_llm_code_institutional.py")
    stage1a_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage1a_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("04_stage1a_compare_dual_model_results.py").run()
    load_script("05_stage1a_llm_review_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("06_stage1a_finalize.py").run()

    stage1b_model = load_script("03_stage1b_llm_code_dimension.py")
    stage1b_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage1b_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("04_stage1b_compare_dual_model_results.py").run()
    load_script("05_stage1b_llm_review_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("06_stage1b_finalize.py").run()
    load_script("06_stage1_finalize.py").run()
    check_stage1_gate()

    stage2_model = load_script("07_stage2_llm_code_trade_investment.py")
    stage2_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage2_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("08_stage2_compare_dual_model_results.py").run()
    load_script("09_stage2_llm_review_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("10_finalize_weights.py").run()

    final = pd.read_csv(config.FINAL_PROVISION_WEIGHTS_PATH, encoding=config.CSV_ENCODING)
    assert len(final) == 3
    assert "stage1a_decision_source" in final.columns
    assert "stage1b_decision_source" in final.columns
