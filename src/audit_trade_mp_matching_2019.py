"""Reproducible audit of trade/MP channel semantics and 2019 regression joins.

The audit is read-only.  It verifies the legacy label migration, independently
recomputes agreement and country-pair scores, and reconciles the regression
files with their dependent-variable and control-variable sources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = (
    ROOT / "migration_backups" / "20260724_pre_trade_mp" / "files"
)


def numeric_equal(
    left: pd.Series, right: pd.Series, *, atol: float = 1e-9
) -> np.ndarray:
    return np.isclose(
        pd.to_numeric(left, errors="coerce").to_numpy(float),
        pd.to_numeric(right, errors="coerce").to_numpy(float),
        atol=atol,
        rtol=0,
        equal_nan=True,
    )


def text_equal(left: pd.Series, right: pd.Series) -> np.ndarray:
    left_values = left.where(left.notna(), "<NA>").astype(str).to_numpy()
    right_values = right.where(right.notna(), "<NA>").astype(str).to_numpy()
    return left_values == right_values


def merged_column(
    merged: pd.DataFrame, column: str, side: str
) -> pd.Series:
    suffixed = f"{column}_{side}"
    return merged[suffixed] if suffixed in merged.columns else merged[column]


def compare_migrated_file(
    relative_path: str,
    keys: list[str],
    numeric_mappings: list[tuple[str, str]],
    category_mappings: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    old = pd.read_csv(BACKUP_ROOT / relative_path, low_memory=False)
    current = pd.read_csv(ROOT / relative_path, low_memory=False)
    merged = old.merge(
        current,
        on=keys,
        how="outer",
        suffixes=("_old", "_current"),
        validate="one_to_one",
        indicator=True,
    )
    result: dict[str, Any] = {
        "artifact": relative_path,
        "rows": len(current),
        "key_duplicates": int(current.duplicated(keys).sum()),
        "unmatched_keys": int(merged["_merge"].ne("both").sum()),
    }
    for old_name, current_name in numeric_mappings:
        mismatch = ~numeric_equal(
            merged_column(merged, old_name, "old"),
            merged_column(merged, current_name, "current"),
        )
        result[f"{old_name}->{current_name}"] = int(mismatch.sum())

    label_map = {
        "mp": "trade",
        "tr": "mp",
        "trade": "trade",
        "both": "both",
        "none": "none",
        "not_applicable": "not_applicable",
    }
    for old_name, current_name in category_mappings or []:
        expected = merged_column(merged, old_name, "old").map(
            lambda value: (
                label_map.get(str(value), value)
                if pd.notna(value)
                else value
            )
        )
        mismatch = ~text_equal(
            expected, merged_column(merged, current_name, "current")
        )
        result[f"{old_name}->{current_name}"] = int(mismatch.sum())
    return result


def audit_migration() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for model in ("a", "b"):
        rows.append(
            compare_migrated_file(
                f"data/interim/stage2/stage2_model_{model}_results.csv",
                ["provision_id"],
                [
                    ("raw_trade_weight", "raw_trade_weight"),
                    ("raw_investment_weight", "raw_mp_weight"),
                    (
                        "normalized_trade_weight",
                        "normalized_trade_weight",
                    ),
                    (
                        "normalized_investment_weight",
                        "normalized_mp_weight",
                    ),
                ],
                [("impact_type", "impact_type")],
            )
        )

    rows.append(
        compare_migrated_file(
            "data/interim/stage2/stage2_dual_model_comparison.csv",
            ["provision_id"],
            [
                ("model_a_trade_weight", "model_a_trade_weight"),
                ("model_a_investment_weight", "model_a_mp_weight"),
                ("model_b_trade_weight", "model_b_trade_weight"),
                ("model_b_investment_weight", "model_b_mp_weight"),
                ("model_a_raw_trade_weight", "model_a_raw_trade_weight"),
                (
                    "model_a_raw_investment_weight",
                    "model_a_raw_mp_weight",
                ),
                ("model_b_raw_trade_weight", "model_b_raw_trade_weight"),
                (
                    "model_b_raw_investment_weight",
                    "model_b_raw_mp_weight",
                ),
                (
                    "both_investment_weight_abs_diff",
                    "both_mp_weight_abs_diff",
                ),
            ],
            [
                ("model_a_impact_type", "model_a_impact_type"),
                ("model_b_impact_type", "model_b_impact_type"),
            ],
        )
    )
    rows.append(
        compare_migrated_file(
            "data/interim/stage2/stage2_arbitration_results.csv",
            ["provision_id"],
            [
                ("final_trade_weight", "final_trade_weight"),
                ("final_investment_weight", "final_mp_weight"),
            ],
            [("final_impact_type", "final_impact_type")],
        )
    )
    rows.append(
        compare_migrated_file(
            "data/processed/final_provision_weights.csv",
            ["provision_id"],
            [
                ("model_a_trade_weight", "model_a_trade_weight"),
                ("model_a_investment_weight", "model_a_mp_weight"),
                ("model_b_trade_weight", "model_b_trade_weight"),
                ("model_b_investment_weight", "model_b_mp_weight"),
                ("final_trade_weight", "final_trade_weight"),
                ("final_investment_weight", "final_mp_weight"),
                ("effective_trade_weight", "effective_trade_weight"),
                ("effective_investment_weight", "effective_mp_weight"),
            ],
            [
                ("model_a_impact_type", "model_a_impact_type"),
                ("model_b_impact_type", "model_b_impact_type"),
                ("final_impact_type", "final_impact_type"),
            ],
        )
    )
    rows.append(
        compare_migrated_file(
            "data/processed/agreement_level_indices.csv",
            ["agreement_id"],
            [
                ("raw_trade_score", "raw_trade_score"),
                ("raw_investment_score", "raw_mp_score"),
                (
                    "num_trade_related_provisions_included",
                    "num_trade_related_provisions_included",
                ),
                (
                    "num_investment_related_provisions_included",
                    "num_mp_related_provisions_included",
                ),
                (
                    "trade_related_provision_coverage",
                    "trade_related_provision_coverage",
                ),
                (
                    "investment_related_provision_coverage",
                    "mp_related_provision_coverage",
                ),
            ],
        )
    )
    rows.append(
        compare_migrated_file(
            "data/processed/country_pair_year_indices.csv",
            ["iso1", "iso2", "year"],
            [
                ("raw_trade_score", "raw_trade_score"),
                ("raw_investment_score", "raw_mp_score"),
            ],
        )
    )

    old_weights = pd.read_csv(
        BACKUP_ROOT / "data/processed/final_provision_weights.csv",
        low_memory=False,
    )
    current_weights = pd.read_csv(
        ROOT / "data/processed/final_provision_weights.csv",
        low_memory=False,
    )
    category_counts = pd.concat(
        [
            old_weights["final_impact_type"]
            .value_counts()
            .rename("before_migration"),
            current_weights["final_impact_type"]
            .value_counts()
            .rename("after_migration"),
        ],
        axis=1,
    ).fillna(0).astype(int)
    return pd.DataFrame(rows), category_counts


def audit_final_weight_rules() -> pd.DataFrame:
    weights = pd.read_csv(
        ROOT / "data/processed/final_provision_weights.csv",
        low_memory=False,
    )
    rows: list[dict[str, Any]] = []
    for impact_type, expected in {
        "trade": (1.0, 0.0),
        "mp": (0.0, 1.0),
        "none": (0.0, 0.0),
        "not_applicable": (0.0, 0.0),
    }.items():
        selected = weights["final_impact_type"].eq(impact_type)
        correct = numeric_equal(
            weights.loc[selected, "effective_trade_weight"],
            pd.Series(expected[0], index=weights.index[selected]),
        ) & numeric_equal(
            weights.loc[selected, "effective_mp_weight"],
            pd.Series(expected[1], index=weights.index[selected]),
        )
        rows.append(
            {
                "impact_type": impact_type,
                "rows": int(selected.sum()),
                "weight_rule_violations": int((~correct).sum()),
            }
        )

    selected = weights["final_impact_type"].eq("both")
    trade_weight = weights.loc[selected, "effective_trade_weight"]
    mp_weight = weights.loc[selected, "effective_mp_weight"]
    correct = (
        trade_weight.gt(0)
        & mp_weight.gt(0)
        & np.isclose(
            (trade_weight + mp_weight).to_numpy(float),
            1.0,
            atol=1e-9,
            rtol=0,
        )
    )
    rows.append(
        {
            "impact_type": "both",
            "rows": int(selected.sum()),
            "weight_rule_violations": int((~correct).sum()),
        }
    )
    return pd.DataFrame(rows)


def audit_recomputed_scores() -> pd.DataFrame:
    weights = pd.read_csv(
        ROOT / "data/processed/final_provision_weights.csv",
        low_memory=False,
    )
    matrix = pd.read_csv(
        ROOT / "data/interim/agreement_matrix.csv", low_memory=False
    )
    provision_columns = [
        column for column in matrix.columns if column.startswith("P")
    ]
    aligned_weights = weights.set_index("provision_id").loc[
        provision_columns
    ]
    coverage = (
        matrix[provision_columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )
    trade_weights = aligned_weights["effective_trade_weight"].to_numpy(float)
    mp_weights = aligned_weights["effective_mp_weight"].to_numpy(float)

    agreement_expected = pd.DataFrame(
        {
            "agreement_id": matrix["agreement_id"],
            "trade_expected": np.round(
                coverage.to_numpy(float) @ trade_weights, 6
            ),
            "mp_expected": np.round(
                coverage.to_numpy(float) @ mp_weights, 6
            ),
        }
    )
    agreement_actual = pd.read_csv(
        ROOT / "data/processed/agreement_level_indices.csv",
        low_memory=False,
    )
    agreement = agreement_actual.merge(
        agreement_expected,
        on="agreement_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    matrix_by_agreement = coverage.copy()
    matrix_by_agreement.index = matrix["agreement_id"]
    bilateral = pd.read_csv(
        ROOT / "data/interim/bilateral_panel.csv",
        usecols=["iso1", "iso2", "year", "agreement_id"],
        low_memory=False,
    )

    def agreement_tuple(values: pd.Series) -> tuple[str, ...]:
        return tuple(sorted(set(values.dropna().astype(str))))

    groups = (
        bilateral.groupby(["iso1", "iso2", "year"], sort=False)[
            "agreement_id"
        ]
        .agg(agreement_tuple)
        .reset_index(name="agreements")
    )
    score_cache: dict[tuple[str, ...], tuple[float, float]] = {}
    for agreement_ids in groups["agreements"].drop_duplicates():
        union_coverage = (
            matrix_by_agreement.loc[list(agreement_ids)]
            .to_numpy(float)
            .max(axis=0)
        )
        score_cache[agreement_ids] = (
            round(float(union_coverage @ trade_weights), 6),
            round(float(union_coverage @ mp_weights), 6),
        )
    groups[["trade_expected", "mp_expected"]] = pd.DataFrame(
        [score_cache[value] for value in groups["agreements"]],
        index=groups.index,
    )
    pair_actual = pd.read_csv(
        ROOT / "data/processed/country_pair_year_indices.csv",
        low_memory=False,
    )
    pair = pair_actual.merge(
        groups.drop(columns="agreements"),
        on=["iso1", "iso2", "year"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    rows: list[dict[str, Any]] = []
    for layer, frame in [
        ("agreement_level_indices", agreement),
        ("country_pair_year_indices", pair),
    ]:
        intended = numeric_equal(
            frame["raw_trade_score"], frame["trade_expected"], atol=1e-8
        ) & numeric_equal(
            frame["raw_mp_score"], frame["mp_expected"], atol=1e-8
        )
        unequal = ~np.isclose(
            frame["trade_expected"],
            frame["mp_expected"],
            atol=1e-8,
            rtol=0,
            equal_nan=True,
        )
        swapped = (
            numeric_equal(
                frame["raw_trade_score"],
                frame["mp_expected"],
                atol=1e-8,
            )
            & numeric_equal(
                frame["raw_mp_score"],
                frame["trade_expected"],
                atol=1e-8,
            )
            & unequal
        )
        rows.append(
            {
                "layer": layer,
                "rows": len(frame),
                "unmatched_keys": int(frame["_merge"].ne("both").sum()),
                "intended_score_mismatches": int((~intended).sum()),
                "trade_mp_unequal_rows": int(unequal.sum()),
                "rows_fitting_swapped_hypothesis": int(swapped.sum()),
                "max_abs_trade_difference": float(
                    np.nanmax(
                        np.abs(
                            frame["raw_trade_score"]
                            - frame["trade_expected"]
                        )
                    )
                ),
                "max_abs_mp_difference": float(
                    np.nanmax(
                        np.abs(
                            frame["raw_mp_score"] - frame["mp_expected"]
                        )
                    )
                ),
            }
        )
    return pd.DataFrame(rows)


def load_base_and_output(
    source_relative_path: str, output_relative_path: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = pd.read_stata(
        ROOT / source_relative_path, convert_categoricals=False
    )
    source = source.loc[
        ~(source["iso_o"].eq("ROW") | source["iso_d"].eq("ROW"))
    ].copy()
    output = pd.read_csv(ROOT / output_relative_path, low_memory=False)
    return source, output


def audit_dependent_variables() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    specifications = [
        (
            "trade",
            "Explained_variable/icio2019.dta",
            "result/regression_2019/trade_cost_2019_matched.csv",
            "result/regression_2019/trade_cost_2019_matched.dta",
        ),
        (
            "mp",
            "Explained_variable/amne2019.dta",
            "result/regression_2019/mp_cost_2019_matched.csv",
            "result/regression_2019/mp_cost_2019_matched.dta",
        ),
    ]
    keys = ["iso_o", "iso_d", "sector_amne"]
    for equation, source_path, csv_path, dta_path in specifications:
        source, csv_output = load_base_and_output(source_path, csv_path)
        dta_output = pd.read_stata(
            ROOT / dta_path, convert_categoricals=False
        )
        csv_merged = source.merge(
            csv_output,
            on=keys,
            how="outer",
            suffixes=("_source", "_output"),
            validate="one_to_one",
            indicator=True,
        )
        dta_merged = source.merge(
            dta_output,
            on=keys,
            how="outer",
            suffixes=("_source", "_output"),
            validate="one_to_one",
            indicator=True,
        )
        if equation == "trade":
            csv_roundtrip = (
                csv_merged["value_output"]
                .astype(np.float32)
                .to_numpy()
                == csv_merged["value_source"]
                .astype(np.float32)
                .to_numpy()
            )
            absolute_difference = np.abs(
                csv_merged["value_output"].astype(float)
                - csv_merged["value_source"].astype(float)
            )
        else:
            csv_roundtrip = numeric_equal(
                csv_merged["value_output"],
                csv_merged["value_source"],
            )
            absolute_difference = np.abs(
                csv_merged["value_output"].astype(float)
                - csv_merged["value_source"].astype(float)
            )
        dta_exact = (
            dta_merged["value_output"].to_numpy()
            == dta_merged["value_source"].to_numpy()
        )
        rows.append(
            {
                "equation": equation,
                "source_rows_after_ROW_filter": len(source),
                "output_rows": len(csv_output),
                "unmatched_keys": int(
                    csv_merged["_merge"].ne("both").sum()
                ),
                "source_key_duplicates": int(source.duplicated(keys).sum()),
                "output_key_duplicates": int(
                    csv_output.duplicated(["year", *keys]).sum()
                ),
                "csv_roundtrip_value_mismatches": int(
                    (~csv_roundtrip).sum()
                ),
                "dta_exact_value_mismatches": int((~dta_exact).sum()),
                "csv_max_absolute_display_difference": float(
                    absolute_difference.max()
                ),
            }
        )
    return pd.DataFrame(rows)


def audit_pair_controls() -> pd.DataFrame:
    pair_source = pd.read_csv(
        ROOT / "data/processed/trade_dummy_icio_2000_2023.csv",
        low_memory=False,
    )
    pair_source = pair_source.loc[pair_source["year"].eq(2019)].rename(
        columns={
            "iso_o": "iso_o_match",
            "iso_d": "iso_d_match",
            "match_status": "dta_match_status",
        }
    )
    pair_keys = ["iso_o_match", "iso_d_match", "year"]
    source_fields = [
        "agreement_applicable",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "num_active_agreements",
        "dta_match_status",
        "raw_trade_score",
        "raw_mp_score",
    ]
    rows: list[dict[str, Any]] = []
    for equation, path, score_column in [
        (
            "trade",
            ROOT / "result/regression_2019/trade_cost_2019_matched.csv",
            "raw_trade_score",
        ),
        (
            "mp",
            ROOT / "result/regression_2019/mp_cost_2019_matched.csv",
            "raw_mp_score",
        ),
    ]:
        output = pd.read_csv(path, low_memory=False)
        output_fields = [
            "agreement_applicable",
            "trade_agreement_dummy",
            "idealpoint_abs_distance",
            "num_active_agreements",
            "dta_match_status",
            score_column,
        ]
        unique_output = output[pair_keys + output_fields].drop_duplicates(
            pair_keys
        )
        merged = unique_output.merge(
            pair_source[pair_keys + source_fields],
            on=pair_keys,
            how="outer",
            suffixes=("_output", "_source"),
            validate="one_to_one",
            indicator=True,
        )
        mismatches = 0
        for column in [
            "agreement_applicable",
            "trade_agreement_dummy",
            "idealpoint_abs_distance",
            "num_active_agreements",
            score_column,
        ]:
            mismatches += int(
                (
                    ~numeric_equal(
                        merged[f"{column}_output"],
                        merged[f"{column}_source"],
                    )
                ).sum()
            )
        mismatches += int(
            (
                ~text_equal(
                    merged["dta_match_status_output"],
                    merged["dta_match_status_source"],
                )
            ).sum()
        )
        wrong_score = (
            "raw_mp_score"
            if score_column == "raw_trade_score"
            else "raw_trade_score"
        )
        unequal = ~np.isclose(
            merged[f"{score_column}_source"],
            merged[wrong_score],
            atol=1e-9,
            rtol=0,
            equal_nan=True,
        )
        wrong_score_hits = (
            numeric_equal(
                merged[f"{score_column}_output"], merged[wrong_score]
            )
            & unequal
        )
        rows.append(
            {
                "equation": equation,
                "source_pair_rows": len(pair_source),
                "output_unique_pairs": len(unique_output),
                "unmatched_pair_keys": int(
                    merged["_merge"].ne("both").sum()
                ),
                "control_or_score_mismatches": mismatches,
                "pairs_where_trade_and_mp_scores_differ": int(
                    unequal.sum()
                ),
                "rows_using_wrong_score_column": int(
                    wrong_score_hits.sum()
                ),
                "matched_dta_not_one": int(
                    output["matched_dta"].ne(1).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def audit_tariffs() -> pd.DataFrame:
    trade = pd.read_csv(
        ROOT / "result/regression_2019/trade_cost_2019_matched.csv",
        low_memory=False,
    )
    tariff = pd.read_csv(
        ROOT / "control__variable/tariff_2019.csv", low_memory=False
    ).rename(columns={"iso_o": "iso_o1", "iso_d": "iso_d1"})
    keys = ["iso_o1", "iso_d1", "sector_amne"]
    merged = trade[keys + ["tariff", "matched_tariff"]].merge(
        tariff,
        on=keys,
        how="left",
        suffixes=("_output", "_source"),
        validate="many_to_one",
        indicator=True,
    )
    reverse = tariff.rename(
        columns={
            "iso_o1": "iso_d1",
            "iso_d1": "iso_o1",
            "tariff": "tariff_reverse",
        }
    )
    merged = merged.merge(
        reverse, on=keys, how="left", validate="many_to_one"
    )
    informative = (
        merged["tariff_source"].notna()
        & merged["tariff_reverse"].notna()
        & ~np.isclose(
            merged["tariff_source"],
            merged["tariff_reverse"],
            atol=1e-12,
            rtol=0,
            equal_nan=True,
        )
    )
    intended_match = numeric_equal(
        merged["tariff_output"], merged["tariff_source"], atol=1e-12
    )
    expected_flag = merged["_merge"].eq("both").astype(int)
    return pd.DataFrame(
        [
            {
                "source_rows": len(tariff),
                "source_key_duplicates": int(tariff.duplicated(keys).sum()),
                "matched_output_rows": int(merged["_merge"].eq("both").sum()),
                "unmatched_output_rows": int(
                    merged["_merge"].eq("left_only").sum()
                ),
                "unmatched_sectors": ",".join(
                    map(
                        str,
                        sorted(
                            merged.loc[
                                merged["_merge"].eq("left_only"),
                                "sector_amne",
                            ].unique()
                        ),
                    )
                ),
                "tariff_value_mismatches": int(
                    (~intended_match).sum()
                ),
                "matched_tariff_flag_mismatches": int(
                    (
                        merged["matched_tariff"].to_numpy()
                        != expected_flag.to_numpy()
                    ).sum()
                ),
                "direction_informative_rows": int(informative.sum()),
            }
        ]
    )


def load_gravity_2019(trade: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    match_codes = set(trade["iso_o_match"]) | set(trade["iso_d_match"])
    columns = [
        "year",
        "iso3_o",
        "iso3_d",
        "country_exists_o",
        "country_exists_d",
        "comlang_off",
        "comlang_ethno",
        "comrelig",
        "scaled_sci_2021",
        "entry_cost_o",
        "entry_cost_d",
        "entry_proc_o",
        "entry_proc_d",
        "entry_time_o",
        "entry_time_d",
        "entry_tp_o",
        "entry_tp_d",
    ]
    parts: list[pd.DataFrame] = []
    scanned_rows = 0
    for chunk in pd.read_csv(
        ROOT / "control__variable/Gravity_V202211.csv",
        usecols=columns,
        chunksize=250_000,
        low_memory=False,
    ):
        scanned_rows += len(chunk)
        selected = chunk.loc[
            chunk["year"].eq(2019)
            & chunk["country_exists_o"].eq(1)
            & chunk["country_exists_d"].eq(1)
            & chunk["iso3_o"].isin(match_codes)
            & chunk["iso3_d"].isin(match_codes)
        ]
        if not selected.empty:
            parts.append(selected)
    gravity = pd.concat(parts, ignore_index=True).rename(
        columns={"iso3_o": "iso_o_match", "iso3_d": "iso_d_match"}
    )
    return gravity, scanned_rows


def audit_gravity() -> tuple[pd.DataFrame, pd.DataFrame]:
    trade = pd.read_csv(
        ROOT / "result/regression_2019/trade_cost_2019_matched.csv",
        low_memory=False,
    )
    gravity, scanned_rows = load_gravity_2019(trade)
    keys = ["iso_o_match", "iso_d_match", "year"]
    source_fields = [
        "comlang_off",
        "comlang_ethno",
        "comrelig",
        "scaled_sci_2021",
        "entry_cost_o",
        "entry_cost_d",
        "entry_proc_o",
        "entry_proc_d",
        "entry_time_o",
        "entry_time_d",
        "entry_tp_o",
        "entry_tp_d",
    ]
    output_fields = [
        "comlang_off",
        "comlang_ethno",
        "cultural_proximity_religion",
        "cultural_distance_religion",
        "scaled_sci_2021",
        "ln_scaled_sci_2021",
        "entry_cost_o",
        "entry_cost_d",
        "entry_proc_o",
        "entry_proc_d",
        "entry_time_o",
        "entry_time_d",
        "entry_tp_o",
        "entry_tp_d",
        "entry_tp_bilateral_mean",
        "matched_gravity",
    ]
    unique_output = trade[keys + output_fields].drop_duplicates(keys)
    merged = unique_output.merge(
        gravity[keys + source_fields],
        on=keys,
        how="outer",
        suffixes=("_output", "_source"),
        validate="one_to_one",
        indicator=True,
    )

    def column(name: str, side: str) -> pd.Series:
        return merged_column(merged, name, side)

    mapping = {
        "comlang_off": "comlang_off",
        "comlang_ethno": "comlang_ethno",
        "cultural_proximity_religion": "comrelig",
        "scaled_sci_2021": "scaled_sci_2021",
        "entry_cost_o": "entry_cost_o",
        "entry_cost_d": "entry_cost_d",
        "entry_proc_o": "entry_proc_o",
        "entry_proc_d": "entry_proc_d",
        "entry_time_o": "entry_time_o",
        "entry_time_d": "entry_time_d",
        "entry_tp_o": "entry_tp_o",
        "entry_tp_d": "entry_tp_d",
    }
    value_mismatches = 0
    for output_name, source_name in mapping.items():
        value_mismatches += int(
            (
                ~numeric_equal(
                    column(output_name, "output"),
                    column(source_name, "source"),
                )
            ).sum()
        )
    religious_proximity = pd.to_numeric(
        column("comrelig", "source"), errors="coerce"
    )
    value_mismatches += int(
        (
            ~numeric_equal(
                column("cultural_distance_religion", "output"),
                1.0 - religious_proximity,
            )
        ).sum()
    )
    sci = pd.to_numeric(
        column("scaled_sci_2021", "source"), errors="coerce"
    )
    expected_log_sci = pd.Series(
        np.where(sci.gt(0), np.log(sci), np.nan), index=merged.index
    )
    value_mismatches += int(
        (
            ~numeric_equal(
                column("ln_scaled_sci_2021", "output"),
                expected_log_sci,
            )
        ).sum()
    )
    entry_tp_o = pd.to_numeric(
        column("entry_tp_o", "source"), errors="coerce"
    )
    entry_tp_d = pd.to_numeric(
        column("entry_tp_d", "source"), errors="coerce"
    )
    expected_entry_mean = pd.Series(
        np.where(
            entry_tp_o.notna() & entry_tp_d.notna(),
            (entry_tp_o + entry_tp_d) / 2.0,
            np.nan,
        ),
        index=merged.index,
    )
    value_mismatches += int(
        (
            ~numeric_equal(
                column("entry_tp_bilateral_mean", "output"),
                expected_entry_mean,
            )
        ).sum()
    )

    direction_rows: list[dict[str, Any]] = []
    for base in ["entry_cost", "entry_proc", "entry_time", "entry_tp"]:
        source_o = pd.to_numeric(
            column(f"{base}_o", "source"), errors="coerce"
        )
        source_d = pd.to_numeric(
            column(f"{base}_d", "source"), errors="coerce"
        )
        output_o = pd.to_numeric(
            column(f"{base}_o", "output"), errors="coerce"
        )
        output_d = pd.to_numeric(
            column(f"{base}_d", "output"), errors="coerce"
        )
        informative = (
            source_o.notna()
            & source_d.notna()
            & ~np.isclose(source_o, source_d, equal_nan=True)
        )
        swapped = (
            informative
            & np.isclose(output_o, source_d, equal_nan=True)
            & np.isclose(output_d, source_o, equal_nan=True)
            & ~(
                np.isclose(output_o, source_o, equal_nan=True)
                & np.isclose(output_d, source_d, equal_nan=True)
            )
        )
        direction_rows.append(
            {
                "variable_family": base,
                "direction_informative_pairs": int(informative.sum()),
                "pairs_fitting_o_d_swap": int(swapped.sum()),
            }
        )

    summary = pd.DataFrame(
        [
            {
                "gravity_rows_scanned": scanned_rows,
                "selected_2019_pairs": len(gravity),
                "selected_pair_key_duplicates": int(
                    gravity.duplicated(keys).sum()
                ),
                "output_unique_pairs": len(unique_output),
                "unmatched_pair_keys": int(
                    merged["_merge"].ne("both").sum()
                ),
                "gravity_or_derived_value_mismatches": value_mismatches,
                "matched_gravity_flag_mismatches": int(
                    column("matched_gravity", "output").ne(1).sum()
                ),
            }
        ]
    )
    return summary, pd.DataFrame(direction_rows)


def audit_sample_flags() -> pd.DataFrame:
    trade = pd.read_csv(
        ROOT / "result/regression_2019/trade_cost_2019_matched.csv",
        low_memory=False,
    )
    mp = pd.read_csv(
        ROOT / "result/regression_2019/mp_cost_2019_matched.csv",
        low_memory=False,
    )
    trade_required = [
        "raw_trade_score",
        "tariff",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "comlang_off",
        "cultural_distance_religion",
    ]
    trade_main = trade[trade_required].notna().all(axis=1).astype(int)
    trade_international = (
        trade_main.eq(1) & trade["is_domestic_pair"].eq(0)
    ).astype(int)
    trade_entry = (
        trade_main.eq(1)
        & trade[["entry_time_o", "entry_time_d"]].notna().all(axis=1)
    ).astype(int)

    mp_required = [
        "raw_mp_score",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
    ]
    mp_main = mp[mp_required].notna().all(axis=1).astype(int)
    mp_international = (
        mp_main.eq(1) & mp["is_domestic_pair"].eq(0)
    ).astype(int)
    return pd.DataFrame(
        [
            {
                "flag": "sample_trade_main",
                "rows_equal_one": int(trade_main.sum()),
                "recalculation_mismatches": int(
                    (trade["sample_trade_main"] != trade_main).sum()
                ),
                "required_columns": ", ".join(trade_required),
            },
            {
                "flag": "sample_trade_main_international",
                "rows_equal_one": int(trade_international.sum()),
                "recalculation_mismatches": int(
                    (
                        trade["sample_trade_main_international"]
                        != trade_international
                    ).sum()
                ),
                "required_columns": "sample_trade_main, international only",
            },
            {
                "flag": "sample_trade_entry_robustness",
                "rows_equal_one": int(trade_entry.sum()),
                "recalculation_mismatches": int(
                    (
                        trade["sample_trade_entry_robustness"]
                        != trade_entry
                    ).sum()
                ),
                "required_columns": (
                    "sample_trade_main, entry_time_o, entry_time_d"
                ),
            },
            {
                "flag": "sample_mp_main",
                "rows_equal_one": int(mp_main.sum()),
                "recalculation_mismatches": int(
                    (mp["sample_mp_main"] != mp_main).sum()
                ),
                "required_columns": ", ".join(mp_required),
            },
            {
                "flag": "sample_mp_main_international",
                "rows_equal_one": int(mp_international.sum()),
                "recalculation_mismatches": int(
                    (
                        mp["sample_mp_main_international"]
                        != mp_international
                    ).sum()
                ),
                "required_columns": "sample_mp_main, international only",
            },
        ]
    )


def audit_known_quality_risks() -> pd.DataFrame:
    weights = pd.read_csv(
        ROOT / "data/processed/final_provision_weights.csv",
        low_memory=False,
    )
    formula_error = (
        weights["provision_text"].fillna("").astype(str).str.strip().eq("#NAME?")
    )
    nonzero_formula_error = (
        weights.loc[
            formula_error,
            ["effective_trade_weight", "effective_mp_weight"],
        ]
        .sum(axis=1)
        .gt(0)
    )
    return pd.DataFrame(
        [
            {
                "severity": "Medium",
                "finding": (
                    "Current sample_trade_main does not implement the newly "
                    "stated trade-facilitation + cultural-proximity main "
                    "specification."
                ),
                "evidence": (
                    "It requires comlang_off and "
                    "cultural_distance_religion, but no entry_* variable."
                ),
            },
            {
                "severity": "Medium",
                "finding": (
                    "Some source provision texts contain spreadsheet formula "
                    "errors."
                ),
                "evidence": (
                    f"{int(formula_error.sum())} provisions have #NAME? text; "
                    f"{int(nonzero_formula_error.sum())} receive non-zero "
                    "trade or MP weight."
                ),
            },
            {
                "severity": "Low",
                "finding": (
                    "The trade CSV uses shortest float32 round-trip text, so "
                    "displayed decimal values are not bit-for-bit equal when "
                    "read as float64."
                ),
                "evidence": (
                    "The .dta output is exactly equal to the source and the "
                    "CSV has zero mismatches after float32 round-trip."
                ),
            },
            {
                "severity": "Methodological caveat",
                "finding": (
                    "The figures write ln(X) and ln(MP), while the delivered "
                    "value fields remain in levels and include zeros."
                ),
                "evidence": (
                    "A literal log-OLS implementation would discard zero "
                    "flows; PPML in levels avoids this loss."
                ),
            },
        ]
    )


def run_all() -> dict[str, pd.DataFrame]:
    migration, category_counts = audit_migration()
    gravity_summary, gravity_direction = audit_gravity()
    return {
        "migration": migration,
        "category_counts": category_counts,
        "weight_rules": audit_final_weight_rules(),
        "score_recalculation": audit_recomputed_scores(),
        "dependent_variables": audit_dependent_variables(),
        "pair_controls": audit_pair_controls(),
        "tariffs": audit_tariffs(),
        "gravity": gravity_summary,
        "gravity_direction": gravity_direction,
        "sample_flags": audit_sample_flags(),
        "quality_risks": audit_known_quality_risks(),
    }


if __name__ == "__main__":
    for name, table in run_all().items():
        print(f"\n## {name}")
        print(table.to_string(index=True))
