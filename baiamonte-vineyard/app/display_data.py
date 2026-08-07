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


ACCESS_CAMERA_TERMS = ("gate", "door", "entrance", "entry", "driveway", "access", "parking", "cancello", "porta", "ingresso", "parcheggio")


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
    access_cameras = sorted(str(item.get("entity_id")) for item in states if is_access_camera(str(item.get("entity_id") or ""), str((item.get("attributes") or {}).get("friendly_name") or "")))
    # A saved list is exact: removed cameras must disappear from the TV page.
    # Gate/door discovery remains the no-configuration fallback.
    camera_ids = list(dict.fromkeys(configured_cameras or access_cameras))
    entrance_cameras = []
    vineyard_cameras = []
    for entity_id in camera_ids:
        item = state_map.get(entity_id) or {}
        attributes = item.get("attributes") or {}
        camera = {"entity_id": entity_id, "name": attributes.get("friendly_name") or entity_id.removeprefix("camera.").replace("_", " ").title(), "available": item.get("state") not in {None, "unavailable", "unknown"}}
        target = entrance_cameras if is_access_camera(entity_id, str(attributes.get("friendly_name") or "")) else vineyard_cameras
        if len(target) < 6:
            target.append(camera)
    cameras = [*entrance_cameras, *vineyard_cameras]

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

    def planning_entities(domain: str, configured: str) -> tuple[list[str], str]:
        explicit = [value.strip() for value in configured.split(",") if value.strip().startswith(domain + ".")]
        if explicit:
            valid = [entity_id for entity_id in dict.fromkeys(explicit) if entity_id in state_map]
            return (valid, "configured") if valid else ([], "configured entity not found")
        rows = []
        available = []
        for item in states:
            entity_id = str(item.get("entity_id") or "")
            if not entity_id.startswith(domain + "."):
                continue
            if item.get("state") not in {None, "unknown", "unavailable"}:
                available.append(entity_id)
            attributes = item.get("attributes") or {}
            text = f"{entity_id} {attributes.get('friendly_name') or ''}".casefold()
            if any(term in text for term in ("baiamonte", "vineyard", "vigneto", "tenuta")):
                rows.append(entity_id)
        if rows:
            return rows, "discovered by vineyard name"
        # A single active calendar/list is unambiguous and can be used without
        # exposing unrelated personal planning sources on the public TV page.
        if domain == "calendar" and len(available) == 1:
            return available, "only available entity"
        return [], f"{len(available)} available; choose explicitly" if available else "none available"

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

    calendar_setting = str(runtime_option("planning_calendar_entities", get_settings().planning_calendar_entities))
    todo_setting = str(runtime_option("planning_todo_entities", get_settings().planning_todo_entities))
    calendar_ids, calendar_source = planning_entities("calendar", calendar_setting)
    todo_ids, todo_source = planning_entities("todo", todo_setting)
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
        "calendar_status": calendar_source,
        "tasks_status": todo_source,
    }
    return {"available": True, "solar_available": bool(candidates), "current_power": current, "energy_today": today, "energy_total": total, "power_indicators": power_indicators, "network_equipment": network_equipment, "cameras": cameras, "entrance_cameras": entrance_cameras, "vineyard_cameras": vineyard_cameras, "live_weather": live_weather, "media": find_baiamonte_media(states), "planning": planning}


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
    vintage_history = fetch_all(
        "SELECT vintage_year,SUM(grapes_kg) grapes_kg,SUM(wine_l) wine_l,SUM(cassette_count) cassette_count "
        "FROM vintage_summaries WHERE estate_id=%s GROUP BY vintage_year ORDER BY vintage_year",
        (estate_id(),),
    )
    conversion_rows = [row for row in vintage_history if row.get("grapes_kg") and row.get("wine_l") and int(row["vintage_year"]) < year]
    conversion = sum(float(row["wine_l"]) / float(row["grapes_kg"]) for row in conversion_rows) / len(conversion_rows) if conversion_rows else 0.70
    blend = fetch_one(
        "SELECT SUM(target_grapes_kg) target_grapes_kg,SUM(COALESCE(target_volume_l,target_grapes_kg*expected_yield_l_per_kg)) target_volume_l "
        "FROM blend_plans WHERE season_id=%s",
        (season_id,),
    ) or {}
    basis_kg = blend.get("target_grapes_kg") if blend.get("target_grapes_kg") is not None else planned
    basis_wine_l = blend.get("target_volume_l") if blend.get("target_volume_l") is not None else (float(basis_kg) * conversion if basis_kg is not None else None)
    projection_scenarios = []
    for name, factor in (("Downside", 0.85), ("Working", 1.0), ("Upside", 1.15)):
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
    cellar_tanks = fetch_all(
        "SELECT c.id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.sensor_entity_id,c.status,"
        "w.id wine_lot_id,w.code lot_code,w.name lot_name,w.stage,w.volume_l,w.variety_summary,w.started_at,"
        "(SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) temp_c,"
        "(SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) density_sg,"
        "(SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) brix,"
        "(SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) ph,"
        "(SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) reading_at,"
        "(SELECT f.next_check_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) next_check_at "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.season_id=%s "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (season_id, estate_id()),
    )
    cellar_demo = not any(row.get("wine_lot_id") for row in cellar_tanks)
    if cellar_demo:
        cellar_tanks = []
        cellar_varieties = fetch_all("SELECT name FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),))
        for variety in cellar_varieties:
            for stage, capacity, level in (("fermentation", 600, 85), ("aging", 225, 75)):
                cellar_tanks.append({
                    "id": f"demo-{len(cellar_tanks)+1}", "code": f"DEMO-{len(cellar_tanks)+1:02d}",
                    "name": f"{variety['name']} — {stage.title()}", "container_type": "tank" if stage == "fermentation" else "barrel",
                    "capacity_l": capacity, "volume_l": round(capacity * level / 100, 1), "level_pct": level,
                    "stage": stage, "variety_summary": variety["name"], "status": "demo", "source": "Original system demo",
                    "temp_c": None, "density_sg": None, "brix": None, "ph": None, "sensor_entity_id": None,
                })
    else:
        for tank in cellar_tanks:
            capacity = float(tank.get("capacity_l") or 0)
            volume = float(tank.get("volume_l") or 0)
            tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
            tank["source"] = "Tank monitor" if tank.get("sensor_entity_id") else "Recorded reading"
    cellar_processes = fetch_all(
        "SELECT f.id,f.observed_at,f.vessel_name,f.stage,f.temp_c,f.density_sg,f.brix,f.ph,f.cap_management,f.addition_action,f.sensory_observation,f.owner_text,f.next_check_at,f.status,w.code lot_code,w.name lot_name "
        "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id WHERE f.estate_id=%s "
        "AND (w.season_id=%s OR w.season_id IS NULL) ORDER BY COALESCE(f.next_check_at,f.observed_at) DESC LIMIT 12",
        (estate_id(), season_id),
    )
    return json_ready({
        "year": year,
        "display": {
            "time_zone": str(runtime_option("tv_time_zone", settings.tv_time_zone)) or "Europe/Rome",
            "cycle_seconds": max(10, int(runtime_option("tv_cycle_seconds", settings.tv_cycle_seconds))),
            "refresh_seconds": max(30, int(runtime_option("tv_refresh_seconds", settings.tv_refresh_seconds))),
            "vineyard_camera_page_enabled": bool(runtime_option("tv_vineyard_camera_page_enabled", settings.tv_vineyard_camera_page_enabled)),
        },
        "estate": {**estate, **vineyard, "variety_count": varieties, "location": "Contrada Baiamonte · Randazzo · Etna"},
        "solar": {key: value for key, value in home_assistant.items() if key not in {"cameras", "entrance_cameras", "vineyard_cameras", "live_weather", "power_indicators", "network_equipment", "media", "planning"}},
        "power_indicators": home_assistant.get("power_indicators", []),
        "cameras": home_assistant.get("cameras", []),
        "entrance_cameras": home_assistant.get("entrance_cameras", []),
        "vineyard_cameras": home_assistant.get("vineyard_cameras", []),
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
                "FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
                "ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date LIMIT 12",
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
            "vintages": vintage_history,
            "prior_vintage": prior_vintage,
        },
        "projections": {
            "basis": "current blend plan" if blend.get("target_grapes_kg") is not None else "harvest plan" if planned is not None else "missing",
            "historical_conversion_l_per_kg": conversion,
            "scenarios": projection_scenarios,
            "working": next((row for row in projection_scenarios if row["name"] == "Working"), {}),
        },
        "cellar": {"year": year, "demo": cellar_demo, "tanks": cellar_tanks, "processes": cellar_processes},
        "pressure": latest_pressure,
        "labs": {"queue": fetch_all(
            "SELECT CONCAT(UPPER(LEFT(sample_type,1)),SUBSTRING(sample_type,2),' sample') sample_name,sample_type,flagged_results,review_status,lab_date "
            "FROM v_lab_decision_queue WHERE estate_id=%s AND (flagged_results>0 OR review_status IN ('decision_needed','reviewing')) ORDER BY lab_date DESC LIMIT 6",
            (estate_id(),),
        )},
        "weather": fetch_all(
            "SELECT YEAR(weather_date) weather_year,MONTH(weather_date) weather_month,AVG(temp_avg_c) temp_avg_c,SUM(COALESCE(rain_mm,0)) rain_mm "
            "FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date) BETWEEN %s AND %s GROUP BY YEAR(weather_date),MONTH(weather_date) ORDER BY weather_year,weather_month",
            (estate_id(), year - 3, year),
        ),
    })
