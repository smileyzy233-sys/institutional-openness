#!/usr/bin/env python3
"""Read-only, public-safe audit of the DTA -> empirical-input review bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

FLOAT_DECIMALS = 6
YEARS = (2000, 2019)
CONS = {
    ("trade", 2000): ("match_y_x_cons/trade_candidate_pool_v1/2000/trade_y_x_cons_2000", "raw_trade_score"),
    ("trade", 2019): ("match_y_x_cons/trade_candidate_pool_v1/2019/trade_y_x_cons_2019", "raw_trade_score"),
    ("mp", 2000): ("match_y_x_cons/mp_controls_v1/2000/mp_y_x_cons_2000", "raw_mp_score"),
    ("mp", 2019): ("match_y_x_cons/mp_controls_v1/2019/mp_y_x_cons_2019", "raw_mp_score"),
}
KEY = ["year", "iso_o", "iso_d", "sector_amne"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rel(path: Path, root: Path) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path.name


def result(status: str, **extra: object) -> dict[str, object]:
    return {"status": status, **extra}


def read_csv(root: Path, name: str, **kw: object) -> pd.DataFrame:
    return pd.read_csv(root / name, encoding="utf-8", low_memory=False, **kw)


def normalize_text(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.replace("\r\n", "\n", regex=False).str.replace("\r", "\n", regex=False)


def keyed_comparison(actual: pd.DataFrame, expected: pd.DataFrame,
                     keys: list[str], values: list[str], tolerance: float = 1e-12) -> dict:
    """Reject missing, duplicate, changed or empty keys before comparing values."""
    ai = pd.MultiIndex.from_frame(actual[keys])
    ei = pd.MultiIndex.from_frame(expected[keys])
    keys_match = (len(ai) > 0 and len(ai) == len(ei) and ai.is_unique
                  and ei.is_unique and not ai.has_duplicates
                  and len(ai.difference(ei)) == 0)
    if not keys_match:
        return result("fail", rows=len(ai), expected_rows=len(ei), keys_match=False)
    a = actual[values].to_numpy(float)
    expected_values = expected[values].copy()
    expected_values.index = ei
    e = expected_values.reindex(ai).to_numpy(float)
    delta = np.abs(a - e)
    finite = bool(np.isfinite(a).all() and np.isfinite(e).all())
    return result("pass" if finite and np.all(delta <= tolerance) else "fail",
                  rows=len(ai), expected_rows=len(ei), keys_match=True, finite=finite,
                  max_abs_diff=float(delta[np.isfinite(delta)].max(initial=0.0)),
                  mismatched_cells=int((~np.isfinite(delta) | (delta > tolerance)).sum()))


def norm_ids(value: object) -> tuple[str, ...]:
    return tuple(x.strip() for x in str(value or "").split(";") if x.strip())


def matrix_check(root: Path) -> dict[str, object]:
    wb = root / "data/raw/DTA 2.0 - Vertical Content (v2)_code.xlsx"
    stored = root / "data/interim/agreement_matrix.csv"
    stata = pd.read_excel(wb, sheet_name="STATA")
    ac = [c for c in stata.columns if str(c).lower().startswith("agree_") and str(c).split("_")[-1].isdigit()]
    src = stata[stata["Provision"].notna()].reset_index(drop=True)
    ids = [f"P{i:04d}" for i in range(1, len(src) + 1)]
    order = sorted(ac, key=lambda x: int(str(x).split("_")[-1]))
    numeric = src[order].apply(pd.to_numeric, errors="coerce")
    invalid = int((src[order].notna() & numeric.isna()).sum().sum())
    vals = numeric.fillna(0.0).to_numpy(float).T
    got = pd.read_csv(stored, encoding="utf-8")
    cols = [c for c in got.columns if str(c).startswith("P")]
    id_order_ok = got["agreement_id"].astype(str).tolist() == [f"agree_{i}" for i in range(1, len(order) + 1)]
    provision_order_ok = cols == ids
    arr = got[ids].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    if arr.shape != vals.shape:
        return result("fail", workbook_rows=len(src), workbook_agreements=len(order), matrix_shape=list(arr.shape), expected_shape=list(vals.shape))
    delta = np.abs(arr - vals)
    bad = int((~np.isfinite(delta) | (delta > 1e-12)).sum()) + invalid
    return result("pass" if id_order_ok and provision_order_ok and bad == 0 else "fail", workbook_rows=len(src), workbook_agreements=len(order), blank_cells=int(stata[order].isna().sum().sum()), partial_cells=int(((pd.to_numeric(stata[order].stack(), errors="coerce") > 0) & (pd.to_numeric(stata[order].stack(), errors="coerce") < 1)).sum()), agreement_id_order=id_order_ok, provision_id_order=provision_order_ok, value_mismatches=bad, max_abs_diff=float(delta.max(initial=0.0)), files=[rel(wb, root), rel(stored, root)])


def weights_check(root: Path) -> dict[str, object]:
    w = read_csv(root, "data/processed/final_provision_weights.csv")
    s = read_csv(root, "data/processed/stage1_final_classification.csv")
    p = read_csv(root, "data/interim/provisions_master.csv")
    required = {"provision_id", "effective_trade_weight", "effective_mp_weight", "final_impact_type", "final_is_institutional_opening", "final_dominant_dimension"}
    if not required.issubset(w.columns):
        return result("fail", missing_columns=sorted(required - set(w.columns)))
    ids_ok = set(w.provision_id.astype(str)) == set(p.provision_id.astype(str)) == set(s.provision_id.astype(str)) and not w.provision_id.duplicated().any()
    wt = w[["effective_trade_weight", "effective_mp_weight"]].apply(pd.to_numeric, errors="coerce")
    finite_ok = bool(np.isfinite(wt.to_numpy(float)).all()) and not wt.isna().any().any() and bool(((wt >= 0) & (wt <= 1)).all().all())
    typ = w.final_impact_type.astype(str)
    canonical = ((typ.eq("trade") & wt.eq([1.0, 0.0]).all(axis=1)) | (typ.eq("mp") & wt.eq([0.0, 1.0]).all(axis=1)) | (typ.eq("both") & (wt.sum(axis=1) - 1).abs().le(1e-12)) | (typ.isin(["none", "not_applicable"]) & wt.eq(0).all(axis=1))).all()
    q = w.merge(s, on="provision_id", how="outer", suffixes=("_w", "_s"), validate="1:1").merge(p, on="provision_id", how="outer", suffixes=("", "_p"), validate="1:1")
    diffs: dict[str, int] = {}
    for c in ["final_is_institutional_opening", "final_dominant_dimension", "policy_area", "original_coding"]:
        left = f"{c}_w" if f"{c}_w" in q else c
        right = f"{c}_s" if f"{c}_s" in q else c
        if left in q and right in q:
            diffs[c] = int((q[left].fillna("").astype(str) != q[right].fillna("").astype(str)).sum())
    text_left = normalize_text(q["provision_text_w"])
    text_master = normalize_text(q["provision_text"])
    text_raw = int((q["provision_text_w"].fillna("").astype(str) != q["provision_text"].fillna("").astype(str)).sum())
    text_norm = int((text_left != text_master).sum())
    ok = ids_ok and finite_ok and bool(canonical) and not any(diffs.values()) and text_norm == 0
    return result("pass" if ok else "fail", rows=len(w), id_sets_match=ids_ok, valid_effective_weights=finite_ok, canonical_by_impact_type=bool(canonical), classification_mismatches=diffs, provision_text_exact_mismatches=text_raw, provision_text_crlf_normalized_mismatches=text_norm, files=[rel(root / "data/processed/final_provision_weights.csv", root), rel(root / "data/processed/stage1_final_classification.csv", root), rel(root / "data/interim/provisions_master.csv", root)])


def score_checks(root: Path) -> dict[str, object]:
    m = read_csv(root, "data/interim/agreement_matrix.csv")
    w = read_csv(root, "data/processed/final_provision_weights.csv")
    a = read_csv(root, "data/processed/agreement_level_indices.csv", usecols=["agreement_id", "raw_trade_score", "raw_mp_score"])
    pc = [c for c in m.columns if str(c).startswith("P")]
    mm = m.set_index("agreement_id")[pc].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    ww = w.set_index("provision_id").loc[pc]
    calc = np.column_stack([mm.to_numpy(float) @ ww["effective_trade_weight"].to_numpy(float), mm.to_numpy(float) @ ww["effective_mp_weight"].to_numpy(float)])
    calc = np.round(calc, FLOAT_DECIMALS)
    got = a.set_index("agreement_id").loc[mm.index][["raw_trade_score", "raw_mp_score"]].to_numpy(float)
    d = np.abs(calc - got)
    matrix_score = result("pass" if np.all(d <= 1e-12) else "fail", rows=len(a), mismatched_cells=int((d > 1e-12).sum()), max_abs_diff=float(d.max(initial=0.0)), rounding_decimals=FLOAT_DECIMALS)
    pair = read_csv(root, "data/processed/country_pair_year_indices.csv", usecols=["pair_key", "year", "agreement_id_list", "raw_trade_score", "raw_mp_score", "trade_agreement_dummy"])
    lists = set(norm_ids(x) for x in pair.agreement_id_list)
    bad_list = sum(any(x not in mm.index for x in k) or not k for k in lists)
    lookup = {k: mm.loc[list(k)].to_numpy(float).max(axis=0) for k in lists if k and all(x in mm.index for x in k)}
    tw = ww["effective_trade_weight"].to_numpy(float); mw = ww["effective_mp_weight"].to_numpy(float)
    calc_pair = np.array([[round(float(lookup[norm_ids(v)] @ tw), FLOAT_DECIMALS), round(float(lookup[norm_ids(v)] @ mw), FLOAT_DECIMALS)] if norm_ids(v) in lookup else [np.nan, np.nan] for v in pair.agreement_id_list])
    got_pair = pair[["raw_trade_score", "raw_mp_score"]].to_numpy(float)
    dp = np.abs(calc_pair - got_pair)
    country = result("pass" if bad_list == 0 and np.all(np.isfinite(calc_pair)) and np.all(dp <= 1e-12) else "fail", rows=len(pair), unique_saved_lists=len(lookup), invalid_saved_lists=int(bad_list), mismatched_cells=int((dp > 1e-12).sum()), max_abs_diff=float(np.nanmax(dp) if np.isfinite(dp).any() else 0.0), basis="saved agreement_id_list in country_pair_year_indices.csv; existing effective agreement list")
    active = read_csv(root, "data/processed/dta_active_agreement_dummy_all_dta_pair_year.csv", usecols=["pair_key", "year", "raw_trade_score", "raw_mp_score", "trade_agreement_dummy"])
    score_cols = ["raw_trade_score", "raw_mp_score"]
    symmetric = bool(pair.groupby(["pair_key", "year"])[score_cols].nunique(dropna=False).le(1).all().all())
    pair_unique = pair.groupby(["pair_key", "year"], as_index=False)[score_cols].first()
    bridge = keyed_comparison(active, pair_unique, ["pair_key", "year"], score_cols)
    bridge["directional_scores_consistent"] = symmetric
    if not symmetric:
        bridge["status"] = "fail"
    p = read_csv(root, "data/processed/trade_dummy_icio_2000_2023.csv", usecols=["iso_o", "iso_d", "pair_key", "year", "raw_trade_score", "raw_mp_score", "trade_agreement_dummy"])
    full_expected = p[["iso_o", "iso_d", "pair_key", "year"]].merge(
        active, on=["pair_key", "year"], how="left", validate="m:1")
    full_expected[score_cols + ["trade_agreement_dummy"]] = full_expected[score_cols + ["trade_agreement_dummy"]].fillna(0)
    full_pair = keyed_comparison(p, full_expected, ["iso_o", "iso_d", "year"], score_cols + ["trade_agreement_dummy"])
    p = p[p.trade_agreement_dummy.eq(1)].copy()
    q = p.merge(active, on=["pair_key", "year"], how="left", suffixes=("_pair", "_active"), validate="m:1")
    d2 = np.abs(q[["raw_trade_score_pair", "raw_mp_score_pair"]].to_numpy(float) - q[["raw_trade_score_active", "raw_mp_score_active"]].to_numpy(float))
    dummy = result("pass" if not q[["raw_trade_score_active", "raw_mp_score_active"]].isna().any().any() and np.all(d2 <= 1e-12) and (q.trade_agreement_dummy_pair == q.trade_agreement_dummy_active).all() else "fail", rows=len(q), pair_dummy_one_rows=len(p), unmatched_active=int(q.raw_trade_score_active.isna().sum()), mismatched_cells=int((d2 > 1e-12).sum()), max_abs_diff=float(d2.max(initial=0.0)))
    return {"agreement_level_matrix_times_weights": matrix_score, "country_pair_saved_list_max": country, "country_to_active_scores": bridge, "full_pair_scores_and_structural_zeros": full_pair, "pair_dummy_scores": dummy, "files":[rel(root / "data/processed/agreement_level_indices.csv", root), rel(root / "data/processed/country_pair_year_indices.csv", root), rel(root / "data/processed/dta_active_agreement_dummy_all_dta_pair_year.csv", root), rel(root / "data/processed/trade_dummy_icio_2000_2023.csv", root)]}


def manifest_check(root: Path) -> dict[str, object]:
    mapping = json.loads((root / "configs/historical_path_mappings.json").read_text(encoding="utf-8"))["relocations"]
    manifests = sorted((root / "outputs/matched_data").rglob("build_manifest.json"))
    cache: dict[Path, str] = {}
    records = []
    for mp in manifests:
        rec = json.loads(mp.read_text(encoding="utf-8")); checks = []
        for name, raw in rec.get("input_paths", {}).items():
            text = str(raw).replace("\\", "/"); mapped = False
            for item in sorted(mapping, key=lambda x: len(str(x["source"])), reverse=True):
                source = str(item["source"]).replace("\\", "/").rstrip("/")
                if text == source or text.startswith(source + "/"):
                    text = str(item["target"]).replace("\\", "/").rstrip("/") + text[len(source):]; mapped = True; break
            path = (root / text).resolve()
            expected = rec.get("input_sha256", {}).get(name); actual = None
            if path.exists():
                if path not in cache:
                    cache[path] = sha256(path)
                actual = cache[path]
            checks.append({"name": name, "path": rel(path, root), "mapped_by_archive": mapped, "exists": path.exists(), "hash_matches": bool(actual and expected and actual == expected), "sha256": actual})
        records.append({"manifest": rel(mp, root), "row_policy": rec.get("row_policy", {}), "inputs": checks})
    policy = json.loads((root / "configs/matching_specs.json").read_text(encoding="utf-8")).get("row_policy", {})
    old = sum(1 for x in records if x["row_policy"] == {"drop_row": True, "keep_domestic": True})
    bad = [x for x in records for c in x["inputs"] if not c["exists"] or not c["hash_matches"]]
    status = "pass" if len(records) == 6 and not bad else "fail"
    return result(status, manifest_count=len(records), input_failures=len(bad), row_policy_known_state={"historical_keep_domestic_true_manifests": old, "current_config": policy, "classification":"known_state"}, manifests=records)


def dta_check(root: Path) -> dict[str, object]:
    pair = read_csv(root, "data/processed/trade_dummy_icio_2000_2023.csv", usecols=["year", "iso_o", "iso_d", "raw_trade_score", "raw_mp_score", "trade_agreement_dummy", "pair_key"])
    out = []
    for (eq, year), (stem, score) in CONS.items():
        base = root / "outputs/matched_data" / stem
        csv = base.with_suffix(".csv"); dta = base.with_suffix(".dta")
        cols = KEY + ["iso_o_match", "iso_d_match", score, "trade_agreement_dummy"]
        c = pd.read_csv(csv, usecols=lambda x: x in cols, low_memory=False)
        d = pd.read_stata(dta, columns=cols, convert_categoricals=False)
        unique = int(d.duplicated(KEY).sum()) == 0
        j = d.merge(pair, left_on=["year", "iso_o_match", "iso_d_match"], right_on=["year", "iso_o", "iso_d"], how="left", suffixes=("_dta", "_pair"), validate="m:1")
        expected = j["raw_trade_score_pair" if eq == "trade" else "raw_mp_score_pair"]
        expected_dummy = j["trade_agreement_dummy_pair"]
        ds = np.abs(pd.to_numeric(j[f"{score}_dta"], errors="coerce").to_numpy(float) - expected.to_numpy(float))
        dd = (j["trade_agreement_dummy_dta"].fillna(-1) != expected_dummy).to_numpy()
        keyed = keyed_comparison(c, d, KEY, [score, "trade_agreement_dummy"])
        unique = unique and keyed["status"] == "pass"
        csv_d = c[KEY + [score]].sort_values(KEY).reset_index(drop=True); dta_d = d[KEY + [score]].sort_values(KEY).reset_index(drop=True)
        csv_diff = np.abs(pd.to_numeric(csv_d[score], errors="coerce").to_numpy(float) - pd.to_numeric(dta_d[score], errors="coerce").to_numpy(float))
        out.append(result("pass" if unique and len(c) == len(d) and np.all(csv_diff <= 1e-12) and np.all(ds <= 1e-12) and not dd.any() else "fail", equation=eq, year=year, rows=len(d), duplicate_keys=int(d.duplicated(KEY).sum()), csv_dta_mismatches=int((csv_diff > 1e-12).sum()), pair_score_mismatches=int((ds > 1e-12).sum()), pair_dummy_mismatches=int(dd.sum()), max_pair_score_abs_diff=float(ds.max(initial=0.0)), files=[rel(csv, root), rel(dta, root), rel(root / "data/processed/trade_dummy_icio_2000_2023.csv", root)]))
    return result("pass" if all(x["status"] == "pass" for x in out) else "fail", products=out)


def stata_check(root: Path, sr: Path) -> dict[str, object]:
    raw_root = sr / "data/raw/io/gravity_resolved_fractional_20260914"
    checks: list[dict[str, object]] = []
    source: dict[tuple[str, int], pd.Series] = {}
    for (eq, year), (stem, score) in CONS.items():
        cons = (root / "outputs/matched_data" / stem).with_suffix(".dta")
        raw = raw_root / cons.name
        exists = raw.exists() and cons.exists()
        raw_hash = sha256(raw) if raw.exists() else None
        checks.append({"equation": eq, "year": year, "cons_path": rel(cons, root), "raw_path": rel(raw, sr), "rows": int(pd.read_stata(raw, columns=["year"], convert_categoricals=False).shape[0]) if raw.exists() else 0, "hash_matches": bool(exists and raw_hash == sha256(cons)), "sha256": raw_hash})
        if not raw.exists():
            continue
        frame = pd.read_stata(raw, columns=KEY + [score], convert_categoricals=False)
        o = frame.iso_o.astype(str).str.strip().str.upper()
        d = frame.iso_d.astype(str).str.strip().str.upper()
        row = o.eq("ROW") | d.eq("ROW")
        domestic = o.eq(d)
        sector_ok = frame.sector_amne.between(1, 19 if eq == "trade" else 20)
        frame = frame[sector_ok & ~row & ~domestic].copy()
        source[(eq, year)] = frame.set_index(KEY)[score]

    derived_checks: list[dict[str, object]] = []
    for eq, score in [("trade", "raw_trade_score"), ("mp", "raw_mp_score")]:
        for year in YEARS:
            ppml = sr / "data/derived" / f"io_{eq}_longdiff_data" / f"{eq}_twoperiod_ppml.dta"
            if not ppml.exists():
                derived_checks.append(result("fail", equation=eq, dataset="ppml", rows=0, reason="missing derived file"))
                continue
            cols = ["year", "iso_o", "iso_d", "sector_amne", score]
            frame = pd.read_stata(ppml, columns=cols, convert_categoricals=False)
            frame = frame[frame.year.eq(year)]
            idx = pd.MultiIndex.from_frame(frame[["year", "iso_o", "iso_d", "sector_amne"]])
            expected = source.get((eq, year), pd.Series(dtype=float)).reindex(idx).to_numpy(float)
            actual = pd.to_numeric(frame[score], errors="coerce").to_numpy(float)
            diff = np.abs(actual - expected)
            o = frame.iso_o.astype(str).str.strip().str.upper(); d = frame.iso_d.astype(str).str.strip().str.upper()
            row = o.eq("ROW") | d.eq("ROW"); domestic = o.eq(d)
            valid = np.isfinite(actual).all() and np.isfinite(expected).all() and np.isfinite(diff).all()
            source_index = source.get((eq, year), pd.Series(dtype=float)).index
            keys_match = (len(idx) > 0 and idx.is_unique and source_index.is_unique
                          and len(idx) == len(source_index)
                          and len(idx.difference(source_index)) == 0)
            valid = valid and keys_match
            derived_checks.append(result("pass" if valid and np.all(diff <= 1e-10) and not row.any() and not domestic.any() else "fail", equation=eq, year=year, dataset="ppml", rows=len(frame), max_abs_diff=float(np.nanmax(diff) if diff.size else 0.0), missing_expected=int(np.isnan(expected).sum()), missing_actual=int(np.isnan(actual).sum()), row_rows=int(row.sum()), domestic_rows=int(domestic.sum())))
            derived_checks[-1]["keys_match"] = bool(keys_match)

        ols = sr / "data/derived" / f"io_{eq}_longdiff_data" / f"{eq}_longdiff_ols.dta"
        if not ols.exists():
            derived_checks.append(result("fail", equation=eq, dataset="ols", rows=0, reason="missing derived file"))
            continue
        score_cols = [f"{score}_2000", f"{score}_2019", f"d_{score}"]
        frame = pd.read_stata(ols, columns=["iso_o", "iso_d", "sector_amne"] + score_cols, convert_categoricals=False)
        expected_values: list[np.ndarray] = []
        actual_values: list[np.ndarray] = []
        keys_match = len(frame) > 0
        for year, col in [(2000, score_cols[0]), (2019, score_cols[1])]:
            idx = pd.MultiIndex.from_frame(pd.DataFrame({"year": year, "iso_o": frame.iso_o, "iso_d": frame.iso_d, "sector_amne": frame.sector_amne}))
            source_index = source.get((eq, year), pd.Series(dtype=float)).index
            keys_match = (keys_match and idx.is_unique and source_index.is_unique
                          and len(idx) == len(source_index)
                          and len(idx.difference(source_index)) == 0)
            exp = source.get((eq, year), pd.Series(dtype=float)).reindex(idx).to_numpy(float)
            expected_values.append(exp); actual_values.append(pd.to_numeric(frame[col], errors="coerce").to_numpy(float))
        diff_level = [np.abs(a - e) for a, e in zip(actual_values, expected_values)]
        actual_diff = pd.to_numeric(frame[score_cols[2]], errors="coerce").to_numpy(float)
        diff_delta = np.abs(actual_diff - (actual_values[1] - actual_values[0]))
        all_diff = np.concatenate(diff_level + [diff_delta])
        o = frame.iso_o.astype(str).str.strip().str.upper(); d = frame.iso_d.astype(str).str.strip().str.upper()
        row = o.eq("ROW") | d.eq("ROW"); domestic = o.eq(d)
        valid = keys_match and all(np.isfinite(x).all() for x in expected_values + actual_values + [actual_diff, all_diff])
        derived_checks.append(result("pass" if valid and np.all(all_diff <= 1e-10) and not row.any() and not domestic.any() else "fail", equation=eq, dataset="ols", rows=len(frame), max_abs_diff=float(np.nanmax(all_diff) if all_diff.size else 0.0), missing_expected=int(sum(np.isnan(x).sum() for x in expected_values)), missing_actual=int(sum(np.isnan(x).sum() for x in actual_values) + np.isnan(actual_diff).sum()), row_rows=int(row.sum()), domestic_rows=int(domestic.sum())))
        derived_checks[-1]["keys_match"] = bool(keys_match)
    ok = all(x["hash_matches"] for x in checks) and len(checks) == 4 and len(derived_checks) == 6 and all(x["status"] == "pass" for x in derived_checks)
    return result("pass" if ok else "fail", raw_snapshots=checks, derived=derived_checks)


def run(root: Path, stata: Path | None) -> dict[str, object]:
    checks = {"matrix": matrix_check(root), "weights": weights_check(root), "scores": score_checks(root), "cons_dta": dta_check(root), "manifests": manifest_check(root)}
    checks["stata"] = stata_check(root, stata) if stata else result("skipped", reason="--stata-root not supplied")
    failures = []
    def walk(x: object, path: str = "") -> None:
        if isinstance(x, dict):
            if x.get("status") == "fail": failures.append(path or "root")
            for k, v in x.items(): walk(v, f"{path}.{k}" if path else k)
        elif isinstance(x, list):
            for i, v in enumerate(x): walk(v, f"{path}[{i}]")
    walk(checks)
    return {"schema": "review_bundle_audit_v1", "status": "fail" if failures else "pass", "failures": failures, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1]); parser.add_argument("--stata-root", type=Path); parser.add_argument("--report", type=Path); args = parser.parse_args(argv)
    if args.report and args.report.exists():
        print(json.dumps({"status": "fail", "error": "refusing to overwrite existing report"}, ensure_ascii=False)); return 2
    try:
        report = run(args.data_root.resolve(), args.stata_root.resolve() if args.stata_root else None)
    except Exception as exc:  # public-safe failure: no source rows or absolute paths
        report = {"schema": "review_bundle_audit_v1", "status": "fail", "failures": ["fatal"], "error": type(exc).__name__}
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write("\n")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
