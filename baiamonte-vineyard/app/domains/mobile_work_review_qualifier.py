"""Unregistered, default-off Admin qualification proposal. No live activation.

Fixed six-source read-only checks; never accept SQL/object/estate parameters.
Only schema/shape/count/timing evidence leaves the temporary process memory.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
import threading
import time
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import pymysql

from ..access import authorize_admin, trusted_ingress_request
from ..config import get_settings, runtime_option
from ..db import ProfilingDictCursor


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
PATH = "/api/v1/admin/mobile-work-review-qualification"
CONTRACT = "baiamonte.admin.work-review-qualification.v1"
RESPONSE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}
MAX_ROWS = 2000
MAX_METADATA_ROWS = 256
TOTAL_SECONDS = 12
_SAFE_FIELDS = {
    "tasks": ("title", "status", "priority", "due_date", "completed_at", "category", "block_id", "season_id", "estimated_hours"),
    "work_activities": ("title", "status", "category", "activity_date", "end_date", "block_id", "task_id", "season_id", "labor_hours", "worker_count"),
    "v_open_work": ("title", "status", "priority", "due_date", "days_until_due", "category", "block_code", "block_name"),
    "issues_decisions": ("issue_text", "issue_type", "subject_ref", "status", "priority", "opened_date", "due_date", "closed_date", "decision_action"),
    "ro_lab_decision_queue": ("sample_id", "sample_name", "sample_type", "lab_date", "result_count", "flagged_results", "needs_review", "review_status", "next_check_at"),
    "lab_reviews": ("sample_id", "decision_type", "review_status", "decision_action", "interpretation", "enologist_approval_required", "approved_at", "next_check_at", "created_at", "updated_at"),
}
SOURCE_SPECS = {
    object_name: {
        "identity": "sample_id" if object_name == "ro_lab_decision_queue" else "id",
        "clock": "updated_at" if object_name in {"tasks", "work_activities", "lab_reviews"} else None,
        "fields": tuple(dict.fromkeys(("estate_id", "sample_id" if object_name == "ro_lab_decision_queue" else "id", *fields,
                                       *(("updated_at",) if object_name in {"tasks", "work_activities", "lab_reviews"} else ())))),
        "view": object_name in {"v_open_work", "ro_lab_decision_queue"},
    }
    for object_name, fields in _SAFE_FIELDS.items()
}
_attempt_lock = threading.Lock()
_attempt_used = False


class QualificationFailure(RuntimeError):
    pass


def _settings_scope(settings: Any) -> str:
    if (settings.db_host, settings.db_port, settings.db_name) != ("core-mariadb", 3306, "baiamonte_vineyard"):
        raise QualificationFailure("database_scope_denied")
    estate = settings.estate_id
    if not isinstance(estate, str) or str(UUID(estate)) != estate:
        raise QualificationFailure("estate_scope_invalid")
    return estate


def _connection(settings: Any):
    _settings_scope(settings)
    # Existing app credential stays on HA, never exported/newly provisioned.
    return pymysql.connect(host=settings.db_host, port=settings.db_port, database=settings.db_name,
                           user=settings.db_user, password=settings.db_password, charset="utf8mb4",
                           cursorclass=ProfilingDictCursor, autocommit=False,
                           connect_timeout=3, read_timeout=3, write_timeout=3)


def collect_qualification(settings: Any, *, connection_factory: Callable[[Any], Any] = _connection,
                          monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Read one rollback-only snapshot; no source rows in returned evidence.

    This qualifies bounded safe-column reads, NOT full reporting fingerprints,
    view predicate semantics, a mobile session or cross-request isolation.
    """
    estate = _settings_scope(settings)
    started = monotonic()
    connection = connection_factory(settings)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION max_statement_time=2")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            objects = tuple(SOURCE_SPECS)
            cursor.execute(
                "SELECT c.table_name,c.column_name,t.table_type FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name "
                "WHERE c.table_schema=DATABASE() AND c.table_name IN (" + ",".join(["%s"] * len(objects)) + ") "
                "ORDER BY c.table_name,c.ordinal_position LIMIT 256", objects,
            )
            metadata = cursor.fetchall()
            if len(metadata) >= MAX_METADATA_ROWS:
                raise QualificationFailure("metadata_bound_exceeded")
            columns = {name: set() for name in objects}
            kinds = {}
            for row in metadata:
                if row["table_name"] not in columns:
                    raise QualificationFailure("metadata_scope_mismatch")
                columns[row["table_name"]].add(row["column_name"])
                kinds[row["table_name"]] = row["table_type"]
            results = {}
            for name, spec in SOURCE_SPECS.items():
                if monotonic() - started >= TOTAL_SECONDS:
                    raise QualificationFailure("qualification_budget_exceeded")
                missing = sorted(set(spec["fields"]) - columns[name])
                kind_ok = kinds.get(name) == ("VIEW" if spec["view"] else "BASE TABLE")
                evidence = {"required_columns_present": not missing, "missing_required_columns": missing,
                            "object_kind_verified": kind_ok, "source_clock_field": spec["clock"],
                            "native_revision_column_present": "revision" in columns[name],
                            "source_clock_timezone_verified": False, "source_definition_verified": False}
                results[name] = evidence
                if missing or not kind_ok:
                    evidence["read_passed"] = False
                    continue  # Never fall back to another view or underlying table.
                before = monotonic()
                # Identity strings are bounded; all other field values become
                # nullness bits on the DB server, never text/measurements here.
                selected = [f"LEFT(`{field}`,192) AS `{field}`" if field in {"estate_id", spec["identity"]}
                            else f"CASE WHEN `{field}` IS NULL THEN NULL ELSE 1 END AS `{field}`" for field in spec["fields"]]
                cursor.execute("SELECT " + ",".join(selected) +
                               f" FROM `{name}` WHERE estate_id=%s ORDER BY `{spec['identity']}` LIMIT 2001", (estate,))
                rows = cursor.fetchall()
                elapsed = monotonic() - before
                if monotonic() - started >= TOTAL_SECONDS:
                    raise QualificationFailure("qualification_budget_exceeded")
                ids = [row.get(spec["identity"]) for row in rows]
                valid = [value for value in ids if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:|\-]{0,190}", value)]
                duplicates = sum(count - 1 for count in Counter(valid).values())
                scope_ok = all(row.get("estate_id") == estate for row in rows)
                nullness_ok = all(row.get(field) is None or row.get(field) == 1 for row in rows
                                  for field in spec["fields"] if field not in {"estate_id", spec["identity"]})
                bound_ok = len(rows) <= MAX_ROWS
                evidence.update({"row_count_or_lower_bound": len(rows), "row_bound_exceeded": not bound_ok,
                                 "identity_invalid_count": len(ids) - len(valid), "duplicate_identity_count": duplicates,
                                 "estate_scope_verified": scope_ok, "field_nullness_projection_verified": nullness_ok,
                                 "source_timestamp_present_count": sum(row.get(spec["clock"]) is not None for row in rows) if spec["clock"] else 0,
                                 "read_seconds": round(elapsed, 6),
                                 "read_passed": bound_ok and len(valid) == len(ids) and not duplicates and scope_ok and nullness_ok})
                # Drop content before the next source; never serialize or log it.
                del rows
            return {"ok": all(value["read_passed"] for value in results.values()), "contract": CONTRACT,
                    "scope": "bounded_schema_identity_field_nullness_only", "read_only": True,
                    "application_cache": "unused", "database_cache_flushed": False,
                    "total_seconds": round(monotonic() - started, 6), "sources": results,
                    "not_verified": ["full_reporting_token_provenance", "view_predicate_semantics", "source_clock_timezone",
                                     "field_value_semantics", "full_projection_latency", "cross_request_generation", "mobile_authorization", "phone_acceptance"]}
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def active_window(raw: Any, now: datetime) -> bool:
    try:
        if not isinstance(raw, dict) or set(raw) != {"issued_at", "expires_at"}:
            return False
        if not all(isinstance(raw[key], str) for key in raw):
            return False
        issued, expires = (datetime.fromisoformat(raw[key].replace("Z", "+00:00")) for key in ("issued_at", "expires_at"))
        return (issued.tzinfo is not None and expires.tzinfo is not None
                and 0 < (expires - issued).total_seconds() <= 900 and issued <= now < expires)
    except (TypeError, ValueError, OverflowError):
        return False


def require_qualification_admin(request: Request) -> None:
    # No option/schema change is shipped here; absent window is default-off.
    if not active_window(runtime_option("mobile_work_review_qualification_window", None), datetime.now(timezone.utc)):
        raise HTTPException(404, "Not found", headers=RESPONSE_HEADERS)
    settings = get_settings()
    if (not settings.trust_home_assistant_ingress or not trusted_ingress_request(request)
            or not request.headers.get("X-Ingress-Path", "").startswith("/api/hassio_ingress/")
            or re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request.headers.get("X-Remote-User-Id", "")) is None):
        raise HTTPException(401, "Authenticated HA ingress required", headers=RESPONSE_HEADERS)
    # API-key-only and direct app-session authorization are deliberately absent.
    try:
        authorize_admin(request, x_api_key=None, settings=settings)
    except HTTPException as error:
        raise HTTPException(error.status_code, error.detail, headers={**(error.headers or {}), **RESPONSE_HEADERS}) from None


@router.get("/mobile-work-review-qualification", dependencies=[Depends(require_qualification_admin)])
def qualification(request: Request) -> JSONResponse:
    global _attempt_used
    headers = RESPONSE_HEADERS
    if request.query_params or request.headers.get("Content-Length", "0") != "0" or request.headers.get("Transfer-Encoding"):
        return JSONResponse({"ok": False, "error": "qualification_accepts_no_parameters"}, status_code=422, headers=headers)
    if not _attempt_lock.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "qualification_busy"}, status_code=429, headers={**headers, "Retry-After": "60"})
    try:
        if _attempt_used:
            return JSONResponse({"ok": False, "error": "qualification_attempt_used"}, status_code=410, headers=headers)
        _attempt_used = True  # At most one attempt per app process, including failures.
        try:
            result = collect_qualification(get_settings())
        except Exception as error:
            # No exception message/SQL/params/connection settings can leave here.
            result = {"ok": False, "contract": CONTRACT, "error": "qualification_failed", "error_type": type(error).__name__}
        return JSONResponse(result, status_code=200 if result["ok"] else 503, headers=headers)
    finally:
        _attempt_lock.release()
