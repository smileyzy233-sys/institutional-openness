from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import config
from conftest import load_script
from utils import read_csv, write_csv


def test_loader_preserves_fractional_coverage_and_english_provision_text() -> None:
    loader = load_script("01_load_dta.py")
    stata = pd.DataFrame(
        {
            "Area": ["Services", "Services"],
            "Coding": ["A1", "A2"],
            "Provision": ["English provision one", "English provision two"],
            "Provision译文": ["条款一", "条款二"],
            "agree_1": [0.5, 1.0],
            "agree_2": [0.0, 1 / 3],
        }
    )

    provisions, matrix, long_matrix = loader.build_provisions_and_matrix(stata)

    assert provisions["provision_text"].tolist() == [
        "English provision one",
        "English provision two",
    ]
    assert provisions["provision_translation"].tolist() == ["条款一", "条款二"]
    assert matrix.loc[matrix["agreement_id"].eq("agree_1"), "P0001"].item() == 0.5
    assert matrix.loc[matrix["agreement_id"].eq("agree_2"), "P0002"].item() == pytest.approx(1 / 3)
    assert long_matrix["coverage"].sum() == pytest.approx(1.0 + 0.5 + 1 / 3)


def test_loader_rejects_out_of_range_coverage() -> None:
    loader = load_script("01_load_dta.py")
    stata = pd.DataFrame(
        {
            "Area": ["Services"],
            "Coding": ["A1"],
            "Provision": ["English provision"],
            "agree_1": [1.2],
        }
    )

    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        loader.build_provisions_and_matrix(stata)


def test_agreement_indices_report_any_full_and_fractional_coverage(temp_pipeline) -> None:
    write_csv(
        pd.DataFrame(
            {
                "agreement_id": ["agree_1"],
                "P0001": [0.5],
                "P0002": [1.0],
            }
        ),
        config.AGREEMENT_MATRIX_PATH,
    )
    write_csv(
        pd.DataFrame(
            {
                "agreement_id": ["agree_1"],
                "WBID": [1],
                "agreement_name": ["Test agreement"],
            }
        ),
        config.AGREEMENTS_MASTER_PATH,
    )
    write_csv(
        pd.DataFrame(
            {
                "provision_id": ["P0001", "P0002"],
                "final_is_institutional_opening": [1, 1],
                "final_dominant_dimension": ["rules", "standards"],
                "final_impact_type": ["both", "both"],
                "effective_trade_weight": [0.8, 0.3],
                "effective_investment_weight": [0.2, 0.7],
                "pipeline_schema_version": [
                    config.PIPELINE_SCHEMA_VERSION,
                    config.PIPELINE_SCHEMA_VERSION,
                ],
            }
        ),
        config.FINAL_PROVISION_WEIGHTS_PATH,
    )

    load_script("11_compute_agreement_indices.py").run()
    out = read_csv(config.AGREEMENT_LEVEL_INDICES_PATH).iloc[0]

    assert out["raw_trade_score"] == pytest.approx(0.7)
    assert out["raw_investment_score"] == pytest.approx(0.8)
    assert out["num_total_provisions_included"] == 2
    assert out["num_total_provisions_full_coverage"] == 1
    assert out["total_provision_coverage"] == pytest.approx(1.5)
    assert out["coverage_matrix_schema_version"] == config.COVERAGE_MATRIX_SCHEMA_VERSION
    assert out["num_rules_provisions_included"] == 1
    assert out["num_rules_provisions_full_coverage"] == 0
    assert out["rules_provision_coverage"] == pytest.approx(0.5)


def test_country_pair_union_uses_maximum_fractional_coverage() -> None:
    country_indices = load_script("12_compute_country_pair_indices.py")
    matrix_by_id = pd.DataFrame(
        {"P0001": [0.5, 0.75], "P0002": [1.0, 0.0]},
        index=["agree_1", "agree_2"],
    )

    result = country_indices.compute_union_tuple(
        ("agree_1", "agree_2"),
        matrix_by_id=matrix_by_id,
        provision_cols=["P0001", "P0002"],
        trade_w=np.array([0.8, 0.3]),
        investment_w=np.array([0.2, 0.7]),
    )

    assert result["raw_trade_score"] == pytest.approx(0.9)
    assert result["raw_investment_score"] == pytest.approx(0.85)
