"""Shared preflight for measurement entry points; never performs research work."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import json
from pathlib import Path

import config


# Config names keep the same registry usable in isolated tests and relocated projects.
OUTPUTS = {
    "measure_x_01_load_dta.py": ("PROVISIONS_MASTER_PATH", "AGREEMENT_MATRIX_PATH", "AGREEMENT_PROVISION_LONG_PATH", "AGREEMENTS_MASTER_PATH", "BILATERAL_PANEL_PATH"),
    "measure_x_02_stage1a_code_institutional.py": ("STAGE1A_TECHNICAL_ERROR_QUEUE_PATH",),
    "measure_x_03_stage1a_compare_models.py": ("STAGE1A_COMPARISON_PATH", "STAGE1A_CONFLICT_QUEUE_PATH"),
    "measure_x_04_stage1a_arbitrate_conflicts.py": ("STAGE1A_ARBITRATION_RESULTS_PATH", "STAGE1A_MANUAL_REVIEW_QUEUE_PATH"),
    "measure_x_05_stage1a_finalize.py": ("STAGE1A_FINAL_CLASSIFICATION_PATH", "STAGE1A_MANIFEST_PATH", "STAGE1A_SUCCESS_PATH"),
    "measure_x_06_stage1b_code_dimension.py": ("STAGE1B_TECHNICAL_ERROR_QUEUE_PATH",),
    "measure_x_07_stage1b_compare_models.py": ("STAGE1B_COMPARISON_PATH", "STAGE1B_CONFLICT_QUEUE_PATH"),
    "measure_x_08_stage1b_arbitrate_conflicts.py": ("STAGE1B_ARBITRATION_RESULTS_PATH", "STAGE1B_MANUAL_REVIEW_QUEUE_PATH"),
    "measure_x_09_stage1b_finalize.py": ("STAGE1B_FINAL_CLASSIFICATION_PATH", "STAGE1B_MANIFEST_PATH", "STAGE1B_SUCCESS_PATH"),
    "measure_x_10_stage1_finalize.py": ("STAGE1_FINAL_CLASSIFICATION_PATH", "STAGE1_MANIFEST_PATH", "STAGE1_SUCCESS_PATH"),
    "measure_x_11_stage2_code_trade_mp.py": ("STAGE2_TECHNICAL_ERROR_QUEUE_PATH",),
    "measure_x_12_stage2_compare_models.py": ("STAGE2_COMPARISON_PATH", "STAGE2_TYPE_CONFLICT_QUEUE_PATH"),
    "measure_x_13_stage2_arbitrate_conflicts.py": ("STAGE2_ARBITRATION_RESULTS_PATH", "STAGE2_MANUAL_REVIEW_QUEUE_PATH"),
    "measure_x_14_finalize_provision_weights.py": ("FINAL_PROVISION_WEIGHTS_PATH",),
    "measure_x_15_compute_agreement_scores.py": ("AGREEMENT_LEVEL_INDICES_PATH",),
    "measure_x_16_compute_country_pair_year_scores.py": ("COUNTRY_PAIR_YEAR_INDICES_PATH",),
    "measure_x_17_validate_outputs.py": ("DIAGNOSTICS_SUMMARY_PATH",),
    "14_build_trade_agreement_dummy.py": ("DTA_ACTIVE_AGREEMENT_DUMMY_PATH", "ICIO_PAIR_YEAR_DUMMY_PATH", "ICIO_ECONOMIES_ALL_YEARS_DUMMY_PATH", "ICIO_2000_2023_DUMMY_PATH", "EXPANDED_UNION_PAIR_YEAR_DUMMY_PATH", "TRADE_AGREEMENT_DUMMY_DIAGNOSTICS_PATH", "TRADE_AGREEMENT_DUMMY_CODE_REPORT_PATH"),
    "10_finalize_weights_single_stage2_model.py": ("FINAL_PROVISION_WEIGHTS_PATH", "STAGE2_COMPARISON_PATH", "STAGE2_TYPE_CONFLICT_QUEUE_PATH", "STAGE2_ARBITRATION_RESULTS_PATH", "STAGE2_MANUAL_REVIEW_QUEUE_PATH"),
}

INPUTS = {
    "measure_x_01_load_dta.py": ("RAW_DATA_PATH",),
    "measure_x_02_stage1a_code_institutional.py": ("PROVISIONS_MASTER_PATH", "STAGE1A_PROMPT_PATH"),
    "measure_x_03_stage1a_compare_models.py": ("PROVISIONS_MASTER_PATH", "STAGE1A_MODEL_A_RESULTS_PATH", "STAGE1A_MODEL_B_RESULTS_PATH"),
    "measure_x_04_stage1a_arbitrate_conflicts.py": ("STAGE1A_CONFLICT_QUEUE_PATH", "STAGE1A_ARBITRATION_PROMPT_PATH"),
    "measure_x_05_stage1a_finalize.py": ("PROVISIONS_MASTER_PATH", "STAGE1A_COMPARISON_PATH"),
    "measure_x_06_stage1b_code_dimension.py": ("PROVISIONS_MASTER_PATH", "STAGE1A_FINAL_CLASSIFICATION_PATH", "STAGE1B_PROMPT_PATH"),
    "measure_x_07_stage1b_compare_models.py": ("STAGE1A_FINAL_CLASSIFICATION_PATH", "STAGE1B_MODEL_A_RESULTS_PATH", "STAGE1B_MODEL_B_RESULTS_PATH"),
    "measure_x_08_stage1b_arbitrate_conflicts.py": ("STAGE1B_CONFLICT_QUEUE_PATH", "STAGE1B_ARBITRATION_PROMPT_PATH"),
    "measure_x_09_stage1b_finalize.py": ("STAGE1A_FINAL_CLASSIFICATION_PATH", "STAGE1B_COMPARISON_PATH"),
    "measure_x_10_stage1_finalize.py": ("PROVISIONS_MASTER_PATH", "STAGE1A_FINAL_CLASSIFICATION_PATH", "STAGE1B_FINAL_CLASSIFICATION_PATH"),
    "measure_x_11_stage2_code_trade_mp.py": ("STAGE1_FINAL_CLASSIFICATION_PATH", "STAGE2_PROMPT_PATH"),
    "measure_x_12_stage2_compare_models.py": ("STAGE1_FINAL_CLASSIFICATION_PATH", "STAGE2_MODEL_A_RESULTS_PATH", "STAGE2_MODEL_B_RESULTS_PATH"),
    "measure_x_13_stage2_arbitrate_conflicts.py": ("STAGE2_TYPE_CONFLICT_QUEUE_PATH", "STAGE2_ARBITRATION_PROMPT_PATH"),
    "measure_x_14_finalize_provision_weights.py": ("STAGE1_FINAL_CLASSIFICATION_PATH", "STAGE2_COMPARISON_PATH"),
    "measure_x_15_compute_agreement_scores.py": ("PROVISIONS_MASTER_PATH", "STAGE1_FINAL_CLASSIFICATION_PATH", "FINAL_PROVISION_WEIGHTS_PATH", "AGREEMENT_MATRIX_PATH", "AGREEMENTS_MASTER_PATH"),
    "measure_x_16_compute_country_pair_year_scores.py": ("FINAL_PROVISION_WEIGHTS_PATH", "AGREEMENT_MATRIX_PATH", "AGREEMENT_LEVEL_INDICES_PATH", "BILATERAL_PANEL_PATH"),
    "measure_x_17_validate_outputs.py": ("PROVISIONS_MASTER_PATH", "FINAL_PROVISION_WEIGHTS_PATH"),
    "14_build_trade_agreement_dummy.py": ("BILATERAL_PANEL_PATH", "COUNTRY_PAIR_YEAR_INDICES_PATH", "ICIO2019_PATH", "IDEALPOINT_ESTIMATES_PATH", "AGREEMENT_SCORES_PATH"),
    "10_finalize_weights_single_stage2_model.py": ("STAGE1_FINAL_CLASSIFICATION_PATH",),
}

MODEL_STAGES = {
    "measure_x_02_stage1a_code_institutional.py": "STAGE1A",
    "measure_x_06_stage1b_code_dimension.py": "STAGE1B",
    "measure_x_11_stage2_code_trade_mp.py": "STAGE2",
}
_approved_outputs: ContextVar[frozenset[Path]] = ContextVar("approved_outputs", default=frozenset())


def _path(value) -> Path:
    value = Path(value)
    return (value if value.is_absolute() else config.PROJECT_ROOT / value).resolve()


def step_paths(filename: str, options: dict | None = None) -> tuple[list[Path], list[Path]]:
    options = options or {}
    inputs = [_path(getattr(config, name)) for name in INPUTS[filename]]
    outputs = [_path(getattr(config, name)) for name in OUTPUTS[filename]]
    if filename in MODEL_STAGES:
        stage = MODEL_STAGES[filename]
        if options.get("output_path") is not None:
            outputs.append(_path(options["output_path"]))
        else:
            roles = [options["model_role"]] if options.get("model_role") else ["A", "B"]
            outputs.extend(_path(getattr(config, f"{stage}_MODEL_{role}_RESULTS_PATH")) for role in roles)
    if filename == "10_finalize_weights_single_stage2_model.py":
        role = options.get("model_role") or "B"
        inputs.append(_path(getattr(config, f"STAGE2_MODEL_{role}_RESULTS_PATH")))
    if filename == "measure_x_01_load_dta.py" and options.get("raw_path") is not None:
        inputs[0] = _path(options["raw_path"])
    if options.get("prompt_path") is not None:
        inputs[-1] = _path(options["prompt_path"])
    if filename in {"measure_x_01_load_dta.py", "14_build_trade_agreement_dummy.py"}:
        outputs.append(_path(config.LOG_DIR / "run_metadata.json"))
    if filename in {"measure_x_15_compute_agreement_scores.py", "measure_x_16_compute_country_pair_year_scores.py"}:
        outputs.append(outputs[0].with_suffix(".provenance.json"))
    return inputs, outputs


def preflight(steps: list[tuple[str, dict]]) -> dict:
    """Inspect paths only, accounting for inputs produced earlier in this command."""
    produced: set[Path] = set()
    plan = []
    missing = []
    for filename, options in steps:
        script = Path(__file__).resolve().parent / filename
        if not script.is_file():
            missing.append(str(script))
        inputs, outputs = step_paths(filename, options)
        missing.extend(str(p) for p in inputs if not p.is_file() and p not in produced)
        plan.append({"script": filename, "inputs": list(map(str, inputs)), "outputs": list(map(str, outputs))})
        produced.update(outputs)
    return {
        "steps": plan,
        "missing_inputs": sorted(set(missing)),
        "existing_outputs": sorted(str(p) for p in produced if p.exists()),
        "outputs": sorted(map(str, produced)),
    }


@contextmanager
def output_permission(paths, *, force: bool = False):
    targets = frozenset(_path(p) for p in paths)
    inherited = _approved_outputs.get()
    collisions = sorted(str(p) for p in targets - inherited if p.exists())
    if collisions and not force:
        raise FileExistsError(
            "已有成果受到保护，未开始执行。若确需覆盖，请显式使用 --force；"
            "--no-resume 本身不授权覆盖。\n" + "\n".join(collisions)
        )
    token = _approved_outputs.set(inherited | targets)
    try:
        yield
    finally:
        _approved_outputs.reset(token)


def protected_step(filename: str):
    """Protect direct Python/CLI calls as well as calls through the root runner."""
    name = Path(filename).name

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def guarded(*args, force=False, dry_run=False, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            inputs, outputs = step_paths(name, bound.arguments)
            if dry_run:
                plan = {"dry_run": True, **preflight([(name, dict(bound.arguments))])}
                print(json.dumps(plan, ensure_ascii=False, indent=2))
                if plan["missing_inputs"]:
                    raise FileNotFoundError("缺少输入：" + ", ".join(plan["missing_inputs"]))
                return plan
            with output_permission(outputs, force=force):
                return function(*args, **kwargs)

        return guarded
    return decorate


def step_cli(function):
    """Small CLI for calculation scripts which previously ignored all CLI flags."""
    parser = argparse.ArgumentParser(description=function.__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parameters = inspect.signature(function).parameters
    if "method" in parameters:
        parser.add_argument("--multi-agreement-method", choices=["union", "max", "mean"], default=parameters["method"].default)
    args = parser.parse_args()
    options = {"method": args.multi_agreement_method} if "method" in parameters else {}
    function(force=args.force, dry_run=args.dry_run, **options)
