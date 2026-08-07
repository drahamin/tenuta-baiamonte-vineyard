"""Resolve Home Assistant entities whose generated IDs vary by installation."""

from __future__ import annotations

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
    terms = re.compile(r"\b(router|gateway|access point|wifi ap|wireless ap|unifi|ubiquiti|omada|deco|eero|wlan)\b", re.I)
    discovered = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        if not entity_id.startswith(("binary_sensor.", "device_tracker.", "sensor.")):
            continue
        attributes = item.get("attributes") or {}
        text = f"{entity_id.replace('_', ' ')} {attributes.get('friendly_name') or ''}"
        if terms.search(text):
            discovered.append(entity_id)
    entity_ids = list(dict.fromkeys([*configured, *discovered]))[:10]
    lights = []
    for entity_id in entity_ids:
        item = state_map.get(entity_id) or {}
        attributes = item.get("attributes") or {}
        raw_state = str(item.get("state") or "unknown").casefold()
        if raw_state in {"unavailable", "unknown", "none", ""}:
            status = "red"
        elif entity_id.startswith("device_tracker."):
            status = "green" if raw_state == "home" else "red"
        elif entity_id.startswith("binary_sensor."):
            status = "green" if raw_state == "on" else "red"
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
