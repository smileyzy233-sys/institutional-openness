from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

import config


def ensure_directories() -> None:
    """Create all directories used by the pipeline."""
    for path in [
        config.INTERIM_DIR,
        config.STAGE1_INTERIM_DIR,
        config.STAGE1A_INTERIM_DIR,
        config.STAGE1B_INTERIM_DIR,
        config.STAGE2_INTERIM_DIR,
        config.PROCESSED_DIR,
        config.NEED_DUMMY_DIR,
        config.PROMPT_DIR,
        config.LOG_DIR,
        config.STAGE1_LOG_DIR,
        config.STAGE1A_LOG_DIR,
        config.STAGE1B_LOG_DIR,
        config.STAGE2_LOG_DIR,
        config.LLM_LOG_DIR,
        config.MANIFEST_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}"


def resolve_project_path(path: Path | str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else config.PROJECT_ROOT / candidate


def clean_colname(col: Any) -> str:
    col = str(col).strip().replace("\n", " ")
    return " ".join(col.split())


def normalized_name(value: Any) -> str:
    text = clean_colname(value).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [clean_colname(col) for col in out.columns]
    return out


def pick_column(
    df: pd.DataFrame,
    candidates: Iterable[str],
    *,
    required: bool = True,
    label: str | None = None,
) -> str | None:
    columns = list(df.columns)
    normalized_to_col = {normalized_name(col): col for col in columns}
    for candidate in candidates:
        match = normalized_to_col.get(normalized_name(candidate))
        if match is not None:
            return match

    candidate_norms = [normalized_name(candidate) for candidate in candidates]
    for col in columns:
        col_norm = normalized_name(col)
        if any(candidate and candidate in col_norm for candidate in candidate_norms):
            return col

    if required:
        pretty = label or ", ".join(candidates)
        raise ValueError(f"Could not find required column for {pretty}. Available: {columns}")
    return None


def load_env_file(path: Path | None = None) -> None:
    if path is not None:
        env_paths = [path]
    else:
        env_paths = []
        for candidate in [Path.cwd() / ".env", config.PROJECT_ROOT / ".env"]:
            if candidate not in env_paths:
                env_paths.append(candidate)

    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_sheet(path: Path, sheet_candidates: Iterable[str], **kwargs: Any) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    normalized_sheets = {normalized_name(sheet): sheet for sheet in workbook.sheet_names}
    for candidate in sheet_candidates:
        match = normalized_sheets.get(normalized_name(candidate))
        if match is not None:
            return clean_columns(pd.read_excel(path, sheet_name=match, **kwargs))
    raise ValueError(
        f"None of sheets {list(sheet_candidates)} found. Available sheets: {workbook.sheet_names}"
    )


def agreement_sort_key(agreement_id: str) -> tuple[int, str]:
    match = re.match(r"^agree_(\d+)$", str(agreement_id))
    if match:
        return int(match.group(1)), ""
    return 10**9, str(agreement_id)


def agreement_id_from_wbid(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower().startswith("agree_"):
        suffix = text.split("_", 1)[1]
        return f"agree_{int(float(suffix))}" if _is_number(suffix) else text.lower()
    if _is_number(text):
        return f"agree_{int(float(text))}"
    match = re.search(r"(\d+)", text)
    if match:
        return f"agree_{int(match.group(1))}"
    return None


def _is_number(value: Any) -> bool:
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def normalize_coverage(value: Any) -> float:
    """Normalize a provision-coverage code while preserving partial coverage."""
    if pd.isna(value):
        return 0.0
    if isinstance(value, bool):
        return float(value)
    try:
        coverage = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Provision coverage must be numeric and within [0, 1]; got {value!r}."
        ) from exc
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"Provision coverage must be within [0, 1]; got {value!r}.")
    return coverage


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding=config.CSV_ENCODING)


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(path, encoding=config.CSV_ENCODING, **kwargs)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a JSON object")
    return parsed


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_prompt_with_sha(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return text, sha256_text(text)


def input_text_hash(row: pd.Series | dict[str, Any], *, extra: str = "") -> str:
    payload = {
        "provision_id": value_from_row(row, "provision_id"),
        "provision_text": value_from_row(row, "provision_text"),
        "chapter_name": value_from_row(row, "chapter_name", ""),
        "section_name": value_from_row(row, "section_name", ""),
        "policy_area": value_from_row(row, "policy_area", ""),
        "original_coding": value_from_row(row, "original_coding", ""),
        "extra": extra,
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def value_from_row(row: pd.Series | dict[str, Any], key: str, default: Any = None) -> Any:
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return value


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def as_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _coerce_int01(value: Any, field: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if pd.isna(value):
        raise ValueError(f"{field} must be 0 or 1")
    text = str(value).strip()
    if text in {"0", "0.0"}:
        return 0
    if text in {"1", "1.0"}:
        return 1
    if isinstance(value, (int, float)) and float(value) in {0.0, 1.0}:
        return int(float(value))
    raise ValueError(f"{field} must be 0 or 1")


def _coerce_optional_float(value: Any, field: str) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _validate_confidence(value: Any) -> float | None:
    confidence = _coerce_optional_float(value, "confidence")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return confidence


def validate_stage1_final_output(record: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        is_inst = _coerce_int01(
            normalized.get("is_institutional_opening"),
            "is_institutional_opening",
        )
        dimension = str(normalized.get("dominant_dimension", "")).strip().lower()
        if dimension not in config.DIMENSION_VALUES:
            raise ValueError(f"dominant_dimension must be one of {sorted(config.DIMENSION_VALUES)}")
        if is_inst == 0 and dimension != "none":
            raise ValueError("is_institutional_opening=0 requires dominant_dimension=none")
        if is_inst == 1 and dimension == "none":
            raise ValueError("is_institutional_opening=1 requires a non-none dimension")
        confidence = _validate_confidence(normalized.get("confidence"))
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001 - status is persisted for audit.
        return normalized, "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["is_institutional_opening"] = is_inst
    normalized["dominant_dimension"] = dimension
    normalized["confidence"] = confidence
    return normalized, "ok", ""


validate_stage1_output = validate_stage1_final_output


def validate_stage1a_output(record: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        is_inst = _coerce_int01(
            normalized.get("is_institutional_opening"),
            "is_institutional_opening",
        )
        reason = str(normalized.get("institutional_reason", "")).strip()
        if not reason:
            raise ValueError("institutional_reason is required")
        confidence = _validate_confidence(normalized.get("confidence"))
        if confidence is None:
            raise ValueError("confidence is required")
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001
        return normalized, "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["is_institutional_opening"] = is_inst
    normalized["institutional_reason"] = reason
    normalized["confidence"] = confidence
    return normalized, "ok", ""


def validate_stage1a_arbitration_output(
    record: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        final_value = _coerce_int01(
            normalized.get("final_is_institutional_opening"),
            "final_is_institutional_opening",
        )
        reason = str(normalized.get("arbitration_reason", "")).strip()
        if not reason:
            raise ValueError("arbitration_reason is required")
        confidence = _validate_confidence(normalized.get("confidence"))
        if confidence is None:
            raise ValueError("confidence is required")
        need_human_review = as_bool(normalized.get("need_human_review"))
        if confidence < config.STAGE1_ARBITRATION_HUMAN_REVIEW_THRESHOLD:
            need_human_review = True
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001
        return dict(record), "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["final_is_institutional_opening"] = final_value
    normalized["arbitration_reason"] = reason
    normalized["confidence"] = confidence
    normalized["need_human_review"] = need_human_review
    return normalized, "ok", ""


def validate_stage1b_output(record: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        dimension = str(normalized.get("dominant_dimension", "")).strip().lower()
        if dimension not in config.INSTITUTIONAL_DIMENSION_VALUES:
            raise ValueError(
                "dominant_dimension must be one of "
                f"{sorted(config.INSTITUTIONAL_DIMENSION_VALUES)}"
            )
        reason = str(normalized.get("dimension_reason", "")).strip()
        if not reason:
            raise ValueError("dimension_reason is required")
        confidence = _validate_confidence(normalized.get("confidence"))
        if confidence is None:
            raise ValueError("confidence is required")
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001
        return normalized, "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["dominant_dimension"] = dimension
    normalized["dimension_reason"] = reason
    normalized["confidence"] = confidence
    return normalized, "ok", ""


def validate_stage1b_arbitration_output(
    record: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        dimension = str(normalized.get("final_dominant_dimension", "")).strip().lower()
        if dimension not in config.INSTITUTIONAL_DIMENSION_VALUES:
            raise ValueError(
                "final_dominant_dimension must be one of "
                f"{sorted(config.INSTITUTIONAL_DIMENSION_VALUES)}"
            )
        reason = str(normalized.get("arbitration_reason", "")).strip()
        if not reason:
            raise ValueError("arbitration_reason is required")
        confidence = _validate_confidence(normalized.get("confidence"))
        if confidence is None:
            raise ValueError("confidence is required")
        need_human_review = as_bool(normalized.get("need_human_review"))
        if confidence < config.STAGE1_ARBITRATION_HUMAN_REVIEW_THRESHOLD:
            need_human_review = True
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001
        return dict(record), "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["final_dominant_dimension"] = dimension
    normalized["arbitration_reason"] = reason
    normalized["confidence"] = confidence
    normalized["need_human_review"] = need_human_review
    return normalized, "ok", ""


def normalize_stage2_weights(
    impact_type: str,
    raw_trade_weight: Any,
    raw_investment_weight: Any,
) -> tuple[float, float]:
    impact_type = str(impact_type).strip().lower()
    if impact_type in config.FIXED_TYPE_WEIGHTS:
        return config.FIXED_TYPE_WEIGHTS[impact_type]
    if impact_type != "both":
        raise ValueError(f"Invalid impact_type: {impact_type}")
    trade_weight = _coerce_optional_float(raw_trade_weight, "trade_weight")
    investment_weight = _coerce_optional_float(raw_investment_weight, "investment_weight")
    if trade_weight is None or investment_weight is None:
        raise ValueError("both requires trade_weight and investment_weight")
    if not 0 < trade_weight < 1 or not 0 < investment_weight < 1:
        raise ValueError("both weights must be strictly between 0 and 1")
    if abs(trade_weight + investment_weight - 1.0) > config.WEIGHT_SUM_TOLERANCE:
        raise ValueError("both weights must sum to 1")
    return float(trade_weight), float(investment_weight)


def validate_stage2_output(record: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    normalized = dict(record)
    try:
        provision_id = str(normalized.get("provision_id", "")).strip()
        if not provision_id:
            raise ValueError("provision_id is required")
        impact_type = str(normalized.get("impact_type", "")).strip().lower()
        if impact_type not in config.IMPACT_TYPE_VALUES:
            raise ValueError(f"impact_type must be one of {sorted(config.IMPACT_TYPE_VALUES)}")
        raw_trade = _coerce_optional_float(
            normalized.get("raw_trade_weight", normalized.get("trade_weight")),
            "raw_trade_weight",
        )
        raw_investment = _coerce_optional_float(
            normalized.get("raw_investment_weight", normalized.get("investment_weight")),
            "raw_investment_weight",
        )
        trade_weight, investment_weight = normalize_stage2_weights(
            impact_type,
            raw_trade,
            raw_investment,
        )
        confidence = _validate_confidence(normalized.get("confidence"))
        raw_response = normalized.get("raw_response")
        if raw_response is not None and str(raw_response).strip():
            parse_json_object(str(raw_response))
    except Exception as exc:  # noqa: BLE001
        return normalized, "invalid", str(exc)

    normalized["provision_id"] = provision_id
    normalized["impact_type"] = impact_type
    normalized["raw_trade_weight"] = raw_trade
    normalized["raw_investment_weight"] = raw_investment
    normalized["normalized_trade_weight"] = trade_weight
    normalized["normalized_investment_weight"] = investment_weight
    normalized["confidence"] = confidence
    return normalized, "ok", ""


def validate_stage2_arbitration_output(
    record: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    mapped = {
        "provision_id": record.get("provision_id"),
        "impact_type": record.get("final_impact_type"),
        "raw_trade_weight": record.get("final_trade_weight"),
        "raw_investment_weight": record.get("final_investment_weight"),
        "confidence": record.get("confidence"),
        "raw_response": record.get("raw_response"),
    }
    normalized, status, message = validate_stage2_output(mapped)
    if status != "ok":
        return dict(record), status, message
    out = dict(record)
    out["provision_id"] = normalized["provision_id"]
    out["final_impact_type"] = normalized["impact_type"]
    out["final_trade_weight"] = normalized["normalized_trade_weight"]
    out["final_investment_weight"] = normalized["normalized_investment_weight"]
    out["confidence"] = normalized["confidence"]
    out["need_human_review"] = as_bool(out.get("need_human_review"))
    return out, "ok", ""


def stage1a_conflict_reason(a_value: Any, b_value: Any) -> tuple[bool, bool, str]:
    institutional_match = int(a_value) == int(b_value)
    needs_arbitration = not institutional_match
    reason = "" if institutional_match else "institutional_mismatch"
    return institutional_match, needs_arbitration, reason


def stage1b_conflict_reason(a_dimension: Any, b_dimension: Any) -> tuple[bool, bool, str]:
    dimension_match = str(a_dimension).strip().lower() == str(b_dimension).strip().lower()
    needs_arbitration = not dimension_match
    reason = "" if dimension_match else "dimension_mismatch"
    return dimension_match, needs_arbitration, reason


def stage2_needs_arbitration(model_a_impact_type: Any, model_b_impact_type: Any) -> bool:
    return str(model_a_impact_type).strip().lower() != str(model_b_impact_type).strip().lower()


def average_both_weights(
    a_trade: Any,
    a_investment: Any,
    b_trade: Any,
    b_investment: Any,
) -> tuple[float, float]:
    trade = (float(a_trade) + float(b_trade)) / 2.0
    investment = (float(a_investment) + float(b_investment)) / 2.0
    total = trade + investment
    if abs(total - 1.0) > config.WEIGHT_SUM_TOLERANCE:
        if total <= 0:
            raise ValueError("Cannot normalize non-positive both weight sum")
        trade /= total
        investment /= total
    return trade, investment


def detect_old_six_classification_values(df: pd.DataFrame) -> None:
    candidate_columns = [
        column
        for column in [
            "weight_type",
            "final_weight_type",
            "impact_type",
            "final_impact_type",
            "model_a_weight_type",
            "model_b_weight_type",
        ]
        if column in df.columns
    ]
    for column in candidate_columns:
        values = df[column].dropna().astype(str).str.strip().str.lower()
        old_values = sorted(set(values) & config.OLD_SIX_CLASSIFICATION_VALUES)
        if old_values:
            raise ValueError(
                "检测到旧流程结果："
                f"{column} contains {old_values}. "
                "这些结果仅保留用于历史审计，不会被新流程复用。"
            )


def check_unique_valid_results(
    df: pd.DataFrame,
    *,
    id_column: str = "provision_id",
    validation_column: str = "validation_status",
) -> None:
    if id_column not in df.columns:
        raise ValueError(f"Missing {id_column}")
    valid = df[df[validation_column].eq("ok")] if validation_column in df.columns else df
    duplicates = valid[id_column][valid[id_column].duplicated()].dropna().astype(str).tolist()
    if duplicates:
        sample = ", ".join(duplicates[:10])
        raise ValueError(f"每个模型每个 provision_id 只能有一条有效结果；重复示例：{sample}")


def load_valid_stage_results(path: Path, *, stage: int, model_role: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing stage {stage} model {model_role} results: {path}")
    df = read_csv(path)
    required = {"provision_id", "validation_status", "parse_status"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {sorted(missing)}")
    failures = df[~(df["validation_status"].eq("ok") & df["parse_status"].eq("ok"))]
    if not failures.empty:
        raise ValueError(
            f"Stage {stage} model {model_role} has {len(failures)} unresolved technical failures."
        )
    check_unique_valid_results(df)
    return df.drop_duplicates("provision_id", keep="last").copy()


def model_settings_for_role(role: str) -> dict[str, Any]:
    normalized = str(role).strip().upper()
    if normalized in {"A", "MODEL_A"}:
        return dict(config.MODEL_A)
    if normalized in {"B", "MODEL_B"}:
        return dict(config.MODEL_B)
    if normalized in {"C", "ARBITRATION", "MODEL_C"}:
        return dict(config.ARBITRATION_MODEL)
    raise ValueError("model role must be A, B, or arbitration")


def thinking_mode_for_role(role: str) -> str:
    thinking_mode = str(model_settings_for_role(role).get("thinking_mode", "")).strip().lower()
    if thinking_mode not in {"enabled", "disabled"}:
        raise ValueError(f"Invalid thinking mode for model role {role}: {thinking_mode!r}")
    return thinking_mode


def stage1a_result_path_for_role(role: str) -> Path:
    return (
        config.STAGE1A_MODEL_A_RESULTS_PATH
        if str(role).strip().upper() == "A"
        else config.STAGE1A_MODEL_B_RESULTS_PATH
    )


def stage1b_result_path_for_role(role: str) -> Path:
    return (
        config.STAGE1B_MODEL_A_RESULTS_PATH
        if str(role).strip().upper() == "A"
        else config.STAGE1B_MODEL_B_RESULTS_PATH
    )


def stage2_result_path_for_role(role: str) -> Path:
    return (
        config.STAGE2_MODEL_A_RESULTS_PATH
        if str(role).strip().upper() == "A"
        else config.STAGE2_MODEL_B_RESULTS_PATH
    )


def validate_provider_setup(provider: str, base_url: str | None) -> None:
    load_env_file()
    if provider == "heuristic":
        return
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in .env or the environment.")
    if provider == "deepseek" and not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise RuntimeError("DEEPSEEK_API_KEY or OPENAI_API_KEY is required for DeepSeek.")
    if provider == "openrouter" and not (
        os.getenv("OPENROUTER_API_KEY") or os.getenv("QWEN_API_KEY")
    ):
        raise RuntimeError("OPENROUTER_API_KEY or QWEN_API_KEY is required for OpenRouter.")
    if provider == "dashscope" and not (
        os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_API_KEY")
    ):
        raise RuntimeError("DASHSCOPE_API_KEY or ALIYUN_API_KEY is required for DashScope.")
    if provider == "local_openai_compatible" and not base_url:
        raise RuntimeError("--base-url is required for local_openai_compatible.")


def call_openai_compatible(
    prompt: str,
    *,
    model_name: str,
    api_key_env_names: list[str],
    base_url: str | None = None,
    allow_placeholder_key: bool = False,
    max_tokens: int | None = None,
    extra_body: dict[str, Any] | None = None,
    request_overrides: dict[str, Any] | None = None,
) -> tuple[str, str]:
    load_env_file()
    api_key = next((os.getenv(name) for name in api_key_env_names if os.getenv(name)), None)
    if not api_key and allow_placeholder_key:
        api_key = "local-openai-compatible"
    if not api_key:
        names = " or ".join(api_key_env_names)
        raise RuntimeError(f"{names} is not set. Add it to .env or the environment.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed. Run: pip install openai") from exc

    client_kwargs: dict[str, str] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    request: dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config.TEMPERATURE,
        "top_p": config.TOP_P,
        "max_tokens": max_tokens or config.MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    if extra_body:
        request["extra_body"] = extra_body
    if request_overrides:
        request.update(request_overrides)
    response = client.chat.completions.create(**request)
    choice = response.choices[0]
    return choice.message.content or "", choice.finish_reason or ""


def call_provider(
    prompt: str,
    *,
    provider: str,
    model_name: str,
    base_url: str | None,
    max_tokens: int | None = None,
    model_role: str | None = None,
) -> tuple[str, str]:
    thinking_mode = thinking_mode_for_role(model_role) if model_role is not None else None
    if provider == "openai":
        return call_openai_compatible(
            prompt,
            model_name=model_name,
            api_key_env_names=["OPENAI_API_KEY"],
            base_url=base_url,
            max_tokens=max_tokens,
        )
    if provider == "deepseek":
        thinking_mode = thinking_mode or str(config.DEEPSEEK_THINKING_MODE).strip().lower()
        if thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("DEEPSEEK_THINKING_MODE must be 'enabled' or 'disabled'.")
        request_overrides = (
            {"reasoning_effort": config.DEEPSEEK_REASONING_EFFORT}
            if thinking_mode == "enabled"
            else None
        )
        return call_openai_compatible(
            prompt,
            model_name=model_name,
            api_key_env_names=["DEEPSEEK_API_KEY", "OPENAI_API_KEY"],
            base_url=base_url or os.getenv("DEEPSEEK_BASE_URL") or config.DEEPSEEK_BASE_URL,
            max_tokens=max_tokens,
            extra_body={"thinking": {"type": thinking_mode}},
            request_overrides=request_overrides,
        )
    if provider == "openrouter":
        return call_openai_compatible(
            prompt,
            model_name=model_name,
            api_key_env_names=["OPENROUTER_API_KEY", "QWEN_API_KEY"],
            base_url=base_url or "https://openrouter.ai/api/v1",
            max_tokens=max_tokens,
        )
    if provider == "dashscope":
        return call_openai_compatible(
            prompt,
            model_name=model_name,
            api_key_env_names=["DASHSCOPE_API_KEY", "ALIYUN_API_KEY"],
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL") or config.DASHSCOPE_BASE_URL,
            max_tokens=max_tokens,
            extra_body=(
                {"enable_thinking": thinking_mode == "enabled"}
                if thinking_mode is not None
                else None
            ),
        )
    if provider == "local_openai_compatible":
        return call_openai_compatible(
            prompt,
            model_name=model_name,
            api_key_env_names=["LOCAL_OPENAI_API_KEY", "OPENAI_API_KEY"],
            base_url=base_url,
            allow_placeholder_key=True,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def render_prompt(template: str, row: pd.Series | dict[str, Any]) -> str:
    values = {
        key: "" if pd.isna(value) else value
        for key, value in (row.items() if isinstance(row, pd.Series) else row.items())
    }
    return template.format(**values)


def _stage1_heuristic_scores(row: pd.Series | dict[str, Any]) -> tuple[int, str]:
    text = " ".join(
        str(value_from_row(row, key, ""))
        for key in ["policy_area", "original_coding", "chapter_name", "section_name", "provision_text"]
    ).lower()
    dimension_terms = {
        "standards": [
            "standard",
            "sps",
            "sanitary",
            "phytosanitary",
            "tbt",
            "technical barrier",
            "conformity assessment",
            "certification",
            "inspection",
        ],
        "management": [
            "customs",
            "single window",
            "paperless",
            "facilitation",
            "procedure",
            "risk management",
            "administration",
            "clearance",
            "committee",
        ],
        "regulation": [
            "regulation",
            "regulatory",
            "law",
            "licensing",
            "approval",
            "competition",
            "subsid",
            "state owned",
            "data flow",
            "privacy",
        ],
        "rules": [
            "national treatment",
            "most-favoured-nation",
            "mfn",
            "market access",
            "rules of origin",
            "procurement",
            "intellectual property",
            "digital trade",
            "labor",
            "labour",
            "environment",
            "negative list",
        ],
    }
    institutional_terms = [
        term
        for terms in dimension_terms.values()
        for term in terms
    ] + [
        "trade",
        "investment",
        "investor",
        "capital",
        "export",
        "import",
        "services",
        "tariff",
    ]
    scores = {
        dimension: sum(1 for term in terms if term in text)
        for dimension, terms in dimension_terms.items()
    }
    best_dimension = max(scores, key=scores.get)
    is_institutional = int(any(term in text for term in institutional_terms))
    if not is_institutional:
        best_dimension = "none"
    elif scores[best_dimension] == 0:
        best_dimension = "rules"
    return is_institutional, best_dimension


def heuristic_stage1a_decision(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    is_institutional, _dimension = _stage1_heuristic_scores(row)
    return {
        "provision_id": value_from_row(row, "provision_id"),
        "is_institutional_opening": is_institutional,
        "institutional_reason": "Development-only deterministic Stage 1A heuristic.",
        "confidence": 0.8,
    }


def heuristic_stage1b_decision(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    is_institutional, dimension = _stage1_heuristic_scores(row)
    if not is_institutional or dimension == "none":
        dimension = "rules"
    return {
        "provision_id": value_from_row(row, "provision_id"),
        "dominant_dimension": dimension,
        "dimension_reason": "Development-only deterministic Stage 1B dimension heuristic.",
        "confidence": 0.8,
    }


def heuristic_stage2_decision(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(value_from_row(row, key, ""))
        for key in ["policy_area", "original_coding", "chapter_name", "section_name", "provision_text"]
    ).lower()
    trade_terms = [
        "trade",
        "export",
        "import",
        "customs",
        "tariff",
        "goods",
        "services",
        "rules of origin",
        "sps",
        "tbt",
        "quota",
        "procurement",
    ]
    investment_terms = [
        "investment",
        "investor",
        "capital",
        "establishment",
        "admission",
        "performance requirement",
        "expropriation",
        "commercial presence",
    ]
    trade_hits = sum(1 for term in trade_terms if term in text)
    investment_hits = sum(1 for term in investment_terms if term in text)
    if trade_hits and investment_hits:
        total = trade_hits + investment_hits
        trade_weight = trade_hits / total
        investment_weight = investment_hits / total
        impact_type = "both"
    elif investment_hits:
        impact_type = "tr"
        trade_weight, investment_weight = 0.0, 1.0
    elif trade_hits:
        impact_type = "mp"
        trade_weight, investment_weight = 1.0, 0.0
    else:
        impact_type = "none"
        trade_weight, investment_weight = 0.0, 0.0
    return {
        "provision_id": value_from_row(row, "provision_id"),
        "impact_type": impact_type,
        "trade_weight": trade_weight,
        "investment_weight": investment_weight,
        "reason": "Development-only deterministic stage 2 heuristic.",
        "confidence": 0.6,
    }


def review_context_hash(payload: dict[str, Any]) -> str:
    normalized = {
        str(key): ("" if pd.isna(value) else value)
        for key, value in payload.items()
    }
    return sha256_text(json.dumps(normalized, ensure_ascii=False, sort_keys=True))


def merge_existing_manual_review(
    new_queue: pd.DataFrame,
    existing_queue: pd.DataFrame,
    human_fields: list[str],
    context_hash_column: str = "review_context_hash",
) -> pd.DataFrame:
    out = new_queue.copy()
    if "provision_id" not in out.columns:
        raise ValueError("manual review queue missing provision_id")
    if context_hash_column not in out.columns:
        raise ValueError(f"manual review queue missing {context_hash_column}")
    if out["provision_id"].duplicated().any():
        duplicates = out.loc[out["provision_id"].duplicated(), "provision_id"].astype(str)
        raise ValueError(f"manual review queue has duplicate provision_id: {duplicates.iloc[0]}")

    for field in human_fields:
        if field not in out.columns:
            out[field] = False if field == "human_review_completed" else ""
    if "stale_human_review" not in out.columns:
        out["stale_human_review"] = False

    if existing_queue.empty or "provision_id" not in existing_queue.columns:
        return out
    existing = existing_queue.drop_duplicates("provision_id", keep="last").set_index("provision_id")
    for index, row in out.iterrows():
        provision_id = row["provision_id"]
        if provision_id not in existing.index:
            continue
        old = existing.loc[provision_id]
        if isinstance(old, pd.DataFrame):
            old = old.iloc[-1]
        same_context = str(old.get(context_hash_column, "")) == str(row.get(context_hash_column, ""))
        if same_context:
            for field in human_fields:
                if field in old.index:
                    out.at[index, field] = old.get(field)
            if "stale_human_review" in old.index:
                out.at[index, "stale_human_review"] = False
        elif as_bool(old.get("human_review_completed")):
            for field in human_fields:
                out.at[index, field] = False if field == "human_review_completed" else ""
            out.at[index, "stale_human_review"] = True
    return out


def _check_hash_in_manifest(path: Path, manifest: dict[str, Any], key: str, label: str) -> str:
    actual = sha256_file(path)
    expected = manifest.get(key)
    if actual != expected:
        raise RuntimeError(f"{label} 门控失败：{path.name} 哈希不匹配")
    return actual


def _assert_id_set(label: str, frame: pd.DataFrame, expected: pd.Series) -> None:
    if "provision_id" not in frame.columns:
        raise RuntimeError(f"{label} 门控失败：缺少 provision_id")
    if not frame["provision_id"].is_unique:
        raise RuntimeError(f"{label} 门控失败：存在重复 provision_id")
    if set(frame["provision_id"].astype(str)) != set(expected.astype(str)):
        raise RuntimeError(f"{label} 门控失败：provision_id 集合不一致")


def check_stage1a_gate() -> dict[str, Any]:
    if not config.STAGE1A_SUCCESS_PATH.exists():
        raise RuntimeError(f"Stage 1A 门控失败：缺少 {config.STAGE1A_SUCCESS_PATH}")
    if not config.STAGE1A_MANIFEST_PATH.exists():
        raise RuntimeError(f"Stage 1A 门控失败：缺少 {config.STAGE1A_MANIFEST_PATH}")
    if not config.STAGE1A_FINAL_CLASSIFICATION_PATH.exists():
        raise RuntimeError(
            f"Stage 1A 门控失败：缺少 {config.STAGE1A_FINAL_CLASSIFICATION_PATH}"
        )
    manifest = read_json(config.STAGE1A_MANIFEST_PATH)
    if manifest.get("pipeline_schema_version") != config.PIPELINE_SCHEMA_VERSION:
        raise RuntimeError("Stage 1A 门控失败：manifest schema version 不匹配")
    _check_hash_in_manifest(
        config.STAGE1A_FINAL_CLASSIFICATION_PATH,
        manifest,
        "stage1a_final_sha256",
        "Stage 1A",
    )
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    final = read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    if len(final) != len(provisions):
        raise RuntimeError("Stage 1A 门控失败：最终行数与条款主表不一致")
    _assert_id_set("Stage 1A", final, provisions["provision_id"])
    values = pd.to_numeric(final["final_is_institutional_opening"], errors="coerce")
    if not values.isin([0, 1]).all():
        raise RuntimeError("Stage 1A 门控失败：final_is_institutional_opening 非 0/1")
    if "stage1a_unresolved" not in final.columns:
        raise RuntimeError("Stage 1A 门控失败：缺少 stage1a_unresolved")
    if as_bool_series(final["stage1a_unresolved"]).any():
        raise RuntimeError("Stage 1A 门控失败：仍存在未解决条款")
    return manifest


def check_stage1b_gate() -> dict[str, Any]:
    stage1a_manifest = check_stage1a_gate()
    stage1a_hash = sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    if not config.STAGE1B_SUCCESS_PATH.exists():
        raise RuntimeError(f"Stage 1B 门控失败：缺少 {config.STAGE1B_SUCCESS_PATH}")
    if not config.STAGE1B_MANIFEST_PATH.exists():
        raise RuntimeError(f"Stage 1B 门控失败：缺少 {config.STAGE1B_MANIFEST_PATH}")
    if not config.STAGE1B_FINAL_CLASSIFICATION_PATH.exists():
        raise RuntimeError(
            f"Stage 1B 门控失败：缺少 {config.STAGE1B_FINAL_CLASSIFICATION_PATH}"
        )
    manifest = read_json(config.STAGE1B_MANIFEST_PATH)
    if manifest.get("pipeline_schema_version") != config.PIPELINE_SCHEMA_VERSION:
        raise RuntimeError("Stage 1B 门控失败：manifest schema version 不匹配")
    if manifest.get("stage1a_final_sha256") != stage1a_hash:
        raise RuntimeError("Stage 1B 门控失败：stage1a_final_sha256 已失效")
    _check_hash_in_manifest(
        config.STAGE1B_FINAL_CLASSIFICATION_PATH,
        manifest,
        "stage1b_final_sha256",
        "Stage 1B",
    )
    stage1a = read_csv(config.STAGE1A_FINAL_CLASSIFICATION_PATH)
    eligible = stage1a.loc[
        pd.to_numeric(stage1a["final_is_institutional_opening"], errors="coerce").eq(1),
        "provision_id",
    ]
    final = read_csv(config.STAGE1B_FINAL_CLASSIFICATION_PATH)
    if len(final) != len(eligible):
        raise RuntimeError("Stage 1B 门控失败：最终行数与 Stage 1A eligible 数量不一致")
    _assert_id_set("Stage 1B", final, eligible)
    if not final["final_dominant_dimension"].astype(str).str.lower().isin(
        config.INSTITUTIONAL_DIMENSION_VALUES
    ).all():
        raise RuntimeError("Stage 1B 门控失败：维度值必须属于四个制度维度")
    if "stage1b_unresolved" not in final.columns:
        raise RuntimeError("Stage 1B 门控失败：缺少 stage1b_unresolved")
    if as_bool_series(final["stage1b_unresolved"]).any():
        raise RuntimeError("Stage 1B 门控失败：仍存在未解决条款")
    manifest.setdefault("stage1a_manifest", stage1a_manifest)
    return manifest


def check_stage1_gate() -> dict[str, Any]:
    stage1a_manifest = check_stage1a_gate()
    stage1b_manifest = check_stage1b_gate()
    if not config.STAGE1_SUCCESS_PATH.exists():
        raise RuntimeError(f"第一阶段门控失败：缺少 {config.STAGE1_SUCCESS_PATH}")
    if not config.STAGE1_MANIFEST_PATH.exists():
        raise RuntimeError(f"第一阶段门控失败：缺少 {config.STAGE1_MANIFEST_PATH}")
    if not config.STAGE1_FINAL_CLASSIFICATION_PATH.exists():
        raise RuntimeError(
            f"第一阶段门控失败：缺少 {config.STAGE1_FINAL_CLASSIFICATION_PATH}"
        )
    manifest = read_json(config.STAGE1_MANIFEST_PATH)
    if manifest.get("pipeline_schema_version") != config.PIPELINE_SCHEMA_VERSION:
        raise RuntimeError("第一阶段门控失败：manifest schema version 不匹配")
    final_hash = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    if final_hash != manifest.get("stage1_final_sha256"):
        raise RuntimeError("第一阶段门控失败：stage1_final_classification.csv 哈希不匹配")
    if manifest.get("stage1a_final_sha256") != sha256_file(config.STAGE1A_FINAL_CLASSIFICATION_PATH):
        raise RuntimeError("第一阶段门控失败：Stage 1A 哈希不匹配")
    if manifest.get("stage1b_final_sha256") != sha256_file(config.STAGE1B_FINAL_CLASSIFICATION_PATH):
        raise RuntimeError("第一阶段门控失败：Stage 1B 哈希不匹配")
    provisions = read_csv(config.PROVISIONS_MASTER_PATH)
    final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    if len(final) != len(provisions):
        raise RuntimeError("第一阶段门控失败：第一阶段最终行数与条款主表不一致")
    if not final["provision_id"].is_unique:
        raise RuntimeError("第一阶段门控失败：stage1_final 存在重复 provision_id")
    if set(final["provision_id"].astype(str)) != set(provisions["provision_id"].astype(str)):
        raise RuntimeError("第一阶段门控失败：stage1_final provision_id 集合不一致")
    if "stage1_unresolved" not in final.columns:
        raise RuntimeError("第一阶段门控失败：缺少 stage1_unresolved 字段")
    if as_bool_series(final["stage1_unresolved"]).any():
        raise RuntimeError("第一阶段门控失败：仍存在未解决条款")
    values = pd.to_numeric(final["final_is_institutional_opening"], errors="coerce")
    if not values.isin([0, 1]).all():
        raise RuntimeError("第一阶段门控失败：final_is_institutional_opening 非 0/1")
    non_inst = values.eq(0)
    if not final.loc[non_inst, "final_dominant_dimension"].astype(str).str.lower().eq("none").all():
        raise RuntimeError("第一阶段门控失败：非制度型开放条款必须对应 none")
    inst = values.eq(1)
    if not final.loc[inst, "final_dominant_dimension"].astype(str).str.lower().isin(
        config.INSTITUTIONAL_DIMENSION_VALUES
    ).all():
        raise RuntimeError("第一阶段门控失败：制度型开放条款必须对应四维度")
    manifest.setdefault("stage1a_manifest", stage1a_manifest)
    manifest.setdefault("stage1b_manifest", stage1b_manifest)
    return manifest


def write_table_manifest() -> None:
    manifest = {
        "generated_at": utc_timestamp(),
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "coverage_matrix_schema_version": config.COVERAGE_MATRIX_SCHEMA_VERSION,
        "raw_data_path": str(config.RAW_DATA_PATH),
        "raw_data_sha256": sha256_file(config.RAW_DATA_PATH),
        "outputs": {
            "provisions_master": str(config.PROVISIONS_MASTER_PATH),
            "agreement_matrix": str(config.AGREEMENT_MATRIX_PATH),
            "agreements_master": str(config.AGREEMENTS_MASTER_PATH),
            "bilateral_panel": str(config.BILATERAL_PANEL_PATH),
            "stage1_final_classification": str(config.STAGE1_FINAL_CLASSIFICATION_PATH),
            "final_provision_weights": str(config.FINAL_PROVISION_WEIGHTS_PATH),
            "agreement_level_indices": str(config.AGREEMENT_LEVEL_INDICES_PATH),
            "country_pair_year_indices": str(config.COUNTRY_PAIR_YEAR_INDICES_PATH),
            "dta_active_agreement_dummy": str(config.DTA_ACTIVE_AGREEMENT_DUMMY_PATH),
            "icio_pair_year_dummy": str(config.ICIO_PAIR_YEAR_DUMMY_PATH),
            "icio_economies_all_years_pair_year_dummy": str(
                config.ICIO_ECONOMIES_ALL_YEARS_DUMMY_PATH
            ),
            "expanded_union_pair_year_dummy": str(
                config.EXPANDED_UNION_PAIR_YEAR_DUMMY_PATH
            ),
            "diagnostics_summary": str(config.DIAGNOSTICS_SUMMARY_PATH),
        },
    }
    write_json(manifest, config.LOG_DIR / "run_metadata.json")
