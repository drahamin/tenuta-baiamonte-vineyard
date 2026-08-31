"""Guarded authority policy for estate camera AI.

Local/on-device camera evidence is collected beside the established vision
service before it can become authoritative.  Promotion is deliberately
evidence-gated and reversible; the established service remains the fallback.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..service import estate_id, json_ready


SETTING_KEY = "camera_ai_policy"
SHADOW_DAYS = 30
CHECK_INTERVAL_DAYS = 7
MIN_WEEKLY_CHECKS = 4
MIN_COMPARISONS = 25
MIN_AGREEMENT_PCT = 90.0
MAX_LOCAL_FAILURE_PCT = 5.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def _stored_policy() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value,updated_at FROM app_settings WHERE estate_id=%s AND setting_key=%s",
        (estate_id(), SETTING_KEY),
    ) or {}
    value = row.get("setting_value")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = {}
    return value if isinstance(value, dict) else {}


def _save_policy(value: dict[str, Any], actor: str) -> None:
    stored = {**value, "updated_by": actor, "updated_at": _utcnow().isoformat()}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), SETTING_KEY, json.dumps(stored)),
        )
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload) "
            "VALUES (%s,'camera-local-ai','internal','policy_updated','processed',%s)",
            (estate_id(), json.dumps({"actor": actor, "policy": stored})),
        )


def record_camera_ai_comparison(
    feature_code: str,
    local_decision: str | None,
    reference_decision: str | None,
    *,
    local_provider: str = "eufy_edge",
    local_failed: bool = False,
    reference_failed: bool = False,
    evidence_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Store one paired forward comparison without retaining camera media."""
    local = str(local_decision or "").strip().casefold() or None
    reference = str(reference_decision or "").strip().casefold() or None
    if not local and not reference and not local_failed and not reference_failed:
        return False
    agreed = bool(local and reference and local == reference and not local_failed and not reference_failed)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO camera_ai_comparisons "
            "(estate_id,feature_code,local_provider,local_decision,reference_decision,agreed,local_failed,reference_failed,evidence_key,metadata) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (estate_id(), str(feature_code)[:80], str(local_provider)[:80], local, reference,
             agreed, bool(local_failed), bool(reference_failed), str(evidence_key or "")[:190] or None,
             json.dumps(metadata or {})),
        )
    return True


def _comparison_metrics(since: datetime | None = None) -> dict[str, Any]:
    clause = " AND observed_at>=%s" if since else ""
    params: tuple[Any, ...] = (estate_id(), since) if since else (estate_id(),)
    row = fetch_one(
        "SELECT COUNT(*) comparisons,SUM(agreed) agreed,SUM(local_failed) local_failures,"
        "SUM(reference_failed) reference_failures,MAX(observed_at) latest_at "
        "FROM camera_ai_comparisons WHERE estate_id=%s" + clause,
        params,
    ) or {}
    comparisons = int(row.get("comparisons") or 0)
    paired = max(0, comparisons - int(row.get("local_failures") or 0) - int(row.get("reference_failures") or 0))
    return {
        "comparisons": comparisons,
        "paired": paired,
        "agreed": int(row.get("agreed") or 0),
        "agreement_pct": round(100 * int(row.get("agreed") or 0) / paired, 1) if paired else None,
        "local_failures": int(row.get("local_failures") or 0),
        "local_failure_pct": round(100 * int(row.get("local_failures") or 0) / comparisons, 1) if comparisons else None,
        "reference_failures": int(row.get("reference_failures") or 0),
        "latest_at": row.get("latest_at"),
    }


def camera_ai_policy_status(now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    stored = _stored_policy()
    shadow_enabled = bool(stored.get("shadow_enabled", True))
    enabled_at = _parse_datetime(stored.get("enabled_at")) or now
    not_before = _parse_datetime(stored.get("primary_not_before")) or enabled_at + timedelta(days=SHADOW_DAYS)
    checks = fetch_all(
        "SELECT id,checked_at,comparisons,agreement_pct,local_failure_pct,eligible,notes "
        "FROM camera_ai_weekly_checks WHERE estate_id=%s ORDER BY checked_at DESC LIMIT 12",
        (estate_id(),),
    )
    metrics = _comparison_metrics(enabled_at)
    last_check = checks[0] if checks else None
    # Manual rechecks in the same seven-day window refresh its scorecard; they
    # can never be used to manufacture four "weekly" checks in one sitting.
    weekly_checks = len({
        max(0, (_parse_datetime(row.get("checked_at")) - enabled_at).days // CHECK_INTERVAL_DAYS)
        for row in checks if _parse_datetime(row.get("checked_at"))
    })
    gates = {
        "shadow_period_complete": now >= not_before,
        "weekly_checks_complete": weekly_checks >= MIN_WEEKLY_CHECKS,
        "comparison_count_complete": metrics["comparisons"] >= MIN_COMPARISONS,
        "agreement_complete": metrics["agreement_pct"] is not None and metrics["agreement_pct"] >= MIN_AGREEMENT_PCT,
        "failure_rate_complete": metrics["local_failure_pct"] is not None and metrics["local_failure_pct"] <= MAX_LOCAL_FAILURE_PCT,
    }
    eligible = shadow_enabled and all(gates.values())
    requested = bool(stored.get("primary_requested", False))
    primary = requested and eligible
    last_checked_at = _parse_datetime((last_check or {}).get("checked_at"))
    next_check_at = (last_checked_at + timedelta(days=CHECK_INTERVAL_DAYS)) if last_checked_at else now
    mode = "primary" if primary else ("eligible" if eligible else "shadow" if shadow_enabled else "disabled")
    return json_ready({
        "mode": mode,
        "shadow_enabled": shadow_enabled,
        "weekly_check_enabled": bool(stored.get("weekly_check_enabled", True)),
        "primary_requested": requested,
        "primary_active": primary,
        "fallback": "Established camera vision service",
        "enabled_at": enabled_at,
        "primary_not_before": not_before,
        "last_check_at": last_checked_at,
        "next_check_at": next_check_at,
        "check_due": now >= next_check_at,
        "weekly_checks": weekly_checks,
        "metrics": metrics,
        "gates": gates,
        "requirements": {
            "shadow_days": SHADOW_DAYS, "weekly_checks": MIN_WEEKLY_CHECKS,
            "comparisons": MIN_COMPARISONS, "agreement_pct": MIN_AGREEMENT_PCT,
            "max_local_failure_pct": MAX_LOCAL_FAILURE_PCT,
        },
        "history": checks,
        "note": "Local camera AI controls triage only after validation; detailed matching and every unsupported task retain the established fallback.",
    })


def update_camera_ai_policy(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    stored = _stored_policy()
    now = _utcnow()
    if "shadow_enabled" in payload:
        enabled = bool(payload["shadow_enabled"])
        if enabled and not bool(stored.get("shadow_enabled")):
            stored["enabled_at"] = now.isoformat()
            stored["primary_not_before"] = (now + timedelta(days=SHADOW_DAYS)).isoformat()
        stored["shadow_enabled"] = enabled
        if not enabled:
            stored["primary_requested"] = False
    if "weekly_check_enabled" in payload:
        stored["weekly_check_enabled"] = bool(payload["weekly_check_enabled"])
    if "primary_requested" in payload:
        stored["primary_requested"] = bool(payload["primary_requested"])
    stored.setdefault("shadow_enabled", True)
    stored.setdefault("weekly_check_enabled", True)
    stored.setdefault("enabled_at", now.isoformat())
    stored.setdefault("primary_not_before", (now + timedelta(days=SHADOW_DAYS)).isoformat())
    _save_policy(stored, actor)
    return camera_ai_policy_status(now)


def run_camera_ai_weekly_check(force: bool = False) -> dict[str, Any]:
    status = camera_ai_policy_status()
    if not status["shadow_enabled"] or not status["weekly_check_enabled"]:
        return {"checked": False, "reason": "Weekly local camera AI checks are disabled", "policy": status}
    if not force and not status["check_due"]:
        return {"checked": False, "deferred": True, "next_check_at": status["next_check_at"], "policy": status}
    metrics = _comparison_metrics(_utcnow() - timedelta(days=SHADOW_DAYS))
    provisional_gates = status["gates"]
    eligible = bool(status["shadow_enabled"] and all(provisional_gates.values()))
    notes = "Promotion gates satisfied" if eligible else "Shadow comparison continues; primary authority remains guarded"
    last_check = _parse_datetime(status.get("last_check_at"))
    with transaction() as (_, cursor):
        if last_check and _utcnow() - last_check < timedelta(days=CHECK_INTERVAL_DAYS):
            cursor.execute(
                "UPDATE camera_ai_weekly_checks SET checked_at=UTC_TIMESTAMP(6),comparisons=%s,agreement_pct=%s,"
                "local_failure_pct=%s,eligible=%s,notes=%s WHERE estate_id=%s ORDER BY checked_at DESC LIMIT 1",
                (metrics["comparisons"], metrics["agreement_pct"], metrics["local_failure_pct"], eligible, notes, estate_id()),
            )
        else:
            cursor.execute(
                "INSERT INTO camera_ai_weekly_checks "
                "(estate_id,comparisons,agreement_pct,local_failure_pct,eligible,notes) VALUES (%s,%s,%s,%s,%s,%s)",
                (estate_id(), metrics["comparisons"], metrics["agreement_pct"], metrics["local_failure_pct"], eligible, notes),
            )
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload) "
            "VALUES (%s,'camera-local-ai','internal','weekly_validation','processed',%s)",
            (estate_id(), json.dumps({"metrics": json_ready(metrics), "eligible": eligible, "notes": notes})),
        )
    return {"checked": True, "metrics": json_ready(metrics), "policy": camera_ai_policy_status()}
