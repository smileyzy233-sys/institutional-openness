"""Build auditable 2019 regression inputs for the trade- and MP-cost equations.

The script removes ROW observations as requested, adds source match flags, and
creates explicit recommended-sample flags without imputing structural gaps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import nbformat as nbf
import numpy as np
import pandas as pd


YEAR = 2019
ISO_BRIDGE = {"ROM": "ROU"}

GRAVITY_COLUMNS = [
    "year",
    "country_id_o",
    "country_id_d",
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

PAIR_DTA_COLUMNS = [
    "iso_o",
    "iso_d",
    "year",
    "agreement_applicable",
    "trade_agreement_dummy",
    "raw_trade_score",
    "raw_mp_score",
    "num_active_agreements",
    "match_status",
    "idealpoint_abs_distance",
]


def project_directory() -> Path:
    return Path(__file__).resolve().parents[1]


def output_directory(project_dir: Path) -> Path:
    return project_dir / "result" / "regression_2019"


def normalize_iso(series: pd.Series) -> pd.Series:
    return series.replace(ISO_BRIDGE)


def validate_unique(data: pd.DataFrame, keys: list[str], source: str) -> None:
    duplicates = int(data.duplicated(keys).sum())
    if duplicates:
        examples = data.loc[data.duplicated(keys, keep=False), keys].head(10)
        raise ValueError(
            f"{source} is not unique on {keys}; duplicates={duplicates}; "
            f"examples={examples.to_dict('records')}"
        )


def load_dependent_variable(path: Path) -> pd.DataFrame:
    data = pd.read_stata(path, convert_categoricals=False)
    required = {
        "iso_o",
        "iso_d",
        "sector_amne",
        "value",
        "country_o",
        "country_d",
        "iso_o1",
        "iso_d1",
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    validate_unique(data, ["iso_o", "iso_d", "sector_amne"], path.name)
    if data["value"].isna().any() or (data["value"] < 0).any():
        raise ValueError(f"{path.name} has null or negative dependent values")

    data = data.copy()
    data.insert(0, "year", YEAR)
    data["iso_o_match"] = normalize_iso(data["iso_o"])
    data["iso_d_match"] = normalize_iso(data["iso_d"])
    data["iso_o1"] = data["iso_o1"].astype(np.int16)
    data["iso_d1"] = data["iso_d1"].astype(np.int16)
    data["sector_amne"] = data["sector_amne"].astype(np.int16)
    data["positive_value"] = data["value"].gt(0).astype(np.int8)
    data["is_domestic_pair"] = data["iso_o"].eq(data["iso_d"]).astype(np.int8)
    data["is_row_pair"] = (
        data["iso_o"].eq("ROW") | data["iso_d"].eq("ROW")
    ).astype(np.int8)
    data = data.loc[data["is_row_pair"].eq(0)].copy()
    return data.reset_index(drop=True)


def load_dta_pair_controls(project_dir: Path) -> pd.DataFrame:
    path = (
        project_dir
        / "data"
        / "processed"
        / "trade_dummy_icio_2000_2023.csv"
    )
    data = pd.read_csv(path, usecols=PAIR_DTA_COLUMNS, low_memory=False)
    data = data.loc[data["year"].eq(YEAR)].copy()
    validate_unique(data, ["iso_o", "iso_d", "year"], path.name)

    data = data.rename(
        columns={
            "iso_o": "iso_o_match",
            "iso_d": "iso_d_match",
            "match_status": "dta_match_status",
        }
    )
    data["matched_dta"] = np.int8(1)
    return data


def load_gravity_pair_controls(
    project_dir: Path, required_iso_codes: set[str]
) -> pd.DataFrame:
    path = project_dir / "control__variable" / "Gravity_V202211.csv"
    match_codes = {ISO_BRIDGE.get(code, code) for code in required_iso_codes}

    parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        usecols=GRAVITY_COLUMNS,
        chunksize=200_000,
        low_memory=False,
    ):
        selected = chunk.loc[
            chunk["year"].eq(YEAR)
            & chunk["country_exists_o"].eq(1)
            & chunk["country_exists_d"].eq(1)
            & chunk["iso3_o"].isin(match_codes)
            & chunk["iso3_d"].isin(match_codes)
        ]
        if not selected.empty:
            parts.append(selected)

    if not parts:
        raise ValueError("No 2019 Gravity rows matched the requested economies")

    data = pd.concat(parts, ignore_index=True)
    data = data.rename(
        columns={"iso3_o": "iso_o_match", "iso3_d": "iso_d_match"}
    )
    validate_unique(
        data, ["iso_o_match", "iso_d_match", "year"], "Gravity 2019 existing countries"
    )

    expected = len(match_codes) ** 2
    if len(data) != expected:
        observed_pairs = set(zip(data["iso_o_match"], data["iso_d_match"]))
        expected_pairs = {(o, d) for o in match_codes for d in match_codes}
        missing = sorted(expected_pairs.difference(observed_pairs))[:20]
        raise ValueError(
            f"Gravity 2019 does not form a square matrix: expected={expected}, "
            f"observed={len(data)}, missing_examples={missing}"
        )

    keep = [
        "iso_o_match",
        "iso_d_match",
        "year",
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
    data = data[keep].copy()
    data["matched_gravity"] = np.int8(1)
    data["cultural_proximity_religion"] = data["comrelig"]
    data["cultural_distance_religion"] = 1.0 - data["comrelig"]
    data["ln_scaled_sci_2021"] = np.where(
        data["scaled_sci_2021"].gt(0),
        np.log(data["scaled_sci_2021"]),
        np.nan,
    )
    both_entry_tp = data[["entry_tp_o", "entry_tp_d"]].notna().all(axis=1)
    data["entry_tp_bilateral_mean"] = np.where(
        both_entry_tp,
        (data["entry_tp_o"] + data["entry_tp_d"]) / 2.0,
        np.nan,
    )
    return data


def build_pair_controls(
    project_dir: Path, dependent_iso_codes: set[str]
) -> pd.DataFrame:
    dta = load_dta_pair_controls(project_dir)
    gravity = load_gravity_pair_controls(
        project_dir, dependent_iso_codes.difference({"ROW"})
    )
    pair = dta.merge(
        gravity,
        on=["iso_o_match", "iso_d_match", "year"],
        how="outer",
        validate="one_to_one",
        indicator="_pair_merge",
    )
    if not pair["_pair_merge"].eq("both").all():
        counts = pair["_pair_merge"].value_counts().to_dict()
        raise ValueError(f"DTA/Gravity pair controls disagree on country coverage: {counts}")
    return pair.drop(columns="_pair_merge")


def load_tariffs(project_dir: Path) -> pd.DataFrame:
    path = project_dir / "control__variable" / "tariff_2019.csv"
    tariff = pd.read_csv(path)
    tariff = tariff.rename(
        columns={"iso_o": "iso_o1", "iso_d": "iso_d1"}
    )
    keys = ["iso_o1", "iso_d1", "sector_amne"]
    validate_unique(tariff, keys, path.name)
    if tariff["tariff"].isna().any() or (tariff["tariff"] < 0).any():
        raise ValueError("tariff_2019.csv contains null or negative tariff values")
    tariff["matched_tariff"] = np.int8(1)
    return tariff


def merge_pair_controls(
    dependent: pd.DataFrame, pair_controls: pd.DataFrame
) -> pd.DataFrame:
    before = len(dependent)
    merged = dependent.merge(
        pair_controls,
        on=["iso_o_match", "iso_d_match", "year"],
        how="left",
        validate="many_to_one",
    )
    if len(merged) != before:
        raise AssertionError("Pair-control merge expanded or contracted the dependent data")
    merged["matched_dta"] = merged["matched_dta"].fillna(0).astype(np.int8)
    merged["matched_gravity"] = (
        merged["matched_gravity"].fillna(0).astype(np.int8)
    )
    return merged


def build_trade_data(
    project_dir: Path, pair_controls: pd.DataFrame
) -> pd.DataFrame:
    source = project_dir / "Explained_variable" / "icio2019.dta"
    trade = load_dependent_variable(source)
    tariff = load_tariffs(project_dir)
    before = len(trade)
    trade = trade.merge(
        tariff,
        on=["iso_o1", "iso_d1", "sector_amne"],
        how="left",
        validate="many_to_one",
    )
    if len(trade) != before:
        raise AssertionError("Tariff merge expanded or contracted ICIO")
    trade["matched_tariff"] = trade["matched_tariff"].fillna(0).astype(np.int8)
    trade = merge_pair_controls(trade, pair_controls)

    main_required = [
        "raw_trade_score",
        "tariff",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "comlang_off",
        "cultural_distance_religion",
    ]
    main_complete = trade[main_required].notna().all(axis=1)
    trade["sample_trade_main"] = (
        trade["is_row_pair"].eq(0) & main_complete
    ).astype(np.int8)
    trade["sample_trade_main_international"] = (
        trade["sample_trade_main"].eq(1)
        & trade["is_domestic_pair"].eq(0)
    ).astype(np.int8)
    trade["sample_trade_entry_robustness"] = (
        trade["sample_trade_main"].eq(1)
        & trade[["entry_time_o", "entry_time_d"]].notna().all(axis=1)
    ).astype(np.int8)
    trade["uses_iso_bridge"] = (
        trade["iso_o"].ne(trade["iso_o_match"])
        | trade["iso_d"].ne(trade["iso_d_match"])
    ).astype(np.int8)

    columns = [
        "year",
        "iso_o",
        "iso_d",
        "iso_o_match",
        "iso_d_match",
        "country_o",
        "country_d",
        "iso_o1",
        "iso_d1",
        "sector_amne",
        "value",
        "positive_value",
        "is_domestic_pair",
        "is_row_pair",
        "raw_trade_score",
        "tariff",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "comlang_off",
        "cultural_proximity_religion",
        "cultural_distance_religion",
        "comlang_ethno",
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
        "agreement_applicable",
        "num_active_agreements",
        "dta_match_status",
        "matched_dta",
        "matched_tariff",
        "matched_gravity",
        "uses_iso_bridge",
        "sample_trade_main",
        "sample_trade_main_international",
        "sample_trade_entry_robustness",
    ]
    return trade[columns]


def build_mp_data(
    project_dir: Path, pair_controls: pd.DataFrame
) -> pd.DataFrame:
    source = project_dir / "Explained_variable" / "amne2019.dta"
    mp = load_dependent_variable(source)
    mp = merge_pair_controls(mp, pair_controls)

    main_required = [
        "raw_mp_score",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
    ]
    main_complete = mp[main_required].notna().all(axis=1)
    mp["sample_mp_main"] = (
        mp["is_row_pair"].eq(0) & main_complete
    ).astype(np.int8)
    mp["sample_mp_main_international"] = (
        mp["sample_mp_main"].eq(1) & mp["is_domestic_pair"].eq(0)
    ).astype(np.int8)
    mp["uses_iso_bridge"] = (
        mp["iso_o"].ne(mp["iso_o_match"])
        | mp["iso_d"].ne(mp["iso_d_match"])
    ).astype(np.int8)

    columns = [
        "year",
        "iso_o",
        "iso_d",
        "iso_o_match",
        "iso_d_match",
        "country_o",
        "country_d",
        "iso_o1",
        "iso_d1",
        "sector_amne",
        "value",
        "positive_value",
        "is_domestic_pair",
        "is_row_pair",
        "raw_mp_score",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
        "agreement_applicable",
        "num_active_agreements",
        "dta_match_status",
        "matched_dta",
        "uses_iso_bridge",
        "sample_mp_main",
        "sample_mp_main_international",
    ]
    return mp[columns]


def stata_variable_labels() -> dict[str, str]:
    return {
        "year": "Observation year",
        "iso_o": "Original origin ISO3 code",
        "iso_d": "Original destination ISO3 code",
        "iso_o_match": "Normalized origin ISO3 merge code",
        "iso_d_match": "Normalized destination ISO3 merge code",
        "country_o": "Origin country name",
        "country_d": "Destination country name",
        "iso_o1": "ICIO/AMNE origin numeric code",
        "iso_d1": "ICIO/AMNE destination numeric code",
        "sector_amne": "Sector code in source dependent-variable file",
        "value": "Dependent variable in levels",
        "positive_value": "1 if dependent value is strictly positive",
        "is_domestic_pair": "1 if origin equals destination",
        "is_row_pair": "1 if origin or destination is ROW",
        "raw_trade_score": "DTA trade-provision depth score",
        "raw_mp_score": "DTA investment-provision depth score",
        "tariff": "2019 bilateral sector tariff",
        "trade_agreement_dummy": "1 if a DTA is active in 2019",
        "idealpoint_abs_distance": "Absolute UN ideal-point distance in 2019",
        "comlang_off": "1 if common official or primary language",
        "comlang_ethno": "1 if common language spoken by at least 9 percent",
        "cultural_proximity_religion": "CEPII religious proximity index",
        "cultural_distance_religion": "1 minus CEPII religious proximity",
        "scaled_sci_2021": "CEPII 2021 Social Connectedness Index",
        "ln_scaled_sci_2021": "Natural log of positive 2021 SCI",
        "entry_cost_o": "Origin business start-up cost percent of GNI pc",
        "entry_cost_d": "Destination business start-up cost percent of GNI pc",
        "entry_proc_o": "Origin number of start-up procedures",
        "entry_proc_d": "Destination number of start-up procedures",
        "entry_time_o": "Origin days required to start a business",
        "entry_time_d": "Destination days required to start a business",
        "entry_tp_o": "Origin start-up days plus procedures",
        "entry_tp_d": "Destination start-up days plus procedures",
        "entry_tp_bilateral_mean": "Mean of origin and destination entry_tp",
        "matched_dta": "1 if DTA/political pair controls matched",
        "matched_tariff": "1 if sector tariff matched",
        "matched_gravity": "1 if CEPII Gravity controls matched",
        "uses_iso_bridge": "1 if ROM to ROU bridge was used",
        "sample_trade_main": "Recommended trade sample, domestic included",
        "sample_trade_main_international": "Recommended trade sample, international only",
        "sample_trade_entry_robustness": "Trade sample also complete on entry barriers",
        "sample_mp_main": "Recommended MP sample, domestic included",
        "sample_mp_main_international": "Recommended MP sample, international only",
    }


def write_data_files(data: pd.DataFrame, stem: Path) -> None:
    data.to_csv(stem.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    labels = {
        column: label
        for column, label in stata_variable_labels().items()
        if column in data.columns
    }
    data.to_stata(
        stem.with_suffix(".dta"),
        write_index=False,
        version=118,
        variable_labels=labels,
    )


def diagnostic_row(
    dataset: str,
    check: str,
    value: float,
    rate: float | None,
    severity: str,
    note: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "check": check,
        "value": value,
        "rate": rate,
        "severity": severity,
        "note": note,
    }


def build_diagnostics(
    trade: pd.DataFrame, mp: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for name, data, key in [
        ("trade", trade, ["iso_o", "iso_d", "sector_amne"]),
        ("mp", mp, ["iso_o", "iso_d", "sector_amne"]),
    ]:
        rows.extend(
            [
                diagnostic_row(
                    name,
                    "rows",
                    len(data),
                    1.0,
                    "info",
                    "Source rows retained after removing all ROW observations",
                ),
                diagnostic_row(
                    name,
                    "duplicate_source_keys",
                    int(data.duplicated(key).sum()),
                    float(data.duplicated(key).mean()),
                    "critical",
                    "Expected zero",
                ),
                diagnostic_row(
                    name,
                    "zero_dependent_values",
                    int(data["value"].eq(0).sum()),
                    float(data["value"].eq(0).mean()),
                    "high",
                    "Use PPML on value levels; log OLS would discard these rows",
                ),
                diagnostic_row(
                    name,
                    "row_pairs",
                    int(data["is_row_pair"].sum()),
                    float(data["is_row_pair"].mean()),
                    "info",
                    "Expected zero: all ROW observations were removed by request",
                ),
                diagnostic_row(
                    name,
                    "dta_matched",
                    int(data["matched_dta"].sum()),
                    float(data["matched_dta"].mean()),
                    "info",
                    "ROM is matched through the explicit ROU bridge",
                ),
                diagnostic_row(
                    name,
                    "idealpoint_missing",
                    int(data["idealpoint_abs_distance"].isna().sum()),
                    float(data["idealpoint_abs_distance"].isna().mean()),
                    "high",
                    "2019 political distance is unavailable for HKG/TWN international pairs",
                ),
                diagnostic_row(
                    name,
                    "iso_bridge_rows",
                    int(data["uses_iso_bridge"].sum()),
                    float(data["uses_iso_bridge"].mean()),
                    "info",
                    "Original ROM is retained; ROU is used only as the merge code",
                ),
            ]
        )

    rows.extend(
        [
            diagnostic_row(
                "trade",
                "tariff_matched",
                int(trade["matched_tariff"].sum()),
                float(trade["matched_tariff"].mean()),
                "high",
                "Tariffs cover sectors 1-19; sector 20 is structurally missing",
            ),
            diagnostic_row(
                "trade",
                "gravity_matched",
                int(trade["matched_gravity"].sum()),
                float(trade["matched_gravity"].mean()),
                "info",
                "All 76 non-ROW economies matched after filtering existing countries",
            ),
            diagnostic_row(
                "trade",
                "comrelig_missing",
                int(trade["cultural_proximity_religion"].isna().sum()),
                float(trade["cultural_proximity_religion"].isna().mean()),
                "medium",
                "CEPII religious proximity is unavailable for pairs involving LTU",
            ),
            diagnostic_row(
                "trade",
                "scaled_sci_2021_missing",
                int(trade["scaled_sci_2021"].isna().sum()),
                float(trade["scaled_sci_2021"].isna().mean()),
                "medium",
                "SCI is unavailable for pairs involving CHN, ISR, or RUS; robustness only",
            ),
            diagnostic_row(
                "trade",
                "sample_trade_main",
                int(trade["sample_trade_main"].sum()),
                float(trade["sample_trade_main"].mean()),
                "info",
                "Complete main variables; domestic pairs retained",
            ),
            diagnostic_row(
                "trade",
                "sample_trade_main_international",
                int(trade["sample_trade_main_international"].sum()),
                float(trade["sample_trade_main_international"].mean()),
                "info",
                "Complete main variables; domestic pairs excluded",
            ),
            diagnostic_row(
                "mp",
                "sample_mp_main",
                int(mp["sample_mp_main"].sum()),
                float(mp["sample_mp_main"].mean()),
                "info",
                "Complete main MP variables; domestic pairs retained",
            ),
            diagnostic_row(
                "mp",
                "sample_mp_main_international",
                int(mp["sample_mp_main_international"].sum()),
                float(mp["sample_mp_main_international"].mean()),
                "info",
                "Complete main MP variables; domestic pairs excluded",
            ),
        ]
    )
    return pd.DataFrame(rows)


def build_variable_selection(pair_controls: pd.DataFrame) -> pd.DataFrame:
    def coverage(columns: list[str]) -> float:
        return float(pair_controls[columns].notna().all(axis=1).mean())

    rows = [
        {
            "equation": "trade",
            "role": "explained variable",
            "selected": "value",
            "source": "icio2019.dta",
            "transformation": "none; estimate PPML in levels",
            "pair_coverage_2019": 1.0,
            "status": "main",
            "rationale": "Preserves zero bilateral-sector trade flows.",
        },
        {
            "equation": "trade",
            "role": "DTA depth",
            "selected": "raw_trade_score",
            "source": "trade_dummy_icio_2000_2023.csv",
            "transformation": "none",
            "pair_coverage_2019": coverage(["raw_trade_score"]),
            "status": "main",
            "rationale": "Trade-related provision depth requested by the research design.",
        },
        {
            "equation": "trade",
            "role": "common language",
            "selected": "comlang_off",
            "source": "CEPII Gravity_V202211",
            "transformation": "none",
            "pair_coverage_2019": coverage(["comlang_off"]),
            "status": "main",
            "rationale": "Narrow and interpretable common official/primary-language dummy.",
        },
        {
            "equation": "trade",
            "role": "cultural distance",
            "selected": "cultural_distance_religion",
            "source": "CEPII comrelig",
            "transformation": "1 - comrelig",
            "pair_coverage_2019": coverage(["comrelig"]),
            "status": "main",
            "rationale": "Continuous bilateral cultural-proximity proxy with intuitive distance sign.",
        },
        {
            "equation": "trade",
            "role": "social/cultural robustness",
            "selected": "ln_scaled_sci_2021",
            "source": "CEPII scaled_sci_2021",
            "transformation": "natural log",
            "pair_coverage_2019": coverage(["scaled_sci_2021"]),
            "status": "robustness only",
            "rationale": "Social connectedness is not a pure cultural measure and is dated 2021.",
        },
        {
            "equation": "trade",
            "role": "business-entry facilitation",
            "selected": "entry_time_o + entry_time_d",
            "source": "CEPII/WDI",
            "transformation": "retain both directional country measures",
            "pair_coverage_2019": coverage(["entry_time_o", "entry_time_d"]),
            "status": "robustness only",
            "rationale": "Interpretable days; unilateral and absorbed by exporter-year/importer-year FE.",
        },
        {
            "equation": "mp",
            "role": "explained variable",
            "selected": "value",
            "source": "amne2019.dta",
            "transformation": "none; estimate PPML in levels",
            "pair_coverage_2019": 1.0,
            "status": "main",
            "rationale": "Preserves the large share of zero MP flows.",
        },
        {
            "equation": "mp",
            "role": "DTA depth",
            "selected": "raw_mp_score",
            "source": "trade_dummy_icio_2000_2023.csv",
            "transformation": "none",
            "pair_coverage_2019": coverage(["raw_mp_score"]),
            "status": "main",
            "rationale": "Investment-related provision depth requested by the research design.",
        },
    ]
    return pd.DataFrame(rows)


def write_readme(
    out_dir: Path,
    trade: pd.DataFrame,
    mp: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    def pct(value: float) -> str:
        return f"{100 * value:.2f}%"

    trade_zero = float(trade["value"].eq(0).mean())
    mp_zero = float(mp["value"].eq(0).mean())
    trade_sample = int(trade["sample_trade_main"].sum())
    trade_sample_intl = int(trade["sample_trade_main_international"].sum())
    mp_sample = int(mp["sample_mp_main"].sum())
    mp_sample_intl = int(mp["sample_mp_main_international"].sum())
    ideal_trade_missing = int(trade["idealpoint_abs_distance"].isna().sum())
    comrelig_missing = int(trade["cultural_proximity_religion"].isna().sum())

    text = f"""# 2019 年回归数据匹配说明

## 交付文件

- `trade_cost_2019_matched.csv/.dta`：贸易成本方程，{len(trade):,} 行。
- `mp_cost_2019_matched.csv/.dta`：跨国生产成本方程，{len(mp):,} 行。
- `matching_diagnostics_2019.csv`：匹配覆盖率、缺失与风险。
- `variable_selection_2019.csv`：主变量和稳健性变量的选择依据。
- `matching_audit_2019.ipynb`：可重新执行的审计笔记本。

## 主变量

贸易方程：

- 被解释变量：`value`（ICIO）。
- 核心解释变量：`raw_trade_score`。
- 控制变量：`tariff`、`trade_agreement_dummy`、
  `idealpoint_abs_distance`、`comlang_off`、
  `cultural_distance_religion = 1 - comrelig`。
- 推荐样本标志：`sample_trade_main`（含国内流量，{trade_sample:,} 行）；
  `sample_trade_main_international`（仅国际流量，{trade_sample_intl:,} 行）。

跨国生产方程：

- 被解释变量：`value`（AMNE）。
- 核心解释变量：`raw_mp_score`。
- 控制变量：`trade_agreement_dummy`、`idealpoint_abs_distance`。
- 推荐样本标志：`sample_mp_main`（含国内流量，{mp_sample:,} 行）；
  `sample_mp_main_international`（仅国际流量，{mp_sample_intl:,} 行）。

## 关键匹配处理

1. 原始被解释变量中的罗马尼亚代码为 `ROM`，DTA/CEPII 使用 `ROU`。
   文件保留 `iso_o`/`iso_d` 原码，同时仅用
   `iso_o_match`/`iso_d_match` 执行 `ROM → ROU` 合并。
2. CEPII Gravity 先筛选 `year == 2019` 且
   `country_exists_o == country_exists_d == 1`，以免历史领土构型导致重复。
3. 按用户要求，来源国或目的国为 `ROW` 的观察已全部删除；输出恰好保留
   76×76 的国家矩阵。
4. 关税覆盖部门 1–19，部门 20 没有关税；缺失保留，未填 0。
5. 理想点距离缺失 {ideal_trade_missing:,} 个贸易行，来自 HKG/TWN
   的国际国家对；`comrelig` 缺失 {comrelig_missing:,} 个贸易行，
   来自涉及 LTU 的国家对。均未插补。

## 变量选择判断

- `comlang_off`：共同官方或主要语言虚拟变量，定义最窄、解释最清楚，
  作为共同语言主控制；`comlang_ethno` 仅保留作替代。
- `comrelig`：0–1 的宗教接近度指数。为了和“文化距离”的文字设定一致，
  主文件同时给出 `cultural_distance_religion = 1 - comrelig`。
- `scaled_sci_2021`：2021 年社交连通度，不是纯粹文化指标且与 2019
  存在时间错位，只建议稳健性检验。
- `entry_*`：CEPII/WDI 的企业开办成本、程序和时间。如需额外的贸易便利化
  稳健性控制，优先分别使用单位清楚的 `entry_time_o` 与 `entry_time_d`；
  `entry_tp` 把天数和程序数相加，解释性较弱。它们都是单边国家变量，在
  出口国—年份和进口国—年份固定效应下会被完全吸收，因此不进入主设定。

## 估计前必须注意

- 2019 年单期数据可以完成匹配和描述性检验，但不能在加入国家对固定效应后
  识别 `raw_trade_score` 或 `raw_mp_score`；若公式中的双边效应按部门设置，
  则国家对×部门固定效应在单期内更会饱和全部观察。这些 DTA 变量在单期内只按
  国家对变化，会与相应固定效应完全共线。单期初步回归需暂不使用国家对固定效应；
  正式模型应扩展为多年面板后再加入国家对固定效应。
- ICIO 的零值占 {pct(trade_zero)}，AMNE 的零值占 {pct(mp_zero)}。
  主估计建议以原始 `value` 做 PPML；直接取对数会系统性丢弃零流量。
- `comlang_off`、`comrelig` 等不随时间变化的双边变量在多年面板的国家对固定效应下
  也会被吸收，只适合单期/无国家对固定效应设定或替代性稳健性检验。

## 数据来源说明

CEPII Gravity 官方文档：
https://www.cepii.fr/DATA_DOWNLOAD/gravity/legacy/202102/Gravity_documentation.pdf
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")

    diagnostics.to_csv(
        out_dir / "matching_diagnostics_2019.csv",
        index=False,
        encoding="utf-8-sig",
    )


def write_notebook(
    project_dir: Path,
    out_dir: Path,
    trade: pd.DataFrame,
    mp: pd.DataFrame,
) -> Path:
    notebook_path = out_dir / "matching_audit_2019.ipynb"
    script_path = project_dir / "src" / "build_regression_2019.py"
    trade_main = int(trade["sample_trade_main"].sum())
    mp_main = int(mp["sample_mp_main"].sum())
    trade_zero = float(trade["value"].eq(0).mean())
    mp_zero = float(mp["value"].eq(0).mean())

    notebook = nbf.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook["metadata"]["language_info"] = {"name": "python"}
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            f"""# 2019 年回归数据匹配审计

## tl;dr

- ICIO 保留 {len(trade):,} 行；推荐贸易主样本 {trade_main:,} 行。
- AMNE 保留 {len(mp):,} 行；推荐跨国生产主样本 {mp_main:,} 行。
- 已处理 `ROM → ROU` 合并桥接，且未把 `ROW` 或结构性缺失误填为 0。
- ICIO/AMNE 零值率分别为 {trade_zero:.2%}/{mp_zero:.2%}，建议 PPML。
- 2019 单期数据不能与国家对固定效应同时识别 DTA 深度系数。
"""
        ),
        nbf.v4.new_markdown_cell(
            """## Context & Methods

### Key Assumptions

- `iso_o` 为来源/出口国，`iso_d` 为目的/进口国。
- DTA 与理想点距离来自同一份 2019 国家对数据。
- CEPII Gravity 只保留 2019 年实际存在的国家构型。
- 除按要求删除 `ROW` 外不再删行；可用样本由显式标志给出。
"""
        ),
        nbf.v4.new_code_cell(
            f"""from pathlib import Path
import sys
import pandas as pd

PROJECT_DIR = Path(r"{project_dir}")
SCRIPT_PATH = Path(r"{script_path}")
sys.path.insert(0, str(SCRIPT_PATH.parent))

from build_regression_2019 import build_all

result = build_all(
    project_dir=PROJECT_DIR,
    write_notebook_file=False,
)
result["summary"]
"""
        ),
        nbf.v4.new_markdown_cell("## Data"),
        nbf.v4.new_code_cell(
            """trade = pd.read_stata(result["trade_dta"], convert_categoricals=False)
mp = pd.read_stata(result["mp_dta"], convert_categoricals=False)

display(trade.head(5))
display(mp.head(5))
"""
        ),
        nbf.v4.new_markdown_cell("## Results"),
        nbf.v4.new_code_cell(
            """diagnostics = pd.read_csv(result["diagnostics_csv"])
selection = pd.read_csv(result["selection_csv"])

display(diagnostics)
display(selection)
"""
        ),
        nbf.v4.new_code_cell(
            """assert trade.duplicated(["iso_o", "iso_d", "sector_amne"]).sum() == 0
assert mp.duplicated(["iso_o", "iso_d", "sector_amne"]).sum() == 0
assert len(trade) == 76 * 76 * 20
assert len(mp) == 76 * 76 * 41
assert not trade[["iso_o", "iso_d"]].isin(["ROW"]).any().any()
assert not mp[["iso_o", "iso_d"]].isin(["ROW"]).any().any()
assert trade["matched_dta"].eq(1).all()
assert trade["matched_gravity"].eq(1).all()
assert mp["matched_dta"].eq(1).all()
assert trade.loc[trade["matched_tariff"].eq(0), "sector_amne"].eq(20).all()
assert trade.loc[trade["uses_iso_bridge"].eq(1), ["iso_o", "iso_d"]].isin(["ROM"]).any(axis=1).all()

print("All structural assertions passed.")
"""
        ),
        nbf.v4.new_markdown_cell(
            """## Takeaways

1. 两份数据的源粒度完整且合并没有扩张行数。
2. 主要缺口有明确来源：`ROW`、关税部门 20、HKG/TWN 理想点以及 LTU 宗教接近度。
3. 主结果应使用显式样本标志，避免对结构性缺失做零值插补。
4. 2019 数据适合先完成变量核对与单期初步估计；国家对固定效应留待多年面板。
"""
        ),
    ]
    nbf.write(notebook, notebook_path)
    return notebook_path


def build_all(
    project_dir: Path | str | None = None,
    *,
    write_notebook_file: bool = True,
) -> dict[str, Any]:
    project_dir = (
        Path(project_dir).resolve()
        if project_dir is not None
        else project_directory()
    )
    out_dir = output_directory(project_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    icio_codes = set(
        pd.read_stata(
            project_dir / "Explained_variable" / "icio2019.dta",
            convert_categoricals=False,
            columns=["iso_o"],
        )["iso_o"].unique()
    )
    pair_controls = build_pair_controls(project_dir, icio_codes)
    trade = build_trade_data(project_dir, pair_controls)
    mp = build_mp_data(project_dir, pair_controls)

    trade_stem = out_dir / "trade_cost_2019_matched"
    mp_stem = out_dir / "mp_cost_2019_matched"
    write_data_files(trade, trade_stem)
    write_data_files(mp, mp_stem)

    diagnostics = build_diagnostics(trade, mp)
    selection = build_variable_selection(pair_controls)
    diagnostics_path = out_dir / "matching_diagnostics_2019.csv"
    selection_path = out_dir / "variable_selection_2019.csv"
    diagnostics.to_csv(diagnostics_path, index=False, encoding="utf-8-sig")
    selection.to_csv(selection_path, index=False, encoding="utf-8-sig")
    write_readme(out_dir, trade, mp, diagnostics)

    notebook_path: Path | None = None
    if write_notebook_file:
        notebook_path = write_notebook(project_dir, out_dir, trade, mp)

    summary = {
        "trade_rows": len(trade),
        "mp_rows": len(mp),
        "trade_zero_rate": float(trade["value"].eq(0).mean()),
        "mp_zero_rate": float(mp["value"].eq(0).mean()),
        "trade_main_rows": int(trade["sample_trade_main"].sum()),
        "trade_main_international_rows": int(
            trade["sample_trade_main_international"].sum()
        ),
        "mp_main_rows": int(mp["sample_mp_main"].sum()),
        "mp_main_international_rows": int(
            mp["sample_mp_main_international"].sum()
        ),
    }
    manifest = {
        "trade_csv": str(trade_stem.with_suffix(".csv")),
        "trade_dta": str(trade_stem.with_suffix(".dta")),
        "mp_csv": str(mp_stem.with_suffix(".csv")),
        "mp_dta": str(mp_stem.with_suffix(".dta")),
        "diagnostics_csv": str(diagnostics_path),
        "selection_csv": str(selection_path),
        "notebook": str(notebook_path) if notebook_path else None,
        "summary": summary,
    }
    (out_dir / "build_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    result = build_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
