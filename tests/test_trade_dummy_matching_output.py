from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import config
from conftest import load_script


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_matching_output_path_matches_matching_configuration():
    specs = json.loads(
        (PROJECT_ROOT / "configs" / "matching_specs.json").read_text(
            encoding="utf-8"
        )
    )

    assert specs["pair_year_source"] == str(
        config.ICIO_2000_2023_DUMMY_PATH.relative_to(config.PROJECT_ROOT)
    ).replace("\\", "/")


def test_matching_panel_is_exact_2000_2023_subset():
    module = load_script("14_build_trade_agreement_dummy.py")
    rows = [
        {"iso_o": "AAA", "iso_d": "AAA", "year": year, "value": year}
        for year in [1999, 2000, 2019, 2023, 2024]
    ]
    all_years = pd.DataFrame(rows)

    matching = module.build_matching_panel(all_years)

    assert matching["year"].tolist() == [2000, 2019, 2023]
    assert matching["value"].tolist() == [2000, 2019, 2023]
