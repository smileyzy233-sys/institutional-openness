from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def audit_module():
    path = ROOT / "scripts" / "verify_review_bundle.py"
    spec = importlib.util.spec_from_file_location("verify_review_bundle_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_matrix_fixture(root: Path) -> None:
    workbook = root / "data/raw/DTA 2.0 - Vertical Content (v2)_code.xlsx"
    matrix = root / "data/interim/agreement_matrix.csv"
    workbook.parent.mkdir(parents=True)
    matrix.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "Area": ["A", "B"],
            "Coding": ["A - prov_01", "B - prov_01"],
            "Provision": ["one", "two"],
            "Provision译文": ["一", "二"],
            "agree_1": [None, 0.5],
            "agree_2": [1, 0],
        }
    ).to_excel(workbook, sheet_name="STATA", index=False)
    pd.DataFrame(
        {
            "agreement_id": ["agree_1", "agree_2"],
            "P0001": [0, 1],
            "P0002": [0.5, 0],
        }
    ).to_csv(matrix, index=False)


def test_matrix_check_preserves_partial_coverage_and_detects_mismatch(tmp_path):
    module = audit_module()
    write_matrix_fixture(tmp_path)
    assert module.matrix_check(tmp_path)["status"] == "pass"
    matrix = tmp_path / "data/interim/agreement_matrix.csv"
    frame = pd.read_csv(matrix)
    frame.loc[0, "P0002"] = 0.25
    frame.to_csv(matrix, index=False)
    checked = module.matrix_check(tmp_path)
    assert checked["status"] == "fail"
    assert checked["value_mismatches"] == 1


def test_main_refuses_to_overwrite_existing_report(tmp_path, capsys):
    module = audit_module()
    report = tmp_path / "audit.json"
    report.write_text(json.dumps({"keep": True}), encoding="utf-8")
    code = module.main(["--data-root", str(tmp_path), "--report", str(report)])
    assert code == 2
    assert json.loads(report.read_text(encoding="utf-8")) == {"keep": True}
    assert "refusing to overwrite" in capsys.readouterr().out


@pytest.mark.parametrize("fault", ["missing_row", "wrong_key", "duplicate", "missing_value", "empty"])
def test_keyed_comparison_rejects_incomplete_or_corrupt_data(fault):
    module = audit_module()
    expected = pd.DataFrame({"id": [1, 2], "score": [0.5, 0.5]})
    actual = expected.copy()
    if fault == "missing_row":
        actual = actual.iloc[:1]
    elif fault == "wrong_key":
        actual.loc[0, "id"] = 3
    elif fault == "duplicate":
        actual.loc[0, "id"] = 2
    elif fault == "missing_value":
        actual.loc[0, "score"] = float("nan")
    else:
        actual = actual.iloc[:0]
    assert module.keyed_comparison(actual, expected, ["id"], ["score"])["status"] == "fail"


def test_keyed_comparison_aligns_by_key_instead_of_row_position():
    module = audit_module()
    expected = pd.DataFrame({"id": [1, 2], "score": [0.5, 1.0]})
    assert module.keyed_comparison(expected.iloc[::-1], expected, ["id"], ["score"])["status"] == "pass"
