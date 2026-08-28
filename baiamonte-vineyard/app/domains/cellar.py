from __future__ import annotations

from typing import Any

from ..db import fetch_one, transaction
from ..service import audit, estate_id, new_id


def manual_tank_definitions(raw: object, limit: int = 8) -> list[list[str]]:
    """Normalize the legacy configured tank string for one-time migration."""
    values = [part.strip() for part in str(raw or "").split(",") if part.strip()][:limit]
    return [[value.strip() for value in definition.split("|")] for definition in values]


def update_tank_details(tank: dict[str, Any], payload: dict[str, Any], actor: str, sensor_keys: set[str], plaato_keys: set[str] | None = None) -> dict[str, Any]:
    """Update stable vessel identity separately from changing cellar readings."""
    mode = str(payload.get("reading_mode") or "").strip().casefold()
    if mode not in {"manual", "sensor", "auto"}:
        raise ValueError("Choose manual, Home Assistant sensor or PLAATO automatic mode")
    container_type = str(payload.get("container_type") or tank.get("container_type") or "tank").strip().casefold()
    if container_type not in {"tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other"}:
        raise ValueError("Choose a supported vessel type")
    code = str(payload.get("code") or tank.get("code") or "").strip().upper()
    name = str(payload.get("name") or tank.get("name") or code).strip()
    if not code or len(code) > 60:
        raise ValueError("Tank code is required and must be 60 characters or fewer")
    if not name or len(name) > 160:
        raise ValueError("Tank name is required and must be 160 characters or fewer")
    try:
        capacity = float(payload.get("capacity_l"))
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid tank capacity") from error
    if not 0 < capacity <= 100000:
        raise ValueError("Tank capacity must be between 0 and 100,000 L")
    active_lot = fetch_one(
        "SELECT COALESCE(volume_l,initial_l,0) volume_l FROM wine_lots WHERE estate_id=%s AND current_container_id=%s ORDER BY started_at DESC,id DESC LIMIT 1",
        (estate_id(), tank["id"]),
    ) or {}
    volume = float(active_lot.get("volume_l") or 0)
    if capacity + 0.001 < volume:
        raise ValueError(f"Capacity cannot be below the current recorded volume of {volume:g} L")
    material = str(payload.get("material") or "").strip()[:80] or None
    location = str(payload.get("location") or "").strip()[:120] or None
    notes = str(payload.get("tank_notes") or "").strip()[:4000] or None
    configured = bool(tank.get("sensor_entity_id") or code.casefold() in sensor_keys or name.casefold() in sensor_keys)
    if mode == "sensor" and not configured:
        raise ValueError("Configure this tank under cellar_live_sensors in Home Assistant App Configuration before enabling sensor mode")
    plaato_configured = bool("*" in (plaato_keys or set()) or code.casefold() in (plaato_keys or set()) or name.casefold() in (plaato_keys or set()))
    if mode == "auto" and not plaato_configured:
        raise ValueError("Add this tank under plaato_tank_mappings and configure the PLAATO API key before enabling automatic mode")
    if mode == "auto":
        configured = True
    sensor_status = "configured" if configured else "not_configured"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_containers SET code=%s,name=%s,container_type=%s,material=%s,capacity_l=%s,location=%s,notes=%s WHERE id=%s AND estate_id=%s",
            (code, name, container_type, material, capacity, location, notes, tank["id"], estate_id()),
        )
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,updated_by) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE reading_mode=VALUES(reading_mode),sensor_status=VALUES(sensor_status),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), tank["id"], mode, sensor_status, actor),
        )
        audit(cursor, "update_tank_details", "cellar_container", tank["id"], {"code": code, "name": name, "capacity_l": capacity, "container_type": container_type, "reading_mode": mode}, actor)
    return {"saved": True, "container_id": tank["id"], "code": code, "name": name, "capacity_l": capacity, "reading_mode": mode, "container_type": container_type, "sensor_status": sensor_status}
