"""Unregistered Work/Review parity projection; no database, routes or grants.

Reuse the frozen ERP DTO, not the deployed direct v1 response shape. A future
adapter must validate its HA session and supply an authoritative bounded
snapshot/revisions. Function arguments are not authentication evidence.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence
from uuid import UUID


CONTRACT = "baiamonte.mobile-work-review.v1"
DATASETS = {
    ("work", "tasks"): ("tasks", ("title", "status", "priority", "due_date", "completed_at", "category", "block_id", "season_id", "estimated_hours")),
    ("work", "activities"): ("work_activities", ("title", "status", "category", "activity_date", "end_date", "block_id", "task_id", "season_id", "labor_hours", "worker_count")),
    ("work", "open"): ("v_open_work", ("title", "status", "priority", "due_date", "days_until_due", "category", "block_code", "block_name")),
    ("work", "issues"): ("issues_decisions", ("issue_text", "issue_type", "subject_ref", "status", "priority", "opened_date", "due_date", "closed_date", "decision_action")),
    ("review", "queue"): ("ro_lab_decision_queue", ("sample_id", "sample_name", "sample_type", "lab_date", "result_count", "flagged_results", "needs_review", "review_status", "next_check_at")),
    ("review", "history"): ("lab_reviews", ("sample_id", "decision_type", "review_status", "decision_action", "interpretation", "enologist_approval_required", "approved_at", "next_check_at", "created_at", "updated_at")),
}
# Proposal vocabulary only: deliberately absent from live session policy.
DATASET_CAPABILITIES = {key: f"{key[0]}.{key[1]}.read" for key in DATASETS}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:|\-]{0,190}")
_REVISION = re.compile(r"(?:0|[1-9][0-9]{0,19})")
_TERMINAL = {"done", "completed", "closed", "resolved", "cancelled", "rejected", "superseded"}
MAX_INPUT_ROWS = 2000


class ProjectionForbidden(PermissionError):
    pass


class SnapshotChanged(RuntimeError):
    code = "mobile_read_snapshot_changed"


class SourceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotEvidence:
    before: str | None = None
    after: str | None = None
    permitted_objects: frozenset[str] = frozenset()
    source_generated_at: Any = None
    last_success_at: Any = None
    degraded: bool = False


def _utc(value: Any) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _matches(view: str, state: str, data: Mapping[str, Any]) -> bool:
    if state == "all":
        return True
    if view == "work":
        terminal = str(data.get("status") or "").strip().lower() in _TERMINAL
        return terminal if state == "completed" else not terminal
    flag = data.get("needs_review", False)
    # Unknown/malformed flags must not turn a closed review into completed.
    clear = flag is False or flag == 0 or (isinstance(flag, str) and flag.strip().lower() in {"0", "false", "no", "off", ""})
    complete = str(data.get("review_status") or "").strip().lower() == "closed" and clear
    return not complete if state == "pending" else complete


def _safe_data(data: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    safe = {}
    for field in fields:
        value = data.get(field)
        if isinstance(value, str):
            if value.strip():
                safe[field] = value.strip()[:500 if field in {"issue_text", "decision_action", "interpretation"} else 160]
        elif isinstance(value, (bool, int)) or isinstance(value, float) and math.isfinite(value):
            safe[field] = value
    return safe


def project_page(
    records: Sequence[Mapping[str, Any]], *, estate_id: str, principal_scope: str,
    role: str, capabilities: frozenset[str], view: str, dataset: str,
    now: datetime, evidence: SnapshotEvidence = SnapshotEvidence(),
    state: str | None = None, limit: int = 50, cursor: str | None = None,
) -> dict[str, Any]:
    """Project an already permitted snapshot. Admin-only proposal, not a grant.

    The older ERP operator role is deliberately not mapped to an HA role here.
    No endpoint imports this module; current sessions and v1 DTOs stay intact.
    """
    if role != "admin" or not isinstance(view, str) or view not in {"work", "review"} or view not in capabilities:
        raise ProjectionForbidden("work/review projection is not permitted")
    if not isinstance(dataset, str) or (view, dataset) not in DATASETS:
        raise ValueError("invalid dataset")
    if DATASET_CAPABILITIES[view, dataset] not in capabilities:
        raise ProjectionForbidden("explicit dataset capability required")
    if not isinstance(estate_id, str) or str(UUID(estate_id)) != estate_id or not isinstance(principal_scope, str) or not 1 <= len(principal_scope) <= 200:
        raise ValueError("invalid server scope")
    state = state if state is not None else "open" if view == "work" else "pending"
    if not isinstance(state, str) or state not in ({"all", "open", "completed"} if view == "work" else {"all", "pending", "completed"}):
        raise ValueError("invalid state")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("invalid limit")
    clock = _utc(now)
    if clock is None:
        raise ValueError("aware clock required")
    if evidence.before != evidence.after:
        raise SnapshotChanged(SnapshotChanged.code)
    if evidence.before is not None and (not isinstance(evidence.before, str) or not 1 <= len(evidence.before) <= 200):
        raise ValueError("invalid snapshot generation")
    generation = hashlib.sha256(json.dumps([CONTRACT, estate_id, principal_scope, evidence.before], separators=(",", ":")).encode()).hexdigest() if evidence.before else None
    anchor = ""
    if cursor is not None:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 512 or re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
            raise ValueError("invalid cursor")
        try:
            value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        except (ValueError, UnicodeError) as error:
            raise ValueError("invalid cursor") from error
        if not isinstance(value, dict) or set(value) != {"c", "g", "v", "d", "s", "a"} or type(value["c"]) is not int or value["c"] != 1 or not isinstance(value["g"], str) or re.fullmatch(r"[0-9a-f]{64}", value["g"]) is None or not isinstance(value["a"], str) or _ID.fullmatch(value["a"]) is None:
            raise ValueError("invalid cursor")
        if (value["v"], value["d"], value["s"]) != (view, dataset, state):
            raise ValueError("cursor request mismatch")
        if generation is None or value["g"] != generation:
            raise SnapshotChanged(SnapshotChanged.code)
        anchor = value["a"]
    source_time, success = _utc(evidence.source_generated_at), _utc(evidence.last_success_at)
    age = int((clock - source_time).total_seconds()) if source_time and source_time <= clock else None
    source = {"source_generated_at": _iso(source_time) if age is not None else None,
              "last_success_at": _iso(success) if success and success <= clock else None,
              "data_age_seconds": age, "state": "unavailable"}
    object_name, fields = DATASETS[view, dataset]
    available = bool(generation) and object_name in evidence.permitted_objects
    result = {"ok": True, "contract": CONTRACT, "view": view, "dataset": dataset, "estate_id": estate_id,
              "source": source, "available": available, "filters": {"state": state}, "items": [], "next_cursor": None}
    if not available:
        return result
    source["state"] = "degraded" if evidence.degraded or age is None or age > 7200 or success is None or success > clock or source_time and success < source_time else "ready"
    if len(records) > MAX_INPUT_ROWS:
        raise SourceUnavailable("snapshot exceeds bounded projection")
    items, seen = [], set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        data = record.get("data")
        if record.get("object") != object_name or not isinstance(data, Mapping) or data.get("estate_id") != estate_id:
            continue
        identifier, revision = record.get("id"), record.get("revision")
        if not isinstance(identifier, str) or _ID.fullmatch(identifier) is None or isinstance(revision, bool) or not isinstance(revision, (int, str)) or _REVISION.fullmatch(str(revision)) is None or identifier in seen:
            raise SourceUnavailable("invalid or duplicate snapshot identity")
        seen.add(identifier)
        if identifier <= anchor or not _matches(view, state, data):
            continue
        safe = _safe_data(data, fields)
        updated = _utc(record.get("source_updated_at"))
        items.append({"id": identifier, "revision": str(revision), "source_updated_at": _iso(updated), "data": safe})
    items.sort(key=lambda item: item["id"])
    result["items"] = items[:limit]
    if len(items) > limit:
        raw = json.dumps({"c": 1, "g": generation, "v": view, "d": dataset, "s": state, "a": items[limit - 1]["id"]}, separators=(",", ":")).encode()
        result["next_cursor"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return result
