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
    raw_mp_weight: Any,
) -> tuple[float, float]:
    impact_type = str(impact_type).strip().lower()
    if impact_type in config.FIXED_TYPE_WEIGHTS:
        return config.FIXED_TYPE_WEIGHTS[impact_type]
    if impact_type != "both":
        raise ValueError(f"Invalid impact_type: {impact_type}")
    trade_weight = _coerce_optional_float(raw_trade_weight, "trade_weight")
    mp_weight = _coerce_optional_float(raw_mp_weight, "mp_weight")
    if trade_weight is None or mp_weight is None:
        raise ValueError("both requires trade_weight and mp_weight")
    if not 0 < trade_weight < 1 or not 0 < mp_weight < 1:
        raise ValueError("both weights must be strictly between 0 and 1")
    if abs(trade_weight + mp_weight - 1.0) > config.WEIGHT_SUM_TOLERANCE:
        raise ValueError("both weights must sum to 1")
    return float(trade_weight), float(mp_weight)


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
        raw_mp = _coerce_optional_float(
            normalized.get("raw_mp_weight", normalized.get("mp_weight")),
            "raw_mp_weight",
        )
        trade_weight, mp_weight = normalize_stage2_weights(
            impact_type,
            raw_trade,
            raw_mp,
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
    normalized["raw_mp_weight"] = raw_mp
    normalized["normalized_trade_weight"] = trade_weight
    normalized["normalized_mp_weight"] = mp_weight
    normalized["confidence"] = confidence
    return normalized, "ok", ""


def validate_stage2_arbitration_output(
    record: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    mapped = {
        "provision_id": record.get("provision_id"),
        "impact_type": record.get("final_impact_type"),
        "raw_trade_weight": record.get("final_trade_weight"),
        "raw_mp_weight": record.get("final_mp_weight"),
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
    out["final_mp_weight"] = normalized["normalized_mp_weight"]
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
    a_mp: Any,
    b_trade: Any,
    b_mp: Any,
) -> tuple[float, float]:
    trade = (float(a_trade) + float(b_trade)) / 2.0
    mp = (float(a_mp) + float(b_mp)) / 2.0
    total = trade + mp
    if abs(total - 1.0) > config.WEIGHT_SUM_TOLERANCE:
        if total <= 0:
            raise ValueError("Cannot normalize non-positive both weight sum")
        trade /= total
        mp /= total
    return trade, mp


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


def assert_impact_label_schema(frame: pd.DataFrame, label: str) -> None:
    column = "impact_label_schema_version"
    if column not in frame.columns:
        raise ValueError(f"{label} missing required column: {column}")
    versions = set(frame[column].dropna().astype(str))
    if versions != {config.IMPACT_LABEL_SCHEMA_VERSION}:
        raise ValueError(
            f"{label} impact label schema mismatch: "
            f"expected {config.IMPACT_LABEL_SCHEMA_VERSION!r}, got {sorted(versions)!r}"
        )


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
    if stage == 2:
        assert_impact_label_schema(df, f"Stage {stage} model {model_role}")
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
        mp_weight = investment_hits / total
        impact_type = "both"
    elif investment_hits:
        impact_type = "mp"
        trade_weight, mp_weight = 0.0, 1.0
    elif trade_hits:
        impact_type = "trade"
        trade_weight, mp_weight = 1.0, 0.0
    else:
        impact_type = "none"
        trade_weight, mp_weight = 0.0, 0.0
    return {
        "provision_id": value_from_row(row, "provision_id"),
        "impact_type": impact_type,
        "raw_trade_weight": trade_weight,
        "raw_mp_weight": mp_weight,
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


def _approved_master_compatibility(current_hash: str) -> bool:
    """Accept only the exact files covered by a recorded, text-equivalent audit."""
    stages = (
        (config.STAGE1A_MANIFEST_PATH, config.STAGE1A_FINAL_CLASSIFICATION_PATH, "stage1a_final_sha256"),
        (config.STAGE1B_MANIFEST_PATH, config.STAGE1B_FINAL_CLASSIFICATION_PATH, "stage1b_final_sha256"),
        (config.STAGE1_MANIFEST_PATH, config.STAGE1_FINAL_CLASSIFICATION_PATH, "stage1_final_sha256"),
    )
    for path in sorted(config.MANIFEST_DIR.glob("measurement_compatibility_*.json")):
        try:
            record = read_json(path)
            if (
                record.get("record_type") != "documentation_only_compatibility_audit"
                or not record.get("authorization")
                or record.get("current_provisions_master_sha256") != current_hash
                or record.get("id_set_matches") is not True
                or record.get("final_provision_weights_sha256")
                != sha256_file(config.FINAL_PROVISION_WEIGHTS_PATH)
            ):
                continue
            comparisons = record.get("text_comparison", {})
            if any(
                comparisons.get(column, {}).get("mismatches_after_crlf_to_lf") != 0
                for column in ("policy_area", "original_coding", "provision_text")
            ):
                continue
            if record.get("provision_count") != len(read_csv(config.PROVISIONS_MASTER_PATH)):
                continue
            preserved = {
                str(item["path"]).replace("\\", "/"): item
                for item in record.get("historical_manifests_preserved", [])
            }
            valid = True
            for manifest_path, final_path, final_key in stages:
                relative = manifest_path.relative_to(config.PROJECT_ROOT).as_posix()
                evidence = preserved.get(relative, {})
                manifest = read_json(manifest_path)
                if (
                    evidence.get("sha256") != sha256_file(manifest_path)
                    or not evidence.get("historical_provisions_master_sha256")
                    or evidence.get("historical_provisions_master_sha256")
                    != manifest.get("provisions_master_sha256")
                    or manifest.get(final_key) != sha256_file(final_path)
                    or record.get("historical_classification_output_hashes_match_current", {}).get(final_key)
                    is not True
                ):
                    valid = False
                    break
            if valid:
                return True
        except (OSError, ValueError, KeyError, TypeError):
            # A missing or malformed audit never grants compatibility.
            continue
    return False


def _check_provisions_manifest(manifest: dict[str, Any], label: str) -> None:
    current_hash = sha256_file(config.PROVISIONS_MASTER_PATH)
    if manifest.get("provisions_master_sha256") == current_hash:
        return
    if _approved_master_compatibility(current_hash):
        return
    raise RuntimeError(
        f"{label} 门控失败：provisions_master_sha256 与当前条款主表不匹配或缺失；"
        "请重新完成分类，或提供精确覆盖当前主表、历史分类清单和权重的兼容审计。"
        "已有兼容记录不能用于放行后来改变的输入或权重。"
    )


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
    _check_provisions_manifest(manifest, "Stage 1A")
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
    _check_provisions_manifest(manifest, "Stage 1B")
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
    _check_provisions_manifest(manifest, "第一阶段")
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


def weight_classification_baseline_record(*, basis: str) -> dict[str, Any]:
    """Freeze a checked legacy binding without changing its embedded old hash."""
    if not basis:
        raise ValueError("A read-only weight baseline requires an audit basis")
    final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH, dtype={"stage1_final_sha256": str})
    _assert_id_set("权重兼容基线", weights, final["provision_id"])
    if not final["provision_id"].is_unique:
        raise RuntimeError("权重兼容基线失败：分类 provision_id 重复。")
    columns = ["final_is_institutional_opening", "final_dominant_dimension"]
    for stage in ("stage1a", "stage1b", "stage1"):
        columns.extend(
            f"{stage}_{suffix}" for suffix in (
                "decision_source", "resolution_method", "final_reason", "was_arbitrated",
                "was_human_reviewed", "unresolved",
            )
        )
    columns.extend(
        ["stage1a_final_sha256", "stage1b_final_sha256", "provision_order", "policy_area", "original_coding", "provision_text"]
    )
    if any(column not in final or column not in weights for column in columns):
        raise RuntimeError("权重兼容基线失败：缺少完整分类比较字段。")
    final = final.assign(provision_id=final["provision_id"].astype(str)).set_index("provision_id")
    weights = weights.assign(provision_id=weights["provision_id"].astype(str)).set_index("provision_id").loc[final.index]
    mismatches = {}
    for column in columns:
        left = final[column].fillna("").astype(str)
        right = weights[column].fillna("").astype(str)
        if column == "provision_text":
            left = left.str.replace("\r\n", "\n", regex=False)
            right = right.str.replace("\r\n", "\n", regex=False)
        mismatches[column] = int(left.ne(right).sum())
    if any(mismatches.values()):
        raise RuntimeError("权重兼容基线失败：权重保留的分类与当前分类存在实质差异。")
    if "stage1_final_sha256" not in weights:
        raise RuntimeError("权重兼容基线失败：缺少嵌入的分类哈希。")
    embedded = sorted(weights["stage1_final_sha256"].fillna("").astype(str).unique().tolist())
    if len(embedded) != 1 or re.fullmatch(r"[0-9a-f]{64}", embedded[0]) is None:
        raise RuntimeError("权重兼容基线失败：嵌入的分类哈希不唯一或无效。")
    return {
        "schema_version": 1,
        "record_type": "frozen_weight_classification_baseline",
        "pipeline_executed": False,
        "recorded_at": utc_timestamp(),
        "basis": basis,
        "provisions_master_sha256": sha256_file(config.PROVISIONS_MASTER_PATH),
        "final_provision_weights_sha256": sha256_file(config.FINAL_PROVISION_WEIGHTS_PATH),
        "embedded_stage1_final_sha256": embedded,
        "classification_files": {
            name: sha256_file(path) for name, path in {
                "stage1a_final": config.STAGE1A_FINAL_CLASSIFICATION_PATH,
                "stage1b_final": config.STAGE1B_FINAL_CLASSIFICATION_PATH,
                "stage1_final": config.STAGE1_FINAL_CLASSIFICATION_PATH,
                "stage1a_manifest": config.STAGE1A_MANIFEST_PATH,
                "stage1b_manifest": config.STAGE1B_MANIFEST_PATH,
                "stage1_manifest": config.STAGE1_MANIFEST_PATH,
            }.items()
        },
        "classification_comparison": {
            "row_count": len(final),
            "id_set_matches": True,
            "crlf_normalized_columns": ["provision_text"],
            "mismatches": mismatches,
        },
    }


def _approved_weight_classification_compatibility() -> bool:
    path = score_provenance_path(config.FINAL_PROVISION_WEIGHTS_PATH)
    if not path.exists():
        return False
    try:
        record = read_json(path)
        expected = weight_classification_baseline_record(basis=record.get("basis", ""))
        return all(record.get(key) == value for key, value in expected.items() if key != "recorded_at")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return False


def check_final_weights_provenance() -> None:
    """Reject weights made for a different classification before calculating X."""
    check_stage1_gate()
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH, dtype={"stage1_final_sha256": str})
    final = read_csv(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    _assert_id_set("最终权重", weights, final["provision_id"])
    final_hash = sha256_file(config.STAGE1_FINAL_CLASSIFICATION_PATH)
    if "stage1_final_sha256" not in weights or not weights["stage1_final_sha256"].eq(final_hash).all():
        if not _approved_weight_classification_compatibility():
            raise RuntimeError(
                "最终权重门控失败：stage1_final_sha256 缺失或不对应当前分类；"
                "请先重新完成赋权，或提供精确绑定现有权重与分类逐列核验的只读兼容基线。"
            )
    if "final_unresolved" not in weights or as_bool_series(weights["final_unresolved"]).any():
        raise RuntimeError("最终权重门控失败：缺少 final_unresolved 或仍有未解决条款。")
    expected = final.assign(provision_id=final["provision_id"].astype(str)).set_index("provision_id")
    actual = weights.assign(provision_id=weights["provision_id"].astype(str)).set_index("provision_id").loc[expected.index]
    for column in ("final_is_institutional_opening", "final_dominant_dimension"):
        if column not in actual:
            raise RuntimeError(f"最终权重门控失败：缺少 {column}。")
        if column == "final_is_institutional_opening":
            matches = pd.to_numeric(actual[column], errors="coerce").eq(
                pd.to_numeric(expected[column], errors="coerce")
            )
        else:
            matches = actual[column].astype(str).str.lower().eq(expected[column].astype(str).str.lower())
        if not matches.all():
            raise RuntimeError(f"最终权重门控失败：{column} 与当前分类不一致。")


def agreement_score_inputs() -> dict[str, Path]:
    return {
        "provisions_master": config.PROVISIONS_MASTER_PATH,
        "stage1_final_classification": config.STAGE1_FINAL_CLASSIFICATION_PATH,
        "final_provision_weights": config.FINAL_PROVISION_WEIGHTS_PATH,
        "agreement_matrix": config.AGREEMENT_MATRIX_PATH,
        "agreements_master": config.AGREEMENTS_MASTER_PATH,
    }


def score_provenance_path(output: Path) -> Path:
    return output.with_suffix(".provenance.json")


def score_provenance_record(
    output: Path,
    inputs: dict[str, Path],
    parameters: dict[str, Any],
    *,
    record_type: str = "generated_score_provenance",
) -> dict[str, Any]:
    """Describe generated scores or an explicitly labelled, read-only baseline."""
    if record_type not in {"generated_score_provenance", "frozen_input_baseline"}:
        raise ValueError(f"Unsupported score provenance record type: {record_type}")
    return {
        "schema_version": 1,
        "record_type": record_type,
        "pipeline_executed": record_type == "generated_score_provenance",
        "recorded_at": utc_timestamp(),
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "impact_label_schema_version": config.IMPACT_LABEL_SCHEMA_VERSION,
        "coverage_matrix_schema_version": config.COVERAGE_MATRIX_SCHEMA_VERSION,
        "output_sha256": sha256_file(output),
        "inputs": {name: sha256_file(path) for name, path in inputs.items()},
        "parameters": parameters,
    }


def check_agreement_score_provenance() -> None:
    output = config.AGREEMENT_LEVEL_INDICES_PATH
    path = score_provenance_path(output)
    if not path.exists():
        raise RuntimeError(
            f"协定指标门控失败：缺少输入版本记录 {path.name}；"
            "请先运行协定指标步骤，或为已核验的现有产物建立明确标注的只读基线。"
        )
    record = read_json(path)
    record_type = record.get("record_type")
    if record_type not in {"generated_score_provenance", "frozen_input_baseline"}:
        raise RuntimeError("协定指标门控失败：无法识别输入版本记录类型。")
    if record_type == "frozen_input_baseline" and not record.get("basis"):
        raise RuntimeError("协定指标门控失败：只读基线缺少核验依据。")
    expected = score_provenance_record(
        output,
        agreement_score_inputs(),
        {"output_float_decimals": config.OUTPUT_FLOAT_DECIMALS},
        record_type=record_type,
    )
    for key in (
        "schema_version", "pipeline_executed", "pipeline_schema_version",
        "impact_label_schema_version", "coverage_matrix_schema_version",
        "output_sha256", "inputs", "parameters",
    ):
        if record.get(key) != expected[key]:
            raise RuntimeError(
                f"协定指标门控失败：{key} 与当前文件或配置不一致；请先重新计算协定指标。"
            )


def write_table_manifest() -> None:
    manifest = {
        "generated_at": utc_timestamp(),
        "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
        "impact_label_schema_version": config.IMPACT_LABEL_SCHEMA_VERSION,
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
            "icio_2000_2023_pair_year_dummy": str(
                config.ICIO_2000_2023_DUMMY_PATH
            ),
            "expanded_union_pair_year_dummy": str(
                config.EXPANDED_UNION_PAIR_YEAR_DUMMY_PATH
            ),
            "diagnostics_summary": str(config.DIAGNOSTICS_SUMMARY_PATH),
        },
    }
    write_json(manifest, config.LOG_DIR / "run_metadata.json")
