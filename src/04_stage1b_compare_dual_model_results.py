from __future__ import annotations

import pandas as pd

import config
from utils import (
    check_stage1a_gate,
    ensure_directories,
    read_csv,
    read_prompt_with_sha,
    sha256_file,
    stage1b_conflict_reason,
    write_csv,
)


MODEL_KEEP_COLUMNS = [
    "provision_id",
    "dominant_dimension",
    "dimension_reason",
    "confidence",
    "model_provider",
    "model_name",
    "prompt_version",
    "prompt_sha256",
    "stage1a_final_sha256",
    "pipeline_schema_version",
    "run_id",
    "raw_response",
]


def eligible_provisions() -> pd.DataFrame:
    check_stage1a_gate()
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    stage1a = read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    eligible_ids = set(
        stage1a.loc[
            pd.to_numeric(stage1a["final_is_institutional_opening"], errors="coerce").eq(1),
            "provision_id",
        ].astype(str)
    )
    return provisions[provisions["provision_id"].astype(str).isin(eligible_ids)].copy()


def load_stage1b_model_results(
    path,
    role: str,
    expected_ids: set[str],
    prompt_sha256: str,
    stage1a_final_sha256: str,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing Stage 1B model {role} results: {path}")
    df = read_csv(path)
    required = {
        "provision_id",
        "dominant_dimension",
        "parse_status",
        "validation_status",
        "prompt_version",
        "prompt_sha256",
        "stage1a_final_sha256",
        "pipeline_schema_version",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    current = df[
        df["parse_status"].eq("ok")
        & df["validation_status"].eq("ok")
        & df["prompt_version"].astype(str).eq(config.STAGE1B_PROMPT_VERSION)
        & df["prompt_sha256"].astype(str).eq(prompt_sha256)
        & df["stage1a_final_sha256"].astype(str).eq(stage1a_final_sha256)
        & df["pipeline_schema_version"].astype(str).eq(config.PIPELINE_SCHEMA_VERSION)
    ].copy()
    if not current["provision_id"].is_unique:
        raise RuntimeError(f"Stage 1B model {role} has duplicate provision_id values")
    ids = set(current["provision_id"].astype(str))
    if ids != expected_ids:
        raise RuntimeError(
            f"Stage 1B model {role} ID set does not match Stage 1A positive IDs; "
            f"expected={len(expected_ids)}, found={len(ids)}"
        )
    if not current["dominant_dimension"].astype(str).str.lower().isin(
        config.INSTITUTIONAL_DIMENSION_VALUES
    ).all():
        raise RuntimeError(f"Stage 1B model {role} contains invalid dimensions")
    return current


def prefix_model(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    keep = [column for column in MODEL_KEEP_COLUMNS if column in frame.columns]
    out = frame[keep].copy()
    return out.rename(
        columns={column: f"{prefix}_{column}" for column in keep if column != "provision_id"}
    )


def run() -> None:
    ensure_directories()
    eligible = eligible_provisions()
    expected_ids = set(eligible["provision_id"].astype(str))
    stage1a_final_sha256 = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    _prompt, prompt_sha256 = read_prompt_with_sha(config.STAGE1B_PROMPT_PATH)

    if not expected_ids:
        empty = pd.DataFrame(
            columns=[
                "provision_id",
                "model_a_dominant_dimension",
                "model_b_dominant_dimension",
                "dimension_match",
                "needs_arbitration",
                "conflict_reason",
                "stage1a_final_sha256",
                "pipeline_schema_version",
            ]
        )
        write_csv(empty, config.STAGE1B_COMPARISON_PATH)
        write_csv(empty, config.STAGE1B_CONFLICT_QUEUE_PATH)
        print("Stage 1B has no eligible provisions; wrote empty comparison files.")
        return

    model_a = load_stage1b_model_results(
        config.STAGE1B_MODEL_A_RESULTS_PATH,
        "A",
        expected_ids,
        prompt_sha256,
        stage1a_final_sha256,
    )
    model_b = load_stage1b_model_results(
        config.STAGE1B_MODEL_B_RESULTS_PATH,
        "B",
        expected_ids,
        prompt_sha256,
        stage1a_final_sha256,
    )

    comparison = eligible.merge(prefix_model(model_a, "model_a"), on="provision_id", how="left")
    comparison = comparison.merge(
        prefix_model(model_b, "model_b"),
        on="provision_id",
        how="left",
        validate="1:1",
    )
    reasons = comparison.apply(
        lambda row: stage1b_conflict_reason(
            row["model_a_dominant_dimension"],
            row["model_b_dominant_dimension"],
        ),
        axis=1,
        result_type="expand",
    )
    reasons.columns = ["dimension_match", "needs_arbitration", "conflict_reason"]
    comparison = pd.concat([comparison, reasons], axis=1)
    comparison["stage1a_final_sha256"] = stage1a_final_sha256
    comparison["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION

    first_columns = [
        "provision_id",
        "model_a_dominant_dimension",
        "model_b_dominant_dimension",
        "dimension_match",
        "needs_arbitration",
        "conflict_reason",
        "stage1a_final_sha256",
        "pipeline_schema_version",
    ]
    remaining = [column for column in comparison.columns if column not in first_columns]
    comparison = comparison[first_columns + remaining]
    write_csv(comparison, config.STAGE1B_COMPARISON_PATH)

    conflict_queue = comparison[comparison["needs_arbitration"]].copy()
    write_csv(conflict_queue, config.STAGE1B_CONFLICT_QUEUE_PATH)

    total = len(comparison)
    conflict_count = len(conflict_queue)
    conflict_rate = conflict_count / total if total else 0
    print(f"Stage 1B eligible provisions: {total:,}")
    print(f"Stage 1B match count: {total - conflict_count:,}")
    print(f"Stage 1B conflict count: {conflict_count:,}")
    print(f"Stage 1B conflict rate: {conflict_rate:.2%}")
    print(f"Wrote Stage 1B comparison rows to {config.STAGE1B_COMPARISON_PATH}")
    print(f"Wrote Stage 1B conflict rows to {config.STAGE1B_CONFLICT_QUEUE_PATH}")


if __name__ == "__main__":
    run()
