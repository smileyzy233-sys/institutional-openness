from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = PROJECT_ROOT / "src" / "run_pipeline.py"


def load_wrapper():
    spec = importlib.util.spec_from_file_location("src_run_pipeline_wrapper", WRAPPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrapper_import_is_side_effect_free_and_main_forwards(monkeypatch):
    forwarded: list[tuple[Path, str]] = []

    def record(path, *, run_name):
        forwarded.append((Path(path), run_name))
        return {}

    monkeypatch.setattr(runpy, "run_path", record)
    wrapper = load_wrapper()

    assert forwarded == []
    wrapper.main()
    assert forwarded == [(PROJECT_ROOT / "run_pipeline.py", "__main__")]
