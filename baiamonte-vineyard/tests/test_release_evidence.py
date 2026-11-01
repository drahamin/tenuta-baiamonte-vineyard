import json
from pathlib import Path
from unittest.mock import patch

from fastapi.responses import JSONResponse

from app.access import authorize_admin
from app.domains import release_evidence


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "232_mobile_intake_source_drafts.sql",
    "233_mobile_intake_result_upgrade.sql",
}


def _valid_schema_inputs():
    columns = [
        {
            "column_name": name, "column_type": column_type,
            "is_nullable": nullable, "column_default": default,
            "extra": extra, "character_set_name": charset,
            "collation_name": collation, "ordinal_position": ordinal,
        }
        for ordinal, (name, column_type, nullable, default, extra, charset, collation)
        in enumerate(release_evidence.EXPECTED_COLUMNS, start=1)
    ]
    indexes = [
        {"index_name": "PRIMARY", "column_name": "report_uuid", "seq_in_index": 1, "non_unique": 0, "index_type": "BTREE"},
        *[
            {"index_name": "ix_mobile_intake_source_review", "column_name": name, "seq_in_index": number, "non_unique": 1, "index_type": "BTREE"}
            for number, name in enumerate(("estate_id", "status", "entry_kind", "received_at"), start=1)
        ],
        {"index_name": "fk_mobile_intake_source_correction", "column_name": "correction_of_report_uuid", "seq_in_index": 1, "non_unique": 1, "index_type": "BTREE"},
    ]
    foreign_keys = [
        {"constraint_name": "fk_mobile_intake_source_estate", "column_name": "estate_id", "referenced_table_schema": "baiamonte_vineyard", "referenced_table_name": "estates", "referenced_column_name": "id", "delete_rule": "RESTRICT", "update_rule": "RESTRICT"},
        {"constraint_name": "fk_mobile_intake_source_correction", "column_name": "correction_of_report_uuid", "referenced_table_schema": "baiamonte_vineyard", "referenced_table_name": "mobile_intake_source_drafts", "referenced_column_name": "report_uuid", "delete_rule": "RESTRICT", "update_rule": "RESTRICT"},
    ]
    create_sql = "CREATE TABLE mobile_intake_source_drafts (CHECK (json_valid(`payload_json`)), CHECK (json_valid(`ingest_result_json`)))"
    table = {"engine": "InnoDB", "table_collation": "utf8mb4_unicode_ci"}
    return columns, indexes, foreign_keys, create_sql, table


def _temporary_release(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    entrypoint = tmp_path / "entrypoint.py"
    entrypoint.write_text("print('scoped entrypoint')\n", encoding="utf-8")
    tracked = package / "app" / "db.py"
    tracked.parent.mkdir()
    tracked.write_text("SCOPED = True\n", encoding="utf-8")
    manifest = {
        "manifest_schema": 1,
        "release_id": "test-intake-release",
        "release_version": "1.11.71",
        "reviewed_base_commit": "2a43c7c5f08477c9c6a84dea48f2fe1e2bfb58ce",
        "migration_allowlist": sorted(EXPECTED),
        "files": {
            "entrypoint.py": release_evidence._sha256(entrypoint),
            "app/db.py": release_evidence._sha256(tracked),
        },
    }
    manifest_path = package / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    database = lambda: {
        "ledger": {name: True for name in EXPECTED},
        "schema": {"ready": True, "ingest_result_json_not_null": True},
    }
    return package, entrypoint, manifest_path, tracked, database


def test_release_evidence_route_is_admin_only_and_read_only():
    routes = [route for route in release_evidence.router.routes if getattr(route, "path", "") == "/api/v1/admin/release-evidence"]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"GET"}
    assert route.dependencies[0].dependency is authorize_admin


def test_packaged_manifest_matches_unique_release_and_exact_allowlist():
    manifest = release_evidence.load_release_manifest(ROOT / "release-manifest.json")
    assert manifest["release_version"] == "1.11.75"
    assert manifest["reviewed_base_commit"] == "1606ada206873b1eaafb8202452661c524632f15"
    assert set(manifest["migration_allowlist"]) == EXPECTED
    assert "233_mobile_directory_projection.sql" not in manifest["migration_allowlist"]
    assert "app/remote_erp.py" in manifest["files"]
    assert "app/intelligence.py" in manifest["files"]
    configured = (ROOT / "config.yaml").read_text(encoding="utf-8")
    assert 'version: "1.11.75"' in configured
    checks = release_evidence.verify_packaged_files(
        manifest,
        package_root=ROOT,
        entrypoint_path=ROOT / "entrypoint.py",
    )
    assert checks and all(checks.values())
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY release-manifest.json release-manifest.json" in dockerfile
    assert 'CMD ["python3", "/entrypoint.py"]' in dockerfile


def test_exact_intake_schema_shape_is_required():
    columns, indexes, foreign_keys, create_sql, table = _valid_schema_inputs()
    evidence = release_evidence.evaluate_intake_schema(columns, indexes, foreign_keys, create_sql, table)
    assert evidence["ready"] is True
    assert evidence["ingest_result_json_check"] is True
    without_result = [row for row in columns if row["column_name"] != "ingest_result_json"]
    assert release_evidence.evaluate_intake_schema(without_result, indexes, foreign_keys, create_sql, table)["ready"] is False


def test_release_evidence_accepts_only_complete_verified_release(tmp_path):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        missing_external_review = release_evidence.build_release_evidence(
            manifest_path=manifest_path,
            package_root=package,
            entrypoint_path=entrypoint,
            entrypoint_verified=True,
            database_collector=database,
        )
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path,
            package_root=package,
            entrypoint_path=entrypoint,
            entrypoint_verified=True,
            expected_manifest_sha256=release_evidence._sha256(manifest_path),
            database_collector=database,
        )
    assert missing_external_review["ok"] is False
    assert missing_external_review["integrity"]["external_manifest_match"] is False
    assert payload["ok"] is True
    assert payload["integrity"]["external_manifest_match"] is True
    assert payload["migration_gate"]["effective_allowlist_exact"] is True
    assert payload["migration_gate"]["ledger_complete"] is True


def test_tampered_artifact_fails_closed(tmp_path):
    package, entrypoint, manifest_path, tracked, database = _temporary_release(tmp_path)
    tracked.write_text("SCOPED = False\n", encoding="utf-8")
    with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
            entrypoint_verified=True, expected_manifest_sha256=release_evidence._sha256(manifest_path),
            database_collector=database,
        )
    assert payload["ok"] is False
    assert payload["integrity"]["packaged_files_valid"] is False


def test_missing_effective_allowlist_fails_closed(tmp_path):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    with patch.dict("os.environ", {}, clear=True), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
            entrypoint_verified=True, expected_manifest_sha256=release_evidence._sha256(manifest_path),
            database_collector=database,
        )
    assert payload["ok"] is False
    assert payload["migration_gate"]["effective_allowlist_exact"] is False


def test_missing_ledger_entry_or_schema_fails_closed(tmp_path):
    package, entrypoint, manifest_path, _tracked, _database = _temporary_release(tmp_path)
    incomplete = lambda: {
        "ledger": {"232_mobile_intake_source_drafts.sql": True, "233_mobile_intake_result_upgrade.sql": False},
        "schema": {"ready": False, "ingest_result_json_not_null": False},
    }
    with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
            entrypoint_verified=True, expected_manifest_sha256=release_evidence._sha256(manifest_path),
            database_collector=incomplete,
        )
    assert payload["ok"] is False
    assert payload["migration_gate"]["ledger_complete"] is False
    assert payload["schema"]["ready"] is False


def test_adversarial_schema_variants_fail_closed_and_return_503(tmp_path, monkeypatch):
    package, entrypoint, manifest_path, _tracked, _database = _temporary_release(tmp_path)
    columns, indexes, foreign_keys, create_sql, table = _valid_schema_inputs()
    variants = []
    enum_superset = [dict(row) for row in columns]
    next(row for row in enum_superset if row["column_name"] == "entry_kind")["column_type"] = "enum('field_observation','damage_report','work_report','cellar_note','agronomy_note','enology_reading','raw_sql')"
    variants.append((enum_superset, indexes, foreign_keys, create_sql, table))
    enum_reordered = [dict(row) for row in columns]
    next(row for row in enum_reordered if row["column_name"] == "status")["column_type"] = "enum('approved','pending_review','rejected','correction_required','superseded')"
    variants.append((enum_reordered, indexes, foreign_keys, create_sql, table))
    wrong_revision = [dict(row) for row in columns]
    next(row for row in wrong_revision if row["column_name"] == "revision")["column_type"] = "int(10) unsigned"
    variants.append((wrong_revision, indexes, foreign_keys, create_sql, table))
    wrong_actor = [dict(row) for row in columns]
    next(row for row in wrong_actor if row["column_name"] == "actor_username")["column_type"] = "int(11)"
    variants.append((wrong_actor, indexes, foreign_keys, create_sql, table))
    wrong_default = [dict(row) for row in columns]
    next(row for row in wrong_default if row["column_name"] == "ingest_status")["column_default"] = "rejected"
    variants.append((wrong_default, indexes, foreign_keys, create_sql, table))
    wrong_collation = [dict(row) for row in columns]
    next(row for row in wrong_collation if row["column_name"] == "actor_username")["collation_name"] = "utf8mb4_general_ci"
    variants.append((wrong_collation, indexes, foreign_keys, create_sql, table))
    wrong_index = [dict(row) for row in indexes]
    review_rows = [row for row in wrong_index if row["index_name"] == "ix_mobile_intake_source_review"]
    review_rows[1]["seq_in_index"], review_rows[2]["seq_in_index"] = 3, 2
    variants.append((columns, wrong_index, foreign_keys, create_sql, table))
    cascade_foreign_keys = [dict(row) for row in foreign_keys]
    cascade_foreign_keys[0]["delete_rule"] = "CASCADE"
    variants.append((columns, indexes, cascade_foreign_keys, create_sql, table))
    cross_schema_foreign_keys = [dict(row) for row in foreign_keys]
    cross_schema_foreign_keys[0]["referenced_table_schema"] = "other_database"
    variants.append((columns, indexes, cross_schema_foreign_keys, create_sql, table))
    wrong_update_foreign_keys = [dict(row) for row in foreign_keys]
    wrong_update_foreign_keys[0]["update_rule"] = "CASCADE"
    variants.append((columns, indexes, wrong_update_foreign_keys, create_sql, table))
    variants.append((columns, indexes, foreign_keys, create_sql, {"engine": "MyISAM", "table_collation": "utf8mb4_unicode_ci"}))
    variants.append((columns, indexes, foreign_keys, create_sql, {"engine": "InnoDB", "table_collation": "utf8mb4_general_ci"}))
    variants.append((columns, indexes, foreign_keys, "CREATE TABLE mobile_intake_source_drafts ()", table))

    build = release_evidence.build_release_evidence
    for variant_columns, variant_indexes, variant_foreign_keys, variant_create, variant_table in variants:
        schema = release_evidence.evaluate_intake_schema(variant_columns, variant_indexes, variant_foreign_keys, variant_create, variant_table)
        assert schema["ready"] is False
        database = lambda schema=schema: {
            "ledger": {name: True for name in EXPECTED},
            "schema": schema,
        }
        with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
            payload = build(
                manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
                entrypoint_verified=True, expected_manifest_sha256=release_evidence._sha256(manifest_path),
                database_collector=database,
            )
        assert payload["ok"] is False
        monkeypatch.setattr(release_evidence, "build_release_evidence", lambda **_kwargs: payload)
        response = release_evidence.release_evidence(release_evidence._sha256(manifest_path))
        assert isinstance(response, JSONResponse)
        assert response.status_code == 503


def test_database_diagnostic_failure_returns_bounded_503(monkeypatch):
    monkeypatch.setattr(release_evidence, "build_release_evidence", lambda **_kwargs: {
        "ok": False,
        "release": {},
        "integrity": {"packaged_files_valid": False},
        "migration_gate": {"ledger_complete": False},
        "schema": {"ready": False},
        "database_evidence_available": False,
    })
    response = release_evidence.release_evidence("0" * 64)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert b"password" not in response.body.lower()
    assert b"secret" not in response.body.lower()
