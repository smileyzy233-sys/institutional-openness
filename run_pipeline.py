from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config  # noqa: E402
from pipeline_safety import output_permission, preflight  # noqa: E402
from utils import check_stage1_gate, check_stage1a_gate, check_stage1b_gate  # noqa: E402


COMMANDS = {
    "measure-x",
    "match-y-x",
    "match-y-x-cons",
    "load",
    "stage1a",
    "stage1a-arbitrate",
    "stage1a-finalize",
    "stage1b",
    "stage1b-arbitrate",
    "stage1b-finalize",
    "stage1",
    "stage1-finalize",
    "stage2",
    "stage2-arbitrate",
    "finalize",
    "finalize-single-stage2",
    "indices",
    "dummy",
    "diagnostics",
    "all",
}

MEASURE_X_SCRIPT_ORDER = [
    "measure_x_01_load_dta.py",
    "measure_x_02_stage1a_code_institutional.py",
    "measure_x_03_stage1a_compare_models.py",
    "measure_x_04_stage1a_arbitrate_conflicts.py",
    "measure_x_05_stage1a_finalize.py",
    "measure_x_06_stage1b_code_dimension.py",
    "measure_x_07_stage1b_compare_models.py",
    "measure_x_08_stage1b_arbitrate_conflicts.py",
    "measure_x_09_stage1b_finalize.py",
    "measure_x_10_stage1_finalize.py",
    "measure_x_11_stage2_code_trade_mp.py",
    "measure_x_12_stage2_compare_models.py",
    "measure_x_13_stage2_arbitrate_conflicts.py",
    "measure_x_14_finalize_provision_weights.py",
    "measure_x_15_compute_agreement_scores.py",
    "measure_x_16_compute_country_pair_year_scores.py",
    "measure_x_17_validate_outputs.py",
]


def load_script(filename: str):
    path = SRC_DIR / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model_settings(args: argparse.Namespace, role: str) -> tuple[str, str, str | None]:
    role = role.upper()
    if role == "A":
        provider = args.llm_provider or args.model_a_provider or config.MODEL_A_PROVIDER
        model = args.model_a or config.MODEL_A_NAME
        base_url = args.model_a_base_url if args.model_a_base_url is not None else config.MODEL_A_BASE_URL
    elif role == "B":
        provider = args.llm_provider or args.model_b_provider or config.MODEL_B_PROVIDER
        model = args.model_b or config.MODEL_B_NAME
        base_url = args.model_b_base_url if args.model_b_base_url is not None else config.MODEL_B_BASE_URL
    else:
        provider = args.llm_provider or args.arbitration_provider or config.ARBITRATION_MODEL_PROVIDER
        model = args.arbitration_model or config.ARBITRATION_MODEL_NAME
        base_url = (
            args.arbitration_base_url
            if args.arbitration_base_url is not None
            else config.ARBITRATION_MODEL_BASE_URL
        )
    if provider == "heuristic":
        if role in {"A", "B"} and ((role == "A" and args.model_a is None) or (role == "B" and args.model_b is None)):
            model = f"heuristic_model_{role.lower()}"
        elif role == "ARBITRATION" and args.arbitration_model is None:
            model = "heuristic_arbitration"
    return provider, model, base_url


def run_stage1a_model(args: argparse.Namespace, role: str) -> None:
    provider, model, base_url = model_settings(args, role)
    load_script("measure_x_02_stage1a_code_institutional.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
        limit=args.limit,
    )


def run_stage1b_model(args: argparse.Namespace, role: str) -> None:
    provider, model, base_url = model_settings(args, role)
    load_script("measure_x_06_stage1b_code_dimension.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
        limit=args.limit,
    )


def run_stage2_model(args: argparse.Namespace, role: str) -> None:
    provider, model, base_url = model_settings(args, role)
    load_script("measure_x_11_stage2_code_trade_mp.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
        limit=args.limit,
    )


def run_stage1a_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("measure_x_04_stage1a_arbitrate_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
    )


def run_stage1b_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("measure_x_08_stage1b_arbitrate_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
    )


def run_stage2_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("measure_x_13_stage2_arbitrate_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume,
        limit=args.limit,
    )


def validate_limit_usage(command: str, args: argparse.Namespace) -> None:
    if args.limit is None:
        return
    allowed = command in {"stage1a", "stage1b"} and args.model_role in {"A", "B"}
    if not allowed:
        raise SystemExit(
            "--limit is only allowed with: "
            "stage1a --model-role A/B or stage1b --model-role A/B"
        )


def command_steps(command: str, args: argparse.Namespace) -> list[tuple[str, dict]]:
    """Describe measurement commands without importing or executing step scripts."""
    role = getattr(args, "model_role", None)
    if command in {"measure-x", "all"}:
        names = list(MEASURE_X_SCRIPT_ORDER)
        if command == "all":
            names.insert(-1, "14_build_trade_agreement_dummy.py")
        # These commands always run both model roles, even if --model-role is set.
        return [(name, {}) for name in names]
    if command == "stage1":
        return [(name, {}) for name in MEASURE_X_SCRIPT_ORDER[1:10]]
    if command in {"stage1a", "stage1b", "stage2"}:
        start = {"stage1a": 1, "stage1b": 5, "stage2": 10}[command]
        names = MEASURE_X_SCRIPT_ORDER[start:start + (1 if role else 2)]
        return [(name, {"model_role": role}) for name in names]
    indexes = {
        "load": 0, "stage1a-arbitrate": 3, "stage1a-finalize": 4,
        "stage1b-arbitrate": 7, "stage1b-finalize": 8,
        "stage1-finalize": 9, "stage2-arbitrate": 12,
        "finalize": 13, "diagnostics": 16,
    }
    if command in indexes:
        return [(MEASURE_X_SCRIPT_ORDER[indexes[command]], {})]
    if command == "indices":
        return [(name, {}) for name in MEASURE_X_SCRIPT_ORDER[14:16]]
    if command == "dummy":
        return [("14_build_trade_agreement_dummy.py", {})]
    if command == "finalize-single-stage2":
        return [("10_finalize_weights_single_stage2_model.py", {"model_role": role or "B"})]
    raise ValueError(f"Unknown measurement command: {command}")


def run_command(command: str, args: argparse.Namespace) -> None:
    validate_limit_usage(command, args)
    if command in {"match-y-x", "match-y-x-cons"}:
        # These entry points already provide read-only preflight and collision checks.
        _execute_command(command, args)
        return
    plan = preflight(command_steps(command, args))
    if args.dry_run:
        print(json.dumps({
            "pipeline": command.replace("-", "_"),
            "dry_run": True,
            "note": "只检查路径与已有输出；没有调用模型、计算或写入文件。",
            **plan,
        }, ensure_ascii=False, indent=2))
        if plan["missing_inputs"]:
            raise FileNotFoundError("缺少输入：" + ", ".join(plan["missing_inputs"]))
        return
    # Check every target before the first stage, so a late collision cannot leave
    # earlier stages partially overwritten. --force does not disable model resume.
    with output_permission(plan["outputs"], force=args.force):
        if plan["missing_inputs"]:
            raise FileNotFoundError("缺少输入：" + ", ".join(plan["missing_inputs"]))
        _execute_command(command, args)


def _execute_command(command: str, args: argparse.Namespace) -> None:
    if command == "measure-x":
        for label, step in measure_x_steps(args):
            print(f"\n=== Running: {label} ===")
            step()
    elif command == "match-y-x":
        load_script("match_y_x_06_validate_export.py").run(
            years=args.years,
            output_root=args.output_root,
            dry_run=args.dry_run,
            force=args.force,
        )
    elif command == "match-y-x-cons":
        if not args.control_spec:
            raise SystemExit("--control-spec is required with match-y-x-cons")
        load_script("match_y_x_cons_07_validate_export.py").run(
            years=args.years,
            control_spec=args.control_spec,
            output_root=args.output_root,
            dry_run=args.dry_run,
            force=args.force,
        )
    elif command == "load":
        load_script("measure_x_01_load_dta.py").run()
    elif command == "stage1a":
        if args.model_role:
            run_stage1a_model(args, args.model_role)
        else:
            run_stage1a_model(args, "A")
            run_stage1a_model(args, "B")
            load_script("measure_x_03_stage1a_compare_models.py").run()
    elif command == "stage1a-arbitrate":
        run_stage1a_arbitration(args)
    elif command == "stage1a-finalize":
        load_script("measure_x_05_stage1a_finalize.py").run(allow_unresolved=False)
        check_stage1a_gate()
    elif command == "stage1b":
        check_stage1a_gate()
        if args.model_role:
            run_stage1b_model(args, args.model_role)
        else:
            run_stage1b_model(args, "A")
            run_stage1b_model(args, "B")
            load_script("measure_x_07_stage1b_compare_models.py").run()
    elif command == "stage1b-arbitrate":
        run_stage1b_arbitration(args)
    elif command == "stage1b-finalize":
        load_script("measure_x_09_stage1b_finalize.py").run(allow_unresolved=False)
        check_stage1b_gate()
    elif command == "stage1-finalize":
        load_script("measure_x_10_stage1_finalize.py").run(allow_unresolved=False)
        check_stage1_gate()
    elif command == "stage1":
        run_stage1_sequence(args)
    elif command == "stage2":
        if args.model_role:
            run_stage2_model(args, args.model_role)
        else:
            run_stage2_model(args, "A")
            run_stage2_model(args, "B")
            load_script("measure_x_12_stage2_compare_models.py").run()
    elif command == "stage2-arbitrate":
        run_stage2_arbitration(args)
    elif command == "finalize":
        load_script("measure_x_14_finalize_provision_weights.py").run(
            allow_unresolved=False
        )
    elif command == "finalize-single-stage2":
        load_script("10_finalize_weights_single_stage2_model.py").run(
            model_role=args.model_role or "B"
        )
    elif command == "indices":
        load_script("measure_x_15_compute_agreement_scores.py").run()
        load_script("measure_x_16_compute_country_pair_year_scores.py").run(
            method=args.multi_agreement_method
        )
    elif command == "dummy":
        load_script("14_build_trade_agreement_dummy.py").run()
    elif command == "diagnostics":
        load_script("measure_x_17_validate_outputs.py").run()
    elif command == "all":
        run_all(args)
    else:
        raise ValueError(f"Unknown command: {command}")


def stage1_steps(args: argparse.Namespace) -> list[tuple[str, Callable[[], None]]]:
    """Return the ordered Stage 1 workflow shared by `stage1` and `all`."""
    return [
        ("Stage 1A model A", lambda: run_stage1a_model(args, "A")),
        ("Stage 1A model B", lambda: run_stage1a_model(args, "B")),
        (
            "Stage 1A compare",
            lambda: load_script("measure_x_03_stage1a_compare_models.py").run(),
        ),
        ("Stage 1A arbitration", lambda: run_stage1a_arbitration(args)),
        (
            "Stage 1A finalize",
            lambda: load_script("measure_x_05_stage1a_finalize.py").run(
                allow_unresolved=False
            ),
        ),
        ("Stage 1A gate", check_stage1a_gate),
        ("Stage 1B model A", lambda: run_stage1b_model(args, "A")),
        ("Stage 1B model B", lambda: run_stage1b_model(args, "B")),
        (
            "Stage 1B compare",
            lambda: load_script("measure_x_07_stage1b_compare_models.py").run(),
        ),
        ("Stage 1B arbitration", lambda: run_stage1b_arbitration(args)),
        (
            "Stage 1B finalize",
            lambda: load_script("measure_x_09_stage1b_finalize.py").run(
                allow_unresolved=False
            ),
        ),
        ("Stage 1B gate", check_stage1b_gate),
        (
            "Stage 1 final merge",
            lambda: load_script("measure_x_10_stage1_finalize.py").run(
                allow_unresolved=False
            ),
        ),
        ("Stage 1 gate", check_stage1_gate),
    ]


def run_stage1_sequence(args: argparse.Namespace) -> None:
    for _, step in stage1_steps(args):
        step()


def measure_x_steps(
    args: argparse.Namespace,
) -> list[tuple[str, Callable[[], None]]]:
    """Return the named measurement scripts in their fixed execution order."""
    return [
        ("measure_x_01_load_dta.py", lambda: load_script("measure_x_01_load_dta.py").run()),
        *[
            (label, fn)
            for label, fn in stage1_steps(args)
        ],
        (
            "measure_x_11_stage2_code_trade_mp.py (model A)",
            lambda: run_stage2_model(args, "A"),
        ),
        (
            "measure_x_11_stage2_code_trade_mp.py (model B)",
            lambda: run_stage2_model(args, "B"),
        ),
        (
            "measure_x_12_stage2_compare_models.py",
            lambda: load_script("measure_x_12_stage2_compare_models.py").run(),
        ),
        (
            "measure_x_13_stage2_arbitrate_conflicts.py",
            lambda: run_stage2_arbitration(args),
        ),
        (
            "measure_x_14_finalize_provision_weights.py",
            lambda: load_script("measure_x_14_finalize_provision_weights.py").run(
                allow_unresolved=False
            ),
        ),
        (
            "measure_x_15_compute_agreement_scores.py",
            lambda: load_script("measure_x_15_compute_agreement_scores.py").run(),
        ),
        (
            "measure_x_16_compute_country_pair_year_scores.py",
            lambda: load_script(
                "measure_x_16_compute_country_pair_year_scores.py"
            ).run(method=args.multi_agreement_method),
        ),
        (
            "measure_x_17_validate_outputs.py",
            lambda: load_script("measure_x_17_validate_outputs.py").run(),
        ),
    ]


def run_all(args: argparse.Namespace) -> None:
    ordered_steps = [
        ("load DTA", lambda: load_script("measure_x_01_load_dta.py").run()),
        *stage1_steps(args),
        ("Stage 2 model A", lambda: run_stage2_model(args, "A")),
        ("Stage 2 model B", lambda: run_stage2_model(args, "B")),
        (
            "Stage 2 compare",
            lambda: load_script("measure_x_12_stage2_compare_models.py").run(),
        ),
        ("Stage 2 arbitration", lambda: run_stage2_arbitration(args)),
        (
            "final weights",
            lambda: load_script("measure_x_14_finalize_provision_weights.py").run(
                allow_unresolved=False
            ),
        ),
        (
            "agreement indices",
            lambda: load_script("measure_x_15_compute_agreement_scores.py").run(),
        ),
        (
            "country-pair indices",
            lambda: load_script(
                "measure_x_16_compute_country_pair_year_scores.py"
            ).run(method=args.multi_agreement_method),
        ),
        ("trade agreement dummy", lambda: load_script("14_build_trade_agreement_dummy.py").run()),
        (
            "diagnostics",
            lambda: load_script("measure_x_17_validate_outputs.py").run(),
        ),
    ]
    for label, fn in ordered_steps:
        print(f"\n=== Running: {label} ===")
        try:
            fn()
        except RuntimeError as exc:
            message = str(exc)
            if "Stage 1A requires" in message or "Stage 1B requires" in message:
                print(message)
                print("\nAfter completing the manual review queue, run:")
                if "Stage 1A requires" in message:
                    print("python run_pipeline.py stage1a-finalize --force")
                else:
                    print("python run_pipeline.py stage1b-finalize --force")
                print("python run_pipeline.py all --resume --force")
                raise
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="DTA institutional opening v3 pipeline.")
    parser.add_argument("command", nargs="?", default=None)
    parser.add_argument(
        "--step",
        default=None,
        help="Backward-compatible alias for the positional command.",
    )
    parser.add_argument("--model-role", choices=["A", "B"], default=None)
    parser.add_argument(
        "--llm-provider",
        default=None,
        choices=[
            "openai",
            "deepseek",
            "openrouter",
            "dashscope",
            "heuristic",
            "local_openai_compatible",
        ],
        help="Override provider for model A, model B, and arbitration.",
    )
    parser.add_argument("--model-a-provider", default=None)
    parser.add_argument("--model-a", default=None)
    parser.add_argument("--model-a-base-url", default=None)
    parser.add_argument("--model-b-provider", default=None)
    parser.add_argument("--model-b", default=None)
    parser.add_argument("--model-b-base-url", default=None)
    parser.add_argument("--arbitration-provider", default=None)
    parser.add_argument("--arbitration-model", default=None)
    parser.add_argument("--arbitration-base-url", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=None,
        help="Configured matching years, for example: --years 2019 2020.",
    )
    parser.add_argument(
        "--control-spec",
        default=None,
        help="Control configuration name for match-y-x-cons.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Optional matching output root; relative paths resolve from the project root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and validate a modular pipeline without writing outputs.",
    )
    parser.add_argument(
        "--multi-agreement-method",
        default=config.MULTI_AGREEMENT_METHOD,
        choices=["union", "max", "mean"],
    )
    args = parser.parse_args()
    command = args.step or args.command or "all"
    if command == "mvp":
        command = "all"
    if command == "stage1-arbitrate":
        command = "stage1a-arbitrate"
    if command not in COMMANDS:
        raise SystemExit(f"Unknown command '{command}'. Expected one of: {sorted(COMMANDS)}")
    run_command(command, args)


if __name__ == "__main__":
    main()
