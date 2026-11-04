"""Per-sensor station report clocks from an existing HA cache, never a frame clock."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ..ha_entities import DEFAULT_GW2000_ENTITIES, gw2000_metric_value
from .mobile_weather_projection import _time, _iso, _number

CONTRACT = "baiamonte.mobile-weather-reports.v1"
RAW_CONTRACT = "baiamonte.station-report-evidence.v1"
STALE_SECONDS = 600
CLOCK_FIELDS = ("last_reported", "last_updated", "last_changed")
# Wire field: source metric, canonical unit, permitted source units, bounds.
SPECS = {
    "temp_c": ("temp_c", "celsius", {"°c", "c", "celsius", "°f", "f", "fahrenheit"}, -100, 70),
    "feels_like_c": ("feels_like_c", "celsius", {"°c", "c", "celsius", "°f", "f", "fahrenheit"}, -100, 90),
    "humidity_pct": ("humidity_pct", "percent", {"%", "percent"}, 0, 100),
    "dew_point_c": ("dew_point_c", "celsius", {"°c", "c", "celsius", "°f", "f", "fahrenheit"}, -100, 70),
    "vpd_kpa": ("vpd_kpa", "kilopascals", {"kpa", "hpa", "mbar", "pa"}, 0, 20),
    "pressure_hpa": ("pressure_hpa", "hectopascals", {"hpa", "mbar", "inhg", "in hg"}, 300, 1200),
    "wind_kph": ("wind_kph", "kilometres_per_hour", {"km/h", "kph", "kmh", "m/s", "mps", "mph", "mi/h"}, 0, 500),
    "wind_gust_kph": ("wind_gust_kph", "kilometres_per_hour", {"km/h", "kph", "kmh", "m/s", "mps", "mph", "mi/h"}, 0, 500),
    "gust_max_today_kph": ("gust_max_today_kph", "kilometres_per_hour", {"km/h", "kph", "kmh", "m/s", "mps", "mph", "mi/h"}, 0, 500),
    "wind_direction_deg": ("wind_direction_deg", "degrees", {"°", "deg", "degree", "degrees"}, 0, 360),
    "wind_direction_10m_deg": ("wind_direction_10m_deg", "degrees", {"°", "deg", "degree", "degrees"}, 0, 360),
    "rain_mm": ("rain_mm", "millimetres", {"mm", "in", "inch", "inches"}, 0, 10000),
    "rain_rate_mm_h": ("rain_rate_mm_h", "millimetres_per_hour", {"mm/h", "mm/hr", "mm/hour", "in/h", "in/hr", "in/hour", "inch/h", "inches/hour"}, 0, 2000),
    "solar_wm2": ("solar_wm2", "watts_per_square_metre", {"w/m²", "w/m2", "kw/m²", "kw/m2"}, 0, 2000),
    "uv_index": ("uv_index", "index", {"", "index", "uv index"}, 0, 30),
    "leaf_wetness_pct": ("leaf_wetness_pct", "percent", {"%", "percent"}, 0, 100),
    "soil_moisture_pct": ("soil_moisture_1", "percent", {"%", "percent"}, 0, 100),
    "soil_temp_c": ("soil_temp_c", "celsius", {"°c", "c", "celsius", "°f", "f", "fahrenheit"}, -100, 70),
    "sensor_battery_v": ("sensor_battery_v", "volts", {"v", "volt", "volts"}, 0, 100),
    "sensor_capacitor_v": ("sensor_capacitor_v", "volts", {"v", "volt", "volts"}, 0, 100),
}


def build_station_evidence(states: Mapping[str, Any], resolved: Mapping[str, str], estate_id: str,
                           *, now: datetime | None = None) -> dict[str, Any]:
    """Attach evidence to the existing refresh without I/O or resolver fallback.

    Only exact commissioned default identities qualify here. A renamed/fuzzy
    alias may remain in the legacy display but is not silently attested.
    """
    capture_clock = _time(now) if now is not None else datetime.now(timezone.utc)
    if capture_clock is None:
        raise ValueError("aware station evidence capture clock required")
    metrics = {}
    for field, (metric, unit, units, lower, upper) in SPECS.items():
        entity = resolved.get(metric)
        item = states.get(entity) if entity == DEFAULT_GW2000_ENTITIES[metric] else None
        item = item if isinstance(item, Mapping) and item.get("entity_id") == entity else {}
        attrs = item.get("attributes")
        attrs = attrs if isinstance(attrs, Mapping) else {}
        source_unit = attrs.get("unit_of_measurement")
        source_unit = source_unit.strip().casefold() if isinstance(source_unit, str) else ""
        clock_field = next((key for key in CLOCK_FIELDS if item.get(key)), None)
        value = gw2000_metric_value(item, metric) if item and source_unit in units else None
        value = _number(value, lower, upper)
        reported = _time(item.get(clock_field)) if clock_field else None
        if reported is not None and reported > capture_clock:
            reported = None  # A bad future clock cannot age into valid cache evidence.
        metrics[field] = {"value": value, "unit": unit, "clock_field": clock_field,
                          "reported_at": _iso(reported)}
    return {"contract": RAW_CONTRACT, "estate_id": estate_id, "metrics": metrics}


def project_station_reports(raw: Any, estate_id: str, source: str | None, now: datetime) -> dict[str, Any]:
    try:
        valid_estate = isinstance(estate_id, str) and str(UUID(estate_id)) == estate_id
    except (ValueError, TypeError, AttributeError):
        valid_estate = False
    clock = _time(now)
    if not valid_estate or clock is None:
        raise ValueError("valid station report boundary required")
    raw = raw if isinstance(raw, Mapping) else {}
    qualified = raw.get("contract") == RAW_CONTRACT and raw.get("estate_id") == estate_id and source == "home_assistant"
    rows = raw.get("metrics") if qualified and isinstance(raw.get("metrics"), Mapping) else {}
    metrics = {}
    for field, (_metric, unit, _units, lower, upper) in SPECS.items():
        row = rows.get(field)
        row = row if isinstance(row, Mapping) else {}
        value = _number(row.get("value"), lower, upper) if row.get("unit") == unit else None
        reported = _time(row.get("reported_at")) if row.get("clock_field") in CLOCK_FIELDS else None
        if value is None or reported is None or reported > clock:
            value, reported = None, None
        age = int((clock - reported).total_seconds()) if reported else None
        metrics[field] = {"value": value, "unit": unit, "reported_at": _iso(reported),
                          "clock_field": row.get("clock_field") if reported else None,
                          "data_age_seconds": age,
                          "quality": "unavailable" if value is None else "current" if age <= STALE_SECONDS else "stale"}
    return {"contract": CONTRACT, "estate_id": estate_id, "timestamp_basis": "home_assistant_state_report",
            "metrics": metrics}
