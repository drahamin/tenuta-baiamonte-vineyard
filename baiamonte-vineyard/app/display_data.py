"""Presentation-safe, read-only data for the vineyard entrance display."""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import fetch_all, fetch_one
from .config import get_settings, runtime_option
from .cellar_demo import apply_live_sensor_readings, cellar_guardrails, demo_cellar, demo_enabled, evaluate_cellar_tanks, live_sensor_entity_ids, live_sensor_tank_keys
from .ha_auth import home_assistant_token
from .ha_entities import build_power_indicators, find_baiamonte_media, find_lte_status, find_network_equipment, home_assistant_inventory, merge_display_weather, resolve_gw2000_entities, solar_energy_summary
from .service import estate_id, json_ready
from .intelligence import latest_cistern_level, predict_next_treatment, whatsapp_phone_number_id
from .domains.vineyard_visual import public_status as vineyard_visual_status
from .process_control import process_controls
from .process_runtime import processing_runtime_snapshot
from .etna import etna_status
from .airport import airport_status
from .weather_advisory import severe_weather_advisories
from .planning_sync import planning_view
from .production_impact import adjust_production_forecasts
from .historical_dashboard import all_vintage_rows, historical_forecast_evidence, reconciled_vintage_history
from .domains.harvest import calculate_blend_program


ACCESS_CAMERA_TERMS = ("gate", "door", "entrance", "entry", "driveway", "access", "parking", "cancello", "porta", "ingresso", "parcheggio")


def _communications_review_condition(alias: str = "i") -> str:
    """Keep the TV review column limited to items that still need a person."""
    base_external_id = f"SUBSTRING_INDEX({alias}.external_id,':',1)"
    pending_action = (
        "EXISTS (SELECT 1 FROM integration_events pending WHERE pending.estate_id=" + alias + ".estate_id "
        "AND pending.integration_name='whatsapp-channel' AND pending.status='received' "
        "AND pending.event_type IN ('intake_approval_pending','manager_control_pending','manager_device_control_pending') "
        "AND (JSON_UNQUOTE(JSON_EXTRACT(pending.payload,'$.record_id'))=" + alias + ".id "
        "OR JSON_UNQUOTE(JSON_EXTRACT(pending.payload,'$.message_id'))=" + base_external_id + "))"
    )
    successful_answer = (
        "EXISTS (SELECT 1 FROM integration_events answered WHERE answered.estate_id=" + alias + ".estate_id "
        "AND answered.integration_name='whatsapp-channel' AND answered.direction='outbound' "
        "AND answered.external_id=" + base_external_id + " AND answered.status='processed' "
        "AND answered.event_type IN ('chatbot_reply','manager_camera_snapshot','inbound_routing'))"
    )
    return (
        f"({alias}.review_status IN ('new','processing','failed') OR "
        f"({alias}.review_status='ready_for_review' AND "
        f"({alias}.source<>'whatsapp' OR {pending_action} OR NOT {successful_answer})))"
    )


def is_access_camera_entity(entity_id: str) -> bool:
    """Limit automatic TV discovery to camera IDs that clearly describe estate access."""
    normalized = entity_id.casefold()
    return normalized.startswith("camera.") and any(term in normalized for term in ACCESS_CAMERA_TERMS)


def is_access_camera(entity_id: str, friendly_name: str = "") -> bool:
    return entity_id.startswith("camera.") and any(term in f"{entity_id} {friendly_name}".casefold() for term in ACCESS_CAMERA_TERMS)


def _load_home_assistant_display_data() -> dict[str, Any]:
    token = home_assistant_token()
    if not token:
        return {"available": False, "diagnostic": {"token_present": False, "attempts": []}}
    states = None
    attempts = []
    # Supervisor tokens are valid through the Supervisor proxy.  Reusing one
    # against Core's direct port produces an invalid-auth warning during Core
    # startup and cannot improve recovery, so keep this request on the
    # authenticated proxy only.
    for url in ("http://supervisor/core/api/states",):
        try:
            request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(request, timeout=6) as response:
                states = json.loads(response.read())
            break
        except urllib.error.HTTPError as error:
            attempts.append({"host": urllib.parse.urlparse(url).hostname, "status": error.code})
        except Exception as error:
            attempts.append({"host": urllib.parse.urlparse(url).hostname, "error": type(error).__name__})
    if states is None:
        return {"available": False, "diagnostic": {"token_present": True, "attempts": attempts}}

    state_map = {item.get("entity_id"): item for item in states}
    cellar_entities = live_sensor_entity_ids(get_settings())
    cellar_sensor_states = {entity_id: state_map[entity_id] for entity_id in cellar_entities if entity_id in state_map}
    weather_entities = resolve_gw2000_entities(states, get_settings().gw2000_entity_prefix)
    camera_setting = str(runtime_option("tv_camera_entities", get_settings().tv_camera_entities))
    configured_cameras = [value.strip() for value in camera_setting.split(",") if value.strip().startswith("camera.")]
    access_cameras = sorted(str(item.get("entity_id")) for item in states if is_access_camera(str(item.get("entity_id") or ""), str((item.get("attributes") or {}).get("friendly_name") or "")))
    # A saved list is exact: removed cameras must disappear from the TV page.
    # Gate/door discovery remains the no-configuration fallback.
    camera_ids = list(dict.fromkeys(configured_cameras or access_cameras))
    entrance_cameras = []
    vineyard_cameras = []
    for entity_id in camera_ids:
        item = state_map.get(entity_id) or {}
        attributes = item.get("attributes") or {}
        base = entity_id.removeprefix("camera.")
        capabilities = attributes.get("capabilities") if isinstance(attributes.get("capabilities"), dict) else {}
        activity = [
            label
            for label, suffix in (("MOTION", "motion_detected"), ("PERSON", "person_detected"), ("VEHICLE", "vehicle_detected"), ("PET", "pet_detected"))
            if str((state_map.get(f"binary_sensor.{base}_{suffix}") or {}).get("state") or "").casefold() == "on"
        ]
        battery_state = (state_map.get(f"sensor.{base}_battery") or {}).get("state")
        try:
            battery = round(float(battery_state))
        except (TypeError, ValueError):
            battery = None
        camera = {
            "entity_id": entity_id,
            "name": attributes.get("friendly_name") or base.replace("_", " ").title(),
            "available": item.get("state") not in {None, "unavailable", "unknown"},
            "ptz": bool(capabilities.get("ptz")),
            "battery": battery,
            "activity": activity,
        }
        target = entrance_cameras if is_access_camera(entity_id, str(attributes.get("friendly_name") or "")) else vineyard_cameras
        if len(target) < 6:
            target.append(camera)
    cameras = [*entrance_cameras, *vineyard_cameras]

    solar = solar_energy_summary(states)
    current = solar["current_power"]
    today = solar["energy_today"]
    forecast_today = solar["forecast_energy_today"]
    forecast_points = solar["forecast_points"]
    power_indicators = build_power_indicators(states, current)
    network_setting = str(runtime_option("network_equipment_entities", get_settings().network_equipment_entities))
    network_equipment = find_network_equipment(states, network_setting)
    lte_status = find_lte_status(states)
    def sensor(entity_id: str) -> float | None:
        try:
            return float((state_map.get(entity_id) or {}).get("state"))
        except (TypeError, ValueError):
            return None
    weather_source_ids = [entity_id for entity_id in weather_entities.values() if entity_id]
    weather_timestamps = [
        str((state_map.get(entity_id) or {}).get("last_updated"))
        for entity_id in weather_source_ids
        if (state_map.get(entity_id) or {}).get("last_updated")
    ]
    live_weather = {
        "observed_at": max(weather_timestamps) if weather_timestamps else date.today().isoformat(),
        "temp_c": sensor(weather_entities.get("temp_c", "")),
        "humidity_pct": sensor(weather_entities.get("humidity_pct", "")),
        "rain_mm": sensor(weather_entities.get("rain_mm", "")),
        "wind_kph": sensor(weather_entities.get("wind_kph", "")),
        "wind_gust_kph": sensor(weather_entities.get("wind_gust_kph", "")),
        "pressure_hpa": sensor(weather_entities.get("pressure_hpa", "")),
        "solar_wm2": sensor(weather_entities.get("solar_wm2", "")),
        "uv_index": sensor(weather_entities.get("uv_index", "")),
        "soil_moisture_pct": sensor(weather_entities.get("soil_moisture_1", "")),
    }

    def service_response(domain: str, service: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = urllib.request.Request(
                f"http://supervisor/core/api/services/{domain}/{service}?return_response",
                data=json.dumps(payload).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                result = json.loads(response.read())
            return result.get("service_response") or result
        except Exception:
            return {}

    weather_ids = [
        str(item.get("entity_id")) for item in states
        if str(item.get("entity_id") or "").startswith("weather.")
        and item.get("state") not in {None, "unknown", "unavailable"}
    ]
    preferred_weather = next(
        (entity_id for entity_id in weather_ids if any(term in entity_id.casefold() for term in ("baiamonte", "ecowitt", "gw2000", "home"))),
        weather_ids[0] if weather_ids else None,
    )
    if preferred_weather:
        live_weather["condition"] = (state_map.get(preferred_weather) or {}).get("state")
    forecast_data = service_response("weather", "get_forecasts", {
        "entity_id": [preferred_weather],
        "type": "daily",
    }) if preferred_weather else {}
    forecast_rows = ((forecast_data.get(preferred_weather) or {}).get("forecast") or []) if preferred_weather else []
    if not forecast_rows and preferred_weather:
        forecast_rows = ((state_map.get(preferred_weather) or {}).get("attributes") or {}).get("forecast") or []
    # The scheduled MariaDB mirror is authoritative for the app view. It
    # provides deduplication, survives temporary Google outages and reports a
    # genuine successful sync instead of merely finding an entity name.
    planning = planning_view()
    return {"available": True, "solar_available": bool(current or forecast_today), "current_power": current, "energy_today": today, "forecast_energy_today": forecast_today, "forecast_energy_remaining": solar["forecast_energy_remaining"], "forecast_energy_tomorrow": solar["forecast_energy_tomorrow"], "forecast_range_today": solar["forecast_range_today"], "forecast_range_remaining": solar["forecast_range_remaining"], "forecast_range_tomorrow": solar["forecast_range_tomorrow"], "solar_forecast": forecast_points, "solar_sources": {"actual": solar["actual_source"], "forecast": solar["forecast_source"], "forecast_available": solar["forecast_available"]}, "inventory": home_assistant_inventory(states), "power_indicators": power_indicators, "network_equipment": network_equipment, "lte_status": lte_status, "cameras": cameras, "entrance_cameras": entrance_cameras, "vineyard_cameras": vineyard_cameras, "live_weather": live_weather, "weather_forecast": forecast_rows[:7], "weather_forecast_entity": preferred_weather, "media": find_baiamonte_media(states), "planning": planning, "cellar_sensor_states": cellar_sensor_states}


# Home Assistant's full state inventory and daily forecast are shared by the
# operational UI, worker portal and TV payload. None of those consumers needs
# a second copy inside the station's normal 15-minute ingestion cadence. A
# short 30-second snapshot keeps controls responsive while coalescing bursts
# from several tablets, televisions and browser tabs.
_HA_CACHE_SECONDS = 30
_ha_cache: tuple[float, dict[str, Any]] | None = None
_ha_cache_lock = threading.Lock()


def _home_assistant_display_data(force: bool = False) -> dict[str, Any]:
    """Reuse one short-lived Core snapshot across API and TV consumers.

    A full Home Assistant state inventory is comparatively expensive and the
    operations UI can request status, weather and TV data at nearly the same
    moment.  Ten seconds keeps controls and weather current while preventing
    duplicate state inventories and forecast service calls.
    """
    global _ha_cache
    now = time.monotonic()
    if not force and _ha_cache and now - _ha_cache[0] < _HA_CACHE_SECONDS:
        return _ha_cache[1]
    with _ha_cache_lock:
        now = time.monotonic()
        if not force and _ha_cache and now - _ha_cache[0] < _HA_CACHE_SECONDS:
            return _ha_cache[1]
        payload = _load_home_assistant_display_data()
        _ha_cache = (time.monotonic(), payload)
        return payload


def system_status_payload(home_assistant: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    controls = process_controls()
    home_assistant = home_assistant if home_assistant is not None else _home_assistant_display_data()
    checkpoints = {row["integration_name"]: row for row in fetch_all(
        "SELECT integration_name,last_success_at,last_attempt_at,last_error FROM sync_checkpoints WHERE estate_id=%s",
        (estate_id(),),
    )}
    weather = checkpoints.get("home_assistant_gw2000_history") or {}
    publisher = checkpoints.get("public_harvest_publisher") or {}
    # Upgraded databases can retain a different utf8mb4 collation on older
    # operational tables. Keep acknowledgement joins explicit so a benign
    # collation difference never turns the entire status endpoint into a 500.
    collation = "utf8mb4_unicode_ci"
    failed_intake_rows = fetch_all(
        "SELECT i.title,i.original_filename,i.processing_error FROM intake_items i WHERE i.estate_id=%s AND i.review_status='failed' "
        "AND i.received_at>=NOW()-INTERVAL 7 DAY AND NOT EXISTS ("
        f"SELECT 1 FROM error_acknowledgements a WHERE a.estate_id COLLATE {collation}=i.estate_id COLLATE {collation} "
        f"AND a.error_kind='intake' AND a.record_id COLLATE {collation}=CAST(i.id AS CHAR) COLLATE {collation}"
        ") ORDER BY i.received_at DESC",
        (estate_id(),),
    )
    failed_integration_rows = fetch_all(
        "SELECT current_event.integration_name,current_event.error_message FROM integration_events current_event "
        "WHERE current_event.estate_id=%s AND current_event.status='failed' "
        "AND current_event.integration_name<>'whatsapp-channel' "
        "AND current_event.occurred_at>=NOW()-INTERVAL 24 HOUR "
        f"AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a WHERE a.estate_id COLLATE {collation}=current_event.estate_id COLLATE {collation} "
        f"AND a.error_kind='integration' AND a.record_id COLLATE {collation}=CAST(current_event.id AS CHAR) COLLATE {collation}) "
        "AND NOT EXISTS ("
        "SELECT 1 FROM integration_events newer_event "
        "WHERE newer_event.estate_id=current_event.estate_id "
        "AND newer_event.integration_name=current_event.integration_name "
        "AND newer_event.event_type=current_event.event_type "
        "AND (newer_event.occurred_at>current_event.occurred_at "
        "OR (newer_event.occurred_at=current_event.occurred_at AND newer_event.id>current_event.id))"
        ") "
        "ORDER BY current_event.occurred_at DESC",
        (estate_id(),),
    )
    live_weather = home_assistant.get("live_weather") or {}
    has_live_weather = any(value is not None for key, value in live_weather.items() if key != "observed_at")
    if not home_assistant.get("available"):
        weather_state, weather_detail = "red", "Home Assistant weather access is unavailable"
    elif not has_live_weather:
        weather_state, weather_detail = "red", "GW2000 weather entities are unavailable in Home Assistant"
    elif weather.get("last_error"):
        weather_state, weather_detail = "red", str(weather["last_error"])
    else:
        weather_state = "green"
        weather_detail = "Live station data" + (" · history updated " + str(weather.get("last_success_at")) if weather.get("last_success_at") else "")
    runtime = processing_runtime_snapshot()
    active_jobs = runtime.get("jobs") or []
    timed_out_jobs = [item for item in active_jobs if item.get("state") == "timed_out"]
    if controls["paused"]:
        processing_state, processing_detail = "off", "Scheduler paused"
    elif timed_out_jobs:
        processing_state = "amber"
        processing_detail = f"{len(active_jobs)} active · {len(timed_out_jobs)} exceeded the expected run time"
    elif active_jobs:
        names = ", ".join(str(item.get("code") or item.get("integration_name")).replace("_", " ") for item in active_jobs[:3])
        processing_state, processing_detail = "amber", f"Running {names}"
    else:
        processing_state, processing_detail = "green", "Idle"
    all_error_details = [
        f"{str(row.get('integration_name') or 'Process').replace('-', ' ')}: {row.get('error_message') or 'Update failed'}"
        for row in failed_integration_rows
    ] + [
        f"{row.get('title') or row.get('original_filename') or 'Inbox item'}: {row.get('processing_error') or 'Processing failed'}"
        for row in failed_intake_rows
    ]
    active_processing_errors = len(all_error_details)
    error_details = all_error_details[:10]
    if active_processing_errors > len(error_details):
        error_details.append(f"And {active_processing_errors - len(error_details)} more; open Operations Control for the full list")
    errors_state = "red" if active_processing_errors else "green"
    errors_detail = "No unresolved errors" if not error_details else "\n".join(error_details)
    if controls["paused"] or not controls["processes"]["public_feed"]["enabled"]:
        publisher_state, publisher_detail = "off", "Publishing paused"
    elif not settings.public_publish_url:
        publisher_state, publisher_detail = "off", "Website connection not configured"
    elif not settings.public_publish_token:
        publisher_state, publisher_detail = "red", "Website publish token missing"
    elif publisher.get("last_error"):
        publisher_state, publisher_detail = "red", str(publisher["last_error"])
    elif publisher.get("last_success_at"):
        last_success = publisher["last_success_at"]
        age_minutes = max(0, int((datetime.now() - last_success).total_seconds() / 60)) if isinstance(last_success, datetime) else None
        stale_after = controls["processes"]["public_feed"]["interval_minutes"] * 2 + 2
        if age_minutes is not None and age_minutes > stale_after:
            publisher_state, publisher_detail = "red", f"Publish overdue · last sent {last_success}"
        else:
            publisher_state, publisher_detail = "green", "Last sent " + str(last_success)
    else:
        publisher_state, publisher_detail = "amber", "Waiting for first website publish"
    services = [
        {"code": "database", "name": "Database", "state": "green", "detail": "Connected"},
        {"code": "weather", "name": "GW2000 weather", "state": weather_state, "detail": weather_detail},
        {"code": "ai", "name": "AI analysis", "state": "green" if settings.openai_api_key else "amber", "detail": "Ready" if settings.openai_api_key else "API key not configured"},
        {"code": "gmail", "name": "Mail intake", "state": "off" if controls["paused"] or not controls["processes"]["gmail"]["enabled"] else "green" if settings.gmail_address and settings.gmail_app_password else "off", "detail": "Paused" if controls["paused"] or not controls["processes"]["gmail"]["enabled"] else f"Every {controls['processes']['gmail']['interval_minutes']} min" if settings.gmail_address and settings.gmail_app_password else "Not configured"},
        {"code": "publisher", "name": "Public feed", "state": publisher_state, "detail": publisher_detail},
        {"code": "processing", "name": "Processing", "state": processing_state, "detail": processing_detail, "active_count": len(active_jobs), "jobs": active_jobs},
        {"code": "errors", "name": "Errors", "state": errors_state, "detail": errors_detail, "error_count": active_processing_errors, "details": error_details},
        home_assistant.get("lte_status") or {"code": "lte", "name": "LTE", "state": "off", "detail": "Status entity not detected"},
    ]
    overall = "red" if any(item["state"] == "red" for item in services) else "amber" if any(item["state"] == "amber" for item in services) else "green"
    return {
        "overall": overall,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "services": services,
        "power": home_assistant.get("power_indicators", []),
        "network": home_assistant.get("network_equipment", []),
        "solar": {"current_power": home_assistant.get("current_power"), "energy_today": home_assistant.get("energy_today"), "forecast_energy_today": home_assistant.get("forecast_energy_today"), "forecast_energy_remaining": home_assistant.get("forecast_energy_remaining"), "forecast_energy_tomorrow": home_assistant.get("forecast_energy_tomorrow"), "range_today": home_assistant.get("forecast_range_today"), "range_remaining": home_assistant.get("forecast_range_remaining"), "range_tomorrow": home_assistant.get("forecast_range_tomorrow"), "forecast": home_assistant.get("solar_forecast", []), "sources": home_assistant.get("solar_sources", {})},
        "inventory": home_assistant.get("inventory") or {},
        "media": home_assistant.get("media"),
        "planning": home_assistant.get("planning") or {"events": [], "items": [], "calendar_connected": False, "tasks_connected": False},
        "cistern_level": latest_cistern_level(),
        "vineyard_visual": vineyard_visual_status(),
    }


def weather_context_payload() -> dict[str, Any]:
    """Return current GW2000 readings and the Home Assistant daily forecast."""
    home_assistant = _home_assistant_display_data()
    current = home_assistant.get("live_weather") or {}
    forecast = home_assistant.get("weather_forecast") or []
    return json_ready({
        "available": bool(home_assistant.get("available")),
        "current": current,
        "forecast": forecast,
        "advisories": severe_weather_advisories(current, forecast),
        "forecast_entity": home_assistant.get("weather_forecast_entity"),
    })


def communications_display_payload(settings: Any | None = None) -> dict[str, Any]:
    """Return a compact, privacy-aware communications summary for the public TV."""
    settings = settings or get_settings()
    current_estate_id = estate_id()
    review_condition = _communications_review_condition("i")
    count_rows = fetch_all(
        "SELECT i.source,COUNT(*) total,"
        "SUM(i.review_status IN ('new','processing')) new_total,"
        f"SUM(i.review_status='ready_for_review' AND {review_condition}) review_total,"
        "SUM(i.review_status='failed') failed_total "
        "FROM intake_items i WHERE i.estate_id=%s AND i.source IN ('gmail','whatsapp','imessage') "
        "AND i.received_at>=NOW()-INTERVAL 24 HOUR GROUP BY i.source",
        (current_estate_id,),
    )
    counts = {str(row["source"]): row for row in count_rows}
    recent = fetch_all(
        "SELECT source,sender_name,received_at,title,classification,review_status,"
        "LEFT(COALESCE(ai_summary,''),180) summary "
        "FROM intake_items WHERE estate_id=%s AND source IN ('gmail','whatsapp') "
        "AND review_status<>'archived' "
        "ORDER BY received_at DESC LIMIT 12",
        (current_estate_id,),
    )
    review_items = fetch_all(
        "SELECT i.source,i.sender_name,i.received_at,i.title,i.classification,i.review_status "
        "FROM intake_items i WHERE i.estate_id=%s AND i.source IN ('gmail','whatsapp') "
        f"AND {review_condition} "
        "ORDER BY FIELD(i.review_status,'failed','ready_for_review','processing','new'),i.received_at DESC LIMIT 8",
        (current_estate_id,),
    )
    events = fetch_all(
        "SELECT integration_name,status,event_type,error_message,occurred_at FROM integration_events "
        "WHERE estate_id=%s AND integration_name IN ('gmail-mailbox','whatsapp-channel') "
        "AND occurred_at>=NOW()-INTERVAL 7 DAY "
        "ORDER BY occurred_at DESC,id DESC LIMIT 80",
        (current_estate_id,),
    )
    latest_events: dict[str, dict[str, Any]] = {}
    latest_event_types: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        latest_events.setdefault(str(event.get("integration_name") or ""), event)
        latest_event_types.setdefault((str(event.get("integration_name") or ""), str(event.get("event_type") or "")), event)
    failed_events = [event for event in latest_event_types.values() if event.get("status") == "failed"][:5]
    failed_intake = [item for item in review_items if item.get("review_status") == "failed"]

    channel_specs = (
        ("gmail", "Gmail", bool(settings.gmail_address and settings.gmail_app_password), "gmail-mailbox"),
        ("whatsapp", "WhatsApp", bool(settings.whatsapp_access_token and whatsapp_phone_number_id()), "whatsapp-channel"),
    )
    channels = []
    for code, name, configured, integration_name in channel_specs:
        latest = latest_events.get(integration_name) or {}
        source_count = counts.get(code) or {}
        if not configured:
            state, detail = "off", "Not configured"
        elif latest.get("status") == "failed":
            state, detail = "red", "Latest action failed"
        elif latest:
            state, detail = "green", f"{int(source_count.get('total') or 0)} received in 24h"
        else:
            state, detail = "amber", "Configured · waiting for activity"
        channels.append({
            "code": code,
            "name": name,
            "state": state,
            "detail": detail,
            "last_activity": latest.get("occurred_at"),
        })

    alerts = [
        {
            "title": f"{str(event.get('integration_name') or 'Communications').replace('-channel','').replace('-mailbox','').title()} error",
            "detail": str(event.get("error_message") or event.get("event_type") or "Message processing failed")[:180],
            "occurred_at": event.get("occurred_at"),
            "severity": "error",
        }
        for event in failed_events
    ]
    alerts.extend({
        "title": str(item.get("title") or f"{str(item.get('source') or 'Message').title()} item failed"),
        "detail": "Open Vineyard Operations to review the processing error.",
        "occurred_at": item.get("received_at"),
        "severity": "error",
    } for item in failed_intake[:3])
    total_24h = sum(int(row.get("total") or 0) for row in count_rows)
    new_total = sum(int(row.get("new_total") or 0) for row in count_rows)
    review_total = sum(int(row.get("review_total") or 0) for row in count_rows)
    failed_total = sum(int(row.get("failed_total") or 0) for row in count_rows) + len(failed_events)
    return {
        "metrics": {
            "received_24h": total_24h,
            "mail_24h": int((counts.get("gmail") or {}).get("total") or 0),
            "new_items": new_total,
            "needs_review": review_total,
            "problems": failed_total,
        },
        "channels": channels,
        "recent": recent,
        "review": review_items,
        "alerts": alerts[:6],
        "privacy_note": "At-a-glance summaries only · full message content stays in Vineyard Operations",
    }


def _build_display_payload(year: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    if year is None:
        try:
            year = datetime.now(ZoneInfo(settings.tv_time_zone or "Europe/Rome")).year
        except (ZoneInfoNotFoundError, ValueError):
            year = date.today().year
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    season_id = season.get("id", "")
    planned = (fetch_one("SELECT SUM(planned_kg) n FROM harvest_plans WHERE season_id=%s", (season_id,)) or {}).get("n")
    harvested = (fetch_one("SELECT SUM(weight_kg) n FROM harvest_lots WHERE season_id=%s", (season_id,)) or {}).get("n")
    completion = round(float(harvested or 0) / float(planned) * 100, 1) if planned else None
    estate = fetch_one("SELECT name,total_area_ha,latitude,longitude FROM estates WHERE id=%s", (estate_id(),)) or {}
    vineyard = fetch_one("SELECT COUNT(*) block_count,COALESCE(SUM(area_ha),0) vineyard_area_ha,COALESCE(SUM(vine_count),0) vine_count FROM vineyard_blocks WHERE estate_id=%s AND active=1", (estate_id(),)) or {}
    varieties = (fetch_one("SELECT COUNT(*) n FROM grape_varieties WHERE estate_id=%s AND active=1", (estate_id(),)) or {"n": 0})["n"]
    home_assistant = _home_assistant_display_data()
    latest_pressure = fetch_all(
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2') ORDER BY risk_score DESC",
        (estate_id(), estate_id()),
    )
    pressure_history = fetch_all(
        "SELECT disease_code,disease_name,assessment_date,risk_score,risk_level FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date,disease_code",
        (estate_id(),),
    )
    planned_treatments = fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s AND crop_scope='vineyard' AND status='planned' ORDER BY application_date", (estate_id(),))
    database_weather = fetch_all(
        "SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph,wind_gust_kph,pressure_hpa,solar_wm2,uv_index,soil_moisture_pct "
        "FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 48",
        (estate_id(),),
    )[::-1]
    live_weather = home_assistant.get("live_weather") or {}
    weather_forecast = home_assistant.get("weather_forecast") or []
    weather_alerts = severe_weather_advisories(live_weather, weather_forecast)
    # The TV's Today view must always end on the current station reading;
    # database rows remain available immediately before it for context.
    database_weather = merge_display_weather(database_weather, live_weather)
    vintage_history = reconciled_vintage_history(all_vintage_rows())
    conversion, forecast_evidence = historical_forecast_evidence(year, vintage_history)
    production_forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg,crates_15kg,source,notes,updated_at FROM production_forecasts "
        "WHERE estate_id=%s AND scenario='base' AND vintage_year BETWEEN %s AND %s ORDER BY vintage_year,variety_name",
        (estate_id(), year, year + 5),
    )
    production_forecasts = adjust_production_forecasts(production_forecasts, year)
    blend = fetch_one(
        "SELECT SUM(target_grapes_kg) target_grapes_kg,SUM(COALESCE(target_volume_l,target_grapes_kg*expected_yield_l_per_kg)) target_volume_l "
        "FROM blend_plans WHERE season_id=%s",
        (season_id,),
    ) or {}
    blend_plans = fetch_all(
        "SELECT code,name,target_grapes_kg,target_volume_l,planned_bottles,components_text,planned_blend_date,decision_status "
        "FROM blend_plans WHERE season_id=%s ORDER BY planned_blend_date IS NULL,planned_blend_date,code",
        (season_id,),
    )
    blend_settings = fetch_one(
        "SELECT grenache_pct,crate_weight_kg,expected_yield_l_per_kg,tank_working_fill_pct "
        "FROM blend_program_settings WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    crate_weight = float(blend_settings.get("crate_weight_kg") or 15)
    planning_conversion = float(blend_settings.get("expected_yield_l_per_kg") or conversion)
    selected_forecasts = [row for row in production_forecasts if int(row.get("vintage_year") or 0) == year]
    has_adjusted_forecast = bool(selected_forecasts)

    def adjusted_forecast_amount(name: str) -> float:
        match = next((row for row in selected_forecasts if name in str(row.get("variety_name") or "").casefold()), None)
        return float((match or {}).get("adjusted_grape_kg", (match or {}).get("grape_kg")) or 0)

    adjusted_program = calculate_blend_program(
        nerello_kg=adjusted_forecast_amount("nerello"),
        grenache_available_kg=adjusted_forecast_amount("grenache"),
        grecanico_kg=adjusted_forecast_amount("grecanico"),
        grenache_pct=float(blend_settings.get("grenache_pct") or 6.5),
        crate_weight_kg=crate_weight,
        yield_l_per_kg=planning_conversion,
        tank_working_fill_pct=float(blend_settings.get("tank_working_fill_pct") or 90),
    )
    adjusted_basis_kg = sum(float(adjusted_program.get(field) or 0) for field in ("nerello_kg", "grenache_available_kg", "grecanico_kg"))
    basis_kg = adjusted_basis_kg if has_adjusted_forecast else blend.get("target_grapes_kg") if blend.get("target_grapes_kg") is not None else planned
    adjusted_wine_l = sum(float(row.get("wine_l") or 0) for row in adjusted_program["wines"])
    basis_wine_l = adjusted_wine_l if has_adjusted_forecast else blend.get("target_volume_l") if blend.get("target_volume_l") is not None else (float(basis_kg) * planning_conversion if basis_kg is not None else None)
    scenario_range = float(forecast_evidence.get("recommended_scenario_range_pct") or 15) / 100
    projection_scenarios = []
    for name, factor in (("Downside", 1 - scenario_range), ("Working", 1.0), ("Upside", 1 + scenario_range)):
        kg = float(basis_kg) * factor if basis_kg is not None else None
        wine_l = float(basis_wine_l) * factor if basis_wine_l is not None else None
        projection_scenarios.append({
            "name": name,
            "grapes_kg": kg,
            "wine_l": wine_l,
            "bottle_equivalents": wine_l / 0.75 if wine_l is not None else None,
            "crates_15kg": kg / 15 if kg is not None else None,
        })
    prior_vintage = next((row for row in reversed(vintage_history) if int(row["vintage_year"]) < year), None)
    cellar_demo = demo_enabled(settings)
    if cellar_demo:
        cellar_payload = demo_cellar(settings, year)
        cellar_tanks = cellar_payload["tanks"]
        cellar_processes = cellar_payload["processes"]
    else:
        cellar_tanks = fetch_all(
            "SELECT c.id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.sensor_entity_id,c.status,"
            "w.id wine_lot_id,w.code lot_code,w.name lot_name,COALESCE(w.stage,cp.manual_stage) stage,COALESCE(w.volume_l,cp.manual_volume_l) volume_l,COALESCE(w.variety_summary,cp.manual_contents) variety_summary,cp.wine_color,w.started_at,"
            "COALESCE((SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_temp_c) temp_c,"
            "COALESCE((SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_density_sg) density_sg,"
            "COALESCE((SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_brix) brix,"
            "COALESCE((SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_ph) ph,"
            "COALESCE((SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_reading_at) reading_at,"
            "(SELECT f.next_check_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) next_check_at,"
            "COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status "
            "FROM cellar_containers c LEFT JOIN wine_lots w ON w.id=("
            "SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.season_id=%s "
            "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1) "
            "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
            "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
            (season_id, estate_id()),
        )
        for tank in cellar_tanks:
            capacity = float(tank.get("capacity_l") or 0)
            volume = float(tank.get("volume_l") or 0)
            tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
            tank["source"] = "Manual record"
        configured_keys = live_sensor_tank_keys(settings)
        sensor_tanks = []
        for tank in cellar_tanks:
            sensor_configured = bool(
                tank.get("sensor_entity_id")
                or str(tank.get("code") or "").casefold() in configured_keys
                or str(tank.get("name") or "").casefold() in configured_keys
            )
            tank["sensor_configured"] = sensor_configured
            if tank.get("reading_mode") == "sensor" and sensor_configured:
                sensor_tanks.append(tank)
        apply_live_sensor_readings(sensor_tanks, settings, home_assistant.get("cellar_sensor_states") or {})
        cellar_processes = fetch_all(
            "SELECT f.id,f.observed_at,f.vessel_name,f.stage,f.temp_c,f.density_sg,f.brix,f.ph,f.cap_management,f.addition_action,f.sensory_observation,f.owner_text,f.next_check_at,f.status,w.code lot_code,w.name lot_name "
            "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id WHERE f.estate_id=%s "
            "AND (w.season_id=%s OR w.season_id IS NULL) ORDER BY COALESCE(f.next_check_at,f.observed_at) DESC LIMIT 12",
            (estate_id(), season_id),
        )
    latest_lab = fetch_one(
        "SELECT s.id,s.sample_name,s.sample_type,s.lab_date,s.laboratory,s.needs_review,"
        "r.review_status,r.interpretation,r.decision_action,r.next_check_at,r.enologist_approval_required,r.approved_by "
        "FROM lab_samples s LEFT JOIN lab_reviews r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s ORDER BY s.lab_date DESC,s.id DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    latest_lab_results = fetch_all(
        "SELECT analyte_name,numeric_value,text_value,unit,flag FROM lab_results "
        "WHERE sample_id=%s ORDER BY FIELD(flag,'high','low','review','normal'),analyte_name LIMIT 6",
        (latest_lab.get("id") or "",),
    ) if latest_lab else []
    flagged_lab_results = [row for row in latest_lab_results if str(row.get("flag") or "").casefold() not in {"", "normal", "none"}]
    lab_suggestion = latest_lab.get("decision_action") or latest_lab.get("interpretation")
    if not lab_suggestion and flagged_lab_results:
        lab_suggestion = "Review flagged results with the enologist before any cellar action."
    if not lab_suggestion and latest_lab:
        lab_suggestion = "No flagged values in the latest sample; continue the recorded monitoring schedule."
    cellar_guard_alerts = evaluate_cellar_tanks(cellar_tanks, settings)
    etna_payload = etna_status()
    airport_payload = airport_status(etna_payload)
    calculated_allocations = [
        {"grape_name": "Grecanico", "total_kg": adjusted_program["grecanico_kg"], "total_crates_15kg": math.ceil(adjusted_program["grecanico_kg"] / crate_weight - 1e-9) if adjusted_program["grecanico_kg"] else 0, "wine_destination": "Grecanico · 100% varietal"},
        {"grape_name": "Nerello Mascalese", "total_kg": adjusted_program["nerello_kg"], "total_crates_15kg": math.ceil(adjusted_program["nerello_kg"] / crate_weight - 1e-9) if adjusted_program["nerello_kg"] else 0, "wine_destination": f"Nerello blend · {adjusted_program['nerello_pct']:g}%"},
        {"grape_name": "Grenache", "total_kg": adjusted_program["grenache_available_kg"], "total_crates_15kg": math.ceil(adjusted_program["grenache_available_kg"] / crate_weight - 1e-9) if adjusted_program["grenache_available_kg"] else 0, "wine_destination": f"{adjusted_program['required_grenache_kg']:g} kg to Nerello blend · {adjusted_program['remaining_grenache_kg']:g} kg to 100% Grenache"},
    ]
    grape_allocations = calculated_allocations if has_adjusted_forecast else fetch_all(
        "SELECT grape_name,total_kg,total_crates_15kg,wine_destination,blend_kg,blend_crates_15kg,varietal_kg,varietal_crates_15kg,field_instruction "
        "FROM grape_allocation_plans WHERE estate_id=%s AND vintage_year=%s ORDER BY grape_name",
        (estate_id(), year),
    )
    wine_outputs = adjusted_program["wines"] if has_adjusted_forecast else fetch_all(
        "SELECT finished_wine,composition,grape_kg,wine_l,bottles_750ml FROM wine_output_plans "
        "WHERE estate_id=%s AND vintage_year=%s ORDER BY finished_wine",
        (estate_id(), year),
    )
    forecast_totals = []
    for forecast_year in sorted({int(row["vintage_year"]) for row in production_forecasts}):
        rows = [row for row in production_forecasts if int(row["vintage_year"]) == forecast_year]
        total_kg = sum(float(row.get("adjusted_grape_kg", row.get("grape_kg")) or 0) for row in rows)
        forecast_totals.append({
            "vintage_year": forecast_year,
            "grape_kg": total_kg,
            "crates_15kg": round(total_kg / 15),
            "baseline_grape_kg": sum(float(row.get("baseline_grape_kg", row.get("grape_kg")) or 0) for row in rows),
            "wine_l": round(total_kg * planning_conversion),
            "bottles_750ml": int(total_kg * planning_conversion / 0.75),
            "sources": sorted({str(row.get("source") or "unlabelled") for row in rows}),
        })
    return json_ready({
        "year": year,
        "display": {
            "time_zone": str(runtime_option("tv_time_zone", settings.tv_time_zone)) or "Europe/Rome",
            "cycle_seconds": max(10, int(runtime_option("tv_cycle_seconds", settings.tv_cycle_seconds))),
            "refresh_seconds": max(30, int(runtime_option("tv_refresh_seconds", settings.tv_refresh_seconds))),
            "vineyard_camera_page_enabled": bool(runtime_option("tv_vineyard_camera_page_enabled", settings.tv_vineyard_camera_page_enabled)),
            "map_brightness_percent": min(180, max(60, int(runtime_option("tv_map_brightness_percent", settings.tv_map_brightness_percent)))),
            "weather_zoom_level": min(6, max(0, int(runtime_option("tv_weather_zoom_level", settings.tv_weather_zoom_level)))),
            "adsb_zoom_level": min(20, max(-6, int(runtime_option("tv_adsb_zoom_level", settings.tv_adsb_zoom_level)))),
            "ais_zoom_level": min(20, max(-6, int(runtime_option("tv_ais_zoom_level", settings.tv_ais_zoom_level)))),
            "adsb_target_size_percent": min(180, max(30, int(runtime_option("tv_adsb_target_size_percent", settings.tv_adsb_target_size_percent)))),
            "ais_target_size_percent": min(180, max(30, int(runtime_option("tv_ais_target_size_percent", settings.tv_ais_target_size_percent)))),
            "theme": str(runtime_option("tv_theme", settings.tv_theme) or "auto"),
            "controls_enabled": bool(runtime_option("tv_controls_enabled", settings.tv_controls_enabled)),
            "home_airport_enabled": bool(runtime_option("tv_home_airport_enabled", settings.tv_home_airport_enabled)),
            "etna_enabled": bool(runtime_option("etna_enabled", settings.etna_enabled)),
        },
        "estate": {**estate, **vineyard, "variety_count": varieties, "location": "Contrada Baiamonte · Randazzo · Etna"},
        "solar": {
            "available": home_assistant.get("solar_available", False),
            "current_power": home_assistant.get("current_power"),
            "energy_today": home_assistant.get("energy_today"),
            "forecast_energy_today": home_assistant.get("forecast_energy_today"),
            "forecast_energy_remaining": home_assistant.get("forecast_energy_remaining"),
            "forecast_energy_tomorrow": home_assistant.get("forecast_energy_tomorrow"),
            "range_today": home_assistant.get("forecast_range_today"),
            "range_remaining": home_assistant.get("forecast_range_remaining"),
            "range_tomorrow": home_assistant.get("forecast_range_tomorrow"),
            "forecast": home_assistant.get("solar_forecast", []),
            "sources": home_assistant.get("solar_sources", {}),
        },
        "weather_forecast": weather_forecast,
        "weather_alerts": weather_alerts,
        "etna": etna_payload,
        "airport": airport_payload,
        "power_indicators": home_assistant.get("power_indicators", []),
        "cistern_level": latest_cistern_level(),
        "vineyard_visual": vineyard_visual_status(),
        "cameras": home_assistant.get("cameras", []),
        "entrance_cameras": home_assistant.get("entrance_cameras", []),
        "vineyard_cameras": home_assistant.get("vineyard_cameras", []),
        "system_status": system_status_payload(home_assistant),
        "communications": communications_display_payload(settings),
        "next_treatment_decision": predict_next_treatment(planned_treatments, latest_pressure),
        "dashboard": {
            "counts": {
                "open_tasks": (fetch_one("SELECT COUNT(*) n FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress')", (estate_id(),)) or {"n": 0})["n"],
                "harvest_kg": harvested,
                "work_hours": (fetch_one("SELECT SUM(labor_hours) n FROM work_activities WHERE season_id=%s", (season_id,)) or {}).get("n"),
                "open_alerts": (fetch_one("SELECT COUNT(*) n FROM alerts WHERE estate_id=%s AND status='open'", (estate_id(),)) or {"n": 0})["n"],
            },
            "tasks": fetch_all(
                "SELECT title,category,status,priority,due_date,(SELECT code FROM vineyard_blocks WHERE id=tasks.block_id) block_code "
                "FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
                "ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date LIMIT 12",
                (estate_id(),),
            ),
            "hospitality_events": fetch_all(
                "SELECT r.id,CONCAT('Hospitality · ',COALESCE(p.name,'Private experience')) title,"
                "r.status,r.start_at,r.end_at,r.guest_count,r.confirmation_code "
                "FROM hospitality_reservations r LEFT JOIN hospitality_packages p ON p.id=r.package_id "
                "WHERE r.estate_id=%s AND r.status IN ('requested','confirmed','arrived') "
                "AND r.start_at>=CURDATE() ORDER BY r.start_at LIMIT 12",
                (estate_id(),),
            ),
            "issues": fetch_all(
                "SELECT issue_text,issue_type,priority,status,due_date,subject_ref,owner_text,decision_action "
                "FROM issues_decisions WHERE estate_id=%s AND status IN ('open','monitoring') "
                "ORDER BY FIELD(priority,'critical','high','medium','low'),due_date IS NULL,due_date,opened_date DESC LIMIT 10",
                (estate_id(),),
            ),
            "alerts": fetch_all(
                "SELECT id,alert_type,severity,title,message,source_id,status,triggered_at,resolved_at FROM alerts "
                "WHERE estate_id=%s AND status='open' "
                "ORDER BY "
                "FIELD(severity,'critical','warning','info'),triggered_at DESC LIMIT 10",
                (estate_id(),),
            ),
            "weather": database_weather,
        },
        "grapes": {
            "metrics": {
                "planned_kg": planned,
                "harvested_kg": harvested,
                "completion_pct": completion,
                "cellar_volume_l": (fetch_one("SELECT SUM(volume_l) n FROM wine_lots WHERE season_id=%s", (season_id,)) or {}).get("n"),
            },
            "varieties": fetch_all(
                "SELECT v.name,p.planned_kg,p.planned_pick_date,p.plan_status,h.harvested_kg,"
                "CASE WHEN p.planned_kg>0 THEN ROUND(COALESCE(h.harvested_kg,0)/p.planned_kg*100,1) ELSE NULL END completion_pct "
                "FROM grape_varieties v LEFT JOIN (SELECT variety_id,SUM(planned_kg) planned_kg,MIN(planned_pick_date) planned_pick_date,"
                "GROUP_CONCAT(DISTINCT status SEPARATOR ', ') plan_status FROM harvest_plans WHERE season_id=%s GROUP BY variety_id) p ON p.variety_id=v.id "
                "LEFT JOIN (SELECT variety_id,SUM(weight_kg) harvested_kg FROM harvest_lots WHERE season_id=%s GROUP BY variety_id) h ON h.variety_id=v.id "
                "WHERE v.estate_id=%s AND v.active=1 AND LOWER(v.name) NOT IN ('blend','other') ORDER BY v.name",
                (season_id, season_id, estate_id()),
            ),
            "vintages": vintage_history,
            "prior_vintage": prior_vintage,
        },
        "projections": {
            "basis": "damage-adjusted production forecast" if has_adjusted_forecast else "current blend plan" if blend.get("target_grapes_kg") is not None else "harvest plan" if planned is not None else "missing",
            "historical_conversion_l_per_kg": conversion,
            "planning_conversion_l_per_kg": planning_conversion,
            "forecast_evidence": forecast_evidence,
            "scenarios": projection_scenarios,
            "working": next((row for row in projection_scenarios if row["name"] == "Working"), {}),
            "blend_plan": {
                "count": len(blend_plans),
                "target_grapes_kg": basis_kg,
                "target_volume_l": basis_wine_l,
                "crates_15kg": float(basis_kg) / crate_weight if basis_kg is not None else None,
                "plans": blend_plans,
            },
            "production_forecasts": production_forecasts,
            "production_forecast_totals": forecast_totals,
            "production_forecast_method": "Database planning records with vintage-isolated, approved damage assessments authoritative after Agronomist confirmation; structured AI event estimates are provisional until then.",
            "grape_allocations": grape_allocations,
            "wine_outputs": wine_outputs,
        },
        "cellar": {"year": year, "demo": cellar_demo, "tanks": cellar_tanks, "processes": cellar_processes, "guardrails": cellar_guardrails(settings), "guard_alerts": cellar_guard_alerts},
        "pressure": latest_pressure,
        "pressure_history": pressure_history,
        "labs": {"queue": fetch_all(
            "SELECT CONCAT(UPPER(LEFT(sample_type,1)),SUBSTRING(sample_type,2),' sample') sample_name,sample_type,flagged_results,review_status,lab_date "
            "FROM v_lab_decision_queue WHERE estate_id=%s AND (flagged_results>0 OR review_status IN ('decision_needed','reviewing')) ORDER BY lab_date DESC LIMIT 6",
            (estate_id(),),
        ), "latest": latest_lab, "latest_results": latest_lab_results, "suggestion": lab_suggestion},
        "weather": fetch_all(
            "SELECT YEAR(weather_date) weather_year,MONTH(weather_date) weather_month,AVG(temp_avg_c) temp_avg_c,SUM(COALESCE(rain_mm,0)) rain_mm "
            "FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date) BETWEEN %s AND %s GROUP BY YEAR(weather_date),MONTH(weather_date) ORDER BY weather_year,weather_month",
            (estate_id(), year - 3, year),
        ),
    })


# TV clients refresh every 120 seconds by default and can be staggered across
# rooms. Reusing one payload for 90 seconds prevents each screen from repeating
# the same database aggregation and Home Assistant inventory while still
# guaranteeing a newly built payload before the following normal refresh.
_DISPLAY_CACHE_SECONDS = 90
_display_cache: dict[int | None, tuple[float, dict[str, Any]]] = {}
_display_cache_lock = threading.Lock()


def display_payload(year: int | None = None, force: bool = False) -> dict[str, Any]:
    """Share one short-lived payload across TV viewers and API consumers."""
    now = time.monotonic()
    cached = _display_cache.get(year)
    if not force and cached and now - cached[0] < _DISPLAY_CACHE_SECONDS:
        return cached[1]
    with _display_cache_lock:
        now = time.monotonic()
        cached = _display_cache.get(year)
        if not force and cached and now - cached[0] < _DISPLAY_CACHE_SECONDS:
            return cached[1]
        payload = _build_display_payload(year)
        _display_cache[year] = (time.monotonic(), payload)
        return payload
