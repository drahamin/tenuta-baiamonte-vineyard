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
            raise RuntimeError("PLAATO API key was rejected") from error
        raise RuntimeError(f"PLAATO API returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise RuntimeError("PLAATO cloud is temporarily unavailable") from error


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


def _reading_history(device_id: str, key: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    rows = _request(
        f"/devices/{urllib.parse.quote(device_id, safe='')}/readings",
        key,
        {
            "temperatureUnit": "Celsius",
            "densityUnit": "Specific Gravity",
            "from": (now - timedelta(days=7)).isoformat(),
            "to": now.isoformat(),
        },
    )
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[-336:]:
        if not isinstance(row, dict):
            continue
        result.append({
            "time": _iso(row.get("time")),
            "temperature_c": _number(row.get("temperature")),
            "density_sg": _number(row.get("density")),
            "frequency_hz": _number(row.get("frequency")),
        })
    return result


def _fermentation_rate(rows: list[dict[str, Any]]) -> float | None:
    """Return gravity decrease in milli-SG/hour from recent readings."""
    valid: list[tuple[datetime, float]] = []
    for row in rows[-12:]:
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
    valid: list[tuple[datetime, float, float | None]] = []
    for row in rows:
        try:
            observed = datetime.fromisoformat(str(row.get("time") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            valid.append((observed, float(row["density_sg"]), _number(row.get("temperature_c"))))
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
    if current is not None and final_gravity is not None and rate is not None and rate >= 0.02 and current > final_gravity:
        eta_hours = round(min(24 * 60, (current - final_gravity) * 1000 / rate), 1)
        finish_at = (valid[-1][0] + timedelta(hours=eta_hours)).isoformat()
    temperatures = [item[2] for item in valid if item[2] is not None]
    span_hours = round((valid[-1][0] - valid[0][0]).total_seconds() / 3600, 1) if len(valid) > 1 else 0.0
    if len(valid) >= 12 and span_hours >= 24 and age_minutes is not None and age_minutes <= 30:
        confidence = "high"
    elif len(valid) >= 4 and span_hours >= 6 and age_minutes is not None and age_minutes <= 180:
        confidence = "medium"
    else:
        confidence = "low"
    if progress is not None and progress >= 99:
        phase = "target reached"
    elif rate is None:
        phase = "insufficient trend"
    elif rate >= 0.5:
        phase = "active fermentation"
    elif rate >= 0.05:
        phase = "slowing fermentation"
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
    return {
        "method": "Recent measured gravity slope; linear extrapolation to the PLAATO final-gravity target",
        "phase": phase,
        "progress_pct": progress,
        "rate_msg_h": rate,
        "estimated_hours_remaining": eta_hours,
        "estimated_finish_at": finish_at,
        "confidence": confidence,
        "reading_count": len(valid),
        "history_span_hours": span_hours,
        "elapsed_days": elapsed_days,
        "temperature_min_c": round(min(temperatures), 2) if temperatures else None,
        "temperature_max_c": round(max(temperatures), 2) if temperatures else None,
        "temperature_avg_c": round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
        "gravity_change": round(valid[-1][1] - valid[0][1], 4) if len(valid) > 1 else None,
        "current_abv_estimate_pct": round(max(0.0, (original_gravity - current) * 131.25), 2) if original_gravity is not None and current is not None else None,
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
        "device_name": f"PLAATO Pro Demo {index + 1}",
        "battery_pct": 82 + seed % 17,
        "wifi_pct": 68 + seed % 29,
        "firmware_version": "demo-2.0",
        "history": history,
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
                    tank_data[tank_key] = {"configured": True, "connected": False, "status": "Mapping not found in PLAATO"}
                    continue
                device_id = str((device or {}).get("id") or ((batch or {}).get("devices") or [""])[-1])
                try:
                    history = _reading_history(device_id, key) if device_id else []
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
                batch_start = _iso((batch or {}).get("start"))
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
                    "history": history[-336:],
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
        tank["source"] = "PLAATO V2 demo" if reading.get("demo") else "PLAATO V2 Pro"
        tank["reading_at"] = reading.get("reading_at") or tank.get("reading_at")
        if reading.get("temperature_c") is not None:
            tank["temp_c"] = reading["temperature_c"]
        if reading.get("density_sg") is not None:
            tank["density_sg"] = reading["density_sg"]
        # PLAATO batch volume is contextual metadata, not a continuous tank-level measurement.
        tank["sensor_issues"] = [] if reading.get("connected") else [reading.get("status") or "PLAATO unavailable"]
