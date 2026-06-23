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
    check_unique_valid_results,
    ensure_directories,
    heuristic_stage1a_decision,
    input_text_hash,
    load_env_file,
    make_run_id,
    model_settings_for_role,
    parse_json_object,
    read_csv,
    read_prompt_with_sha,
    render_prompt,
    resolve_project_path,
    stage1a_result_path_for_role,
    thinking_mode_for_role,
    utc_timestamp,
    validate_provider_setup,
    validate_stage1a_output,
    write_csv,
)


METADATA_DEFAULTS = {
    "chapter_name": "",
    "section_name": "",
    "policy_area": "",
    "original_coding": "",
}


def provision_prompt_row(row: pd.Series) -> dict[str, Any]:
    payload = {key: ("" if pd.isna(value) else value) for key, value in row.items()}
    for key, default in METADATA_DEFAULTS.items():
        payload.setdefault(key, default)
    return payload


def complete_record(
    provision: pd.Series,
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
    prompt_sha256: str,
) -> dict[str, Any]:
    parsed = parsed or {}
    row = provision_prompt_row(provision)
    return {
        "provision_id": row.get("provision_id"),
        "provision_text": row.get("provision_text"),
        "chapter_name": row.get("chapter_name", ""),
        "section_name": row.get("section_name", ""),
        "policy_area": row.get("policy_area", ""),
        "original_coding": row.get("original_coding", ""),
        "is_institutional_opening": parsed.get("is_institutional_opening"),
        "institutional_reason": parsed.get("institutional_reason"),
        "confidence": parsed.get("confidence"),
        "parse_status": parse_status,
        "validation_status": validation_status,
        "error_message": error_message,
        "retry_count": retry_count,
        "model_role": model_role,
        "model_provider": model_provider,
        "model_name": model_name,
        "prompt_version": config.STAGE1A_PROMPT_VERSION,
        "prompt_sha256": prompt_sha256,
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": utc_timestamp(),
        "input_hash": input_hash,
        "raw_response": raw_response,
    }


def call_stage1a_model(
    prompt: str,
    provision: pd.Series,
    *,
    provider: str,
    model_name: str,
    base_url: str | None,
    model_role: str,
) -> tuple[str, str]:
    if provider == "heuristic":
        return json.dumps(heuristic_stage1a_decision(provision), ensure_ascii=False), "stop"
    return call_provider(
        prompt,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        max_tokens=config.MAX_TOKENS,
        model_role=model_role,
    )


def code_one_provision(
    provision: pd.Series,
    *,
    prompt_template: str,
    prompt_sha256: str,
    model_role: str,
    provider: str,
    model_name: str,
    base_url: str | None,
    run_id: str,
) -> dict[str, Any]:
    prompt_row = provision_prompt_row(provision)
    base_prompt = render_prompt(prompt_template, prompt_row)
    input_hash = input_text_hash(
        prompt_row,
        extra=(
            f"{config.STAGE1A_PROMPT_VERSION}:{prompt_sha256}:"
            f"{model_role}:{thinking_mode_for_role(model_role)}"
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
            raw, _finish_reason = call_stage1a_model(
                prompt,
                provision,
                provider=provider,
                model_name=model_name,
                base_url=base_url,
                model_role=model_role,
            )
            last_raw = raw
            try:
                parsed = parse_json_object(raw)
                parsed["provision_id"] = prompt_row["provision_id"]
                parsed["raw_response"] = raw
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                last_parse_status = "invalid_json"
                last_validation_status = "invalid"
                last_error = f"{type(exc).__name__}: {exc}"
                parsed = None
            else:
                normalized, status, message = validate_stage1a_output(parsed)
                if status == "ok":
                    return complete_record(
                        provision,
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
                        prompt_sha256=prompt_sha256,
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
        provision,
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
        prompt_sha256=prompt_sha256,
    )


def current_input_hashes(
    provisions: pd.DataFrame,
    prompt_sha256: str,
    model_role: str,
) -> dict[str, str]:
    return {
        str(row["provision_id"]): input_text_hash(
            provision_prompt_row(row),
            extra=(
                f"{config.STAGE1A_PROMPT_VERSION}:{prompt_sha256}:"
                f"{model_role}:{thinking_mode_for_role(model_role)}"
            ),
        )
        for _, row in provisions.iterrows()
    }


def legacy_input_hashes(provisions: pd.DataFrame, prompt_sha256: str) -> dict[str, str]:
    """Return Stage 1A hashes emitted before thinking mode was versioned."""
    return {
        str(row["provision_id"]): input_text_hash(
            provision_prompt_row(row),
            extra=f"{config.STAGE1A_PROMPT_VERSION}:{prompt_sha256}",
        )
        for _, row in provisions.iterrows()
    }


def filter_current_rows(
    existing: pd.DataFrame,
    *,
    model_role: str,
    provider: str,
    model_name: str,
    prompt_sha256: str,
    expected_hashes: dict[str, str],
    legacy_expected_hashes: dict[str, str] | None = None,
) -> pd.DataFrame:
    if existing.empty:
        return existing
    required = {
        "provision_id",
        "parse_status",
        "validation_status",
        "model_role",
        "model_provider",
        "model_name",
        "prompt_version",
        "prompt_sha256",
        "pipeline_schema_version",
        "input_hash",
    }
    if not required.issubset(existing.columns):
        return pd.DataFrame(columns=existing.columns)
    expected = existing["provision_id"].astype(str).map(expected_hashes)
    input_hash_matches = existing["input_hash"].eq(expected)
    if legacy_expected_hashes is not None:
        legacy_expected = existing["provision_id"].astype(str).map(legacy_expected_hashes)
        input_hash_matches |= existing["input_hash"].eq(legacy_expected)
    mask = (
        existing["model_role"].astype(str).str.upper().eq(model_role)
        & existing["model_provider"].eq(provider)
        & existing["model_name"].eq(model_name)
        & existing["prompt_version"].astype(str).eq(config.STAGE1A_PROMPT_VERSION)
        & existing["prompt_sha256"].astype(str).eq(prompt_sha256)
        & existing["pipeline_schema_version"].astype(str).eq(config.PIPELINE_SCHEMA_VERSION)
        & input_hash_matches
    )
    return existing.loc[mask].copy()


def run(
    *,
    model_role: str = "A",
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    output_path: Path | None = None,
    prompt_path: Path = config.STAGE1A_PROMPT_PATH,
    resume: bool = True,
    limit: int | None = None,
) -> None:
    ensure_directories()
    load_env_file()
    model_role = str(model_role).strip().upper()
    settings = model_settings_for_role(model_role)
    provider = provider or settings["provider"]
    model_name = model_name or settings["name"]
    base_url = base_url if base_url is not None else settings["base_url"]
    output_path = resolve_project_path(output_path or stage1a_result_path_for_role(model_role))
    prompt_template, prompt_sha256 = read_prompt_with_sha(resolve_project_path(prompt_path))
    validate_provider_setup(provider, base_url)

    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    expected_hashes = current_input_hashes(provisions, prompt_sha256, model_role)
    legacy_expected_hashes = legacy_input_hashes(provisions, prompt_sha256)
    if not resume and output_path.exists():
        output_path.unlink()
    existing = read_csv(output_path) if resume and output_path.exists() else pd.DataFrame()
    current_existing = filter_current_rows(
        existing,
        model_role=model_role,
        provider=provider,
        model_name=model_name,
        prompt_sha256=prompt_sha256,
        expected_hashes=expected_hashes,
        legacy_expected_hashes=legacy_expected_hashes,
    )
    if current_existing.empty or "provision_id" not in current_existing.columns:
        completed_ids = set()
    else:
        completed_ids = set(
            current_existing.loc[
                current_existing.get("parse_status", pd.Series(dtype=str)).eq("ok")
                & current_existing.get("validation_status", pd.Series(dtype=str)).eq("ok"),
                "provision_id",
            ].astype(str)
        )
    pending = provisions[~provisions["provision_id"].astype(str).isin(completed_ids)].copy()
    if limit is not None:
        if limit < 0:
            raise ValueError("--limit must be zero or positive")
        pending = pending.head(limit)

    run_id = make_run_id(f"stage1a_model_{model_role.lower()}")
    rows: list[dict[str, Any]] = current_existing.to_dict("records") if resume else []
    print(
        f"Stage 1A model {model_role} pending provisions: {len(pending):,}; "
        f"provider={provider}; model={model_name}"
    )
    for index, (_, provision) in enumerate(pending.iterrows(), start=1):
        row = code_one_provision(
            provision,
            prompt_template=prompt_template,
            prompt_sha256=prompt_sha256,
            model_role=model_role,
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            run_id=run_id,
        )
        rows.append(row)
        if index == 1 or index % 25 == 0 or index == len(pending):
            print(
                f"Stage 1A model {model_role}: {index:,}/{len(pending):,} "
                f"{row['provision_id']} ({row['validation_status']})"
            )

    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=["provision_id", "parse_status", "validation_status"])
    else:
        result = result.drop_duplicates(
            [
                "provision_id",
                "model_role",
                "model_provider",
                "model_name",
                "prompt_version",
                "prompt_sha256",
                "input_hash",
            ],
            keep="last",
        )
        check_unique_valid_results(result)
    write_csv(result, output_path)

    failures = result[
        ~(result.get("parse_status", pd.Series(dtype=str)).eq("ok")
          & result.get("validation_status", pd.Series(dtype=str)).eq("ok"))
    ].copy()
    if failures.empty and config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH.exists():
        existing_failures = read_csv(config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH)
        if "model_role" in existing_failures.columns:
            existing_failures = existing_failures[
                existing_failures["model_role"].astype(str).str.upper().ne(model_role)
            ]
        write_csv(existing_failures, config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH)
    elif not failures.empty:
        existing_failures = (
            read_csv(config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH)
            if config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH.exists()
            else pd.DataFrame()
        )
        if not existing_failures.empty and "model_role" in existing_failures.columns:
            existing_failures = existing_failures[
                existing_failures["model_role"].astype(str).str.upper().ne(model_role)
            ]
        write_csv(
            pd.concat([existing_failures, failures], ignore_index=True),
            config.STAGE1A_TECHNICAL_ERROR_QUEUE_PATH,
        )
    print(f"Wrote Stage 1A model {model_role} results to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1A institutional-opening coding.")
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
    parser.add_argument("--prompt-path", type=Path, default=config.STAGE1A_PROMPT_PATH)
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
