"""Estate water and off-grid energy operating workspaces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from ..access import authorize
from ..db import fetch_all, fetch_one, transaction
from ..display_data import system_status_payload
from ..service import estate_id, json_ready
from .cistern_learning import cistern_learning_status


router = APIRouter(prefix="/api/v1/operations", tags=["estate utilities"], dependencies=[Depends(authorize)])


def _number(row: dict[str, Any] | None) -> float | None:
    try:
        value = float((row or {}).get("state") if (row or {}).get("state") is not None else (row or {}).get("value"))
        unit = str((row or {}).get("unit") or "")
        return value * 1000 if unit == "kW" else value
    except (TypeError, ValueError):
        return None


def _find(rows: list[dict[str, Any]], terms: tuple[str, ...], units: tuple[str, ...] = ()) -> dict[str, Any] | None:
    ranked = []
    for row in rows:
        text = f"{row.get('entity_id')} {row.get('name')}".casefold().replace("_", " ")
        score = max((len(term) for term in terms if term in text), default=0)
        if score and (not units or str(row.get("unit") or "") in units) and row.get("available"):
            ranked.append((score, row))
    return max(ranked, key=lambda pair: pair[0])[1] if ranked else None


def _energy_settings() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='energy_management'", (estate_id(),)) or {}
    try:
        raw = row.get("setting_value") or {}
        loaded = raw if isinstance(raw, dict) else json.loads(raw)
    except (TypeError, ValueError):
        loaded = {}
    return {"mode": "shadow", "battery_capacity_kwh": 10.24, "reserve_floor_pct": 30,
            "critical_floor_pct": 20, "recovery_target_pct": 45,
            "automatic_control_enabled": False, "approved_controllable_loads": [], **loaded}


def _energy_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    rows = status.get("solar_entities") or []
    solar = status.get("solar") or {}
    current_power = solar.get("current_power") or {}
    pv = _number(current_power) if "growatt" in str(current_power.get("source") or "").casefold() else None
    load = _number(_find(rows, ("load power", "output power", "consumption power", "estate load"), ("W", "kW")))
    soc_row = _find(rows, ("battery state of charge", "battery soc", "battery level"), ("%",))
    battery_power = _number(_find(rows, ("battery power", "battery charge power", "battery discharge power"), ("W", "kW")))
    grid = _number(_find(rows, ("grid power", "grid import", "utility power"), ("W", "kW")))
    generator = _number(_find(rows, ("generator power", "generator load"), ("W", "kW")))
    remaining = _number(solar.get("forecast_energy_remaining"))
    return {"pv_power_w": pv, "estate_load_w": load, "battery_soc_pct": _number(soc_row),
            "battery_power_w": battery_power, "grid_power_w": grid, "generator_power_w": generator,
            "forecast_remaining_kwh": remaining, "soc_entity": soc_row}


def _record_energy(snapshot: dict[str, Any]) -> None:
    if not any(snapshot.get(key) is not None for key in ("pv_power_w", "estate_load_w", "battery_soc_pct", "battery_power_w")):
        return
    observed = datetime.now(timezone.utc).replace(second=0, microsecond=0).replace(tzinfo=None)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT IGNORE INTO estate_energy_observations (estate_id,observed_at,pv_power_w,estate_load_w,battery_soc_pct,battery_power_w,grid_power_w,generator_power_w,forecast_remaining_kwh,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (estate_id(), observed, snapshot.get("pv_power_w"), snapshot.get("estate_load_w"), snapshot.get("battery_soc_pct"), snapshot.get("battery_power_w"), snapshot.get("grid_power_w"), snapshot.get("generator_power_w"), snapshot.get("forecast_remaining_kwh"), json.dumps({"source": "Home Assistant", "mode": "shadow"})),
        )


def _energy_learning(snapshot: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    rows = fetch_all("SELECT observed_at,estate_load_w,battery_soc_pct FROM estate_energy_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 2016", (estate_id(),))
    def hour(row: dict[str, Any]) -> int:
        value = row.get("observed_at")
        try:
            observed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
            observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed
            return observed.astimezone(ZoneInfo("Europe/Rome")).hour
        except (TypeError, ValueError):
            return 12
    night_loads = [float(row["estate_load_w"]) for row in rows if row.get("estate_load_w") is not None and (hour(row) >= 20 or hour(row) < 7)]
    learned_w = round(median(night_loads), 1) if len(night_loads) >= 12 else None
    soc = snapshot.get("battery_soc_pct")
    capacity = float(settings.get("battery_capacity_kwh") or 10.24)
    reserve = float(settings.get("reserve_floor_pct") or 30)
    usable_kwh = max(0.0, capacity * ((float(soc) - reserve) / 100)) if soc is not None else None
    hours_at_load = usable_kwh / (learned_w / 1000) if usable_kwh is not None and learned_w and learned_w > 0 else None
    status = "commissioning" if soc is None else "learning" if learned_w is None else "guarded"
    risk = "unknown" if soc is None else "critical" if soc <= float(settings.get("critical_floor_pct") or 20) else "reserve" if soc <= reserve else "normal"
    missing = []
    if soc is None: missing.append("Battery state of charge")
    if snapshot.get("estate_load_w") is None: missing.append("Estate load power")
    if snapshot.get("battery_power_w") is None: missing.append("Battery charge / discharge power")
    return {"model": "estate-energy-reserve-v1", "status": status, "risk": risk,
            "observation_count": len(rows), "night_observation_count": len(night_loads),
            "learned_night_load_w": learned_w, "usable_above_reserve_kwh": usable_kwh,
            "estimated_hours_above_reserve": hours_at_load, "missing_evidence": missing,
            "control_eligible": not missing and bool(settings.get("approved_controllable_loads")),
            "control_enabled": bool(settings.get("automatic_control_enabled")) and not missing and bool(settings.get("approved_controllable_loads")),
            "method": "Rolling median night load with a fixed reserve floor; runs in shadow mode until telemetry and controllable loads are approved."}


@router.get("/water")
def water_workspace() -> dict[str, Any]:
    status = system_status_payload()
    history = fetch_all("SELECT id,observed_at,level_percent,confidence,source,model,notes FROM cistern_level_estimates WHERE estate_id=%s ORDER BY observed_at DESC,id DESC LIMIT 96", (estate_id(),))
    entities = status.get("water_entities") or []
    return json_ready({"checked_at": status.get("checked_at"), "level": status.get("cistern_level") or {},
                       "history": list(reversed(history)), "learning": cistern_learning_status(),
                       "entities": entities, "health": {"connected": sum(1 for row in entities if row.get("available")), "unavailable": sum(1 for row in entities if not row.get("available"))},
                       "future_integrations": [
                           {"name": "Cistern inflow / outflow meters", "status": "ready for entity"},
                           {"name": "Pump pressure and electrical load", "status": "ready for entity"},
                           {"name": "Irrigation zones and valves", "status": "ready for entity"},
                           {"name": "Additional storage / well", "status": "ready for entity"}]})


@router.get("/solar")
def solar_workspace() -> dict[str, Any]:
    status = system_status_payload()
    snapshot = _energy_snapshot(status)
    try:
        _record_energy(snapshot)
        settings = _energy_settings()
        learning = _energy_learning(snapshot, settings)
    except Exception:
        settings = _energy_settings()
        learning = {"model": "estate-energy-reserve-v1", "status": "commissioning", "risk": "unknown", "missing_evidence": ["Energy learning database"], "control_enabled": False, "control_eligible": False}
    entities = status.get("solar_entities") or []
    checks = [
        {"name": "Growatt inverter telemetry", "ready": any("growatt" in f"{r.get('entity_id')} {r.get('name')}".casefold() and r.get("available") for r in entities)},
        {"name": "Battery state of charge", "ready": snapshot.get("battery_soc_pct") is not None},
        {"name": "Battery charge / discharge", "ready": snapshot.get("battery_power_w") is not None},
        {"name": "Estate load measurement", "ready": snapshot.get("estate_load_w") is not None},
        {"name": "Approved controllable loads", "ready": bool(settings.get("approved_controllable_loads"))},
    ]
    return json_ready({"checked_at": status.get("checked_at"), "solar": status.get("solar") or {}, "power": status.get("power") or [],
                       "snapshot": snapshot, "settings": settings, "learning": learning, "entities": entities,
                       "commissioning": checks, "commissioning_ready": all(row["ready"] for row in checks),
                       "safety_statement": "Reserve protection is decision support until every required meter and approved load control is verified. No missing sensor is treated as zero, and no load is switched automatically during commissioning."})
