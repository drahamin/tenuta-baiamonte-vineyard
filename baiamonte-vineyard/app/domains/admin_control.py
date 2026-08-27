"""Administrative process, runtime, connection, and recovery status.

This module is the first extraction from the legacy application composition
root.  It deliberately preserves the existing Admin Control response contract;
people, labor, and payment assembly remain in ``main`` until their own bounded
services are extracted.
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timedelta
from typing import Any

from ..config import Settings, addon_version, get_settings
from ..db import fetch_all, fetch_one
from ..process_control import PROCESS_ORDER, process_controls
from ..process_runtime import processing_runtime_snapshot
from ..service import estate_id, json_ready


PROCESS_INTEGRATIONS = {
    "full_refresh": "full-system-refresh",
    "planning": "google-planning",
    "weather": "home-assistant-weather",
    "forecast_sources": "external-prediction-sources",
    "product_catalog": "italian-ministry-product-catalog",
    "harvest": "harvest-projection",
    "cistern": "cistern-camera-level",
    "gmail": "gmail-intake",
    "finance": "fattureincloud",
    "whatsapp": "whatsapp-system",
    "cameras": "camera-awareness",
    "etna": "etna-monitor",
    "public_feed": "public-harvest-publisher",
    "traffic": "home-assistant-traffic",
    "disease": "disease-pressure",
    "alerts": "operational-alerts",
}

# Historical releases logged the camera job under this narrower name. Keep it
# retryable without allowing it to override the current process health event.
LEGACY_PROCESS_INTEGRATIONS = {"camera-snapshot-cache": "cameras"}


def process_statuses(
    controls: dict[str, Any],
    latest: dict[str, dict[str, Any]],
    processing_runtime: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """Combine scheduled controls, last events, and active runs deterministically."""
    active_by_code = {str(item.get("code")): item for item in processing_runtime.get("jobs") or []}
    processes: list[dict[str, Any]] = []
    for code in PROCESS_ORDER:
        item = controls["processes"][code]
        event = latest.get(PROCESS_INTEGRATIONS.get(code, code)) or {}
        occurred = event.get("occurred_at")
        next_run = occurred + timedelta(minutes=item["interval_minutes"]) if occurred and item["enabled"] and not controls["paused"] else None
        age_minutes = max(0, int((now - occurred).total_seconds() / 60)) if occurred else None
        active = active_by_code.get(code)
        if active and active.get("state") == "timed_out":
            health = "timed_out"
        elif active:
            health = "running"
        elif controls["paused"] or not item["enabled"]:
            health = "paused"
        elif event.get("status") == "failed":
            health = "error"
        elif age_minutes is None:
            health = "waiting"
        elif age_minutes > item["interval_minutes"] * 2 + 2:
            health = "stale"
        else:
            health = "healthy"
        processes.append({
            **item,
            "code": code,
            "health": health,
            "last_status": event.get("status"),
            "last_run": occurred,
            "next_run": next_run,
            "last_error": active.get("error") if active and active.get("error") else event.get("error_message"),
            "active_run": active,
        })
    return processes


def _website_connection(settings: Settings, processes: list[dict[str, Any]]) -> dict[str, str]:
    website_process = next((item for item in processes if item["code"] == "public_feed"), {})
    state = "off" if not settings.public_publish_url else {
        "healthy": "green",
        "error": "red",
        "stale": "red",
        "waiting": "amber",
        "paused": "off",
    }.get(str(website_process.get("health")), "amber")
    detail = (
        "Not configured" if not settings.public_publish_url else
        str(website_process.get("last_error") or "Publish is overdue") if state == "red" else
        f"Last publish {website_process.get('last_run')}" if state == "green" else
        "Publishing paused" if state == "off" else
        "Waiting for a successful publish"
    )
    return {"state": state, "detail": detail}


def _storage_summary() -> dict[str, Any]:
    try:
        storage = shutil.disk_usage("/data")
        return {
            "total_bytes": storage.total,
            "used_bytes": storage.used,
            "free_bytes": storage.free,
            "used_percent": round(storage.used / storage.total * 100, 1) if storage.total else None,
        }
    except OSError:
        return {"total_bytes": None, "used_bytes": None, "free_bytes": None, "used_percent": None}


def admin_control_foundation(app_started_monotonic: float) -> dict[str, Any]:
    """Build the non-people foundation of the existing Admin Control payload."""
    controls = process_controls()
    settings = get_settings()
    collation = "utf8mb4_unicode_ci"
    latest = {row["integration_name"]: row for row in fetch_all(
        "SELECT e.integration_name,e.status,e.occurred_at,e.error_message,e.payload FROM integration_events e "
        "JOIN (SELECT candidate.integration_name,MAX(candidate.id) id FROM integration_events candidate WHERE candidate.estate_id=%s "
        f"AND NOT (candidate.status='failed' AND EXISTS (SELECT 1 FROM error_acknowledgements a "
        f"WHERE a.estate_id COLLATE {collation}=candidate.estate_id COLLATE {collation} AND a.error_kind='integration' "
        f"AND a.record_id COLLATE {collation}=CAST(candidate.id AS CHAR) COLLATE {collation})) "
        "GROUP BY candidate.integration_name) x ON x.id=e.id",
        (estate_id(),),
    )}
    now = datetime.now()
    processing_runtime = processing_runtime_snapshot()
    processes = process_statuses(controls, latest, processing_runtime, now)
    review = fetch_one(
        "SELECT COUNT(*) total,SUM(review_status='ready_for_review') ready,SUM(review_status='failed') failed "
        "FROM intake_items WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed')",
        (estate_id(),),
    ) or {}
    review_age = fetch_one(
        "SELECT MIN(received_at) oldest_pending_at FROM intake_items WHERE estate_id=%s "
        "AND review_status IN ('new','processing','ready_for_review','failed')",
        (estate_id(),),
    ) or {}
    recovery_errors = fetch_all(
        "SELECT current_event.id,current_event.integration_name,current_event.event_type,current_event.error_message,current_event.occurred_at "
        "FROM integration_events current_event WHERE current_event.estate_id=%s AND current_event.status='failed' "
        "AND current_event.integration_name<>'whatsapp-channel' "
        "AND NOT EXISTS (SELECT 1 FROM integration_events newer_event WHERE newer_event.estate_id=current_event.estate_id "
        "AND newer_event.integration_name=current_event.integration_name AND newer_event.event_type=current_event.event_type "
        "AND (newer_event.occurred_at>current_event.occurred_at OR (newer_event.occurred_at=current_event.occurred_at AND newer_event.id>current_event.id))) "
        f"AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a WHERE a.estate_id COLLATE {collation}=current_event.estate_id COLLATE {collation} "
        f"AND a.error_kind='integration' AND a.record_id COLLATE {collation}=CAST(current_event.id AS CHAR) COLLATE {collation}) "
        "ORDER BY current_event.occurred_at DESC LIMIT 30",
        (estate_id(),),
    )
    failed_intake = fetch_all(
        "SELECT i.id,i.source,i.title,i.original_filename,i.processing_error,i.received_at occurred_at FROM intake_items i "
        f"WHERE i.estate_id=%s AND i.review_status='failed' AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a "
        f"WHERE a.estate_id COLLATE {collation}=i.estate_id COLLATE {collation} AND a.error_kind='intake' "
        f"AND a.record_id COLLATE {collation}=CAST(i.id AS CHAR) COLLATE {collation}) "
        "ORDER BY i.received_at DESC LIMIT 20",
        (estate_id(),),
    )
    attachment_count = fetch_one("SELECT COUNT(*) total FROM entity_attachments WHERE estate_id=%s", (estate_id(),)) or {}
    mcp_hosts = {item.strip() for item in settings.mcp_allowed_hosts.split(",") if item.strip()}
    setup_warnings = []
    if not settings.mcp_server_token:
        setup_warnings.append("Create an MCP server token to connect Codex on the Mac.")
    if not any(item.startswith("192.168.0.10:") for item in mcp_hosts):
        setup_warnings.append("Allow 192.168.0.10:* in MCP allowed hosts.")
    if not settings.openai_api_key:
        setup_warnings.append("Add an OpenAI API key to enable document, photo and question analysis.")

    connections = {
        "mac_api": {"state": "green" if settings.mcp_server_token or settings.api_key else "amber", "detail": "Authenticated" if settings.mcp_server_token or settings.api_key else "Needs setup"},
        "gmail": {"state": "green" if settings.gmail_address and settings.gmail_app_password else "amber", "detail": "Configured" if settings.gmail_address and settings.gmail_app_password else "Needs setup"},
        "whatsapp": {"state": "green" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "amber", "detail": "Configured" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "Needs setup"},
        "website": _website_connection(settings, processes),
    }
    runtime = {
        "version": addon_version(),
        "uptime_seconds": int(time.monotonic() - app_started_monotonic),
        "database": "connected",
        "storage": _storage_summary(),
        "attachment_count": int(attachment_count.get("total") or 0),
        "processing_errors_24h": len(recovery_errors) + len(failed_intake),
        "oldest_review_at": review_age.get("oldest_pending_at"),
        "processing": processing_runtime,
    }
    mac_setup = {
        "endpoint": "http://192.168.0.10:8100/mcp",
        "token_configured": bool(settings.mcp_server_token),
        "writes_enabled": bool(settings.mcp_allow_writes),
        "allowed_host_ready": any(item.startswith("192.168.0.10:") for item in mcp_hosts),
        "setup_warnings": setup_warnings,
    }
    return {
        "controls": controls,
        "checked_at": now,
        "processes": processes,
        "review_queue": review,
        "connections": connections,
        "runtime": runtime,
        "mac_setup": mac_setup,
        "recovery_errors": recovery_errors,
        "failed_intake": failed_intake,
    }


def admin_runtime_payload(app_started_monotonic: float) -> dict[str, Any]:
    """Return the independently loadable runtime portion of Admin Control."""
    foundation = admin_control_foundation(app_started_monotonic)
    controls = foundation["controls"]
    return json_ready({
        "paused": controls["paused"],
        "updated_at": controls.get("updated_at"),
        "updated_by": controls.get("updated_by"),
        "checked_at": foundation["checked_at"],
        "processes": foundation["processes"],
        "review_queue": foundation["review_queue"],
        "connections": foundation["connections"],
        "runtime": foundation["runtime"],
        "mac_setup": foundation["mac_setup"],
        "recovery_errors": [
            {**row, "kind": "integration", "recoverable": row["integration_name"] in (set(PROCESS_INTEGRATIONS.values()) | set(LEGACY_PROCESS_INTEGRATIONS))}
            for row in foundation["recovery_errors"]
        ] + [{**row, "kind": "intake", "recoverable": True} for row in foundation["failed_intake"]],
    })
