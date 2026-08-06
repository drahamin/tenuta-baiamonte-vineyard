"""Resolve Home Assistant entities whose generated IDs vary by installation."""

from __future__ import annotations

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
    candidates = []
    for item in states:
        entity_id = str(item.get("entity_id") or "")
        attributes = item.get("attributes") or {}
        text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold().replace("_", " ")
        if entity_id.startswith("sensor.") and any(prefix in text for prefix in prefixes):
            candidates.append((entity_id, attributes, text))

    resolved: dict[str, str] = {}
    for metric, default_entity in DEFAULT_GW2000_ENTITIES.items():
        default_state = str((by_id.get(default_entity) or {}).get("state") or "").casefold()
        if default_entity in by_id and default_state not in {"", "unknown", "unavailable"}:
            resolved[metric] = default_entity
            continue
        spec = _SPECS[metric]
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
    return resolved


def merge_display_weather(database_weather: list[dict[str, Any]], live_weather: dict[str, Any]) -> list[dict[str, Any]]:
    """End the TV series on a usable live observation without losing history."""
    if any(value is not None for key, value in live_weather.items() if key != "observed_at"):
        return [*database_weather[-47:], live_weather]
    return database_weather
