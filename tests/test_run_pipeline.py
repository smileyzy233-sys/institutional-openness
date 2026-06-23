from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_runner():
    path = PROJECT_ROOT / "run_pipeline.py"
    spec = importlib.util.spec_from_file_location("pipeline_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage1_command_and_all_share_the_same_stage1_sequence(monkeypatch):
    runner = load_runner()
    calls: list[str] = []
    args = SimpleNamespace(multi_agreement_method="union")

    def record(name):
        return lambda *args, **kwargs: calls.append(name)

    class Script:
        def __init__(self, filename):
            self.filename = filename

        def run(self, **kwargs):
            calls.append(self.filename)

    monkeypatch.setattr(runner, "load_script", Script)
    monkeypatch.setattr(runner, "run_stage1a_model", lambda args, role: calls.append(f"stage1a-{role}"))
    monkeypatch.setattr(runner, "run_stage1b_model", lambda args, role: calls.append(f"stage1b-{role}"))
    monkeypatch.setattr(runner, "run_stage2_model", lambda args, role: calls.append(f"stage2-{role}"))
    monkeypatch.setattr(runner, "run_stage1a_arbitration", record("stage1a-arbitration"))
    monkeypatch.setattr(runner, "run_stage1b_arbitration", record("stage1b-arbitration"))
    monkeypatch.setattr(runner, "run_stage2_arbitration", record("stage2-arbitration"))
    monkeypatch.setattr(runner, "check_stage1a_gate", record("stage1a-gate"))
    monkeypatch.setattr(runner, "check_stage1b_gate", record("stage1b-gate"))
    monkeypatch.setattr(runner, "check_stage1_gate", record("stage1-gate"))

    runner.run_stage1_sequence(args)
    stage1_calls = calls.copy()

    calls.clear()
    runner.run_all(args)

    assert calls[1 : 1 + len(stage1_calls)] == stage1_calls

