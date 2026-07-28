import re
from pathlib import Path

import pandas as pd

import config
from utils import (
    agreement_id_from_wbid,
    agreement_sort_key,
    clean_columns,
    ensure_directories,
    normalize_coverage,
    pick_column,
    read_sheet,
    write_csv,
    write_table_manifest,
)


def build_provisions_and_matrix(stata_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build provision master, agreement-provision matrix, and a long matrix."""
    area_col = pick_column(stata_df, ["Area"], label="STATA policy area")
    coding_col = pick_column(stata_df, ["Coding"], label="STATA coding")
    # Do not use normalized matching here: "Provision" and "Provision译文"
    # both normalize to "provision" and would otherwise select the last column.
    if "Provision" not in stata_df.columns:
        raise ValueError("STATA sheet must contain the English 'Provision' column.")
    provision_col = "Provision"
    translation_col = "Provision译文" if "Provision译文" in stata_df.columns else None
    agree_cols = [col for col in stata_df.columns if re.match(r"^agree_\d+$", str(col), re.I)]
    if not agree_cols:
        raise ValueError("No agree_* columns found in STATA sheet.")

    agree_cols = sorted(agree_cols, key=agreement_sort_key)
    source_cols = [area_col, coding_col, provision_col]
    if translation_col:
        source_cols.append(translation_col)
    source = stata_df[source_cols + agree_cols].copy()
    source = source[source[provision_col].notna()].reset_index(drop=True)

    provision_data: dict[str, object] = {
        "provision_id": [f"P{i + 1:04d}" for i in range(len(source))],
        "provision_order": range(1, len(source) + 1),
        "policy_area": source[area_col].astype(str).str.strip(),
        "original_coding": source[coding_col].astype(str).str.strip(),
        "provision_text": source[provision_col].astype(str).str.strip(),
    }
    if translation_col:
        provision_data["provision_translation"] = source[translation_col].fillna("").astype(str).str.strip()
    provisions = pd.DataFrame(provision_data)

    matrix_values = source[agree_cols].apply(lambda col: col.map(normalize_coverage))
    matrix = matrix_values.T
    matrix.index.name = "agreement_id"
    matrix.columns = provisions["provision_id"].tolist()
    matrix = matrix.reset_index()

    long_matrix = matrix.melt(
        id_vars=["agreement_id"],
        var_name="provision_id",
        value_name="coverage",
    )
    return provisions, matrix, long_matrix


def build_agreements_master(agreements_df: pd.DataFrame) -> pd.DataFrame:
    """Clean agreement metadata and add the agreement_id used by STATA columns."""
    agreements_df = clean_columns(agreements_df)
    wbid_col = pick_column(agreements_df, ["WB ID", "WBID", "World Bank ID"], label="WB ID")
    agreement_col = pick_column(agreements_df, ["Agreement", "Agreement Name"], label="agreement name")
    coverage_col = pick_column(agreements_df, ["Coverage"], required=False)
    type_col = pick_column(agreements_df, ["Type"], required=False)
    status_col = pick_column(agreements_df, ["Status"], required=False)
    entry_col = pick_column(
        agreements_df,
        ["Date of Entry into Force (G)", "Date of Entry into Force", "Entry into Force"],
        required=False,
    )

    out = pd.DataFrame()
    out["WBID"] = agreements_df[wbid_col]
    out["agreement_id"] = agreements_df[wbid_col].map(agreement_id_from_wbid)
    out["agreement_name"] = agreements_df[agreement_col].astype(str).str.strip()
    out["coverage"] = agreements_df[coverage_col] if coverage_col else ""
    out["type"] = agreements_df[type_col] if type_col else ""
    out["status"] = agreements_df[status_col] if status_col else ""
    out["date_entry_into_force"] = agreements_df[entry_col] if entry_col else ""

    for col in agreements_df.columns:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(col)).strip("_").lower()
        if cleaned and cleaned not in out.columns:
            out[cleaned] = agreements_df[col]

    out = out[out["agreement_id"].notna()].drop_duplicates("agreement_id")
    out = out.sort_values("agreement_id", key=lambda series: series.map(agreement_sort_key))
    return out.reset_index(drop=True)


def build_bilateral_panel(bilateral_df: pd.DataFrame) -> pd.DataFrame:
    """Clean bilateral panel fields and add the agreement_id used by STATA columns."""
    bilateral_df = clean_columns(bilateral_df)
    iso1_col = pick_column(bilateral_df, ["iso1", "ISO1"], label="iso1")
    iso2_col = pick_column(bilateral_df, ["iso2", "ISO2"], label="iso2")
    wbid_col = pick_column(bilateral_df, ["WBID", "WB ID"], label="WBID")
    year_col = pick_column(bilateral_df, ["year", "Year"], label="year")
    rta_col = pick_column(bilateral_df, ["rta_name", "RTA Name", "Agreement"], required=False)
    economy1_col = pick_column(bilateral_df, ["Economy1"], required=False)
    economy2_col = pick_column(bilateral_df, ["Economy2"], required=False)
    type_col = pick_column(bilateral_df, ["type", "Type"], required=False)
    entry_col = pick_column(bilateral_df, ["entry", "Entry"], required=False)

    out = pd.DataFrame()
    out["iso1"] = bilateral_df[iso1_col].astype(str).str.strip()
    out["iso2"] = bilateral_df[iso2_col].astype(str).str.strip()
    out["rta_name"] = bilateral_df[rta_col].astype(str).str.strip() if rta_col else ""
    out["WBID"] = bilateral_df[wbid_col]
    out["agreement_id"] = bilateral_df[wbid_col].map(agreement_id_from_wbid)
    out["year"] = pd.to_numeric(bilateral_df[year_col], errors="coerce").astype("Int64")
    out["Economy1"] = bilateral_df[economy1_col].astype(str).str.strip() if economy1_col else ""
    out["Economy2"] = bilateral_df[economy2_col].astype(str).str.strip() if economy2_col else ""
    out["type"] = bilateral_df[type_col].astype(str).str.strip() if type_col else ""
    out["entry"] = bilateral_df[entry_col] if entry_col else ""

    out = out[out["agreement_id"].notna() & out["year"].notna()].copy()
    out["year"] = out["year"].astype(int)
    return out.reset_index(drop=True)


def run(raw_path: Path = config.RAW_DATA_PATH) -> None:
    """Read DTA 2.0 and write MVP interim files."""
    ensure_directories()
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw data not found: {raw_path}")

    stata_df = read_sheet(raw_path, ["STATA"])
    agreements_df = read_sheet(raw_path, ["Agreements"])
    bilateral_df = read_sheet(raw_path, ["Bilateral Information"])

    provisions, matrix, long_matrix = build_provisions_and_matrix(stata_df)
    agreements = build_agreements_master(agreements_df)
    bilateral = build_bilateral_panel(bilateral_df)

    write_csv(provisions, config.PROVISIONS_MASTER_PATH)
    write_csv(matrix, config.AGREEMENT_MATRIX_PATH)
    write_csv(long_matrix, config.AGREEMENT_PROVISION_LONG_PATH)
    write_csv(agreements, config.AGREEMENTS_MASTER_PATH)
    write_csv(bilateral, config.BILATERAL_PANEL_PATH)
    write_table_manifest()

    print(f"Wrote {len(provisions):,} provisions to {config.PROVISIONS_MASTER_PATH}")
    print(f"Wrote {len(matrix):,} agreements to {config.AGREEMENT_MATRIX_PATH}")
    print(f"Wrote {len(bilateral):,} bilateral-year rows to {config.BILATERAL_PANEL_PATH}")


if __name__ == "__main__":
    run()
