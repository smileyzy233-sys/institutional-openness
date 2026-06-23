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
    check_unique_valid_results,
    ensure_directories,
    heuristic_stage2_decision,
    input_text_hash,
    make_run_id,
    model_settings_for_role,
    parse_json_object,
    read_csv,
    render_prompt,
    resolve_project_path,
    sha256_file,
    stage2_result_path_for_role,
    thinking_mode_for_role,
    utc_timestamp,
    validate_provider_setup,
    validate_stage2_output,
    write_csv,
)


def ensure_prompt(prompt_path: Path) -> str:
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def prompt_row(row: pd.Series) -> dict[str, Any]:
    payload = {key: ("" if pd.isna(value) else value) for key, value in row.items()}
    for key in ["chapter_name", "section_name", "policy_area", "original_coding"]:
        payload.setdefault(key, "")
    return payload


def complete_record(
    row: pd.Series,
    parsed: dict[str, Any] | None,
    *,
    raw_response: str,
    parse_status: str,
    validation_status: str,
    error_message: str,
    retry_count: int,
    model_role: str,
    model_provider: str,
    model_name: str,
    run_id: str,
    input_hash: str,
    stage1_final_sha256: str,
) -> dict[str, Any]:
    parsed = parsed or {}
    return {
        "provision_id": row["provision_id"],
        "provision_text": row.get("provision_text", ""),
        "chapter_name": row.get("chapter_name", ""),
        "section_name": row.get("section_name", ""),
        "policy_area": row.get("policy_area", ""),
        "original_coding": row.get("original_coding", ""),
        "final_dominant_dimension": row.get("final_dominant_dimension"),
        "impact_type": parsed.get("impact_type"),
        "raw_trade_weight": parsed.get("raw_trade_weight"),
        "raw_investment_weight": parsed.get("raw_investment_weight"),
        "normalized_trade_weight": parsed.get("normalized_trade_weight"),
        "normalized_investment_weight": parsed.get("normalized_investment_weight"),
        "reason": parsed.get("reason"),
        "confidence": parsed.get("confidence"),
        "parse_status": parse_status,
        "validation_status": validation_status,
        "error_message": error_message,
        "retry_count": retry_count,
        "model_role": model_role,
        "model_provider": model_provider,
        "model_name": model_name,
        "prompt_version": config.STAGE2_PROMPT_VERSION,
        "stage1_final_sha256": stage1_final_sha256,
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": utc_timestamp(),
        "input_hash": input_hash,
        "raw_response": raw_response,
    }


def call_stage2_model(
    prompt: str,
    row: pd.Series,
    *,
    provider: str,
    model_name: str,
    base_url: str | None,
    model_role: str,
) -> tuple[str, str]:
    if provider == "heuristic":
        return json.dumps(heuristic_stage2_decision(row), ensure_ascii=False), "stop"
    return call_provider(
        prompt,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        max_tokens=config.MAX_TOKENS,
        model_role=model_role,
    )


def code_one(
    row: pd.Series,
    *,
    prompt_template: str,
    model_role: str,
    provider: str,
    model_name: str,
    base_url: str | None,
    run_id: str,
    stage1_final_sha256: str,
) -> dict[str, Any]:
    prompt_payload = prompt_row(row)
    base_prompt = render_prompt(prompt_template, prompt_payload)
    input_hash = input_text_hash(
        prompt_payload,
        extra=(
            f"{config.STAGE2_PROMPT_VERSION}:{model_role}:"
            f"{thinking_mode_for_role(model_role)}"
        ),
    )
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
            raw, _finish_reason = call_stage2_model(
                prompt,
                row,
                provider=provider,
                model_name=model_name,
                base_url=base_url,
                model_role=model_role,
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
                parsed = None
            else:
                normalized, status, message = validate_stage2_output(parsed)
                if status == "ok":
                    return complete_record(
                        row,
                        normalized,
                        raw_response=raw,
                        parse_status="ok",
                        validation_status="ok",
                        error_message="",
                        retry_count=attempt - 1,
                        model_role=model_role,
                        model_provider=provider,
                        model_name=model_name,
                        run_id=run_id,
                        input_hash=input_hash,
                        stage1_final_sha256=stage1_final_sha256,
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
        model_role=model_role,
        model_provider=provider,
        model_name=model_name,
        run_id=run_id,
        input_hash=input_hash,
        stage1_final_sha256=stage1_final_sha256,
    )


def existing_ok_ids(
    output_path: Path,
    *,
    model_role: str,
    provider: str,
    model_name: str,
    stage1_final_sha256: str,
    expected_hashes: dict[str, str],
) -> set[str]:
    if not output_path.exists():
        return set()
    existing = read_csv(output_path)
    required = {
        "provision_id",
        "parse_status",
        "validation_status",
        "model_role",
        "model_provider",
        "model_name",
        "prompt_version",
        "pipeline_schema_version",
        "stage1_final_sha256",
        "input_hash",
    }
    if not required.issubset(existing.columns):
        return set()
    mask = (
        existing["parse_status"].eq("ok")
        & existing["validation_status"].eq("ok")
        & existing["model_role"].astype(str).str.upper().eq(model_role)
        & existing["model_provider"].eq(provider)
        & existing["model_name"].eq(model_name)
        & existing["prompt_version"].eq(config.STAGE2_PROMPT_VERSION)
        & existing["pipeline_schema_version"].eq(config.PIPELINE_SCHEMA_VERSION)
        & existing["stage1_final_sha256"].eq(stage1_final_sha256)
        & existing["input_hash"].eq(existing["provision_id"].astype(str).map(expected_hashes))
    )
    return set(existing.loc[mask, "provision_id"].astype(str))


def run(
    *,
    model_role: str = "A",
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    output_path: Path | None = None,
    prompt_path: Path = config.STAGE2_PROMPT_PATH,
    resume: bool = True,
    limit: int | None = None,
) -> None:
    ensure_directories()
    check_stage1_gate()
    stage1_final_sha256 = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    model_role = str(model_role).strip().upper()
    settings = model_settings_for_role(model_role)
    provider = provider or settings["provider"]
    model_name = model_name or settings["name"]
    base_url = base_url if base_url is not None else settings["base_url"]
    output_path = resolve_project_path(output_path or stage2_result_path_for_role(model_role))
    prompt_template = ensure_prompt(resolve_project_path(prompt_path))
    validate_provider_setup(provider, base_url)

    stage1_final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    eligible = stage1_final[
        pd.to_numeric(stage1_final["final_is_institutional_opening"], errors="coerce").eq(1)
    ].copy()
    expected_hashes = {
        str(row["provision_id"]): input_text_hash(
            prompt_row(row),
            extra=(
                f"{config.STAGE2_PROMPT_VERSION}:{model_role}:"
                f"{thinking_mode_for_role(model_role)}"
            ),
        )
        for _, row in eligible.iterrows()
    }

    if not resume and output_path.exists():
        output_path.unlink()
    completed_ids = existing_ok_ids(
        output_path,
        model_role=model_role,
        provider=provider,
        model_name=model_name,
        stage1_final_sha256=stage1_final_sha256,
        expected_hashes=expected_hashes,
    ) if resume else set()
    pending = eligible[~eligible["provision_id"].astype(str).isin(completed_ids)].copy()
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be zero or positive")
        pending = pending.head(limit)

    run_id = make_run_id(f"stage2_model_{model_role.lower()}")
    rows: list[dict[str, Any]] = []
    if resume and output_path.exists():
        existing = read_csv(output_path)
        if "stage1_final_sha256" in existing.columns:
            existing = existing[existing["stage1_final_sha256"].eq(stage1_final_sha256)]
        rows.extend(existing.to_dict("records"))

    print(
        f"Stage 2 model {model_role} eligible provisions: {len(eligible):,}; "
        f"pending={len(pending):,}; provider={provider}; model={model_name}"
    )
    for index, (_, row) in enumerate(pending.iterrows(), start=1):
        result = code_one(
            row,
            prompt_template=prompt_template,
            model_role=model_role,
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            run_id=run_id,
            stage1_final_sha256=stage1_final_sha256,
        )
        rows.append(result)
        if index == 1 or index % 25 == 0 or index == len(pending):
            print(
                f"Stage 2 model {model_role}: {index:,}/{len(pending):,} "
                f"{result['provision_id']} ({result['validation_status']})"
            )

    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=[
            "provision_id",
            "validation_status",
            "parse_status",
            "model_role",
            "model_provider",
            "model_name",
            "prompt_version",
            "stage1_final_sha256",
            "pipeline_schema_version",
        ])
    else:
        result = result.drop_duplicates(
            ["provision_id", "model_role", "model_provider", "model_name", "prompt_version"],
            keep="last",
        )
        check_unique_valid_results(result)
    write_csv(result, output_path)

    failures = result[
        ~(result["parse_status"].eq("ok") & result["validation_status"].eq("ok"))
    ].copy()
    if failures.empty and config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH.exists():
        existing = read_csv(config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
        existing = existing[existing["model_role"].astype(str).str.upper().ne(model_role)]
        write_csv(existing, config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
    elif not failures.empty:
        existing = (
            read_csv(config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH)
            if config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH.exists()
            else pd.DataFrame()
        )
        if not existing.empty and "model_role" in existing.columns:
            existing = existing[existing["model_role"].astype(str).str.upper().ne(model_role)]
        write_csv(
            pd.concat([existing, failures], ignore_index=True),
            config.STAGE2_TECHNICAL_ERROR_QUEUE_PATH,
        )
    print(f"Wrote Stage 2 model {model_role} results to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2 trade-investment coding.")
    parser.add_argument("--model-role", choices=["A", "B"], default="A")
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
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--prompt-path", type=Path, default=config.STAGE2_PROMPT_PATH)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run(
        model_role=args.model_role,
        provider=args.provider,
        model_name=args.model,
        base_url=args.base_url,
        output_path=args.output,
        prompt_path=args.prompt_path,
        resume=args.resume and not args.force,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
