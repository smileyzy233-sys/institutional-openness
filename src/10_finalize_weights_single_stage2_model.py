from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils import (
    check_stage1_gate,
    detect_old_six_classification_values,
    ensure_directories,
    load_valid_stage_results,
    normalize_stage2_weights,
    read_csv,
    sha256_file,
    stage2_result_path_for_role,
    utc_timestamp,
    validate_stage2_output,
    write_csv,
)


MODEL_KEEP_COLUMNS = [
    "provision_id",
    "impact_type",
    "raw_trade_weight",
    "raw_investment_weight",
    "normalized_trade_weight",
    "normalized_investment_weight",
    "reason",
    "confidence",
    "model_provider",
    "model_name",
    "prompt_version",
    "run_id",
    "stage1_final_sha256",
    "raw_response",
]


def selected_model_decision(row: pd.Series, model_role: str) -> dict[str, Any]:
    record = {
        "provision_id": row.get("provision_id"),
        "impact_type": row.get("impact_type"),
        "raw_trade_weight": row.get("raw_trade_weight"),
        "raw_investment_weight": row.get("raw_investment_weight"),
        "confidence": row.get("confidence"),
        "raw_response": row.get("raw_response"),
    }
    normalized, status, message = validate_stage2_output(record)
    if status != "ok":
        raise ValueError(f"Invalid Stage 2 model {model_role} row {row.get('provision_id')}: {message}")

    impact_type = normalized["impact_type"]
    method = "single_model_both" if impact_type == "both" else "single_model_fixed"
    return {
        "final_impact_type": impact_type,
        "final_trade_weight": normalized["normalized_trade_weight"],
        "final_investment_weight": normalized["normalized_investment_weight"],
        "stage2_decision_source": f"single_model_{model_role.lower()}",
        "stage2_resolution_method": method,
        "stage2_was_arbitrated": False,
        "stage2_was_human_reviewed": False,
        "final_unresolved": False,
    }


def not_applicable_stage2(model_role: str) -> dict[str, Any]:
    return {
        "model_a_impact_type": "",
        "model_b_impact_type": "",
        "model_a_trade_weight": pd.NA,
        "model_a_investment_weight": pd.NA,
        "model_b_trade_weight": pd.NA,
        "model_b_investment_weight": pd.NA,
        "stage2_single_model_role": model_role,
        "final_impact_type": "not_applicable",
        "final_trade_weight": 0.0,
        "final_investment_weight": 0.0,
        "effective_trade_weight": 0.0,
        "effective_investment_weight": 0.0,
        "stage2_decision_source": "not_applicable",
        "stage2_resolution_method": "not_applicable",
        "stage2_was_arbitrated": False,
        "stage2_was_human_reviewed": False,
        "both_trade_weight_abs_diff": pd.NA,
        "both_investment_weight_abs_diff": pd.NA,
        "final_unresolved": False,
    }


def assert_final_consistent(final_df: pd.DataFrame, provisions: pd.DataFrame) -> None:
    assert len(final_df) == len(provisions)
    assert final_df["provision_id"].is_unique
    assert not final_df["final_unresolved"].astype(str).str.lower().isin({"true", "1"}).any()

    non_inst = pd.to_numeric(
        final_df["final_is_institutional_opening"],
        errors="coerce",
    ).eq(0)
    assert final_df.loc[non_inst, "final_impact_type"].eq("not_applicable").all()
    assert pd.to_numeric(final_df.loc[non_inst, "final_trade_weight"], errors="coerce").eq(0).all()
    assert pd.to_numeric(
        final_df.loc[non_inst, "final_investment_weight"],
        errors="coerce",
    ).eq(0).all()

    inst = pd.to_numeric(
        final_df["final_is_institutional_opening"],
        errors="coerce",
    ).eq(1)
    assert final_df.loc[inst, "final_impact_type"].isin(config.IMPACT_TYPE_VALUES).all()

    both_mask = final_df["final_impact_type"].eq("both")
    trade = pd.to_numeric(final_df["final_trade_weight"], errors="coerce")
    investment = pd.to_numeric(final_df["final_investment_weight"], errors="coerce")
    assert trade[both_mask].gt(0).all()
    assert investment[both_mask].gt(0).all()
    assert (trade[both_mask] + investment[both_mask] - 1.0).abs().le(
        config.WEIGHT_SUM_TOLERANCE
    ).all()

    fixed_expectations = {
        "mp": (1.0, 0.0),
        "tr": (0.0, 1.0),
        "none": (0.0, 0.0),
    }
    for impact_type, (trade_weight, investment_weight) in fixed_expectations.items():
        mask = final_df["final_impact_type"].eq(impact_type)
        assert trade[mask].eq(trade_weight).all()
        assert investment[mask].eq(investment_weight).all()


def build_synthetic_comparison(
    stage1_final: pd.DataFrame,
    model_results: pd.DataFrame,
    *,
    model_role: str,
    stage1_final_sha256: str,
) -> pd.DataFrame:
    eligible = stage1_final[
        pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1)
    ].copy()
    comparison = eligible.merge(
        model_results[[column for column in MODEL_KEEP_COLUMNS if column in model_results.columns]],
        on="provision_id",
        how="left",
        validate="1:1",
    )
    missing = comparison["impact_type"].isna()
    if missing.any():
        raise RuntimeError(
            "Single-model Stage 2 comparison missing selected-model output for "
            f"{int(missing.sum())} eligible provisions."
        )

    impact = comparison["impact_type"].astype(str).str.strip().str.lower()
    trade = pd.to_numeric(comparison["normalized_trade_weight"], errors="coerce")
    investment = pd.to_numeric(comparison["normalized_investment_weight"], errors="coerce")

    out = pd.DataFrame(
        {
            "provision_id": comparison["provision_id"],
            "model_a_impact_type": impact,
            "model_b_impact_type": impact,
            "type_match": True,
            "needs_arbitration": False,
            "conflict_reason": "",
            "model_a_trade_weight": trade,
            "model_a_investment_weight": investment,
            "model_b_trade_weight": trade,
            "model_b_investment_weight": investment,
            "both_trade_weight_abs_diff": 0.0,
            "both_investment_weight_abs_diff": 0.0,
            "stage1_final_sha256": stage1_final_sha256,
            "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            "stage2_single_model_role": model_role,
            "comparison_generated_for": "single_stage2_model_route",
        }
    )
    remaining = [column for column in eligible.columns if column not in out.columns]
    return out.merge(eligible[["provision_id"] + remaining], on="provision_id", how="left")


def write_single_model_interim_files(
    stage1_final: pd.DataFrame,
    model_results: pd.DataFrame,
    *,
    model_role: str,
    stage1_final_sha256: str,
) -> None:
    comparison = build_synthetic_comparison(
        stage1_final,
        model_results,
        model_role=model_role,
        stage1_final_sha256=stage1_final_sha256,
    )
    write_csv(comparison, config.STAGE2_COMPARISON_PATH)
    write_csv(comparison.iloc[0:0].copy(), config.STAGE2_TYPE_CONFLICT_QUEUE_PATH)

    arbitration_cols = [
        "provision_id",
        "final_impact_type",
        "final_trade_weight",
        "final_investment_weight",
        "reason",
        "confidence",
        "need_human_review",
        "parse_status",
        "validation_status",
        "error_message",
        "retry_count",
        "model_role",
        "model_provider",
        "model_name",
        "prompt_version",
        "stage1_final_sha256",
        "pipeline_schema_version",
        "run_id",
        "created_at",
        "input_hash",
        "raw_response",
    ]
    manual_cols = [
        "provision_id",
        "human_review_completed",
        "human_final_impact_type",
        "human_final_trade_weight",
        "human_final_investment_weight",
        "human_review_notes",
    ]
    write_csv(pd.DataFrame(columns=arbitration_cols), config.STAGE2_ARBITRATION_RESULTS_PATH)
    write_csv(pd.DataFrame(columns=manual_cols), config.STAGE2_MANUAL_REVIEW_QUEUE_PATH)


def run(*, model_role: str = "B") -> None:
    model_role = str(model_role or "B").strip().upper()
    if model_role not in {"A", "B"}:
        raise ValueError("model_role must be A or B")

    ensure_directories()
    check_stage1_gate()
    stage1_final_sha256 = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)

    if config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH.exists():
        tech = read_csv(config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
        if not tech.empty:
            raise RuntimeError(
                f"Stage 2 has {len(tech)} unresolved technical errors; cannot finalize."
            )

    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    stage1_final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    detect_old_six_classification_values(stage1_final)

    result_path = stage2_result_path_for_role(model_role)
    model_results = load_valid_stage_results(result_path, stage=2, model_role=model_role)
    if not model_results["stage1_final_sha256"].eq(stage1_final_sha256).all():
        raise RuntimeError(
            f"Stage 2 model {model_role} results are stale because Stage 1 final hash changed."
        )

    model_by_id = model_results.drop_duplicates("provision_id", keep="last").set_index("provision_id")
    eligible_ids = set(
        stage1_final.loc[
            pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1),
            "provision_id",
        ].astype(str)
    )
    missing_ids = sorted(eligible_ids - set(model_by_id.index.astype(str)))
    if missing_ids:
        sample = ", ".join(missing_ids[:10])
        raise RuntimeError(
            f"Stage 2 model {model_role} is missing {len(missing_ids)} eligible provisions; "
            f"sample: {sample}"
        )

    rows: list[dict[str, Any]] = []
    run_id = utc_timestamp().replace(":", "").replace("+", "Z")
    for _, stage1_row in stage1_final.iterrows():
        provision_id = stage1_row["provision_id"]
        base = stage1_row.to_dict()
        base["stage2_eligible"] = int(str(provision_id) in eligible_ids)

        if str(provision_id) not in eligible_ids:
            decision = not_applicable_stage2(model_role)
        else:
            model_row = model_by_id.loc[provision_id]
            if isinstance(model_row, pd.DataFrame):
                model_row = model_row.iloc[-1]
            decision = selected_model_decision(model_row, model_role)
            decision["stage2_single_model_role"] = model_role
            for role in ["A", "B"]:
                prefix = f"model_{role.lower()}"
                if role == model_role:
                    decision[f"{prefix}_impact_type"] = decision["final_impact_type"]
                    decision[f"{prefix}_trade_weight"] = decision["final_trade_weight"]
                    decision[f"{prefix}_investment_weight"] = decision["final_investment_weight"]
                else:
                    decision[f"{prefix}_impact_type"] = ""
                    decision[f"{prefix}_trade_weight"] = pd.NA
                    decision[f"{prefix}_investment_weight"] = pd.NA
            decision["both_trade_weight_abs_diff"] = pd.NA
            decision["both_investment_weight_abs_diff"] = pd.NA
            decision["effective_trade_weight"] = decision["final_trade_weight"]
            decision["effective_investment_weight"] = decision["final_investment_weight"]

        base.update(decision)
        base["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
        base["run_id"] = run_id
        base["stage1_final_sha256"] = stage1_final_sha256
        rows.append(base)

    final_df = pd.DataFrame(rows)
    float_columns = [
        "model_a_trade_weight",
        "model_a_investment_weight",
        "model_b_trade_weight",
        "model_b_investment_weight",
        "final_trade_weight",
        "final_investment_weight",
        "effective_trade_weight",
        "effective_investment_weight",
        "both_trade_weight_abs_diff",
        "both_investment_weight_abs_diff",
    ]
    for column in float_columns:
        if column in final_df.columns:
            final_df[column] = pd.to_numeric(final_df[column], errors="coerce").round(
                config.OUTPUT_FLOAT_DECIMALS
            )

    first_cols = [
        "provision_id",
        "provision_text",
        "chapter_name",
        "section_name",
        "final_is_institutional_opening",
        "final_dominant_dimension",
        "stage1a_decision_source",
        "stage1a_resolution_method",
        "stage1a_was_arbitrated",
        "stage1a_was_human_reviewed",
        "stage1b_decision_source",
        "stage1b_resolution_method",
        "stage1b_was_arbitrated",
        "stage1b_was_human_reviewed",
        "stage1_decision_source",
        "stage1_resolution_method",
        "stage2_eligible",
        "stage2_single_model_role",
        "model_a_impact_type",
        "model_b_impact_type",
        "model_a_trade_weight",
        "model_a_investment_weight",
        "model_b_trade_weight",
        "model_b_investment_weight",
        "final_impact_type",
        "final_trade_weight",
        "final_investment_weight",
        "effective_trade_weight",
        "effective_investment_weight",
        "stage2_decision_source",
        "stage2_resolution_method",
        "stage2_was_arbitrated",
        "stage2_was_human_reviewed",
        "both_trade_weight_abs_diff",
        "both_investment_weight_abs_diff",
        "final_unresolved",
        "pipeline_schema_version",
        "run_id",
        "stage1_final_sha256",
    ]
    remaining = [column for column in final_df.columns if column not in first_cols]
    final_df = final_df[[column for column in first_cols if column in final_df.columns] + remaining]

    assert_final_consistent(final_df, provisions)
    detect_old_six_classification_values(final_df)
    write_csv(final_df, config.FINAL_PROVISION_WEIGHTS_PATH)
    write_single_model_interim_files(
        stage1_final,
        model_results,
        model_role=model_role,
        stage1_final_sha256=stage1_final_sha256,
    )
    print(
        f"Wrote single-model Stage 2 final provision weights using model {model_role} "
        f"to {config.FINAL_PROVISION_WEIGHTS_PATH}"
    )


if __name__ == "__main__":
    run()
