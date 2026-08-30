"""Read-only, presentation-safe network operations console."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ..access import authorize_admin
from ..config import get_settings
from ..db import fetch_all
from ..display_data import _home_assistant_display_data, system_status_payload
from ..service import estate_id, json_ready


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
LAYER_NAMES = {
    "wan": "Internet & WAN", "routing": "Routers & gateways",
    "switching": "Switches & Ethernet", "wireless": "Wi-Fi & access points",
    "tunnels": "Tunnels & remote access", "radio": "Radio & LTE",
    "clients": "Connected devices",
}


def _metric_kind(row: dict[str, Any]) -> str | None:
    text = f"{row.get('name', '')} {row.get('entity_id', '')} {row.get('unit', '')}".casefold()
    if any(term in text for term in ("latency", "ping", " ms")):
        return "latency"
    if any(term in text for term in ("packet loss", "packet_loss")):
        return "packet_loss"
    if any(term in text for term in ("rssi", "signal", "dbm")):
        return "signal"
    if any(term in text for term in ("throughput", "bandwidth", "download", "upload", "bit/s", "bps")):
        return "throughput"
    if any(term in text for term in ("cpu", "memory", "utilization", "load")):
        return "utilization"
    if any(term in text for term in ("client", "connection")):
        return "clients"
    if "uptime" in text:
        return "uptime"
    return None


def build_network_operations_payload(
    home_assistant: dict[str, Any],
    status: dict[str, Any],
    checkpoints: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    equipment = list(home_assistant.get("network_entities") or [])
    cameras = list(home_assistant.get("camera_health") or [])
    services = list(status.get("services") or [])
    categories = []
    for code, name in LAYER_NAMES.items():
        rows = [row for row in equipment if row.get("category") == code]
        categories.append({
            "code": code, "name": name, "total": len(rows),
            "healthy": sum(row.get("health") == "good" for row in rows),
            "attention": sum(row.get("health") == "attention" for row in rows),
            "offline": sum(row.get("health") == "offline" for row in rows),
            "instrumented": bool(rows),
        })
    endpoint_codes = {"database", "weather", "publisher", "lte", "processing"}
    endpoints = [dict(row) for row in services if row.get("code") in endpoint_codes]
    endpoints.insert(0, {
        "code": "vineyard_api", "name": "Vineyard API", "state": "green",
        "detail": "This authenticated endpoint is responding",
    })
    checkpoint_names = {str(row.get("integration_name") or ""): row for row in checkpoints}
    for endpoint in endpoints:
        if endpoint["code"] == "publisher":
            endpoint["name"] = "Public website & feed"
            checkpoint = checkpoint_names.get("public_harvest_publisher") or {}
            endpoint["last_success_at"] = checkpoint.get("last_success_at")
            endpoint["last_attempt_at"] = checkpoint.get("last_attempt_at")
    metrics = []
    for row in equipment:
        kind = _metric_kind(row)
        if kind and row.get("numeric_value") is not None:
            metrics.append({**row, "kind": kind})
    critical = [row for row in equipment if row.get("category") in {"wan", "routing", "tunnels", "radio"}]
    offline_critical = [row for row in critical if row.get("health") == "offline"]
    camera_online = sum(bool(row.get("available")) for row in cameras)
    endpoint_healthy = sum(row.get("state") == "green" for row in endpoints)
    incident_rows = [{
        "name": str(row.get("integration_name") or "Integration").replace("-", " ").title(),
        "detail": row.get("error_message") or "Latest operation failed",
        "occurred_at": row.get("occurred_at"), "source": "processing",
    } for row in failures]
    incident_rows.extend({
        "name": row.get("name"), "detail": f"{row.get('state')} · {row.get('entity_id')}",
        "occurred_at": row.get("last_updated"), "source": "Home Assistant",
    } for row in offline_critical)
    overall = "red" if offline_critical or any(row.get("state") == "red" for row in endpoints) else "amber" if any(not row["instrumented"] for row in categories[:6]) else "green"
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": overall,
        "kpis": {
            "equipment_total": len(equipment),
            "equipment_healthy": sum(row.get("health") == "good" for row in equipment),
            "critical_offline": len(offline_critical),
            "cameras_online": camera_online, "cameras_total": len(cameras),
            "endpoints_healthy": endpoint_healthy, "endpoints_total": len(endpoints),
        },
        "categories": categories, "equipment": equipment, "metrics": metrics,
        "cameras": cameras, "endpoints": endpoints, "incidents": incident_rows[:20],
        "status_lights": list(home_assistant.get("network_equipment") or []) + [home_assistant.get("lte_status") or {}],
        "source": {
            "home_assistant_available": bool(home_assistant.get("available")),
            "snapshot_cache_seconds": 30,
            "checkpoint_count": len(checkpoints),
            "note": "Home Assistant state inventory plus vineyard processing checkpoints. Missing meters are shown as not instrumented, never estimated.",
        },
    }


@router.get("/network", dependencies=[Depends(authorize_admin)])
def network_operations() -> dict[str, Any]:
    home_assistant = _home_assistant_display_data()
    status = system_status_payload(home_assistant)
    checkpoints = fetch_all(
        "SELECT integration_name,last_success_at,last_attempt_at,last_error FROM sync_checkpoints WHERE estate_id=%s ORDER BY integration_name",
        (estate_id(),),
    )
    failures = fetch_all(
        "SELECT integration_name,error_message,occurred_at FROM integration_events WHERE estate_id=%s AND status='failed' AND occurred_at>=NOW()-INTERVAL 24 HOUR ORDER BY occurred_at DESC LIMIT 20",
        (estate_id(),),
    )
    return json_ready(build_network_operations_payload(home_assistant, status, checkpoints, failures))
