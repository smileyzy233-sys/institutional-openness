from collections import OrderedDict

import numpy as np
import pandas as pd

import config
from utils import ensure_directories, read_csv, write_csv


def unique_join(values: pd.Series) -> str:
    out: OrderedDict[str, None] = OrderedDict()
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            out[text] = None
    return "; ".join(out.keys())


def unique_tuple(values: pd.Series) -> tuple[str, ...]:
    out: OrderedDict[str, None] = OrderedDict()
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            out[text] = None
    return tuple(out.keys())


def compute_union_tuple(
    agreement_ids: tuple[str, ...],
    *,
    matrix_by_id: pd.DataFrame,
    provision_cols: list[str],
    trade_w: np.ndarray,
    investment_w: np.ndarray,
) -> dict[str, float | int]:
    agreement_ids = tuple(agreement_id for agreement_id in agreement_ids if agreement_id in matrix_by_id.index)
    if not agreement_ids:
        return {
            "raw_trade_score": np.nan,
            "raw_investment_score": np.nan,
            "num_active_agreements": 0,
        }

    # A country pair covered by multiple active agreements retains the strongest
    # coverage observed for each provision; partial coverage is not double counted.
    union_x = matrix_by_id.loc[agreement_ids, provision_cols].to_numpy(dtype=float).max(axis=0)
    return {
        "raw_trade_score": float(np.round(union_x @ trade_w, config.OUTPUT_FLOAT_DECIMALS)),
        "raw_investment_score": float(np.round(union_x @ investment_w, config.OUTPUT_FLOAT_DECIMALS)),
        "num_active_agreements": len(agreement_ids),
    }


def validate_inputs(agreement_indices: pd.DataFrame, weights: pd.DataFrame) -> None:
    if "pipeline_schema_version" not in agreement_indices.columns:
        raise ValueError("agreement_level_indices.csv missing pipeline_schema_version")
    versions = set(agreement_indices["pipeline_schema_version"].dropna().astype(str))
    if versions != {config.PIPELINE_SCHEMA_VERSION}:
        raise ValueError(f"agreement indices schema mismatch: {sorted(versions)}")
    if "coverage_matrix_schema_version" not in agreement_indices.columns:
        raise ValueError("agreement_level_indices.csv missing coverage_matrix_schema_version")
    coverage_versions = set(agreement_indices["coverage_matrix_schema_version"].dropna().astype(str))
    if coverage_versions != {config.COVERAGE_MATRIX_SCHEMA_VERSION}:
        raise ValueError(
            "agreement coverage schema mismatch: "
            f"{sorted(coverage_versions)}"
        )
    required_weights = {"provision_id", "effective_trade_weight", "effective_investment_weight"}
    missing = required_weights - set(weights.columns)
    if missing:
        raise ValueError(f"final_provision_weights.csv missing required columns: {sorted(missing)}")


def run(method: str = config.MULTI_AGREEMENT_METHOD) -> None:
    """Compute country-pair-year raw scores and retain the union default."""
    ensure_directories()
    if method not in {"union", "max", "mean"}:
        raise ValueError("method must be one of: union, max, mean")

    bilateral = read_csv(config.BILATERAL_PANEL_PATH)
    agreement_indices = read_csv(config.AGREEMENT_LEVEL_INDICES_PATH)
    matrix = read_csv(config.AGREEMENT_MATRIX_PATH)
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    validate_inputs(agreement_indices, weights)

    provision_cols = [col for col in matrix.columns if col.startswith("P")]
    matrix_by_id = matrix.set_index("agreement_id")
    raw_coverage = matrix_by_id[provision_cols]
    coverage = raw_coverage.apply(pd.to_numeric, errors="coerce")
    invalid_coverage = raw_coverage.notna() & (
        coverage.isna() | coverage.lt(0) | coverage.gt(1)
    )
    if invalid_coverage.any().any():
        agreement_id, provision_id = invalid_coverage.stack()[
            lambda values: values
        ].index[0]
        raise ValueError(
            "agreement_matrix.csv contains a non-numeric or out-of-range coverage value "
            f"at agreement {agreement_id}, provision {provision_id}."
        )
    matrix_by_id[provision_cols] = coverage.fillna(0.0)

    weight_lookup = weights.set_index("provision_id")
    trade_w = weight_lookup.loc[provision_cols, "effective_trade_weight"].astype(float).to_numpy()
    investment_w = weight_lookup.loc[provision_cols, "effective_investment_weight"].astype(float).to_numpy()

    bilateral = bilateral.merge(
        agreement_indices[["agreement_id", "raw_trade_score", "raw_investment_score"]],
        on="agreement_id",
        how="left",
    )

    group_cols = ["iso1", "iso2", "year"]
    bilateral = bilateral.sort_values(group_cols + ["agreement_id"])
    grouped = bilateral.groupby(group_cols, dropna=False, sort=True)
    meta = grouped.agg(
        Economy1=("Economy1", "first"),
        Economy2=("Economy2", "first"),
        WBID_list=("WBID", unique_join),
        rta_name_list=("rta_name", unique_join),
        agreement_tuple=("agreement_id", unique_tuple),
    ).reset_index()
    meta["agreement_id_list"] = meta["agreement_tuple"].map(lambda values: "; ".join(values))
    meta["method"] = method

    if method == "union":
        score_cache: dict[tuple[str, ...], dict[str, float | int]] = {}
        for combo in meta["agreement_tuple"].drop_duplicates().tolist():
            score_cache[combo] = compute_union_tuple(
                combo,
                matrix_by_id=matrix_by_id,
                provision_cols=provision_cols,
                trade_w=trade_w,
                investment_w=investment_w,
            )
        scores = pd.DataFrame([score_cache[combo] for combo in meta["agreement_tuple"]])
        out = pd.concat([meta.drop(columns=["agreement_tuple"]).reset_index(drop=True), scores], axis=1)
    else:
        agg_func = "max" if method == "max" else "mean"
        score_meta = grouped.agg(
            raw_trade_score=("raw_trade_score", agg_func),
            raw_investment_score=("raw_investment_score", agg_func),
            num_active_agreements=("agreement_id", "nunique"),
        ).reset_index()
        out = meta.drop(columns=["agreement_tuple"]).merge(score_meta, on=group_cols, how="left")

    iso1 = out["iso1"].fillna("").astype(str).str.strip().str.upper()
    iso2 = out["iso2"].fillna("").astype(str).str.strip().str.upper()
    out["pair_a"] = iso1.where(iso1.le(iso2), iso2)
    out["pair_b"] = iso2.where(iso1.le(iso2), iso1)
    out["pair_key"] = out["pair_a"] + "__" + out["pair_b"]
    out["trade_agreement_dummy"] = 1
    out["trade_agreement_dummy"] = out["trade_agreement_dummy"].astype("int8")
    out["pipeline_schema_version"] = config.PIPELINE_SCHEMA_VERSION
    out["coverage_matrix_schema_version"] = config.COVERAGE_MATRIX_SCHEMA_VERSION

    if out[["raw_trade_score", "raw_investment_score"]].isna().any().any():
        raise AssertionError("Country-pair output contains missing raw scores")
    out[["raw_trade_score", "raw_investment_score"]] = out[
        ["raw_trade_score", "raw_investment_score"]
    ].round(config.OUTPUT_FLOAT_DECIMALS)
    symmetry = out.groupby(["pair_key", "year"])[
        ["trade_agreement_dummy", "raw_trade_score", "raw_investment_score"]
    ].nunique(dropna=False)
    if symmetry.gt(1).any(axis=1).any():
        raise AssertionError("Country-pair dummy or raw scores differ across directions")

    first_cols = [
        "iso1",
        "iso2",
        "pair_a",
        "pair_b",
        "pair_key",
        "year",
        "Economy1",
        "Economy2",
        "WBID_list",
        "agreement_id_list",
        "rta_name_list",
        "trade_agreement_dummy",
        "num_active_agreements",
        "raw_trade_score",
        "raw_investment_score",
        "method",
        "pipeline_schema_version",
        "coverage_matrix_schema_version",
    ]
    out = out[[col for col in first_cols if col in out.columns]]
    write_csv(out, config.COUNTRY_PAIR_YEAR_INDICES_PATH)
    print(
        f"Wrote country-pair-year raw scores and agreement dummy for {len(out):,} rows "
        f"to {config.COUNTRY_PAIR_YEAR_INDICES_PATH}"
    )


if __name__ == "__main__":
    run()
