"""Chunk-read and prepare unselected Gravity control candidates."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from match_y_x_common import (
    X_KEY,
    load_matching_specs,
    project_directory,
    require_columns,
    resolve_config_path,
    resolve_years,
    validate_unique,
)


ONE_MINUS_PATTERN = re.compile(r"^1\s*-\s*([A-Za-z_][A-Za-z0-9_]*)$")
PRODUCT_PATTERN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)$"
)


def materialize_derived_candidates(
    data: pd.DataFrame,
    derived_candidates: dict[str, str],
) -> pd.DataFrame:
    """Create the small, configuration-declared set of safe derived fields."""

    out = data.copy()
    for variable, expression in derived_candidates.items():
        one_minus = ONE_MINUS_PATTERN.fullmatch(expression.strip())
        product = PRODUCT_PATTERN.fullmatch(expression.strip())
        if one_minus:
            source = one_minus.group(1)
            require_columns(out.columns, [source], expression)
            out[variable] = 1.0 - pd.to_numeric(out[source], errors="coerce")
        elif product:
            left, right = product.groups()
            require_columns(out.columns, [left, right], expression)
            out[variable] = pd.to_numeric(
                out[left], errors="coerce"
            ) * pd.to_numeric(out[right], errors="coerce")
        else:
            raise ValueError(
                "Unsupported derived Gravity candidate expression "
                f"for {variable}: {expression!r}"
            )
    return out


def prepare_gravity(
    project_dir: Path,
    specs: dict[str, Any],
    years: list[int],
    target_iso_codes: Iterable[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_config_path(project_dir, specs["gravity_path"])
    if not path.exists():
        raise FileNotFoundError(f"Missing Gravity file: {path}")
    gravity_spec = specs["gravity"]
    columns = list(gravity_spec["read_columns"])
    codes = {str(code) for code in target_iso_codes if str(code)}
    parts: list[pd.DataFrame] = []
    scanned_rows = 0
    for chunk in pd.read_csv(
        path,
        usecols=columns,
        chunksize=int(gravity_spec.get("chunksize", 200_000)),
        low_memory=False,
    ):
        scanned_rows += len(chunk)
        selected = chunk.loc[
            chunk["year"].isin(years)
            & chunk["country_exists_o"].eq(1)
            & chunk["country_exists_d"].eq(1)
            & chunk["iso3_o"].isin(codes)
            & chunk["iso3_d"].isin(codes)
        ]
        if not selected.empty:
            parts.append(selected)
    if not parts:
        raise ValueError(
            f"No Gravity rows matched years={years} and {len(codes)} target economies"
        )
    data = pd.concat(parts, ignore_index=True)
    data = data.rename(
        columns={"iso3_o": "iso_o_match", "iso3_d": "iso_d_match"}
    )
    validate_unique(data, X_KEY, "filtered Gravity controls")
    expected_rows = len(codes) ** 2 * len(years)
    if len(data) != expected_rows:
        observed = {
            int(year): int(count)
            for year, count in data.groupby("year").size().items()
        }
        raise ValueError(
            "Filtered Gravity data does not form a complete directed square: "
            f"expected={expected_rows}, observed={observed}"
        )
    candidate_controls = list(gravity_spec["candidate_controls"])
    derived_candidates = dict(gravity_spec.get("derived_candidates", {}))
    unknown_derived = sorted(
        set(derived_candidates).difference(candidate_controls)
    )
    if unknown_derived:
        raise ValueError(
            "Derived Gravity candidates must also be configured as candidates: "
            f"{unknown_derived}"
        )
    keep = X_KEY + candidate_controls
    base_candidates = [
        column
        for column in candidate_controls
        if column not in derived_candidates
    ]
    require_columns(data.columns, base_candidates, str(path))
    data = materialize_derived_candidates(
        data,
        derived_candidates,
    )
    data["match_gravity"] = np.int8(1)
    for family in ["entry_cost", "entry_proc", "entry_time", "entry_tp"]:
        data[f"match_{family}"] = (
            data[[f"{family}_o", f"{family}_d"]].notna().all(axis=1).astype(np.int8)
        )
    data["match_comlang"] = data["comlang_off"].notna().astype(np.int8)
    data["match_comrelig"] = data["comrelig"].notna().astype(np.int8)
    match_columns = [
        "match_gravity",
        "match_entry_cost",
        "match_entry_proc",
        "match_entry_time",
        "match_entry_tp",
        "match_comlang",
        "match_comrelig",
    ]
    diagnostics = {
        "source": str(path),
        "years": years,
        "rows_scanned": scanned_rows,
        "rows_selected": len(data),
        "target_iso_count": len(codes),
        "duplicate_keys": 0,
        "candidate_missing_rates": {
            column: float(data[column].isna().mean())
            for column in candidate_controls
        },
        "derived_candidates": derived_candidates,
    }
    return data[keep + match_columns], diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", required=True, type=int)
    args = parser.parse_args()
    root = project_directory()
    specs = load_matching_specs(root)
    years = resolve_years(specs, args.years)
    pair_path = resolve_config_path(root, specs["pair_year_source"])
    pair = pd.read_csv(pair_path, usecols=["iso_o", "iso_d", "year"])
    pair = pair.loc[pair["year"].isin(years)]
    codes = set(pair["iso_o"]) | set(pair["iso_d"])
    data, diagnostics = prepare_gravity(root, specs, years, codes)
    print({**diagnostics, "columns": list(data.columns)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
