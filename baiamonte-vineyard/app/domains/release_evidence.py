"""Fail-closed, administrator-only evidence for the scoped intake release.

The endpoint intentionally returns only artifact integrity and schema-shape
booleans. It never returns database rows, SQL text, credentials, connection
settings, or arbitrary information-schema metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..access import authorize_admin
from ..config import addon_version, get_settings
from ..db import configured_migration_allowlist, connect


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PACKAGE_ROOT / "release-manifest.json"
EXPECTED_MIGRATIONS = (
    "232_mobile_intake_source_drafts.sql",
    "233_mobile_intake_result_upgrade.sql",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_release_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release manifest must be an object")
    return value


def verify_packaged_files(
    manifest: dict[str, Any],
    *,
    package_root: Path = PACKAGE_ROOT,
    entrypoint_path: Path = Path("/entrypoint.py"),
) -> dict[str, bool]:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return {}
    results: dict[str, bool] = {}
    for relative, expected in sorted(files.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            results[str(relative)] = False
            continue
        path = entrypoint_path if relative == "entrypoint.py" else package_root / relative
        try:
            results[relative] = path.is_file() and _sha256(path) == expected
        except OSError:
            results[relative] = False
    return results


def parent_is_packaged_entrypoint() -> bool:
    """Confirm Uvicorn is a child of the Dockerfile's packaged entrypoint."""
    try:
        parts = [part.decode("utf-8", "replace") for part in Path(f"/proc/{os.getppid()}/cmdline").read_bytes().split(b"\0") if part]
    except OSError:
        return False
    return bool(parts and Path(parts[0]).name.startswith("python") and len(parts) > 1 and parts[1] == "/entrypoint.py")


def evaluate_intake_schema(
    columns: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
    foreign_keys: list[dict[str, Any]],
    create_sql: str,
) -> dict[str, bool]:
    by_name = {str(row.get("column_name") or ""): row for row in columns}
    required = {
        "report_uuid", "estate_id", "actor_username", "actor_role", "entry_kind",
        "occurred_at", "received_at", "source_timezone", "payload_sha256",
        "payload_json", "correction_of_report_uuid", "ingest_status",
        "validation_reason", "ingest_result_json", "status", "revision",
        "reviewed_by", "reviewed_at", "review_note", "created_at", "updated_at",
    }
    index_map: dict[str, list[str]] = {}
    for row in sorted(indexes, key=lambda item: (str(item.get("index_name") or ""), int(item.get("seq_in_index") or 0))):
        index_map.setdefault(str(row.get("index_name") or ""), []).append(str(row.get("column_name") or ""))
    fk_map = {
        str(row.get("constraint_name") or ""): (
            str(row.get("column_name") or ""),
            str(row.get("referenced_table_name") or ""),
            str(row.get("referenced_column_name") or ""),
        )
        for row in foreign_keys
    }
    normalized_create = " ".join(str(create_sql or "").casefold().split())
    entry_kind = str(by_name.get("entry_kind", {}).get("column_type") or "").casefold()
    ingest_status = str(by_name.get("ingest_status", {}).get("column_type") or "").casefold()
    review_status = str(by_name.get("status", {}).get("column_type") or "").casefold()
    checks = {
        "table_present": bool(columns),
        "required_columns_present": required.issubset(by_name),
        "primary_key_exact": index_map.get("PRIMARY") == ["report_uuid"],
        "review_index_exact": index_map.get("ix_mobile_intake_source_review") == ["estate_id", "status", "entry_kind", "received_at"],
        "estate_foreign_key_exact": fk_map.get("fk_mobile_intake_source_estate") == ("estate_id", "estates", "id"),
        "correction_foreign_key_exact": fk_map.get("fk_mobile_intake_source_correction") == ("correction_of_report_uuid", "mobile_intake_source_drafts", "report_uuid"),
        "payload_json_not_null": str(by_name.get("payload_json", {}).get("is_nullable") or "").upper() == "NO" and "json_valid(`payload_json`)" in normalized_create,
        "ingest_result_json_not_null": str(by_name.get("ingest_result_json", {}).get("is_nullable") or "").upper() == "NO" and "json_valid(`ingest_result_json`)" in normalized_create,
        "revision_unsigned_not_null": str(by_name.get("revision", {}).get("is_nullable") or "").upper() == "NO" and "unsigned" in str(by_name.get("revision", {}).get("column_type") or "").casefold(),
        "entry_kind_enum_exact": all(value in entry_kind for value in ("field_observation", "damage_report", "work_report", "cellar_note", "agronomy_note", "enology_reading")),
        "ingest_status_enum_exact": all(value in ingest_status for value in ("validated", "conflict", "rejected")),
        "review_status_enum_exact": all(value in review_status for value in ("pending_review", "approved", "rejected", "correction_required", "superseded")),
    }
    checks["ready"] = all(checks.values())
    return checks


def collect_database_evidence(connection_factory: Callable[[], Any] = connect) -> dict[str, Any]:
    database = get_settings().db_name
    connection = connection_factory()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM schema_migrations WHERE version IN (%s,%s)",
                EXPECTED_MIGRATIONS,
            )
            applied = {str(row.get("version") or "") for row in cursor.fetchall()}
            cursor.execute(
                "SELECT column_name,data_type,column_type,is_nullable FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='mobile_intake_source_drafts' ORDER BY ordinal_position",
                (database,),
            )
            columns = list(cursor.fetchall())
            cursor.execute(
                "SELECT index_name,column_name,seq_in_index FROM information_schema.statistics "
                "WHERE table_schema=%s AND table_name='mobile_intake_source_drafts' ORDER BY index_name,seq_in_index",
                (database,),
            )
            indexes = list(cursor.fetchall())
            cursor.execute(
                "SELECT constraint_name,column_name,referenced_table_name,referenced_column_name "
                "FROM information_schema.key_column_usage WHERE table_schema=%s "
                "AND table_name='mobile_intake_source_drafts' AND referenced_table_name IS NOT NULL",
                (database,),
            )
            foreign_keys = list(cursor.fetchall())
            cursor.execute("SHOW CREATE TABLE `mobile_intake_source_drafts`")
            create_row = cursor.fetchone() or {}
            create_sql = str(create_row.get("Create Table") or create_row.get("Create View") or "")
        return {
            "ledger": {name: name in applied for name in EXPECTED_MIGRATIONS},
            "schema": evaluate_intake_schema(columns, indexes, foreign_keys, create_sql),
        }
    finally:
        connection.close()


def build_release_evidence(
    *,
    manifest_path: Path = MANIFEST_PATH,
    package_root: Path = PACKAGE_ROOT,
    entrypoint_path: Path = Path("/entrypoint.py"),
    entrypoint_verified: bool | None = None,
    database_collector: Callable[[], dict[str, Any]] = collect_database_evidence,
) -> dict[str, Any]:
    try:
        manifest = load_release_manifest(manifest_path)
        file_checks = verify_packaged_files(manifest, package_root=package_root, entrypoint_path=entrypoint_path)
        manifest_hash = _sha256(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError):
        manifest, file_checks, manifest_hash = {}, {}, None
    expected_allowlist = frozenset(EXPECTED_MIGRATIONS)
    try:
        effective_allowlist = configured_migration_allowlist()
    except ValueError:
        effective_allowlist = None
    manifest_allowlist = manifest.get("migration_allowlist")
    manifest_valid = (
        manifest.get("manifest_schema") == 1
        and manifest.get("release_version") == addon_version()
        and isinstance(manifest_allowlist, list)
        and frozenset(manifest_allowlist) == expected_allowlist
        and set(file_checks) == set((manifest.get("files") or {}).keys())
        and bool(file_checks)
    )
    try:
        database = database_collector()
        ledger = dict(database.get("ledger") or {})
        schema = dict(database.get("schema") or {})
        database_evidence_available = True
    except Exception:
        ledger = {name: False for name in EXPECTED_MIGRATIONS}
        schema = {"ready": False}
        database_evidence_available = False
    exact_allowlist = effective_allowlist == expected_allowlist
    ledger_complete = set(ledger) == expected_allowlist and all(ledger.values())
    packaged_files_valid = bool(file_checks) and all(file_checks.values())
    parent_entrypoint = parent_is_packaged_entrypoint() if entrypoint_verified is None else entrypoint_verified
    ready = all((manifest_valid, packaged_files_valid, parent_entrypoint, exact_allowlist, database_evidence_available, ledger_complete, schema.get("ready") is True))
    return {
        "ok": ready,
        "release": {
            "release_id": manifest.get("release_id"),
            "release_version": manifest.get("release_version"),
            "reviewed_base_commit": manifest.get("reviewed_base_commit"),
            "manifest_sha256": manifest_hash,
        },
        "integrity": {
            "manifest_valid": manifest_valid,
            "packaged_files": file_checks,
            "packaged_files_valid": packaged_files_valid,
            "entrypoint_verified": parent_entrypoint,
        },
        "migration_gate": {
            "expected_allowlist": list(EXPECTED_MIGRATIONS),
            "effective_allowlist_exact": exact_allowlist,
            "startup_completed": True,
            "ledger": ledger,
            "ledger_complete": ledger_complete,
        },
        "schema": schema,
        "database_evidence_available": database_evidence_available,
    }


@router.get("/release-evidence", dependencies=[Depends(authorize_admin)], response_model=None)
def release_evidence() -> Any:
    payload = build_release_evidence()
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload
