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

    stage1a_model = load_script("measure_x_02_stage1a_code_institutional.py")
    stage1a_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage1a_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("measure_x_03_stage1a_compare_models.py").run()
    load_script("measure_x_04_stage1a_arbitrate_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("measure_x_05_stage1a_finalize.py").run()

    stage1b_model = load_script("measure_x_06_stage1b_code_dimension.py")
    stage1b_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage1b_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("measure_x_07_stage1b_compare_models.py").run()
    load_script("measure_x_08_stage1b_arbitrate_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("measure_x_09_stage1b_finalize.py").run()
    load_script("measure_x_10_stage1_finalize.py").run()
    check_stage1_gate()

    stage2_model = load_script("measure_x_11_stage2_code_trade_mp.py")
    stage2_model.run(model_role="A", provider="heuristic", model_name="heuristic_a", resume=False)
    stage2_model.run(model_role="B", provider="heuristic", model_name="heuristic_b", resume=False)
    load_script("measure_x_12_stage2_compare_models.py").run()
    load_script("measure_x_13_stage2_arbitrate_conflicts.py").run(provider="heuristic", model_name="heuristic_arbitration", resume=False)
    load_script("measure_x_14_finalize_provision_weights.py").run()

    final = pd.read_csv(config.FINAL_PROVISION_WEIGHTS_PATH, encoding=config.CSV_ENCODING)
    assert len(final) == 3
    assert "stage1a_decision_source" in final.columns
    assert "stage1b_decision_source" in final.columns
    assert set(final["impact_label_schema_version"]) == {
        config.IMPACT_LABEL_SCHEMA_VERSION
    }
