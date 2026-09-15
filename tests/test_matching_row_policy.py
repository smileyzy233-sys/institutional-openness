from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from conftest import load_script
from match_y_x_common import (
    apply_row_policy,
    country_pair_masks,
    validate_row_policy_acceptance,
)


def _policy_spec(
    *, drop_row: bool = True, keep_domestic: bool = False
) -> dict:
    return {
        "row_policy": {
            "drop_row": drop_row,
            "keep_domestic": keep_domestic,
        }
    }


def _policy_frame() -> pd.DataFrame:
    """Small frame containing international, domestic, ROW, and missing ISO pairs."""
    return pd.DataFrame(
        {
            "iso_o": [
                "AAA",
                " FRA ",
                " row ",
                "ROW",
                None,
                np.nan,
                pd.NA,
                "",
            ],
            "iso_d": [
                "BBB",
                "fra",
                " ROW ",
                "DEU",
                "FRA",
                "FRA",
                "FRA",
                "FRA",
            ],
            "sector_amne": list(range(1, 9)),
        }
    )


@pytest.mark.parametrize(
    ("specs", "expected_rows", "expected_row_rows", "expected_domestic_rows"),
    [
        ({}, 5, 0, 0),
        (_policy_spec(keep_domestic=True), 6, 0, 1),
        (_policy_spec(drop_row=False), 6, 1, 0),
        (_policy_spec(drop_row=False, keep_domestic=True), 8, 2, 2),
    ],
)
def test_row_policy_defaults_and_independent_switches(
    specs, expected_rows, expected_row_rows, expected_domestic_rows
):
    data = _policy_frame()
    filtered, audit = apply_row_policy(data, specs)

    assert len(filtered) == expected_rows
    assert audit["rows_before"] == 8
    assert audit["row_rows_before"] == 2
    assert audit["domestic_rows_before"] == 2
    assert audit["overlap_rows_before"] == 1
    assert audit["rows_dropped"] == 8 - expected_rows
    assert audit["rows_after"] == expected_rows
    assert int(filtered["is_row_pair"].eq(1).sum()) == expected_row_rows
    assert int(filtered["is_domestic_pair"].eq(1).sum()) == expected_domestic_rows

    # Filtering only adds diagnostics; it never replaces the source ISO values.
    assert filtered.loc[filtered["sector_amne"].eq(1), "iso_o"].iat[0] == "AAA"
    assert filtered.loc[filtered["sector_amne"].eq(1), "iso_d"].iat[0] == "BBB"
    if expected_domestic_rows:
        domestic = filtered.loc[filtered["is_domestic_pair"].eq(1)].iloc[0]
        assert domestic["iso_o"] == " FRA "
        assert domestic["iso_d"] == "fra"


def test_country_pair_masks_do_not_classify_missing_or_blank_iso_as_domestic():
    data = pd.DataFrame(
        {
            "iso_o": [
                None,
                np.nan,
                pd.NA,
                "",
                "\t",
                "\u00a0",
                None,
                "FRA",
            ],
            "iso_d": [
                None,
                np.nan,
                pd.NA,
                "",
                "\t",
                "\u00a0",
                "FRA",
                " fra ",
            ],
        }
    )
    row, domestic = country_pair_masks(data)

    assert not bool(row.any())
    assert domestic.tolist() == [False, False, False, False, False, False, False, True]


@pytest.mark.parametrize("keep_domestic", [False, True])
@pytest.mark.parametrize("drop_row", [False, True])
def test_acceptance_gates_use_source_and_post_row_counts_independently(
    keep_domestic, drop_row
):
    audit = {
        "rows_before": 8,
        "row_rows_before": 2,
    }
    specs = {
        "row_policy": {
            "drop_row": drop_row,
            "keep_domestic": keep_domestic,
        },
        "acceptance": {
            "2020": {
                "trade_source_rows": 8,
                "trade_rows_excluding_row": 6,
            }
        },
    }

    # The source and ROW-excluded gates remain valid under either domestic
    # setting and whether ROW is ultimately retained by policy.
    validate_row_policy_acceptance(audit, specs, "trade", 2020)

    for key, value in [
        ("trade_source_rows", 7),
        ("trade_rows_excluding_row", 7),
    ]:
        broken = json.loads(json.dumps(specs))
        broken["acceptance"]["2020"][key] = value
        with pytest.raises(ValueError, match="trade row acceptance failed"):
            validate_row_policy_acceptance(audit, broken, "trade", 2020)


def test_row_policy_is_idempotent_and_deduplicates_row_domestic_overlap():
    first, first_audit = apply_row_policy(_policy_frame(), {})
    second, second_audit = apply_row_policy(first, {})

    pd.testing.assert_frame_equal(
        first.reset_index(drop=True), second.reset_index(drop=True)
    )
    assert first_audit["overlap_rows_before"] == 1
    assert first_audit["rows_dropped"] == 3
    assert second_audit["rows_before"] == len(first)
    assert second_audit["rows_dropped"] == 0


def _write_dependent_source(tmp_path, equation: str, rows, year: int = 2020):
    stem = "amne" if equation == "mp" else "icio"
    path = tmp_path / "Explained_variable" / f"{stem}{year}.dta"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_stata(path, write_index=False, version=118)
    return path


def _prepare_specs(*, equation: str = "trade", policy: dict | None = None):
    specs = {
        "equations": {
            equation: {
                "dependent_path_template": (
                    "Explained_variable/amne{year}.dta"
                    if equation == "mp"
                    else "Explained_variable/icio{year}.dta"
                ),
                "dependent_column": "value",
                "x_column": f"raw_{'mp' if equation == 'mp' else 'trade'}_score",
            }
        },
        "iso_aliases": {"ROM": "ROU"},
    }
    if policy is not None:
        specs["row_policy"] = policy["row_policy"]
    return specs


@pytest.mark.parametrize(
    ("policy", "expected_rows"),
    [
        (None, 1),
        ({"row_policy": {"drop_row": True, "keep_domestic": True}}, 2),
        ({"row_policy": {"drop_row": False, "keep_domestic": True}}, 3),
    ],
)
def test_prepare_y_applies_policy_without_rewriting_original_iso(
    tmp_path, policy, expected_rows
):
    source_rows = [
        {
            "iso_o": "AAA",
            "iso_d": "BBB",
            "sector_amne": 1,
            "value": 2.0,
            "country_o": "A",
            "country_d": "B",
            "iso_o1": 1,
            "iso_d1": 2,
        },
        {
            "iso_o": " FRA ",
            "iso_d": "fra",
            "sector_amne": 2,
            "value": 0.0,
            "country_o": "France",
            "country_d": "France",
            "iso_o1": 3,
            "iso_d1": 3,
        },
        {
            "iso_o": " row ",
            "iso_d": "DEU",
            "sector_amne": 3,
            "value": 1.0,
            "country_o": "Rest of world",
            "country_d": "Germany",
            "iso_o1": 99,
            "iso_d1": 4,
        },
    ]
    _write_dependent_source(tmp_path, "trade", source_rows)
    module = load_script("match_y_x_02_prepare_y.py")
    out = module.prepare_y(
        tmp_path, _prepare_specs(policy=policy), "trade", 2020
    )

    assert len(out) == expected_rows
    assert out["iso_o"].isin(["AAA", " FRA ", " row "]).all()
    assert out["iso_d"].isin(["BBB", "fra", "DEU"]).all()
    assert out.attrs["row_policy_audit"]["rows_before"] == 3
    assert out.attrs["row_policy_audit"]["rows_after"] == expected_rows
    assert out.attrs["row_policy_audit"]["rows_dropped"] == 3 - expected_rows
    assert out.loc[out["sector_amne"].eq(1), "iso_o"].iat[0] == "AAA"
    assert out.loc[out["sector_amne"].eq(1), "iso_d"].iat[0] == "BBB"


def test_left_join_preserves_rows_and_rejects_duplicate_right_keys():
    common = load_script("match_y_x_cons_common.py")
    base = pd.DataFrame(
        {
            "year": [2020, 2020, 2020, 2020],
            "iso_o_match": ["AAA", "AAA", "BBB", "CCC"],
            "iso_d_match": ["BBB", "CCC", "AAA", "DDD"],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    right = pd.DataFrame(
        {
            "year": [2020, 2020, 2020],
            "iso_o_match": ["AAA", "AAA", "BBB"],
            "iso_d_match": ["BBB", "CCC", "AAA"],
            "control": [10.0, 20.0, 30.0],
        }
    )

    merged, diagnostic = common.left_merge_checked(
        base,
        right,
        keys=["year", "iso_o_match", "iso_d_match"],
        source="synthetic controls",
        match_flag="match_control",
    )
    assert len(merged) == len(base) == diagnostic["rows_before"]
    assert diagnostic["rows_after"] == len(base)
    assert merged["control"].iloc[:3].tolist() == [10.0, 20.0, 30.0]
    assert pd.isna(merged["control"].iloc[3])
    assert merged["match_control"].tolist() == [1, 1, 1, 0]

    duplicate_right = pd.concat([right, right.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="not unique"):
        common.left_merge_checked(
            base,
            duplicate_right,
            keys=["year", "iso_o_match", "iso_d_match"],
            source="synthetic duplicate controls",
            match_flag="match_control",
        )


@pytest.mark.parametrize(
    ("iso_o", "iso_d"),
    [("AAA", "AAA"), ("ROW", "BBB")],
)
def test_validate_dataset_rejects_post_filter_domestic_or_row_rows(iso_o, iso_d):
    export = load_script("match_y_x_06_validate_export.py")
    data = _synthetic_yx("trade")
    data.loc[0, "iso_o"] = iso_o
    data.loc[0, "iso_d"] = iso_d
    specs = {"row_policy": {"drop_row": True, "keep_domestic": False}}
    audit = {
        "rows_before": len(data),
        "rows_after": len(data),
    }

    with pytest.raises(ValueError, match="row_policy"):
        export._validate_dataset(
            data,
            "trade",
            "raw_trade_score",
            2020,
            specs,
            audit,
        )


def _write_minimal_matching_config(
    tmp_path, *, keep_domestic: bool, include_row_policy: bool = True
):
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "matching_specs.json"
    config = {
        "schema_version": "matching_specs_v1",
        "years": [2020],
        "iso_aliases": {},
        "pair_year_source": "pairs.csv",
        "gravity_path": "gravity.csv",
        "tariff_paths": {"2020": "tariff.csv"},
        "output_root": "outputs/matched_data",
        "equations": {
            "trade": {
                "dependent_path_template": "Explained_variable/icio{year}.dta",
                "dependent_column": "value",
                "x_column": "raw_trade_score",
            },
            "mp": {
                "dependent_path_template": "Explained_variable/amne{year}.dta",
                "dependent_column": "value",
                "x_column": "raw_mp_score",
            },
        },
        "control_specs": {
            "mp_controls_v1": {
                "equations": ["mp"],
                "mp": {"selected_controls": [], "candidate_controls": []},
            }
        },
    }
    if include_row_policy:
        config["row_policy"] = {
            "drop_row": True,
            "keep_domestic": keep_domestic,
        }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    for relative in ["pairs.csv", "gravity.csv", "tariff.csv"]:
        (tmp_path / relative).write_bytes(b"synthetic source\n")
    # The exporter hashes these configured inputs but does not read them;
    # keep them as opaque synthetic source files so this test never builds Y.
    for relative in [
        "Explained_variable/icio2020.dta",
        "Explained_variable/amne2020.dta",
    ]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic dependent source\n")
    return config_path


def test_load_matching_specs_defaults_and_rejects_non_boolean_policy(tmp_path):
    config_path = _write_minimal_matching_config(
        tmp_path,
        keep_domestic=False,
        include_row_policy=False,
    )
    common = load_script("match_y_x_common.py")
    specs = common.load_matching_specs(tmp_path)
    assert specs["row_policy"] == {"drop_row": True, "keep_domestic": False}

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["row_policy"] = {"drop_row": True, "keep_domestic": "false"}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON booleans"):
        common.load_matching_specs(tmp_path)


def _synthetic_yx(equation: str) -> pd.DataFrame:
    x_column = f"raw_{equation}_score"
    return pd.DataFrame(
        {
            "year": [2020, 2020],
            "iso_o": ["AAA", "BBB"],
            "iso_d": ["BBB", "AAA"],
            "iso_o_match": ["AAA", "BBB"],
            "iso_d_match": ["BBB", "AAA"],
            "country_o": ["A", "B"],
            "country_d": ["B", "A"],
            "iso_o1": [1, 2],
            "iso_d1": [2, 1],
            "sector_amne": [1, 1],
            "value": [1.0, 0.0],
            "positive_value": [1, 0],
            "is_domestic_pair": [0, 0],
            "is_row_pair": [0, 0],
            x_column: [0.2, 0.3],
            "matched_x": [1, 1],
            "uses_iso_bridge": [0, 0],
        }
    )


def _zero_filter_audit(policy: dict, rows: int = 2) -> dict:
    return {
        "row_policy": policy["row_policy"],
        "rows_before": rows,
        "row_rows_before": 0,
        "domestic_rows_before": 0,
        "overlap_rows_before": 0,
        "rows_dropped": 0,
        "rows_after": rows,
        "row_rows_after": 0,
        "domestic_rows_after": 0,
    }


def _export_synthetic_yx(tmp_path, *, keep_domestic: bool):
    _write_minimal_matching_config(tmp_path, keep_domestic=keep_domestic)
    common = load_script("match_y_x_common.py")
    cons_common = load_script("match_y_x_cons_common.py")
    specs = common.load_matching_specs(tmp_path)
    export = load_script("match_y_x_06_validate_export.py")
    export.current_git_commit = lambda _: None
    trade = _synthetic_yx("trade")
    mp = _synthetic_yx("mp")
    output_root = tmp_path / "synthetic_outputs"
    export._write_year(
        tmp_path,
        specs,
        2020,
        trade,
        mp,
        row_policy_audits={
            "trade": _zero_filter_audit(specs, len(trade)),
            "mp": _zero_filter_audit(specs, len(mp)),
        },
        output_root=output_root,
        force=False,
    )
    return common, cons_common, specs, output_root


def test_synthetic_yx_export_manifest_and_mp_control_left_join(tmp_path):
    common, cons_common, specs, output_root = _export_synthetic_yx(
        tmp_path, keep_domestic=False
    )
    paths = common.y_x_output_paths(tmp_path, specs, 2020, output_root)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["row_policy"] == {"drop_row": True, "keep_domestic": False}
    assert manifest["row_policy_audit"]["mp"]["rows_dropped"] == 0

    mp_base, _ = cons_common.read_y_x_base(
        tmp_path, specs, "mp", 2020, output_root
    )
    mp_module = load_script("match_y_x_cons_05_merge_mp_controls.py")
    pair_controls = pd.DataFrame(
        {
            "year": [2020, 2020],
            "iso_o_match": ["AAA", "BBB"],
            "iso_d_match": ["BBB", "AAA"],
            "trade_agreement_dummy": [0, 1],
            "idealpoint_abs_distance": [0.1, 0.2],
            "match_trade_agreement": [1, 1],
            "match_idealpoint": [1, 1],
        }
    )
    merged, diagnostics = mp_module.merge_mp_controls(
        mp_base, pair_controls
    )
    assert len(merged) == len(mp_base) == 2
    assert len(diagnostics) == 1
    assert merged["match_pair_controls"].tolist() == [1, 1]


def test_old_keep_domestic_manifest_is_rejected_by_read_and_control_dry_run(
    tmp_path,
):
    common, cons_common, specs, output_root = _export_synthetic_yx(
        tmp_path, keep_domestic=True
    )
    # The persisted manifest records the old policy. Change only the config
    # used by the new consumer; no output is rebuilt or overwritten.
    config_path = tmp_path / "configs" / "matching_specs.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["row_policy"]["keep_domestic"] = False
    config_path.write_text(json.dumps(config), encoding="utf-8")
    fresh_specs = common.load_matching_specs(tmp_path)

    with pytest.raises(ValueError, match="row_policy mismatch"):
        cons_common.read_y_x_base(
            tmp_path, fresh_specs, "mp", 2020, output_root
        )

    controls = load_script("match_y_x_cons_07_validate_export.py")
    for force in (False, True):
        with pytest.raises(ValueError, match="row_policy mismatch"):
            controls.run(
                project_dir=tmp_path,
                years=[2020],
                control_spec="mp_controls_v1",
                output_root=output_root,
                dry_run=True,
                force=force,
            )


@pytest.mark.parametrize("tamper", ["missing_manifest", "hash"])
def test_yx_manifest_presence_and_hash_are_required(tmp_path, tamper):
    common, cons_common, specs, output_root = _export_synthetic_yx(
        tmp_path, keep_domestic=False
    )
    paths = common.y_x_output_paths(tmp_path, specs, 2020, output_root)
    if tamper == "missing_manifest":
        paths["manifest"].unlink()
        expected = "manifest"
    else:
        paths["mp_csv"].write_text(
            paths["mp_csv"].read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        expected = "SHA256"

    with pytest.raises(ValueError, match=expected):
        cons_common.read_y_x_base(tmp_path, specs, "mp", 2020, output_root)
