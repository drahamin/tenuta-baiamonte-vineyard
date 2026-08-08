"""Small-team severe-weather screening from GW2000 and Home Assistant forecasts."""

from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def severe_weather_advisories(current: dict[str, Any] | None, forecast: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return concise condition, severity, timing and vineyard action records."""
    current, forecast = current or {}, forecast or []
    candidates: list[dict[str, Any]] = []

    def add(code: str, severity: str, title: str, detail: str, action: str, timing: str) -> None:
        candidates.append({"code": code, "severity": severity, "title": title, "detail": detail, "action": action, "timing": timing})

    rows = [{**current, "datetime": current.get("observed_at"), "_current": True}, *forecast[:7]]
    for row in rows:
        condition = str(row.get("condition") or "").replace("_", " ").casefold()
        temperature = _number(row.get("temperature") if row.get("temperature") is not None else row.get("temp_c"))
        low = _number(row.get("templow"))
        wind = _number(row.get("wind_speed") if row.get("wind_speed") is not None else row.get("wind_gust_kph") or row.get("wind_kph"))
        rain = _number(row.get("precipitation") if row.get("precipitation") is not None else row.get("rain_mm"))
        humidity = _number(row.get("humidity") if row.get("humidity") is not None else row.get("humidity_pct"))
        uv_index = _number(row.get("uv_index"))
        timing = "Now" if row.get("_current") else str(row.get("datetime") or "Forecast")
        if any(term in condition for term in ("lightning", "thunder", "temporale")):
            add("thunderstorm", "critical", "Thunderstorm / lightning", condition.title(), "Stop exposed field work; shelter people and secure equipment. Resume only after the storm has cleared.", timing)
        if "hail" in condition or "grandine" in condition:
            add("hail", "critical", "Hail risk", condition.title(), "Move people and movable equipment under cover; inspect fruit, shoots and nets after the event.", timing)
        if temperature is not None and temperature >= 34:
            add("heat", "critical" if temperature >= 40 else "warning", "Extreme heat", f"Up to {temperature:.1f}°C", "Move strenuous work to early hours, verify water, inspect exposed fruit and review irrigation need.", timing)
        if low is not None and low <= 3:
            add("frost", "critical" if low <= 0 else "warning", "Frost risk", f"Low {low:.1f}°C", "Check low parcels and frost protection; inspect young growth at first light.", timing)
        if temperature is not None and temperature <= 0:
            add("freeze", "critical", "Freezing conditions", f"{temperature:.1f}°C", "Protect people, exposed pipes and sensitive young vines; check roads and shaded surfaces for ice.", timing)
        if wind is not None and wind >= 45:
            add("wind", "critical" if wind >= 70 else "warning", "Damaging wind", f"Up to {wind:.0f} km/h", "Stop spraying and elevated work; secure doors, covers and loose equipment and inspect trellis lines.", timing)
        if rain is not None and rain >= 20:
            add("rain", "critical" if rain >= 50 else "warning", "Heavy rain / runoff", f"{rain:.1f} mm", "Check drains, access roads and erosion points; delay machinery on saturated soil.", timing)
        if any(term in condition for term in ("fog", "nebbia")):
            add("visibility", "warning", "Low visibility", condition.title(), "Use vehicle lights, reduce estate traffic and postpone machinery work where visibility is unsafe.", timing)
        if any(term in condition for term in ("snow", "ice", "sleet", "neve", "ghiaccio")):
            add("snow_ice", "critical", "Snow / ice risk", condition.title(), "Limit estate traffic, protect exposed water systems and check safe access before field work.", timing)
        if temperature is not None and temperature >= 34 and humidity is not None and humidity <= 20 and wind is not None and wind >= 25:
            add("fire_weather", "critical", "High fire-weather risk", f"{temperature:.1f}°C · humidity {humidity:.0f}% · wind {wind:.0f} km/h", "Avoid flames and spark-producing work, keep access clear and check extinguishers and water points.", timing)
        if uv_index is not None and uv_index >= 8:
            add("uv", "warning", "Very high UV", f"UV index {uv_index:.0f}", "Move exposed work away from midday and require shade, water, hats and sun protection.", timing)

    soil = _number(current.get("soil_moisture_pct"))
    current_temp = _number(current.get("temp_c"))
    if soil is not None and soil < 20 and current_temp is not None and current_temp >= 30:
        add("drought", "warning", "Dry soil and heat stress", f"Soil {soil:.0f}% · {current_temp:.1f}°C", "Inspect representative vines before changing irrigation; prioritize young vines and visibly stressed blocks.", "Now")

    order = {"critical": 2, "warning": 1, "info": 0}
    best: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if item["code"] not in best or order[item["severity"]] > order[best[item["code"]]["severity"]]:
            best[item["code"]] = item
    return sorted(best.values(), key=lambda item: (-order[item["severity"]], item["timing"], item["title"]))
