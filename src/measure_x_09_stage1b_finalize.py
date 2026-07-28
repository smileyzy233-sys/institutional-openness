from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils import (
    as_bool,
    as_bool_series,
    check_stage1a_gate,
    ensure_directories,
    read_csv,
    read_prompt_with_sha,
    sha256_file,
    utc_timestamp,
    validate_stage1b_arbitration_output,
    write_csv,
    write_json,
)


def load_optional_csv(path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return read_csv(path)


def clear_success() -> None:
    if config.STAGE1B_SUCCESS_PATH.exists():
        config.STAGE1B_SUCCESS_PATH.unlink()


def eligible_ids() -> set[str]:
    stage1a = read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    return set(
        stage1a.loc[
            pd.to_numeric(stage1a["final_is_institutional_opening"], errors="coerce").eq(1),
            "provision_id",
        ].astype(str)
    )


def completed_human(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None or not as_bool(row.get("human_review_completed")):
        return None
    dimension = str(row.get("human_final_dominant_dimension", "")).strip().lower()
    if dimension not in config.INSTITUTIONAL_DIMENSION_VALUES:
        raise ValueError(f"Invalid Stage 1B human review for {row.get('provision_id')}")
    return {
        "final_dominant_dimension": dimension,
        "stage1b_decision_source": "human_review",
        "stage1b_resolution_method": "human_review",
        "stage1b_final_reason": row.get("human_review_reason", ""),
        "stage1b_was_arbitrated": True,
        "stage1b_was_human_reviewed": True,
        "stage1b_unresolved": False,
    }


def valid_arbitration(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if not (
        str(row.get("parse_status", "")).strip() == "ok"
        and str(row.get("validation_status", "")).strip() == "ok"
        and not as_bool(row.get("need_human_review"))
    ):
        return None
    normalized, status, message = validate_stage1b_arbitration_output(row.to_dict())
    if status != "ok":
        raise ValueError(f"Invalid Stage 1B arbitration for {row.get('provision_id')}: {message}")
    return {
        "final_dominant_dimension": normalized["final_dominant_dimension"],
        "stage1b_decision_source": "arbitration_model",
        "stage1b_resolution_method": "arbitrated",
        "stage1b_final_reason": normalized.get("arbitration_reason", ""),
        "stage1b_was_arbitrated": True,
        "stage1b_was_human_reviewed": False,
        "stage1b_unresolved": False,
    }


def consensus(row: pd.Series) -> dict[str, Any]:
    dimension = str(row["model_a_dominant_dimension"]).strip().lower()
    if dimension not in config.INSTITUTIONAL_DIMENSION_VALUES:
        raise ValueError(f"Invalid Stage 1B consensus for {row['provision_id']}")
    return {
        "final_dominant_dimension": dimension,
        "stage1b_decision_source": "dual_model_consensus",
        "stage1b_resolution_method": "dual_model_consensus",
        "stage1b_final_reason": str(row.get("model_a_dimension_reason", "") or "").strip(),
        "stage1b_was_arbitrated": False,
        "stage1b_was_human_reviewed": False,
        "stage1b_unresolved": False,
    }


def unresolved() -> dict[str, Any]:
    return {
        "final_dominant_dimension": pd.NA,
        "stage1b_decision_source": "",
        "stage1b_resolution_method": "unresolved",
        "stage1b_final_reason": "Stage 1B conflict lacks valid arbitration or completed human review.",
        "stage1b_was_arbitrated": True,
        "stage1b_was_human_reviewed": False,
        "stage1b_unresolved": True,
    }


def assert_complete(stage1b_final: pd.DataFrame, expected_ids: set[str]) -> None:
    assert len(stage1b_final) == len(expected_ids)
    assert stage1b_final["provision_id"].is_unique
    assert set(stage1b_final["provision_id"].astype(str)) == expected_ids
    assert not as_bool_series(stage1b_final["stage1b_unresolved"]).any()
    assert stage1b_final["final_dominant_dimension"].astype(str).str.lower().isin(
        config.INSTITUTIONAL_DIMENSION_VALUES
    ).all()


def write_manifest(stage1b_final: pd.DataFrame, run_id: str, stage1a_final_sha256: str) -> None:
    stage1b_hash = sha256_file(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    provisions_hash = sha256_file(config.PROVISIONS_MASTER_PATH)
    _prompt, prompt_sha256 = read_prompt_with_sha(config.STAGE1B_PROMPT_PATH)
    _arb_prompt, arbitration_prompt_sha256 = read_prompt_with_sha(
        config.STAGE1B_ARBITRATION_PROMPT_PATH
    )
    manifest = {
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "provisions_master_sha256": provisions_hash,
        "stage1a_final_sha256": stage1a_final_sha256,
        "stage1b_final_sha256": stage1b_hash,
        "model_a_name": str(stage1b_final.get("model_a_model_name", pd.Series(dtype=str)).dropna().iloc[0])
        if "model_a_model_name" in stage1b_final.columns and stage1b_final["model_a_model_name"].notna().any()
        else config.MODEL_A_NAME,
        "model_b_name": str(stage1b_final.get("model_b_model_name", pd.Series(dtype=str)).dropna().iloc[0])
        if "model_b_model_name" in stage1b_final.columns and stage1b_final["model_b_model_name"].notna().any()
        else config.MODEL_B_NAME,
        "prompt_versions": {
            "stage1b_prompt_version": config.STAGE1B_PROMPT_VERSION,
            "stage1b_arbitration_prompt_version": config.STAGE1B_ARBITRATION_PROMPT_VERSION,
        },
        "prompt_sha256": {
            "stage1b_prompt_sha256": prompt_sha256,
            "stage1b_arbitration_prompt_sha256": arbitration_prompt_sha256,
        },
        "eligible_provisions": int(len(stage1b_final)),
        "consensus_count": int(stage1b_final["stage1b_decision_source"].eq("dual_model_consensus").sum()),
        "arbitration_count": int(as_bool_series(stage1b_final["stage1b_was_arbitrated"]).sum()),
        "human_review_count": int(as_bool_series(stage1b_final["stage1b_was_human_reviewed"]).sum()),
        "unresolved_count": int(as_bool_series(stage1b_final["stage1b_unresolved"]).sum()),
        "completed_at": utc_timestamp(),
    }
    write_json(manifest, config.STAGE1B_MANIFEST_PATH)
    config.STAGE1B_SUCCESS_PATH.write_text(
        f"pipeline_schema_version={config.PIPELINE_SCHEMA_VERSION}\n"
        f"run_id={run_id}\n"
        f"stage1a_final_sha256={stage1a_final_sha256}\n"
        f"stage1b_final_sha256={stage1b_hash}\n",
        encoding="utf-8",
    )


def run(*, allow_unresolved: bool = config.ALLOW_UNRESOLVED) -> None:
    ensure_directories()
    clear_success()
    check_stage1a_gate()
    stage1a_final_sha256 = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    expected_ids = eligible_ids()
    if not config.STAGE1B_COMPARISON_PATH.exists():
        raise FileNotFoundError(
            f"Stage 1B comparison not found: {config.STAGE1B_COMPARISON_PATH}"
        )
    if config.STAGE1B_TECHNICAL_ERROR_QUEUE_PATH.exists():
        tech = read_csv(config.STAGE1B_TECHNICAL_ERROR_QUEUE_PATH)
        if not tech.empty:
            raise RuntimeError(
                f"Stage 1B has {len(tech)} unresolved technical errors; cannot finalize."
            )

    comparison = read_csv(config.STAGE1B_COMPARISON_PATH)
    if set(comparison.get("provision_id", pd.Series(dtype=str)).astype(str)) != expected_ids:
        raise RuntimeError("Stage 1B comparison ID set does not match Stage 1A positive IDs.")
    if not comparison.empty and not comparison["stage1a_final_sha256"].eq(stage1a_final_sha256).all():
        raise RuntimeError("Stage 1B comparison is stale because Stage 1A final hash changed.")
    arbitration = load_optional_csv(config.STAGE1B_ARBITRATION_RESULTS_PATH, [])
    manual = load_optional_csv(config.STAGE1B_MANUAL_REVIEW_QUEUE_PATH, [])
    arbitration_by_id = (
        arbitration.drop_duplicates("provision_id", keep="last").set_index("provision_id")
        if not arbitration.empty and "provision_id" in arbitration.columns
        else pd.DataFrame().set_index(pd.Index([]))
    )
    manual_by_id = (
        manual.drop_duplicates("provision_id", keep="last").set_index("provision_id")
        if not manual.empty and "provision_id" in manual.columns
        else pd.DataFrame().set_index(pd.Index([]))
    )

    decisions: list[dict[str, Any]] = []
    unresolved_ids: list[str] = []
    for _, row in comparison.iterrows():
        provision_id = row["provision_id"]
        if not as_bool(row["needs_arbitration"]):
            decision = consensus(row)
        else:
            manual_row = manual_by_id.loc[provision_id] if provision_id in manual_by_id.index else None
            if isinstance(manual_row, pd.DataFrame):
                manual_row = manual_row.iloc[-1]
            decision = completed_human(manual_row)
            if decision is None:
                arb_row = arbitration_by_id.loc[provision_id] if provision_id in arbitration_by_id.index else None
                if isinstance(arb_row, pd.DataFrame):
                    arb_row = arb_row.iloc[-1]
                decision = valid_arbitration(arb_row)
            if decision is None:
                decision = unresolved()
                unresolved_ids.append(str(provision_id))
        decisions.append(decision)

    stage1b_final = pd.concat(
        [comparison.reset_index(drop=True), pd.DataFrame(decisions)],
        axis=1,
    )
    _prompt, prompt_sha256 = read_prompt_with_sha(config.STAGE1B_PROMPT_PATH)
    _arb_prompt, arbitration_prompt_sha256 = read_prompt_with_sha(
        config.STAGE1B_ARBITRATION_PROMPT_PATH
    )
    stage1b_final["stage1a_final_sha256"] = stage1a_final_sha256
    stage1b_final["stage1b_prompt_version"] = config.STAGE1B_PROMPT_VERSION
    stage1b_final["stage1b_prompt_sha256"] = prompt_sha256
    stage1b_final["stage1b_arbitration_prompt_version"] = (
        config.STAGE1B_ARBITRATION_PROMPT_VERSION
    )
    stage1b_final["stage1b_arbitration_prompt_sha256"] = arbitration_prompt_sha256
    stage1b_final["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
    stage1b_final["run_id"] = utc_timestamp().replace(":", "").replace("+", "Z")

    first_cols = [
        "provision_id",
        "final_dominant_dimension",
        "stage1b_decision_source",
        "stage1b_resolution_method",
        "stage1b_final_reason",
        "stage1b_was_arbitrated",
        "stage1b_was_human_reviewed",
        "stage1b_unresolved",
        "model_a_dominant_dimension",
        "model_b_dominant_dimension",
        "stage1a_final_sha256",
        "stage1b_prompt_version",
        "stage1b_prompt_sha256",
        "stage1b_arbitration_prompt_version",
        "stage1b_arbitration_prompt_sha256",
        "pipeline_schema_version",
        "run_id",
    ]
    for column in first_cols:
        if column not in stage1b_final.columns:
            stage1b_final[column] = pd.Series(dtype=object)
    remaining = [column for column in stage1b_final.columns if column not in first_cols]
    stage1b_final = stage1b_final[first_cols + remaining]

    if unresolved_ids and not allow_unresolved:
        write_csv(stage1b_final, config.STAGE1B_FINAL_CLASSIFICATION_PATH)
        sample = ", ".join(unresolved_ids[:10])
        raise RuntimeError(
            f"Stage 1B requires {len(unresolved_ids)} completed human reviews. "
            f"Sample unresolved provision_id: {sample}. Edit: "
            f"{config.STAGE1B_MANUAL_REVIEW_QUEUE_PATH}. Then run: "
            "python run_pipeline.py stage1b-finalize"
        )

    assert_complete(stage1b_final, expected_ids)
    write_csv(stage1b_final, config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    write_manifest(stage1b_final, str(stage1b_final["run_id"].iloc[0]), stage1a_final_sha256)
    print(f"Wrote Stage 1B final classification to {config.STAGE1B_FINAL_CLASSIFICATION_PATH}")
    print(f"Wrote Stage 1B success marker to {config.STAGE1B_SUCCESS_PATH}")


if __name__ == "__main__":
    run()
