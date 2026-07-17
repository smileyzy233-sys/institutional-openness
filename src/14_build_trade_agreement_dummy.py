from __future__ import annotations

from collections import OrderedDict
from itertools import combinations
import re
from typing import Iterable

import numpy as np
import pandas as pd

import config
from utils import ensure_directories, read_csv, write_csv, write_table_manifest


ISO_ALIASES = {
    "ROM": "ROU",
    "SER": "SRB",
    "YUG": "SRB",
    "ZAR": "COD",
    "TMP": "TLS",
    "WBG": "PSE",
}
VALID_ISO3_RE = re.compile(r"^[A-Z]{3}$")
ICIO_YEAR = 2019
EXPECTED_ICIO_ECONOMY_COUNT = 76
EXPECTED_DTA_MIN_YEAR = 1958
EXPECTED_DTA_MAX_YEAR = 2023
ICIO_SAMPLE_SCOPE = "ICIO2019_economies_excluding_ROW"
ICIO_2019_CROSSCHECK_FIELDS = [
    "iso_o",
    "iso_d",
    "year",
    "trade_agreement_dummy",
    "raw_trade_score",
    "raw_investment_score",
    "num_active_agreements",
    "agreement_id_list",
    "WBID_list",
    "rta_name_list",
    "match_status",
]


def validate_country_pair_input() -> None:
    if not config.COUNTRY_PAIR_YEAR_INDICES_PATH.exists():
        raise FileNotFoundError(
            f"Country-pair raw scores not found: {config.COUNTRY_PAIR_YEAR_INDICES_PATH}. "
            "Run `python run_pipeline.py indices` first."
        )
    pair_indices = read_csv(config.COUNTRY_PAIR_YEAR_INDICES_PATH)
    if "pipeline_schema_version" not in pair_indices.columns:
        raise ValueError("country_pair_year_indices.csv missing pipeline_schema_version")
    versions = set(pair_indices["pipeline_schema_version"].dropna().astype(str))
    if versions != {config.PIPELINE_SCHEMA_VERSION}:
        raise ValueError(f"country pair indices schema mismatch: {sorted(versions)}")
    if "coverage_matrix_schema_version" not in pair_indices.columns:
        raise ValueError("country_pair_year_indices.csv missing coverage_matrix_schema_version")
    coverage_versions = set(pair_indices["coverage_matrix_schema_version"].dropna().astype(str))
    if coverage_versions != {config.COVERAGE_MATRIX_SCHEMA_VERSION}:
        raise ValueError(
            "country pair coverage schema mismatch: "
            f"{sorted(coverage_versions)}"
        )


def normalize_iso3(value: object, aliases: dict[str, str] | None = None) -> str:
    """Normalize an ISO-like code while preserving unknown non-empty codes."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "<NA>"}:
        return ""
    mapping = ISO_ALIASES if aliases is None else aliases
    return mapping.get(text, text)


def is_valid_iso3(value: object) -> bool:
    return bool(VALID_ISO3_RE.fullmatch(str(value).strip().upper()))


def load_iso_aliases() -> dict[str, str]:
    """Load optional user mappings on top of the conservative built-in aliases."""
    aliases = dict(ISO_ALIASES)
    path = config.COUNTRY_CODE_CROSSWALK_PATH
    if not path.exists():
        return aliases

    crosswalk = read_csv(path, dtype=str).fillna("")
    required = {"source_code", "target_code"}
    if not required.issubset(crosswalk.columns):
        raise ValueError(
            f"Country-code crosswalk must contain {sorted(required)}; got {list(crosswalk.columns)}"
        )
    for row in crosswalk.itertuples(index=False):
        source = str(getattr(row, "source_code")).strip().upper()
        target = str(getattr(row, "target_code")).strip().upper()
        if source and target:
            aliases[source] = aliases.get(target, target)
    return aliases


def collision_safe_aliases(
    code_columns: Iterable[pd.Series], aliases: dict[str, str]
) -> dict[str, str]:
    """Avoid collapsing codes that the same source treats as distinct economies."""
    source_codes: set[str] = set()
    for series in code_columns:
        source_codes.update(series.map(lambda value: normalize_iso3(value, {})))
    return {
        source: target
        for source, target in aliases.items()
        if source == target or source not in source_codes or target not in source_codes
    }


def make_pair_key(df: pd.DataFrame, col1: str, col2: str) -> pd.DataFrame:
    """Build an undirected pair key without changing the source direction."""
    code1 = df[col1].fillna("").astype(str).str.strip().str.upper()
    code2 = df[col2].fillna("").astype(str).str.strip().str.upper()
    valid_pair = code1.ne("") & code2.ne("")
    pair_a = pd.Series(np.where(code1.le(code2), code1, code2), index=df.index)
    pair_b = pd.Series(np.where(code1.le(code2), code2, code1), index=df.index)
    pair_a = pair_a.where(valid_pair, "")
    pair_b = pair_b.where(valid_pair, "")
    pair_key = (pair_a + "__" + pair_b).where(valid_pair, "")
    is_domestic = (valid_pair & code1.eq(code2)).astype("int8")
    return pd.DataFrame(
        {
            "pair_a": pair_a,
            "pair_b": pair_b,
            "pair_key": pair_key,
            "is_domestic_pair": is_domestic,
        },
        index=df.index,
    )


def stable_unique_join(values: Iterable[object]) -> str:
    unique: OrderedDict[str, None] = OrderedDict()
    for value in values:
        if value is None or pd.isna(value):
            continue
        if isinstance(value, (int, np.integer)):
            text = str(int(value))
        elif isinstance(value, (float, np.floating)) and float(value).is_integer():
            text = str(int(value))
        else:
            text = str(value).strip()
        if text and text.lower() not in {"nan", "none"}:
            unique[text] = None
    return "; ".join(unique.keys())


def prepare_active_agreements(
    bilateral: pd.DataFrame, aliases: dict[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"iso1", "iso2", "year", "agreement_id"}
    missing = required - set(bilateral.columns)
    if missing:
        raise ValueError(f"bilateral_panel.csv is missing required columns: {sorted(missing)}")

    source = bilateral.copy()
    for optional in ["WBID", "rta_name"]:
        if optional not in source.columns:
            source[optional] = ""
    dta_aliases = collision_safe_aliases([source["iso1"], source["iso2"]], aliases)
    source["iso1"] = source["iso1"].map(
        lambda value: normalize_iso3(value, dta_aliases)
    )
    source["iso2"] = source["iso2"].map(
        lambda value: normalize_iso3(value, dta_aliases)
    )
    source["year"] = pd.to_numeric(source["year"], errors="coerce")
    source["agreement_id"] = source["agreement_id"].fillna("").astype(str).str.strip()
    source = source[
        source["iso1"].ne("")
        & source["iso2"].ne("")
        & source["year"].notna()
        & source["agreement_id"].ne("")
    ].copy()
    source["year"] = source["year"].astype(int)
    source = pd.concat([source, make_pair_key(source, "iso1", "iso2")], axis=1)
    source = source[source["is_domestic_pair"].eq(0)].copy()
    source = source.sort_values(["pair_key", "year", "agreement_id"], kind="stable")

    active = (
        source.groupby(["pair_a", "pair_b", "pair_key", "year"], sort=True, as_index=False)
        .agg(
            num_active_agreements=("agreement_id", "nunique"),
            agreement_id_list=("agreement_id", stable_unique_join),
            WBID_list=("WBID", stable_unique_join),
            rta_name_list=("rta_name", stable_unique_join),
        )
    )
    active.insert(4, "trade_agreement_dummy", 1)
    active["trade_agreement_dummy"] = active["trade_agreement_dummy"].astype("int8")
    active["num_active_agreements"] = active["num_active_agreements"].astype("int32")
    return source, active


def attach_raw_scores(
    active: pd.DataFrame, pair_scores: pd.DataFrame, aliases: dict[str, str]
) -> pd.DataFrame:
    """Attach direction-invariant raw scores to active DTA pair-years."""
    required = {"iso1", "iso2", "year", "raw_trade_score", "raw_investment_score"}
    missing = required - set(pair_scores.columns)
    if missing:
        raise ValueError(
            "country_pair_year_indices.csv is missing required columns: "
            f"{sorted(missing)}. Run `python run_pipeline.py indices` first."
        )

    scores = pair_scores.copy()
    score_aliases = collision_safe_aliases([scores["iso1"], scores["iso2"]], aliases)
    scores["iso1"] = scores["iso1"].map(
        lambda value: normalize_iso3(value, score_aliases)
    )
    scores["iso2"] = scores["iso2"].map(
        lambda value: normalize_iso3(value, score_aliases)
    )
    scores["year"] = pd.to_numeric(scores["year"], errors="coerce")
    scores["raw_trade_score"] = pd.to_numeric(
        scores["raw_trade_score"], errors="coerce"
    )
    scores["raw_investment_score"] = pd.to_numeric(
        scores["raw_investment_score"], errors="coerce"
    )
    scores = scores[
        scores["iso1"].ne("")
        & scores["iso2"].ne("")
        & scores["year"].notna()
        & scores["raw_trade_score"].notna()
        & scores["raw_investment_score"].notna()
    ].copy()
    scores["year"] = scores["year"].astype(int)
    scores = scores.drop(
        columns=["pair_a", "pair_b", "pair_key", "is_domestic_pair"],
        errors="ignore",
    )
    scores = pd.concat([scores, make_pair_key(scores, "iso1", "iso2")], axis=1)

    score_columns = ["raw_trade_score", "raw_investment_score"]
    conflicts = scores.groupby(["pair_key", "year"])[score_columns].nunique(dropna=False)
    if conflicts.gt(1).any(axis=1).any():
        examples = conflicts.loc[conflicts.gt(1).any(axis=1)].head().index.tolist()
        raise AssertionError(f"Raw scores differ across pair directions: {examples}")

    score_lookup = (
        scores.groupby(["pair_key", "year"], as_index=False, sort=True)[score_columns]
        .first()
    )
    out = active.merge(score_lookup, on=["pair_key", "year"], how="left", validate="1:1")
    missing_scores = out[score_columns].isna().any(axis=1)
    if missing_scores.any():
        examples = out.loc[missing_scores, ["pair_key", "year"]].head().to_dict("records")
        raise AssertionError(f"Active DTA pair-years are missing raw scores: {examples}")
    return out


def load_idealpoint_country_year(needed_isos: set[str] | None = None) -> pd.DataFrame:
    """Load UNGA ideal points as an ISO3-country-year lookup."""
    if not config.IDEALPOINT_ESTIMATES_PATH.exists():
        raise FileNotFoundError(
            f"Ideal point estimates not found: {config.IDEALPOINT_ESTIMATES_PATH}"
        )
    if not config.AGREEMENT_SCORES_PATH.exists():
        raise FileNotFoundError(
            f"Agreement score source not found: {config.AGREEMENT_SCORES_PATH}"
        )

    ideal = pd.read_csv(
        config.IDEALPOINT_ESTIMATES_PATH,
        encoding=config.CSV_ENCODING,
        usecols=["ccode", "session", "IdealPointAll", "iso3c"],
    )
    session_year = pd.read_csv(
        config.AGREEMENT_SCORES_PATH,
        encoding=config.CSV_ENCODING,
        usecols=["session.x", "year"],
    ).drop_duplicates()
    session_year = session_year.rename(columns={"session.x": "session"})
    if session_year["session"].duplicated().any():
        duplicates = session_year.loc[
            session_year["session"].duplicated(), "session"
        ].tolist()
        raise ValueError(f"UNGA session-year mapping is not unique: {duplicates[:5]}")

    ideal["iso3c"] = ideal["iso3c"].map(normalize_iso3)
    ideal["session"] = pd.to_numeric(ideal["session"], errors="coerce")
    ideal["IdealPointAll"] = pd.to_numeric(ideal["IdealPointAll"], errors="coerce")
    ideal = ideal[
        ideal["iso3c"].ne("")
        & ideal["session"].notna()
        & ideal["IdealPointAll"].notna()
    ].copy()
    if needed_isos is not None:
        ideal = ideal[ideal["iso3c"].isin(needed_isos)].copy()

    country_year = ideal.merge(session_year, on="session", how="left", validate="m:1")
    country_year["year"] = pd.to_numeric(country_year["year"], errors="coerce")
    country_year = country_year[country_year["year"].notna()].copy()
    country_year["year"] = country_year["year"].astype("int32")

    duplicated = country_year.duplicated(["iso3c", "year"], keep=False)
    if duplicated.any():
        examples = (
            country_year.loc[duplicated, ["iso3c", "ccode", "session", "year"]]
            .sort_values(["iso3c", "year", "ccode"])
            .head()
            .to_dict("records")
        )
        raise ValueError(f"Ideal point ISO-year lookup is not unique: {examples}")

    return country_year[["iso3c", "year", "IdealPointAll"]].rename(
        columns={"IdealPointAll": "idealpoint"}
    )


def attach_idealpoint_distance(
    frame: pd.DataFrame, *, origin_col: str, destination_col: str
) -> pd.DataFrame:
    """Attach absolute UNGA ideal-point distance for directed country-year rows."""
    out = frame.copy()
    needed_isos = set(out[origin_col].dropna().astype(str)) | set(
        out[destination_col].dropna().astype(str)
    )
    ideal = load_idealpoint_country_year(needed_isos)
    origin_lookup = ideal.rename(
        columns={"iso3c": origin_col, "idealpoint": "_idealpoint_o"}
    )
    destination_lookup = ideal.rename(
        columns={"iso3c": destination_col, "idealpoint": "_idealpoint_d"}
    )

    out = out.merge(
        origin_lookup,
        on=[origin_col, "year"],
        how="left",
        validate="m:1",
    )
    out = out.merge(
        destination_lookup,
        on=[destination_col, "year"],
        how="left",
        validate="m:1",
    )
    out["idealpoint_abs_distance"] = (
        out["_idealpoint_o"].sub(out["_idealpoint_d"]).abs()
    )
    domestic = out[origin_col].eq(out[destination_col])
    out.loc[domestic, "idealpoint_abs_distance"] = 0.0
    return out.drop(columns=["_idealpoint_o", "_idealpoint_d"])


def prepare_icio(aliases: dict[str, str]) -> pd.DataFrame:
    if not config.ICIO2019_PATH.exists():
        raise FileNotFoundError(f"ICIO input not found: {config.ICIO2019_PATH}")
    icio = pd.read_stata(config.ICIO2019_PATH, convert_categoricals=False)
    missing = {"iso_o", "iso_d"} - set(icio.columns)
    if missing:
        raise ValueError(f"icio2019.dta is missing required columns: {sorted(missing)}")

    icio = icio.copy()
    icio["iso_o_raw"] = icio["iso_o"]
    icio["iso_d_raw"] = icio["iso_d"]
    icio["iso_o"] = icio["iso_o"].map(lambda value: normalize_iso3(value, aliases))
    icio["iso_d"] = icio["iso_d"].map(lambda value: normalize_iso3(value, aliases))
    icio["year"] = ICIO_YEAR
    return icio


def build_icio_economy_sample(
    icio: pd.DataFrame, dta_source: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Extract the DTA-matchable ICIO economy sample and stable names."""
    dta_codes = set(dta_source["iso1"]) | set(dta_source["iso2"])
    icio_codes = sorted(
        code
        for code in (set(icio["iso_o"]) | set(icio["iso_d"]))
        if code
    )
    sample_codes = sorted(
        code
        for code in icio_codes
        if code != "ROW" and is_valid_iso3(code) and code in dta_codes
    )
    excluded_codes = sorted(set(icio_codes) - set(sample_codes))

    names_by_code: dict[str, OrderedDict[str, None]] = {}
    for code_col, name_col in [("iso_o", "country_o"), ("iso_d", "country_d")]:
        if name_col not in icio.columns:
            continue
        for code, name in icio[[code_col, name_col]].itertuples(index=False, name=None):
            code = str(code).strip().upper()
            if not code or name is None or pd.isna(name):
                continue
            name_text = str(name).strip()
            if name_text:
                names_by_code.setdefault(code, OrderedDict())[name_text] = None

    conflicts = {
        code: list(names.keys())
        for code, names in names_by_code.items()
        if code in sample_codes and len(names) > 1
    }
    if conflicts:
        raise ValueError(f"ICIO economy-name conflicts after code normalization: {conflicts}")

    sample = pd.DataFrame({"iso_code": sample_codes})
    sample["country_name"] = sample["iso_code"].map(
        lambda code: next(iter(names_by_code.get(code, {})), "")
    )
    missing_names = sample.loc[sample["country_name"].eq(""), "iso_code"].tolist()
    if missing_names:
        raise ValueError(f"ICIO economy names are missing for: {missing_names}")
    return sample, excluded_codes


def build_icio_economies_all_years_panel(
    sample: pd.DataFrame, dta_source: pd.DataFrame, active: pd.DataFrame
) -> pd.DataFrame:
    """Build the complete directed ICIO-economy-by-year agreement panel."""
    year_values = pd.to_numeric(dta_source["year"], errors="coerce").dropna().astype(int)
    if year_values.empty:
        raise ValueError("bilateral_panel.csv contains no usable years")
    years = np.arange(year_values.min(), year_values.max() + 1, dtype="int32")
    codes = sample["iso_code"].tolist()
    country_names = dict(zip(sample["iso_code"], sample["country_name"]))

    panel = pd.MultiIndex.from_product(
        [codes, codes, years], names=["iso_o", "iso_d", "year"]
    ).to_frame(index=False)
    panel.insert(2, "country_o", panel["iso_o"].map(country_names))
    panel.insert(3, "country_d", panel["iso_d"].map(country_names))
    panel = attach_agreement_data(
        panel, active, origin_col="iso_o", destination_col="iso_d"
    )
    panel = attach_idealpoint_distance(panel, origin_col="iso_o", destination_col="iso_d")
    panel["sample_scope"] = ICIO_SAMPLE_SCOPE
    preferred = [
        "iso_o",
        "iso_d",
        "country_o",
        "country_d",
        "year",
        "pair_a",
        "pair_b",
        "pair_key",
        "is_domestic_pair",
        "agreement_applicable",
        "trade_agreement_dummy",
        "raw_trade_score",
        "raw_investment_score",
        "num_active_agreements",
        "agreement_id_list",
        "WBID_list",
        "rta_name_list",
        "match_status",
        "idealpoint_abs_distance",
        "sample_scope",
    ]
    return panel[preferred].sort_values(["iso_o", "iso_d", "year"], kind="stable")


def count_2019_crosscheck_mismatches(
    all_years_panel: pd.DataFrame, pair_year: pd.DataFrame, sample_codes: set[str]
) -> int:
    """Count row-level differences from the legacy 2019 ICIO pair table."""
    current = all_years_panel.loc[
        all_years_panel["year"].eq(ICIO_YEAR), ICIO_2019_CROSSCHECK_FIELDS
    ].copy()
    legacy = pair_year.loc[
        pair_year["iso_o"].isin(sample_codes) & pair_year["iso_d"].isin(sample_codes),
        ICIO_2019_CROSSCHECK_FIELDS,
    ].copy()
    current = current.sort_values(["iso_o", "iso_d", "year"]).reset_index(drop=True)
    legacy = legacy.sort_values(["iso_o", "iso_d", "year"]).reset_index(drop=True)
    if len(current) != len(legacy):
        return max(len(current), len(legacy))

    text_columns = [
        "iso_o",
        "iso_d",
        "agreement_id_list",
        "WBID_list",
        "rta_name_list",
        "match_status",
    ]
    integer_columns = [
        "year",
        "trade_agreement_dummy",
        "num_active_agreements",
    ]
    for frame in [current, legacy]:
        for column in text_columns:
            frame[column] = frame[column].fillna("").astype(str)
        for column in integer_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
        for column in ["raw_trade_score", "raw_investment_score"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    exact_columns = [column for column in current.columns if not column.startswith("raw_")]
    mismatch = current[exact_columns].ne(legacy[exact_columns]).any(axis=1)
    mismatch |= ~np.isclose(current["raw_trade_score"], legacy["raw_trade_score"])
    mismatch |= ~np.isclose(
        current["raw_investment_score"], legacy["raw_investment_score"]
    )
    return int(mismatch.sum())


def attach_agreement_data(
    frame: pd.DataFrame, active: pd.DataFrame, *, origin_col: str, destination_col: str
) -> pd.DataFrame:
    out = pd.concat([frame.copy(), make_pair_key(frame, origin_col, destination_col)], axis=1)
    active_fields = [
        "pair_key",
        "year",
        "trade_agreement_dummy",
        "raw_trade_score",
        "raw_investment_score",
        "num_active_agreements",
        "agreement_id_list",
        "WBID_list",
        "rta_name_list",
    ]
    out = out.merge(active[active_fields], on=["pair_key", "year"], how="left", validate="m:1")

    valid_codes = out[origin_col].map(is_valid_iso3) & out[destination_col].map(is_valid_iso3)
    domestic = out["is_domestic_pair"].eq(1)
    matched = out["trade_agreement_dummy"].eq(1)
    applicable = valid_codes & ~domestic

    out["agreement_applicable"] = applicable.astype("int8")
    out["trade_agreement_dummy"] = matched.where(applicable, False).astype("int8")
    for column in ["raw_trade_score", "raw_investment_score"]:
        out[column] = (
            pd.to_numeric(out[column], errors="coerce")
            .fillna(0.0)
            .where(out["trade_agreement_dummy"].eq(1), 0.0)
        )
    out["num_active_agreements"] = (
        pd.to_numeric(out["num_active_agreements"], errors="coerce")
        .fillna(0)
        .where(applicable, 0)
        .astype("int32")
    )
    for column in ["agreement_id_list", "WBID_list", "rta_name_list"]:
        out[column] = out[column].fillna("").astype(str).where(applicable, "")

    out["match_status"] = np.select(
        [~valid_codes, domestic, out["trade_agreement_dummy"].eq(1)],
        [
            "invalid_country_code",
            "domestic_pair_not_applicable",
            "matched_active_agreement",
        ],
        default="no_active_agreement_in_dta",
    )
    return out


def build_icio_pair_year(icio: pd.DataFrame, active: pd.DataFrame) -> pd.DataFrame:
    keep = ["iso_o", "iso_d", "year"]
    for optional in ["country_o", "country_d"]:
        if optional in icio.columns:
            keep.append(optional)
    pair_year = icio[keep].drop_duplicates(["iso_o", "iso_d", "year"], keep="first")
    pair_year = attach_agreement_data(
        pair_year, active, origin_col="iso_o", destination_col="iso_d"
    )
    preferred = [
        "iso_o",
        "iso_d",
        "country_o",
        "country_d",
        "year",
        "pair_a",
        "pair_b",
        "pair_key",
        "is_domestic_pair",
        "agreement_applicable",
        "trade_agreement_dummy",
        "raw_trade_score",
        "raw_investment_score",
        "num_active_agreements",
        "agreement_id_list",
        "WBID_list",
        "rta_name_list",
        "match_status",
    ]
    return pair_year[[column for column in preferred if column in pair_year.columns]].sort_values(
        ["iso_o", "iso_d", "year"], kind="stable"
    )


def build_expanded_union(
    dta_source: pd.DataFrame, icio: pd.DataFrame, active: pd.DataFrame
) -> pd.DataFrame:
    dta_countries = set(dta_source["iso1"]) | set(dta_source["iso2"])
    icio_countries = set(icio["iso_o"]) | set(icio["iso_d"])
    countries = sorted(
        code for code in (dta_countries | icio_countries) if code and is_valid_iso3(code)
    )
    years = sorted(set(dta_source["year"].astype(int)) | {ICIO_YEAR})
    pair_rows = list(combinations(countries, 2))
    pairs = pd.DataFrame(pair_rows, columns=["pair_a", "pair_b"])
    pairs["pair_key"] = pairs["pair_a"] + "__" + pairs["pair_b"]

    pair_count = len(pairs)
    union = pd.DataFrame(
        {
            "pair_a": np.tile(pairs["pair_a"].to_numpy(), len(years)),
            "pair_b": np.tile(pairs["pair_b"].to_numpy(), len(years)),
            "pair_key": np.tile(pairs["pair_key"].to_numpy(), len(years)),
            "year": np.repeat(np.asarray(years, dtype="int32"), pair_count),
        }
    )
    active_fields = [
        "pair_key",
        "year",
        "trade_agreement_dummy",
        "raw_trade_score",
        "raw_investment_score",
        "num_active_agreements",
        "agreement_id_list",
        "WBID_list",
        "rta_name_list",
    ]
    union = union.merge(active[active_fields], on=["pair_key", "year"], how="left", validate="1:1")
    union.insert(0, "iso1", union["pair_a"])
    union.insert(1, "iso2", union["pair_b"])
    union["trade_agreement_dummy"] = (
        union["trade_agreement_dummy"].fillna(0).astype("int8")
    )
    for column in ["raw_trade_score", "raw_investment_score"]:
        union[column] = pd.to_numeric(union[column], errors="coerce").fillna(0.0)
    union["num_active_agreements"] = (
        union["num_active_agreements"].fillna(0).astype("int32")
    )
    for column in ["agreement_id_list", "WBID_list", "rta_name_list"]:
        union[column] = union[column].fillna("").astype(str)
    union["source_country_scope"] = "DTA_or_ICIO_union"
    return union


def build_code_mismatch_report(
    dta_source: pd.DataFrame, icio: pd.DataFrame
) -> pd.DataFrame:
    dta_codes = set(dta_source["iso1"]) | set(dta_source["iso2"])
    icio_codes = set(icio["iso_o"]) | set(icio["iso_d"])
    rows: list[dict[str, str]] = []

    country_names: dict[str, str] = {}
    for code_col, name_col in [("iso_o", "country_o"), ("iso_d", "country_d")]:
        if name_col in icio.columns:
            names = icio[[code_col, name_col]].drop_duplicates(code_col)
            country_names.update(
                dict(zip(names[code_col].astype(str), names[name_col].fillna("").astype(str)))
            )

    for code in sorted(code for code in icio_codes - dta_codes if is_valid_iso3(code)):
        rows.append(
            {
                "code": code,
                "source": "ICIO",
                "issue": "icio_country_not_found_in_dta",
                "country_name_if_available": country_names.get(code, ""),
            }
        )
    for code in sorted(code for code in dta_codes - icio_codes if is_valid_iso3(code)):
        rows.append(
            {
                "code": code,
                "source": "DTA",
                "issue": "dta_country_not_found_in_icio",
                "country_name_if_available": "",
            }
        )

    for code_col, name_col in [("iso_o", "country_o"), ("iso_d", "country_d")]:
        invalid = icio.loc[~icio[code_col].map(is_valid_iso3), [code_col]].copy()
        if name_col in icio.columns:
            invalid[name_col] = icio.loc[invalid.index, name_col]
        else:
            invalid[name_col] = ""
        invalid = invalid.drop_duplicates([code_col, name_col])
        for row in invalid.itertuples(index=False):
            rows.append(
                {
                    "code": str(getattr(row, code_col)),
                    "source": f"ICIO.{code_col}",
                    "issue": "invalid_icio_country_code",
                    "country_name_if_available": str(getattr(row, name_col) or ""),
                }
            )
    return pd.DataFrame(
        rows,
        columns=["code", "source", "issue", "country_name_if_available"],
    )


def build_diagnostics(
    icio: pd.DataFrame,
    pair_year: pd.DataFrame,
    all_years_panel: pd.DataFrame,
    sample: pd.DataFrame,
    excluded_codes: list[str],
    active: pd.DataFrame,
    expanded: pd.DataFrame,
    mismatch: pd.DataFrame,
) -> pd.DataFrame:
    dta_countries = set(active["pair_a"]) | set(active["pair_b"])
    icio_countries = set(icio["iso_o"]) | set(icio["iso_d"])
    metrics = OrderedDict(
        [
            ("icio_rows", len(icio)),
            ("icio_unique_origin_countries", icio["iso_o"].nunique()),
            ("icio_unique_destination_countries", icio["iso_d"].nunique()),
            ("icio_unique_countries", len(icio_countries)),
            ("icio_unique_directed_pairs", icio[["iso_o", "iso_d"]].drop_duplicates().shape[0]),
            (
                "icio_unique_international_directed_pairs",
                icio.loc[icio["iso_o"].ne(icio["iso_d"]), ["iso_o", "iso_d"]]
                .drop_duplicates()
                .shape[0],
            ),
            (
                "icio_unique_domestic_pairs",
                icio.loc[icio["iso_o"].eq(icio["iso_d"]), ["iso_o", "iso_d"]]
                .drop_duplicates()
                .shape[0],
            ),
            ("icio_pair_year_rows", len(pair_year)),
            ("icio_pair_year_dummy_1", int(pair_year["trade_agreement_dummy"].eq(1).sum())),
            ("icio_pair_year_dummy_0", int(pair_year["trade_agreement_dummy"].eq(0).sum())),
            ("icio_pair_year_domestic_rows", int(pair_year["is_domestic_pair"].eq(1).sum())),
            ("icio_pair_year_international_rows", int(pair_year["is_domestic_pair"].eq(0).sum())),
            ("icio_sample_economies_all_years_country_count", len(sample)),
            ("icio_sample_economies_all_years_min_year", int(all_years_panel["year"].min())),
            ("icio_sample_economies_all_years_max_year", int(all_years_panel["year"].max())),
            ("icio_sample_economies_all_years_year_count", int(all_years_panel["year"].nunique())),
            ("icio_sample_economies_all_years_rows", len(all_years_panel)),
            (
                "icio_sample_economies_all_years_international_rows",
                int(all_years_panel["is_domestic_pair"].eq(0).sum()),
            ),
            (
                "icio_sample_economies_all_years_domestic_rows",
                int(all_years_panel["is_domestic_pair"].eq(1).sum()),
            ),
            (
                "icio_sample_economies_all_years_dummy_1",
                int(all_years_panel["trade_agreement_dummy"].eq(1).sum()),
            ),
            (
                "icio_sample_economies_all_years_dummy_0",
                int(all_years_panel["trade_agreement_dummy"].eq(0).sum()),
            ),
            (
                "icio_sample_economies_all_years_idealpoint_distance_non_missing",
                int(all_years_panel["idealpoint_abs_distance"].notna().sum()),
            ),
            (
                "icio_sample_economies_all_years_idealpoint_distance_missing",
                int(all_years_panel["idealpoint_abs_distance"].isna().sum()),
            ),
            (
                "icio_sample_economies_all_years_international_idealpoint_distance_missing",
                int(
                    all_years_panel.loc[
                        all_years_panel["is_domestic_pair"].eq(0),
                        "idealpoint_abs_distance",
                    ]
                    .isna()
                    .sum()
                ),
            ),
            ("icio_sample_excluded_code_count", len(excluded_codes)),
            ("icio_sample_excluded_codes", "; ".join(excluded_codes)),
            (
                "icio_sample_economies_all_years_primary_key_duplicates",
                int(all_years_panel.duplicated(["iso_o", "iso_d", "year"]).sum()),
            ),
            (
                "icio_sample_economies_all_years_2019_crosscheck_mismatch_rows",
                count_2019_crosscheck_mismatches(
                    all_years_panel, pair_year, set(sample["iso_code"])
                ),
            ),
            ("dta_active_pair_year_rows", len(active)),
            ("dta_unique_countries", len(dta_countries)),
            ("dta_min_year", int(active["year"].min())),
            ("dta_max_year", int(active["year"].max())),
            (
                "expanded_union_countries",
                len(set(expanded["iso1"]) | set(expanded["iso2"])),
            ),
            ("expanded_union_pair_year_rows", len(expanded)),
            ("expanded_union_dummy_1", int(expanded["trade_agreement_dummy"].eq(1).sum())),
            ("expanded_union_dummy_0", int(expanded["trade_agreement_dummy"].eq(0).sum())),
            (
                "invalid_icio_country_code_rows",
                int((~icio["iso_o"].map(is_valid_iso3) | ~icio["iso_d"].map(is_valid_iso3)).sum()),
            ),
            (
                "icio_country_not_in_dta_count",
                int(mismatch["issue"].eq("icio_country_not_found_in_dta").sum()),
            ),
            (
                "dta_country_not_in_icio_count",
                int(mismatch["issue"].eq("dta_country_not_found_in_icio").sum()),
            ),
        ]
    )
    return pd.DataFrame({"metric": list(metrics.keys()), "value": list(metrics.values())})


def validate_outputs(
    pair_year: pd.DataFrame,
    all_years_panel: pd.DataFrame,
    sample: pd.DataFrame,
    excluded_codes: list[str],
    active: pd.DataFrame,
    expanded: pd.DataFrame,
) -> None:
    if pair_year.duplicated(["iso_o", "iso_d", "year"]).any():
        raise AssertionError("ICIO pair-year output contains duplicate directed pairs")
    international = pair_year[pair_year["is_domestic_pair"].eq(0)]
    if international.groupby(["pair_a", "pair_b", "year"])[
        "trade_agreement_dummy"
    ].nunique().max() > 1:
        raise AssertionError("Dummy differs across directions of the same pair-year")
    if active.empty or not active["trade_agreement_dummy"].eq(1).all():
        raise AssertionError("DTA active output must contain only dummy = 1")
    if active[["raw_trade_score", "raw_investment_score"]].isna().any().any():
        raise AssertionError("DTA active output contains missing raw scores")
    if active["pair_a"].eq(active["pair_b"]).any():
        raise AssertionError("DTA active output must not contain domestic pairs")
    union_values = set(expanded["trade_agreement_dummy"].unique())
    if not {0, 1}.issubset(union_values):
        raise AssertionError("Expanded union output must contain both dummy values 0 and 1")

    expected_year_count = EXPECTED_DTA_MAX_YEAR - EXPECTED_DTA_MIN_YEAR + 1
    expected_rows = EXPECTED_ICIO_ECONOMY_COUNT ** 2 * expected_year_count
    domestic = all_years_panel["iso_o"].eq(all_years_panel["iso_d"])
    assert len(sample) == EXPECTED_ICIO_ECONOMY_COUNT
    assert excluded_codes == ["ROW"]
    assert all_years_panel.duplicated(["iso_o", "iso_d", "year"]).sum() == 0
    assert len(all_years_panel) == expected_rows
    assert all_years_panel["year"].min() == EXPECTED_DTA_MIN_YEAR
    assert all_years_panel["year"].max() == EXPECTED_DTA_MAX_YEAR
    assert all_years_panel["year"].nunique() == expected_year_count
    assert all_years_panel["iso_o"].nunique() == EXPECTED_ICIO_ECONOMY_COUNT
    assert all_years_panel["iso_d"].nunique() == EXPECTED_ICIO_ECONOMY_COUNT
    assert "ROW" not in set(all_years_panel["iso_o"])
    assert "ROW" not in set(all_years_panel["iso_d"])
    assert set(all_years_panel["trade_agreement_dummy"].unique()) <= {0, 1}
    assert all_years_panel.loc[domestic, "trade_agreement_dummy"].eq(0).all()
    assert all_years_panel.loc[domestic, "agreement_applicable"].eq(0).all()
    assert all_years_panel.loc[~domestic, "agreement_applicable"].eq(1).all()
    assert "idealpoint_abs_distance" in all_years_panel.columns
    assert all_years_panel["idealpoint_abs_distance"].dropna().ge(0).all()
    assert all_years_panel.loc[domestic, "idealpoint_abs_distance"].eq(0).all()
    assert all_years_panel.groupby("year").size().eq(
        EXPECTED_ICIO_ECONOMY_COUNT ** 2
    ).all()

    symmetry = all_years_panel.groupby(["pair_a", "pair_b", "year"])[
        [
            "trade_agreement_dummy",
            "raw_trade_score",
            "raw_investment_score",
            "num_active_agreements",
            "agreement_id_list",
            "idealpoint_abs_distance",
        ]
    ].nunique(dropna=False)
    assert symmetry.le(1).all().all()
    inactive = all_years_panel["trade_agreement_dummy"].eq(0)
    assert all_years_panel.loc[inactive, "raw_trade_score"].eq(0).all()
    assert all_years_panel.loc[inactive, "raw_investment_score"].eq(0).all()
    assert count_2019_crosscheck_mismatches(
        all_years_panel, pair_year, set(sample["iso_code"])
    ) == 0


def run() -> None:
    ensure_directories()
    validate_country_pair_input()
    if not config.BILATERAL_PANEL_PATH.exists():
        raise FileNotFoundError(
            f"DTA bilateral panel not found: {config.BILATERAL_PANEL_PATH}. "
            "Run `python run_pipeline.py load` first."
        )

    aliases = load_iso_aliases()
    bilateral = read_csv(config.BILATERAL_PANEL_PATH)
    dta_source, active = prepare_active_agreements(bilateral, aliases)
    if not config.COUNTRY_PAIR_YEAR_INDICES_PATH.exists():
        raise FileNotFoundError(
            f"Country-pair raw scores not found: {config.COUNTRY_PAIR_YEAR_INDICES_PATH}. "
            "Run `python run_pipeline.py indices` first."
        )
    pair_scores = read_csv(config.COUNTRY_PAIR_YEAR_INDICES_PATH)
    active = attach_raw_scores(active, pair_scores, aliases)
    icio = prepare_icio(aliases)

    pair_year = build_icio_pair_year(icio, active)
    sample, excluded_codes = build_icio_economy_sample(icio, dta_source)
    all_years_panel = build_icio_economies_all_years_panel(sample, dta_source, active)
    expanded = build_expanded_union(dta_source, icio, active)
    mismatch = build_code_mismatch_report(dta_source, icio)
    diagnostics = build_diagnostics(
        icio,
        pair_year,
        all_years_panel,
        sample,
        excluded_codes,
        active,
        expanded,
        mismatch,
    )

    validate_outputs(
        pair_year,
        all_years_panel,
        sample,
        excluded_codes,
        active,
        expanded,
    )

    write_csv(active, config.DTA_ACTIVE_AGREEMENT_DUMMY_PATH)
    write_csv(pair_year, config.ICIO_PAIR_YEAR_DUMMY_PATH)
    write_csv(all_years_panel, config.ICIO_ECONOMIES_ALL_YEARS_DUMMY_PATH)
    write_csv(expanded, config.EXPANDED_UNION_PAIR_YEAR_DUMMY_PATH)
    write_csv(diagnostics, config.TRADE_AGREEMENT_DUMMY_DIAGNOSTICS_PATH)
    write_csv(mismatch, config.TRADE_AGREEMENT_DUMMY_CODE_REPORT_PATH)
    write_table_manifest()

    print(f"Wrote {len(active):,} active DTA pair-years")
    print(f"Wrote {len(pair_year):,} ICIO directed pair-years")
    print(
        f"Wrote {len(all_years_panel):,} ICIO-sample directed pair-years "
        f"for {len(sample)} economies; excluded {excluded_codes}"
    )
    print(f"Wrote {len(expanded):,} expanded union pair-years")
    print(f"Diagnostics: {config.TRADE_AGREEMENT_DUMMY_DIAGNOSTICS_PATH}")


if __name__ == "__main__":
    run()
