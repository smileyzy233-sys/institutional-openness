from __future__ import annotations

import pandas as pd

import config
from utils import (
    as_bool_series,
    check_stage1_gate,
    ensure_directories,
    load_valid_stage_results,
    read_csv,
    sha256_file,
    stage2_needs_arbitration,
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


def prefix_model(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    keep = [column for column in MODEL_KEEP_COLUMNS if column in frame.columns]
    out = frame[keep].copy()
    out = out.rename(
        columns={column: f"{prefix}_{column}" for column in keep if column != "provision_id"}
    )
    out = out.rename(
        columns={
            f"{prefix}_normalized_trade_weight": f"{prefix}_trade_weight",
            f"{prefix}_normalized_investment_weight": f"{prefix}_investment_weight",
        }
    )
    return out


def mark_stale_and_raise(frame: pd.DataFrame, path, current_hash: str) -> None:
    stale = ~frame["stage1_final_sha256"].eq(current_hash)
    if stale.any():
        frame = frame.copy()
        frame["stale"] = stale
        write_csv(frame, path)
        raise RuntimeError(
            f"Stage 2 results in {path} are stale because stage1_final_sha256 changed."
        )


def run() -> None:
    ensure_directories()
    check_stage1_gate()
    current_hash = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    stage1_final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    eligible = stage1_final[
        pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1)
    ].copy()

    if config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH.exists():
        tech = read_csv(config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
        if not tech.empty:
            raise RuntimeError(
                f"Stage 2 has {len(tech)} unresolved technical errors; cannot compare."
            )

    if eligible.empty:
        empty = pd.DataFrame(columns=[
            "provision_id",
            "model_a_impact_type",
            "model_b_impact_type",
            "type_match",
            "needs_arbitration",
            "conflict_reason",
            "stage1_final_sha256",
            "pipeline_schema_version",
        ])
        write_csv(empty, config.STAGE2_COMPARISON_PATH)
        write_csv(empty, config.STAGE2_TYPE_CONFLICT_QUEUE_PATH)
        print("Stage 2 has no eligible provisions; wrote empty comparison files.")
        return

    model_a = load_valid_stage_results(
        config.STAGE2_MODEL_A_RESULTS_PATH,
        stage=2,
        model_role="A",
    )
    model_b = load_valid_stage_results(
        config.STAGE2_MODEL_B_RESULTS_PATH,
        stage=2,
        model_role="B",
    )
    mark_stale_and_raise(model_a, config.STAGE2_MODEL_A_RESULTS_PATH, current_hash)
    mark_stale_and_raise(model_b, config.STAGE2_MODEL_B_RESULTS_PATH, current_hash)

    comparison = eligible.merge(prefix_model(model_a, "model_a"), on="provision_id", how="left")
    comparison = comparison.merge(
        prefix_model(model_b, "model_b"),
        on="provision_id",
        how="left",
        validate="1:1",
    )
    missing_a = comparison["model_a_impact_type"].isna()
    missing_b = comparison["model_b_impact_type"].isna()
    if missing_a.any() or missing_b.any():
        raise RuntimeError(
            "Stage 2 comparison requires one valid model A and model B result for each "
            f"eligible provision; missing A={int(missing_a.sum())}, missing B={int(missing_b.sum())}"
        )

    comparison["type_match"] = comparison["model_a_impact_type"].astype(str).str.lower().eq(
        comparison["model_b_impact_type"].astype(str).str.lower()
    )
    comparison["needs_arbitration"] = comparison.apply(
        lambda row: stage2_needs_arbitration(
            row["model_a_impact_type"],
            row["model_b_impact_type"],
        ),
        axis=1,
    )
    comparison["conflict_reason"] = comparison["needs_arbitration"].map(
        {True: "impact_type", False: ""}
    )
    both_both = (
        comparison["model_a_impact_type"].astype(str).str.lower().eq("both")
        & comparison["model_b_impact_type"].astype(str).str.lower().eq("both")
    )
    comparison["both_trade_weight_abs_diff"] = (
        pd.to_numeric(comparison["model_a_trade_weight"], errors="coerce")
        - pd.to_numeric(comparison["model_b_trade_weight"], errors="coerce")
    ).abs().where(both_both)
    comparison["both_investment_weight_abs_diff"] = (
        pd.to_numeric(comparison["model_a_investment_weight"], errors="coerce")
        - pd.to_numeric(comparison["model_b_investment_weight"], errors="coerce")
    ).abs().where(both_both)
    comparison["both_trade_weight_abs_diff"] = comparison[
        "both_trade_weight_abs_diff"
    ].round(config.OUTPUT_FLOAT_DECIMALS)
    comparison["both_investment_weight_abs_diff"] = comparison[
        "both_investment_weight_abs_diff"
    ].round(config.OUTPUT_FLOAT_DECIMALS)
    comparison["stage1_final_sha256"] = current_hash
    comparison["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION

    first_columns = [
        "provision_id",
        "model_a_impact_type",
        "model_b_impact_type",
        "type_match",
        "needs_arbitration",
        "conflict_reason",
        "model_a_trade_weight",
        "model_a_investment_weight",
        "model_b_trade_weight",
        "model_b_investment_weight",
        "both_trade_weight_abs_diff",
        "both_investment_weight_abs_diff",
        "stage1_final_sha256",
        "pipeline_schema_version",
    ]
    remaining = [column for column in comparison.columns if column not in first_columns]
    comparison = comparison[first_columns + remaining]
    write_csv(comparison, config.STAGE2_COMPARISON_PATH)

    conflict_queue = comparison[as_bool_series(comparison["needs_arbitration"])].copy()
    write_csv(conflict_queue, config.STAGE2_TYPE_CONFLICT_QUEUE_PATH)
    print(f"Wrote {len(comparison):,} Stage 2 comparison rows to {config.STAGE2_COMPARISON_PATH}")
    print(f"Wrote {len(conflict_queue):,} Stage 2 type conflicts to {config.STAGE2_TYPE_CONFLICT_QUEUE_PATH}")


if __name__ == "__main__":
    run()
