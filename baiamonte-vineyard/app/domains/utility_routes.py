"""Estate water and off-grid energy operating workspaces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..access import authorize, authorize_admin, request_username
from ..db import fetch_all, fetch_one, transaction
from ..display_data import system_status_payload
from ..intelligence import record_owner_assisted_cistern_reading
from ..service import estate_id, json_ready
from .cistern_learning import cistern_learning_status


router = APIRouter(prefix="/api/v1/operations", tags=["estate utilities"], dependencies=[Depends(authorize)])

BATTERY_ENTITY_PREFIX = "baiamonte_can_"


class CisternReferenceReading(BaseModel):
    level_percent: float = Field(ge=0, le=100)
    confidence: float = Field(default=0.6, ge=0, le=1)
    notes: str = Field(min_length=3, max_length=1000)


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


def _entity(rows: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("entity_id") == entity_id and row.get("available")), None)


def _battery_bank(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def value(suffix: str) -> Any:
        row = _entity(rows, f"sensor.{BATTERY_ENTITY_PREFIX}{suffix}")
        return _number(row) if row and row.get("unit") else (row or {}).get("state")

    packs = []
    for address in (1, 2):
        prefix = f"battery_{address}_"
        online = _entity(rows, f"binary_sensor.{BATTERY_ENTITY_PREFIX}battery_{address}_online")
        packs.append({
            "address": address,
            "online": str((online or {}).get("state") or "off").casefold() == "on",
            "soc_pct": value(prefix + "battery_soc"),
            "voltage_v": value(prefix + "battery_voltage"),
            "current_a": value(prefix + "battery_current"),
            "power_w": value(prefix + "battery_power"),
            "temperature_c": value(prefix + "pack_temperature"),
            "cell_spread_mv": value(prefix + "cell_voltage_difference"),
        })
    all_online = _entity(rows, f"binary_sensor.{BATTERY_ENTITY_PREFIX}bank_all_batteries_online")
    return {
        "connected": str((all_online or {}).get("state") or "off").casefold() == "on",
        "health": value("bank_health"),
        "status": value("bank_status"),
        "soc_pct": value("bank_soc"),
        "voltage_v": value("bank_voltage"),
        "current_a": value("bank_current"),
        "power_w": value("bank_power"),
        "remaining_kwh": value("bank_remaining_energy"),
        "nominal_kwh": value("bank_nominal_energy"),
        "soc_difference_pct": value("bank_soc_difference"),
        "maximum_cell_spread_mv": value("bank_maximum_cell_spread"),
        "energy_charged_kwh": value("bank_energy_charged"),
        "energy_discharged_kwh": value("bank_energy_discharged"),
        "packs": packs,
    }


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
    pv_row = _entity(rows, "sensor.total_dc_input_power")
    pv = _number(pv_row)
    if pv is None and "growatt" in str(current_power.get("source") or "").casefold():
        pv = _number(current_power)
    load_row = _entity(rows, "sensor.wifi_din_rail_40a_main_power")
    measured_load = _number(load_row)
    soc_row = _entity(rows, "sensor.baiamonte_can_bank_soc") or _find(rows, ("battery state of charge", "battery soc", "battery level"), ("%",))
    battery_power = _number(_entity(rows, "sensor.baiamonte_can_bank_power") or _find(rows, ("battery power", "battery charge power", "battery discharge power"), ("W", "kW")))
    grid_row = _find(rows, ("grid power", "grid import", "utility power"), ("W", "kW"))
    generator_row = _entity(rows, "sensor.generator_main_breaker_phase_a_power")
    grid = _number(grid_row)
    generator = _number(generator_row)
    # Felicity signed power is positive while discharging and negative while charging.
    # Therefore source input + battery output equals the downstream load. Mixing DC PV
    # and AC generator measurements makes this a useful operational estimate, not a
    # revenue-grade measurement; prefer the estate main meter whenever it is online.
    contributors = {"solar_w": pv, "generator_w": generator, "grid_w": grid, "battery_w": battery_power}
    sources = [value for key, value in contributors.items() if key != "battery_w" and value is not None]
    calculated_load = max(0.0, sum(sources) + battery_power) if battery_power is not None and sources else None
    load = measured_load if measured_load is not None else calculated_load
    load_method = "measured" if measured_load is not None else "calculated" if calculated_load is not None else "unavailable"
    load_confidence = "high" if measured_load is not None else "medium" if battery_power is not None and pv is not None and generator is not None else "low" if calculated_load is not None else "none"
    remaining = _number(solar.get("forecast_energy_remaining"))
    return {"pv_power_w": pv, "estate_load_w": load, "measured_load_w": measured_load,
            "calculated_load_w": calculated_load, "load_method": load_method, "load_confidence": load_confidence,
            "load_components": contributors, "battery_soc_pct": _number(soc_row),
            "battery_power_w": battery_power, "grid_power_w": grid, "generator_power_w": generator,
            "forecast_remaining_kwh": remaining, "soc_entity": soc_row}


def _energy_flow(snapshot: dict[str, Any], battery: dict[str, Any]) -> list[dict[str, Any]]:
    """Readable, curated energy-flow cards for the owner-facing page."""
    battery_power = snapshot.get("battery_power_w")
    battery_direction = "Waiting for BMS"
    if battery_power is not None:
        battery_direction = "Charging" if battery_power < -5 else "Discharging" if battery_power > 5 else "Idle"
    return [
        {"label": "Solar input", "value_w": snapshot.get("pv_power_w"), "detail": "Live DC meter" if snapshot.get("pv_power_w") is not None else "Growatt meter unavailable", "tone": "solar"},
        {"label": "Generator input", "value_w": snapshot.get("generator_power_w"), "detail": "Live AC input meter" if snapshot.get("generator_power_w") is not None else "Generator meter unavailable", "tone": "generator"},
        {"label": "Battery bank", "value_w": abs(battery_power) if battery_power is not None else None, "detail": battery_direction, "tone": "charging" if battery_direction == "Charging" else "discharging"},
        {"label": "Total estate load", "value_w": snapshot.get("estate_load_w"), "detail": f"{str(snapshot.get('load_method') or 'unavailable').title()} · {str(snapshot.get('load_confidence') or 'no')} confidence", "tone": "load"},
        {"label": "Stored energy", "value_kwh": battery.get("remaining_kwh"), "detail": f"{battery.get('soc_pct')}% state of charge" if battery.get("soc_pct") is not None else "Waiting for BMS", "tone": "storage"},
    ]


def _overnight_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose the native HA forecast without duplicating its solar-clock logic."""
    readiness = _entity(rows, "sensor.baiamonte_overnight_readiness")
    return {
        "status": (readiness or {}).get("state"),
        "coverage_pct": _number(_entity(rows, "sensor.baiamonte_overnight_coverage")),
        "energy_required_kwh": _number(_entity(rows, "sensor.baiamonte_overnight_energy_requirement")),
        "target_energy_kwh": _number(_entity(rows, "sensor.baiamonte_overnight_target_energy")),
        "energy_needed_kwh": _number(_entity(rows, "sensor.baiamonte_energy_needed_until_sunrise")),
        "required_net_charge_w": _number(_entity(rows, "sensor.baiamonte_required_net_charging_power")),
        "ready": (_number(_entity(rows, "sensor.baiamonte_overnight_coverage")) or 0) >= 100,
    }


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


@router.post("/water/cistern-reference", dependencies=[Depends(authorize_admin)])
def save_cistern_reference(reading: CisternReferenceReading, username: str = Depends(request_username)) -> dict[str, Any]:
    return {"level": record_owner_assisted_cistern_reading(
        reading.level_percent, reading.confidence, reading.notes, username or "administrator"
    )}


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
    battery_bank = _battery_bank(entities)
    checks = [
        {"name": "Growatt inverter telemetry", "ready": any("growatt" in f"{r.get('entity_id')} {r.get('name')}".casefold() and r.get("available") for r in entities)},
        {"name": "Felicity RS485 bank online", "ready": battery_bank.get("connected")},
        {"name": "Direct battery state of charge", "ready": snapshot.get("battery_soc_pct") is not None},
        {"name": "Direct battery charge / discharge", "ready": snapshot.get("battery_power_w") is not None},
        {"name": "Estate load measurement", "ready": snapshot.get("estate_load_w") is not None},
    ]
    return json_ready({"checked_at": status.get("checked_at"), "solar": status.get("solar") or {}, "power": status.get("power") or [],
                       "snapshot": snapshot, "battery_bank": battery_bank, "energy_flow": _energy_flow(snapshot, battery_bank), "settings": settings, "learning": learning, "entities": entities,
                       "overnight": _overnight_readiness(entities),
                       "commissioning": checks, "commissioning_ready": all(row["ready"] for row in checks),
                       "battery_live": bool(battery_bank.get("connected") and snapshot.get("battery_soc_pct") is not None and snapshot.get("battery_power_w") is not None),
                       "safety_statement": "The Felicity battery bank is live and read-only. Reserve automation remains disabled unless separate load meters and explicitly approved controls are available; missing sensors are never treated as zero."})
