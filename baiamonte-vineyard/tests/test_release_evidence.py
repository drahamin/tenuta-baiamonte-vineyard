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
    required = {
        "report_uuid": ("char(36)", "NO"),
        "estate_id": ("char(36)", "NO"),
        "actor_username": ("varchar(80)", "NO"),
        "actor_role": ("varchar(40)", "NO"),
        "entry_kind": ("enum('field_observation','damage_report','work_report','cellar_note','agronomy_note','enology_reading')", "NO"),
        "occurred_at": ("datetime(6)", "NO"),
        "received_at": ("datetime(6)", "NO"),
        "source_timezone": ("varchar(64)", "NO"),
        "payload_sha256": ("char(64)", "NO"),
        "payload_json": ("longtext", "NO"),
        "correction_of_report_uuid": ("char(36)", "YES"),
        "ingest_status": ("enum('validated','conflict','rejected')", "NO"),
        "validation_reason": ("varchar(160)", "YES"),
        "ingest_result_json": ("longtext", "NO"),
        "status": ("enum('pending_review','approved','rejected','correction_required','superseded')", "NO"),
        "revision": ("bigint(20) unsigned", "NO"),
        "reviewed_by": ("varchar(160)", "YES"),
        "reviewed_at": ("datetime(6)", "YES"),
        "review_note": ("text", "YES"),
        "created_at": ("datetime(6)", "NO"),
        "updated_at": ("datetime(6)", "NO"),
    }
    columns = [
        {"column_name": name, "data_type": column_type.split("(", 1)[0], "column_type": column_type, "is_nullable": nullable}
        for name, (column_type, nullable) in required.items()
    ]
    indexes = [
        {"index_name": "PRIMARY", "column_name": "report_uuid", "seq_in_index": 1},
        *[
            {"index_name": "ix_mobile_intake_source_review", "column_name": name, "seq_in_index": number}
            for number, name in enumerate(("estate_id", "status", "entry_kind", "received_at"), start=1)
        ],
    ]
    foreign_keys = [
        {"constraint_name": "fk_mobile_intake_source_estate", "column_name": "estate_id", "referenced_table_name": "estates", "referenced_column_name": "id"},
        {"constraint_name": "fk_mobile_intake_source_correction", "column_name": "correction_of_report_uuid", "referenced_table_name": "mobile_intake_source_drafts", "referenced_column_name": "report_uuid"},
    ]
    create_sql = "CREATE TABLE mobile_intake_source_drafts (CHECK (json_valid(`payload_json`)), CHECK (json_valid(`ingest_result_json`)))"
    return columns, indexes, foreign_keys, create_sql


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
    assert manifest["release_version"] == "1.11.71"
    assert set(manifest["migration_allowlist"]) == EXPECTED
    assert "233_mobile_directory_projection.sql" not in manifest["migration_allowlist"]
    configured = (ROOT / "config.yaml").read_text(encoding="utf-8")
    assert 'version: "1.11.71"' in configured
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
    columns, indexes, foreign_keys, create_sql = _valid_schema_inputs()
    evidence = release_evidence.evaluate_intake_schema(columns, indexes, foreign_keys, create_sql)
    assert evidence["ready"] is True
    assert evidence["ingest_result_json_not_null"] is True
    without_result = [row for row in columns if row["column_name"] != "ingest_result_json"]
    assert release_evidence.evaluate_intake_schema(without_result, indexes, foreign_keys, create_sql)["ready"] is False


def test_release_evidence_accepts_only_complete_verified_release(tmp_path):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path,
            package_root=package,
            entrypoint_path=entrypoint,
            entrypoint_verified=True,
            database_collector=database,
        )
    assert payload["ok"] is True
    assert payload["migration_gate"]["effective_allowlist_exact"] is True
    assert payload["migration_gate"]["ledger_complete"] is True


def test_tampered_artifact_fails_closed(tmp_path):
    package, entrypoint, manifest_path, tracked, database = _temporary_release(tmp_path)
    tracked.write_text("SCOPED = False\n", encoding="utf-8")
    with patch.dict("os.environ", {"BAIAMONTE_MIGRATION_ALLOWLIST": ",".join(sorted(EXPECTED))}), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
            entrypoint_verified=True, database_collector=database,
        )
    assert payload["ok"] is False
    assert payload["integrity"]["packaged_files_valid"] is False


def test_missing_effective_allowlist_fails_closed(tmp_path):
    package, entrypoint, manifest_path, _tracked, database = _temporary_release(tmp_path)
    with patch.dict("os.environ", {}, clear=True), patch.object(release_evidence, "addon_version", return_value="1.11.71"):
        payload = release_evidence.build_release_evidence(
            manifest_path=manifest_path, package_root=package, entrypoint_path=entrypoint,
            entrypoint_verified=True, database_collector=database,
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
            entrypoint_verified=True, database_collector=incomplete,
        )
    assert payload["ok"] is False
    assert payload["migration_gate"]["ledger_complete"] is False
    assert payload["schema"]["ready"] is False


def test_database_diagnostic_failure_returns_bounded_503(monkeypatch):
    monkeypatch.setattr(release_evidence, "build_release_evidence", lambda: {
        "ok": False,
        "release": {},
        "integrity": {"packaged_files_valid": False},
        "migration_gate": {"ledger_complete": False},
        "schema": {"ready": False},
        "database_evidence_available": False,
    })
    response = release_evidence.release_evidence()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert b"password" not in response.body.lower()
    assert b"secret" not in response.body.lower()
