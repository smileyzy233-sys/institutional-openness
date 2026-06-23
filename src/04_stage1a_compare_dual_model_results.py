from __future__ import annotations

import pandas as pd

import config
from utils import (
    ensure_directories,
    read_csv,
    read_prompt_with_sha,
    stage1a_conflict_reason,
    write_csv,
)


MODEL_KEEP_COLUMNS = [
    "provision_id",
    "is_institutional_opening",
    "institutional_reason",
    "confidence",
    "model_provider",
    "model_name",
    "prompt_version",
    "prompt_sha256",
    "pipeline_schema_version",
    "run_id",
    "raw_response",
]


def load_stage1a_model_results(path, role: str, expected_count: int, prompt_sha256: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing Stage 1A model {role} results: {path}")
    df = read_csv(path)
    required = {
        "provision_id",
        "is_institutional_opening",
        "parse_status",
        "validation_status",
        "prompt_version",
        "prompt_sha256",
        "pipeline_schema_version",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    current = df[
        df["parse_status"].eq("ok")
        & df["validation_status"].eq("ok")
        & df["prompt_version"].astype(str).eq(config.STAGE1A_PROMPT_VERSION)
        & df["prompt_sha256"].astype(str).eq(prompt_sha256)
        & df["pipeline_schema_version"].astype(str).eq(config.PIPELINE_SCHEMA_VERSION)
    ].copy()
    if len(current) != expected_count:
        raise RuntimeError(
            f"Stage 1A model {role} requires {expected_count} current valid rows; "
            f"found {len(current)}"
        )
    if not current["provision_id"].is_unique:
        raise RuntimeError(f"Stage 1A model {role} has duplicate provision_id values")
    return current


def prefix_model(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    keep = [column for column in MODEL_KEEP_COLUMNS if column in frame.columns]
    out = frame[keep].copy()
    return out.rename(
        columns={column: f"{prefix}_{column}" for column in keep if column != "provision_id"}
    )


def run() -> None:
    ensure_directories()
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    _prompt_template, prompt_sha256 = read_prompt_with_sha(config.STAGE1A_PROMPT_PATH)
    expected_count = len(provisions)
    model_a = load_stage1a_model_results(
        config.STAGE1A_MODEL_A_RESULTS_PATH,
        "A",
        expected_count,
        prompt_sha256,
    )
    model_b = load_stage1a_model_results(
        config.STAGE1A_MODEL_B_RESULTS_PATH,
        "B",
        expected_count,
        prompt_sha256,
    )

    comparison = provisions.merge(prefix_model(model_a, "model_a"), on="provision_id", how="left")
    comparison = comparison.merge(
        prefix_model(model_b, "model_b"),
        on="provision_id",
        how="left",
        validate="1:1",
    )
    missing_a = comparison["model_a_is_institutional_opening"].isna()
    missing_b = comparison["model_b_is_institutional_opening"].isna()
    if missing_a.any() or missing_b.any():
        raise RuntimeError(
            "Stage 1A comparison requires one valid model A and model B result per provision; "
            f"missing A={int(missing_a.sum())}, missing B={int(missing_b.sum())}"
        )

    reasons = comparison.apply(
        lambda row: stage1a_conflict_reason(
            row["model_a_is_institutional_opening"],
            row["model_b_is_institutional_opening"],
        ),
        axis=1,
        result_type="expand",
    )
    reasons.columns = ["institutional_match", "needs_arbitration", "conflict_reason"]
    comparison = pd.concat([comparison, reasons], axis=1)
    comparison["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION

    first_columns = [
        "provision_id",
        "model_a_is_institutional_opening",
        "model_b_is_institutional_opening",
        "institutional_match",
        "needs_arbitration",
        "conflict_reason",
        "pipeline_schema_version",
    ]
    remaining = [column for column in comparison.columns if column not in first_columns]
    comparison = comparison[first_columns + remaining]
    write_csv(comparison, config.STAGE1A_COMPARISON_PATH)

    conflict_queue = comparison[comparison["needs_arbitration"]].copy()
    write_csv(conflict_queue, config.STAGE1A_CONFLICT_QUEUE_PATH)

    conflict_count = len(conflict_queue)
    conflict_rate = conflict_count / expected_count if expected_count else 0
    print(f"Stage 1A total provisions: {expected_count:,}")
    print(f"Stage 1A match count: {expected_count - conflict_count:,}")
    print(f"Stage 1A conflict count: {conflict_count:,}")
    print(f"Stage 1A conflict rate: {conflict_rate:.2%}")
    print(f"Wrote Stage 1A comparison rows to {config.STAGE1A_COMPARISON_PATH}")
    print(f"Wrote Stage 1A conflict rows to {config.STAGE1A_CONFLICT_QUEUE_PATH}")


if __name__ == "__main__":
    run()
