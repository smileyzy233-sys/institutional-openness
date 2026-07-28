from __future__ import annotations

import pandas as pd

import config
from utils import (
    as_bool_series,
    check_stage1a_gate,
    check_stage1b_gate,
    ensure_directories,
    read_csv,
    read_prompt_with_sha,
    sha256_file,
    utc_timestamp,
    write_csv,
    write_json,
)


def clear_success() -> None:
    if config.STAGE1_SUCCESS_PATH.exists():
        config.STAGE1_SUCCESS_PATH.unlink()


def assert_complete(stage1_final: pd.DataFrame, provisions: pd.DataFrame) -> None:
    assert len(stage1_final) == len(provisions)
    assert stage1_final["provision_id"].is_unique
    assert set(stage1_final["provision_id"].astype(str)) == set(
        provisions["provision_id"].astype(str)
    )
    values = pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce")
    assert values.isin([0, 1]).all()
    non_inst = values.eq(0)
    assert stage1_final.loc[non_inst, "final_dominant_dimension"].astype(str).str.lower().eq(
        "none"
    ).all()
    inst = values.eq(1)
    assert stage1_final.loc[inst, "final_dominant_dimension"].astype(str).str.lower().isin(
        config.INSTITUTIONAL_DIMENSION_VALUES
    ).all()
    assert not as_bool_series(stage1_final["stage1_unresolved"]).any()


def merged_reason(row: pd.Series) -> str:
    stage1a_reason = str(row.get("stage1a_final_reason", "") or "").strip()
    if int(row["final_is_institutional_opening"]) == 0:
        return f"Stage 1A: {stage1a_reason}".strip()
    stage1b_reason = str(row.get("stage1b_final_reason", "") or "").strip()
    parts = []
    if stage1a_reason:
        parts.append(f"Stage 1A: {stage1a_reason}")
    if stage1b_reason:
        parts.append(f"Stage 1B: {stage1b_reason}")
    return " ".join(parts)


def write_manifest(stage1_final: pd.DataFrame, run_id: str) -> None:
    stage1_hash = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    stage1a_hash = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    stage1b_hash = sha256_file(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    provisions_hash = sha256_file(config.PROVISIONS_MASTER_PATH)
    _stage1a_prompt, stage1a_prompt_sha = read_prompt_with_sha(config.STAGE1A_PROMPT_PATH)
    _stage1a_arb, stage1a_arb_sha = read_prompt_with_sha(config.STAGE1A_ARBITRATION_PROMPT_PATH)
    _stage1b_prompt, stage1b_prompt_sha = read_prompt_with_sha(config.STAGE1B_PROMPT_PATH)
    _stage1b_arb, stage1b_arb_sha = read_prompt_with_sha(config.STAGE1B_ARBITRATION_PROMPT_PATH)

    stage1a_was_arbitrated = as_bool_series(stage1_final["stage1a_was_arbitrated"])
    stage1b_was_arbitrated = as_bool_series(stage1_final["stage1b_was_arbitrated"])
    unique_arbitrated = stage1_final.loc[
        stage1a_was_arbitrated | stage1b_was_arbitrated,
        "provision_id",
    ].nunique()
    total = len(stage1_final)
    dimensions = stage1_final["final_dominant_dimension"].astype(str).str.lower()
    stage1a_conflict_count = int(stage1a_was_arbitrated.sum())
    stage1b_conflict_count = int(stage1b_was_arbitrated.sum())
    manifest = {
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "provisions_master_sha256": provisions_hash,
        "stage1a_final_sha256": stage1a_hash,
        "stage1b_final_sha256": stage1b_hash,
        "stage1_final_sha256": stage1_hash,
        "prompt_versions": {
            "stage1a_prompt_version": config.STAGE1A_PROMPT_VERSION,
            "stage1a_arbitration_prompt_version": config.STAGE1A_ARBITRATION_PROMPT_VERSION,
            "stage1b_prompt_version": config.STAGE1B_PROMPT_VERSION,
            "stage1b_arbitration_prompt_version": config.STAGE1B_ARBITRATION_PROMPT_VERSION,
        },
        "prompt_sha256": {
            "stage1a_prompt_sha256": stage1a_prompt_sha,
            "stage1a_arbitration_prompt_sha256": stage1a_arb_sha,
            "stage1b_prompt_sha256": stage1b_prompt_sha,
            "stage1b_arbitration_prompt_sha256": stage1b_arb_sha,
        },
        "total_provisions": int(total),
        "institutional_provisions": int(
            pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1).sum()
        ),
        "non_institutional_provisions": int(
            pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(0).sum()
        ),
        "stage1a_consensus_count": int(stage1_final["stage1a_decision_source"].eq("dual_model_consensus").sum()),
        "stage1a_arbitration_count": stage1a_conflict_count,
        "stage1a_human_review_count": int(as_bool_series(stage1_final["stage1a_was_human_reviewed"]).sum()),
        "stage1b_consensus_count": int(stage1_final["stage1b_decision_source"].eq("dual_model_consensus").sum()),
        "stage1b_arbitration_count": stage1b_conflict_count,
        "stage1b_human_review_count": int(as_bool_series(stage1_final["stage1b_was_human_reviewed"]).sum()),
        "stage1a_conflict_rate": float(stage1a_conflict_count / total) if total else 0.0,
        "stage1b_conflict_rate": float(stage1b_conflict_count / total) if total else 0.0,
        "stage1_unique_arbitrated_provision_count": int(unique_arbitrated),
        "stage1_unique_arbitrated_provision_rate": float(unique_arbitrated / total) if total else 0.0,
        "dimension_counts": {
            dimension: int(dimensions.eq(dimension).sum())
            for dimension in ["rules", "regulation", "management", "standards", "none"]
        },
        "completed_at": utc_timestamp(),
    }
    write_json(manifest, config.STAGE1_MANIFEST_PATH)
    config.STAGE1_SUCCESS_PATH.write_text(
        f"pipeline_schema_version={config.PIPELINE_SCHEMA_VERSION}\n"
        f"run_id={run_id}\n"
        f"stage1_final_sha256={stage1_hash}\n",
        encoding="utf-8",
    )


def run(*, allow_unresolved: bool = config.ALLOW_UNRESOLVED) -> None:
    del allow_unresolved
    ensure_directories()
    clear_success()
    check_stage1a_gate()
    check_stage1b_gate()

    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    stage1a = read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    stage1b = read_csv(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    stage1a_hash = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    stage1b_hash = sha256_file(config.STAGE1B_FINAL_CLASSIFICATION_PATH)

    eligible_ids = set(
        stage1a.loc[
            pd.to_numeric(stage1a["final_is_institutional_opening"], errors="coerce").eq(1),
            "provision_id",
        ].astype(str)
    )
    stage1b_ids = set(stage1b["provision_id"].astype(str))
    if stage1b_ids != eligible_ids:
        raise RuntimeError("Stage 1B final ID set does not exactly match Stage 1A positive IDs.")

    merged = provisions.merge(
        stage1a.drop_duplicates("provision_id"),
        on="provision_id",
        how="left",
        suffixes=("", "_stage1a"),
        validate="1:1",
    )
    missing_stage1a = merged["final_is_institutional_opening"].isna()
    if missing_stage1a.any():
        raise RuntimeError(
            f"Stage 1 final merge missing Stage 1A rows: {int(missing_stage1a.sum())}"
        )
    merged = merged.merge(
        stage1b.drop_duplicates("provision_id"),
        on="provision_id",
        how="left",
        suffixes=("", "_stage1b"),
        validate="1:1",
    )

    values = pd.to_numeric(merged["final_is_institutional_opening"], errors="coerce").astype(int)
    non_inst = values.eq(0)
    merged.loc[non_inst, "final_dominant_dimension"] = "none"
    for column, value in {
        "stage1b_decision_source": "not_applicable",
        "stage1b_resolution_method": "not_applicable",
        "stage1b_final_reason": "",
        "stage1b_was_arbitrated": False,
        "stage1b_was_human_reviewed": False,
        "stage1b_unresolved": False,
    }.items():
        if column in merged.columns:
            merged[column] = merged[column].astype("object")
        merged.loc[non_inst, column] = value

    inst = values.eq(1)
    missing_dimensions = merged.loc[inst, "final_dominant_dimension"].isna()
    if missing_dimensions.any():
        sample = ", ".join(
            merged.loc[inst & merged["final_dominant_dimension"].isna(), "provision_id"]
            .astype(str)
            .head(10)
        )
        raise RuntimeError(f"Stage 1B dimension missing for institutional provisions: {sample}")

    merged["stage1a_final_sha256"] = stage1a_hash
    merged["stage1b_final_sha256"] = stage1b_hash
    merged["stage1_was_arbitrated"] = (
        as_bool_series(merged["stage1a_was_arbitrated"])
        | as_bool_series(merged["stage1b_was_arbitrated"])
    )
    merged["stage1_was_human_reviewed"] = (
        as_bool_series(merged["stage1a_was_human_reviewed"])
        | as_bool_series(merged["stage1b_was_human_reviewed"])
    )
    merged["stage1_unresolved"] = (
        as_bool_series(merged["stage1a_unresolved"])
        | as_bool_series(merged["stage1b_unresolved"])
    )
    merged["stage1_decision_source"] = merged.apply(
        lambda row: "+".join(
            part
            for part in [
                str(row.get("stage1a_decision_source", "") or ""),
                str(row.get("stage1b_decision_source", "") or ""),
            ]
            if part and part != "not_applicable"
        )
        or "not_applicable",
        axis=1,
    )
    merged["stage1_resolution_method"] = merged.apply(
        lambda row: "+".join(
            part
            for part in [
                str(row.get("stage1a_resolution_method", "") or ""),
                str(row.get("stage1b_resolution_method", "") or ""),
            ]
            if part and part != "not_applicable"
        )
        or "not_applicable",
        axis=1,
    )
    merged["stage1_final_reason"] = merged.apply(merged_reason, axis=1)
    merged["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
    merged["run_id"] = utc_timestamp().replace(":", "").replace("+", "Z")

    first_cols = [
        "provision_id",
        "final_is_institutional_opening",
        "final_dominant_dimension",
        "stage1a_decision_source",
        "stage1a_resolution_method",
        "stage1a_final_reason",
        "stage1a_was_arbitrated",
        "stage1a_was_human_reviewed",
        "stage1b_decision_source",
        "stage1b_resolution_method",
        "stage1b_final_reason",
        "stage1b_was_arbitrated",
        "stage1b_was_human_reviewed",
        "stage1_decision_source",
        "stage1_resolution_method",
        "stage1_final_reason",
        "stage1_was_arbitrated",
        "stage1_was_human_reviewed",
        "stage1_unresolved",
        "stage1a_final_sha256",
        "stage1b_final_sha256",
        "pipeline_schema_version",
        "run_id",
    ]
    remaining = [column for column in merged.columns if column not in first_cols]
    stage1_final = merged[first_cols + remaining]
    assert_complete(stage1_final, provisions)
    write_csv(stage1_final, config.STAGE1_FINAL_CLASSIFICATION_PATH)
    write_manifest(stage1_final, str(stage1_final["run_id"].iloc[0]))
    print(f"Wrote Stage 1 final classification to {config.STAGE1_FINAL_CLASSIFICATION_PATH}")
    print(f"Wrote Stage 1 success marker to {config.STAGE1_SUCCESS_PATH}")


if __name__ == "__main__":
    run()
