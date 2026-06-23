from __future__ import annotations

from typing import Any

import pandas as pd

import config
from utils import (
    as_bool,
    as_bool_series,
    average_both_weights,
    check_stage1_gate,
    detect_old_six_classification_values,
    ensure_directories,
    normalize_stage2_weights,
    read_csv,
    sha256_file,
    utc_timestamp,
    validate_stage2_arbitration_output,
    validate_stage2_output,
    write_csv,
)


def load_optional_csv(path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return read_csv(path)


def completed_human_stage2(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None or not as_bool(row.get("human_review_completed")):
        return None
    record = {
        "provision_id": row.get("provision_id"),
        "impact_type": row.get("human_final_impact_type"),
        "raw_trade_weight": row.get("human_final_trade_weight"),
        "raw_investment_weight": row.get("human_final_investment_weight"),
        "confidence": None,
    }
    normalized, status, message = validate_stage2_output(record)
    if status != "ok":
        raise ValueError(f"Invalid Stage 2 human review for {row.get('provision_id')}: {message}")
    impact_type = normalized["impact_type"]
    method = "human_both" if impact_type == "both" else "human_fixed"
    return {
        "final_impact_type": impact_type,
        "final_trade_weight": normalized["normalized_trade_weight"],
        "final_investment_weight": normalized["normalized_investment_weight"],
        "stage2_decision_source": "human_review",
        "stage2_resolution_method": method,
        "stage2_was_arbitrated": True,
        "stage2_was_human_reviewed": True,
        "final_unresolved": False,
    }


def valid_arbitration_stage2(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if not (
        str(row.get("parse_status", "")).strip() == "ok"
        and str(row.get("validation_status", "")).strip() == "ok"
        and not as_bool(row.get("need_human_review"))
    ):
        return None
    normalized, status, message = validate_stage2_arbitration_output(row.to_dict())
    if status != "ok":
        raise ValueError(f"Invalid Stage 2 arbitration for {row.get('provision_id')}: {message}")
    impact_type = normalized["final_impact_type"]
    method = "arbitrated_both" if impact_type == "both" else "arbitrated_fixed"
    return {
        "final_impact_type": impact_type,
        "final_trade_weight": normalized["final_trade_weight"],
        "final_investment_weight": normalized["final_investment_weight"],
        "stage2_decision_source": "arbitration_model",
        "stage2_resolution_method": method,
        "stage2_was_arbitrated": True,
        "stage2_was_human_reviewed": False,
        "final_unresolved": False,
    }


def consensus_stage2(row: pd.Series) -> dict[str, Any]:
    impact_type = str(row["model_a_impact_type"]).strip().lower()
    if impact_type != str(row["model_b_impact_type"]).strip().lower():
        raise ValueError(f"Not a Stage 2 consensus row: {row['provision_id']}")
    if impact_type == "both":
        trade_weight, investment_weight = average_both_weights(
            row["model_a_trade_weight"],
            row["model_a_investment_weight"],
            row["model_b_trade_weight"],
            row["model_b_investment_weight"],
        )
        method = "dual_model_weight_mean"
    else:
        trade_weight, investment_weight = normalize_stage2_weights(impact_type, None, None)
        method = "fixed_consensus"
    return {
        "final_impact_type": impact_type,
        "final_trade_weight": trade_weight,
        "final_investment_weight": investment_weight,
        "stage2_decision_source": "dual_model_consensus",
        "stage2_resolution_method": method,
        "stage2_was_arbitrated": False,
        "stage2_was_human_reviewed": False,
        "final_unresolved": False,
    }


def not_applicable_stage2() -> dict[str, Any]:
    return {
        "model_a_impact_type": "",
        "model_b_impact_type": "",
        "model_a_trade_weight": pd.NA,
        "model_a_investment_weight": pd.NA,
        "model_b_trade_weight": pd.NA,
        "model_b_investment_weight": pd.NA,
        "final_impact_type": "not_applicable",
        "final_trade_weight": 0.0,
        "final_investment_weight": 0.0,
        "stage2_decision_source": "not_applicable",
        "stage2_resolution_method": "not_applicable",
        "stage2_was_arbitrated": False,
        "stage2_was_human_reviewed": False,
        "both_trade_weight_abs_diff": pd.NA,
        "both_investment_weight_abs_diff": pd.NA,
        "final_unresolved": False,
    }


def unresolved_stage2() -> dict[str, Any]:
    return {
        "final_impact_type": pd.NA,
        "final_trade_weight": pd.NA,
        "final_investment_weight": pd.NA,
        "stage2_decision_source": "",
        "stage2_resolution_method": "unresolved",
        "stage2_was_arbitrated": True,
        "stage2_was_human_reviewed": False,
        "final_unresolved": True,
    }


def assert_final_consistent(final_df: pd.DataFrame, provisions: pd.DataFrame) -> None:
    assert len(final_df) == len(provisions)
    assert final_df["provision_id"].is_unique
    assert not as_bool_series(final_df["final_unresolved"]).any()

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
    assert pd.to_numeric(final_df.loc[both_mask, "final_trade_weight"], errors="coerce").gt(0).all()
    assert pd.to_numeric(
        final_df.loc[both_mask, "final_investment_weight"],
        errors="coerce",
    ).gt(0).all()
    both_sum = (
        pd.to_numeric(final_df.loc[both_mask, "final_trade_weight"], errors="coerce")
        + pd.to_numeric(final_df.loc[both_mask, "final_investment_weight"], errors="coerce")
    )
    assert (both_sum - 1.0).abs().le(config.WEIGHT_SUM_TOLERANCE).all()

    fixed_expectations = {
        "mp": (1.0, 0.0),
        "tr": (0.0, 1.0),
        "none": (0.0, 0.0),
    }
    for impact_type, (trade_weight, investment_weight) in fixed_expectations.items():
        mask = final_df["final_impact_type"].eq(impact_type)
        assert pd.to_numeric(final_df.loc[mask, "final_trade_weight"], errors="coerce").eq(trade_weight).all()
        assert pd.to_numeric(
            final_df.loc[mask, "final_investment_weight"],
            errors="coerce",
        ).eq(investment_weight).all()


def run(*, allow_unresolved: bool = config.ALLOW_UNRESOLVED) -> None:
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
    eligible_ids = set(
        stage1_final.loc[
            pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1),
            "provision_id",
        ].astype(str)
    )
    comparison = load_optional_csv(config.STAGE2_COMPARISON_PATH, [])
    if eligible_ids and comparison.empty:
        raise RuntimeError("Stage 2 comparison is required for eligible Stage 1 provisions.")
    if not comparison.empty:
        detect_old_six_classification_values(comparison)
        if not comparison["stage1_final_sha256"].eq(stage1_final_sha256).all():
            raise RuntimeError("Stage 2 comparison is stale because Stage 1 final hash changed.")
    arbitration = load_optional_csv(config.STAGE2_ARBITRATION_RESULTS_PATH, [])
    manual = load_optional_csv(config.STAGE2_MANUAL_REVIEW_QUEUE_PATH, [])

    comparison_by_id = (
        comparison.drop_duplicates("provision_id", keep="last").set_index("provision_id")
        if not comparison.empty and "provision_id" in comparison.columns
        else pd.DataFrame().set_index(pd.Index([]))
    )
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

    rows: list[dict[str, Any]] = []
    unresolved_ids: list[str] = []
    for _, stage1_row in stage1_final.iterrows():
        provision_id = stage1_row["provision_id"]
        base = stage1_row.to_dict()
        base["stage2_eligible"] = int(str(provision_id) in eligible_ids)
        if str(provision_id) not in eligible_ids:
            decision = not_applicable_stage2()
        else:
            comp_row = (
                comparison_by_id.loc[provision_id]
                if provision_id in comparison_by_id.index
                else None
            )
            if isinstance(comp_row, pd.DataFrame):
                comp_row = comp_row.iloc[-1]
            if comp_row is None:
                decision = unresolved_stage2()
            else:
                for column in [
                    "model_a_impact_type",
                    "model_b_impact_type",
                    "model_a_trade_weight",
                    "model_a_investment_weight",
                    "model_b_trade_weight",
                    "model_b_investment_weight",
                    "both_trade_weight_abs_diff",
                    "both_investment_weight_abs_diff",
                ]:
                    base[column] = comp_row.get(column)
                if not as_bool(comp_row.get("needs_arbitration")):
                    decision = consensus_stage2(comp_row)
                else:
                    manual_row = (
                        manual_by_id.loc[provision_id]
                        if provision_id in manual_by_id.index
                        else None
                    )
                    if isinstance(manual_row, pd.DataFrame):
                        manual_row = manual_row.iloc[-1]
                    decision = completed_human_stage2(manual_row)
                    if decision is None:
                        arb_row = (
                            arbitration_by_id.loc[provision_id]
                            if provision_id in arbitration_by_id.index
                            else None
                        )
                        if isinstance(arb_row, pd.DataFrame):
                            arb_row = arb_row.iloc[-1]
                        decision = valid_arbitration_stage2(arb_row)
                    if decision is None:
                        decision = unresolved_stage2()
            if decision.get("final_unresolved"):
                unresolved_ids.append(str(provision_id))
        base.update(decision)
        base["effective_trade_weight"] = (
            0.0
            if int(base["final_is_institutional_opening"]) == 0
            else base["final_trade_weight"]
        )
        base["effective_investment_weight"] = (
            0.0
            if int(base["final_is_institutional_opening"]) == 0
            else base["final_investment_weight"]
        )
        base["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
        base["run_id"] = utc_timestamp().replace(":", "").replace("+", "Z")
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

    if unresolved_ids and not allow_unresolved:
        write_csv(final_df, config.FINAL_PROVISION_WEIGHTS_PATH)
        sample = ", ".join(unresolved_ids[:10])
        raise RuntimeError(
            f"Finalization has {len(unresolved_ids)} unresolved Stage 2 provisions; "
            f"sample: {sample}."
        )

    assert_final_consistent(final_df, provisions)
    detect_old_six_classification_values(final_df)
    write_csv(final_df, config.FINAL_PROVISION_WEIGHTS_PATH)
    print(f"Wrote final provision weights to {config.FINAL_PROVISION_WEIGHTS_PATH}")


if __name__ == "__main__":
    run()
