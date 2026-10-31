"""Fail-closed, administrator-only evidence for the scoped intake release.

The endpoint intentionally returns only artifact integrity and schema-shape
booleans. It never returns database rows, SQL text, credentials, connection
settings, or arbitrary information-schema metadata.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header
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
_TEXT = ("utf8mb4", "utf8mb4_unicode_ci")
_JSON = ("utf8mb4", "utf8mb4_bin")
# name, column_type, nullable, default, extra, charset, collation.  This is an
# ordered contract: an added/reordered/coerced column is not an accepted schema.
EXPECTED_COLUMNS = (
    ("report_uuid", "char(36)", "NO", None, "", *_TEXT),
    ("estate_id", "char(36)", "NO", None, "", *_TEXT),
    ("actor_username", "varchar(80)", "NO", None, "", *_TEXT),
    ("actor_role", "varchar(40)", "NO", None, "", *_TEXT),
    ("entry_kind", "enum('field_observation','damage_report','work_report','cellar_note','agronomy_note','enology_reading')", "NO", None, "", *_TEXT),
    ("occurred_at", "datetime(6)", "NO", None, "", None, None),
    ("received_at", "datetime(6)", "NO", None, "", None, None),
    ("source_timezone", "varchar(64)", "NO", None, "", *_TEXT),
    ("payload_sha256", "char(64)", "NO", None, "", *_TEXT),
    ("payload_json", "longtext", "NO", None, "", *_JSON),
    ("correction_of_report_uuid", "char(36)", "YES", "NULL", "", *_TEXT),
    ("ingest_status", "enum('validated','conflict','rejected')", "NO", "validated", "", *_TEXT),
    ("validation_reason", "varchar(160)", "YES", "NULL", "", *_TEXT),
    ("ingest_result_json", "longtext", "NO", None, "", *_JSON),
    ("status", "enum('pending_review','approved','rejected','correction_required','superseded')", "NO", "pending_review", "", *_TEXT),
    ("revision", "bigint(20) unsigned", "NO", "1", "", None, None),
    ("reviewed_by", "varchar(160)", "YES", "NULL", "", *_TEXT),
    ("reviewed_at", "datetime(6)", "YES", "NULL", "", None, None),
    ("review_note", "text", "YES", "NULL", "", *_TEXT),
    ("created_at", "datetime(6)", "NO", "current_timestamp(6)", "", None, None),
    ("updated_at", "datetime(6)", "NO", "current_timestamp(6)", "on update current_timestamp(6)", None, None),
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
    table: dict[str, Any] | None = None,
    database: str = "baiamonte_vineyard",
) -> dict[str, bool]:
    def normalized_default(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if len(text) >= 2 and text[0] == text[-1] == "'":
            text = text[1:-1].replace("''", "'")
        return text.casefold()

    expected_names = {row[0] for row in EXPECTED_COLUMNS}
    actual_columns = []
    for row in sorted(columns, key=lambda item: int(item.get("ordinal_position") or 0)):
        actual_columns.append((
            str(row.get("column_name") or ""),
            str(row.get("column_type") or "").casefold(),
            str(row.get("is_nullable") or "").upper(),
            normalized_default(row.get("column_default")),
            " ".join(str(row.get("extra") or "").casefold().split()),
            str(row.get("character_set_name") or "").casefold() or None,
            str(row.get("collation_name") or "").casefold() or None,
        ))
    expected_columns = [
        (name, column_type.casefold(), nullable, normalized_default(default), extra, charset, collation)
        for name, column_type, nullable, default, extra, charset, collation in EXPECTED_COLUMNS
    ]
    by_name = {row[0]: row for row in actual_columns}
    index_map: dict[str, list[tuple[str, int, str]]] = {}
    for row in sorted(indexes, key=lambda item: (str(item.get("index_name") or ""), int(item.get("seq_in_index") or 0))):
        index_map.setdefault(str(row.get("index_name") or ""), []).append((
            str(row.get("column_name") or ""),
            int(row.get("non_unique") or 0),
            str(row.get("index_type") or "").upper(),
        ))
    fk_map = {
        str(row.get("constraint_name") or ""): (
            str(row.get("column_name") or ""),
            str(row.get("referenced_table_schema") or ""),
            str(row.get("referenced_table_name") or ""),
            str(row.get("referenced_column_name") or ""),
            str(row.get("delete_rule") or "").upper(),
            str(row.get("update_rule") or "").upper(),
        )
        for row in foreign_keys
    }
    normalized_create = " ".join(str(create_sql or "").casefold().split())
    expected_indexes = {
        "PRIMARY": [("report_uuid", 0, "BTREE")],
        "ix_mobile_intake_source_review": [(name, 1, "BTREE") for name in ("estate_id", "status", "entry_kind", "received_at")],
        "fk_mobile_intake_source_correction": [("correction_of_report_uuid", 1, "BTREE")],
    }
    table = table or {}
    checks = {
        "table_present": bool(columns),
        "column_names_exact": len(by_name) == len(actual_columns) and set(by_name) == expected_names,
        "column_contract_exact": actual_columns == expected_columns,
        "indexes_exact": index_map == expected_indexes,
        "foreign_keys_exact": fk_map == {
            "fk_mobile_intake_source_estate": ("estate_id", database, "estates", "id", "RESTRICT", "RESTRICT"),
            "fk_mobile_intake_source_correction": ("correction_of_report_uuid", database, "mobile_intake_source_drafts", "report_uuid", "RESTRICT", "RESTRICT"),
        },
        "table_engine_exact": str(table.get("engine") or "").casefold() == "innodb",
        "table_collation_exact": str(table.get("table_collation") or "").casefold() == "utf8mb4_unicode_ci",
        "payload_json_check": "json_valid(`payload_json`)" in normalized_create,
        "ingest_result_json_check": "json_valid(`ingest_result_json`)" in normalized_create,
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
                "SELECT column_name,column_type,is_nullable,column_default,extra,character_set_name,collation_name,ordinal_position FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name='mobile_intake_source_drafts' ORDER BY ordinal_position",
                (database,),
            )
            columns = list(cursor.fetchall())
            cursor.execute(
                "SELECT index_name,column_name,seq_in_index,non_unique,index_type FROM information_schema.statistics "
                "WHERE table_schema=%s AND table_name='mobile_intake_source_drafts' ORDER BY index_name,seq_in_index",
                (database,),
            )
            indexes = list(cursor.fetchall())
            cursor.execute(
                "SELECT k.constraint_name,k.column_name,k.referenced_table_schema,k.referenced_table_name,k.referenced_column_name,r.delete_rule,r.update_rule "
                "FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r "
                "ON r.constraint_schema=k.constraint_schema AND r.table_name=k.table_name AND r.constraint_name=k.constraint_name "
                "WHERE k.table_schema=%s AND k.table_name='mobile_intake_source_drafts' AND k.referenced_table_name IS NOT NULL",
                (database,),
            )
            foreign_keys = list(cursor.fetchall())
            cursor.execute(
                "SELECT engine,table_collation FROM information_schema.tables "
                "WHERE table_schema=%s AND table_name='mobile_intake_source_drafts'",
                (database,),
            )
            table = cursor.fetchone() or {}
            cursor.execute("SHOW CREATE TABLE `mobile_intake_source_drafts`")
            create_row = cursor.fetchone() or {}
            create_sql = str(create_row.get("Create Table") or create_row.get("Create View") or "")
        return {
            "ledger": {name: name in applied for name in EXPECTED_MIGRATIONS},
            "schema": evaluate_intake_schema(columns, indexes, foreign_keys, create_sql, table, database),
        }
    finally:
        connection.close()


def build_release_evidence(
    *,
    manifest_path: Path = MANIFEST_PATH,
    package_root: Path = PACKAGE_ROOT,
    entrypoint_path: Path = Path("/entrypoint.py"),
    entrypoint_verified: bool | None = None,
    expected_manifest_sha256: str | None = None,
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
    external_manifest_match = bool(
        manifest_hash
        and expected_manifest_sha256
        and len(expected_manifest_sha256) == 64
        and hmac.compare_digest(manifest_hash, expected_manifest_sha256.casefold())
    )
    parent_entrypoint = parent_is_packaged_entrypoint() if entrypoint_verified is None else entrypoint_verified
    ready = all((manifest_valid, packaged_files_valid, external_manifest_match, parent_entrypoint, exact_allowlist, database_evidence_available, ledger_complete, schema.get("ready") is True))
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
            "external_manifest_match": external_manifest_match,
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
def release_evidence(
    x_baiamonte_expected_manifest_sha256: str | None = Header(default=None),
) -> Any:
    payload = build_release_evidence(expected_manifest_sha256=x_baiamonte_expected_manifest_sha256)
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload
