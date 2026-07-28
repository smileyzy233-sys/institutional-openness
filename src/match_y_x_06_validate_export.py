"""Validate and export the control-free trade and MP Y-X datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from match_y_x_common import (
    Y_KEY,
    base_cli_parser,
    check_output_collisions,
    current_git_commit,
    file_sha256,
    forbidden_y_x_columns,
    load_matching_specs,
    load_sibling_script,
    parse_year_arguments,
    project_directory,
    resolve_config_path,
    resolve_years,
    validate_csv_dta_pair,
    validate_unique,
    write_csv_dta,
    y_x_output_paths,
)


def _validate_dataset(
    data: pd.DataFrame,
    equation: str,
    x_column: str,
    year: int,
    specs: dict[str, Any],
) -> dict[str, Any]:
    validate_unique(data, Y_KEY, f"{equation} Y-X {year}")
    forbidden = forbidden_y_x_columns(data.columns)
    if forbidden:
        raise ValueError(f"{equation} Y-X contains forbidden controls: {forbidden}")
    if data["value"].isna().any() or data["value"].lt(0).any():
        raise ValueError(f"{equation} Y-X has missing or negative dependent values")
    match_rate = float(data["matched_x"].mean())
    if match_rate != 1.0 or data[x_column].isna().any():
        raise ValueError(
            f"{equation} X match is incomplete for {year}: match_rate={match_rate}"
        )
    domestic = data["is_domestic_pair"].eq(1)
    if data.loc[domestic, x_column].ne(0).any():
        raise ValueError(f"{equation} domestic {x_column} values must be zero")
    acceptance = specs.get("acceptance", {}).get(str(year), {})
    expected_rows = acceptance.get(f"{equation}_rows_after_row_policy")
    if expected_rows is not None and len(data) != int(expected_rows):
        raise ValueError(
            f"{equation} row acceptance failed for {year}: "
            f"expected={expected_rows}, observed={len(data)}"
        )
    return {
        "equation": equation,
        "year": year,
        "rows": len(data),
        "columns": list(data.columns),
        "duplicate_keys": 0,
        "x_column": x_column,
        "x_match_rate": match_rate,
        "x_missing": int(data[x_column].isna().sum()),
        "dependent_zero_rate": float(data["value"].eq(0).mean()),
        "domestic_rows": int(domestic.sum()),
        "iso_bridge_rows": int(data["uses_iso_bridge"].sum()),
    }


def _write_year(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
    trade: pd.DataFrame,
    mp: pd.DataFrame,
    *,
    output_root: Path | str | None,
    force: bool,
) -> dict[str, Any]:
    paths = y_x_output_paths(project_dir, specs, year, output_root)
    targets = [
        paths["trade_csv"],
        paths["trade_dta"],
        paths["mp_csv"],
        paths["mp_dta"],
        paths["diagnostics"],
        paths["manifest"],
    ]
    check_output_collisions(targets, force)
    trade_diag = _validate_dataset(
        trade, "trade", specs["equations"]["trade"]["x_column"], year, specs
    )
    mp_diag = _validate_dataset(
        mp, "mp", specs["equations"]["mp"]["x_column"], year, specs
    )
    write_csv_dta(trade, paths["trade_csv"], paths["trade_dta"])
    write_csv_dta(mp, paths["mp_csv"], paths["mp_dta"])
    trade_pair = validate_csv_dta_pair(
        paths["trade_csv"],
        paths["trade_dta"],
        Y_KEY + ["value", "raw_trade_score"],
    )
    mp_pair = validate_csv_dta_pair(
        paths["mp_csv"],
        paths["mp_dta"],
        Y_KEY + ["value", "raw_mp_score"],
    )
    diagnostics = {
        "pipeline": "match_y_x",
        "year": year,
        "trade": trade_diag,
        "mp": mp_diag,
        "csv_dta_validation": {"trade": trade_pair, "mp": mp_pair},
    }
    paths["diagnostics"].write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    inputs = {
        equation: resolve_config_path(
            project_dir,
            equation_spec["dependent_path_template"],
            year=year,
        )
        for equation, equation_spec in specs["equations"].items()
    }
    inputs["pair_year_source"] = resolve_config_path(
        project_dir, specs["pair_year_source"]
    )
    manifest = {
        "pipeline": "match_y_x",
        "matching_schema_version": specs["schema_version"],
        "year": year,
        "config_path": str(Path(specs["_config_path"]).relative_to(project_dir)),
        "input_paths": {
            name: str(path.relative_to(project_dir)) for name, path in inputs.items()
        },
        "input_sha256": {name: file_sha256(path) for name, path in inputs.items()},
        "input_rows": {
            "trade": trade_diag["rows"],
            "mp": mp_diag["rows"],
        },
        "input_columns": {
            "trade": trade_diag["columns"],
            "mp": mp_diag["columns"],
        },
        "merge_keys": ["year", "iso_o_match", "iso_d_match"],
        "row_policy": specs["row_policy"],
        "iso_aliases": specs["iso_aliases"],
        "output_rows": {"trade": len(trade), "mp": len(mp)},
        "output_sha256": {
            "trade_csv": trade_pair["csv_sha256"],
            "trade_dta": trade_pair["dta_sha256"],
            "mp_csv": mp_pair["csv_sha256"],
            "mp_dta": mp_pair["dta_sha256"],
        },
        "duplicate_counts": {"trade": 0, "mp": 0},
        "match_rates": {
            "trade_x": trade_diag["x_match_rate"],
            "mp_x": mp_diag["x_match_rate"],
        },
        "missing_rates": {
            "trade_x": float(trade["raw_trade_score"].isna().mean()),
            "mp_x": float(mp["raw_mp_score"].isna().mean()),
        },
        "code_commit_if_available": current_git_commit(project_dir),
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"paths": {key: str(value) for key, value in paths.items()}, **diagnostics}


def run(
    *,
    project_dir: Path | str | None = None,
    years: list[int] | None = None,
    output_root: Path | str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    root = (
        Path(project_dir).resolve()
        if project_dir is not None
        else project_directory()
    )
    specs = load_matching_specs(root)
    selected_years = resolve_years(specs, years)
    validate_sources = load_sibling_script("match_y_x_01_validate_sources.py")
    preflight = validate_sources.validate_sources(
        root, specs, selected_years, output_root=output_root
    )
    if dry_run:
        plan = {
            "pipeline": "match_y_x",
            "dry_run": True,
            "years": selected_years,
            "equations": {
                name: {
                    "dependent_path": str(
                        resolve_config_path(
                            root, equation["dependent_path_template"], year=year
                        )
                    ),
                    "x_column": equation["x_column"],
                }
                for name, equation in specs["equations"].items()
                for year in selected_years[:1]
            },
            "row_policy": specs["row_policy"],
            "iso_aliases": specs["iso_aliases"],
            "outputs": preflight["outputs"],
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return plan

    all_targets: list[Path] = []
    for year in selected_years:
        paths = y_x_output_paths(root, specs, year, output_root)
        all_targets.extend(
            paths[name]
            for name in [
                "trade_csv",
                "trade_dta",
                "mp_csv",
                "mp_dta",
                "diagnostics",
                "manifest",
            ]
        )
    check_output_collisions(all_targets, force)

    prepare_y = load_sibling_script("match_y_x_02_prepare_y.py")
    prepare_x = load_sibling_script("match_y_x_03_prepare_x.py")
    build_trade = load_sibling_script("match_y_x_04_build_trade.py")
    build_mp = load_sibling_script("match_y_x_05_build_mp.py")
    results: dict[str, Any] = {"pipeline": "match_y_x", "years": {}}
    for year in selected_years:
        x_data = prepare_x.prepare_x(root, specs, year)
        trade = build_trade.build_trade(
            prepare_y.prepare_y(root, specs, "trade", year),
            x_data,
        )
        mp = build_mp.build_mp(
            prepare_y.prepare_y(root, specs, "mp", year),
            x_data,
        )
        results["years"][str(year)] = _write_year(
            root,
            specs,
            year,
            trade,
            mp,
            output_root=output_root,
            force=force,
        )
    return results


def main() -> int:
    parser = base_cli_parser(__doc__)
    args = parser.parse_args()
    result = run(
        years=parse_year_arguments(args.years),
        output_root=args.output_root,
        dry_run=args.dry_run,
        force=args.force,
    )
    if not args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
