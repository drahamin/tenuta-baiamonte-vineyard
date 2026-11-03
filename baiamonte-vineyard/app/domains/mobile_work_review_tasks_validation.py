"""Default-off tasks-only Admin validation; no mobile route/grant or row output."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import threading
import time
from typing import Any, Callable, Mapping

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..access import authorize_admin, trusted_ingress_request
from ..config import get_settings, runtime_option
from ..remote_erp import reporting_row_revision as authoritative_reporting_token
from .mobile_work_review_connection import make_connection_factory
from .mobile_work_review_metadata import HEADERS, MetadataRoute, active_window as metadata_time_window
from .mobile_work_review_projection import SnapshotChanged, SourceUnavailable, project_page
from .mobile_work_review_source import SourceBoundary, capture_dataset


PATH = "/api/v1/admin/mobile-work-review-tasks-validation"
CONTRACT = "baiamonte.admin.work-review-tasks-validation.v1"
WINDOW_OPTION = "mobile_work_review_tasks_validation_window"
MAX_CAPTURES = 2
TOTAL_SECONDS = 24
router = APIRouter(prefix="/api/v1/admin", tags=["administration"], route_class=MetadataRoute)
_lock = threading.Lock()
_used = False


class ValidationWindowClosed(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def active_window(raw: Any, now: datetime) -> bool:
    return (isinstance(raw, dict) and set(raw) == {"issued_at", "expires_at", "reporting_columns_sha256"}
            and isinstance(raw["reporting_columns_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", raw["reporting_columns_sha256"]) is not None
            and metadata_time_window({"issued_at": raw["issued_at"], "expires_at": raw["expires_at"]}, now))


def require_validation_admin(request: Request) -> None:
    if not active_window(runtime_option(WINDOW_OPTION, None), utc_now()):
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


def collect_tasks_validation(settings: Any, window: dict[str, str], principal_scope: str, *,
                             clock: Callable[[], datetime] = utc_now,
                             monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """At most two complete tasks reads; all row/token/cursor data stays local.

    Each capture independently rolls back/closes; no source write, cache flush,
    extra dataset, fallback or automatic retry. Budgets are cooperative, not a
    hard wall-clock/RSS promise. Empty/small sources explicitly lack evidence.
    """
    if not active_window(window, clock()):
        raise ValidationWindowClosed()
    if not isinstance(principal_scope, str) or re.fullmatch(r"[0-9a-f]{64}", principal_scope) is None:
        raise SourceUnavailable("server principal scope unavailable")
    started = monotonic()
    boundary = SourceBoundary(settings.estate_id, settings.db_host, settings.db_port, settings.db_name)
    factory = make_connection_factory(settings, boundary)
    captures, counts, timings, checks = [], [], [], []
    for _index in range(MAX_CAPTURES):
        if not active_window(window, clock()):
            raise ValidationWindowClosed()
        if monotonic() - started >= TOTAL_SECONDS:
            raise SourceUnavailable("validation budget exceeded")
        observed = [0]
        def reference(data: Mapping[str, Any]) -> int:
            value = authoritative_reporting_token(data)
            observed[0] += 1
            return value
        before = monotonic()
        captured = capture_dataset(boundary=boundary, view="work", dataset="tasks", connection_factory=factory,
                                   clock=clock, monotonic=monotonic,
                                   reviewed_column_fingerprints={"tasks": window["reporting_columns_sha256"]},
                                   reporting_token_reference=reference)
        count = len(captured.snapshot.records)
        if observed[0] != count:
            raise SourceUnavailable("reference validation unavailable")
        captures.append(captured); counts.append(count); checks.append(observed[0])
        timings.append(round(monotonic() - before, 6))
    if not active_window(window, clock()):
        raise ValidationWindowClosed()
    if captures[0].snapshot.generation != captures[1].snapshot.generation:
        raise SnapshotChanged(SnapshotChanged.code)
    # Internal pure-projector arguments exercise a read shape; they do not
    # assign any live mobile session capability or change its role ceiling.
    args = {"estate_id": boundary.estate_id, "principal_scope": principal_scope, "role": "admin",
            "capabilities": frozenset({"work", "work.tasks.read"}), "view": "work", "dataset": "tasks",
            "state": "all", "limit": 1}
    first = project_page(captures[0].snapshot.records, now=clock(), evidence=captures[0].evidence, **args)
    if not first["available"] or len(first["items"]) != min(1, counts[0]):
        raise SourceUnavailable("internal first page unavailable")
    pagination = False
    if first["next_cursor"] is not None:
        second = project_page(captures[1].snapshot.records, now=clock(), evidence=captures[1].evidence,
                              cursor=first["next_cursor"], **args)
        if not second["available"] or len(second["items"]) != 1 or {item["id"] for item in first["items"]} & {item["id"] for item in second["items"]}:
            raise SourceUnavailable("internal second page unavailable")
        pagination = True
    elapsed = monotonic() - started
    if elapsed >= TOTAL_SECONDS:
        raise SourceUnavailable("validation budget exceeded")
    return {"ok": True, "contract": CONTRACT, "scope": "tasks_only_aggregate_validation", "read_only": True,
            "captures_completed": len(captures), "row_counts": counts, "capture_seconds": timings,
            "reference_tokens_checked": sum(checks), "reference_tokens_match": True if sum(checks) else None,
            "generation_stable": True, "pagination_verified": pagination,
            "evidence_status": "validated_bounded_read" if pagination else "partial_insufficient_rows",
            "unknown_item_clock_counts": [sum(record["source_updated_at"] is None for record in captured.snapshot.records) for captured in captures],
            "source_state": "degraded", "source_payload_returned": False, "database_cache_flushed": False,
            "total_seconds": round(elapsed, 6),
            "not_verified": ["historical_source_timezone", "business_field_semantics", "view_dependencies", "cross_dataset_generation",
                             "cold_database_latency", "mobile_session_authorization", "dataset_grants", "phone_acceptance"]}


@router.get("/mobile-work-review-tasks-validation", response_model=None)
def tasks_validation(request: Request) -> JSONResponse:
    global _used
    require_validation_admin(request)
    if request.query_params or request.headers.get("Content-Length", "0") != "0" or request.headers.get("Transfer-Encoding"):
        return JSONResponse({"ok": False, "error": "tasks_validation_accepts_no_parameters"}, status_code=422, headers=HEADERS)
    if not _lock.acquire(blocking=False):
        return JSONResponse({"ok": False, "error": "tasks_validation_busy"}, status_code=429, headers={**HEADERS, "Retry-After": "60"})
    try:
        if _used:
            return JSONResponse({"ok": False, "error": "tasks_validation_attempt_used"}, status_code=410, headers=HEADERS)
        window = runtime_option(WINDOW_OPTION, None)
        if not active_window(window, utc_now()):
            return JSONResponse({"ok": False, "error": "tasks_validation_window_closed"}, status_code=410, headers=HEADERS)
        _used = True
        try:
            settings = get_settings()
            principal = hashlib.sha256(json.dumps(["tasks-validation.v1", settings.estate_id, request.headers["X-Remote-User-Id"]], separators=(",", ":")).encode()).hexdigest()
            result = collect_tasks_validation(settings, window, principal)
            return JSONResponse(result, headers=HEADERS)
        except SnapshotChanged:
            return JSONResponse({"ok": False, "contract": CONTRACT, "error": "mobile_read_snapshot_changed"}, status_code=409, headers=HEADERS)
        except ValidationWindowClosed:
            return JSONResponse({"ok": False, "contract": CONTRACT, "error": "tasks_validation_window_closed"}, status_code=410, headers=HEADERS)
        except Exception as error:
            return JSONResponse({"ok": False, "contract": CONTRACT, "error": "tasks_validation_failed", "error_type": type(error).__name__}, status_code=503, headers=HEADERS)
    finally:
        _lock.release()
