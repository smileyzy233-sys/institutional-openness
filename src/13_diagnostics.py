from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils import as_bool_series, ensure_directories, read_csv, write_csv


def safe_csv(path) -> pd.DataFrame:
    return read_csv(path) if path.exists() else pd.DataFrame()


def ok_unique_count(frame: pd.DataFrame) -> int:
    if frame.empty or "provision_id" not in frame.columns:
        return 0
    if {"parse_status", "validation_status"}.issubset(frame.columns):
        frame = frame[frame["parse_status"].eq("ok") & frame["validation_status"].eq("ok")]
    return int(frame["provision_id"].nunique())


def completed_human_count(frame: pd.DataFrame) -> int:
    if frame.empty or "human_review_completed" not in frame.columns:
        return 0
    return int(as_bool_series(frame["human_review_completed"]).sum())


def old_value_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    count = 0
    for column in frame.columns:
        values = frame[column].dropna().astype(str).str.strip().str.lower()
        count += int(values.isin(config.OLD_SIX_CLASSIFICATION_VALUES).sum())
    return count


def final_quality(final: pd.DataFrame, provisions: pd.DataFrame) -> dict[str, Any]:
    if final.empty:
        return {
            "quality_final_generated": False,
        }
    non_inst = pd.to_numeric(final["final_is_institutional_opening"], errors="coerce").eq(0)
    both = final["final_impact_type"].eq("both")
    mp = final["final_impact_type"].eq("mp")
    tr = final["final_impact_type"].eq("tr")
    none = final["final_impact_type"].eq("none")
    trade = pd.to_numeric(final["final_trade_weight"], errors="coerce")
    invest = pd.to_numeric(final["final_investment_weight"], errors="coerce")
    return {
        "quality_final_generated": True,
        "quality_non_institutional_not_applicable": bool(final.loc[non_inst, "final_impact_type"].eq("not_applicable").all()),
        "quality_non_institutional_zero_weights": bool((trade[non_inst].eq(0) & invest[non_inst].eq(0)).all()),
        "quality_mp_fixed_1_0": bool((trade[mp].eq(1) & invest[mp].eq(0)).all()),
        "quality_tr_fixed_0_1": bool((trade[tr].eq(0) & invest[tr].eq(1)).all()),
        "quality_none_fixed_0_0": bool((trade[none].eq(0) & invest[none].eq(0)).all()),
        "quality_both_weights_positive": bool((trade[both].gt(0) & invest[both].gt(0)).all()),
        "quality_both_weight_sum_1": bool((trade[both] + invest[both] - 1.0).abs().le(config.WEIGHT_SUM_TOLERANCE).all()),
        "quality_final_count_matches_master": bool(len(final) == len(provisions)),
        "quality_duplicate_provision_id_count": int(final["provision_id"].duplicated().sum()),
        "quality_missing_weight_count": int(final[["final_trade_weight", "final_investment_weight"]].isna().any(axis=1).sum()),
        "quality_old_six_classification_value_count": old_value_count(final),
        "quality_unresolved_count": int(as_bool_series(final["final_unresolved"]).sum()) if "final_unresolved" in final.columns else 0,
    }


def run() -> None:
    ensure_directories()
    provisions = safe_csv(config.PROVISIONS_MASTER_PATH)
    stage1a_a = safe_csv(config.STAGE1A_MODEL_A_RESULTS_PATH)
    stage1a_b = safe_csv(config.STAGE1A_MODEL_B_RESULTS_PATH)
    stage1a_tech = safe_csv(config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH)
    stage1a_comparison = safe_csv(config.STAGE1A_COMPARISON_PATH)
    stage1a_conflict = safe_csv(config.STAGE1A_CONFLICT_QUEUE_PATH)
    stage1a_arbitration = safe_csv(config.STAGE1A_ARBITRATION_RESULTS_PATH)
    stage1a_manual = safe_csv(config.STAGE1A_MANUAL_REVIEW_QUEUE_PATH)
    stage1a_final = safe_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    stage1b_a = safe_csv(config.STAGE1B_MODEL_A_RESULTS_PATH)
    stage1b_b = safe_csv(config.STAGE1B_MODEL_B_RESULTS_PATH)
    stage1b_tech = safe_csv(config.STAGE1B_TECHNICAL_ERROR_QUEUE_PATH)
    stage1b_comparison = safe_csv(config.STAGE1B_COMPARISON_PATH)
    stage1b_conflict = safe_csv(config.STAGE1B_CONFLICT_QUEUE_PATH)
    stage1b_arbitration = safe_csv(config.STAGE1B_ARBITRATION_RESULTS_PATH)
    stage1b_manual = safe_csv(config.STAGE1B_MANUAL_REVIEW_QUEUE_PATH)
    stage1b_final = safe_csv(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    stage1_final = safe_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)

    stage2_a = safe_csv(config.STAGE2_MODEL_A_RESULTS_PATH)
    stage2_b = safe_csv(config.STAGE2_MODEL_B_RESULTS_PATH)
    stage2_tech = safe_csv(config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
    stage2_comparison = safe_csv(config.STAGE2_COMPARISON_PATH)
    stage2_conflict = safe_csv(config.STAGE2_TYPE_CONFLICT_QUEUE_PATH)
    stage2_arbitration = safe_csv(config.STAGE2_ARBITRATION_RESULTS_PATH)
    stage2_manual = safe_csv(config.STAGE2_MANUAL_REVIEW_QUEUE_PATH)
    final = safe_csv(config.FINAL_PROVISION_WEIGHTS_PATH)

    stage1a_conflict_rate = (
        len(stage1a_conflict) / len(provisions)
        if len(provisions)
        else 0.0
    )
    stage1b_conflict_rate = (
        len(stage1b_conflict) / len(stage1b_comparison)
        if len(stage1b_comparison)
        else 0.0
    )
    stage1_unique_arbitrated_ids: set[str] = set()
    if "stage1a_was_arbitrated" in stage1_final.columns:
        stage1_unique_arbitrated_ids |= set(
            stage1_final.loc[
                as_bool_series(stage1_final["stage1a_was_arbitrated"]),
                "provision_id",
            ].astype(str)
        )
    if "stage1b_was_arbitrated" in stage1_final.columns:
        stage1_unique_arbitrated_ids |= set(
            stage1_final.loc[
                as_bool_series(stage1_final["stage1b_was_arbitrated"]),
                "provision_id",
            ].astype(str)
        )
    stage1_unique_human_ids: set[str] = set()
    if "stage1a_was_human_reviewed" in stage1_final.columns:
        stage1_unique_human_ids |= set(
            stage1_final.loc[
                as_bool_series(stage1_final["stage1a_was_human_reviewed"]),
                "provision_id",
            ].astype(str)
        )
    if "stage1b_was_human_reviewed" in stage1_final.columns:
        stage1_unique_human_ids |= set(
            stage1_final.loc[
                as_bool_series(stage1_final["stage1b_was_human_reviewed"]),
                "provision_id",
            ].astype(str)
        )
    unique_arbitration_rate = (
        len(stage1_unique_arbitrated_ids) / len(provisions)
        if len(provisions)
        else 0.0
    )

    diagnostics: dict[str, Any] = {
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "provisions_count": len(provisions),
        "stage1a_model_a_success_count": ok_unique_count(stage1a_a),
        "stage1a_model_b_success_count": ok_unique_count(stage1a_b),
        "stage1a_technical_failure_count": len(stage1a_tech),
        "stage1a_match_count": int(stage1a_comparison.get("institutional_match", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1"}).sum()),
        "stage1a_conflict_count": len(stage1a_conflict),
        "stage1a_conflict_rate": stage1a_conflict_rate,
        "stage1a_arbitration_completed_count": ok_unique_count(stage1a_arbitration),
        "stage1a_human_review_count": completed_human_count(stage1a_manual),
        "stage1a_unresolved_count": int(as_bool_series(stage1a_final["stage1a_unresolved"]).sum()) if "stage1a_unresolved" in stage1a_final.columns else 0,
        "stage1a_institutional_count": int(pd.to_numeric(stage1a_final.get("final_is_institutional_opening", pd.Series(dtype=float)), errors="coerce").eq(1).sum()),
        "stage1a_non_institutional_count": int(pd.to_numeric(stage1a_final.get("final_is_institutional_opening", pd.Series(dtype=float)), errors="coerce").eq(0).sum()),
        "stage1b_eligible_count": len(stage1b_final),
        "stage1b_model_a_success_count": ok_unique_count(stage1b_a),
        "stage1b_model_b_success_count": ok_unique_count(stage1b_b),
        "stage1b_technical_failure_count": len(stage1b_tech),
        "stage1b_match_count": int(stage1b_comparison.get("dimension_match", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1"}).sum()),
        "stage1b_conflict_count": len(stage1b_conflict),
        "stage1b_conflict_rate": stage1b_conflict_rate,
        "stage1b_arbitration_completed_count": ok_unique_count(stage1b_arbitration),
        "stage1b_human_review_count": completed_human_count(stage1b_manual),
        "stage1b_unresolved_count": int(as_bool_series(stage1b_final["stage1b_unresolved"]).sum()) if "stage1b_unresolved" in stage1b_final.columns else 0,
        "stage1_unique_arbitrated_provision_count": len(stage1_unique_arbitrated_ids),
        "stage1_unique_arbitrated_provision_rate": unique_arbitration_rate,
        "stage1_unique_human_reviewed_provision_count": len(stage1_unique_human_ids),
        "stage1_unique_human_reviewed_provision_rate": (
            len(stage1_unique_human_ids) / len(provisions) if len(provisions) else 0.0
        ),
        "quality_stage1a_conflict_rate_below_target": bool(stage1a_conflict_rate < config.STAGE1_ARBITRATION_RATE_TARGET),
        "quality_stage1b_conflict_rate_below_target": bool(stage1b_conflict_rate < config.STAGE1_ARBITRATION_RATE_TARGET),
        "quality_stage1_unique_arbitration_rate_below_target": bool(unique_arbitration_rate < config.STAGE1_ARBITRATION_RATE_TARGET),
        "stage1_unresolved_count": int(as_bool_series(stage1_final["stage1_unresolved"]).sum()) if "stage1_unresolved" in stage1_final.columns else 0,
        "stage1_institutional_provision_count": int(pd.to_numeric(stage1_final.get("final_is_institutional_opening", pd.Series(dtype=float)), errors="coerce").eq(1).sum()),
        "stage1_non_institutional_provision_count": int(pd.to_numeric(stage1_final.get("final_is_institutional_opening", pd.Series(dtype=float)), errors="coerce").eq(0).sum()),
    }
    if "final_dominant_dimension" in stage1_final.columns:
        dimensions = stage1_final["final_dominant_dimension"].astype(str).str.lower()
        for dimension in ["rules", "regulation", "management", "standards", "none"]:
            diagnostics[f"stage1_final_dimension_{dimension}_count"] = int(dimensions.eq(dimension).sum())

    diagnostics.update(
        {
            "stage2_should_process_count": int(len(stage1_final[pd.to_numeric(stage1_final.get("final_is_institutional_opening", pd.Series(dtype=float)), errors="coerce").eq(1)])) if not stage1_final.empty else 0,
            "stage2_actual_processed_count": int(stage2_comparison["provision_id"].nunique()) if "provision_id" in stage2_comparison.columns else 0,
            "stage2_model_a_success_count": ok_unique_count(stage2_a),
            "stage2_model_b_success_count": ok_unique_count(stage2_b),
            "stage2_technical_failure_count": len(stage2_tech),
            "stage2_type_match_count": int(stage2_comparison.get("type_match", pd.Series(dtype=bool)).astype(str).str.lower().isin({"true", "1"}).sum()),
            "stage2_type_conflict_count": len(stage2_conflict),
            "stage2_type_arbitration_count": ok_unique_count(stage2_arbitration),
            "stage2_human_review_count": completed_human_count(stage2_manual),
            "stage2_unresolved_count": int(as_bool_series(final["final_unresolved"]).sum()) if "final_unresolved" in final.columns else 0,
        }
    )
    if "final_impact_type" in final.columns:
        impact = final["final_impact_type"].astype(str).str.lower()
        for impact_type in ["mp", "tr", "both", "none", "not_applicable"]:
            diagnostics[f"final_impact_type_{impact_type}_count"] = int(impact.eq(impact_type).sum())

    both_rows = stage2_comparison[
        stage2_comparison.get("model_a_impact_type", pd.Series(dtype=str)).astype(str).str.lower().eq("both")
        & stage2_comparison.get("model_b_impact_type", pd.Series(dtype=str)).astype(str).str.lower().eq("both")
    ] if not stage2_comparison.empty else pd.DataFrame()
    if both_rows.empty:
        diagnostics.update(
            {
                "both_model_a_avg_trade_weight": float("nan"),
                "both_model_b_avg_trade_weight": float("nan"),
                "both_final_avg_trade_weight": float("nan"),
                "both_model_trade_weight_mean_abs_diff": float("nan"),
                "both_model_trade_weight_max_abs_diff": float("nan"),
                "both_model_trade_weight_median_abs_diff": float("nan"),
            }
        )
    else:
        a_trade = pd.to_numeric(both_rows["model_a_trade_weight"], errors="coerce")
        b_trade = pd.to_numeric(both_rows["model_b_trade_weight"], errors="coerce")
        diff = (a_trade - b_trade).abs()
        final_both = final[final.get("final_impact_type", pd.Series(dtype=str)).eq("both")]
        diagnostics.update(
            {
                "both_model_a_avg_trade_weight": float(a_trade.mean()),
                "both_model_b_avg_trade_weight": float(b_trade.mean()),
                "both_final_avg_trade_weight": float(pd.to_numeric(final_both.get("final_trade_weight", pd.Series(dtype=float)), errors="coerce").mean()),
                "both_model_trade_weight_mean_abs_diff": float(diff.mean()),
                "both_model_trade_weight_max_abs_diff": float(diff.max()),
                "both_model_trade_weight_median_abs_diff": float(diff.median()),
            }
        )

    diagnostics.update(final_quality(final, provisions))
    output = pd.DataFrame([diagnostics])
    write_csv(output, config.DIAGNOSTICS_SUMMARY_PATH)
    print(output.to_string(index=False))
    print(f"Wrote diagnostics to {config.DIAGNOSTICS_SUMMARY_PATH}")


if __name__ == "__main__":
    run()
