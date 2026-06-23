from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils import (
    as_bool,
    as_bool_series,
    ensure_directories,
    read_csv,
    read_prompt_with_sha,
    sha256_file,
    utc_timestamp,
    validate_stage1a_arbitration_output,
    write_csv,
    write_json,
)


def load_optional_csv(path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return read_csv(path)


def clear_success() -> None:
    if config.STAGE1A_SUCCESS_PATH.exists():
        config.STAGE1A_SUCCESS_PATH.unlink()


def completed_human(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None or not as_bool(row.get("human_review_completed")):
        return None
    try:
        value = int(float(row.get("human_final_is_institutional_opening")))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Stage 1A human review for {row.get('provision_id')}") from exc
    if value not in {0, 1}:
        raise ValueError(f"Invalid Stage 1A human review for {row.get('provision_id')}")
    return {
        "final_is_institutional_opening": value,
        "stage1a_decision_source": "human_review",
        "stage1a_resolution_method": "human_review",
        "stage1a_final_reason": row.get("human_review_reason", ""),
        "stage1a_was_arbitrated": True,
        "stage1a_was_human_reviewed": True,
        "stage1a_unresolved": False,
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
    normalized, status, message = validate_stage1a_arbitration_output(row.to_dict())
    if status != "ok":
        raise ValueError(f"Invalid Stage 1A arbitration for {row.get('provision_id')}: {message}")
    return {
        "final_is_institutional_opening": normalized["final_is_institutional_opening"],
        "stage1a_decision_source": "arbitration_model",
        "stage1a_resolution_method": "arbitrated",
        "stage1a_final_reason": normalized.get("arbitration_reason", ""),
        "stage1a_was_arbitrated": True,
        "stage1a_was_human_reviewed": False,
        "stage1a_unresolved": False,
    }


def consensus(row: pd.Series) -> dict[str, Any]:
    value = int(float(row["model_a_is_institutional_opening"]))
    reason = str(row.get("model_a_institutional_reason", "") or "").strip()
    return {
        "final_is_institutional_opening": value,
        "stage1a_decision_source": "dual_model_consensus",
        "stage1a_resolution_method": "dual_model_consensus",
        "stage1a_final_reason": reason,
        "stage1a_was_arbitrated": False,
        "stage1a_was_human_reviewed": False,
        "stage1a_unresolved": False,
    }


def unresolved() -> dict[str, Any]:
    return {
        "final_is_institutional_opening": pd.NA,
        "stage1a_decision_source": "",
        "stage1a_resolution_method": "unresolved",
        "stage1a_final_reason": "Stage 1A conflict lacks valid arbitration or completed human review.",
        "stage1a_was_arbitrated": True,
        "stage1a_was_human_reviewed": False,
        "stage1a_unresolved": True,
    }


def assert_complete(stage1a_final: pd.DataFrame, provisions: pd.DataFrame) -> None:
    assert len(stage1a_final) == len(provisions)
    assert stage1a_final["provision_id"].is_unique
    assert set(stage1a_final["provision_id"].astype(str)) == set(
        provisions["provision_id"].astype(str)
    )
    assert not as_bool_series(stage1a_final["stage1a_unresolved"]).any()
    values = pd.to_numeric(stage1a_final["final_is_institutional_opening"], errors="coerce")
    assert values.isin([0, 1]).all()


def write_manifest(stage1a_final: pd.DataFrame, run_id: str) -> None:
    stage1a_hash = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    provisions_hash = sha256_file(config.PROVISIONS_MASTER_PATH)
    _prompt, prompt_sha256 = read_prompt_with_sha(config.STAGE1A_PROMPT_PATH)
    _arb_prompt, arbitration_prompt_sha256 = read_prompt_with_sha(
        config.STAGE1A_ARBITRATION_PROMPT_PATH
    )
    manifest = {
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "provisions_master_sha256": provisions_hash,
        "stage1a_final_sha256": stage1a_hash,
        "model_a_name": str(stage1a_final.get("model_a_model_name", pd.Series(dtype=str)).dropna().iloc[0])
        if "model_a_model_name" in stage1a_final.columns and stage1a_final["model_a_model_name"].notna().any()
        else config.MODEL_A_NAME,
        "model_b_name": str(stage1a_final.get("model_b_model_name", pd.Series(dtype=str)).dropna().iloc[0])
        if "model_b_model_name" in stage1a_final.columns and stage1a_final["model_b_model_name"].notna().any()
        else config.MODEL_B_NAME,
        "prompt_versions": {
            "stage1a_prompt_version": config.STAGE1A_PROMPT_VERSION,
            "stage1a_arbitration_prompt_version": config.STAGE1A_ARBITRATION_PROMPT_VERSION,
        },
        "prompt_sha256": {
            "stage1a_prompt_sha256": prompt_sha256,
            "stage1a_arbitration_prompt_sha256": arbitration_prompt_sha256,
        },
        "total_provisions": int(len(stage1a_final)),
        "institutional_provisions": int(
            pd.to_numeric(stage1a_final["final_is_institutional_opening"], errors="coerce").eq(1).sum()
        ),
        "non_institutional_provisions": int(
            pd.to_numeric(stage1a_final["final_is_institutional_opening"], errors="coerce").eq(0).sum()
        ),
        "consensus_count": int(stage1a_final["stage1a_decision_source"].eq("dual_model_consensus").sum()),
        "arbitration_count": int(as_bool_series(stage1a_final["stage1a_was_arbitrated"]).sum()),
        "human_review_count": int(as_bool_series(stage1a_final["stage1a_was_human_reviewed"]).sum()),
        "unresolved_count": int(as_bool_series(stage1a_final["stage1a_unresolved"]).sum()),
        "completed_at": utc_timestamp(),
    }
    write_json(manifest, config.STAGE1A_MANIFEST_PATH)
    config.STAGE1A_SUCCESS_PATH.write_text(
        f"pipeline_schema_version={config.PIPELINE_SCHEMA_VERSION}\n"
        f"run_id={run_id}\n"
        f"stage1a_final_sha256={stage1a_hash}\n",
        encoding="utf-8",
    )


def run(*, allow_unresolved: bool = config.ALLOW_UNRESOLVED) -> None:
    ensure_directories()
    clear_success()
    if not config.STAGE1A_COMPARISON_PATH.exists():
        raise FileNotFoundError(
            f"Stage 1A comparison not found: {config.STAGE1A_COMPARISON_PATH}"
        )
    if config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH.exists():
        tech = read_csv(config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH)
        if not tech.empty:
            raise RuntimeError(
                f"Stage 1A has {len(tech)} unresolved technical errors; cannot finalize."
            )

    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    comparison = read_csv(config.STAGE1A_COMPARISON_PATH)
    arbitration = load_optional_csv(config.STAGE1A_ARBITRATION_RESULTS_PATH, [])
    manual = load_optional_csv(config.STAGE1A_MANUAL_REVIEW_QUEUE_PATH, [])
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

    stage1a_final = pd.concat(
        [comparison.reset_index(drop=True), pd.DataFrame(decisions)],
        axis=1,
    )
    _prompt, prompt_sha256 = read_prompt_with_sha(config.STAGE1A_PROMPT_PATH)
    _arb_prompt, arbitration_prompt_sha256 = read_prompt_with_sha(
        config.STAGE1A_ARBITRATION_PROMPT_PATH
    )
    stage1a_final["stage1a_prompt_version"] = config.STAGE1A_PROMPT_VERSION
    stage1a_final["stage1a_prompt_sha256"] = prompt_sha256
    stage1a_final["stage1a_arbitration_prompt_version"] = (
        config.STAGE1A_ARBITRATION_PROMPT_VERSION
    )
    stage1a_final["stage1a_arbitration_prompt_sha256"] = arbitration_prompt_sha256
    stage1a_final["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
    stage1a_final["run_id"] = utc_timestamp().replace(":", "").replace("+", "Z")

    first_cols = [
        "provision_id",
        "final_is_institutional_opening",
        "stage1a_decision_source",
        "stage1a_resolution_method",
        "stage1a_final_reason",
        "stage1a_was_arbitrated",
        "stage1a_was_human_reviewed",
        "stage1a_unresolved",
        "model_a_is_institutional_opening",
        "model_b_is_institutional_opening",
        "stage1a_prompt_version",
        "stage1a_prompt_sha256",
        "stage1a_arbitration_prompt_version",
        "stage1a_arbitration_prompt_sha256",
        "pipeline_schema_version",
        "run_id",
    ]
    remaining = [column for column in stage1a_final.columns if column not in first_cols]
    stage1a_final = stage1a_final[first_cols + remaining]

    if unresolved_ids and not allow_unresolved:
        write_csv(stage1a_final, config.STAGE1A_FINAL_CLASSIFICATION_PATH)
        sample = ", ".join(unresolved_ids[:10])
        raise RuntimeError(
            f"Stage 1A requires {len(unresolved_ids)} completed human reviews. "
            f"Sample unresolved provision_id: {sample}. Edit: "
            f"{config.STAGE1A_MANUAL_REVIEW_QUEUE_PATH}. Then run: "
            "python run_pipeline.py stage1a-finalize"
        )

    assert_complete(stage1a_final, provisions)
    write_csv(stage1a_final, config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    write_manifest(stage1a_final, str(stage1a_final["run_id"].iloc[0]))
    print(f"Wrote Stage 1A final classification to {config.STAGE1A_FINAL_CLASSIFICATION_PATH}")
    print(f"Wrote Stage 1A success marker to {config.STAGE1A_SUCCESS_PATH}")


if __name__ == "__main__":
    run()
