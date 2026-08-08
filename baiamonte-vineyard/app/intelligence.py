from __future__ import annotations

import base64
import asyncio
import hashlib
import imaplib
import json
import mimetypes
import os
import re
import smtplib
import time
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .config import get_settings, runtime_option
from .cellar_demo import apply_live_sensor_readings, cellar_guardrails, demo_cellar, demo_enabled, evaluate_cellar_tanks, live_sensor_entity_ids
from .db import fetch_all, fetch_one, transaction
from .ha_auth import home_assistant_token
from .etna import refresh_etna
from .ha_entities import DEFAULT_GW2000_ENTITIES, resolve_gw2000_entities
from .fattureincloud import pull_fattureincloud
from .publisher import publish_once
from .service import estate_id, json_ready, new_id


INTAKE_ROOT = Path(os.environ.get("INTAKE_ROOT", "/data/intake"))
GW2000_ENTITIES = DEFAULT_GW2000_ENTITIES
PLANNING_ENTITIES = {
    "cover.sonoff_1001f2446e",
    "sensor.sonoff_1001f2446e_voltage_1",
    "sensor.sonoff_1001f2446e_current_1",
    "sensor.sonoff_1001f2446e_power_1",
    "sensor.sonoff_1001f2446e_energy_1",
    "sensor.total_solar_input_dc_kwh",
    "sensor.generator_main_breaker_phase_a_power",
    "sensor.generator_main_breaker_total_energy",
}


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def risk_level(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 35:
        return "moderate"
    return "low"


def _ha_get(path: str) -> Any:
    token = home_assistant_token()
    if not token:
        return None
    error: Exception | None = None
    for base in ("http://supervisor/core/api", "http://homeassistant:8123/api", "http://core-homeassistant:8123/api"):
        try:
            request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except Exception as current_error:
            error = current_error
    if error:
        raise error
    return None


def _ha_post(path: str, payload: dict[str, Any]) -> Any:
    token = home_assistant_token()
    if not token:
        return None
    request = urllib.request.Request("http://supervisor/core/api" + path, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"[]")


def latest_cistern_level() -> dict[str, Any]:
    settings = get_settings()
    try:
        row = fetch_one(
            "SELECT observed_at,level_percent,confidence,source,camera_entity_id,model,notes FROM cistern_level_estimates WHERE estate_id=%s ORDER BY observed_at DESC,id DESC LIMIT 1",
            (estate_id(),),
        ) or {}
    except Exception:
        row = {}
    if not row:
        row = {
            "observed_at": None,
            "level_percent": max(0.0, min(100.0, float(settings.cistern_level_initial_percent))),
            "confidence": 0.35,
            "source": "initial_camera_estimate",
            "camera_entity_id": settings.cistern_camera_entity,
            "model": None,
            "notes": "Initial visual estimate; the cistern appeared nearly empty.",
        }
    return json_ready({**row, "estimated": True, "label": "Camera estimate"})


def _publish_cistern_level(level: dict[str, Any]) -> None:
    percent = round(max(0.0, min(100.0, float(level.get("level_percent") or 0))), 1)
    _ha_post("/states/sensor.baiamonte_cistern_water_level", {"state": percent, "attributes": {
        "friendly_name": "Baiamonte Cistern Water Level", "unit_of_measurement": "%", "state_class": "measurement",
        "icon": "mdi:storage-tank", "source": level.get("source") or "camera_estimate", "estimate": True,
        "confidence": level.get("confidence"), "observed_at": level.get("observed_at"), "notes": level.get("notes"),
    }})
    _ha_post("/states/binary_sensor.baiamonte_cistern_low_water", {
        "state": "on" if percent < 10 else "off",
        "attributes": {"friendly_name": "Baiamonte Cistern Low Water", "device_class": "problem", "level_percent": percent, "threshold_percent": 10, "estimate": True},
    })


def _cistern_camera_light(settings: Any) -> tuple[str | None, bool]:
    """Turn on a matching camera light and return whether it must be restored."""
    states = _ha_get("/states") or []
    configured = str(settings.cistern_camera_light_entity or "").strip()
    state_by_id = {str(item.get("entity_id") or ""): item for item in states}
    entity_id = configured if configured in state_by_id else None
    if not entity_id and not configured:
        camera_key = str(settings.cistern_camera_entity or "").split(".", 1)[-1].casefold()
        for item in states:
            candidate = str(item.get("entity_id") or "")
            if not candidate.startswith(("light.", "switch.")):
                continue
            name = str((item.get("attributes") or {}).get("friendly_name") or "")
            haystack = f"{candidate} {name}".casefold().replace("-", "_").replace(" ", "_")
            camera_match = camera_key and camera_key in haystack
            cistern_match = any(term in haystack for term in ("cistern", "cisterna", "tank"))
            light_match = any(term in haystack for term in ("light", "led", "lamp", "spotlight", "illuminator"))
            if light_match and (camera_match or cistern_match):
                entity_id = candidate
                break
    if not entity_id:
        return None, False
    was_on = str(state_by_id[entity_id].get("state") or "").lower() == "on"
    if not was_on:
        domain = entity_id.split(".", 1)[0]
        _ha_post(f"/services/{domain}/turn_on", {"entity_id": entity_id})
        time.sleep(2.5)
    return entity_id, not was_on


def _restore_cistern_camera_light(entity_id: str | None, restore_off: bool) -> None:
    if not entity_id or not restore_off:
        return
    domain = entity_id.split(".", 1)[0]
    try:
        _ha_post(f"/services/{domain}/turn_off", {"entity_id": entity_id})
    except Exception:
        pass


def refresh_cistern_level() -> dict[str, Any]:
    """Estimate cistern level from one private HA camera still per full refresh."""
    settings = get_settings()
    previous = latest_cistern_level()
    # Publish the last accepted value first so dashboards remain useful even if
    # this refresh cannot obtain or analyze a new frame.
    _publish_cistern_level(previous)
    if not settings.cistern_level_ai_enabled or not settings.openai_api_key:
        return {"updated": False, "reason": "AI disabled or API key unavailable", "level": previous}
    token = home_assistant_token()
    if not token:
        return {"updated": False, "reason": "Home Assistant access unavailable", "level": previous}
    entity_id = str(settings.cistern_camera_entity or "camera.192_168_0_54").strip()
    light_entity, restore_light = _cistern_camera_light(settings)
    try:
        request = urllib.request.Request(
            "http://supervisor/core/api/camera_proxy/" + urllib.parse.quote(entity_id, safe="."),
            headers={"Authorization": f"Bearer {token}", "Accept": "image/jpeg,image/png"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            image = response.read(8 * 1024 * 1024)
            mime = str(response.headers.get_content_type() or "image/jpeg")
    finally:
        _restore_cistern_camera_light(light_entity, restore_light)
    if not image:
        raise ValueError("Cistern camera returned an empty image")
    prior = float(previous.get("level_percent") or settings.cistern_level_initial_percent)
    prompt = (
        "Estimate the percentage of water remaining in this fixed cistern camera image. The last accepted estimate is "
        f"{prior:.1f} percent and the tank was initially confirmed nearly empty. Return JSON only with usable (boolean), "
        "level_percent (0-100), confidence (0-1), visible_waterline (boolean), and notes (one short sentence). This is an "
        "uncalibrated visual estimate, not an instrument reading. Keep the prior value unless the water surface or waterline "
        "provides clear evidence of change; do not infer a change from darkness, glare, condensation, or reflections alone."
    )
    encoded = base64.b64encode(image).decode()
    body = json.dumps({"model": settings.openai_model, "input": [{"role": "user", "content": [
        {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"},
    ]}], "text": {"format": {"type": "json_object"}}}).encode()
    ai_request = urllib.request.Request("https://api.openai.com/v1/responses", data=body, headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(ai_request, timeout=90) as response:
        parsed = json.loads(_response_text(json.loads(response.read())) or "{}")
    if not parsed.get("usable"):
        _publish_cistern_level(previous)
        return {"updated": False, "reason": "Camera frame unsuitable", "level": previous, "analysis": parsed}
    percent = max(0.0, min(100.0, float(parsed.get("level_percent"))))
    confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0)))
    if confidence < 0.35:
        _publish_cistern_level(previous)
        return {"updated": False, "reason": "Camera estimate confidence too low", "level": previous, "analysis": parsed}
    if abs(percent - prior) > 20 and (confidence < 0.75 or not parsed.get("visible_waterline")):
        _publish_cistern_level(previous)
        return {"updated": False, "reason": "Large change was not visually confirmed", "level": previous, "analysis": parsed}
    observed_at, notes = datetime.now(), str(parsed.get("notes") or "AI camera estimate")[:1000]
    parsed["illumination_entity"] = light_entity
    parsed["illumination_used"] = bool(light_entity)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cistern_level_estimates (id,estate_id,observed_at,level_percent,confidence,source,camera_entity_id,model,notes,image_sha256,metadata) VALUES (%s,%s,%s,%s,%s,'camera_ai',%s,%s,%s,%s,%s)",
            (new_id(), estate_id(), observed_at, percent, confidence, entity_id, settings.openai_model, notes, hashlib.sha256(image).hexdigest(), json.dumps(json_ready(parsed))),
        )
    level = {"observed_at": observed_at, "level_percent": round(percent, 1), "confidence": round(confidence, 2), "source": "camera_ai", "camera_entity_id": entity_id, "model": settings.openai_model, "notes": notes, "estimated": True, "label": "Camera estimate"}
    _publish_cistern_level(level)
    return {"updated": True, "level": json_ready(level)}


def home_assistant_state_map(entity_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Read a selected set of Home Assistant states in one request."""
    if not entity_ids:
        return {}
    states = _ha_get("/states") or []
    return {item.get("entity_id"): item for item in states if item.get("entity_id") in entity_ids}


def _traffic_origin(value: str) -> str:
    parts = urllib.parse.urlsplit(str(value or "").strip())
    if parts.scheme and parts.netloc:
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
    return str(value or "").split("?", 1)[0].split("#", 1)[0].removesuffix("/tv").rstrip("/")


def publish_home_assistant_traffic_sensors() -> dict[str, Any]:
    """Keep the Overview's ten-nearest aircraft and vessel sensors current."""
    settings = get_settings()
    sources = {
        "aircraft": _traffic_origin(runtime_option("tv_adsb_url", settings.tv_adsb_url)),
        "vessels": _traffic_origin(runtime_option("tv_ais_url", settings.tv_ais_url)),
    }
    results: dict[str, Any] = {}
    for kind, origin in sources.items():
        entity_id = f"sensor.baiamonte_{kind}"
        try:
            request = urllib.request.Request(origin + "/api/status", headers={"Accept": "application/json", "User-Agent": "Baiamonte-Vineyard-HA-Bridge/1.0"})
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read(2 * 1024 * 1024))
            if kind == "aircraft":
                rows = sorted(payload.get("aircraft") or [], key=lambda row: float(row.get("distance_km") or 1e9))[:10]
                count = int((payload.get("counts") or {}).get("aircraft") or len(payload.get("aircraft") or []))
                attributes = {"nearest_aircraft": rows, "positioned": int((payload.get("counts") or {}).get("positioned") or len(rows)), "receiver_ready": bool((payload.get("receiver") or {}).get("ready")), "friendly_name": "Baiamonte Aircraft", "icon": "mdi:airplane"}
            else:
                rows = sorted(payload.get("nearest_vessels") or payload.get("vessels") or [], key=lambda row: float(row.get("distance_km") or 1e9))[:10]
                count = len(payload.get("vessels") or [])
                attributes = {"nearest_vessels": rows, "connection": payload.get("connection") or payload.get("service_status"), "last_error": payload.get("last_error"), "friendly_name": "Baiamonte Vessels", "icon": "mdi:ferry"}
            attributes["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            _ha_post(f"/states/{entity_id}", {"state": count, "attributes": attributes})
            results[kind] = {"count": count, "nearest": len(rows), "status": attributes.get("connection") or attributes.get("receiver_ready")}
        except Exception as error:
            results[kind] = {"error": str(error)[:240]}
    return results


def alert_preference(alert_type: str) -> dict[str, Any]:
    return fetch_one(
        "SELECT * FROM alert_preferences WHERE estate_id=%s AND alert_type=%s",
        (estate_id(), alert_type),
    ) or {
        "alert_type": alert_type, "enabled": 1, "min_severity": "warning",
        "notify_home_assistant": 1, "notify_email": 0, "notify_whatsapp": 0,
        "email_recipients": "", "whatsapp_recipients": "",
    }


def send_alert_notifications(alert_type: str, severity: str, title: str, message: str) -> dict[str, str]:
    """Send only user-enabled alert channels; database alerts remain the audit source."""
    preference = alert_preference(alert_type)
    order = {"info": 0, "warning": 1, "critical": 2}
    if not preference.get("enabled") or order.get(severity, 0) < order.get(str(preference.get("min_severity") or "warning"), 1):
        return {"status": "filtered"}
    settings = get_settings()
    results: dict[str, str] = {}
    if preference.get("notify_home_assistant") and settings.ha_notifications_enabled and home_assistant_token():
        try:
            service = settings.ha_notify_service.strip("/")
            _ha_post("/services/" + service, {"title": title, "message": message})
            results["home_assistant"] = "sent"
        except Exception as error:
            results["home_assistant"] = f"error: {error}"
    email_recipients = [value.strip() for value in str(preference.get("email_recipients") or "").split(",") if value.strip()]
    if preference.get("notify_email") and email_recipients:
        if not settings.gmail_address or not settings.gmail_app_password:
            results["email"] = "not configured"
        else:
            try:
                email = EmailMessage()
                email["Subject"] = title
                email["From"] = settings.gmail_address
                email["To"] = ", ".join(email_recipients)
                email.set_content(message + "\n\nTenuta Baiamonte Vineyard Operations")
                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
                    smtp.login(settings.gmail_address, settings.gmail_app_password)
                    smtp.send_message(email)
                results["email"] = "sent"
            except Exception as error:
                results["email"] = f"error: {error}"
    whatsapp_recipients = [re.sub(r"\D", "", value) for value in str(preference.get("whatsapp_recipients") or "").split(",") if re.sub(r"\D", "", value)]
    if preference.get("notify_whatsapp") and whatsapp_recipients:
        if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
            results["whatsapp"] = "not configured"
        else:
            endpoint = f"https://graph.facebook.com/{settings.whatsapp_phone_number_id}/messages"
            for recipient in whatsapp_recipients:
                try:
                    payload = json.dumps({"messaging_product": "whatsapp", "to": recipient, "type": "text", "text": {"body": f"{title}\n{message}"}}).encode()
                    request = urllib.request.Request(endpoint, data=payload, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}", "Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=30):
                        pass
                    results[f"whatsapp:{recipient[-4:]}"] = "sent"
                except Exception as error:
                    results[f"whatsapp:{recipient[-4:]}"] = f"error: {error}"
    return results


def create_alert_once(alert_type: str, severity: str, title: str, message: str, source_id: str, metadata: dict[str, Any] | None = None) -> bool:
    preference = alert_preference(alert_type)
    order = {"info": 0, "warning": 1, "critical": 2}
    if not preference.get("enabled") or order.get(severity, 0) < order.get(str(preference.get("min_severity") or "warning"), 1):
        return False
    created = False
    with transaction() as (_, cursor):
        cursor.execute("SELECT id FROM alerts WHERE estate_id=%s AND source_id=%s LIMIT 1", (estate_id(), source_id))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO alerts (id,estate_id,alert_type,severity,title,message,source,source_id,status,triggered_at,metadata) VALUES (%s,%s,%s,%s,%s,%s,'operational-intelligence',%s,'open',NOW(),%s)",
                (new_id(), estate_id(), alert_type, severity, title, message, source_id, json.dumps(json_ready(metadata or {}))),
            )
            created = True
    if created:
        send_alert_notifications(alert_type, severity, title, message)
    return created


def refresh_operational_alerts() -> dict[str, int]:
    """Create small-team alerts from conditions already recorded in the database."""
    today = date.today().isoformat()
    created = 0
    weather = fetch_one(
        "SELECT MIN(temp_c) min_temp_c,MAX(temp_c) max_temp_c,MAX(wind_gust_kph) max_gust_kph,MAX(COALESCE(rain_mm,0)) rain_24h_mm,MIN(soil_moisture_pct) min_soil_moisture_pct,MAX(uv_index) max_uv_index,MAX(observed_at) latest_at FROM weather_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 24 HOUR",
        (estate_id(),),
    ) or {}
    current_weather = fetch_one(
        "SELECT temp_c,humidity_pct,COALESCE(wind_gust_kph,wind_kph) wind_kph,observed_at FROM weather_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 2 HOUR ORDER BY observed_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    min_temp = _numeric(weather.get("min_temp_c"))
    max_temp = _numeric(weather.get("max_temp_c"))
    max_gust = _numeric(weather.get("max_gust_kph"))
    rain = _numeric(weather.get("rain_24h_mm"))
    soil = _numeric(weather.get("min_soil_moisture_pct"))
    uv_index = _numeric(weather.get("max_uv_index"))
    conditions: list[tuple[str, str, str, str]] = []
    if max_temp is not None and max_temp >= 34:
        conditions.append(("heat", "critical" if max_temp >= 40 else "warning", "Extreme vineyard heat", f"Temperature reached {max_temp:.1f} C. Move strenuous work to early hours, verify drinking water, inspect exposed fruit and review irrigation need."))
    if min_temp is not None and min_temp <= 3:
        conditions.append(("frost", "critical" if min_temp <= 0 else "warning", "Vineyard frost risk", f"Temperature reached {min_temp:.1f} C. Check low parcels and frost protection, then inspect young growth at first light."))
    if max_gust is not None and max_gust >= 45:
        conditions.append(("wind", "critical" if max_gust >= 70 else "warning", "Damaging wind", f"Gusts reached {max_gust:.0f} km/h. Stop spraying and elevated work, secure loose equipment and inspect trellis lines."))
    if rain is not None and rain >= 20:
        conditions.append(("rain", "critical" if rain >= 50 else "warning", "Heavy rain and runoff risk", f"Daily rain reached {rain:.1f} mm. Check drains, access roads and erosion points and keep machinery off saturated soil."))
    if soil is not None and soil < 20 and max_temp is not None and max_temp >= 30:
        conditions.append(("drought", "warning", "Dry soil and heat stress", f"Soil moisture fell to {soil:.0f}% with heat at {max_temp:.1f} C. Inspect representative vines before changing irrigation and prioritize young or visibly stressed blocks."))
    current_temp = _numeric(current_weather.get("temp_c"))
    current_humidity = _numeric(current_weather.get("humidity_pct"))
    current_wind = _numeric(current_weather.get("wind_kph"))
    if current_temp is not None and current_temp >= 34 and current_humidity is not None and current_humidity <= 20 and current_wind is not None and current_wind >= 25:
        conditions.append(("fire_weather", "critical", "High fire-weather risk", f"Current conditions are {current_temp:.1f} C, {current_humidity:.0f}% humidity and {current_wind:.0f} km/h wind. Avoid flames and spark-producing work, keep access clear and check extinguishers and water points."))
    if uv_index is not None and uv_index >= 8:
        conditions.append(("uv", "warning", "Very high UV", f"UV index reached {uv_index:.0f}. Move exposed work away from midday and require shade, water, hats and sun protection."))
    for code, severity, title, message in conditions:
        created += int(create_alert_once("weather", severity, title, message, f"weather:{today}:{code}:{severity}", {**weather, "condition": code}))
    lab = fetch_one(
        "SELECT COUNT(DISTINCT s.id) n,MAX(s.lab_date) latest_date FROM lab_samples s LEFT JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s AND (s.needs_review=1 OR r.flag IN ('low','high','review'))",
        (estate_id(),),
    ) or {}
    if int(lab.get("n") or 0):
        created += int(create_alert_once("laboratory", "warning", "Laboratory review needed", f"{int(lab['n'])} laboratory sample(s) have flagged results or still need review.", f"laboratory:{lab.get('latest_date') or today}", lab))
    overdue = fetch_one(
        "SELECT COUNT(*) n,MIN(due_date) oldest_due FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') AND priority IN ('high','urgent') AND due_date<CURDATE()",
        (estate_id(),),
    ) or {}
    if int(overdue.get("n") or 0):
        created += int(create_alert_once("tasks", "warning", "Priority work overdue", f"{int(overdue['n'])} high-priority vineyard task(s) are overdue. Review assignments and dates.", f"tasks:{today}", overdue))
    settings = get_settings()
    if not demo_enabled(settings):
        cellar_tanks = _live_cellar_tanks()
        sensor_states: dict[str, dict[str, Any]] = {}
        sensor_ids = live_sensor_entity_ids(settings)
        if sensor_ids:
            try:
                sensor_states = home_assistant_state_map(sensor_ids)
            except Exception:
                pass
        apply_live_sensor_readings(cellar_tanks, settings, sensor_states)
        for guard in evaluate_cellar_tanks(cellar_tanks, settings):
            tank_key = guard.get("tank_id") or guard.get("tank_code")
            for category in sorted({item.get("category") for item in guard.get("violations", []) if item.get("category")}):
                alert_type = f"cellar_{category}"
                title = f"Cellar {category} · {guard['tank_name']}"
                message = "; ".join(guard["messages"]) + ". Verify the sensor and lot, then ask the enologist before corrective cellar action."
                created += int(create_alert_once(alert_type, "warning", title, message, f"{alert_type}:{today}:{tank_key}", guard))
        overdue_checks = fetch_one(
            "SELECT COUNT(*) n,MIN(next_check_at) oldest_due FROM fermentation_observations WHERE estate_id=%s AND next_check_at<NOW() AND COALESCE(status,'') NOT IN ('completed','closed')",
            (estate_id(),),
        ) or {}
        if int(overdue_checks.get("n") or 0):
            created += int(create_alert_once("cellar_checks", "warning", "Cellar checks overdue", f"{int(overdue_checks['n'])} cellar check(s) are overdue. Review the lot and assign the next check.", f"cellar_checks:{today}", overdue_checks))
    failures = fetch_one(
        "SELECT COUNT(*) n,MAX(current_event.occurred_at) latest_at FROM integration_events current_event "
        "WHERE current_event.estate_id=%s AND current_event.status='failed' "
        "AND current_event.occurred_at>=NOW()-INTERVAL 24 HOUR "
        "AND NOT EXISTS ("
        "SELECT 1 FROM integration_events newer_event "
        "WHERE newer_event.estate_id=current_event.estate_id "
        "AND newer_event.integration_name=current_event.integration_name "
        "AND newer_event.event_type=current_event.event_type "
        "AND (newer_event.occurred_at>current_event.occurred_at "
        "OR (newer_event.occurred_at=current_event.occurred_at AND newer_event.id>current_event.id))"
        ")",
        (estate_id(),),
    ) or {}
    if int(failures.get("n") or 0):
        severity = "critical" if int(failures["n"]) >= 3 else "warning"
        created += int(create_alert_once("system", severity, "Vineyard service errors", f"{int(failures['n'])} integration(s) still have a failed latest attempt.", f"system:{today}:{severity}", failures))
    return {"created": created}


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _live_cellar_tanks() -> list[dict[str, Any]]:
    """Read the latest recorded tank state for alerting and AI context."""
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), date.today().year)) or {}
    rows = fetch_all(
        "SELECT c.id,c.code,c.name,c.capacity_l,c.sensor_entity_id,w.code lot_code,w.name lot_name,w.stage,w.volume_l,w.variety_summary,"
        "(SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) temp_c,"
        "(SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) density_sg,"
        "(SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) brix,"
        "(SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) ph,"
        "(SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) reading_at "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.season_id=%s "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (season.get("id", ""), estate_id()),
    )
    for tank in rows:
        capacity, volume = _numeric(tank.get("capacity_l")) or 0, _numeric(tank.get("volume_l")) or 0
        tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
    return rows


def _gw2000_station() -> str:
    row = fetch_one("SELECT id FROM weather_stations WHERE estate_id=%s AND external_id='gw2000a'", (estate_id(),))
    if row:
        return row["id"]
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO weather_stations (id,estate_id,name,station_type,external_id,location_type,metadata) VALUES (%s,%s,'GW2000A','home_assistant','gw2000a','vineyard',JSON_OBJECT('source','Home Assistant recorder'))", (record_id, estate_id()))
    return record_id


def _sync_weather_history_chunk(
    station_id: str,
    gw2000_entities: dict[str, str],
    start: datetime,
    end: datetime,
) -> int:
    entity_list = ",".join(gw2000_entities.values())
    path = "/history/period/" + urllib.parse.quote(start.isoformat(), safe="-:T") + "?" + urllib.parse.urlencode(
        {
            "end_time": end.isoformat(),
            "filter_entity_id": entity_list,
            "minimal_response": "",
            "no_attributes": "",
        }
    )
    history = _ha_get(path) or []
    daily: dict[date, dict[str, list[float]]] = {}
    reverse = {entity: key for key, entity in gw2000_entities.items()}
    for series in history:
        if not series:
            continue
        key = reverse.get(series[0].get("entity_id"))
        if not key:
            continue
        for point in series:
            value = _numeric(point.get("state"))
            if value is None:
                continue
            try:
                day = datetime.fromisoformat(str(point.get("last_changed", "")).replace("Z", "+00:00")).date()
            except Exception:
                continue
            daily.setdefault(day, {}).setdefault(key, []).append(value)
    with transaction() as (_, cursor):
        for day, fields in daily.items():
            temps = fields.get("temp_c", [])
            humidities = fields.get("humidity_pct", [])
            winds = fields.get("wind_gust_kph", []) + fields.get("wind_kph", [])
            rains = fields.get("rain_mm", [])
            solar = fields.get("solar_wm2", [])
            soils = fields.get("soil_moisture_1", []) + fields.get("soil_moisture_2", [])
            avg_temp = sum(temps) / len(temps) if temps else None
            gdd = max(0, avg_temp - 10) if avg_temp is not None else None
            cursor.execute(
                "INSERT INTO weather_daily (estate_id,station_id,weather_date,temp_min_c,temp_avg_c,temp_max_c,humidity_avg_pct,rain_mm,wind_max_kph,solar_mj_m2,soil_moisture_avg_pct,gdd_base10) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE temp_min_c=VALUES(temp_min_c),temp_avg_c=VALUES(temp_avg_c),temp_max_c=VALUES(temp_max_c),humidity_avg_pct=VALUES(humidity_avg_pct),rain_mm=VALUES(rain_mm),wind_max_kph=VALUES(wind_max_kph),solar_mj_m2=VALUES(solar_mj_m2),soil_moisture_avg_pct=VALUES(soil_moisture_avg_pct),gdd_base10=VALUES(gdd_base10)",
                (estate_id(), station_id, day, min(temps) if temps else None, avg_temp, max(temps) if temps else None, sum(humidities) / len(humidities) if humidities else None, max(rains) if rains else None, max(winds) if winds else None, (sum(solar) / len(solar)) * 0.0864 if solar else None, sum(soils) / len(soils) if soils else None, gdd),
            )
        cursor.execute(
            "INSERT INTO sync_checkpoints (estate_id,integration_name,checkpoint_value,last_success_at,last_attempt_at,metadata) VALUES (%s,'home_assistant_gw2000_history',%s,NOW(),NOW(),%s) ON DUPLICATE KEY UPDATE checkpoint_value=VALUES(checkpoint_value),last_success_at=NOW(),last_attempt_at=NOW(),last_error=NULL,metadata=VALUES(metadata)",
            (estate_id(), end.isoformat(), json.dumps({"days": len(daily), "entities": list(gw2000_entities.values())})),
        )
    return len(daily)


def sync_home_assistant_weather() -> dict[str, Any]:
    if not home_assistant_token():
        return {"configured": False, "message": "Home Assistant supervisor access is not available"}
    station_id = _gw2000_station()
    states = _ha_get("/states") or []
    state_map = {row.get("entity_id"): row for row in states}
    gw2000_entities = resolve_gw2000_entities(states, get_settings().gw2000_entity_prefix)
    snapshot_at = datetime.now().replace(second=0, microsecond=0)
    with transaction() as (_, cursor):
        for entity_id in PLANNING_ENTITIES:
            item = state_map.get(entity_id)
            if not item:
                continue
            attributes = item.get("attributes") or {}
            cursor.execute(
                "INSERT IGNORE INTO planning_sensor_snapshots (estate_id,entity_id,recorded_at,state_value,numeric_value,unit,friendly_name,attributes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), entity_id, snapshot_at, str(item.get("state")), _numeric(item.get("state")), attributes.get("unit_of_measurement"), attributes.get("friendly_name"), json.dumps(attributes)),
            )
    values = {key: _numeric((state_map.get(entity) or {}).get("state")) for key, entity in gw2000_entities.items()}
    for key in GW2000_ENTITIES:
        values.setdefault(key, None)
    soil_values = [values.pop("soil_moisture_1"), values.pop("soil_moisture_2")]
    values["soil_moisture_pct"] = sum(v for v in soil_values if v is not None) / len([v for v in soil_values if v is not None]) if any(v is not None for v in soil_values) else None
    if any(value is not None for value in values.values()):
        observed_at = datetime.now().replace(second=0, microsecond=0)
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO weather_observations (estate_id,station_id,observed_at,temp_c,humidity_pct,pressure_hpa,wind_kph,wind_gust_kph,rain_mm,solar_wm2,uv_index,soil_moisture_pct,source_hash,raw_payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE temp_c=VALUES(temp_c),humidity_pct=VALUES(humidity_pct),pressure_hpa=VALUES(pressure_hpa),wind_kph=VALUES(wind_kph),wind_gust_kph=VALUES(wind_gust_kph),rain_mm=VALUES(rain_mm),solar_wm2=VALUES(solar_wm2),uv_index=VALUES(uv_index),soil_moisture_pct=VALUES(soil_moisture_pct),source_hash=VALUES(source_hash),raw_payload=VALUES(raw_payload)",
                (estate_id(), station_id, observed_at, values.get("temp_c"), values.get("humidity_pct"), values.get("pressure_hpa"), values.get("wind_kph"), values.get("wind_gust_kph"), values.get("rain_mm"), values.get("solar_wm2"), values.get("uv_index"), values.get("soil_moisture_pct"), digest, json.dumps(values)),
            )
    checkpoint = fetch_one("SELECT checkpoint_value FROM sync_checkpoints WHERE estate_id=%s AND integration_name='home_assistant_gw2000_history'", (estate_id(),))
    start = datetime.fromisoformat(checkpoint["checkpoint_value"]) if checkpoint and checkpoint.get("checkpoint_value") else datetime(2023, 1, 1)
    now = datetime.now()
    end = start
    imported_days = 0
    # Four restart-safe chunks move roughly eight weeks per cycle without asking
    # Home Assistant Recorder for an excessively large response in one request.
    for _ in range(4):
        end = min(start + timedelta(days=14), now)
        if start >= end or not gw2000_entities:
            break
        imported_days += _sync_weather_history_chunk(station_id, gw2000_entities, start, end)
        start = end
    return {"configured": True, "live_values": values, "history_through": end.isoformat(), "history_days_imported": imported_days}


def calculate_disease_pressure(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Screening signals only; treatment decisions remain with the agronomist."""
    temp = float(metrics.get("temp_avg_c") or 0)
    max_temp = float(metrics.get("temp_max_c") or temp)
    humidity = float(metrics.get("humidity_avg_pct") or 0)
    rain = float(metrics.get("rain_72h_mm") or 0)
    rain_7d = float(metrics.get("rain_7d_mm") or rain)
    leaf_wetness = float(metrics.get("leaf_wetness_avg_pct") or 0)
    wind_gust = float(metrics.get("wind_gust_max_kph") or 0)
    solar = float(metrics.get("solar_avg_wm2") or 0)
    soil = metrics.get("soil_moisture_avg_pct")
    soil_value = float(soil) if soil is not None else 35.0
    stage = str(metrics.get("phenology_stage") or "").casefold()
    susceptible_stage = 10 if any(term in stage for term in ("flower", "bloom", "fruit", "berry", "cluster", "veraison", "invaiatura")) else 0
    maturity_disease = min(25.0, float(metrics.get("maturity_disease_pct") or 0) * 1.25)
    scouting = metrics.get("scouting") if isinstance(metrics.get("scouting"), list) else []
    severity_points = {"trace": 3, "low": 8, "medium": 18, "high": 30, "critical": 45}
    scouting_scores = {"downy_mildew": 0.0, "powdery_mildew": 0.0, "botrytis": 0.0, "heat_stress": 0.0}
    terms = {"downy_mildew": ("downy", "peronospora"), "powdery_mildew": ("powdery", "oidium", "oidio"), "botrytis": ("botrytis", "grey rot", "gray rot", "muffa"), "heat_stress": ("heat", "water stress", "drought", "sunburn", "calore", "siccità")}
    for observation in scouting:
        text = f"{observation.get('issue_type') or ''} {observation.get('notes') or ''}".casefold()
        points = severity_points.get(str(observation.get("severity") or "low").casefold(), 8)
        matches = [code for code, words in terms.items() if any(word in text for word in words)]
        for code in matches or scouting_scores:
            scouting_scores[code] += points if matches else points * .25
    downy = _clamp((humidity - 60) * 1.15 + min(rain, 30) * 1.7 + min(rain_7d, 60) * .35 + leaf_wetness * .35 + (16 if 10 <= temp <= 28 else 0) + susceptible_stage + maturity_disease + scouting_scores["downy_mildew"])
    powdery = _clamp((humidity - 45) * .75 + (28 if 18 <= temp <= 30 else 4) + susceptible_stage + maturity_disease + scouting_scores["powdery_mildew"] - min(rain, 20) * .35)
    botrytis = _clamp((humidity - 70) * 1.2 + min(rain, 35) * 1.25 + min(rain_7d, 60) * .3 + leaf_wetness * .4 + (16 if 15 <= temp <= 25 else 0) + susceptible_stage + maturity_disease + scouting_scores["botrytis"])
    heat = _clamp((max_temp - 29) * 8 + max(0, 32 - soil_value) * 1.5 + max(0, solar - 550) * .025 + max(0, wind_gust - 35) * .35 + scouting_scores["heat_stress"])
    definitions = (
        ("downy_mildew", "Downy mildew", downy, "Scout susceptible blocks and review canopy wetness with Sebastian before any treatment decision."),
        ("powdery_mildew", "Powdery mildew", powdery, "Inspect shaded bunch zones and recent growth; ask Sebastian to confirm whether action is warranted."),
        ("botrytis", "Botrytis", botrytis, "Check bunch condition and airflow, especially after rain; record field evidence before deciding."),
        ("heat_stress", "Heat stress", heat, "Inspect vine and soil-water stress early in the day and review irrigation or protection priorities."),
    )
    return [
        {"disease_code": code, "disease_name": name, "risk_score": score, "risk_level": risk_level(score), "suggested_action": action}
        for code, name, score, action in definitions
    ]


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return None


def _meaningful_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in {"", "null", "none", "n/a", "unknown"} else text


def _has_weather_evidence(assessment: dict[str, Any]) -> bool:
    snapshot = assessment.get("input_snapshot")
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            snapshot = {}
    if not isinstance(snapshot, dict) or int(snapshot.get("weather_observation_count") or 0) <= 0:
        return False
    return any(snapshot.get(key) is not None for key in (
        "temp_avg_c", "temp_max_c", "humidity_avg_pct", "rain_72h_mm", "soil_moisture_avg_pct"
    ))


def predict_next_treatment(
    treatments: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    prediction_date: date | None = None,
) -> dict[str, Any]:
    """Predict the next review point, never an autonomous pesticide instruction."""
    today = prediction_date or date.today()
    planned: list[tuple[date, dict[str, Any]]] = []
    overdue: list[tuple[date, dict[str, Any]]] = []
    for row in treatments:
        if row.get("status") != "planned":
            continue
        planned_date = _date_value(row.get("planned_application_date") or row.get("application_date"))
        if not planned_date:
            continue
        (planned if planned_date >= today else overdue).append((planned_date, row))

    safety = "Sebastian/agronomist approval, current Italian label, PHI, REI, weather and PPE checks are required before application."
    if planned:
        planned_date, row = min(planned, key=lambda item: item[0])
        return {
            "type": "recorded_plan", "headline": _meaningful_text(row.get("purpose")) or "Recorded treatment plan",
            "timing_label": "Today" if planned_date == today else f"In {(planned_date - today).days} days",
            "window_start": planned_date, "window_end": planned_date, "confidence": "Recorded plan",
            "risk_level": "planned", "why": _meaningful_text(row.get("source_instructions")) or _meaningful_text(row.get("notes")) or "This date is already recorded in the vineyard plan.",
            "suggested_action": f"Confirm current field conditions and the recorded plan with Sebastian. {safety}",
            "agronomist_status": "approved" if row.get("agronomist_approved") else "pending",
            "requires_agronomist_approval": True, "source_record_id": row.get("id"),
        }
    overdue = [item for item in overdue if (today - item[0]).days <= 45]
    if overdue:
        planned_date, row = max(overdue, key=lambda item: item[0])
        return {
            "type": "overdue_verification", "headline": _meaningful_text(row.get("purpose")) or "Verify overdue treatment plan",
            "timing_label": f"Verify now · {(today - planned_date).days} days overdue",
            "window_start": today, "window_end": today, "confidence": "Recorded plan needs reconciliation",
            "risk_level": "high", "why": f"The planned date was {planned_date.isoformat()}, but the record is still marked planned.",
            "suggested_action": "Confirm whether it was completed, cancelled or rescheduled; do not duplicate an application. " + safety,
            "agronomist_status": "pending", "requires_agronomist_approval": True, "source_record_id": row.get("id"),
        }

    current = [row for row in assessments if row.get("disease_code") != "heat_stress"]
    if not current or not any(_has_weather_evidence(row) for row in current):
        return {
            "type": "insufficient_data", "headline": "No treatment prediction yet",
            "timing_label": "Waiting for current weather evidence", "window_start": None, "window_end": None,
            "confidence": "Insufficient data", "risk_level": "unknown",
            "why": "The disease model does not have enough current GW2000 weather evidence to support a timing estimate.",
            "suggested_action": "Check the weather sync and scout the vineyard. No treatment is recommended from missing data.",
            "agronomist_status": "not_required", "requires_agronomist_approval": True,
        }
    highest = max(current, key=lambda row: float(row.get("risk_score") or 0))
    level = highest.get("risk_level") or "low"
    windows = {"critical": (0, 1), "high": (1, 3), "moderate": (3, 7), "low": (7, 7)}
    start_days, end_days = windows.get(level, (7, 7))
    review_start, review_end = today + timedelta(days=start_days), today + timedelta(days=end_days)
    no_action = level == "low"
    return {
        "type": "monitor" if no_action else "field_review",
        "headline": "No treatment predicted from current evidence" if no_action else f"Review {highest.get('disease_name', 'disease')} risk with Sebastian",
        "timing_label": f"Reassess by {review_end.strftime('%d %b')}" if no_action else f"Field review {review_start.strftime('%d %b')}–{review_end.strftime('%d %b')}",
        "window_start": review_start, "window_end": review_end, "confidence": "Weather screening",
        "risk_level": level, "why": highest.get("evidence_summary") or "Current weather-based disease pressure screening.",
        "suggested_action": (highest.get("suggested_action") or "Scout susceptible blocks.") + " " + safety,
        "agronomist_status": highest.get("agronomist_status") or "pending",
        "requires_agronomist_approval": True, "source_assessment_id": highest.get("id"),
    }


def refresh_disease_pressure() -> list[dict[str, Any]]:
    row = fetch_one(
        "SELECT AVG(temp_c) temp_avg_c,MIN(temp_c) temp_min_c,MAX(temp_c) temp_max_c,AVG(humidity_pct) humidity_avg_pct,"
        "SUM(CASE WHEN observed_at>=NOW()-INTERVAL 72 HOUR THEN COALESCE(rain_mm,0) ELSE 0 END) rain_72h_mm,"
        "SUM(COALESCE(rain_mm,0)) rain_7d_mm,AVG(leaf_wetness_pct) leaf_wetness_avg_pct,"
        "AVG(soil_moisture_pct) soil_moisture_avg_pct,MAX(wind_gust_kph) wind_gust_max_kph,AVG(solar_wm2) solar_avg_wm2,"
        "MAX(observed_at) weather_latest_at,COUNT(*) weather_observation_count "
        "FROM weather_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 7 DAY",
        (estate_id(),),
    ) or {}
    row["scouting"] = fetch_all(
        "SELECT issue_type,severity,incidence_pct,notes,observed_at FROM scouting_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 14 DAY ORDER BY observed_at DESC LIMIT 30",
        (estate_id(),),
    )
    maturity = fetch_one(
        "SELECT MAX(disease_pct) maturity_disease_pct,MAX(sampled_at) maturity_latest_at FROM maturity_samples WHERE estate_id=%s AND sampled_at>=NOW()-INTERVAL 30 DAY",
        (estate_id(),),
    ) or {}
    row.update(maturity)
    phenology = fetch_one(
        "SELECT stage_name,stage_code,observed_date FROM phenology_observations WHERE estate_id=%s ORDER BY observed_date DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    row["phenology_stage"] = phenology.get("stage_name") or phenology.get("stage_code")
    row["phenology_date"] = phenology.get("observed_date")
    treatment = fetch_one(
        "SELECT MAX(application_date) latest_treatment_at,COUNT(*) treatments_30d FROM spray_applications WHERE estate_id=%s AND status='completed' AND application_date>=NOW()-INTERVAL 30 DAY",
        (estate_id(),),
    ) or {}
    row.update(treatment)
    assessments = calculate_disease_pressure(row)
    now = datetime.now()
    evidence_parts = [
        f"weather through {row.get('weather_latest_at') or 'not available'}",
        f"avg/max {float(row.get('temp_avg_c') or 0):.1f}/{float(row.get('temp_max_c') or 0):.1f} C",
        f"humidity {float(row.get('humidity_avg_pct') or 0):.0f}%",
        f"rain 72 h/7 d {float(row.get('rain_72h_mm') or 0):.1f}/{float(row.get('rain_7d_mm') or 0):.1f} mm",
    ]
    if row.get("leaf_wetness_avg_pct") is not None:
        evidence_parts.append(f"leaf wetness {float(row['leaf_wetness_avg_pct']):.0f}%")
    if row.get("soil_moisture_avg_pct") is not None:
        evidence_parts.append(f"soil moisture {float(row['soil_moisture_avg_pct']):.0f}%")
    if row.get("phenology_stage"):
        evidence_parts.append(f"stage {row['phenology_stage']}")
    evidence_parts.append(f"{len(row['scouting'])} recent scouting observation(s)")
    if row["scouting"]:
        evidence_parts.append("scouting: " + ", ".join(str(item.get("issue_type") or "observation") for item in row["scouting"][:3]))
    if row.get("maturity_disease_pct") is not None:
        evidence_parts.append(f"maturity disease max {float(row['maturity_disease_pct']):.1f}%")
    treatment_context = f"{int(row.get('treatments_30d') or 0)} completed treatment(s) in 30 d"
    if row.get("latest_treatment_at"):
        treatment_context += f", latest {str(row['latest_treatment_at'])[:10]}"
    evidence_parts.append(treatment_context + " (context only)")
    evidence = "; ".join(evidence_parts) + "."
    with transaction() as (_, cursor):
        for item in assessments:
            record_id = new_id()
            cursor.execute(
                "INSERT INTO disease_pressure_assessments (id,estate_id,assessed_at,assessment_date,model_version,disease_code,disease_name,risk_score,risk_level,evidence_summary,suggested_action,input_snapshot) "
                "VALUES (%s,%s,%s,%s,'evidence-screen-v2',%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE assessed_at=VALUES(assessed_at),model_version=VALUES(model_version),risk_score=VALUES(risk_score),risk_level=VALUES(risk_level),evidence_summary=VALUES(evidence_summary),suggested_action=VALUES(suggested_action),input_snapshot=VALUES(input_snapshot)",
                (record_id, estate_id(), now, now.date(), item["disease_code"], item["disease_name"], item["risk_score"], item["risk_level"], evidence, item["suggested_action"], json.dumps(json_ready(row))),
            )
            source_id = f"pressure:{now.date()}:{item['disease_code']}"
            if item["risk_level"] in {"high", "critical"}:
                create_alert_once("disease_pressure", "critical" if item["risk_level"] == "critical" else "warning", f"{item['disease_name']} pressure {item['risk_level']}", item["suggested_action"], source_id, item)
    return [{**item, "evidence_summary": evidence, "agronomist_status": "pending"} for item in assessments]


def save_intake_file(data: bytes, filename: str, media_type: str | None, source: str, title: str | None = None,
                     message_text: str | None = None, external_id: str | None = None,
                     sender_name: str | None = None, sender_address: str | None = None) -> str:
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Files must be 20 MB or smaller")
    digest = hashlib.sha256(data).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "upload").name)[:180]
    record_id = new_id()
    INTAKE_ROOT.mkdir(parents=True, exist_ok=True)
    path = INTAKE_ROOT / f"{record_id}-{safe_name}"
    path.write_bytes(data)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO intake_items (id,estate_id,source,external_id,sender_name,sender_address,received_at,title,message_text,original_filename,stored_path,media_type,file_sha256,classification,review_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s,%s,'unclassified','new')",
            (record_id, estate_id(), source, external_id, sender_name, sender_address, title, message_text, safe_name, str(path), media_type or mimetypes.guess_type(safe_name)[0], digest),
        )
    return record_id


def analyze_intake(record_id: str) -> dict[str, Any]:
    settings = get_settings()
    item = fetch_one("SELECT * FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not item:
        raise ValueError("Intake item not found")
    if not settings.openai_api_key:
        return {"configured": False, "message": "Add the OpenAI API key in app configuration to analyze this item."}
    prompt = (
        "Classify this Tenuta Baiamonte vineyard intake as one of lab_report, vineyard_instruction, cellar_instruction, "
        "labor_hours, completed_work, issue_or_decision, harvest_total, treatment_instruction, weather, olive_record, finance, or other. "
        "Extract only explicit facts and preserve names, dates, units, block, variety, lot and sender. Return JSON with classification, summary, "
        "facts, uncertainties, suggested_database_records, and required_human_review. Each suggested record must name the destination section and fields. "
        "Do not invent missing values. Never approve a treatment or lab correction; mark those agronomist_review_required or enologist_review_required."
    )
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt + "\nMessage: " + (item.get("message_text") or "") }]
    path = Path(item["stored_path"]) if item.get("stored_path") else None
    if path and path.exists():
        raw = path.read_bytes()
        mime = item.get("media_type") or "application/octet-stream"
        encoded = base64.b64encode(raw).decode()
        if mime.startswith("image/"):
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
        else:
            content.append({"type": "input_file", "filename": item.get("original_filename") or "document", "file_data": f"data:{mime};base64,{encoded}"})
    request_body = json.dumps({"model": settings.openai_model, "input": [{"role": "user", "content": content}], "text": {"format": {"type": "json_object"}}}).encode()
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=request_body, headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read())
        output_text = _response_text(result) or "{}"
        parsed = json.loads(output_text)
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET classification=%s,ai_summary=%s,extracted_data=%s,review_status='ready_for_review',processing_error=NULL WHERE id=%s", (parsed.get("classification"), parsed.get("summary"), json.dumps(parsed), record_id))
        return {"configured": True, "analysis": parsed}
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET review_status='failed',processing_error=%s WHERE id=%s", (str(error)[:1000], record_id))
        raise


def _response_text(result: dict[str, Any]) -> str:
    if result.get("output_text"):
        return str(result["output_text"])
    parts: list[str] = []
    for item in result.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)


def ask_assistant(question: str, language: str = "en", focus: str = "vineyard") -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"configured": False, "message": "Add the OpenAI API key in app configuration to ask vineyard questions."}
    if demo_enabled(settings):
        cellar_context = demo_cellar(settings, date.today().year)
    else:
        cellar_tanks = _live_cellar_tanks()
        cellar_context = {"demo": False, "tanks": cellar_tanks, "guardrails": cellar_guardrails(settings), "guard_alerts": evaluate_cellar_tanks(cellar_tanks, settings)}
    context = {
        "weather_recent": json_ready(fetch_all("SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph,soil_moisture_pct FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 96", (estate_id(),))),
        "disease_pressure": json_ready(fetch_all("SELECT assessment_date,disease_name,risk_score,risk_level,evidence_summary,suggested_action,agronomist_status,agronomist_notes FROM disease_pressure_assessments WHERE estate_id=%s ORDER BY assessment_date DESC,risk_score DESC LIMIT 20", (estate_id(),))),
        "lab_flags": json_ready(fetch_all("SELECT lab_date,sample_name,analyte_name,numeric_value,unit,comparison_flag,decision_action FROM v_lab_comparison WHERE estate_id=%s AND comparison_flag IN ('review','high','low') ORDER BY lab_date DESC LIMIT 40", (estate_id(),))),
        "lab_recent": json_ready(fetch_all("SELECT lab_date,sample_name,sample_type,analyte_name,numeric_value,text_value,unit,comparison_flag,reference_min,reference_max FROM v_lab_comparison WHERE estate_id=%s ORDER BY lab_date DESC,sample_name,analyte_name LIMIT 120", (estate_id(),))),
        "planned_treatments": json_ready(fetch_all("SELECT application_date,purpose,block_code,products,agronomist_approved FROM v_treatment_history WHERE estate_id=%s AND status='planned' ORDER BY application_date LIMIT 30", (estate_id(),))),
        "treatment_history": json_ready(fetch_all("SELECT application_date,planned_application_date,purpose,block_code,products,source_doses,source_water_text,status,planned_by,assigned_to,agronomist_approved,actual_details_confirmed,source_instructions FROM v_treatment_history WHERE estate_id=%s ORDER BY application_date DESC LIMIT 60", (estate_id(),))),
        "open_work": json_ready(fetch_all("SELECT title,category,priority,due_date,block_code,status FROM v_open_work WHERE estate_id=%s ORDER BY due_date LIMIT 30", (estate_id(),))),
        "cellar": json_ready(cellar_context),
    }
    system = (
        "You are the Tenuta Baiamonte vineyard decision-support assistant. "
        f"The current question focus is {focus}. Answer from the supplied database context, distinguish facts from inference, "
        "and say when data is missing. Never approve or prescribe a pesticide treatment. Treatment suggestions must require Sebastian/agronomist review, "
        "current Italian label legality, PHI, REI, weather and PPE checks. For cellar questions, explain any crossed guardrail, distinguish demo from live data, "
        "and require source verification and enologist approval before corrective action. Do not alter data or control equipment."
        + (" Reply in Italian." if language == "it" else " Reply in English.")
    )
    request_body = json.dumps({"model": settings.openai_model, "input": [{"role": "developer", "content": system}, {"role": "user", "content": question + "\n\nCurrent database context:\n" + json.dumps(context)}]}).encode()
    request = urllib.request.Request("https://api.openai.com/v1/responses", data=request_body, headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.loads(response.read())
    return {"configured": True, "answer": _response_text(result), "model": settings.openai_model}


def poll_gmail_once() -> int:
    settings = get_settings()
    if not settings.gmail_address or not settings.gmail_app_password:
        return 0
    allowed = {item.strip().casefold() for item in settings.gmail_allowed_senders.split(",") if item.strip()}
    saved = 0
    mailbox = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mailbox.login(settings.gmail_address, settings.gmail_app_password)
        mailbox.select(settings.gmail_folder or "INBOX", readonly=True)
        _, ids = mailbox.search(None, "UNSEEN")
        for message_id in (ids[0].split() if ids and ids[0] else [])[-50:]:
            external_id = message_id.decode()
            if fetch_one("SELECT id FROM intake_items WHERE estate_id=%s AND source='gmail' AND external_id LIKE %s", (estate_id(), external_id + ":%")):
                continue
            _, payload = mailbox.fetch(message_id, "(BODY.PEEK[])")
            raw = next((part[1] for part in payload if isinstance(part, tuple)), None)
            if not raw:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw)
            sender_name, sender_address = parseaddr(message.get("From", ""))
            if allowed and sender_address.casefold() not in allowed:
                continue
            body_part = message.get_body(preferencelist=("plain",))
            body_text = body_part.get_content() if body_part else ""
            parts = list(message.iter_attachments())
            if not parts and body_text.strip():
                record_id = save_intake_file(body_text.encode(), "message.txt", "text/plain", "gmail", message.get("Subject"), body_text, f"{external_id}:body", sender_name, sender_address)
                saved += 1
                if settings.openai_api_key:
                    try:
                        analyze_intake(record_id)
                    except Exception:
                        pass
            for part in parts:
                data = part.get_payload(decode=True) or b""
                if not data:
                    continue
                attachment_id = f"{external_id}:{part.get_filename() or saved}"
                record_id = save_intake_file(data, part.get_filename() or "attachment", part.get_content_type(), "gmail", message.get("Subject"), body_text, attachment_id, sender_name, sender_address)
                saved += 1
                if settings.openai_api_key:
                    try:
                        analyze_intake(record_id)
                    except Exception:
                        pass
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass
    return saved


def _record_scheduled_integration(integration_name: str, status: str, result: Any = None, error: Exception | None = None) -> None:
    try:
        payload = None
        if result is not None:
            payload = json.dumps(json_ready(result))
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload,error_message) "
                "VALUES (%s,%s,'inbound','scheduled_sync',%s,%s,%s)",
                (estate_id(), integration_name, status, payload, str(error)[:1000] if error else None),
            )
    except Exception:
        pass


def refresh_etna_alerts() -> dict[str, Any]:
    """Refresh official Etna sources and alert once per new activity notice."""
    payload = refresh_etna()
    activity = payload.get("activity") or {}
    source = activity.get("source") or {}
    created = False
    if activity.get("active") and source.get("sent_at"):
        created = create_alert_once(
            "etna",
            "critical",
            "Mount Etna activity notice",
            f"INGV issued {source.get('description', 'a new Etna activity notice')} at {source.get('sent_at')}. Open the Etna page and follow INGV and Civil Protection instructions.",
            "etna-activity-" + str(activity.get("since") or source.get("sent_at")),
            {"official_source": source.get("url"), "activity": activity},
        )
    civil = payload.get("civil_protection") or {}
    if civil.get("level") in {"yellow", "orange", "red"}:
        created = create_alert_once(
            "etna",
            "critical" if civil.get("level") in {"orange", "red"} else "warning",
            f"Etna Civil Protection alert: {str(civil.get('level')).upper()}",
            "Review the official Civil Protection status and local instructions. Etna can change suddenly.",
            "etna-civil-" + str(civil.get("level")),
            {"official_source": civil.get("url"), "level": civil.get("level")},
        ) or created
    ash = payload.get("ash_advisory") or {}
    ash_code = str(ash.get("aviation_colour_code") or "").lower()
    if ash_code in {"orange", "red"} and ash.get("issued_at"):
        created = create_alert_once(
            "etna",
            "critical" if ash_code == "red" else "warning",
            f"Etna ash advisory: {ash_code.upper()}",
            " · ".join(filter(None, [
                ash.get("eruption_details"),
                f"Movement {ash.get('ash_direction')}" if ash.get("ash_direction") else None,
                f"Top {ash.get('plume_top')}" if ash.get("plume_top") else None,
                f"Next advisory {ash.get('next_advisory')}" if ash.get("next_advisory") else None,
            ])),
            "etna-vaac-" + str(ash.get("issued_at")),
            {"official_source": ash.get("url"), "ash_advisory": ash},
        ) or created
    return {"activity": activity.get("code"), "communications": len(payload.get("communications") or []), "seismic_events": len(payload.get("seismic_events") or []), "alert_created": created, "errors": payload.get("errors") or {}}


async def integration_loop() -> None:
    settings = get_settings()
    weather_elapsed = max(1, settings.weather_sync_minutes)
    gmail_elapsed = max(1, settings.gmail_poll_minutes)
    finance_elapsed = max(15, settings.fattureincloud_sync_minutes)
    full_elapsed = max(5, settings.full_refresh_minutes)
    etna_elapsed = max(2, settings.etna_refresh_minutes)
    while True:
        if full_elapsed >= max(5, settings.full_refresh_minutes):
            await run_full_refresh()
            weather_elapsed = gmail_elapsed = finance_elapsed = full_elapsed = etna_elapsed = 0
            await asyncio.sleep(60)
            weather_elapsed += 1
            gmail_elapsed += 1
            finance_elapsed += 1
            full_elapsed += 1
            continue
        jobs: list[tuple[str, Any]] = [("disease-pressure", refresh_disease_pressure), ("home-assistant-traffic", publish_home_assistant_traffic_sensors)]
        if settings.etna_enabled and etna_elapsed >= max(2, settings.etna_refresh_minutes):
            jobs.append(("etna-monitor", refresh_etna_alerts))
            etna_elapsed = 0
        if weather_elapsed >= max(1, settings.weather_sync_minutes):
            jobs.append(("home-assistant-weather", sync_home_assistant_weather))
            weather_elapsed = 0
        if gmail_elapsed >= max(1, settings.gmail_poll_minutes):
            jobs.append(("gmail-intake", poll_gmail_once))
            gmail_elapsed = 0
        if settings.fattureincloud_token and settings.fattureincloud_company_id and finance_elapsed >= max(15, settings.fattureincloud_sync_minutes):
            jobs.append(("fattureincloud", pull_fattureincloud))
            finance_elapsed = 0
        jobs.append(("operational-alerts", refresh_operational_alerts))
        for integration_name, job in jobs:
            try:
                result = await asyncio.to_thread(job)
                if integration_name != "disease-pressure":
                    _record_scheduled_integration(integration_name, "processed", result=result)
            except Exception as error:
                _record_scheduled_integration(integration_name, "failed", error=error)
        weather_elapsed += 1
        gmail_elapsed += 1
        finance_elapsed += 1
        full_elapsed += 1
        etna_elapsed += 1
        await asyncio.sleep(60)


async def run_full_refresh() -> dict[str, Any]:
    """Run every configured read/sync/publish subsystem once and keep an audit trail."""
    settings = get_settings()
    jobs: list[tuple[str, Any]] = [
        ("home-assistant-weather", sync_home_assistant_weather),
        ("cistern-camera-level", refresh_cistern_level),
    ]
    if settings.etna_enabled:
        jobs.append(("etna-monitor", refresh_etna_alerts))
    if settings.gmail_address and settings.gmail_app_password:
        jobs.append(("gmail-intake", poll_gmail_once))
    if settings.fattureincloud_token and settings.fattureincloud_company_id:
        jobs.append(("fattureincloud", pull_fattureincloud))
    if settings.public_publish_url:
        jobs.append(("public-harvest-publisher", publish_once))
    jobs.extend([
        ("home-assistant-traffic", publish_home_assistant_traffic_sensors),
        ("disease-pressure", refresh_disease_pressure),
        ("operational-alerts", refresh_operational_alerts),
    ])
    completed: dict[str, Any] = {}
    failures: dict[str, str] = {}
    for integration_name, job in jobs:
        try:
            result = await asyncio.to_thread(job)
            completed[integration_name] = json_ready(result)
            _record_scheduled_integration(integration_name, "processed", result=result)
        except Exception as error:
            failures[integration_name] = str(error)[:300]
            _record_scheduled_integration(integration_name, "failed", error=error)
    summary = {
        "status": "failed" if failures else "processed",
        "completed": list(completed),
        "failed": failures,
        "scheduled_every_minutes": max(5, settings.full_refresh_minutes),
    }
    _record_scheduled_integration(
        "full-system-refresh",
        summary["status"],
        result=summary if not failures else None,
        error=RuntimeError(json.dumps(failures)) if failures else None,
    )
    return summary
