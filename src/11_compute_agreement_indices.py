import numpy as np
import pandas as pd

import config
from utils import (
    detect_old_six_classification_values,
    ensure_directories,
    read_csv,
    write_csv,
)


REQUIRED_WEIGHT_COLUMNS = {
    "provision_id",
    "final_is_institutional_opening",
    "final_dominant_dimension",
    "final_impact_type",
    "effective_trade_weight",
    "effective_investment_weight",
}


def validate_weights(weights: pd.DataFrame) -> None:
    missing = REQUIRED_WEIGHT_COLUMNS - set(weights.columns)
    if missing:
        raise ValueError(f"final_provision_weights.csv missing required columns: {sorted(missing)}")
    detect_old_six_classification_values(weights)
    if "pipeline_schema_version" not in weights.columns:
        raise ValueError("final_provision_weights.csv missing pipeline_schema_version")
    versions = set(weights["pipeline_schema_version"].dropna().astype(str))
    if versions != {config.PIPELINE_SCHEMA_VERSION}:
        raise ValueError(
            "final_provision_weights.csv schema version mismatch: "
            f"{sorted(versions)}"
        )


def run() -> None:
    """Compute agreement-level raw trade and investment scores."""
    ensure_directories()
    matrix = read_csv(config.AGREEMENT_MATRIX_PATH)
    agreements = read_csv(config.AGREEMENTS_MASTER_PATH)
    weights = read_csv(config.FINAL_PROVISION_WEIGHTS_PATH)
    validate_weights(weights)

    provision_cols = [col for col in matrix.columns if col.startswith("P")]
    weight_lookup = weights.set_index("provision_id")
    missing_weights = [col for col in provision_cols if col not in weight_lookup.index]
    if missing_weights:
        raise ValueError(f"Missing final weights for {len(missing_weights):,} provision columns.")

    raw_x = matrix[provision_cols]
    x = raw_x.apply(pd.to_numeric, errors="coerce")
    invalid_x = raw_x.notna() & (x.isna() | x.lt(0) | x.gt(1))
    if invalid_x.any().any():
        sample = invalid_x.stack()[lambda values: values].index[0]
        raise ValueError(
            "agreement_matrix.csv contains a non-numeric or out-of-range coverage value "
            f"at agreement {matrix.loc[sample[0], 'agreement_id']}, provision {sample[1]}."
        )
    x = x.fillna(0.0)
    aligned_weights = weight_lookup.loc[provision_cols]
    trade_w = aligned_weights["effective_trade_weight"].astype(float).to_numpy()
    investment_w = aligned_weights["effective_investment_weight"].astype(float).to_numpy()

    x_values = x.to_numpy(dtype=float)
    any_coverage = x_values > 0
    full_coverage = x_values == 1
    institutional_mask = aligned_weights["final_is_institutional_opening"].astype(int).eq(1).to_numpy()
    dimension_values = aligned_weights["final_dominant_dimension"].astype(str).str.lower()
    trade_related_mask = trade_w > 0
    investment_related_mask = investment_w > 0
    raw_trade = np.round(x_values @ trade_w, config.OUTPUT_FLOAT_DECIMALS)
    raw_investment = np.round(x_values @ investment_w, config.OUTPUT_FLOAT_DECIMALS)

    out = pd.DataFrame(
        {
            "agreement_id": matrix["agreement_id"],
            "raw_trade_score": raw_trade,
            "raw_investment_score": raw_investment,
            "num_total_provisions_included": any_coverage.sum(axis=1),
            "num_total_provisions_full_coverage": full_coverage.sum(axis=1),
            "total_provision_coverage": x_values.sum(axis=1),
            "num_trade_related_provisions_included": (any_coverage & trade_related_mask).sum(axis=1),
            "num_trade_related_provisions_full_coverage": (full_coverage & trade_related_mask).sum(axis=1),
            "trade_related_provision_coverage": (x_values * trade_related_mask).sum(axis=1),
            "num_investment_related_provisions_included": (
                any_coverage & investment_related_mask
            ).sum(axis=1),
            "num_investment_related_provisions_full_coverage": (
                full_coverage & investment_related_mask
            ).sum(axis=1),
            "investment_related_provision_coverage": (x_values * investment_related_mask).sum(axis=1),
            "num_institutional_related_provisions_included": (
                any_coverage & institutional_mask
            ).sum(axis=1),
            "num_institutional_related_provisions_full_coverage": (
                full_coverage & institutional_mask
            ).sum(axis=1),
            "institutional_related_provision_coverage": (x_values * institutional_mask).sum(axis=1),
            "num_rules_provisions_included": (
                any_coverage & dimension_values.eq("rules").to_numpy()
            ).sum(axis=1),
            "num_rules_provisions_full_coverage": (
                full_coverage & dimension_values.eq("rules").to_numpy()
            ).sum(axis=1),
            "rules_provision_coverage": (
                x_values * dimension_values.eq("rules").to_numpy()
            ).sum(axis=1),
            "num_regulation_provisions_included": (
                any_coverage & dimension_values.eq("regulation").to_numpy()
            ).sum(axis=1),
            "num_regulation_provisions_full_coverage": (
                full_coverage & dimension_values.eq("regulation").to_numpy()
            ).sum(axis=1),
            "regulation_provision_coverage": (
                x_values * dimension_values.eq("regulation").to_numpy()
            ).sum(axis=1),
            "num_management_provisions_included": (
                any_coverage & dimension_values.eq("management").to_numpy()
            ).sum(axis=1),
            "num_management_provisions_full_coverage": (
                full_coverage & dimension_values.eq("management").to_numpy()
            ).sum(axis=1),
            "management_provision_coverage": (
                x_values * dimension_values.eq("management").to_numpy()
            ).sum(axis=1),
            "num_standards_provisions_included": (
                any_coverage & dimension_values.eq("standards").to_numpy()
            ).sum(axis=1),
            "num_standards_provisions_full_coverage": (
                full_coverage & dimension_values.eq("standards").to_numpy()
            ).sum(axis=1),
            "standards_provision_coverage": (
                x_values * dimension_values.eq("standards").to_numpy()
            ).sum(axis=1),
            "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
            "coverage_matrix_schema_version": config.COVERAGE_MATRIX_SCHEMA_VERSION,
        }
    )

    out = out.merge(agreements, on="agreement_id", how="left")
    first_cols = [
        "agreement_id",
        "WBID",
        "agreement_name",
        "coverage",
        "type",
        "status",
        "date_entry_into_force",
        "raw_trade_score",
        "raw_investment_score",
        "num_total_provisions_included",
        "num_total_provisions_full_coverage",
        "total_provision_coverage",
        "num_trade_related_provisions_included",
        "num_trade_related_provisions_full_coverage",
        "trade_related_provision_coverage",
        "num_investment_related_provisions_included",
        "num_investment_related_provisions_full_coverage",
        "investment_related_provision_coverage",
        "num_institutional_related_provisions_included",
        "num_institutional_related_provisions_full_coverage",
        "institutional_related_provision_coverage",
        "num_rules_provisions_included",
        "num_rules_provisions_full_coverage",
        "rules_provision_coverage",
        "num_regulation_provisions_included",
        "num_regulation_provisions_full_coverage",
        "regulation_provision_coverage",
        "num_management_provisions_included",
        "num_management_provisions_full_coverage",
        "management_provision_coverage",
        "num_standards_provisions_included",
        "num_standards_provisions_full_coverage",
        "standards_provision_coverage",
        "pipeline_schema_version",
        "coverage_matrix_schema_version",
    ]
    remaining = [col for col in out.columns if col not in first_cols]
    out = out[[col for col in first_cols if col in out.columns] + remaining]

    write_csv(out, config.AGREEMENT_LEVEL_INDICES_PATH)
    print(
        f"Wrote agreement-level raw scores for {len(out):,} agreements "
        f"to {config.AGREEMENT_LEVEL_INDICES_PATH}"
    )


if __name__ == "__main__":
    run()
