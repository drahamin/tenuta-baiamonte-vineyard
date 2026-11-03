"""Default-off, one-attempt Admin metadata inspection; never reads source rows."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import threading
import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import pymysql
from starlette.datastructures import MutableHeaders

from ..access import authorize_admin, trusted_ingress_request
from ..config import get_settings, runtime_option
from ..db import ProfilingDictCursor


PATH = "/api/v1/admin/mobile-work-review-metadata"
CONTRACT = "baiamonte.admin.work-review-metadata.v1"
WINDOW_OPTION = "mobile_work_review_metadata_window"
OBJECTS = ("tasks", "work_activities", "v_open_work", "issues_decisions", "ro_lab_decision_queue", "lab_reviews")
VIEWS = ("v_open_work", "ro_lab_decision_queue")
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}
FORBIDDEN = ("password", "secret", "token", "credential", "authorization", "api_key", "private_key", "cookie", "webhook", "cost", "price", "amount", "value_eur")
ENUM_FIELDS = frozenset({"status", "review_status", "decision_type", "priority"})
MAX_COLUMNS = 256
MAX_DEFINITION_BYTES = 65536
MAX_RESPONSE_BYTES = 256 * 1024
TOTAL_SECONDS = 12
_lock = threading.Lock()
_used = False


class MetadataRoute(APIRoute):
    async def handle(self, scope, receive, send):
        if self.methods and scope["method"] not in self.methods:
            raise HTTPException(405, "Method Not Allowed", headers={**HEADERS, "Allow": ", ".join(sorted(self.methods))})
        async def guarded_send(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(HEADERS)
            await send(message)
        await super().handle(scope, receive, guarded_send)


router = APIRouter(prefix="/api/v1/admin", tags=["administration"], route_class=MetadataRoute)


class MetadataFailure(RuntimeError):
    pass


def active_window(raw: Any, now: datetime) -> bool:
    try:
        if not isinstance(raw, dict) or set(raw) != {"issued_at", "expires_at"}:
            return False
        if any(not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is None for value in raw.values()):
            return False
        issued, expiry = (datetime.fromisoformat(raw[key].replace("Z", "+00:00")) for key in ("issued_at", "expires_at"))
        return 0 < (expiry - issued).total_seconds() <= 600 and issued <= now < expiry
    except (ValueError, TypeError, OverflowError):
        return False


def require_metadata_admin(request: Request) -> None:
    if not active_window(runtime_option(WINDOW_OPTION, None), datetime.now(timezone.utc)):
        raise HTTPException(404, "Not found", headers=HEADERS)
    settings = get_settings()
    if (not settings.trust_home_assistant_ingress or not trusted_ingress_request(request)
            or not request.headers.get("X-Ingress-Path", "").startswith("/api/hassio_ingress/")
            or re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request.headers.get("X-Remote-User-Id", "")) is None):
        raise HTTPException(401, "Authenticated HA ingress required", headers=HEADERS)
    try:
        authorize_admin(request, x_api_key=None, settings=settings)
    except HTTPException as error:
        raise HTTPException(error.status_code, error.detail, headers={**(error.headers or {}), **HEADERS}) from None


def _scope(settings: Any) -> None:
    if (settings.db_host, settings.db_port, settings.db_name) != ("core-mariadb", 3306, "baiamonte_vineyard"):
        raise MetadataFailure("database scope denied")


def _connection(settings: Any):
    _scope(settings)
    return pymysql.connect(host=settings.db_host, port=settings.db_port, database=settings.db_name,
                           user=settings.db_user, password=settings.db_password, charset="utf8mb4",
                           cursorclass=ProfilingDictCursor, autocommit=False,
                           connect_timeout=3, read_timeout=3, write_timeout=3)


def _text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > maximum:
        raise MetadataFailure("metadata text unavailable")
    return value


def collect_metadata(settings: Any, *, connection_factory: Callable[[Any], Any] = _connection,
                     monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Three fixed metadata SELECTs, rollback/close; no source-row SQL or fallback.

    View SQL is private schema evidence, not automatically approved semantics.
    Current timezone names cannot prove historical DATETIME writer semantics.
    The total budget is cooperative, not a hard wall-clock interruption.
    """
    _scope(settings)
    started = monotonic()
    connection = connection_factory(settings)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION max_statement_time=2")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cursor.execute("SELECT DATABASE() AS database_name,@@session.time_zone AS session_time_zone,"
                           "@@global.time_zone AS global_time_zone,@@system_time_zone AS system_time_zone,"
                           "UTC_TIMESTAMP(6) AS database_utc_now")
            environment = cursor.fetchone()
            if not environment or environment.get("database_name") != "baiamonte_vineyard":
                raise MetadataFailure("database scope denied")
            zones = {key: _text(environment.get(key), 128) for key in ("session_time_zone", "global_time_zone", "system_time_zone")}
            db_clock = environment.get("database_utc_now")
            if not isinstance(db_clock, datetime) or db_clock.tzinfo is not None:
                raise MetadataFailure("database UTC clock unavailable")
            zones["database_utc_now"] = db_clock.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            if monotonic() - started >= TOTAL_SECONDS:
                raise MetadataFailure("metadata budget exceeded")
            cursor.execute(
                "SELECT c.table_name AS table_name,c.column_name AS column_name,c.data_type AS data_type,"
                "c.is_nullable AS is_nullable,c.numeric_precision AS numeric_precision,c.numeric_scale AS numeric_scale,"
                "c.datetime_precision AS datetime_precision,c.character_maximum_length AS character_maximum_length,"
                "CASE WHEN c.column_name IN ('status','review_status','decision_type','priority') "
                "AND c.data_type='enum' AND OCTET_LENGTH(c.column_type)<=4096 THEN c.column_type ELSE NULL END AS enum_declaration,"
                "t.table_type AS table_type,t.engine AS engine FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name "
                "WHERE c.table_schema=DATABASE() AND c.table_name IN (" + ",".join(["%s"] * len(OBJECTS)) + ") "
                "ORDER BY c.table_name,c.ordinal_position LIMIT 257", OBJECTS,
            )
            metadata = cursor.fetchall()
            if len(metadata) > MAX_COLUMNS:
                raise MetadataFailure("column metadata bound exceeded")
            sources = {name: {"metadata_available": False, "expected_kind": "VIEW" if name in VIEWS else "BASE TABLE", "columns": []} for name in OBJECTS}
            seen = set()
            for row in metadata:
                name, column = row.get("table_name"), row.get("column_name")
                if name not in sources or not isinstance(column, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", column) is None or (name, column) in seen:
                    raise MetadataFailure("column metadata scope unavailable")
                seen.add((name, column))
                kind = _text(row.get("table_type"), 32)
                engine = row.get("engine")
                engine = None if engine is None else _text(engine, 96)
                current = sources[name]
                if current["metadata_available"] and (current["object_kind"], current["engine"]) != (kind, engine):
                    raise MetadataFailure("inconsistent object metadata")
                current.update(metadata_available=True, object_kind=kind, engine=engine,
                               object_kind_verified=kind == current["expected_kind"])
                if any(fragment in column.casefold() for fragment in FORBIDDEN):
                    continue  # Do not export excluded financial/security column names.
                datatype = _text(row.get("data_type"), 64)
                nullable = row.get("is_nullable")
                if nullable not in {"YES", "NO"}:
                    raise MetadataFailure("nullability metadata unavailable")
                item = {"name": column, "data_type": datatype, "nullable": nullable == "YES"}
                for key in ("numeric_precision", "numeric_scale", "datetime_precision", "character_maximum_length"):
                    value = row.get(key)
                    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**32):
                        raise MetadataFailure("type metadata unavailable")
                    item[key] = value
                if datatype == "enum" and column in ENUM_FIELDS:
                    declaration = row.get("enum_declaration")
                    item["enum_declaration"] = None if declaration is None else _text(declaration, 4096)
                current["columns"].append(item)
            if monotonic() - started >= TOTAL_SECONDS:
                raise MetadataFailure("metadata budget exceeded")
            cursor.execute(
                "SELECT table_name AS object_name,OCTET_LENGTH(view_definition) AS definition_bytes,"
                "CASE WHEN OCTET_LENGTH(view_definition)<=65536 THEN view_definition ELSE NULL END AS view_definition,"
                "check_option AS check_option,security_type AS security_type FROM information_schema.views "
                "WHERE table_schema=DATABASE() AND table_name IN (%s,%s) LIMIT 3", VIEWS,
            )
            definitions = cursor.fetchall()
            if len(definitions) > len(VIEWS):
                raise MetadataFailure("view metadata bound exceeded")
            views = {name: {"available": False} for name in VIEWS}
            seen_views = set()
            for row in definitions:
                name = row.get("object_name")
                if name not in views or name in seen_views:
                    raise MetadataFailure("view metadata scope unavailable")
                seen_views.add(name)
                size, sql = row.get("definition_bytes"), row.get("view_definition")
                if sql is None:
                    continue  # Permission denied, missing or oversized: never use another source.
                if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_DEFINITION_BYTES or len(sql.encode()) != size:
                    raise MetadataFailure("view definition bound unavailable")
                definition = {"view_definition": _text(sql, MAX_DEFINITION_BYTES),
                              "check_option": _text(row.get("check_option"), 32), "security_type": _text(row.get("security_type"), 32)}
                fingerprint = hashlib.sha256(json.dumps({"scheme": "baiamonte.reviewed-view.v1", "object": name, **definition},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
                views[name] = {"available": True, "definition_bytes": size, "fingerprint": fingerprint,
                               "review_status": "requires_private_semantic_review", **definition}
            if monotonic() - started >= TOTAL_SECONDS:
                raise MetadataFailure("metadata budget exceeded")
            result = {"ok": all(item["metadata_available"] and item["object_kind_verified"] for item in sources.values()) and all(item["available"] for item in views.values()),
                      "contract": CONTRACT, "read_only": True, "source_record_reads": 0,
                      "database_scope_verified": True, "sources": sources, "views": views, "timezone_settings": zones,
                      "total_seconds": round(monotonic() - started, 6),
                      "not_verified": ["historical_source_timezone", "view_predicate_semantics", "view_dependency_engines",
                                       "full_reporting_token_provenance", "cold_projection_latency", "mobile_authorization", "phone_acceptance"]}
            if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode()) > MAX_RESPONSE_BYTES:
                raise MetadataFailure("metadata response bound exceeded")
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
    elapsed = monotonic() - started
    if elapsed >= TOTAL_SECONDS:
        raise MetadataFailure("metadata cleanup budget exceeded")
    result["total_seconds"] = round(elapsed, 6)
    return result


@router.get("/mobile-work-review-metadata", response_model=None)
def metadata_inspection(request: Request) -> JSONResponse:
    global _used
    require_metadata_admin(request)
    if request.query_params or request.headers.get("Content-Length", "0") != "0" or request.headers.get("Transfer-Encoding"):
        return JSONResponse({"ok": False, "error": "metadata_accepts_no_parameters"}, status_code=422, headers=HEADERS)
    if not _lock.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "metadata_busy"}, status_code=429, headers={**HEADERS, "Retry-After": "60"})
    try:
        if _used:
            return JSONResponse({"ok": False, "error": "metadata_attempt_used"}, status_code=410, headers=HEADERS)
        _used = True  # One attempt per process, including failures; never automatic.
        try:
            result = collect_metadata(get_settings())
        except Exception as error:
            result = {"ok": False, "contract": CONTRACT, "error": "metadata_inspection_failed", "error_type": type(error).__name__}
        return JSONResponse(result, status_code=200 if result["ok"] else 503, headers=HEADERS)
    finally:
        _lock.release()
