from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import config  # noqa: E402
from utils import ensure_directories, sha256_file, write_csv, write_json  # noqa: E402


def load_script(filename: str):
    path = SRC_DIR / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def temp_pipeline(monkeypatch, tmp_path):
    root = tmp_path
    interim = root / "data" / "interim"
    stage1 = interim / "stage1"
    stage1a = stage1 / "stage1a"
    stage1b = stage1 / "stage1b"
    stage2 = interim / "stage2"
    processed = root / "data" / "processed"
    manifests = root / "manifests"
    prompts = root / "prompts"
    logs = root / "logs"
    need_dummy = root / "data" / "need_dummy"

    path_values = {
        "PROJECT_ROOT": root,
        "INTERIM_DIR": interim,
        "STAGE1_INTERIM_DIR": stage1,
        "STAGE1A_INTERIM_DIR": stage1a,
        "STAGE1B_INTERIM_DIR": stage1b,
        "STAGE2_INTERIM_DIR": stage2,
        "PROCESSED_DIR": processed,
        "NEED_DUMMY_DIR": need_dummy,
        "PROMPT_DIR": prompts,
        "LOG_DIR": logs,
        "STAGE1_LOG_DIR": logs / "stage1",
        "STAGE1A_LOG_DIR": logs / "stage1a",
        "STAGE1B_LOG_DIR": logs / "stage1b",
        "STAGE2_LOG_DIR": logs / "stage2",
        "LLM_LOG_DIR": logs / "llm_calls",
        "MANIFEST_DIR": manifests,
        "PROVISIONS_MASTER_PATH": interim / "provisions_master.csv",
        "AGREEMENT_MATRIX_PATH": interim / "agreement_matrix.csv",
        "AGREEMENT_PROVISION_LONG_PATH": interim / "agreement_provision_long.csv",
        "AGREEMENTS_MASTER_PATH": interim / "agreements_master.csv",
        "BILATERAL_PANEL_PATH": interim / "bilateral_panel.csv",
        "STAGE1A_MODEL_A_RESULTS_PATH": stage1a / "stage1a_model_a_results.csv",
        "STAGE1A_MODEL_B_RESULTS_PATH": stage1a / "stage1a_model_b_results.csv",
        "STAGE1A_TECHNICAL_ERROR_QUEUE_PATH": stage1a / "stage1a_technical_error_queue.csv",
        "STAGE1A_COMPARISON_PATH": stage1a / "stage1a_dual_model_comparison.csv",
        "STAGE1A_CONFLICT_QUEUE_PATH": stage1a / "stage1a_conflict_queue.csv",
        "STAGE1A_ARBITRATION_RESULTS_PATH": stage1a / "stage1a_arbitration_results.csv",
        "STAGE1A_MANUAL_REVIEW_QUEUE_PATH": stage1a / "stage1a_manual_review_queue.csv",
        "STAGE1A_FINAL_CLASSIFICATION_PATH": processed / "stage1a_final_classification.csv",
        "STAGE1A_SUCCESS_PATH": processed / "STAGE1A_SUCCESS",
        "STAGE1A_MANIFEST_PATH": manifests / "stage1a_manifest.json",
        "STAGE1B_MODEL_A_RESULTS_PATH": stage1b / "stage1b_model_a_results.csv",
        "STAGE1B_MODEL_B_RESULTS_PATH": stage1b / "stage1b_model_b_results.csv",
        "STAGE1B_TECHNICAL_ERROR_QUEUE_PATH": stage1b / "stage1b_technical_error_queue.csv",
        "STAGE1B_COMPARISON_PATH": stage1b / "stage1b_dual_model_comparison.csv",
        "STAGE1B_CONFLICT_QUEUE_PATH": stage1b / "stage1b_conflict_queue.csv",
        "STAGE1B_ARBITRATION_RESULTS_PATH": stage1b / "stage1b_arbitration_results.csv",
        "STAGE1B_MANUAL_REVIEW_QUEUE_PATH": stage1b / "stage1b_manual_review_queue.csv",
        "STAGE1B_FINAL_CLASSIFICATION_PATH": processed / "stage1b_final_classification.csv",
        "STAGE1B_SUCCESS_PATH": processed / "STAGE1B_SUCCESS",
        "STAGE1B_MANIFEST_PATH": manifests / "stage1b_manifest.json",
        "STAGE1_FINAL_CLASSIFICATION_PATH": processed / "stage1_final_classification.csv",
        "STAGE1_SUCCESS_PATH": processed / "STAGE1_SUCCESS",
        "STAGE1_MANIFEST_PATH": manifests / "stage1_manifest.json",
        "STAGE2_MODEL_A_RESULTS_PATH": stage2 / "stage2_model_a_results.csv",
        "STAGE2_MODEL_B_RESULTS_PATH": stage2 / "stage2_model_b_results.csv",
        "STAGE2_TECHNICAL_ERROR_QUEUE_PATH": stage2 / "stage2_technical_error_queue.csv",
        "STAGE2_COMPARISON_PATH": stage2 / "stage2_dual_model_comparison.csv",
        "STAGE2_TYPE_CONFLICT_QUEUE_PATH": stage2 / "stage2_type_conflict_queue.csv",
        "STAGE2_ARBITRATION_RESULTS_PATH": stage2 / "stage2_arbitration_results.csv",
        "STAGE2_MANUAL_REVIEW_QUEUE_PATH": stage2 / "stage2_manual_review_queue.csv",
        "FINAL_PROVISION_WEIGHTS_PATH": processed / "final_provision_weights.csv",
        "AGREEMENT_LEVEL_INDICES_PATH": processed / "agreement_level_indices.csv",
        "COUNTRY_PAIR_YEAR_INDICES_PATH": processed / "country_pair_year_indices.csv",
        "DIAGNOSTICS_SUMMARY_PATH": processed / "diagnostics_summary.csv",
        "STAGE1A_PROMPT_PATH": prompts / "stage1a_institutional.txt",
        "STAGE1A_ARBITRATION_PROMPT_PATH": prompts / "stage1a_arbitration.txt",
        "STAGE1B_PROMPT_PATH": prompts / "stage1b_dimension.txt",
        "STAGE1B_ARBITRATION_PROMPT_PATH": prompts / "stage1b_arbitration.txt",
        "STAGE2_PROMPT_PATH": prompts / "stage2_trade_investment.txt",
        "STAGE2_ARBITRATION_PROMPT_PATH": prompts / "stage2_type_arbitration.txt",
    }
    for name, value in path_values.items():
        monkeypatch.setattr(config, name, value)
    ensure_directories()
    for path in [
        config.STAGE1A_PROMPT_PATH,
        config.STAGE1A_ARBITRATION_PROMPT_PATH,
        config.STAGE1B_PROMPT_PATH,
        config.STAGE1B_ARBITRATION_PROMPT_PATH,
        config.STAGE2_PROMPT_PATH,
        config.STAGE2_ARBITRATION_PROMPT_PATH,
    ]:
        path.write_text("Prompt for {provision_id}: {provision_text}", encoding="utf-8")
    return root


def write_stage1_success_manifest(stage1_final):
    stage1_final = stage1_final.copy()
    if "stage1_unresolved" not in stage1_final.columns:
        stage1_final["stage1_unresolved"] = False
    for column, default in {
        "stage1a_decision_source": "test",
        "stage1a_resolution_method": "test",
        "stage1a_final_reason": "",
        "stage1a_was_arbitrated": False,
        "stage1a_was_human_reviewed": False,
        "stage1a_unresolved": False,
        "stage1b_decision_source": "test",
        "stage1b_resolution_method": "test",
        "stage1b_final_reason": "",
        "stage1b_was_arbitrated": False,
        "stage1b_was_human_reviewed": False,
        "stage1b_unresolved": False,
        "stage1_decision_source": "test",
        "stage1_resolution_method": "test",
        "stage1_final_reason": "",
        "stage1_was_arbitrated": False,
        "stage1_was_human_reviewed": False,
    }.items():
        if column not in stage1_final.columns:
            stage1_final[column] = default

    stage1a_final = stage1_final[
        [
            "provision_id",
            "final_is_institutional_opening",
            "stage1a_decision_source",
            "stage1a_resolution_method",
            "stage1a_final_reason",
            "stage1a_was_arbitrated",
            "stage1a_was_human_reviewed",
            "stage1a_unresolved",
        ]
    ].copy()
    write_csv(stage1a_final, config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    stage1a_hash = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    write_json(
        {
            "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            "run_id": "test",
            "stage1a_final_sha256": stage1a_hash,
        },
        config.STAGE1A_MANIFEST_PATH,
    )
    config.STAGE1A_SUCCESS_PATH.write_text("ok", encoding="utf-8")

    stage1b_final = stage1_final[
        stage1_final["final_is_institutional_opening"].astype(int).eq(1)
    ][
        [
            "provision_id",
            "final_dominant_dimension",
            "stage1b_decision_source",
            "stage1b_resolution_method",
            "stage1b_final_reason",
            "stage1b_was_arbitrated",
            "stage1b_was_human_reviewed",
            "stage1b_unresolved",
        ]
    ].copy()
    stage1b_final["stage1a_final_sha256"] = stage1a_hash
    write_csv(stage1b_final, config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    stage1b_hash = sha256_file(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    write_json(
        {
            "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            "run_id": "test",
            "stage1a_final_sha256": stage1a_hash,
            "stage1b_final_sha256": stage1b_hash,
        },
        config.STAGE1B_MANIFEST_PATH,
    )
    config.STAGE1B_SUCCESS_PATH.write_text("ok", encoding="utf-8")

    stage1_final["stage1a_final_sha256"] = stage1a_hash
    stage1_final["stage1b_final_sha256"] = stage1b_hash
    write_csv(stage1_final, config.STAGE1_FINAL_CLASSIFICATION_PATH)
    stage1_hash = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    provisions_hash = sha256_file(config.PROVISIONS_MASTER_PATH)
    write_json(
        {
            "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            "run_id": "test",
            "provisions_master_sha256": provisions_hash,
            "stage1a_final_sha256": stage1a_hash,
            "stage1b_final_sha256": stage1b_hash,
            "stage1_final_sha256": stage1_hash,
            "total_provisions": len(stage1_final),
            "institutional_provisions": int(stage1_final["final_is_institutional_opening"].eq(1).sum()),
            "non_institutional_provisions": int(stage1_final["final_is_institutional_opening"].eq(0).sum()),
            "dual_model_consensus_count": len(stage1_final),
            "arbitration_count": 0,
            "human_review_count": 0,
            "unresolved_count": int(stage1_final["stage1_unresolved"].astype(bool).sum()),
        },
        config.STAGE1_MANIFEST_PATH,
    )
    config.STAGE1_SUCCESS_PATH.write_text("ok", encoding="utf-8")
    return stage1_hash
