from __future__ import annotations

import pandas as pd
import pytest

import config
from conftest import write_stage1_success_manifest
from utils import (
    agreement_score_inputs,
    check_agreement_score_provenance,
    check_final_weights_provenance,
    check_stage1_gate,
    read_csv,
    read_json,
    score_provenance_path,
    score_provenance_record,
    sha256_file,
    weight_classification_baseline_record,
    write_csv,
    write_json,
)


def seed_classification() -> None:
    write_csv(
        pd.DataFrame(
            {
                "provision_id": ["P0001"],
                "provision_order": [1],
                "policy_area": ["Services"],
                "original_coding": ["A1"],
                "provision_text": ["First\r\nsecond"],
            }
        ),
        config.PROVISIONS_MASTER_PATH,
    )
    final = read_csv(config.PROVISIONS_MASTER_PATH).assign(
        final_is_institutional_opening=1,
        final_dominant_dimension="rules",
    )
    final_hash = write_stage1_success_manifest(final)
    weights = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH).assign(
        stage1_final_sha256=final_hash,
        final_unresolved=False,
        effective_trade_weight=0.75,
        effective_mp_weight=0.25,
    )
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)


def record_approved_newline_compatibility() -> None:
    preserved = []
    for path in (
        config.STAGE1A_MANIFEST_PATH,
        config.STAGE1B_MANIFEST_PATH,
        config.STAGE1_MANIFEST_PATH,
    ):
        preserved.append(
            {
                "path": path.relative_to(config.PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(path),
                "historical_provisions_master_sha256": read_json(path)["provisions_master_sha256"],
            }
        )
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    provisions["provision_text"] = provisions["provision_text"].str.replace("\r\n", "\n", regex=False)
    write_csv(provisions, config.PROVISIONS_MASTER_PATH)
    write_json(
        {
            "record_type": "documentation_only_compatibility_audit",
            "authorization": "Synthetic fixture: explicitly approved newline-only compatibility",
            "historical_manifests_preserved": preserved,
            "current_provisions_master_sha256": sha256_file(config.PROVISIONS_MASTER_PATH),
            "final_provision_weights_sha256": sha256_file(config.FINAL_PROVISION_WEIGHTS_PATH),
            "provision_count": 1,
            "id_set_matches": True,
            "text_comparison": {
                column: {"mismatches_after_crlf_to_lf": 0}
                for column in ("policy_area", "original_coding", "provision_text")
            },
            "historical_classification_output_hashes_match_current": {
                key: True
                for key in ("stage1a_final_sha256", "stage1b_final_sha256", "stage1_final_sha256")
            },
        },
        config.MANIFEST_DIR / "measurement_compatibility_fixture.json",
    )


def seed_score_record(*, baseline: bool = False) -> None:
    config.AGREEMENT_MATRIX_PATH.write_text("agreement_id,P0001\nA1,1\n", encoding="utf-8")
    config.AGREEMENTS_MASTER_PATH.write_text("agreement_id,agreement_name\nA1,Example\n", encoding="utf-8")
    config.AGREEMENT_LEVEL_INDICES_PATH.write_text("synthetic fixture output", encoding="utf-8")
    record = score_provenance_record(
        config.AGREEMENT_LEVEL_INDICES_PATH,
        agreement_score_inputs(),
        {"output_float_decimals": config.OUTPUT_FLOAT_DECIMALS},
        record_type="frozen_input_baseline" if baseline else "generated_score_provenance",
    )
    if baseline:
        record["basis"] = "Synthetic read-only baseline; no data recomputation"
    write_json(record, score_provenance_path(config.AGREEMENT_LEVEL_INDICES_PATH))


def test_current_master_and_weights_pass(temp_pipeline):
    seed_classification()
    check_stage1_gate()
    check_final_weights_provenance()


@pytest.mark.parametrize("manifest_name", ["STAGE1A_MANIFEST_PATH", "STAGE1B_MANIFEST_PATH", "STAGE1_MANIFEST_PATH"])
@pytest.mark.parametrize("missing", [False, True])
def test_each_stage_requires_current_master_hash(temp_pipeline, manifest_name, missing):
    seed_classification()
    path = getattr(config, manifest_name)
    manifest = read_json(path)
    if missing:
        manifest.pop("provisions_master_sha256")
    else:
        manifest["provisions_master_sha256"] = "different input"
    write_json(manifest, path)
    with pytest.raises(RuntimeError, match="provisions_master_sha256"):
        check_stage1_gate()


def test_changed_text_rejected_even_with_same_ids(temp_pipeline):
    seed_classification()
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    provisions["provision_text"] = "Different research meaning"
    write_csv(provisions, config.PROVISIONS_MASTER_PATH)
    with pytest.raises(RuntimeError, match="provisions_master_sha256"):
        check_stage1_gate()


def test_exact_approved_newline_audit_passes(temp_pipeline):
    seed_classification()
    record_approved_newline_compatibility()
    check_final_weights_provenance()


@pytest.mark.parametrize("changed_file", ["PROVISIONS_MASTER_PATH", "STAGE1_MANIFEST_PATH", "STAGE1_FINAL_CLASSIFICATION_PATH", "FINAL_PROVISION_WEIGHTS_PATH"])
def test_compatibility_never_covers_later_changes(temp_pipeline, changed_file):
    seed_classification()
    record_approved_newline_compatibility()
    path = getattr(config, changed_file)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="provisions_master_sha256"):
        check_stage1_gate()


def test_weights_must_bind_current_classification(temp_pipeline):
    seed_classification()
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    weights["stage1_final_sha256"] = "stale classification"
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)
    with pytest.raises(RuntimeError, match="stage1_final_sha256"):
        check_final_weights_provenance()


def test_weight_classification_columns_must_match(temp_pipeline):
    seed_classification()
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    weights["final_dominant_dimension"] = "standards"
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)
    with pytest.raises(RuntimeError, match="final_dominant_dimension"):
        check_final_weights_provenance()


def record_weight_baseline() -> None:
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    weights["stage1_final_sha256"] = "0" * 64
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)
    write_json(
        weight_classification_baseline_record(basis="Synthetic read-only comparison"),
        score_provenance_path(config.FINAL_PROVISION_WEIGHTS_PATH),
    )


def test_legacy_weight_binding_needs_exact_audited_baseline(temp_pipeline):
    seed_classification()
    record_weight_baseline()
    check_final_weights_provenance()
    record = read_json(score_provenance_path(config.FINAL_PROVISION_WEIGHTS_PATH))
    assert record["pipeline_executed"] is False
    assert record["embedded_stage1_final_sha256"] == ["0" * 64]
    assert record["classification_files"]["stage1_final"] != "0" * 64


def test_weight_baseline_rejects_later_weight_change(temp_pipeline):
    seed_classification()
    record_weight_baseline()
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    weights["effective_trade_weight"] = 0.5
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)
    with pytest.raises(RuntimeError, match="stage1_final_sha256"):
        check_final_weights_provenance()


def test_weight_baseline_cannot_authorize_classification_change(temp_pipeline):
    seed_classification()
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    weights["stage1a_decision_source"] = "Different decision"
    write_csv(weights, config.FINAL_PROVISION_WEIGHTS_PATH)
    with pytest.raises(RuntimeError, match="实质差异"):
        weight_classification_baseline_record(basis="Synthetic attempted incompatible audit")


def test_agreement_score_without_record_is_rejected(temp_pipeline):
    seed_classification()
    with pytest.raises(RuntimeError, match="缺少输入版本记录"):
        check_agreement_score_provenance()


@pytest.mark.parametrize("baseline", [False, True])
def test_agreement_score_exact_record_passes(temp_pipeline, baseline):
    seed_classification()
    seed_score_record(baseline=baseline)
    check_agreement_score_provenance()


@pytest.mark.parametrize("changed_file", ["FINAL_PROVISION_WEIGHTS_PATH", "AGREEMENT_MATRIX_PATH", "AGREEMENTS_MASTER_PATH", "AGREEMENT_LEVEL_INDICES_PATH"])
def test_agreement_score_rejects_changed_inputs_or_output(temp_pipeline, changed_file):
    seed_classification()
    seed_score_record()
    path = getattr(config, changed_file)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="协定指标门控失败"):
        check_agreement_score_provenance()


def test_baseline_cannot_claim_recomputation(temp_pipeline):
    seed_classification()
    seed_score_record(baseline=True)
    path = score_provenance_path(config.AGREEMENT_LEVEL_INDICES_PATH)
    record = read_json(path)
    record["pipeline_executed"] = True
    write_json(record, path)
    with pytest.raises(RuntimeError, match="pipeline_executed"):
        check_agreement_score_provenance()
