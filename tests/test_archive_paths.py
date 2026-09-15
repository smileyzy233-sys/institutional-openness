"""Path-only checks: no research data construction or estimation."""
import json
from pathlib import Path

from archive_paths import historical_path, logical_relative


def configured_project(tmp_path):
    root = tmp_path / "project"
    config = root / "configs" / "historical_path_mappings.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"relocations": [
        {"source": "result/current_version", "target": "outputs/matched_data"},
        {"source": "result/legacy", "target": "../project_archive/project/history/legacy"},
    ]}), encoding="utf-8")
    return root


def test_current_and_archived_references_keep_historical_keys(tmp_path):
    root = configured_project(tmp_path)
    for old, target in [
        ("result/current_version/match_y_x/item.txt", "outputs/matched_data/match_y_x/item.txt"),
        ("result/legacy/item.txt", "../project_archive/project/history/legacy/item.txt"),
    ]:
        destination = (root / target).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("unchanged evidence", encoding="utf-8")
        assert historical_path(root, old) == destination
        assert logical_relative(root, destination) == Path(old)


def test_restored_original_location_takes_precedence(tmp_path):
    root = configured_project(tmp_path)
    original = root / "result/legacy/item.txt"
    original.parent.mkdir(parents=True)
    original.write_text("restored evidence", encoding="utf-8")
    assert historical_path(root, "result/legacy/item.txt") == original


def test_similar_directory_name_is_not_an_alias(tmp_path):
    root = configured_project(tmp_path)
    assert historical_path(root, "result/legacy_other/item.txt") == root / "result/legacy_other/item.txt"


def test_previous_backup_mapping_remains_available_without_new_config(tmp_path):
    root = tmp_path / "project"
    path = historical_path(root, "migration_backups/version/preflight_manifest.json")
    assert path == tmp_path / "project_archive/project/migration_backups/version/preflight_manifest.json"
    assert logical_relative(root, path) == Path("migration_backups/version/preflight_manifest.json")


def test_legacy_overlap_can_report_file_outside_project(tmp_path):
    import pandas as pd
    from conftest import load_script

    root = configured_project(tmp_path)
    mapping = root / "configs/historical_path_mappings.json"
    mapping.write_text(json.dumps({"relocations": [{
        "source": "result/regression_2019",
        "target": "../project_archive/project/history/regression_2019",
    }]}), encoding="utf-8")
    frame = pd.DataFrame({
        "year": [2019], "iso_o": ["AAA"], "iso_d": ["BBB"],
        "sector_amne": [1], "value": [2.0], "raw_trade_score": [0.5],
        "trade_agreement_dummy": [1], "idealpoint_abs_distance": [0.2],
    })
    logical = "result/regression_2019/trade_cost_2019_matched.csv"
    path = historical_path(root, logical)
    path.parent.mkdir(parents=True)
    frame.to_csv(path, index=False)
    exporter = load_script("match_y_x_cons_07_validate_export.py")
    result = exporter._legacy_overlap(root, "trade", 2019, frame)
    assert result["legacy_path"] == logical
    assert not any(result["mismatch_counts"].values())
