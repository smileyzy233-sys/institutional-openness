"""Prepare directional sector tariffs without zero-filling structural gaps."""

from __future__ import annotations

import argparse
from numbers import Number
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    load_matching_specs,
    normalize_iso3,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_tariff_path,
    resolve_years,
    validate_unique,
)


TARIFF_SOURCE_COLUMNS = ["iso_o", "iso_d", "sector_amne", "tariff"]
TARIFF_KEY = ["year", "iso_o1", "iso_d1", "sector_amne"]
CROSSWALK_COLUMNS = ["iso3_o", "iso_o", "country_o"]


def _is_missing_scalar(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _country_value_kind(value: object) -> str:
    if _is_missing_scalar(value):
        return "missing"
    if isinstance(value, (bool, np.bool_)):
        return "unsupported"
    if isinstance(value, Number):
        return "numeric"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "missing"
        try:
            float(text)
        except ValueError:
            return "string"
        return "numeric"
    return "unsupported"


def _detect_country_key_type(series: pd.Series, column: str) -> str:
    kinds = {_country_value_kind(value) for value in series.array}
    if "unsupported" in kinds:
        examples = [
            repr(value)
            for value in series.array
            if _country_value_kind(value) == "unsupported"
        ][:10]
        raise ValueError(
            f"Unsupported tariff country code values in {column}: {examples}"
        )
    present = kinds.difference({"missing"})
    if not present:
        raise ValueError(f"Tariff country key {column} contains only missing values")
    if present == {"numeric", "string"}:
        raise ValueError(
            f"Mixed tariff country code types in {column}; "
            "ISO3 strings and numeric country IDs cannot be combined"
        )
    return "numeric" if present == {"numeric"} else "iso3_string"


def _coerce_required_integer(
    series: pd.Series,
    label: str,
) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    invalid = series.notna() & values.isna()
    if invalid.any():
        examples = series.loc[invalid].drop_duplicates().head(10).tolist()
        raise ValueError(f"{label} must be numeric; invalid values={examples}")
    if values.isna().any():
        raise ValueError(f"{label} must not contain missing values")
    fractional = ~np.isclose(values.to_numpy(dtype=float) % 1, 0)
    if fractional.any():
        examples = values.loc[fractional].drop_duplicates().head(10).tolist()
        raise ValueError(
            f"{label} must contain integer-valued country/sector codes; "
            f"invalid values={examples}"
        )
    return values.astype("int64")


def _normalized_aliases(specs: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source, destination in specs.get("iso_aliases", {}).items():
        source_code = normalize_iso3(source)
        destination_code = normalize_iso3(destination)
        if not source_code or not destination_code:
            raise ValueError(
                f"Invalid ISO alias mapping: {source!r} -> {destination!r}"
            )
        aliases[source_code] = destination_code
    return aliases


def _load_country_code_lookup(
    project_dir: Path,
    specs: dict[str, Any],
) -> dict[str, int]:
    crosswalk_text = specs.get("dependent_identity_crosswalk")
    if not crosswalk_text:
        raise ValueError(
            "ISO3 tariff country keys require dependent_identity_crosswalk"
        )
    path = resolve_config_path(project_dir, str(crosswalk_text))
    if not path.exists():
        raise FileNotFoundError(f"Tariff country crosswalk not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".dta":
        crosswalk = pd.read_stata(path, convert_categoricals=False)
    elif suffix == ".csv":
        crosswalk = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(
            f"Unsupported tariff country crosswalk format: {path.suffix}"
        )
    require_columns(crosswalk.columns, CROSSWALK_COLUMNS, str(path))
    numeric_ids = _coerce_required_integer(
        crosswalk["iso_o"], f"{path.name}.iso_o"
    )
    aliases = _normalized_aliases(specs)
    lookup: dict[str, int] = {}

    def add_mapping(code: str, numeric_id: int) -> None:
        if not code:
            raise ValueError(f"{path.name}.iso3_o must not contain missing values")
        existing = lookup.get(code)
        if existing is not None and existing != numeric_id:
            raise ValueError(
                f"Conflicting tariff country crosswalk mapping for {code}: "
                f"{existing} versus {numeric_id}"
            )
        lookup[code] = numeric_id

    for raw_value, numeric_id in zip(
        crosswalk["iso3_o"].array,
        numeric_ids.array,
        strict=True,
    ):
        raw_code = normalize_iso3(raw_value)
        normalized_code = aliases.get(raw_code, raw_code)
        add_mapping(raw_code, int(numeric_id))
        add_mapping(normalized_code, int(numeric_id))
    return lookup


def normalize_tariff_country_keys(
    tariff: pd.DataFrame,
    project_dir: Path,
    specs: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize numeric or ISO3 tariff country keys to integer country IDs."""
    require_columns(tariff.columns, ["iso_o", "iso_d"], "tariff data")
    key_types = {
        column: _detect_country_key_type(tariff[column], column)
        for column in ["iso_o", "iso_d"]
    }
    if len(set(key_types.values())) != 1:
        raise ValueError(
            "Tariff origin and destination country keys use inconsistent types: "
            f"{key_types}"
        )
    source_key_type = key_types["iso_o"]
    out = tariff.copy()
    diagnostics = {
        "source_key_type": source_key_type,
        "output_key_type": "numeric_country_id",
        "origin_unmapped": 0,
        "destination_unmapped": 0,
    }
    if source_key_type == "numeric":
        out["iso_o1"] = _coerce_required_integer(
            out["iso_o"], "Tariff iso_o"
        )
        out["iso_d1"] = _coerce_required_integer(
            out["iso_d"], "Tariff iso_d"
        )
    else:
        lookup = _load_country_code_lookup(project_dir, specs)
        aliases = _normalized_aliases(specs)
        unmapped_by_column: dict[str, list[str]] = {}
        for source, target, direction in [
            ("iso_o", "iso_o1", "origin"),
            ("iso_d", "iso_d1", "destination"),
        ]:
            raw_codes = out[source].map(normalize_iso3)
            normalized_codes = raw_codes.map(
                lambda code: aliases.get(code, code)
            )
            mapped = normalized_codes.map(lookup)
            missing = mapped.isna()
            unmapped = sorted(
                {
                    code if code else "<missing>"
                    for code in raw_codes.loc[missing].tolist()
                }
            )
            unmapped_by_column[direction] = unmapped
            diagnostics[f"{direction}_unmapped"] = len(unmapped)
            out[target] = mapped
        errors = []
        if unmapped_by_column["origin"]:
            errors.append(
                "Unmapped tariff origin ISO codes: "
                f"{unmapped_by_column['origin'][:10]}"
            )
        if unmapped_by_column["destination"]:
            errors.append(
                "Unmapped tariff destination ISO codes: "
                f"{unmapped_by_column['destination'][:10]}"
            )
        if errors:
            raise ValueError("; ".join(errors))
        out["iso_o1"] = _coerce_required_integer(
            out["iso_o1"], "Tariff iso_o1"
        )
        out["iso_d1"] = _coerce_required_integer(
            out["iso_d1"], "Tariff iso_d1"
        )
    out = out.drop(columns=["iso_o", "iso_d"])
    return out, diagnostics


def prepare_tariff(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_tariff_path(project_dir, specs, year)
    if not path.exists():
        raise FileNotFoundError(f"Missing tariff file for {year}: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        tariff = pd.read_csv(
            path, usecols=TARIFF_SOURCE_COLUMNS, low_memory=False
        )
    elif suffix == ".dta":
        tariff = pd.read_stata(
            path,
            columns=TARIFF_SOURCE_COLUMNS,
            convert_categoricals=False,
        )
    else:
        raise ValueError(
            f"Unsupported tariff format for {year}: {path.suffix}. "
            "Expected .csv or .dta."
        )
    require_columns(tariff.columns, TARIFF_SOURCE_COLUMNS, str(path))
    tariff, key_diagnostics = normalize_tariff_country_keys(
        tariff, project_dir, specs
    )
    tariff.insert(0, "year", np.int16(year))
    tariff["sector_amne"] = _coerce_required_integer(
        tariff["sector_amne"], "Tariff sector_amne"
    )

    values = pd.to_numeric(tariff["tariff"], errors="coerce")
    invalid_tariffs = tariff["tariff"].notna() & values.isna()
    if invalid_tariffs.any():
        examples = (
            tariff.loc[invalid_tariffs, "tariff"]
            .drop_duplicates()
            .head(10)
            .tolist()
        )
        raise ValueError(
            f"Tariff values must be numeric in {path}; invalid values={examples}"
        )
    if values.isna().any():
        raise ValueError(f"Tariff file contains missing tariff values: {path}")
    negative_count = int(values.lt(0).sum())
    if negative_count:
        raise ValueError(f"Tariff file contains negative values: {path}")
    tariff["tariff"] = values

    duplicate_count = validate_unique(tariff, TARIFF_KEY, f"tariff {year}")
    observed = sorted(int(value) for value in tariff["sector_amne"].unique())
    acceptance = specs.get("acceptance", {}).get(str(year), {})
    expected_range = acceptance.get("tariff_sectors")
    if expected_range:
        expected = list(range(int(expected_range[0]), int(expected_range[1]) + 1))
        if observed != expected:
            raise ValueError(
                f"Tariff sectors for {year} must be {expected_range[0]}-"
                f"{expected_range[1]}; observed={observed}"
            )
    if 20 in observed:
        raise ValueError("Tariff sector 20 must remain structurally absent")

    tariff["match_tariff"] = np.int8(1)
    diagnostics = {
        "source": str(path),
        "source_format": suffix.removeprefix("."),
        **key_diagnostics,
        "year": year,
        "rows": len(tariff),
        "duplicate_keys": duplicate_count,
        "sectors": observed,
        "missing_tariff": int(tariff["tariff"].isna().sum()),
        "negative_tariff": negative_count,
    }
    return tariff[TARIFF_KEY + ["tariff", "match_tariff"]], diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    resolve_years(specs, [args.year])
    data, diagnostics = prepare_tariff(root, specs, args.year)
    print({**diagnostics, "columns": list(data.columns)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
