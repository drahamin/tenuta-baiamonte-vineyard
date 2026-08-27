"""Resolve Home Assistant entities whose generated IDs vary by installation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


DEFAULT_GW2000_ENTITIES = {
    "temp_c": "sensor.gw2000a_outdoor_temperature",
    "humidity_pct": "sensor.gw2000a_humidity",
    "pressure_hpa": "sensor.gw2000a_relative_pressure",
    "wind_kph": "sensor.gw2000a_wind_speed",
    "wind_gust_kph": "sensor.gw2000a_wind_gust",
    "rain_mm": "sensor.gw2000a_daily_rain_rate_piezo",
    "solar_wm2": "sensor.gw2000a_solar_radiation",
    "uv_index": "sensor.gw2000a_uv_index",
    "soil_moisture_1": "sensor.gw2000a_soil_moisture_1",
    "soil_moisture_2": "sensor.gw2000a_soil_moisture_2",
}

UNAVAILABLE_STATES = {"", "unknown", "unavailable", "none"}


def _numeric_state(item: dict[str, Any] | None) -> float | None:
    try:
        return float((item or {}).get("state"))
    except (TypeError, ValueError):
        return None


def _public_sensor(item: dict[str, Any], value: float, *, source: str, name: str | None = None, entity_id: str | None = None, unit: str | None = None) -> dict[str, Any]:
    attributes = item.get("attributes") or {}
    return {
        "entity_id": entity_id or item.get("entity_id"),
        "name": name or attributes.get("friendly_name") or item.get("entity_id"),
        "value": value,
        "unit": unit if unit is not None else attributes.get("unit_of_measurement") or "",
        "device_class": attributes.get("device_class") or "",
        "source": source,
    }


def solar_energy_summary(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate actual Growatt production from the Solcast prediction."""
    state_map = {str(item.get("entity_id") or ""): item for item in states}

    def solcast_sensor(*terms: str) -> dict[str, Any] | None:
        """Find Solcast sensors without depending on the integration's entity prefix."""
        exact = "sensor.solcast_pv_forecast_" + "_".join(terms)
        if exact in state_map:
            return state_map[exact]
        candidates = []
        for entity_id, item in state_map.items():
            attributes = item.get("attributes") or {}
            searchable = " ".join((entity_id, str(attributes.get("friendly_name") or ""))).casefold()
            if "solcast" in searchable and all(term.casefold() in searchable for term in terms):
                candidates.append(item)
        return next((item for item in candidates if _numeric_state(item) is not None), candidates[0] if candidates else None)

    def attribute_number(attributes: dict[str, Any], *names: str) -> float | None:
        for name in names:
            value = attributes.get(name)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def probability_range(item: dict[str, Any] | None, likely: float | None) -> dict[str, Any] | None:
        if not item:
            return None
        attributes = item.get("attributes") or {}
        analysis = attributes.get("analysis") if isinstance(attributes.get("analysis"), dict) else {}
        low = attribute_number(attributes, "estimate10", "pv_estimate10", "estimate10_kwh")
        high = attribute_number(attributes, "estimate90", "pv_estimate90", "estimate90_kwh")
        if low is None:
            low = attribute_number(analysis, "estimate10", "estimate10_kwh", "pv_estimate10")
        if high is None:
            high = attribute_number(analysis, "estimate90", "estimate90_kwh", "pv_estimate90")
        central = attribute_number(attributes, "estimate", "pv_estimate")
        if central is None:
            central = likely
        confidence = attribute_number(analysis, "confidence")
        if confidence is not None and confidence <= 1:
            confidence *= 100
        if low is None and high is None and central is None:
            return None
        unit = str(attributes.get("unit_of_measurement") or "kWh")
        return {
            "low": low,
            "likely": central,
            "high": high,
            "spread": (round(high - low, 3) if low is not None and high is not None else None),
            "confidence_percent": (round(confidence, 1) if confidence is not None else None),
            "unit": unit,
            "basis": "Solcast P10 / P50 / P90",
        }

    def matching(suffixes: tuple[str, ...]) -> list[dict[str, Any]]:
        return [
            item for entity_id, item in state_map.items()
            if "growatt" in entity_id.casefold() and any(entity_id.casefold().endswith(suffix) for suffix in suffixes)
            and _numeric_state(item) is not None
        ]

    def combined(rows: list[dict[str, Any]], name: str, unit: str, entity_id: str) -> dict[str, Any] | None:
        if not rows:
            return None
        total = 0.0
        for row in rows:
            value = _numeric_state(row) or 0.0
            row_unit = str((row.get("attributes") or {}).get("unit_of_measurement") or unit)
            if unit == "W" and row_unit == "kW":
                value *= 1000
            elif unit == "kWh" and row_unit == "Wh":
                value /= 1000
            total += value
        return _public_sensor(rows[0], total, source="Growatt live", name=name, entity_id=entity_id, unit=unit)

    actual_power = combined(matching(("_pv1_watts", "_pv2_watts")), "Growatt PV input", "W", "derived.growatt_pv_input")
    actual_today = combined(matching(("_pv1_kwh_today", "_pv2_kwh_today")), "Growatt PV energy today", "kWh", "derived.growatt_pv_energy_today")

    solcast_now_item = solcast_sensor("power", "now")
    solcast_now_value = _numeric_state(solcast_now_item)
    solcast_now = _public_sensor(solcast_now_item, solcast_now_value, source="Solcast estimate") if solcast_now_item and solcast_now_value is not None else None
    solcast_today_item = solcast_sensor("forecast", "today")
    solcast_today_value = _numeric_state(solcast_today_item)
    solcast_today = _public_sensor(solcast_today_item, solcast_today_value, source="Solcast forecast") if solcast_today_item and solcast_today_value is not None else None

    solcast_remaining_item = solcast_sensor("forecast", "remaining", "today")
    solcast_remaining_value = _numeric_state(solcast_remaining_item)
    solcast_remaining = _public_sensor(solcast_remaining_item, solcast_remaining_value, source="Solcast forecast") if solcast_remaining_item and solcast_remaining_value is not None else None
    solcast_tomorrow_item = solcast_sensor("forecast", "tomorrow")
    solcast_tomorrow_value = _numeric_state(solcast_tomorrow_item)
    solcast_tomorrow = _public_sensor(solcast_tomorrow_item, solcast_tomorrow_value, source="Solcast forecast") if solcast_tomorrow_item and solcast_tomorrow_value is not None else None

    forecast_points: list[dict[str, Any]] = []
    if solcast_today_item:
        attributes = solcast_today_item.get("attributes") or {}
        detail = attributes.get("detailedHourly") or attributes.get("detailedForecast")
        if not isinstance(detail, list):
            detail = next((value for key, value in attributes.items() if key.startswith("detailedHourly") and isinstance(value, list)), [])
        for point in detail or []:
            if not isinstance(point, dict):
                continue
            observed_at = point.get("period_start") or point.get("datetime") or point.get("time")
            value = point.get("pv_estimate") if point.get("pv_estimate") is not None else point.get("estimate")
            try:
                if observed_at and value is not None:
                    low = point.get("pv_estimate10") if point.get("pv_estimate10") is not None else point.get("estimate10")
                    high = point.get("pv_estimate90") if point.get("pv_estimate90") is not None else point.get("estimate90")
                    forecast_points.append({
                        "observed_at": str(observed_at),
                        "power_w": round(float(value) * 1000, 1),
                        "low_w": round(float(low) * 1000, 1) if low is not None else None,
                        "high_w": round(float(high) * 1000, 1) if high is not None else None,
                    })
            except (TypeError, ValueError):
                continue

    return {
        "current_power": actual_power or solcast_now,
        "energy_today": actual_today,
        "forecast_energy_today": solcast_today,
        "forecast_energy_remaining": solcast_remaining,
        "forecast_energy_tomorrow": solcast_tomorrow,
        "forecast_range_today": probability_range(solcast_today_item, solcast_today_value),
        "forecast_range_remaining": probability_range(solcast_remaining_item, solcast_remaining_value),
        "forecast_range_tomorrow": probability_range(solcast_tomorrow_item, solcast_tomorrow_value),
        "forecast_points": forecast_points[:48],
        "actual_source": "Growatt" if actual_power or actual_today else None,
        "forecast_source": "Solcast" if solcast_now or solcast_today else None,
        "forecast_available": bool(solcast_now or solcast_today or solcast_remaining or solcast_tomorrow or forecast_points),
    }


def home_assistant_inventory(states: list[dict[str, Any]], config_root: str | Path = "/homeassistant") -> dict[str, Any]:
    """Summarize registered devices, active entities and dashboard coverage without exposing sensitive attributes."""
    root = Path(config_root)
    state_map = {str(item.get("entity_id") or ""): item for item in states}
    registry_entities: list[dict[str, Any]] = []
    registry_devices: list[dict[str, Any]] = []
    try:
        registry_entities = json.loads((root / ".storage/core.entity_registry").read_text(encoding="utf-8")).get("data", {}).get("entities", [])
    except (OSError, ValueError, TypeError):
        pass
    try:
        registry_devices = json.loads((root / ".storage/core.device_registry").read_text(encoding="utf-8")).get("data", {}).get("devices", [])
    except (OSError, ValueError, TypeError):
        pass

    enabled_entities = [row for row in registry_entities if row.get("disabled_by") is None] if registry_entities else [{"entity_id": key} for key in state_map]
    enabled_devices = [row for row in registry_devices if row.get("disabled_by") is None]
    unavailable = []
    domains: dict[str, int] = {}
    category_terms = {
        "Solar, battery & power": ("solar", "pv", "growatt", "inverter", "battery", "grid", "generator", "energy", "power"),
        "Weather & vineyard sensors": ("gw2000", "ecowitt", "weather", "rain", "wind", "humidity", "soil", "temperature", "uv_"),
        "Cameras & safety": ("camera", "eufy", "alarm", "smoke", "fire", "motion", "siren", "doorbell"),
        "Network & communications": ("router", "gateway", "access_point", "wifi", "starlink", "lte", "modem", "omada", "whatsapp"),
        "Water & cellar": ("cistern", "water", "pump", "tank", "cellar", "wine", "refrigerator"),
        "Media & displays": ("media_player", "television", "samsung", "firetv", "speaker", "alexa", "display"),
    }
    categories = {name: {"name": name, "entities": 0, "unavailable": 0} for name in category_terms}
    for row in enabled_entities:
        entity_id = str(row.get("entity_id") or "")
        if not entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        domains[domain] = domains.get(domain, 0) + 1
        state_row = state_map.get(entity_id) or {}
        attributes = state_row.get("attributes") or {}
        text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold()
        category = next((name for name, terms in category_terms.items() if any(term in text for term in terms)), "Other Home Assistant")
        if category not in categories:
            categories[category] = {"name": category, "entities": 0, "unavailable": 0}
        categories[category]["entities"] += 1
        raw_state = str(state_row.get("state") or "unknown").casefold()
        if raw_state in UNAVAILABLE_STATES:
            categories[category]["unavailable"] += 1
            if len(unavailable) < 40:
                unavailable.append({
                    "entity_id": entity_id,
                    "name": attributes.get("friendly_name") or entity_id.split(".", 1)[-1].replace("_", " ").title(),
                    "state": raw_state,
                    "category": category,
                })

    # Some intentional local-push entities are runtime-owned and therefore do
    # not live in the entity registry. A live state is a valid dashboard target
    # and must not be reported as a missing reference.
    registered_ids = {str(row.get("entity_id") or "") for row in registry_entities} | set(state_map)
    dashboard_references: set[str] = set()
    dashboard_root = root / "baiamonte_dashboards"
    for path in dashboard_root.glob("*.yaml") if dashboard_root.is_dir() else []:
        try:
            dashboard_references.update(re.findall(r"^\s*(?:-\s*)?entity:\s*([a-z_]+\.[a-zA-Z0-9_]+)\s*$", path.read_text(encoding="utf-8"), re.M))
        except OSError:
            continue
    missing_dashboard = sorted(entity_id for entity_id in dashboard_references if entity_id not in registered_ids)
    manufacturers: dict[str, int] = {}
    for device in enabled_devices:
        name = str(device.get("manufacturer") or "Unknown")
        manufacturers[name] = manufacturers.get(name, 0) + 1
    return {
        "device_count": len(enabled_devices) if registry_devices else None,
        "entity_count": len(enabled_entities),
        "available_entities": sum(1 for row in enabled_entities if str((state_map.get(str(row.get("entity_id") or "")) or {}).get("state") or "unknown").casefold() not in UNAVAILABLE_STATES),
        "unavailable_entities": sum(item["unavailable"] for item in categories.values()),
        "categories": sorted(categories.values(), key=lambda item: (-item["entities"], item["name"])),
        "top_domains": [{"name": name, "count": count} for name, count in sorted(domains.items(), key=lambda item: (-item[1], item[0]))[:12]],
        "top_manufacturers": [{"name": name, "count": count} for name, count in sorted(manufacturers.items(), key=lambda item: (-item[1], item[0]))[:12]],
        "unavailable": unavailable,
        "dashboard_reference_count": len(dashboard_references),
        "missing_dashboard_references": missing_dashboard[:40],
    }

_SPECS = {
    "temp_c": {"terms": ("outdoor temperature", "outside temperature", "temperatura esterna", "outdoor_temperature"), "classes": ("temperature",), "exclude": ("indoor",)},
    "humidity_pct": {"terms": ("outdoor humidity", "outside humidity", "umidità esterna", "humidity"), "classes": ("humidity",), "exclude": ("indoor", "soil")},
    "pressure_hpa": {"terms": ("relative pressure", "atmospheric pressure", "pressione relativa", "pressure"), "classes": ("atmospheric_pressure",), "exclude": ()},
    "wind_kph": {"terms": ("wind speed", "velocità vento", "wind_speed"), "classes": ("wind_speed",), "exclude": ("gust", "raffica")},
    "wind_gust_kph": {"terms": ("wind gust", "gust", "raffica"), "classes": ("wind_speed",), "exclude": ()},
    "rain_mm": {"terms": ("daily rain", "daily rainfall", "pioggia giornaliera", "rain"), "classes": ("precipitation",), "exclude": ("hourly", "weekly", "monthly", "yearly")},
    "solar_wm2": {"terms": ("solar radiation", "irradiance", "radiazione solare"), "classes": ("irradiance",), "exclude": ("energy",)},
    "uv_index": {"terms": ("uv index", "indice uv", "uv_index"), "classes": (), "exclude": ()},
    "soil_moisture_1": {"terms": ("soil moisture 1", "soil moisture", "umidità suolo", "soil_moisture_1"), "classes": ("moisture",), "exclude": ("soil moisture 2", "soil_moisture_2")},
    "soil_moisture_2": {"terms": ("soil moisture 2", "umidità suolo 2", "soil_moisture_2"), "classes": ("moisture",), "exclude": ()},
}


def resolve_gw2000_entities(states: list[dict[str, Any]], prefix_setting: str = "gw2000,ecowitt") -> dict[str, str]:
    """Find the station sensors using entity IDs, friendly names, and device classes."""
    prefixes = tuple(value.strip().casefold() for value in prefix_setting.split(",") if value.strip()) or ("gw2000", "ecowitt")
    by_id = {str(item.get("entity_id") or ""): item for item in states}
    all_candidates = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        attributes = item.get("attributes") or {}
        text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold().replace("_", " ")
        if entity_id.startswith("sensor."):
            all_candidates.append((entity_id, attributes, text))
    station_candidates = [row for row in all_candidates if any(prefix in row[2] for prefix in prefixes)]

    resolved: dict[str, str] = {}
    for metric, default_entity in DEFAULT_GW2000_ENTITIES.items():
        default_state = str((by_id.get(default_entity) or {}).get("state") or "").casefold()
        if default_entity in by_id and default_state not in {"", "unknown", "unavailable"}:
            resolved[metric] = default_entity
            continue
        spec = _SPECS[metric]
        for candidates in (station_candidates, all_candidates):
            ranked = []
            for entity_id, attributes, text in candidates:
                if any(term in text for term in spec["exclude"]):
                    continue
                term_score = max((len(term) for term in spec["terms"] if term in text), default=0)
                class_score = 20 if str(attributes.get("device_class") or "") in spec["classes"] else 0
                if term_score:
                    ranked.append((class_score + term_score, entity_id))
            if ranked:
                resolved[metric] = max(ranked)[1]
                break
    return resolved


def merge_display_weather(database_weather: list[dict[str, Any]], live_weather: dict[str, Any]) -> list[dict[str, Any]]:
    """End the TV series on a usable live observation without losing history."""
    if any(value is not None for key, value in live_weather.items() if key != "observed_at"):
        return [*database_weather[-47:], live_weather]
    return database_weather


def build_power_indicators(states: list[dict[str, Any]], solar_current: dict[str, Any] | None) -> list[dict[str, str]]:
    """Build simple, presentation-safe power-source status lights."""
    numeric_rows = []
    for item in states:
        attributes = item.get("attributes") or {}
        unit = str(attributes.get("unit_of_measurement") or "")
        try:
            value = float(item.get("state"))
        except (TypeError, ValueError):
            continue
        text = f"{item.get('entity_id') or ''} {attributes.get('friendly_name') or ''}".casefold().replace("_", " ")
        numeric_rows.append({"text": text, "value": value, "unit": unit})

    def choose(terms: tuple[str, ...], units: set[str], exclude: tuple[str, ...] = ()) -> dict[str, Any] | None:
        ranked = []
        for row in numeric_rows:
            if row["unit"] not in units or any(term in row["text"] for term in exclude):
                continue
            score = max((len(term) for term in terms if term in row["text"]), default=0)
            if score:
                ranked.append((score, row))
        return max(ranked, key=lambda item: item[0])[1] if ranked else None

    def watts(row: dict[str, Any] | None) -> float | None:
        if not row:
            return None
        return float(row["value"]) * (1000 if row.get("unit") == "kW" else 1)

    def power_light(code: str, name: str, row: dict[str, Any] | None, threshold: float = 30) -> dict[str, str]:
        value = watts(row)
        if value is None:
            return {"code": code, "name": name, "state": "off", "detail": "Sensor not detected"}
        state = "green" if abs(value) >= threshold else "off"
        return {"code": code, "name": name, "state": state, "detail": f"{value:,.0f} W · {'active' if state == 'green' else 'idle'}"}

    solar_row = None
    if solar_current:
        solar_row = {"value": solar_current.get("value"), "unit": solar_current.get("unit") or "W"}
    grid = choose(("grid power", "grid import", "utility power", "meter power"), {"W", "kW"}, ("solar", "pv", "battery", "generator"))
    generator = choose(("generator main breaker", "generator power", "generator"), {"W", "kW"})
    battery = choose(("battery state of charge", "battery soc", "battery level"), {"%"})
    indicators = [
        power_light("solar", "Solar", solar_row),
        power_light("grid", "Grid", grid),
        power_light("generator", "Generator", generator, 50),
    ]
    if battery:
        charge = float(battery["value"])
        state = "red" if charge < 15 else "amber" if charge < 40 else "green"
        indicators.append({"code": "battery", "name": "Battery", "state": state, "detail": f"{charge:.0f}% charge"})
    else:
        indicators.append({"code": "battery", "name": "Battery", "state": "off", "detail": "Sensor not detected"})
    return indicators


def find_baiamonte_media(states: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the active Baiamonte speaker group without exposing HA controls."""
    candidates = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        if not entity_id.startswith("media_player."):
            continue
        attributes = item.get("attributes") or {}
        state = str(item.get("state") or "").casefold()
        text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold().replace("_", " ")
        is_group = bool(attributes.get("group_members")) or "group" in text or "gruppo" in text
        baiamonte_score = 50 if any(name in text for name in ("baiamonte", "tenuta baiamonte", "vineyard", "vigneto")) else 0
        group_score = 25 if is_group else 0
        active_score = 100 if state == "playing" else 60 if state == "paused" else 0
        if active_score and baiamonte_score:
            candidates.append((active_score + baiamonte_score + group_score, item))
    if not candidates:
        return None
    item = max(candidates, key=lambda value: value[0])[1]
    attributes = item.get("attributes") or {}
    return {
        "entity_id": item.get("entity_id"),
        "name": attributes.get("friendly_name") or "Baiamonte speakers",
        "state": item.get("state"),
        "title": attributes.get("media_title") or attributes.get("media_series_title") or attributes.get("media_channel"),
        "artist": attributes.get("media_artist") or attributes.get("media_album_artist"),
        "album": attributes.get("media_album_name"),
        "source": attributes.get("source") or attributes.get("app_name"),
    }


def find_network_equipment(states: list[dict[str, Any]], configured_entities: str = "") -> list[dict[str, Any]]:
    """Return presentation-safe status lights for routers and access points."""
    state_map = {str(item.get("entity_id") or ""): item for item in states}
    configured = [value.strip() for value in configured_entities.split(",") if value.strip()]
    configured_set = set(configured)
    terms = re.compile(r"\b(router|gateway|access point|wifi ap|wireless ap|unifi|ubiquiti|omada|deco|eero|wlan)\b", re.I)
    discovered: list[tuple[int, str]] = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        if not entity_id.startswith(("binary_sensor.", "device_tracker.", "sensor.")):
            continue
        attributes = item.get("attributes") or {}
        text = f"{entity_id.replace('_', ' ')} {attributes.get('friendly_name') or ''}"
        normalized = text.casefold()
        if terms.search(text) and "miami" not in normalized:
            raw = str(item.get("state") or "unknown").casefold()
            # Home Assistant often retains unavailable entities from replaced
            # router integrations. Do not alarm on those stale discoveries;
            # explicitly configured entities remain visible for diagnosis.
            if raw in {"unavailable", "unknown", "none", ""} and entity_id not in configured_set:
                continue
            # Do not auto-promote spare physical ports into estate alarms. An
            # administrator can still opt into any one of these entities by
            # listing it explicitly in network_equipment_entities.
            if raw == "off" and entity_id not in configured_set and re.search(
                r"port_[2-9]_(?:lan_status|internet_link|online_detection)$", entity_id
            ):
                continue
            score = 100 if raw not in {"unavailable", "unknown", "none", ""} else 0
            score += 60 if any(term in normalized for term in ("internet link", "online detection", "access point", "router main")) else 0
            score += 25 if entity_id.startswith("binary_sensor.") else 0
            discovered.append((score, entity_id))
    discovered_ids = [entity_id for _, entity_id in sorted(discovered, key=lambda value: (-value[0], value[1]))]
    entity_ids = list(dict.fromkeys([*configured, *discovered_ids]))[:10]
    lights = []
    for entity_id in entity_ids:
        item = state_map.get(entity_id) or {}
        attributes = item.get("attributes") or {}
        raw_state = str(item.get("state") or "unknown").casefold()
        text = f"{entity_id.replace('_', ' ')} {attributes.get('friendly_name') or ''}".casefold()
        device_class = str(attributes.get("device_class") or "").casefold()
        if raw_state in {"unavailable", "unknown", "none", ""}:
            status = "red"
        elif entity_id.startswith("device_tracker."):
            status = "green" if raw_state == "home" else "red"
        elif entity_id.startswith("binary_sensor."):
            if device_class in {"problem", "safety", "tamper"} or " problem" in text:
                status = "red" if raw_state == "on" else "green"
            elif device_class == "connectivity" or any(term in text for term in ("internet link", "online detection", "connected")):
                status = "green" if raw_state == "on" else "red"
            else:
                # A disabled unused LAN port is informational, not a system fault.
                status = "green" if raw_state == "on" else "off"
        else:
            status = "green"
        detail_parts = [str(item.get("state") or "unavailable")]
        if attributes.get("ip") or attributes.get("ip_address"):
            detail_parts.append(str(attributes.get("ip") or attributes.get("ip_address")))
        lights.append({
            "code": entity_id,
            "name": attributes.get("friendly_name") or entity_id.split(".", 1)[-1].replace("_", " ").title(),
            "state": status,
            "detail": " · ".join(detail_parts),
        })
    return lights


def find_lte_status(states: list[dict[str, Any]]) -> dict[str, str]:
    """Find the best Home Assistant LTE/cellular health entity without exposing controls."""
    terms = re.compile(r"\b(lte|cellular|mobile data|modem|nokia|wan|internet link|online detection)\b", re.I)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        if not entity_id.startswith(("binary_sensor.", "device_tracker.", "sensor.", "switch.")):
            continue
        attributes = item.get("attributes") or {}
        text = f"{entity_id.replace('_', ' ')} {attributes.get('friendly_name') or ''}"
        normalized = text.casefold()
        if not terms.search(text) or "miami" in normalized:
            continue
        raw = str(item.get("state") or "unknown").casefold()
        score = 120 if raw not in {"unavailable", "unknown", "none", ""} else 0
        score += 80 if any(word in normalized for word in ("internet link", "online detection", "connected", "connectivity")) else 0
        score += 40 if any(word in normalized for word in ("status", "signal", "rssi")) else 20
        if entity_id.startswith(("binary_sensor.", "device_tracker.")):
            score += 20
        ranked.append((score, item))
    if not ranked:
        return {"code": "lte", "name": "LTE", "state": "off", "detail": "Status entity not detected"}
    item = max(ranked, key=lambda value: value[0])[1]
    entity_id = str(item.get("entity_id") or "")
    attributes = item.get("attributes") or {}
    raw = str(item.get("state") or "unknown").casefold()
    if raw in {"unavailable", "unknown", "none", ""}:
        state = "red"
    elif entity_id.startswith("device_tracker."):
        state = "green" if raw == "home" else "red"
    elif entity_id.startswith(("binary_sensor.", "switch.")):
        device_class = str(attributes.get("device_class") or "").casefold()
        text = f"{entity_id.replace('_', ' ')} {attributes.get('friendly_name') or ''}".casefold()
        if device_class in {"problem", "safety", "tamper"} or " problem" in text:
            state = "red" if raw == "on" else "green"
        elif device_class == "connectivity" or any(word in text for word in ("internet link", "online detection", "connected")):
            state = "green" if raw == "on" else "red"
        else:
            state = "green" if raw == "on" else "off"
    else:
        try:
            value = float(raw)
            unit = str(attributes.get("unit_of_measurement") or "")
            state = "green" if unit in {"dBm", "dB"} and value >= -80 else "amber" if unit in {"dBm", "dB"} and value >= -100 else "green"
        except ValueError:
            state = "green" if raw in {"connected", "online", "ok", "available", "active"} else "amber"
    name = attributes.get("friendly_name") or "LTE connection"
    return {"code": "lte", "name": str(name), "state": state, "detail": f"{item.get('state') or 'unavailable'} · {entity_id}"}
