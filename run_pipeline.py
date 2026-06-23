from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import config  # noqa: E402
from utils import check_stage1_gate, check_stage1a_gate, check_stage1b_gate  # noqa: E402


COMMANDS = {
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
    "indices",
    "dummy",
    "diagnostics",
    "all",
}


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
    load_script("03_stage1a_llm_code_institutional.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
        limit=args.limit,
    )


def run_stage1b_model(args: argparse.Namespace, role: str) -> None:
    provider, model, base_url = model_settings(args, role)
    load_script("03_stage1b_llm_code_dimension.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
        limit=args.limit,
    )


def run_stage2_model(args: argparse.Namespace, role: str) -> None:
    provider, model, base_url = model_settings(args, role)
    load_script("07_stage2_llm_code_trade_investment.py").run(
        model_role=role,
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
        limit=args.limit,
    )


def run_stage1a_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("05_stage1a_llm_review_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
    )


def run_stage1b_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("05_stage1b_llm_review_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
    )


def run_stage2_arbitration(args: argparse.Namespace) -> None:
    provider, model, base_url = model_settings(args, "ARBITRATION")
    load_script("09_stage2_llm_review_conflicts.py").run(
        provider=provider,
        model_name=model,
        base_url=base_url,
        resume=args.resume and not args.force,
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


def run_command(command: str, args: argparse.Namespace) -> None:
    validate_limit_usage(command, args)
    if command == "load":
        load_script("01_load_dta.py").run()
    elif command == "stage1a":
        if args.model_role:
            run_stage1a_model(args, args.model_role)
        else:
            run_stage1a_model(args, "A")
            run_stage1a_model(args, "B")
            load_script("04_stage1a_compare_dual_model_results.py").run()
    elif command == "stage1a-arbitrate":
        run_stage1a_arbitration(args)
    elif command == "stage1a-finalize":
        load_script("06_stage1a_finalize.py").run(allow_unresolved=False)
        check_stage1a_gate()
    elif command == "stage1b":
        check_stage1a_gate()
        if args.model_role:
            run_stage1b_model(args, args.model_role)
        else:
            run_stage1b_model(args, "A")
            run_stage1b_model(args, "B")
            load_script("04_stage1b_compare_dual_model_results.py").run()
    elif command == "stage1b-arbitrate":
        run_stage1b_arbitration(args)
    elif command == "stage1b-finalize":
        load_script("06_stage1b_finalize.py").run(allow_unresolved=False)
        check_stage1b_gate()
    elif command == "stage1-finalize":
        load_script("06_stage1_finalize.py").run(allow_unresolved=False)
        check_stage1_gate()
    elif command == "stage1":
        run_stage1_sequence(args)
    elif command == "stage2":
        if args.model_role:
            run_stage2_model(args, args.model_role)
        else:
            run_stage2_model(args, "A")
            run_stage2_model(args, "B")
            load_script("08_stage2_compare_dual_model_results.py").run()
    elif command == "stage2-arbitrate":
        run_stage2_arbitration(args)
    elif command == "finalize":
        load_script("10_finalize_weights.py").run(allow_unresolved=False)
    elif command == "indices":
        load_script("11_compute_agreement_indices.py").run()
        load_script("12_compute_country_pair_indices.py").run(method=args.multi_agreement_method)
    elif command == "dummy":
        load_script("14_build_trade_agreement_dummy.py").run()
    elif command == "diagnostics":
        load_script("13_diagnostics.py").run()
    elif command == "all":
        run_all(args)
    else:
        raise ValueError(f"Unknown command: {command}")


def stage1_steps(args: argparse.Namespace) -> list[tuple[str, Callable[[], None]]]:
    """Return the ordered Stage 1 workflow shared by `stage1` and `all`."""
    return [
        ("Stage 1A model A", lambda: run_stage1a_model(args, "A")),
        ("Stage 1A model B", lambda: run_stage1a_model(args, "B")),
        ("Stage 1A compare", lambda: load_script("04_stage1a_compare_dual_model_results.py").run()),
        ("Stage 1A arbitration", lambda: run_stage1a_arbitration(args)),
        ("Stage 1A finalize", lambda: load_script("06_stage1a_finalize.py").run(allow_unresolved=False)),
        ("Stage 1A gate", check_stage1a_gate),
        ("Stage 1B model A", lambda: run_stage1b_model(args, "A")),
        ("Stage 1B model B", lambda: run_stage1b_model(args, "B")),
        ("Stage 1B compare", lambda: load_script("04_stage1b_compare_dual_model_results.py").run()),
        ("Stage 1B arbitration", lambda: run_stage1b_arbitration(args)),
        ("Stage 1B finalize", lambda: load_script("06_stage1b_finalize.py").run(allow_unresolved=False)),
        ("Stage 1B gate", check_stage1b_gate),
        ("Stage 1 final merge", lambda: load_script("06_stage1_finalize.py").run(allow_unresolved=False)),
        ("Stage 1 gate", check_stage1_gate),
    ]


def run_stage1_sequence(args: argparse.Namespace) -> None:
    for _, step in stage1_steps(args):
        step()


def run_all(args: argparse.Namespace) -> None:
    ordered_steps = [
        ("load DTA", lambda: load_script("01_load_dta.py").run()),
        *stage1_steps(args),
        ("Stage 2 model A", lambda: run_stage2_model(args, "A")),
        ("Stage 2 model B", lambda: run_stage2_model(args, "B")),
        ("Stage 2 compare", lambda: load_script("08_stage2_compare_dual_model_results.py").run()),
        ("Stage 2 arbitration", lambda: run_stage2_arbitration(args)),
        ("final weights", lambda: load_script("10_finalize_weights.py").run(allow_unresolved=False)),
        ("agreement indices", lambda: load_script("11_compute_agreement_indices.py").run()),
        ("country-pair indices", lambda: load_script("12_compute_country_pair_indices.py").run(method=args.multi_agreement_method)),
        ("trade agreement dummy", lambda: load_script("14_build_trade_agreement_dummy.py").run()),
        ("diagnostics", lambda: load_script("13_diagnostics.py").run()),
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
                    print("python run_pipeline.py stage1a-finalize")
                else:
                    print("python run_pipeline.py stage1b-finalize")
                print("python run_pipeline.py all --resume")
                return
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
