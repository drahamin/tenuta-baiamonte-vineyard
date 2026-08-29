"""Read-only PLAATO V2 Pro fermentation monitoring.

PLAATO remains the authority for its sensor and batch telemetry.  This module
normalizes that data for cellar screens without making cellar-control changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from threading import Lock
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from ..config import Settings, runtime_option


PLAATO_API_ORIGIN = "https://api.plaato.cloud"
PLAATO_DEMO_KEY = "demo"
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_LOCK = Lock()


def plaato_api_key(settings: Settings) -> str:
    return str(runtime_option("plaato_api_key", settings.plaato_api_key) or "").strip()


def plaato_demo_enabled(settings: Settings) -> bool:
    """Return true for the documented local-only demo credential."""
    return plaato_api_key(settings).casefold() == PLAATO_DEMO_KEY


def plaato_mapping(settings: Settings) -> dict[str, str]:
    """Return tank-code/name to PLAATO batch/device/fermenter identifier."""
    raw = str(runtime_option("plaato_tank_mappings", settings.plaato_tank_mappings) or "")
    result: dict[str, str] = {}
    for definition in (part.strip() for part in raw.split(",") if part.strip()):
        parts = [part.strip() for part in definition.split("|", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            result[parts[0].casefold()] = parts[1]
    return result


def plaato_tank_keys(settings: Settings) -> set[str]:
    if plaato_demo_enabled(settings):
        return {"*"}
    return set(plaato_mapping(settings)) if plaato_api_key(settings) else set()


def _request(path: str, key: str, query: dict[str, str] | None = None) -> Any:
    suffix = "?" + urllib.parse.urlencode(query) if query else ""
    request = urllib.request.Request(
        PLAATO_API_ORIGIN + path + suffix,
        headers={
            "x-plaato-api-key": key,
            "Accept": "application/json",
            "User-Agent": "Tenuta-Baiamonte-PLAATO-V2/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError("Tank Sensor API key was rejected") from error
        raise RuntimeError(f"Tank Sensor API returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise RuntimeError("Tank Sensor cloud is temporarily unavailable") from error


def _iso(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_value(batch: dict[str, Any], key: str, nested: str) -> float | None:
    return _number(((batch.get("latestReading") or {}).get(key) or {}).get(nested))


def _reading_history(device_id: str, key: str, batch_start: str | None = None) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    history_from = now - timedelta(days=90)
    try:
        started = datetime.fromisoformat(str(batch_start).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        history_from = max(history_from, started)
    except (TypeError, ValueError):
        pass
    rows = _request(
        f"/devices/{urllib.parse.quote(device_id, safe='')}/readings",
        key,
        {
            "temperatureUnit": "Celsius",
            "densityUnit": "Specific Gravity",
            "from": history_from.isoformat(),
            "to": now.isoformat(),
        },
    )
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[-4320:]:
        if not isinstance(row, dict):
            continue
        result.append({
            "time": _iso(row.get("time")),
            "temperature_c": _number(row.get("temperature")),
            "density_sg": _number(row.get("density")),
            "frequency_hz": _number(row.get("frequency")),
            "activity_msg_h_sensor": _activity_value(row),
        })
    return _enrich_activity(result)


def _display_history(rows: list[dict[str, Any]], limit: int = 720) -> list[dict[str, Any]]:
    """Keep a representative full-batch curve without overloading HA/mobile clients."""
    if len(rows) <= limit:
        return rows
    indexes = {round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)}
    return [row for index, row in enumerate(rows) if index in indexes]


def _activity_value(row: dict[str, Any]) -> float | None:
    """Normalize an activity value when the API includes PLAATO's mSG/hour field."""
    for value in (
        row.get("fermentationActivity"),
        row.get("fermentation_activity"),
        row.get("activity"),
        row.get("activityMsgPerHour"),
        (row.get("fermentation") or {}).get("activity") if isinstance(row.get("fermentation"), dict) else None,
    ):
        if isinstance(value, dict):
            value = value.get("milliSpecificGravityPerHour") or value.get("mSGPerHour") or value.get("value")
        number = _number(value)
        if number is not None:
            return round(max(0.0, number), 3)
    return None


def _rate_between(rows: list[dict[str, Any]]) -> float | None:
    valid: list[tuple[datetime, float]] = []
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row.get("time") or "").replace("Z", "+00:00"))
            density = float(row["density_sg"])
            valid.append((observed, density))
        except (KeyError, TypeError, ValueError):
            continue
    if len(valid) < 2:
        return None
    elapsed = (valid[-1][0] - valid[0][0]).total_seconds() / 3600
    if elapsed <= 0:
        return None
    return round(max(0.0, (valid[0][1] - valid[-1][1]) * 1000 / elapsed), 3)


def _enrich_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach PLAATO activity or a clearly identified rolling density-slope equivalent."""
    enriched: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        row = dict(raw)
        sensor_activity = _number(row.get("activity_msg_h_sensor"))
        calculated = _rate_between(rows[max(0, index - 5):index + 1])
        row["fermentation_rate_msg_h"] = round(sensor_activity, 3) if sensor_activity is not None else calculated
        row["activity_source"] = "sensor" if sensor_activity is not None else ("density slope" if calculated is not None else None)
        enriched.append(row)
    return enriched


def _fermentation_rate(rows: list[dict[str, Any]]) -> float | None:
    """Return gravity decrease in milli-SG/hour from recent readings."""
    if rows:
        direct = _number(rows[-1].get("fermentation_rate_msg_h"))
        if direct is not None:
            return round(max(0.0, direct), 3)
    return _rate_between(rows[-12:])


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _fermentation_projection(
    rows: list[dict[str, Any]],
    original_gravity: float | None,
    final_gravity: float | None,
    batch_start: str | None,
    age_minutes: float | None,
) -> dict[str, Any]:
    """Build a transparent short-range projection from measured gravity slope.

    This is intentionally descriptive, not a cellar-control recommendation.  An
    ETA is only produced when PLAATO supplies a final-gravity target.
    """
    rows = _enrich_activity(rows)
    valid: list[tuple[datetime, float, float | None, float | None]] = []
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row.get("time") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            valid.append((observed, float(row["density_sg"]), _number(row.get("temperature_c")), _number(row.get("fermentation_rate_msg_h"))))
        except (KeyError, TypeError, ValueError):
            continue
    valid.sort(key=lambda item: item[0])
    current = valid[-1][1] if valid else None
    rate = _fermentation_rate(rows)
    progress = None
    if original_gravity is not None and final_gravity is not None and current is not None and original_gravity > final_gravity:
        progress = round(max(0.0, min(100.0, (original_gravity - current) / (original_gravity - final_gravity) * 100)), 1)
    eta_hours = None
    finish_at = None
    finish_early_at = None
    finish_late_at = None
    if current is not None and final_gravity is not None and rate is not None and rate >= 0.02 and current > final_gravity:
        eta_hours = round(min(24 * 60, (current - final_gravity) * 1000 / rate), 1)
        finish_at = (valid[-1][0] + timedelta(hours=eta_hours)).isoformat()
        recent_rates = [item[3] for item in valid[-48:] if item[3] is not None and item[3] >= 0.02]
        fast_rate = _percentile(recent_rates, .75) or rate * 1.35
        slow_rate = _percentile(recent_rates, .25) or rate * .65
        if fast_rate and slow_rate:
            remaining_msg = (current - final_gravity) * 1000
            early_hours = min(24 * 60, remaining_msg / max(fast_rate, .02))
            late_hours = min(24 * 60, remaining_msg / max(slow_rate, .02))
            finish_early_at = (valid[-1][0] + timedelta(hours=early_hours)).isoformat()
            finish_late_at = (valid[-1][0] + timedelta(hours=late_hours)).isoformat()
    temperatures = [item[2] for item in valid if item[2] is not None]
    span_hours = round((valid[-1][0] - valid[0][0]).total_seconds() / 3600, 1) if len(valid) > 1 else 0.0
    if len(valid) >= 12 and span_hours >= 24 and age_minutes is not None and age_minutes <= 30:
        confidence = "high"
    elif len(valid) >= 4 and span_hours >= 6 and age_minutes is not None and age_minutes <= 180:
        confidence = "medium"
    else:
        confidence = "low"
    peak = max((item for item in valid if item[3] is not None), key=lambda item: item[3], default=None)
    peak_rate = peak[3] if peak else None
    recent_rate = sum(item[3] for item in valid[-12:] if item[3] is not None) / max(1, sum(1 for item in valid[-12:] if item[3] is not None))
    previous_rates = [item[3] for item in valid[-24:-12] if item[3] is not None]
    previous_rate = sum(previous_rates) / len(previous_rates) if previous_rates else None
    pace = "steady"
    if previous_rate is not None and recent_rate > previous_rate * 1.2:
        pace = "accelerating"
    elif previous_rate is not None and recent_rate < previous_rate * .65:
        pace = "slowing"
    stable_hours = 0.0
    if valid:
        latest_density = valid[-1][1]
        stable_start = valid[-1][0]
        # PLAATO documents ±0.002 SG sensor accuracy; variation inside that band
        # is reported as apparent stability, not proof of completion.
        for item in reversed(valid[:-1]):
            if abs(item[1] - latest_density) > .002:
                break
            stable_start = item[0]
        stable_hours = round(max(0.0, (valid[-1][0] - stable_start).total_seconds() / 3600), 1)
    if progress is not None and progress >= 99 and stable_hours >= 24:
        phase = "target reached"
    elif rate is None:
        phase = "insufficient trend"
    elif valid and (valid[-1][0] - valid[0][0]).total_seconds() <= 12 * 3600 and rate < .05:
        phase = "lag / settling"
    elif rate >= 0.5:
        phase = "active fermentation" if pace == "steady" else f"active · {pace}"
    elif rate >= 0.05:
        phase = "slowing fermentation"
    elif stable_hours >= 24:
        phase = "stable for review"
    else:
        phase = "stable / near dry"
    elapsed_days = None
    try:
        started = datetime.fromisoformat(str(batch_start).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if valid:
            elapsed_days = round(max(0.0, (valid[-1][0] - started).total_seconds() / 86400), 1)
    except (TypeError, ValueError):
        pass
    events: list[dict[str, Any]] = []
    if batch_start:
        events.append({"time": batch_start, "kind": "batch", "label": "Batch started", "detail": "PLAATO batch metadata"})
    if valid:
        events.append({"time": valid[0][0].isoformat(), "kind": "measurement", "label": "Monitoring window begins", "detail": f"{valid[0][1]:.4f} SG"})
    active = next((item for item in valid if item[3] is not None and item[3] >= .05), None)
    if active:
        events.append({"time": active[0].isoformat(), "kind": "activity", "label": "Activity detected", "detail": f"{active[3]:.3f} mSG/h"})
    if peak:
        events.append({"time": peak[0].isoformat(), "kind": "peak", "label": "Peak measured activity", "detail": f"{peak[3]:.3f} mSG/h"})
    if stable_hours >= 6 and valid:
        events.append({"time": (valid[-1][0] - timedelta(hours=stable_hours)).isoformat(), "kind": "stable", "label": "Apparent stability begins", "detail": f"Inside ±0.002 SG for {stable_hours:g} h"})
    if finish_at:
        events.append({"time": finish_at, "kind": "projection", "label": "Projected target gravity", "detail": f"Calculated from recent measured activity · {confidence} confidence"})
    events.sort(key=lambda item: str(item.get("time") or ""))
    guidance = []
    if phase.startswith("lag"):
        guidance.append("Watch for a sustained must-density decline; a long lag needs enologist review.")
    elif phase.startswith("active"):
        guidance.append("Alcoholic fermentation is active; follow temperature, density and cap-management observations together.")
    elif "slowing" in phase:
        guidance.append("Activity is slowing; schedule a reference density/lab check and review pressing or racking readiness for this wine protocol.")
    elif "stable" in phase or phase == "target reached":
        guidance.append("Confirm dryness and stability with the enologist and a reference sample before declaring alcoholic fermentation complete.")
    if stable_hours >= 24:
        guidance.append("Gravity has remained inside the sensor accuracy band for at least 24 hours.")
    if temperatures and max(temperatures) - min(temperatures) >= 3:
        guidance.append("The measured temperature span exceeds 3°C; review the tank temperature history.")
    guidance.append("PLAATO density/activity does not confirm malolactic fermentation; use laboratory malic/lactic results for MLF decisions.")
    return {
        "method": "Recent measured gravity slope; linear extrapolation to the Tank Sensor final-gravity target",
        "phase": phase,
        "progress_pct": progress,
        "rate_msg_h": rate,
        "estimated_hours_remaining": eta_hours,
        "estimated_finish_at": finish_at,
        "estimated_finish_early_at": finish_early_at,
        "estimated_finish_late_at": finish_late_at,
        "confidence": confidence,
        "reading_count": len(valid),
        "history_span_hours": span_hours,
        "elapsed_days": elapsed_days,
        "temperature_min_c": round(min(temperatures), 2) if temperatures else None,
        "temperature_max_c": round(max(temperatures), 2) if temperatures else None,
        "temperature_avg_c": round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
        "gravity_change": round(valid[-1][1] - valid[0][1], 4) if len(valid) > 1 else None,
        "current_abv_estimate_pct": round(max(0.0, (original_gravity - current) * 131.25), 2) if original_gravity is not None and current is not None else None,
        "peak_activity_msg_h": round(peak_rate, 3) if peak_rate is not None else None,
        "peak_activity_at": peak[0].isoformat() if peak else None,
        "recent_activity_msg_h": round(recent_rate, 3) if rate is not None else None,
        "pace": pace,
        "stable_hours": stable_hours,
        "completion_review_ready": bool(progress is not None and progress >= 99 and stable_hours >= 24),
        "events": events,
        "guidance": guidance,
    }


def _age_minutes(value: str | None) -> float | None:
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - observed).total_seconds() / 60)
    except (TypeError, ValueError):
        return None


def _demo_reading(tank: dict[str, Any], index: int, now: datetime | None = None) -> dict[str, Any]:
    """Return a realistic, moving PLAATO-shaped stream without network access."""
    now = now or datetime.now(timezone.utc)
    identity = str(tank.get("code") or tank.get("name") or index)
    seed = sum(ord(character) for character in identity) + index * 17
    original_gravity = round(1.082 + (seed % 13) / 1000, 3)
    final_gravity = round(0.994 + (seed % 4) / 1000, 3)
    elapsed_days = 3.5 + (seed % 7) * 0.55
    progress = min(0.91, 0.24 + (seed % 58) / 100)
    batch_start_dt = now - timedelta(days=elapsed_days)
    history_start = max(batch_start_dt, now - timedelta(days=7))
    sample_count = max(2, min(337, int((now - history_start).total_seconds() / 1800) + 1))
    history: list[dict[str, Any]] = []
    start_progress = max(0.015, progress - min(0.48, elapsed_days * 0.075))
    base_temp = 20.2 + (seed % 25) / 10
    for sample in range(sample_count):
        fraction = sample / max(1, sample_count - 1)
        # Smooth decay with a mild slowdown near the current reading.
        sample_progress = start_progress + (progress - start_progress) * (1 - (1 - fraction) ** 1.35)
        density = original_gravity - (original_gravity - final_gravity) * sample_progress
        temperature = base_temp + 0.7 * math.sin((sample + seed) / 13) + 0.18 * math.sin((sample + seed) / 3.7)
        observed = history_start + (now - history_start) * fraction
        history.append({
            "time": observed.isoformat(),
            "temperature_c": round(temperature, 2),
            "density_sg": round(density, 4),
            "frequency_hz": round(1090 + (density - 1) * 900 + math.sin(sample / 9) * 2.5, 2),
        })
    history = _enrich_activity(history)
    latest = history[-1]
    current_abv = round(max(0.0, (original_gravity - latest["density_sg"]) * 131.25), 2)
    age = round((seed % 5) + 0.4, 1)
    batch_start = batch_start_dt.isoformat()
    return {
        "demo": True,
        "configured": True,
        "connected": True,
        "status": "demo live",
        "reading_at": latest["time"],
        "age_minutes": age,
        "temperature_c": latest["temperature_c"],
        "density_sg": latest["density_sg"],
        "plato": round(max(0.0, 259 - 259 / latest["density_sg"]), 2),
        "frequency_hz": latest["frequency_hz"],
        "fermentation_rate_msg_h": _fermentation_rate(history),
        "activity_source": latest.get("activity_source"),
        "original_gravity": original_gravity,
        "final_gravity": final_gravity,
        "abv_pct": current_abv,
        "attenuation_pct": round(progress * 100, 1),
        "batch_volume": _number(tank.get("volume_l")),
        "batch_id": f"demo-batch-{index + 1}",
        "batch_name": f"{tank.get('variety_summary') or tank.get('lot_name') or 'Estate wine'} · simulated",
        "batch_start": batch_start,
        "batch_end": None,
        "batch_enabled": True,
        "batch_auto_management": True,
        "fermenter_id": f"demo-fermenter-{index + 1}",
        "fermenter_name": tank.get("name") or tank.get("code") or f"Demo fermenter {index + 1}",
        "device_id": f"demo-pro-{index + 1}",
        "device_name": f"Tank Sensor Demo {index + 1}",
        "battery_pct": 82 + seed % 17,
        "wifi_pct": 68 + seed % 29,
        "firmware_version": "demo-2.0",
        "history": history,
        "history_sample_count": len(history),
        "history_downsampled": False,
        "projection": _fermentation_projection(history, original_gravity, final_gravity, batch_start, age),
    }


def fetch_plaato_snapshot(settings: Settings, *, force: bool = False) -> dict[str, Any]:
    key = plaato_api_key(settings)
    mappings = plaato_mapping(settings)
    if not key:
        return {"configured": False, "connected": False, "status": "API key required", "tanks": {}}
    if key.casefold() == PLAATO_DEMO_KEY:
        return {
            "demo": True,
            "configured": True,
            "connected": True,
            "status": "Demo simulation",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "device_count": 0,
            "batch_count": 0,
            "fermenter_count": 0,
            "mapped_tank_count": 0,
            "tanks": {},
        }
    ttl = max(60, int(runtime_option("plaato_sync_minutes", settings.plaato_sync_minutes) or 5) * 60)
    cache_key = (key, tuple(sorted(mappings.items())), ttl)
    with _LOCK:
        if not force and _CACHE.get("key") == cache_key and _CACHE.get("payload") is not None and time.monotonic() - float(_CACHE.get("at") or 0) < ttl:
            return _CACHE["payload"]
        try:
            batches = _request("/batches", key)
            devices = _request("/devices", key)
            fermenters = _request("/fermenters", key)
            batches = batches if isinstance(batches, list) else []
            devices = devices if isinstance(devices, list) else []
            fermenters = fermenters if isinstance(fermenters, list) else []
            device_by_id = {str(row.get("id")): row for row in devices if isinstance(row, dict) and row.get("id")}
            batch_by_id = {str(row.get("id")): row for row in batches if isinstance(row, dict) and row.get("id")}
            fermenter_by_id = {str(row.get("id")): row for row in fermenters if isinstance(row, dict) and row.get("id")}
            by_identifier: dict[str, tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]] = {}
            for batch in batches:
                batch_devices = [str(value) for value in batch.get("devices") or []]
                device = device_by_id.get(batch_devices[-1]) if batch_devices else None
                fermenter = fermenter_by_id.get(str(batch.get("fermenterId") or ""))
                for value in (batch.get("id"), batch.get("name"), *(batch_devices or []), (fermenter or {}).get("id"), (fermenter or {}).get("name")):
                    if value:
                        by_identifier[str(value).casefold()] = (batch, device, fermenter)
            for device in devices:
                for value in (device.get("id"), device.get("name"), device.get("barcode")):
                    if value and str(value).casefold() not in by_identifier:
                        by_identifier[str(value).casefold()] = (None, device, None)
            tank_data: dict[str, Any] = {}
            for tank_key, identifier in mappings.items():
                batch, device, fermenter = by_identifier.get(identifier.casefold(), (None, None, None))
                if not batch and not device and not fermenter:
                    tank_data[tank_key] = {"configured": True, "connected": False, "status": "Tank Sensor mapping not found"}
                    continue
                device_id = str((device or {}).get("id") or ((batch or {}).get("devices") or [""])[-1])
                batch_start = _iso((batch or {}).get("start"))
                try:
                    history = _reading_history(device_id, key, batch_start) if device_id else []
                except RuntimeError:
                    history = []
                last_history = history[-1] if history else {}
                observed_at = _iso(last_history.get("time") or ((batch or {}).get("latestReading") or {}).get("time") or (device or {}).get("lastOnline"))
                age = _age_minutes(observed_at)
                density = _number(last_history.get("density_sg"))
                if density is None and batch:
                    density = _latest_value(batch, "density", "specificGravity")
                temperature = _number(last_history.get("temperature_c"))
                if temperature is None and batch:
                    temperature = _latest_value(batch, "temperature", "celsius")
                original_gravity = _number((batch or {}).get("OG"))
                final_gravity = _number((batch or {}).get("FG"))
                display_history = _display_history(history)
                tank_data[tank_key] = {
                    "configured": True,
                    "connected": age is not None and age <= max(180, ttl / 60 * 3),
                    "status": "live" if age is not None and age <= max(180, ttl / 60 * 3) else "stale",
                    "reading_at": observed_at,
                    "age_minutes": round(age, 1) if age is not None else None,
                    "temperature_c": temperature,
                    "density_sg": density,
                    "plato": _latest_value(batch, "density", "plato") if batch else None,
                    "frequency_hz": _number(last_history.get("frequency_hz")),
                    "fermentation_rate_msg_h": _fermentation_rate(history),
                    "activity_source": last_history.get("activity_source"),
                    "original_gravity": original_gravity,
                    "final_gravity": final_gravity,
                    "abv_pct": _number((batch or {}).get("ABV")),
                    "attenuation_pct": _number((batch or {}).get("attenuation")),
                    "batch_volume": _number((batch or {}).get("volume")),
                    "batch_id": (batch or {}).get("id"),
                    "batch_name": (batch or {}).get("name"),
                    "batch_start": batch_start,
                    "batch_end": _iso((batch or {}).get("end")),
                    "batch_enabled": (batch or {}).get("enabled"),
                    "batch_auto_management": (batch or {}).get("autoManagement"),
                    "fermenter_id": (fermenter or {}).get("id"),
                    "fermenter_name": (fermenter or {}).get("name"),
                    "device_id": (device or {}).get("id"),
                    "device_name": (device or {}).get("name"),
                    "battery_pct": _number((device or {}).get("batteryLevel")),
                    "wifi_pct": _number((device or {}).get("wifiStrength")),
                    "firmware_version": (device or {}).get("firmwareVersion"),
                    "history": display_history,
                    "history_sample_count": len(history),
                    "history_downsampled": len(display_history) < len(history),
                    "projection": _fermentation_projection(history, original_gravity, final_gravity, batch_start, age),
                }
            payload = {
                "configured": True,
                "connected": True,
                "status": "Connected",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "device_count": len(devices),
                "batch_count": len(batches),
                "fermenter_count": len(fermenters),
                "mapped_tank_count": len(mappings),
                "tanks": tank_data,
            }
        except RuntimeError as error:
            payload = {"configured": True, "connected": False, "status": str(error), "tanks": {}}
        _CACHE.update({"key": cache_key, "at": time.monotonic(), "payload": payload})
        return payload


def apply_plaato_readings(tanks: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    by_key = {
        str(value).strip().casefold(): tank
        for tank in tanks
        for value in (tank.get("code"), tank.get("name"))
        if value
    }
    readings = dict(snapshot.get("tanks") or {})
    if snapshot.get("demo"):
        readings = {
            str(tank.get("code") or tank.get("name") or index).strip().casefold(): _demo_reading(tank, index)
            for index, tank in enumerate(tanks)
        }
    for key, reading in readings.items():
        tank = by_key.get(str(key).casefold())
        if not tank:
            continue
        tank["plaato"] = reading
        tank["sensor_status"] = reading.get("status") or "fault"
        tank["source"] = "Tank Sensor demo" if reading.get("demo") else "Tank Sensor"
        tank["reading_at"] = reading.get("reading_at") or tank.get("reading_at")
        if reading.get("temperature_c") is not None:
            tank["temp_c"] = reading["temperature_c"]
        if reading.get("density_sg") is not None:
            tank["density_sg"] = reading["density_sg"]
        # PLAATO batch volume is contextual metadata, not a continuous tank-level measurement.
        tank["sensor_issues"] = [] if reading.get("connected") else [reading.get("status") or "Tank Sensor unavailable"]
