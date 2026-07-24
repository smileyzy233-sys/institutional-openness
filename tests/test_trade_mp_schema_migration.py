from __future__ import annotations

import json

import pandas as pd
import pytest

import migrate_trade_mp_schema as migration


def legacy_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "impact_type": "mp",
                "raw_trade_weight": 1.0,
                "raw_investment_weight": 0.0,
                "normalized_trade_weight": 1.0,
                "normalized_investment_weight": 0.0,
                "final_impact_type_mp_count": 500,
                "final_impact_type_tr_count": 132,
                "quality_mp_fixed_1_0": True,
                "quality_tr_fixed_0_1": True,
                "prompt_version": "v3_zh_stage2_trade_invest",
                "raw_response": json.dumps(
                    {
                        "impact_type": "mp",
                        "trade_weight": 1.0,
                        "investment_weight": 0.0,
                        "reason": "Legacy mp means trade.",
                    }
                ),
                "reason": "Legacy label `mp` means trade in this row.",
            },
            {
                "provision_id": "P2",
                "impact_type": "tr",
                "raw_trade_weight": 0.0,
                "raw_investment_weight": 1.0,
                "normalized_trade_weight": 0.0,
                "normalized_investment_weight": 1.0,
                "final_impact_type_mp_count": 500,
                "final_impact_type_tr_count": 132,
                "quality_mp_fixed_1_0": True,
                "quality_tr_fixed_0_1": True,
                "prompt_version": "v3_zh_stage2_trade_invest",
                "raw_response": json.dumps(
                    {
                        "impact_type": "tr",
                        "raw_trade_weight": 0.0,
                        "raw_investment_weight": 1.0,
                    }
                ),
                "reason": "Legacy label `tr` means the investment channel.",
            },
        ]
    )


def configure_root(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(migration, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        migration,
        "PREFLIGHT_MANIFEST_PATH",
        tmp_path / "migration_backups" / "preflight_manifest.json",
    )


def test_simultaneous_category_and_diagnostic_mapping(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "stage2.csv"
    legacy_rows().to_csv(path, index=False, encoding="utf-8-sig")

    audit, _reviews = migration.migrate_file(path, dry_run=False)
    migrated = pd.read_csv(path, encoding="utf-8-sig")

    assert audit.old_mp_to_trade_count == 2  # column plus raw_response
    assert audit.old_tr_to_mp_count == 2
    assert migrated["impact_type"].tolist() == ["trade", "mp"]
    assert migrated["final_impact_type_trade_count"].tolist() == [500, 500]
    assert migrated["final_impact_type_mp_count"].tolist() == [132, 132]
    assert migrated["quality_trade_fixed_1_0"].all()
    assert migrated["quality_mp_fixed_0_1"].all()


def test_raw_response_is_parsed_as_json_and_renamed(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "stage2.csv"
    legacy_rows().to_csv(path, index=False, encoding="utf-8-sig")

    migration.migrate_file(path, dry_run=False)
    migrated = pd.read_csv(path, encoding="utf-8-sig")
    payloads = migrated["raw_response"].map(json.loads).tolist()

    assert payloads[0]["impact_type"] == "trade"
    assert payloads[1]["impact_type"] == "mp"
    assert payloads[0]["raw_trade_weight"] == 1.0
    assert payloads[0]["raw_mp_weight"] == 0.0
    assert payloads[0]["reason"] == "Legacy trade means trade."
    assert "investment_weight" not in payloads[0]
    assert "raw_investment_weight" not in payloads[1]
    assert migrated["reason"].tolist() == [
        "Legacy label `trade` means trade in this row.",
        "Legacy label `mp` means the investment channel.",
    ]


def test_migration_is_idempotent_and_removes_legacy_columns(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "stage2.csv"
    legacy_rows().to_csv(path, index=False, encoding="utf-8-sig")

    first, _ = migration.migrate_file(path, dry_run=False)
    first_sha = migration.sha256_file(path)
    second, _ = migration.migrate_file(path, dry_run=False)

    assert first.changed
    assert not second.changed
    assert migration.sha256_file(path) == first_sha
    columns = pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns
    assert not any("investment_weight" in column for column in columns)
    assert "raw_mp_weight" in columns
    assert "normalized_mp_weight" in columns


def test_dry_run_does_not_modify_file(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "stage2.csv"
    legacy_rows().to_csv(path, index=False, encoding="utf-8-sig")
    before = migration.sha256_file(path)

    audit, reviews = migration.migrate_file(path, dry_run=True)

    assert audit.changed
    assert audit.dry_run
    assert migration.sha256_file(path) == before
    assert reviews


def test_column_collision_raises_without_losing_either_source(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "collision.csv"
    pd.DataFrame(
        {
            "provision_id": ["P1"],
            "raw_investment_score": [1.25],
            "raw_mp_score": [9.75],
        }
    ).to_csv(path, index=False, encoding="utf-8-sig")
    before = migration.sha256_file(path)

    with pytest.raises(ValueError, match="collision"):
        migration.migrate_file(path, dry_run=False)

    assert migration.sha256_file(path) == before


def test_fixed_trade_mp_and_both_weights_are_validated(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "weights.csv"
    pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "impact_type": "mp",
                "normalized_trade_weight": 1.0,
                "normalized_investment_weight": 0.0,
            },
            {
                "provision_id": "P2",
                "impact_type": "tr",
                "normalized_trade_weight": 0.0,
                "normalized_investment_weight": 1.0,
            },
            {
                "provision_id": "P3",
                "impact_type": "both",
                "normalized_trade_weight": 0.4,
                "normalized_investment_weight": 0.6,
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    migration.migrate_file(path, dry_run=False)
    migrated = pd.read_csv(path, encoding="utf-8-sig").set_index("provision_id")

    assert migrated.loc["P1", ["normalized_trade_weight", "normalized_mp_weight"]].tolist() == [
        1.0,
        0.0,
    ]
    assert migrated.loc["P2", ["normalized_trade_weight", "normalized_mp_weight"]].tolist() == [
        0.0,
        1.0,
    ]
    assert (
        migrated.loc["P3", "normalized_trade_weight"]
        + migrated.loc["P3", "normalized_mp_weight"]
    ) == pytest.approx(1.0)


def test_empty_current_schema_file_is_idempotent(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text(
        "provision_id,impact_label_schema_version,final_impact_type\n",
        encoding="utf-8",
    )

    assert migration.needs_migration(path) is False


def test_current_schema_only_resolves_reason_tokens(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "current.csv"
    pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "impact_label_schema_version": migration.IMPACT_LABEL_SCHEMA_VERSION,
                "impact_type": "mp",
                "reason": "Legacy tr means investment; uppercase MP remains an acronym.",
                "raw_response": json.dumps(
                    {
                        "impact_type": "mp",
                        "reason": "Legacy tr means investment; MP remains uppercase.",
                    }
                ),
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    assert migration.needs_migration(path) is True
    audit, reviews = migration.migrate_file(path, dry_run=False)
    migrated = pd.read_csv(path, encoding="utf-8-sig").iloc[0]
    payload = json.loads(migrated["raw_response"])

    assert audit.changed
    assert audit.old_mp_to_trade_count == 0
    assert audit.old_tr_to_mp_count == 0
    assert migrated["impact_type"] == "mp"
    assert migrated["reason"] == "Legacy mp means investment; uppercase MP remains an acronym."
    assert payload["impact_type"] == "mp"
    assert payload["reason"] == "Legacy mp means investment; MP remains uppercase."
    assert {review["status"] for review in reviews} == {"context_migrated_to_mp"}
    assert migration.needs_migration(path) is False


def test_embedded_raw_response_columns_are_migrated(monkeypatch, tmp_path):
    configure_root(monkeypatch, tmp_path)
    path = tmp_path / "comparison.csv"
    pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "model_a_impact_type": "mp",
                "model_a_raw_response_y": json.dumps(
                    {
                        "impact_type": "mp",
                        "reason": "Legacy mp means trade.",
                    }
                ),
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    migration.migrate_file(path, dry_run=False)
    migrated = pd.read_csv(path, encoding="utf-8-sig").iloc[0]
    payload = json.loads(migrated["model_a_raw_response_y"])

    assert migrated["model_a_impact_type"] == "trade"
    assert payload["impact_type"] == "trade"
    assert payload["reason"] == "Legacy trade means trade."
    assert migrated["migration_version"] == migration.MIGRATION_VERSION
