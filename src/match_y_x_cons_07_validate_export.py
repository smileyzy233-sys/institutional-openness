"""Validate and export configured control matches on top of Y-X data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from match_y_x_common import (
    Y_KEY,
    assert_stata_columns,
    check_output_collisions,
    current_git_commit,
    file_sha256,
    load_matching_specs,
    load_sibling_script,
    parse_year_arguments,
    project_directory,
    resolve_config_path,
    resolve_tariff_path,
    resolve_years,
    validate_csv_dta_pair,
    validate_unique,
    write_csv_dta,
    y_x_output_paths,
)
from match_y_x_cons_common import (
    assert_mp_has_no_trade_controls,
    assert_no_final_sample_flags,
    control_output_paths,
    get_control_spec,
    read_y_x_base,
)


TARIFF_KEY = ["year", "iso_o1", "iso_d1", "sector_amne"]
BINARY_GRAVITY_FIELDS = {
    "gatt_o",
    "gatt_d",
    "both_gatt",
    "wto_o",
    "wto_d",
    "both_wto",
    "eu_o",
    "eu_d",
    "both_eu",
    "fta_wto",
    "fta_wto_raw",
    "comlang_off",
    "comlang_ethno",
    "comleg_pretrans",
    "comleg_posttrans",
    "transition_legalchange",
    "comcol",
    "col45",
    "heg_o",
    "heg_d",
    "col_dep_ever",
    "col_dep",
    "col_dep_end_conflict",
    "sibling_ever",
    "sibling",
    "sib_conflict",
}
CATEGORICAL_GRAVITY_FIELDS = {
    "rta_coverage",
    "rta_type",
    "legal_old_o",
    "legal_old_d",
    "legal_new_o",
    "legal_new_d",
    "empire",
}


def _equation_targets(paths: dict[str, Path], equations: list[str]) -> list[Path]:
    targets = [
        paths["diagnostics"],
        paths["dictionary"],
        paths["manifest"],
        paths["readme"],
    ]
    for equation in equations:
        targets.extend([paths[f"{equation}_csv"], paths[f"{equation}_dta"]])
    return targets


def _validate_equation(
    data: pd.DataFrame,
    equation: str,
    year: int,
) -> dict[str, Any]:
    validate_unique(data, Y_KEY, f"{equation} Y-X-controls {year}")
    assert_stata_columns(data.columns)
    assert_no_final_sample_flags(data)
    if data["value"].isna().any() or data["value"].lt(0).any():
        raise ValueError(f"{equation} contains missing or negative dependent values")
    x_column = "raw_trade_score" if equation == "trade" else "raw_mp_score"
    if data[x_column].isna().any():
        raise ValueError(f"{equation} contains missing {x_column}")
    if equation == "trade":
        sector20 = data["sector_amne"].eq(20)
        if data.loc[sector20, "tariff"].notna().any():
            raise ValueError("ICIO sector 20 tariffs must remain missing")
        if data.loc[sector20, "match_tariff"].ne(0).any():
            raise ValueError("ICIO sector 20 must have match_tariff=0")
    else:
        assert_mp_has_no_trade_controls(data)
    return {
        "rows": len(data),
        "columns": list(data.columns),
        "duplicate_keys": 0,
        "dependent_zero_rate": float(data["value"].eq(0).mean()),
    }


def _legacy_overlap(
    project_dir: Path,
    equation: str,
    year: int,
    data: pd.DataFrame,
) -> dict[str, Any]:
    old_name = (
        f"trade_cost_{year}_matched.csv"
        if equation == "trade"
        else f"mp_cost_{year}_matched.csv"
    )
    old_path = project_dir / "result" / f"regression_{year}" / old_name
    if not old_path.exists():
        raise FileNotFoundError(f"Legacy comparison file is missing: {old_path}")
    old = pd.read_csv(old_path, low_memory=False)
    if len(old) != len(data):
        raise AssertionError(
            f"Legacy {equation} row mismatch: old={len(old)}, new={len(data)}"
        )
    common = [column for column in old.columns if column in data.columns]
    required = Y_KEY + [
        "value",
        "raw_trade_score" if equation == "trade" else "raw_mp_score",
        "trade_agreement_dummy",
        "idealpoint_abs_distance",
    ]
    missing_required = sorted(set(required).difference(common))
    if missing_required:
        raise AssertionError(
            f"Legacy overlap is missing required fields: {missing_required}"
        )
    mismatch_counts: dict[str, int] = {}
    for column in common:
        left = old[column]
        right = data[column]
        if pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
            equal = np.isclose(
                pd.to_numeric(left, errors="coerce"),
                pd.to_numeric(right, errors="coerce"),
                rtol=0,
                atol=1e-7,
                equal_nan=True,
            )
        else:
            equal = left.fillna("").astype(str).eq(right.fillna("").astype(str))
        mismatch_counts[column] = int((~np.asarray(equal)).sum())
    mismatched = {key: value for key, value in mismatch_counts.items() if value}
    if mismatched:
        raise AssertionError(
            f"Legacy overlapping fields differ for {equation} {year}: {mismatched}"
        )
    return {
        "legacy_path": str(old_path.relative_to(project_dir)),
        "rows": len(data),
        "overlap_columns": common,
        "mismatch_counts": mismatch_counts,
    }


def _dictionary_rows(
    project_dir: Path,
    equation: str,
    data: pd.DataFrame,
    equation_spec: dict[str, Any],
    specs: dict[str, Any],
    year: int,
) -> list[dict[str, Any]]:
    selected = set(equation_spec["selected_controls"])
    candidates = set(equation_spec["candidate_controls"])
    gravity_candidates = set(specs["gravity"]["candidate_controls"])
    derived_candidates = dict(
        specs["gravity"].get("derived_candidates", {})
    )
    dependent_path = specs["equations"][equation][
        "dependent_path_template"
    ].format(year=year)
    pair_path = specs["pair_year_source"]
    tariff_path = str(
        resolve_tariff_path(project_dir, specs, year).relative_to(project_dir)
    )
    gravity_path = specs["gravity_path"]
    rows: list[dict[str, Any]] = []
    for variable in data.columns:
        source_file = dependent_path
        source_column = variable
        matching_keys = "year + iso_o + iso_d + sector_amne"
        transformation = "none"
        unit_or_scale = "source scale"
        note = ""
        if variable == "value":
            role = "dependent"
            selected_status = "dependent"
        elif variable in {"raw_trade_score", "raw_mp_score"}:
            role = "core_x"
            selected_status = "core_x"
            source_file = pair_path
            matching_keys = "year + iso_o_match + iso_d_match"
        elif variable in selected:
            role = "control"
            selected_status = "confirmed_control"
        elif variable in candidates:
            role = "control_candidate"
            selected_status = (
                "derived_candidate"
                if variable in derived_candidates
                else "candidate_control"
            )
            note = "Matched candidate only; not selected for the final regression."
        else:
            role = "diagnostic"
            selected_status = "diagnostic"
        if variable == "tariff":
            source_file = tariff_path
            matching_keys = "year + iso_o1 + iso_d1 + sector_amne"
        elif variable in {"trade_agreement_dummy", "idealpoint_abs_distance"}:
            source_file = pair_path
            matching_keys = "year + iso_o_match + iso_d_match"
        elif variable in gravity_candidates:
            source_file = gravity_path
            matching_keys = "year + iso_o_match + iso_d_match"
        if variable in derived_candidates:
            expression = derived_candidates[variable]
            source_column = (
                expression.split("-", maxsplit=1)[1].strip()
                if expression.strip().startswith("1") and "-" in expression
                else ", ".join(
                    part.strip() for part in expression.split("*")
                )
            )
            transformation = expression
        if variable == "cultural_distance_religion":
            unit_or_scale = "0-1 distance"
            note += " Higher values indicate less religious proximity."
        elif variable == "comrelig":
            unit_or_scale = "0-1 proximity"
            note += " Higher values indicate greater religious proximity."
        elif variable in BINARY_GRAVITY_FIELDS:
            unit_or_scale = "0/1"
        elif variable == "entry_cost_o" or variable == "entry_cost_d":
            unit_or_scale = "% of GNI per capita"
            note += " Business start-up cost; not a customs/border measure."
        elif variable.startswith("entry_proc_"):
            unit_or_scale = "number of start-up procedures"
            note += " Business registration environment; not customs clearance."
        elif variable.startswith("entry_time_"):
            unit_or_scale = "days to start a business"
            note += " Business registration environment; not customs clearance."
        elif variable.startswith("entry_tp_"):
            unit_or_scale = "start-up days + procedures"
            note += " Composite business start-up measure; not customs clearance."
        elif variable.startswith("gmt_offset_2020_"):
            unit_or_scale = "hours from GMT (2020)"
        elif variable in {"col_dep_end_year", "sever_year"}:
            unit_or_scale = "calendar year"
        elif variable in CATEGORICAL_GRAVITY_FIELDS:
            unit_or_scale = "CEPII numeric category code"
            note += " Retains the CEPII CSV category code."
        elif variable == "scaled_sci_2021":
            note += " Higher values indicate stronger social connectedness."
        elif variable == "diplo_disagreement":
            note += " Higher values indicate greater UN-vote disagreement."
        if variable == "trade_agreement_dummy":
            unit_or_scale = "0/1"
        if variable.startswith(("match_", "sample_", "available_", "is_", "uses_")):
            unit_or_scale = "0/1 diagnostic flag"
            note = "Missing control values are not zero-filled."
        rows.append(
            {
                "variable": variable,
                "equation": equation,
                "role": role,
                "source_file": source_file,
                "source_column": source_column,
                "matching_keys": matching_keys,
                "transformation": transformation,
                "unit_or_scale": unit_or_scale,
                "selected_status": selected_status,
                "missing_policy": "preserve missing; do not fill with zero",
                "note": note,
            }
        )
    return rows


def _diagnostic_rows(
    equation: str,
    year: int,
    data: pd.DataFrame,
    merges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for merge in merges:
        rows.append(
            {
                "equation": equation,
                "year": year,
                "source": merge["source"],
                "check": "merge_match_rate",
                "value": merge["rows_after"],
                "rate": merge["match_rate"],
                "note": (
                    f"rows_before={merge['rows_before']}; "
                    f"rows_after={merge['rows_after']}; "
                    f"right_key_duplicates={merge['right_key_duplicates']}"
                ),
            }
        )
        for variable, rate in merge["missing_rates"].items():
            rows.append(
                {
                    "equation": equation,
                    "year": year,
                    "source": merge["source"],
                    "check": f"missing_rate:{variable}",
                    "value": int(data[variable].isna().sum()),
                    "rate": rate,
                    "note": "Missing values preserved; not filled with zero.",
                }
            )
    rows.extend(
        [
            {
                "equation": equation,
                "year": year,
                "source": "output",
                "check": "rows",
                "value": len(data),
                "rate": 1.0,
                "note": "Y-X row count retained.",
            },
            {
                "equation": equation,
                "year": year,
                "source": "output",
                "check": "dependent_zero_rate",
                "value": int(data["value"].eq(0).sum()),
                "rate": float(data["value"].eq(0).mean()),
                "note": "Dependent values remain in levels.",
            },
        ]
    )
    return rows


def _write_readme(
    path: Path,
    control_spec: str,
    year: int,
    configured: dict[str, Any],
) -> None:
    lines = [
        f"# {control_spec}: {year} control-match output",
        "",
        "These files add controls to the separately built Y-X datasets. They do not run regressions.",
        "",
        "Missing tariff, political-distance, Gravity, and candidate values are preserved and never filled with zero.",
        "",
    ]
    for equation in configured["equations"]:
        spec = configured[equation]
        lines.extend(
            [
                f"## {equation}",
                "",
                "Confirmed controls: "
                + (", ".join(spec["selected_controls"]) or "none"),
                "",
                "Matched candidates (not final selections): "
                + (", ".join(spec["candidate_controls"]) or "none"),
                "",
            ]
        )
    lines.extend(
        [
            "The `trade_candidate_pool_v1` candidate variables are available for later research decisions only.",
            "The CEPII `entry_*` fields measure business start-up procedures, cost, and time; they are not customs-clearance or border-efficiency measures.",
            "Categorical Gravity fields retain the numeric codes in the CEPII CSV; use the supplied CEPII label files where available.",
            "Source documentation: https://www.cepii.fr/DATA_DOWNLOAD/gravity/doc/Gravity_documentation.pdf",
            "No `sample_trade_main` or `sample_mp_main` flag is produced.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_year(
    project_dir: Path,
    specs: dict[str, Any],
    control_spec_name: str,
    control_spec: dict[str, Any],
    year: int,
    datasets: dict[str, pd.DataFrame],
    merge_diagnostics: dict[str, list[dict[str, Any]]],
    input_paths: dict[str, Path],
    source_diagnostics: dict[str, Any],
    *,
    output_root: Path | str | None,
    force: bool,
) -> dict[str, Any]:
    equations = control_spec["equations"]
    paths = control_output_paths(
        project_dir, specs, control_spec_name, year, output_root
    )
    check_output_collisions(_equation_targets(paths, equations), force)
    validation: dict[str, Any] = {}
    csv_dta: dict[str, Any] = {}
    legacy: dict[str, Any] = {}
    dictionary_rows: list[dict[str, Any]] = []
    diagnostics_rows: list[dict[str, Any]] = []
    for equation in equations:
        data = datasets[equation]
        validation[equation] = _validate_equation(data, equation, year)
        if control_spec_name == "legacy_2019_v1":
            legacy[equation] = _legacy_overlap(
                project_dir, equation, year, data
            )
        write_csv_dta(
            data, paths[f"{equation}_csv"], paths[f"{equation}_dta"]
        )
        x_column = (
            "raw_trade_score" if equation == "trade" else "raw_mp_score"
        )
        core = Y_KEY + ["value", x_column]
        controls = (
            control_spec[equation]["selected_controls"]
            + control_spec[equation]["candidate_controls"]
        )
        csv_dta[equation] = validate_csv_dta_pair(
            paths[f"{equation}_csv"],
            paths[f"{equation}_dta"],
            core + controls,
        )
        dictionary_rows.extend(
            _dictionary_rows(
                project_dir,
                equation,
                data,
                control_spec[equation],
                specs,
                year,
            )
        )
        diagnostics_rows.extend(
            _diagnostic_rows(
                equation, year, data, merge_diagnostics[equation]
            )
        )
    tariff_diagnostics = source_diagnostics.get("tariff")
    if isinstance(tariff_diagnostics, dict):
        for check, value in tariff_diagnostics.items():
            if check == "year":
                continue
            if isinstance(value, (list, dict)):
                rendered_value: Any = json.dumps(value, ensure_ascii=False)
            else:
                rendered_value = value
            diagnostics_rows.append(
                {
                    "equation": "trade",
                    "year": year,
                    "source": "tariff_preparation",
                    "check": check,
                    "value": rendered_value,
                    "rate": np.nan,
                    "note": "Tariff source and key-normalization diagnostic.",
                }
            )
    diagnostics = pd.DataFrame(diagnostics_rows)
    dictionary = pd.DataFrame(dictionary_rows)
    diagnostics.to_csv(paths["diagnostics"], index=False, encoding="utf-8-sig")
    dictionary.to_csv(paths["dictionary"], index=False, encoding="utf-8-sig")
    _write_readme(paths["readme"], control_spec_name, year, control_spec)

    selected_controls = {
        equation: control_spec[equation]["selected_controls"]
        for equation in equations
    }
    candidate_controls = {
        equation: control_spec[equation]["candidate_controls"]
        for equation in equations
    }
    manifest = {
        "equation": equations if len(equations) > 1 else equations[0],
        "year": year,
        "control_spec": control_spec_name,
        "matching_schema_version": specs["schema_version"],
        "input_paths": {
            name: str(path.relative_to(project_dir))
            for name, path in input_paths.items()
        },
        "input_sha256": {
            name: file_sha256(path) for name, path in input_paths.items()
        },
        "input_rows": {
            **{
                equation: len(datasets[equation]) for equation in equations
            },
            **{
                name: details.get("rows", details.get("rows_selected"))
                for name, details in source_diagnostics.items()
                if isinstance(details, dict)
            },
        },
        "input_columns": {
            equation: list(datasets[equation].columns)
            for equation in equations
        },
        "merge_keys": {
            "pair_controls": ["year", "iso_o_match", "iso_d_match"],
            "tariff": ["year", "iso_o1", "iso_d1", "sector_amne"],
            "gravity": ["year", "iso_o_match", "iso_d_match"],
        },
        "output_rows": {
            equation: len(datasets[equation]) for equation in equations
        },
        "output_sha256": {
            f"{equation}_{suffix}": csv_dta[equation][f"{suffix}_sha256"]
            for equation in equations
            for suffix in ["csv", "dta"]
        },
        "duplicate_counts": {
            equation: 0 for equation in equations
        },
        "match_rates": {
            f"{equation}:{item['source']}": item["match_rate"]
            for equation in equations
            for item in merge_diagnostics[equation]
        },
        "missing_rates": {
            equation: {
                column: float(datasets[equation][column].isna().mean())
                for column in (
                    selected_controls[equation]
                    + candidate_controls[equation]
                )
                if column in datasets[equation]
            }
            for equation in equations
        },
        "iso_aliases": specs["iso_aliases"],
        "row_policy": specs["row_policy"],
        "selected_controls": selected_controls,
        "candidate_controls": candidate_controls,
        "transformations": specs["gravity"]["derived_candidates"],
        "source_diagnostics": source_diagnostics,
        "code_commit_if_available": current_git_commit(project_dir),
        "legacy_overlap_validation": legacy or None,
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "paths": {
            key: str(value)
            for key, value in paths.items()
            if key == "directory"
            or key in {"diagnostics", "dictionary", "manifest", "readme"}
            or any(key.startswith(equation) for equation in equations)
        },
        "validation": validation,
        "legacy_overlap_validation": legacy or None,
    }


def _preflight_paths(
    project_dir: Path,
    specs: dict[str, Any],
    control_spec_name: str,
    control_spec: dict[str, Any],
    years: list[int],
    output_root: Path | str | None,
) -> dict[str, Any]:
    inputs: list[str] = []
    outputs: list[str] = []
    for year in years:
        yx_paths = y_x_output_paths(project_dir, specs, year, output_root)
        for equation in control_spec["equations"]:
            path = yx_paths[f"{equation}_csv"]
            if not path.exists():
                raise FileNotFoundError(
                    f"Missing {equation} Y-X input for {year}: {path}"
                )
            inputs.append(str(path))
        paths = control_output_paths(
            project_dir, specs, control_spec_name, year, output_root
        )
        outputs.extend(str(path) for path in _equation_targets(
            paths, control_spec["equations"]
        ))
    pair_path = resolve_config_path(project_dir, specs["pair_year_source"])
    if not pair_path.exists():
        raise FileNotFoundError(f"Missing pair controls: {pair_path}")
    inputs.append(str(pair_path))
    if "trade" in control_spec["equations"]:
        gravity = resolve_config_path(project_dir, specs["gravity_path"])
        if not gravity.exists():
            raise FileNotFoundError(f"Missing Gravity controls: {gravity}")
        inputs.append(str(gravity))
        for year in years:
            tariff = resolve_tariff_path(project_dir, specs, year)
            if not tariff.exists():
                raise FileNotFoundError(f"Missing tariff controls: {tariff}")
            inputs.append(str(tariff))
    return {"inputs": inputs, "outputs": outputs}


def _assert_numeric_integral_key(
    series: pd.Series,
    label: str,
) -> None:
    if not pd.api.types.is_numeric_dtype(series.dtype):
        raise TypeError(f"{label} must be numeric; observed dtype={series.dtype}")
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if np.isnan(values).any() or not np.isfinite(values).all():
        raise ValueError(f"{label} contains missing or non-finite key values")
    if not np.isclose(values % 1, 0).all():
        examples = series.loc[~np.isclose(values % 1, 0)].head(10).tolist()
        raise ValueError(
            f"{label} must contain integer-valued merge keys; "
            f"invalid values={examples}"
        )


def _preflight_tariff_keys(
    project_dir: Path,
    specs: dict[str, Any],
    year: int,
    trade_path: Path,
    tariff_module: Any,
) -> dict[str, Any]:
    trade_keys = pd.read_csv(
        trade_path,
        usecols=TARIFF_KEY,
        low_memory=False,
    )
    tariff, tariff_diagnostics = tariff_module.prepare_tariff(
        project_dir, specs, year
    )
    duplicate_count = validate_unique(
        tariff, TARIFF_KEY, f"tariff preflight {year}"
    )
    trade_dtypes = {
        key: str(trade_keys[key].dtype) for key in TARIFF_KEY
    }
    tariff_dtypes = {
        key: str(tariff[key].dtype) for key in TARIFF_KEY
    }
    key_dtype_compatible = all(
        pd.api.types.is_numeric_dtype(trade_keys[key].dtype)
        and pd.api.types.is_numeric_dtype(tariff[key].dtype)
        for key in TARIFF_KEY
    )
    if not key_dtype_compatible:
        raise TypeError(
            "Trade and tariff merge-key dtypes are incompatible after tariff "
            f"normalization: trade={trade_dtypes}; tariff={tariff_dtypes}"
        )
    for key in TARIFF_KEY:
        _assert_numeric_integral_key(
            trade_keys[key], f"{trade_path.name}.{key}"
        )
        _assert_numeric_integral_key(
            tariff[key], f"normalized tariff.{key}"
        )
    if not trade_keys["year"].eq(year).all():
        observed_years = sorted(trade_keys["year"].unique().tolist())
        raise ValueError(
            f"{trade_path.name} must contain only year {year}; "
            f"observed={observed_years}"
        )
    return {
        "source": tariff_diagnostics["source"],
        "source_format": tariff_diagnostics["source_format"],
        "source_key_type": tariff_diagnostics["source_key_type"],
        "normalized_key_type": "numeric",
        "unmapped_origin_codes": tariff_diagnostics["origin_unmapped"],
        "unmapped_destination_codes": tariff_diagnostics[
            "destination_unmapped"
        ],
        "duplicate_keys": duplicate_count,
        "key_dtype_compatible": key_dtype_compatible,
        "trade_key_dtypes": trade_dtypes,
        "tariff_key_dtypes": tariff_dtypes,
        "sectors": tariff_diagnostics["sectors"],
        "trade_rows": len(trade_keys),
        "tariff_rows": len(tariff),
    }


def run(
    *,
    project_dir: Path | str | None = None,
    years: list[int] | None = None,
    control_spec: str,
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
    configured = get_control_spec(specs, control_spec)
    preflight = _preflight_paths(
        root, specs, control_spec, configured, selected_years, output_root
    )
    tariff_module = None
    if "trade" in configured["equations"]:
        tariff_module = load_sibling_script(
            "match_y_x_cons_02_prepare_tariff.py"
        )
        tariff_preflight_by_year = {}
        for year in selected_years:
            trade_path = y_x_output_paths(
                root, specs, year, output_root
            )["trade_csv"]
            tariff_preflight_by_year[str(year)] = _preflight_tariff_keys(
                root,
                specs,
                year,
                trade_path,
                tariff_module,
            )
        preflight["tariff_preflight"] = (
            tariff_preflight_by_year[str(selected_years[0])]
            if len(selected_years) == 1
            else tariff_preflight_by_year
        )
    if dry_run:
        plan = {
            "pipeline": "match_y_x_cons",
            "dry_run": True,
            "years": selected_years,
            "control_spec": control_spec,
            "equations": configured["equations"],
            "selected_controls": {
                equation: configured[equation]["selected_controls"]
                for equation in configured["equations"]
            },
            "candidate_controls": {
                equation: configured[equation]["candidate_controls"]
                for equation in configured["equations"]
            },
            **preflight,
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return plan

    all_targets: list[Path] = []
    for year in selected_years:
        paths = control_output_paths(
            root, specs, control_spec, year, output_root
        )
        all_targets.extend(_equation_targets(paths, configured["equations"]))
    check_output_collisions(all_targets, force)

    pair_module = load_sibling_script(
        "match_y_x_cons_01_prepare_pair_controls.py"
    )
    if tariff_module is None:
        tariff_module = load_sibling_script(
            "match_y_x_cons_02_prepare_tariff.py"
        )
    gravity_module = load_sibling_script("match_y_x_cons_03_prepare_gravity.py")
    trade_module = load_sibling_script(
        "match_y_x_cons_04_merge_trade_controls.py"
    )
    mp_module = load_sibling_script("match_y_x_cons_05_merge_mp_controls.py")
    sample_module = load_sibling_script(
        "match_y_x_cons_06_build_sample_flags.py"
    )
    results: dict[str, Any] = {
        "pipeline": "match_y_x_cons",
        "control_spec": control_spec,
        "years": {},
    }
    for year in selected_years:
        datasets: dict[str, pd.DataFrame] = {}
        merge_diagnostics: dict[str, list[dict[str, Any]]] = {}
        source_diagnostics: dict[str, Any] = {}
        input_paths: dict[str, Path] = {}
        pair_controls, pair_diag = pair_module.prepare_pair_controls(
            root, specs, year
        )
        source_diagnostics["pair_controls"] = pair_diag
        input_paths["pair_controls"] = resolve_config_path(
            root, specs["pair_year_source"]
        )
        if "trade" in configured["equations"]:
            trade_y_x, trade_path = read_y_x_base(
                root, specs, "trade", year, output_root
            )
            input_paths["trade_y_x"] = trade_path
            tariff, tariff_diag = tariff_module.prepare_tariff(root, specs, year)
            source_diagnostics["tariff"] = tariff_diag
            input_paths["tariff"] = resolve_tariff_path(root, specs, year)
            target_codes = set(trade_y_x["iso_o_match"]) | set(
                trade_y_x["iso_d_match"]
            )
            gravity, gravity_diag = gravity_module.prepare_gravity(
                root, specs, [year], target_codes
            )
            source_diagnostics["gravity"] = gravity_diag
            input_paths["gravity"] = resolve_config_path(
                root, specs["gravity_path"]
            )
            trade, trade_merges = trade_module.merge_trade_controls(
                trade_y_x, tariff, pair_controls, gravity
            )
            datasets["trade"] = sample_module.build_trade_sample_flags(trade)
            merge_diagnostics["trade"] = trade_merges
        if "mp" in configured["equations"]:
            mp_y_x, mp_path = read_y_x_base(
                root, specs, "mp", year, output_root
            )
            input_paths["mp_y_x"] = mp_path
            mp, mp_merges = mp_module.merge_mp_controls(
                mp_y_x, pair_controls
            )
            datasets["mp"] = sample_module.build_mp_sample_flags(mp)
            merge_diagnostics["mp"] = mp_merges
        results["years"][str(year)] = _write_year(
            root,
            specs,
            control_spec,
            configured,
            year,
            datasets,
            merge_diagnostics,
            input_paths,
            source_diagnostics,
            output_root=output_root,
            force=force,
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", default=None)
    parser.add_argument("--control-spec", required=True)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(
        years=parse_year_arguments(args.years),
        control_spec=args.control_spec,
        output_root=args.output_root,
        dry_run=args.dry_run,
        force=args.force,
    )
    if not args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
