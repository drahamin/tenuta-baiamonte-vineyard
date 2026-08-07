"""Presentation-safe, read-only data for the vineyard entrance display."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import fetch_all, fetch_one
from .config import get_settings, runtime_option
from .ha_auth import home_assistant_token
from .ha_entities import build_power_indicators, find_baiamonte_media, find_network_equipment, merge_display_weather, resolve_gw2000_entities
from .service import estate_id, json_ready
from .intelligence import predict_next_treatment


ACCESS_CAMERA_TERMS = ("gate", "door", "entrance", "entry", "driveway", "access", "cancello", "porta", "ingresso")


def is_access_camera_entity(entity_id: str) -> bool:
    """Limit automatic TV discovery to camera IDs that clearly describe estate access."""
    normalized = entity_id.casefold()
    return normalized.startswith("camera.") and any(term in normalized for term in ACCESS_CAMERA_TERMS)


def is_access_camera(entity_id: str, friendly_name: str = "") -> bool:
    return entity_id.startswith("camera.") and any(term in f"{entity_id} {friendly_name}".casefold() for term in ACCESS_CAMERA_TERMS)


def _home_assistant_display_data() -> dict[str, Any]:
    token = home_assistant_token()
    if not token:
        return {"available": False, "diagnostic": {"token_present": False, "attempts": []}}
    states = None
    attempts = []
    for url in ("http://supervisor/core/api/states", "http://homeassistant:8123/api/states", "http://core-homeassistant:8123/api/states"):
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
    weather_entities = resolve_gw2000_entities(states, get_settings().gw2000_entity_prefix)
    camera_setting = str(runtime_option("tv_camera_entities", get_settings().tv_camera_entities))
    configured_cameras = [value.strip() for value in camera_setting.split(",") if value.strip().startswith("camera.")]
    all_cameras = sorted(str(item.get("entity_id")) for item in states if str(item.get("entity_id") or "").startswith("camera."))
    access_cameras = sorted(str(item.get("entity_id")) for item in states if is_access_camera(str(item.get("entity_id") or ""), str((item.get("attributes") or {}).get("friendly_name") or "")))
    discovered = access_cameras or all_cameras
    # A saved list is exact: removed cameras must disappear from the TV page.
    # Gate/door discovery remains the no-configuration fallback.
    camera_ids = list(dict.fromkeys(configured_cameras or discovered))[:6]
    cameras = []
    for entity_id in camera_ids:
        item = state_map.get(entity_id) or {}
        attributes = item.get("attributes") or {}
        cameras.append({"entity_id": entity_id, "name": attributes.get("friendly_name") or entity_id.removeprefix("camera.").replace("_", " ").title(), "available": item.get("state") not in {None, "unavailable", "unknown"}})

    candidates = []
    for item in states:
        attributes = item.get("attributes") or {}
        text = f"{item.get('entity_id','')} {attributes.get('friendly_name','')}".casefold()
        if any(word in text for word in ("solar", "photovoltaic", "inverter", "pv ", "pv_")):
            try:
                value = float(item.get("state"))
            except (TypeError, ValueError):
                continue
            candidates.append({"entity_id": item.get("entity_id"), "name": attributes.get("friendly_name") or item.get("entity_id"), "value": value, "unit": attributes.get("unit_of_measurement") or "", "device_class": attributes.get("device_class") or "", "text": text})

    def choose(kind: str, prefer: tuple[str, ...] = ()) -> dict[str, Any] | None:
        pool = [row for row in candidates if row["device_class"] == kind or (kind == "power" and row["unit"] in {"W", "kW"}) or (kind == "energy" and row["unit"] in {"Wh", "kWh", "MWh"})]
        pool.sort(key=lambda row: (not any(word in row["text"] for word in prefer), "total_solar_input" not in row["text"], row["name"]))
        return pool[0] if pool else None

    current = choose("power", ("current", "production", "solar power", "pv power"))
    today = choose("energy", ("today", "daily", "day"))
    if today and not any(word in today["text"] for word in ("today", "daily", " day")):
        today = None
    total = choose("energy", ("total_solar_input", "lifetime", "total"))
    power_indicators = build_power_indicators(states, current)
    network_setting = str(runtime_option("network_equipment_entities", get_settings().network_equipment_entities))
    network_equipment = find_network_equipment(states, network_setting)
    def sensor(entity_id: str) -> float | None:
        try:
            return float((state_map.get(entity_id) or {}).get("state"))
        except (TypeError, ValueError):
            return None
    live_weather = {
        "observed_at": date.today().isoformat(),
        "temp_c": sensor(weather_entities.get("temp_c", "")),
        "humidity_pct": sensor(weather_entities.get("humidity_pct", "")),
        "rain_mm": sensor(weather_entities.get("rain_mm", "")),
        "wind_kph": sensor(weather_entities.get("wind_kph", "")),
        "soil_moisture_pct": sensor(weather_entities.get("soil_moisture_1", "")),
    }

    def planning_entities(domain: str) -> list[str]:
        rows = []
        for item in states:
            entity_id = str(item.get("entity_id") or "")
            if not entity_id.startswith(domain + "."):
                continue
            attributes = item.get("attributes") or {}
            text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold()
            if any(term in text for term in ("baiamonte", "vineyard", "vigneto", "tenuta")):
                rows.append(entity_id)
        return rows

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

    calendar_ids = planning_entities("calendar")
    todo_ids = planning_entities("todo")
    start = datetime.now().astimezone()
    calendar_data = service_response("calendar", "get_events", {
        "entity_id": calendar_ids,
        "start_date_time": start.isoformat(),
        "end_date_time": (start + timedelta(days=45)).isoformat(),
    }) if calendar_ids else {}
    todo_data = service_response("todo", "get_items", {"entity_id": todo_ids}) if todo_ids else {}
    events = []
    for entity_id, result in calendar_data.items():
        for event in (result or {}).get("events", []):
            events.append({"entity_id": entity_id, **event})
    items = []
    for entity_id, result in todo_data.items():
        for item in (result or {}).get("items", []):
            items.append({"entity_id": entity_id, **item})
    events.sort(key=lambda item: str(item.get("start") or ""))
    items.sort(key=lambda item: (str(item.get("status") or "") == "completed", str(item.get("due") or "9999"), str(item.get("summary") or item.get("item") or "")))
    planning = {
        "calendar_entities": calendar_ids,
        "todo_entities": todo_ids,
        "events": events[:20],
        "items": items[:40],
        "calendar_connected": bool(calendar_ids),
        "tasks_connected": bool(todo_ids),
    }
    return {"available": True, "solar_available": bool(candidates), "current_power": current, "energy_today": today, "energy_total": total, "power_indicators": power_indicators, "network_equipment": network_equipment, "cameras": cameras, "live_weather": live_weather, "media": find_baiamonte_media(states), "planning": planning}


def system_status_payload(home_assistant: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    home_assistant = home_assistant if home_assistant is not None else _home_assistant_display_data()
    checkpoints = {row["integration_name"]: row for row in fetch_all(
        "SELECT integration_name,last_success_at,last_attempt_at,last_error FROM sync_checkpoints WHERE estate_id=%s",
        (estate_id(),),
    )}
    weather = checkpoints.get("home_assistant_gw2000_history") or {}
    publisher = checkpoints.get("public_harvest_publisher") or {}
    failed_intake = (fetch_one(
        "SELECT COUNT(*) n FROM intake_items WHERE estate_id=%s AND review_status='failed' AND received_at>=NOW()-INTERVAL 7 DAY",
        (estate_id(),),
    ) or {"n": 0})["n"]
    failed_integrations = (fetch_one(
        "SELECT COUNT(*) n FROM integration_events WHERE estate_id=%s AND status='failed' AND occurred_at>=NOW()-INTERVAL 24 HOUR",
        (estate_id(),),
    ) or {"n": 0})["n"]
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
    processing_state = "red" if failed_intake or failed_integrations else "green"
    if not settings.public_publish_url:
        publisher_state, publisher_detail = "off", "Website connection not configured"
    elif not settings.public_publish_token:
        publisher_state, publisher_detail = "red", "Website publish token missing"
    elif publisher.get("last_error"):
        publisher_state, publisher_detail = "red", str(publisher["last_error"])
    elif publisher.get("last_success_at"):
        publisher_state, publisher_detail = "green", "Last sent " + str(publisher["last_success_at"])
    else:
        publisher_state, publisher_detail = "amber", "Waiting for first website publish"
    services = [
        {"code": "database", "name": "Database", "state": "green", "detail": "Connected"},
        {"code": "weather", "name": "GW2000 weather", "state": weather_state, "detail": weather_detail},
        {"code": "ai", "name": "AI analysis", "state": "green" if settings.openai_api_key else "amber", "detail": "Ready" if settings.openai_api_key else "API key not configured"},
        {"code": "gmail", "name": "Mail intake", "state": "green" if settings.gmail_address and settings.gmail_app_password else "off", "detail": f"Every {settings.gmail_poll_minutes} min" if settings.gmail_address and settings.gmail_app_password else "Not configured"},
        {"code": "publisher", "name": "Public feed", "state": publisher_state, "detail": publisher_detail},
        {"code": "processing", "name": "Processing", "state": processing_state, "detail": f"{failed_intake + failed_integrations} recent error(s)" if failed_intake or failed_integrations else "No recent errors"},
    ]
    overall = "red" if any(item["state"] == "red" for item in services) else "amber" if any(item["state"] == "amber" for item in services) else "green"
    return {
        "overall": overall,
        "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "services": services,
        "power": home_assistant.get("power_indicators", []),
        "network": home_assistant.get("network_equipment", []),
        "media": home_assistant.get("media"),
        "planning": home_assistant.get("planning") or {"events": [], "items": [], "calendar_connected": False, "tasks_connected": False},
    }


def display_payload(year: int | None = None) -> dict[str, Any]:
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
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s) ORDER BY risk_score DESC",
        (estate_id(), estate_id()),
    )
    planned_treatments = fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s AND status='planned' ORDER BY application_date", (estate_id(),))
    database_weather = fetch_all("SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 48", (estate_id(),))[::-1]
    live_weather = home_assistant.get("live_weather") or {}
    # The TV's Today view must always end on the current station reading;
    # database rows remain available immediately before it for context.
    database_weather = merge_display_weather(database_weather, live_weather)
    return json_ready({
        "year": year,
        "display": {
            "time_zone": str(runtime_option("tv_time_zone", settings.tv_time_zone)) or "Europe/Rome",
            "cycle_seconds": max(10, int(runtime_option("tv_cycle_seconds", settings.tv_cycle_seconds))),
            "refresh_seconds": max(30, int(runtime_option("tv_refresh_seconds", settings.tv_refresh_seconds))),
        },
        "estate": {**estate, **vineyard, "variety_count": varieties, "location": "Contrada Baiamonte · Randazzo · Etna"},
        "solar": {key: value for key, value in home_assistant.items() if key not in {"cameras", "live_weather", "power_indicators", "network_equipment", "media", "planning"}},
        "power_indicators": home_assistant.get("power_indicators", []),
        "cameras": home_assistant.get("cameras", []),
        "system_status": system_status_payload(home_assistant),
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
                "FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') ORDER BY due_date IS NULL,due_date LIMIT 6",
                (estate_id(),),
            ),
            "alerts": fetch_all("SELECT severity,title,'Vineyard attention item' message,triggered_at FROM alerts WHERE estate_id=%s AND status='open' ORDER BY triggered_at DESC LIMIT 6", (estate_id(),)),
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
                "WHERE v.estate_id=%s AND v.active=1 ORDER BY v.name",
                (season_id, season_id, estate_id()),
            ),
            "vintages": fetch_all("SELECT vintage_year,SUM(grapes_kg) grapes_kg,SUM(wine_l) wine_l FROM vintage_summaries WHERE estate_id=%s GROUP BY vintage_year ORDER BY vintage_year", (estate_id(),)),
        },
        "pressure": fetch_all(
            "SELECT disease_code,disease_name,risk_score,risk_level,agronomist_status FROM disease_pressure_assessments "
            "WHERE estate_id=%s AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date DESC,risk_score DESC LIMIT 16",
            (estate_id(),),
        ),
        "labs": {"queue": fetch_all(
            "SELECT CONCAT(UPPER(LEFT(sample_type,1)),SUBSTRING(sample_type,2),' sample') sample_name,sample_type,flagged_results,review_status,lab_date "
            "FROM v_lab_decision_queue WHERE estate_id=%s AND (flagged_results>0 OR review_status IN ('decision_needed','reviewing')) ORDER BY lab_date DESC LIMIT 6",
            (estate_id(),),
        )},
        "weather": fetch_all(
            "SELECT YEAR(weather_date) weather_year,MONTH(weather_date) weather_month,AVG(temp_avg_c) temp_avg_c "
            "FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date) BETWEEN %s AND %s GROUP BY YEAR(weather_date),MONTH(weather_date) ORDER BY weather_year,weather_month",
            (estate_id(), year - 3, year),
        ),
    })
