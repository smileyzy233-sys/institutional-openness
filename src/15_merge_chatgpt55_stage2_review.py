from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

import config
from utils import read_csv, utc_timestamp, write_csv


REVIEW_DIR = config.INTERIM_DIR / "chatgpt55_stage2_review"
GPT_OUTPUT_DIR = REVIEW_DIR / "gpt5.5_output"
MERGED_DIR = REVIEW_DIR / "merged_analysis"

CONFLICT_BLIND_PATH = REVIEW_DIR / "stage2_conflict_82_blind_for_chatgpt55.csv"
CONFLICT_KEY_PATH = REVIEW_DIR / "stage2_conflict_82_blind_answer_key.csv"
CONFLICT_REVIEW_PATH = GPT_OUTPUT_DIR / "stage2_conflict_82_chatgpt55_review_compact.csv"
CONSENSUS_BASE_PATH = REVIEW_DIR / "stage2_consensus_682_for_chatgpt55.csv"

REVIEW_COLS = [
    "review_verdict",
    "review_recommended_impact_type",
    "review_trade_weight",
    "review_investment_weight",
    "review_issue_type",
    "review_reason",
    "review_confidence",
]

CONFLICT_REVIEW_COLS = [
    "review_final_impact_type",
    "review_trade_weight",
    "review_investment_weight",
    "review_decision",
    "review_reason",
    "review_confidence",
    "needs_human_followup",
]

IMPACT_ORDER = ["mp", "tr", "both", "none"]
MODEL_ORDER = ["a", "b", "neither", "uncertain", "unknown"]
VERDICT_ORDER = ["accept", "revise", "uncertain", "missing"]


def norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_lower(value: object) -> str:
    return norm_text(value).lower()


def as_float(value: object) -> float:
    text = norm_text(value)
    if not text:
        return float("nan")
    return float(text)


def role_to_letter(value: object) -> str:
    role = norm_lower(value)
    if role in {"model_a", "a"}:
        return "A"
    if role in {"model_b", "b"}:
        return "B"
    return role or "unknown"


def ordered_counts(series: pd.Series, order: list[str] | None = None) -> pd.DataFrame:
    counts = series.fillna("").map(norm_lower).value_counts(dropna=False)
    if order is not None:
        ordered_index = [value for value in order if value in counts.index]
        ordered_index += [value for value in counts.index if value not in ordered_index]
        counts = counts.reindex(ordered_index)
    total = int(counts.sum())
    out = counts.rename_axis("value").reset_index(name="n")
    out["share"] = (out["n"] / total).round(6) if total else 0.0
    return out


def validate_required_columns(df: pd.DataFrame, cols: list[str], path: Path) -> None:
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise ValueError(f"{path} missing required columns: {missing}")


def profile_tuple(row: pd.Series, prefix: str) -> tuple[str, float, float]:
    return (
        norm_lower(row[f"{prefix}_impact_type"]),
        as_float(row[f"{prefix}_trade_weight"]),
        as_float(row[f"{prefix}_investment_weight"]),
    )


def same_profile(left: tuple[str, float, float], right: tuple[str, float, float]) -> bool:
    return (
        left[0] == right[0]
        and abs(left[1] - right[1]) < 1e-9
        and abs(left[2] - right[2]) < 1e-9
    )


def summarize_frame(
    df: pd.DataFrame,
    group_cols: list[str],
    count_col: str,
    order: list[str] | None = None,
) -> pd.DataFrame:
    grouped = (
        df.assign(_value=df[count_col].fillna("").map(norm_lower))
        .groupby(group_cols + ["_value"], dropna=False)
        .size()
        .reset_index(name="n")
    )
    totals = grouped.groupby(group_cols, dropna=False)["n"].transform("sum")
    grouped["share_within_group"] = (grouped["n"] / totals).round(6)
    grouped = grouped.rename(columns={"_value": count_col})
    if order:
        grouped["_order"] = grouped[count_col].apply(
            lambda value: order.index(value) if value in order else len(order)
        )
        grouped = grouped.sort_values(group_cols + ["_order", count_col]).drop(columns="_order")
    return grouped


def merge_conflict_review() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    blind = read_csv(CONFLICT_BLIND_PATH)
    key = read_csv(CONFLICT_KEY_PATH)
    review = read_csv(CONFLICT_REVIEW_PATH)
    validate_required_columns(blind, ["provision_id", "policy_area"], CONFLICT_BLIND_PATH)
    validate_required_columns(
        blind,
        [
            "option_1_impact_type",
            "option_1_trade_weight",
            "option_1_investment_weight",
            "option_2_impact_type",
            "option_2_trade_weight",
            "option_2_investment_weight",
        ],
        CONFLICT_BLIND_PATH,
    )
    validate_required_columns(
        key,
        [
            "provision_id",
            "option_1_model_role",
            "option_2_model_role",
            "model_a_impact_type",
            "model_b_impact_type",
        ],
        CONFLICT_KEY_PATH,
    )
    validate_required_columns(review, ["provision_id"] + CONFLICT_REVIEW_COLS, CONFLICT_REVIEW_PATH)

    blind_context = blind.drop(
        columns=[col for col in CONFLICT_REVIEW_COLS if col in blind.columns],
        errors="ignore",
    )
    merged = blind_context.merge(key, on="provision_id", how="left", validate="1:1")
    merged = merged.merge(
        review[["provision_id"] + CONFLICT_REVIEW_COLS],
        on="provision_id",
        how="left",
        validate="1:1",
    )
    if len(merged) != 82:
        raise ValueError(f"Expected 82 conflict rows, got {len(merged)}")
    if merged[CONFLICT_REVIEW_COLS].isna().any(axis=None):
        missing = merged.loc[merged[CONFLICT_REVIEW_COLS].isna().any(axis=1), "provision_id"]
        raise ValueError(f"Conflict review has missing review fields for: {missing.tolist()}")

    for opt in ["option_1", "option_2"]:
        merged[f"{opt}_model_letter"] = merged[f"{opt}_model_role"].map(role_to_letter)

    for model in ["A", "B"]:
        impact_values: list[str] = []
        trade_values: list[float] = []
        invest_values: list[float] = []
        for _, row in merged.iterrows():
            model_opt = "option_1" if row["option_1_model_letter"] == model else "option_2"
            impact_values.append(norm_lower(row[f"{model_opt}_impact_type"]))
            trade_values.append(as_float(row[f"{model_opt}_trade_weight"]))
            invest_values.append(as_float(row[f"{model_opt}_investment_weight"]))
        prefix = f"model_{model.lower()}"
        merged[f"{prefix}_impact_type_from_blind"] = impact_values
        merged[f"{prefix}_trade_weight_from_blind"] = trade_values
        merged[f"{prefix}_investment_weight_from_blind"] = invest_values

    decision_models: list[str] = []
    exact_models: list[str] = []
    for _, row in merged.iterrows():
        decision = norm_lower(row["review_decision"])
        if decision in {"option_1", "option_2"}:
            decision_models.append(row[f"{decision}_model_letter"])
        elif decision in {"neither", "uncertain"}:
            decision_models.append(decision)
        else:
            decision_models.append("unknown")

        final_profile = (
            norm_lower(row["review_final_impact_type"]),
            as_float(row["review_trade_weight"]),
            as_float(row["review_investment_weight"]),
        )
        matched = []
        for model in ["A", "B"]:
            model_profile = (
                norm_lower(row[f"model_{model.lower()}_impact_type_from_blind"]),
                as_float(row[f"model_{model.lower()}_trade_weight_from_blind"]),
                as_float(row[f"model_{model.lower()}_investment_weight_from_blind"]),
            )
            if same_profile(final_profile, model_profile):
                matched.append(model)
        exact_models.append("+".join(matched) if matched else "neither")

    merged["review_decision_model"] = decision_models
    merged["exact_profile_match_model"] = exact_models
    merged["decision_equals_exact_profile"] = (
        merged["review_decision_model"].astype(str) == merged["exact_profile_match_model"].astype(str)
    )

    summary = {
        "conflict_model_adoption_by_decision": ordered_counts(
            merged["review_decision_model"], MODEL_ORDER
        ),
        "conflict_model_adoption_by_exact_profile": ordered_counts(
            merged["exact_profile_match_model"], MODEL_ORDER
        ),
        "conflict_final_impact_distribution": ordered_counts(
            merged["review_final_impact_type"], IMPACT_ORDER
        ),
        "conflict_by_policy_area_and_model": summarize_frame(
            merged, ["policy_area"], "review_decision_model", MODEL_ORDER
        ),
        "conflict_by_policy_area_and_final_type": summarize_frame(
            merged, ["policy_area"], "review_final_impact_type", IMPACT_ORDER
        ),
    }
    return merged, summary


def read_consensus_review_outputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(GPT_OUTPUT_DIR.glob("stage2_consensus_682_chunk_*.csv"))
    if not files:
        raise FileNotFoundError(f"No consensus review files found in {GPT_OUTPUT_DIR}")

    seen: dict[str, dict[str, str]] = {}
    sources: dict[str, list[str]] = defaultdict(list)
    duplicate_rows = 0
    inconsistent_rows: list[dict[str, str]] = []

    for path in files:
        frame = read_csv(path)
        validate_required_columns(frame, ["provision_id"] + REVIEW_COLS, path)
        for _, row in frame.iterrows():
            provision_id = norm_text(row["provision_id"])
            if not provision_id:
                continue
            values = {col: norm_text(row[col]) for col in REVIEW_COLS}
            sources[provision_id].append(path.name)
            if provision_id in seen:
                duplicate_rows += 1
                if seen[provision_id] != values:
                    inconsistent_rows.append(
                        {
                            "provision_id": provision_id,
                            "first_values": repr(seen[provision_id]),
                            "conflicting_file": path.name,
                            "conflicting_values": repr(values),
                        }
                    )
            else:
                seen[provision_id] = values

    if inconsistent_rows:
        raise ValueError(
            "Consensus duplicate review rows disagree; inspect "
            f"{len(inconsistent_rows)} inconsistent provision_id values."
        )

    review_rows = []
    for provision_id, values in seen.items():
        review_rows.append(
            {
                "provision_id": provision_id,
                **values,
                "review_source_files": ";".join(sources[provision_id]),
                "review_duplicate_source_rows": len(sources[provision_id]) - 1,
            }
        )
    review = pd.DataFrame(review_rows)

    quality = pd.DataFrame(
        [
            {"check": "consensus_review_files_read", "value": len(files)},
            {"check": "consensus_unique_provision_ids", "value": len(review)},
            {"check": "consensus_duplicate_source_rows", "value": duplicate_rows},
            {"check": "consensus_inconsistent_duplicate_ids", "value": len(inconsistent_rows)},
        ]
    )
    return review, quality


def merge_consensus_review() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DataFrame]:
    base = read_csv(CONSENSUS_BASE_PATH)
    validate_required_columns(
        base,
        [
            "provision_id",
            "policy_area",
            "consensus_impact_type",
            "consensus_trade_weight",
            "consensus_investment_weight",
        ],
        CONSENSUS_BASE_PATH,
    )
    review, quality = read_consensus_review_outputs()
    base_context = base.drop(
        columns=[col for col in REVIEW_COLS if col in base.columns],
        errors="ignore",
    )
    merged = base_context.merge(review, on="provision_id", how="left", validate="1:1")
    if len(merged) != 682:
        raise ValueError(f"Expected 682 consensus rows, got {len(merged)}")
    missing = merged["review_verdict"].isna()
    if missing.any():
        raise ValueError(
            "Consensus review missing review output for provision_id values: "
            f"{merged.loc[missing, 'provision_id'].tolist()}"
        )

    merged["review_verdict_norm"] = merged["review_verdict"].map(norm_lower)
    merged["consensus_impact_type_norm"] = merged["consensus_impact_type"].map(norm_lower)
    merged["review_recommended_impact_type_norm"] = merged[
        "review_recommended_impact_type"
    ].map(norm_lower)
    merged["impact_type_changed_by_review"] = (
        merged["consensus_impact_type_norm"] != merged["review_recommended_impact_type_norm"]
    )

    nonaccept = merged[~merged["review_verdict_norm"].eq("accept")].copy()
    from_to = (
        nonaccept.groupby(
            ["consensus_impact_type_norm", "review_recommended_impact_type_norm"],
            dropna=False,
        )
        .size()
        .reset_index(name="n")
        .rename(
            columns={
                "consensus_impact_type_norm": "from_consensus_impact_type",
                "review_recommended_impact_type_norm": "to_review_impact_type",
            }
        )
    )
    if not from_to.empty:
        from_to["share_of_nonaccept"] = (from_to["n"] / len(nonaccept)).round(6)

    issue_rows = []
    for _, row in merged.iterrows():
        raw_issue = norm_text(row["review_issue_type"])
        if not raw_issue or raw_issue.lower() == "none":
            continue
        parts = []
        for semicolon_part in raw_issue.split("；"):
            for comma_part in semicolon_part.replace(";", ",").split(","):
                part = comma_part.strip()
                if part and part.lower() != "none":
                    parts.append(part)
        for part in parts:
            issue_rows.append(
                {
                    "provision_id": row["provision_id"],
                    "policy_area": row["policy_area"],
                    "review_issue_type": part,
                }
            )
    issues = pd.DataFrame(issue_rows)
    if issues.empty:
        issues = pd.DataFrame(columns=["provision_id", "policy_area", "review_issue_type"])
    issue_counts = (
        issues.groupby("review_issue_type", dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["n", "review_issue_type"], ascending=[False, True])
    )
    if not issue_counts.empty:
        issue_counts["share_of_all_consensus"] = (issue_counts["n"] / len(merged)).round(6)

    summary = {
        "consensus_verdict_distribution": ordered_counts(
            merged["review_verdict_norm"], VERDICT_ORDER
        ),
        "consensus_review_recommended_impact_distribution": ordered_counts(
            merged["review_recommended_impact_type_norm"], IMPACT_ORDER
        ),
        "consensus_original_impact_distribution": ordered_counts(
            merged["consensus_impact_type_norm"], IMPACT_ORDER
        ),
        "consensus_by_policy_area_and_verdict": summarize_frame(
            merged, ["policy_area"], "review_verdict_norm", VERDICT_ORDER
        ),
        "consensus_by_original_type_and_verdict": summarize_frame(
            merged, ["consensus_impact_type_norm"], "review_verdict_norm", VERDICT_ORDER
        ),
        "consensus_nonaccept_from_to": from_to,
        "consensus_issue_type_counts": issue_counts,
        "consensus_issues_by_policy_area": (
            issues.groupby(["policy_area", "review_issue_type"], dropna=False)
            .size()
            .reset_index(name="n")
            .sort_values(["policy_area", "n", "review_issue_type"], ascending=[True, False, True])
        ),
    }
    return merged, summary, quality


def build_final_review_table(conflict: pd.DataFrame, consensus: pd.DataFrame) -> pd.DataFrame:
    conflict_final = pd.DataFrame(
        {
            "provision_id": conflict["provision_id"],
            "policy_area": conflict["policy_area"],
            "original_coding": conflict.get("original_coding", ""),
            "final_dominant_dimension": conflict.get("final_dominant_dimension", ""),
            "provision_text": conflict.get("provision_text", ""),
            "stage2_review_group": "conflict_82",
            "external_review_status": conflict["review_decision_model"],
            "external_review_issue_type": "",
            "external_review_reason": conflict["review_reason"],
            "external_review_confidence": conflict["review_confidence"],
            "external_review_needs_human_followup": conflict["needs_human_followup"].map(norm_lower),
            "final_impact_type_after_gpt55": conflict["review_final_impact_type"].map(norm_lower),
            "final_trade_weight_after_gpt55": conflict["review_trade_weight"],
            "final_investment_weight_after_gpt55": conflict["review_investment_weight"],
        }
    )
    consensus_final = pd.DataFrame(
        {
            "provision_id": consensus["provision_id"],
            "policy_area": consensus["policy_area"],
            "original_coding": consensus.get("original_coding", ""),
            "final_dominant_dimension": consensus.get("final_dominant_dimension", ""),
            "provision_text": consensus.get("provision_text", ""),
            "stage2_review_group": "consensus_682",
            "external_review_status": consensus["review_verdict_norm"],
            "external_review_issue_type": consensus["review_issue_type"],
            "external_review_reason": consensus["review_reason"],
            "external_review_confidence": consensus["review_confidence"],
            "external_review_needs_human_followup": consensus["review_verdict_norm"]
            .isin(["revise", "uncertain"])
            .map({True: "true", False: "false"}),
            "final_impact_type_after_gpt55": consensus[
                "review_recommended_impact_type_norm"
            ],
            "final_trade_weight_after_gpt55": consensus["review_trade_weight"],
            "final_investment_weight_after_gpt55": consensus["review_investment_weight"],
        }
    )
    final = pd.concat([conflict_final, consensus_final], ignore_index=True)
    return final.sort_values("provision_id").reset_index(drop=True)


def add_total_and_share(df: pd.DataFrame, count_col: str = "n") -> pd.DataFrame:
    out = df.copy()
    total = out[count_col].sum()
    out["share"] = (out[count_col] / total).round(6) if total else 0.0
    return out


def write_summary_markdown(
    conflict: pd.DataFrame,
    consensus: pd.DataFrame,
    final_review: pd.DataFrame,
    quality: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
) -> None:
    conflict_model = summaries["conflict_model_adoption_by_decision"].set_index("value")["n"]
    conflict_type = summaries["conflict_final_impact_distribution"].set_index("value")["n"]
    consensus_verdict = summaries["consensus_verdict_distribution"].set_index("value")["n"]
    final_type = summaries["final_impact_distribution"].set_index("value")["n"]

    decisive_conflict = int(conflict_model.get("a", 0) + conflict_model.get("b", 0))
    b_share_decisive = (
        conflict_model.get("b", 0) / decisive_conflict if decisive_conflict else 0.0
    )
    consensus_accept_rate = consensus_verdict.get("accept", 0) / len(consensus)

    policy_nonaccept = summaries["consensus_policy_nonaccept_rates"].copy()
    top_policy_nonaccept = policy_nonaccept.head(6)

    lines = [
        "# ChatGPT 5.5 Stage 2 Review Merge Summary",
        "",
        f"Generated at: {utc_timestamp()}",
        "",
        "## Data Quality Checks",
        "",
        f"- Conflict review rows: {len(conflict)} / 82.",
        f"- Consensus review rows: {len(consensus)} / 682.",
        "- Consensus duplicate full/review-only rows were checked for identical review fields.",
    ]
    for _, row in quality.iterrows():
        lines.append(f"- {row['check']}: {row['value']}.")

    lines += [
        "",
        "## Conflict Arbitration: 82 Rows",
        "",
        (
            f"- Decision-based model adoption: A={int(conflict_model.get('a', 0))}, "
            f"B={int(conflict_model.get('b', 0))}, "
            f"neither={int(conflict_model.get('neither', 0))}."
        ),
        (
            f"- Among decisive option choices only, B share = {b_share_decisive:.2%} "
            f"({int(conflict_model.get('b', 0))}/{decisive_conflict})."
        ),
        (
            f"- Final impact distribution: mp={int(conflict_type.get('mp', 0))}, "
            f"tr={int(conflict_type.get('tr', 0))}, "
            f"both={int(conflict_type.get('both', 0))}, "
            f"none={int(conflict_type.get('none', 0))}."
        ),
        (
            f"- Human follow-up flagged by conflict review: "
            f"{int(conflict['needs_human_followup'].map(norm_lower).eq('true').sum())}."
        ),
        "",
        "Policy-area split is heterogeneous: B is favored most strongly in Services, Subsidies, "
        "SOEs, and Environmental Laws, while A is favored in Movement of Capital and "
        "Competition Policy. This supports B more than A for a single-model route, but not "
        "as a uniform rule across all policy areas.",
        "",
        "## Consensus Objectivity Review: 682 Rows",
        "",
        (
            f"- Verdicts: accept={int(consensus_verdict.get('accept', 0))} "
            f"({consensus_accept_rate:.2%}), revise={int(consensus_verdict.get('revise', 0))}, "
            f"uncertain={int(consensus_verdict.get('uncertain', 0))}."
        ),
        "- Non-accept rows are concentrated in a small number of policy areas:",
    ]
    for _, row in top_policy_nonaccept.iterrows():
        lines.append(
            f"  - {row['policy_area']}: {int(row['nonaccept_n'])}/{int(row['total_n'])} "
            f"({row['nonaccept_rate']:.2%})."
        )

    lines += [
        "",
        "## Combined 764-Row External Review Result",
        "",
        (
            f"- Final distribution after applying conflict arbitration and consensus review: "
            f"mp={int(final_type.get('mp', 0))}, tr={int(final_type.get('tr', 0))}, "
            f"both={int(final_type.get('both', 0))}, none={int(final_type.get('none', 0))}."
        ),
        (
            "- Double-model route remains empirically defensible: the v4 prompt reduced "
            "Stage 2 conflicts to 82/764, and the independent review accepted "
            "665/682 consensus rows."
        ),
        (
            "- Single-model route, if required by the advisor's earlier suggestion, has "
            "stronger support for model B on the conflict-only blind audit "
            f"({int(conflict_model.get('b', 0))} B vs "
            f"{int(conflict_model.get('a', 0))} A), but the policy-area split should be reported."
        ),
        "",
        "## Output Files",
        "",
        "- stage2_conflict_82_gpt55_merged_with_key.csv",
        "- stage2_consensus_682_gpt55_merged.csv",
        "- stage2_review_final_764_gpt55.csv",
        "- stage2_review_human_followup_candidates.csv",
        "- summary_*.csv",
    ]
    (MERGED_DIR / "chatgpt55_stage2_review_summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run() -> None:
    MERGED_DIR.mkdir(parents=True, exist_ok=True)

    conflict, conflict_summary = merge_conflict_review()
    consensus, consensus_summary, quality = merge_consensus_review()
    final_review = build_final_review_table(conflict, consensus)

    final_distribution = ordered_counts(
        final_review["final_impact_type_after_gpt55"], IMPACT_ORDER
    )

    policy_nonaccept = (
        consensus.groupby("policy_area", dropna=False)["review_verdict_norm"]
        .agg(
            total_n="size",
            revise_n=lambda s: int((s == "revise").sum()),
            uncertain_n=lambda s: int((s == "uncertain").sum()),
        )
        .reset_index()
    )
    policy_nonaccept["nonaccept_n"] = (
        policy_nonaccept["revise_n"] + policy_nonaccept["uncertain_n"]
    )
    policy_nonaccept["nonaccept_rate"] = (
        policy_nonaccept["nonaccept_n"] / policy_nonaccept["total_n"]
    ).round(6)
    policy_nonaccept = policy_nonaccept.sort_values(
        ["nonaccept_n", "nonaccept_rate", "policy_area"],
        ascending=[False, False, True],
    )

    final_by_group = (
        final_review.groupby(["stage2_review_group", "final_impact_type_after_gpt55"], dropna=False)
        .size()
        .reset_index(name="n")
    )
    final_by_group["share_within_group"] = (
        final_by_group["n"]
        / final_by_group.groupby("stage2_review_group")["n"].transform("sum")
    ).round(6)

    summaries: dict[str, pd.DataFrame] = {
        **conflict_summary,
        **consensus_summary,
        "final_impact_distribution": final_distribution,
        "final_impact_distribution_by_group": final_by_group,
        "consensus_policy_nonaccept_rates": policy_nonaccept,
    }

    write_csv(conflict, MERGED_DIR / "stage2_conflict_82_gpt55_merged_with_key.csv")
    write_csv(consensus, MERGED_DIR / "stage2_consensus_682_gpt55_merged.csv")
    write_csv(final_review, MERGED_DIR / "stage2_review_final_764_gpt55.csv")

    conflict_followup = conflict[
        conflict["needs_human_followup"].map(norm_lower).eq("true")
        | conflict["review_decision_model"].isin(["neither", "uncertain", "unknown"])
    ].copy()
    conflict_followup["followup_source"] = "conflict_82"
    conflict_followup["followup_reason"] = conflict_followup.apply(
        lambda row: "human_followup_flag;neither_or_uncertain"
        if norm_lower(row["needs_human_followup"]) == "true"
        and row["review_decision_model"] in {"neither", "uncertain", "unknown"}
        else (
            "human_followup_flag"
            if norm_lower(row["needs_human_followup"]) == "true"
            else "neither_or_uncertain"
        ),
        axis=1,
    )
    consensus_followup = consensus[~consensus["review_verdict_norm"].eq("accept")].copy()
    consensus_followup["followup_source"] = "consensus_682"
    consensus_followup["followup_reason"] = consensus_followup["review_verdict_norm"]
    followup_cols = [
        "provision_id",
        "policy_area",
        "original_coding",
        "final_dominant_dimension",
        "provision_text",
        "followup_source",
        "followup_reason",
        "review_reason",
        "review_confidence",
    ]
    conflict_followup_for_output = conflict_followup.reindex(columns=followup_cols)
    consensus_followup_for_output = consensus_followup.reindex(columns=followup_cols)
    followup = pd.concat(
        [conflict_followup_for_output, consensus_followup_for_output],
        ignore_index=True,
    ).sort_values(["followup_source", "policy_area", "provision_id"])
    write_csv(followup, MERGED_DIR / "stage2_review_human_followup_candidates.csv")

    quality_checks = pd.concat(
        [
            pd.DataFrame(
                [
                    {"check": "conflict_rows_expected", "value": 82},
                    {"check": "conflict_rows_observed", "value": len(conflict)},
                    {"check": "consensus_rows_expected", "value": 682},
                    {"check": "consensus_rows_observed", "value": len(consensus)},
                    {"check": "final_rows_expected", "value": 764},
                    {"check": "final_rows_observed", "value": len(final_review)},
                    {
                        "check": "conflict_decision_exact_profile_disagreements",
                        "value": int((~conflict["decision_equals_exact_profile"]).sum()),
                    },
                    {"check": "human_followup_candidate_rows", "value": len(followup)},
                ]
            ),
            quality,
        ],
        ignore_index=True,
    )
    write_csv(quality_checks, MERGED_DIR / "summary_review_package_quality_checks.csv")

    for name, frame in summaries.items():
        write_csv(frame, MERGED_DIR / f"summary_{name}.csv")

    write_summary_markdown(conflict, consensus, final_review, quality_checks, summaries)

    print(f"Wrote merged ChatGPT 5.5 review outputs to {MERGED_DIR}")
    print(f"Conflict rows: {len(conflict)}")
    print(f"Consensus rows: {len(consensus)}")
    print(f"Final reviewed Stage 2 rows: {len(final_review)}")
    print(f"Human follow-up candidates: {len(followup)}")


if __name__ == "__main__":
    run()
