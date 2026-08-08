"""Configurable moving cellar demonstration data for the dashboard and TV."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any

from .config import Settings, runtime_option
from .db import fetch_all


def demo_enabled(settings: Settings) -> bool:
    return str(runtime_option("cellar_mode", settings.cellar_mode)).strip().casefold() == "demo"


def cellar_guardrails(settings: Settings) -> dict[str, float]:
    """Return the user-configured screening limits used for tank alerts."""
    names = (
        "cellar_temp_min_c", "cellar_temp_max_c", "cellar_level_min_pct", "cellar_level_max_pct",
        "cellar_ph_min", "cellar_ph_max", "cellar_density_min_sg", "cellar_density_max_sg",
    )
    values = {name: float(getattr(settings, name)) for name in names}
    try:
        from .service import estate_id
        rows = fetch_all("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='cellar_guardrails'", (estate_id(),))
        saved = json.loads(rows[0]["setting_value"]) if rows and isinstance(rows[0]["setting_value"], str) else (rows[0]["setting_value"] if rows else {})
        for name in names:
            if name in saved:
                values[name] = float(saved[name])
    except Exception:
        pass
    for minimum, maximum in (
        ("cellar_temp_min_c", "cellar_temp_max_c"), ("cellar_level_min_pct", "cellar_level_max_pct"),
        ("cellar_ph_min", "cellar_ph_max"), ("cellar_density_min_sg", "cellar_density_max_sg"),
    ):
        if values[minimum] > values[maximum]:
            values[minimum], values[maximum] = values[maximum], values[minimum]
    return values


def evaluate_cellar_tanks(tanks: list[dict[str, Any]], settings: Settings) -> list[dict[str, Any]]:
    """Annotate tank rows and return explicit guardrail crossings without controlling equipment."""
    limits = cellar_guardrails(settings)
    alerts: list[dict[str, Any]] = []
    checks = (
        ("temp_c", "Temperature", "temperature", limits["cellar_temp_min_c"], limits["cellar_temp_max_c"], "°C"),
        ("level_pct", "Fill level", "level", limits["cellar_level_min_pct"], limits["cellar_level_max_pct"], "%"),
        ("ph", "pH", "chemistry", limits["cellar_ph_min"], limits["cellar_ph_max"], ""),
        ("density_sg", "Density", "chemistry", limits["cellar_density_min_sg"], limits["cellar_density_max_sg"], " SG"),
    )
    for tank in tanks:
        messages: list[str] = []
        violations: list[dict[str, Any]] = []
        for key, label, category, minimum, maximum, unit in checks:
            raw = tank.get(key)
            if raw is None:
                continue
            value = float(raw)
            if value < minimum:
                messages.append(f"{label} {value:g}{unit} below {minimum:g}{unit}")
                violations.append({"category": category, "field": key, "direction": "low", "value": value, "limit": minimum})
            elif value > maximum:
                messages.append(f"{label} {value:g}{unit} above {maximum:g}{unit}")
                violations.append({"category": category, "field": key, "direction": "high", "value": value, "limit": maximum})
        sensor_issues = list(tank.get("sensor_issues") or [])
        if sensor_issues:
            messages.append("Monitor unavailable: " + ", ".join(sensor_issues))
            violations.append({"category": "sensor", "entities": sensor_issues})
        tank["guard_state"] = "warning" if messages else "normal"
        tank["guard_messages"] = messages
        if messages:
            alerts.append({
                "tank_id": tank.get("id"), "tank_code": tank.get("code"), "tank_name": tank.get("name") or tank.get("code") or "Tank",
                "messages": messages, "reading_at": tank.get("reading_at"),
                "violations": violations,
            })
    return alerts


def _number(parts: list[str], index: int, fallback: float) -> float:
    try:
        return float(parts[index])
    except (IndexError, TypeError, ValueError):
        return fallback


def live_sensor_entity_ids(settings: Settings) -> set[str]:
    """Return only explicitly configured cellar sensor entities."""
    raw = str(runtime_option("cellar_live_sensors", settings.cellar_live_sensors) or "")
    entity_ids: set[str] = set()
    for definition in (part.strip() for part in raw.split(",") if part.strip()):
        for value in [item.strip() for item in definition.split("|")][1:6]:
            if value and "." in value:
                entity_ids.add(value)
    return entity_ids


def apply_live_sensor_readings(tanks: list[dict[str, Any]], settings: Settings, state_map: dict[str, dict[str, Any]]) -> None:
    """Overlay configured Home Assistant readings onto matching live vessels."""
    raw = str(runtime_option("cellar_live_sensors", settings.cellar_live_sensors) or "")
    by_key = {
        str(value).strip().casefold(): tank
        for tank in tanks
        for value in (tank.get("code"), tank.get("name"))
        if value
    }

    def reading(entity_id: str) -> tuple[float | None, str, str | None]:
        item = state_map.get(entity_id) or {}
        try:
            value = float(item.get("state"))
        except (TypeError, ValueError):
            value = None
        attributes = item.get("attributes") or {}
        return value, str(attributes.get("unit_of_measurement") or ""), item.get("last_updated") or item.get("last_changed")

    for definition in (part.strip() for part in raw.split(",") if part.strip()):
        parts = [value.strip() for value in definition.split("|")]
        if not parts:
            continue
        tank = by_key.get(parts[0].casefold())
        if not tank:
            continue
        entities = (parts + [""] * 6)[1:6]
        level_entity, temp_entity, density_entity, brix_entity, ph_entity = entities
        timestamps: list[str] = []
        sensor_issues: list[str] = []
        if level_entity:
            value, unit, observed_at = reading(level_entity)
            if value is not None:
                capacity = float(tank.get("capacity_l") or 0)
                if unit.casefold() in {"l", "liter", "litre", "liters", "litres"}:
                    tank["volume_l"] = round(value, 1)
                    tank["level_pct"] = round(value / capacity * 100, 1) if capacity else None
                else:
                    tank["level_pct"] = round(max(0, min(100, value)), 1)
                    tank["volume_l"] = round(capacity * tank["level_pct"] / 100, 1) if capacity else tank.get("volume_l")
            if observed_at:
                timestamps.append(str(observed_at))
        for entity_id, field in ((temp_entity, "temp_c"), (density_entity, "density_sg"), (brix_entity, "brix"), (ph_entity, "ph")):
            if not entity_id:
                continue
            value, unit, observed_at = reading(entity_id)
            if value is not None:
                if field == "temp_c" and unit.casefold() in {"°f", "f"}:
                    value = (value - 32) * 5 / 9
                tank[field] = round(value, 3 if field == "density_sg" else 2)
            if observed_at:
                timestamps.append(str(observed_at))
        for entity_id in (value for value in entities if value):
            state = str((state_map.get(entity_id) or {}).get("state") or "").strip().casefold()
            if not state or state in {"unknown", "unavailable", "none"}:
                sensor_issues.append(entity_id)
        configured = next((entity_id for entity_id in entities if entity_id), None)
        if configured:
            tank["sensor_entity_id"] = configured
            tank["source"] = "Home Assistant tank sensors"
            if timestamps:
                tank["reading_at"] = max(timestamps)
            tank["sensor_issues"] = sensor_issues


def demo_cellar(settings: Settings, year: int) -> dict[str, Any]:
    """Return visibly active demo tanks using editable Home Assistant baselines."""
    raw = str(runtime_option("cellar_demo_tanks", settings.cellar_demo_tanks) or settings.cellar_demo_tanks)
    now = datetime.now(timezone.utc)
    phase = now.timestamp() / 90
    tanks: list[dict[str, Any]] = []
    for index, definition in enumerate(part.strip() for part in raw.split(",") if part.strip()):
        parts = [value.strip() for value in definition.split("|")]
        capacity = max(1, _number(parts, 1, 750))
        level_base = min(100, max(0, _number(parts, 4, 70)))
        level = min(100, max(0, level_base + math.sin(phase + index * 1.4) * 0.7))
        temp_base = _number(parts, 5, 20)
        density_base = _number(parts, 6, 1.020)
        brix_base = _number(parts, 7, 10)
        ph_base = _number(parts, 8, 3.35)
        tanks.append({
            "id": f"demo-{index + 1}",
            "code": f"D-{index + 1:02d}",
            "name": parts[0] if parts else f"Tank {index + 1}",
            "container_type": "barrel" if len(parts) > 3 and parts[3].casefold() == "aging" else "tank",
            "capacity_l": round(capacity, 1),
            "volume_l": round(capacity * level / 100, 1),
            "level_pct": round(level, 1),
            "stage": parts[3] if len(parts) > 3 and parts[3] else "fermentation",
            "variety_summary": parts[2] if len(parts) > 2 and parts[2] else "Demo lot",
            "status": "demo",
            "source": "Configured vessel",
            "temp_c": round(temp_base + math.sin(phase / 2 + index) * 0.25, 1),
            "density_sg": round(max(0.980, density_base - (math.sin(phase / 3 + index) + 1) * 0.0005), 3),
            "brix": round(max(0, brix_base - (math.sin(phase / 3 + index) + 1) * 0.08), 1),
            "ph": round(ph_base + math.sin(phase / 4 + index) * 0.01, 2),
            "sensor_entity_id": None,
            "reading_at": now.isoformat(),
            "next_check_at": (now + timedelta(hours=index + 1)).isoformat(),
        })
        if len(tanks) >= 8:
            break
    processes = [
        {
            "id": f"demo-process-{index + 1}",
            "observed_at": now.isoformat(),
            "vessel_name": tank["name"],
            "lot_name": tank["variety_summary"],
            "stage": tank["stage"],
            "temp_c": tank["temp_c"],
            "density_sg": tank["density_sg"],
            "brix": tank["brix"],
            "ph": tank["ph"],
            "cap_management": "Demo circulation running" if tank["stage"] == "fermentation" else None,
            "sensory_observation": "Demo readings updating",
            "next_check_at": tank["next_check_at"],
            "status": "demo",
        }
        for index, tank in enumerate(tanks[:4])
    ]
    guard_alerts = evaluate_cellar_tanks(tanks, settings)
    return {"year": year, "demo": True, "tanks": tanks, "processes": processes, "guardrails": cellar_guardrails(settings), "guard_alerts": guard_alerts, "updated_at": now.isoformat()}
