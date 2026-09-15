from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import pandas as pd

import config
from conftest import load_script
from pipeline_safety import output_permission, protected_step, step_paths


ROOT = Path(__file__).resolve().parents[1]


def runner():
    spec = importlib.util.spec_from_file_location("safety_runner", ROOT / "run_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments(**overrides):
    return SimpleNamespace(**{
        "limit": None, "model_role": None, "dry_run": True, "force": False,
        "resume": True, "years": [2000, 2019], "output_root": None,
        "control_spec": "trade_candidate_pool_v1", **overrides,
    })


@pytest.mark.parametrize("command", sorted(runner().COMMANDS - {"match-y-x", "match-y-x-cons"}))
def test_every_measurement_dry_run_never_loads_step_or_dispatches(command, monkeypatch, capsys):
    module = runner()
    monkeypatch.setattr(module, "load_script", lambda *a: pytest.fail("dry-run loaded a step"))
    monkeypatch.setattr(module, "_execute_command", lambda *a: pytest.fail("dry-run executed"))
    missing = False
    try:
        module.run_command(command, arguments())
    except FileNotFoundError:
        missing = True
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert missing == bool(plan["missing_inputs"])


def test_default_cli_dry_run_is_safe(monkeypatch, capsys):
    module = runner()
    monkeypatch.setattr(module, "_execute_command", lambda *a: pytest.fail("default all executed"))
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--dry-run"])
    missing = False
    try:
        module.main()
    except FileNotFoundError:
        missing = True
    plan = json.loads(capsys.readouterr().out)
    assert plan["pipeline"] == "all"
    assert plan["dry_run"] is True
    assert missing == bool(plan["missing_inputs"])


def test_full_command_checks_late_outputs_before_first_stage(monkeypatch, tmp_path):
    module = runner()
    late = tmp_path / "existing_final.csv"
    late.write_bytes(b"keep existing research")
    monkeypatch.setattr(module, "preflight", lambda steps: {"outputs": [str(late)], "missing_inputs": []})
    monkeypatch.setattr(module, "_execute_command", lambda *a: pytest.fail("partial run started"))
    with pytest.raises(FileExistsError, match="--force"):
        module.run_command("all", arguments(dry_run=False, resume=False))
    assert late.read_bytes() == b"keep existing research"


def test_direct_step_rejects_overwrite_before_work(monkeypatch, tmp_path):
    target = tmp_path / "weights.csv"
    target.write_bytes(b"original")
    monkeypatch.setattr(config, "FINAL_PROVISION_WEIGHTS_PATH", target)

    @protected_step("measure_x_14_finalize_provision_weights.py")
    def work():
        target.write_bytes(b"new")

    with pytest.raises(FileExistsError):
        work()
    assert target.read_bytes() == b"original"
    work(force=True)
    assert target.read_bytes() == b"new"


def test_no_resume_is_not_permission_to_replace_model_cache(monkeypatch, tmp_path):
    target = tmp_path / "model.csv"
    target.write_bytes(b"valuable cached decisions")
    module = load_script("measure_x_02_stage1a_code_institutional.py")
    monkeypatch.setattr(module, "ensure_directories", lambda: pytest.fail("entered model work"))
    with pytest.raises(FileExistsError):
        module.run(output_path=target, resume=False)
    assert target.read_bytes() == b"valuable cached decisions"


def test_new_outputs_can_be_updated_inside_one_approved_run(tmp_path):
    target = tmp_path / "metadata.json"
    with output_permission([target]):
        target.write_text("first stage")
        with output_permission([target]):
            target.write_text("second stage")
    with pytest.raises(FileExistsError):
        with output_permission([target]):
            pytest.fail("permission leaked outside the command")


def test_restart_failure_keeps_existing_model_file(temp_pipeline, monkeypatch):
    from utils import write_csv

    write_csv(pd.DataFrame([{"provision_id": "P1", "provision_text": "test"}]), config.PROVISIONS_MASTER_PATH)
    target = config.STAGE1A_MODEL_A_RESULTS_PATH
    target.write_bytes(b"original model decisions")
    module = load_script("measure_x_02_stage1a_code_institutional.py")

    def fail_before_results(*args, **kwargs):
        assert target.read_bytes() == b"original model decisions"
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(module, "code_one_provision", fail_before_results)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        module.run(provider="heuristic", resume=False, force=True)
    assert target.read_bytes() == b"original model decisions"


def test_force_keeps_resume_choice(monkeypatch):
    module = runner()
    seen = []
    monkeypatch.setattr(module, "model_settings", lambda *a: ("heuristic", "fake", None))
    monkeypatch.setattr(module, "load_script", lambda name: SimpleNamespace(run=lambda **kw: seen.append(kw)))
    module.run_stage1a_model(arguments(force=True), "A")
    assert seen[0]["resume"] is True
    module.run_stage1a_model(arguments(force=True, resume=False), "A")
    assert seen[1]["resume"] is False


def test_model_role_and_custom_path_preflight_are_precise(tmp_path):
    custom = tmp_path / "custom_model.csv"
    _, targets = step_paths("measure_x_02_stage1a_code_institutional.py", {"model_role": "B", "output_path": custom})
    assert custom.resolve() in targets
    assert config.STAGE1A_MODEL_A_RESULTS_PATH.resolve() not in targets
    assert config.STAGE1A_MODEL_B_RESULTS_PATH.resolve() not in targets
