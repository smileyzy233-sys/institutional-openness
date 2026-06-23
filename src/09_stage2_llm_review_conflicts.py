from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

import config
from utils import (
    call_provider,
    check_stage1_gate,
    ensure_directories,
    heuristic_stage2_decision,
    make_run_id,
    merge_existing_manual_review,
    model_settings_for_role,
    parse_json_object,
    read_csv,
    render_prompt,
    resolve_project_path,
    review_context_hash,
    utc_timestamp,
    validate_provider_setup,
    validate_stage2_arbitration_output,
    write_csv,
)


ARBITRATION_COLUMNS = [
    "provision_id",
    "final_impact_type",
    "final_trade_weight",
    "final_investment_weight",
    "arbitration_reason",
    "confidence",
    "need_human_review",
    "parse_status",
    "validation_status",
    "error_message",
    "retry_count",
    "model_provider",
    "model_name",
    "prompt_version",
    "pipeline_schema_version",
    "run_id",
    "created_at",
    "stage1_final_sha256",
    "review_context_hash",
    "raw_response",
]

HUMAN_FIELDS = [
    "human_final_impact_type",
    "human_final_trade_weight",
    "human_final_investment_weight",
    "human_review_reason",
    "human_reviewer",
    "human_reviewed_at",
    "human_review_completed",
]


def ensure_prompt(prompt_path: Path) -> str:
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def prompt_row(row: pd.Series) -> dict[str, Any]:
    payload = {key: ("" if pd.isna(value) else value) for key, value in row.items()}
    for key in ["chapter_name", "section_name", "policy_area", "original_coding"]:
        payload.setdefault(key, "")
    return payload


def heuristic_arbitration_response(row: pd.Series) -> str:
    decision = heuristic_stage2_decision(row)
    payload = {
        "final_impact_type": decision["impact_type"],
        "final_trade_weight": decision["trade_weight"],
        "final_investment_weight": decision["investment_weight"],
        "arbitration_reason": "Development-only deterministic stage 2 arbitration heuristic.",
        "confidence": 0.6,
        "need_human_review": False,
    }
    return json.dumps(payload, ensure_ascii=False)


def context_hash_for_row(row: pd.Series) -> str:
    keys = [
        "provision_id",
        "provision_text",
        "model_a_impact_type",
        "model_b_impact_type",
        "model_a_trade_weight",
        "model_a_investment_weight",
        "model_b_trade_weight",
        "model_b_investment_weight",
        "model_a_model_name",
        "model_b_model_name",
        "model_a_prompt_version",
        "model_b_prompt_version",
        "stage1_final_sha256",
    ]
    payload = {key: row.get(key, "") for key in keys}
    payload["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
    return review_context_hash(payload)


def complete_record(
    row: pd.Series,
    parsed: dict[str, Any] | None,
    *,
    raw_response: str,
    parse_status: str,
    validation_status: str,
    error_message: str,
    retry_count: int,
    provider: str,
    model_name: str,
    run_id: str,
) -> dict[str, Any]:
    parsed = parsed or {}
    return {
        "provision_id": row["provision_id"],
        "final_impact_type": parsed.get("final_impact_type"),
        "final_trade_weight": parsed.get("final_trade_weight"),
        "final_investment_weight": parsed.get("final_investment_weight"),
        "arbitration_reason": parsed.get("arbitration_reason"),
        "confidence": parsed.get("confidence"),
        "need_human_review": parsed.get("need_human_review"),
        "parse_status": parse_status,
        "validation_status": validation_status,
        "error_message": error_message,
        "retry_count": retry_count,
        "model_provider": provider,
        "model_name": model_name,
        "prompt_version": config.STAGE2_ARBITRATION_PROMPT_VERSION,
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": utc_timestamp(),
        "stage1_final_sha256": row.get("stage1_final_sha256", ""),
        "review_context_hash": row.get("review_context_hash", ""),
        "raw_response": raw_response,
    }


def review_one(
    row: pd.Series,
    *,
    template: str,
    provider: str,
    model_name: str,
    base_url: str | None,
    run_id: str,
) -> dict[str, Any]:
    base_prompt = render_prompt(template, prompt_row(row))
    last_raw = ""
    last_parse_status = "api_error"
    last_validation_status = "invalid"
    last_error = ""
    for attempt in range(1, config.MAX_LLM_RETRIES + 1):
        prompt = base_prompt
        if last_error:
            prompt += (
                "\n\nThe previous response failed validation: "
                f"{last_error}. Return corrected strict JSON only."
            )
        try:
            if provider == "heuristic":
                raw = heuristic_arbitration_response(row)
            else:
                raw, _finish_reason = call_provider(
                    prompt,
                    provider=provider,
                    model_name=model_name,
                    base_url=base_url,
                    max_tokens=config.ARBITRATION_MAX_TOKENS,
                    model_role="arbitration",
                )
            last_raw = raw
            try:
                parsed = parse_json_object(raw)
                parsed["provision_id"] = row["provision_id"]
                parsed["raw_response"] = raw
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_parse_status = "invalid_json"
                last_validation_status = "invalid"
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                normalized, status, message = validate_stage2_arbitration_output(parsed)
                if status == "ok":
                    return complete_record(
                        row,
                        normalized,
                        raw_response=raw,
                        parse_status="ok",
                        validation_status="ok",
                        error_message="",
                        retry_count=attempt - 1,
                        provider=provider,
                        model_name=model_name,
                        run_id=run_id,
                    )
                last_parse_status = "ok"
                last_validation_status = status
                last_error = message
        except Exception as exc:  # noqa: BLE001
            last_parse_status = "api_error"
            last_validation_status = "invalid"
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < config.MAX_LLM_RETRIES:
            time.sleep(min(2**attempt, 10))
    return complete_record(
        row,
        None,
        raw_response=last_raw,
        parse_status=last_parse_status,
        validation_status=last_validation_status,
        error_message=last_error,
        retry_count=config.MAX_LLM_RETRIES,
        provider=provider,
        model_name=model_name,
        run_id=run_id,
    )


def empty_outputs() -> None:
    write_csv(pd.DataFrame(columns=ARBITRATION_COLUMNS), config.STAGE2_ARBITRATION_RESULTS_PATH)
    write_csv(
        pd.DataFrame(columns=["provision_id", "review_context_hash", *HUMAN_FIELDS]),
        config.STAGE2_MANUAL_REVIEW_QUEUE_PATH,
    )


def run(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    prompt_path: Path = config.STAGE2_ARBITRATION_PROMPT_PATH,
    resume: bool = True,
    limit: int | None = None,
) -> None:
    ensure_directories()
    check_stage1_gate()
    settings = model_settings_for_role("arbitration")
    provider = provider or settings["provider"]
    model_name = model_name or settings["name"]
    base_url = base_url if base_url is not None else settings["base_url"]
    validate_provider_setup(provider, base_url)

    if not config.STAGE2_TYPE_CONFLICT_QUEUE_PATH.exists():
        raise FileNotFoundError(
            f"Stage 2 type conflict queue not found: {config.STAGE2_TYPE_CONFLICT_QUEUE_PATH}"
        )
    queue = read_csv(config.STAGE2_TYPE_CONFLICT_QUEUE_PATH)
    if queue.empty:
        empty_outputs()
        print("Stage 2 type conflict queue is empty; wrote empty arbitration/manual review files.")
        return
    queue = queue.copy()
    queue["review_context_hash"] = queue.apply(context_hash_for_row, axis=1)
    template = ensure_prompt(resolve_project_path(prompt_path))

    if not resume and config.STAGE2_ARBITRATION_RESULTS_PATH.exists():
        config.STAGE2_ARBITRATION_RESULTS_PATH.unlink()
    existing = (
        read_csv(config.STAGE2_ARBITRATION_RESULTS_PATH)
        if resume and config.STAGE2_ARBITRATION_RESULTS_PATH.exists()
        else pd.DataFrame(columns=ARBITRATION_COLUMNS)
    )
    reviewed_ids = set()
    if not existing.empty:
        mask = (
            existing["validation_status"].eq("ok")
            & existing["parse_status"].eq("ok")
            & existing["prompt_version"].eq(config.STAGE2_ARBITRATION_PROMPT_VERSION)
            & existing["pipeline_schema_version"].eq(config.PIPELINE_SCHEMA_VERSION)
            & existing["model_provider"].eq(provider)
            & existing["model_name"].eq(model_name)
        )
        if "review_context_hash" in existing.columns:
            current_context = dict(
                zip(queue["provision_id"].astype(str), queue["review_context_hash"].astype(str))
            )
            mask &= existing["review_context_hash"].eq(
                existing["provision_id"].astype(str).map(current_context)
            )
        existing = existing.loc[mask].copy()
        reviewed_ids = set(existing["provision_id"].astype(str))
    pending = queue[~queue["provision_id"].astype(str).isin(reviewed_ids)].copy()
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be zero or positive")
        pending = pending.head(limit)

    run_id = make_run_id("stage2_arbitration")
    rows = existing.to_dict("records")
    print(f"Stage 2 arbitration pending conflicts: {len(pending):,}")
    for index, (_, row) in enumerate(pending.iterrows(), start=1):
        result = review_one(
            row,
            template=template,
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            run_id=run_id,
        )
        rows.append(result)
        if index == 1 or index % 25 == 0 or index == len(pending):
            print(
                f"Stage 2 arbitration: {index:,}/{len(pending):,} "
                f"{result['provision_id']} ({result['validation_status']})"
            )
    results = pd.DataFrame(rows)
    results = results.drop_duplicates(
        ["provision_id", "model_provider", "model_name", "prompt_version"],
        keep="last",
    )
    write_csv(results[ARBITRATION_COLUMNS], config.STAGE2_ARBITRATION_RESULTS_PATH)

    manual_ids = set(
        results.loc[
            ~(
                results["parse_status"].eq("ok")
                & results["validation_status"].eq("ok")
                & ~results["need_human_review"].map(lambda value: str(value).lower() in {"true", "1", "yes"})
            ),
            "provision_id",
        ].astype(str)
    )
    manual_queue = queue[queue["provision_id"].astype(str).isin(manual_ids)].copy()
    existing_manual = (
        read_csv(config.STAGE2_MANUAL_REVIEW_QUEUE_PATH)
        if config.STAGE2_MANUAL_REVIEW_QUEUE_PATH.exists()
        else pd.DataFrame()
    )
    manual_queue = merge_existing_manual_review(manual_queue, existing_manual, HUMAN_FIELDS)
    write_csv(manual_queue, config.STAGE2_MANUAL_REVIEW_QUEUE_PATH)
    print(f"Wrote Stage 2 arbitration results to {config.STAGE2_ARBITRATION_RESULTS_PATH}")
    print(f"Wrote {len(manual_queue):,} Stage 2 manual review rows to {config.STAGE2_MANUAL_REVIEW_QUEUE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Review Stage 2 type conflicts.")
    parser.add_argument(
        "--provider",
        default=None,
        choices=[
            "openai",
            "deepseek",
            "openrouter",
            "dashscope",
            "heuristic",
            "local_openai_compatible",
        ],
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--prompt-path", type=Path, default=config.STAGE2_ARBITRATION_PROMPT_PATH)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(
        provider=args.provider,
        model_name=args.model,
        base_url=args.base_url,
        prompt_path=args.prompt_path,
        resume=args.resume and not args.force,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
