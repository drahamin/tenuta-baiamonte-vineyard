"""Payroll identity links and supporting Home Assistant presence evidence."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..access import match_home_assistant_person, people_profiles
from ..db import fetch_all, fetch_one
from ..ha_auth import home_assistant_token
from ..intelligence import home_assistant_people
from ..service import estate_id
from .people_presence import resolve_timesheet_presence_entities


class PresenceValidationError(ValueError):
    """Invalid timesheet input independent of any HTTP transport."""


def labor_identity_links() -> dict[str, str]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='labor_identity_links'",
        (estate_id(),),
    ) or {}
    try:
        payload = json.loads(row.get("setting_value") or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(worker_key).strip(): str(person_entity).strip()
        for worker_key, person_entity in payload.items()
        if str(worker_key).strip() and str(person_entity).strip().startswith("person.")
    }


def timesheet_presence(worker: str, raw_entries: list[dict[str, Any]]) -> dict[str, Any]:
    dates = []
    for row in raw_entries:
        if not isinstance(row, dict):
            raise PresenceValidationError("Every timesheet row must be a dated labor entry")
        row_worker = str(row.get("person_or_crew") or row.get("worker") or worker).strip()
        if row_worker.casefold() != worker.casefold():
            raise PresenceValidationError("Approve one employee at a time; split mixed-worker hours into separate reviews")
        try:
            dates.append(date.fromisoformat(str(row.get("work_date") or row.get("date"))[:10]))
        except (AttributeError, TypeError, ValueError):
            continue
    dates = sorted(set(dates))
    if not dates:
        return {"available": False, "reason": "No dated rows", "days": [], "confidence_percent": 0}
    resolved_identity = resolve_timesheet_presence_entities(
        worker,
        labor_identity_links(),
        home_assistant_people(),
        people_profiles(),
        match_home_assistant_person,
    )
    if not resolved_identity:
        return {
            "available": False,
            "reason": "No Home Assistant person or phone entity is assigned to this worker",
            "days": [{"work_date": day.isoformat(), "status": "unknown", "sources": [], "confidence_percent": 0} for day in dates],
            "confidence_percent": 0,
        }
    aliases, entities = resolved_identity
    person_entity = next((entity for entity in entities if entity.startswith("person.")), "")
    vehicle_by_day: dict[date, list[dict[str, Any]]] = {day: [] for day in dates}
    if person_entity:
        try:
            vehicle_rows = fetch_all(
                "SELECT observed_at,confidence_pct,camera_entity_id FROM worker_vehicle_observations "
                "WHERE estate_id=%s AND person_entity=%s AND presence_status='present' "
                "AND observed_at>=%s AND observed_at<%s ORDER BY observed_at",
                (estate_id(), person_entity, datetime.combine(dates[0], datetime.min.time()),
                 datetime.combine(dates[-1] + timedelta(days=1), datetime.min.time())),
            )
            for row in vehicle_rows:
                observed_at = row.get("observed_at")
                if isinstance(observed_at, datetime):
                    local_day = observed_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Rome")).date()
                    if local_day in vehicle_by_day:
                        vehicle_by_day[local_day].append(row)
        except Exception:
            vehicle_by_day = {day: [] for day in dates}
    camera_entities = (
        "sensor.gate_doorbell_person_name_2",
        "sensor.front_gate_person_name",
        "sensor.vineyard_north_person_name",
        "sensor.mid_vineyard_north_person_name",
        "sensor.rear_gate_person_name",
    )
    token = home_assistant_token()
    if not token:
        vehicle_days = [{
            "work_date": day.isoformat(),
            "status": "confirmed" if vehicle_by_day[day] else "unknown",
            "sources": sorted({str(row.get("camera_entity_id") or "parking camera") + " · vehicle" for row in vehicle_by_day[day]}),
            "confidence_percent": round(sum(float(row.get("confidence_pct") or 0) for row in vehicle_by_day[day]) / len(vehicle_by_day[day])) if vehicle_by_day[day] else 0,
            "confidence_basis": "configured vehicle sighting (driver not identified)" if vehicle_by_day[day] else "no retained evidence",
        } for day in dates]
        return {
            "available": any(vehicle_by_day.values()),
            "reason": "Home Assistant history authentication unavailable; retained vehicle evidence is shown where available",
            "days": vehicle_days,
            "confidence_percent": round(sum(row["confidence_percent"] for row in vehicle_days) / len(vehicle_days)),
        }
    rome = ZoneInfo("Europe/Rome")
    start = datetime.combine(dates[0], datetime.min.time()).replace(tzinfo=rome)
    end = datetime.combine(dates[-1] + timedelta(days=1), datetime.min.time()).replace(tzinfo=rome)
    query = urllib.parse.urlencode({"end_time": end.isoformat(), "filter_entity_id": ",".join((*entities, *camera_entities)), "minimal_response": ""})
    url = "http://supervisor/core/api/history/period/" + urllib.parse.quote(start.isoformat(), safe="-:T+") + "?" + query
    try:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            history = json.loads(response.read())
    except Exception as error:
        return {
            "available": False,
            "reason": f"Home Assistant history could not be read: {type(error).__name__}",
            "days": [{"work_date": day.isoformat(), "status": "unknown", "sources": [], "confidence_percent": 0} for day in dates],
            "confidence_percent": 0,
        }
    evidence = {day: {"confirmed": set(), "away": set(), "vehicle": vehicle_by_day[day]} for day in dates}
    for series in history if isinstance(history, list) else []:
        if not series:
            continue
        entity_id = str(series[0].get("entity_id") or "")
        for point in series:
            try:
                observed = datetime.fromisoformat(str(point.get("last_changed") or point.get("last_updated") or "").replace("Z", "+00:00")).astimezone(rome).date()
            except ValueError:
                continue
            if observed not in evidence:
                continue
            value = str(point.get("state") or "").casefold()
            if entity_id in entities and value == "home":
                evidence[observed]["confirmed"].add(entity_id)
            elif entity_id in entities and value == "not_home":
                evidence[observed]["away"].add(entity_id)
            elif entity_id in camera_entities and any(alias in value for alias in aliases):
                evidence[observed]["confirmed"].add(entity_id)
    days = []
    for day in dates:
        confirmed, away, vehicle = evidence[day]["confirmed"], evidence[day]["away"], evidence[day]["vehicle"]
        vehicle_sources = {str(row.get("camera_entity_id") or "parking camera") + " · vehicle" for row in vehicle}
        status = "confirmed" if confirmed or vehicle else "away" if away else "unknown"
        sources = sorted((confirmed | vehicle_sources) or away)
        has_location_source = any(source.startswith(("person.", "device_tracker.")) for source in confirmed)
        has_camera_source = any(source.startswith("sensor.") for source in confirmed)
        vehicle_confidence = round(sum(float(row.get("confidence_pct") or 0) for row in vehicle) / len(vehicle)) if vehicle else 0
        confidence = 92 if has_location_source else 78 if has_camera_source else min(72, vehicle_confidence) if vehicle else 58 if away else 0
        basis = "GPS/person presence" if has_location_source else "camera recognition" if has_camera_source else "configured vehicle sighting (driver not identified)" if vehicle else "away-state evidence" if away else "no retained evidence"
        days.append({"work_date": day.isoformat(), "status": status, "sources": sources, "confidence_percent": confidence, "confidence_basis": basis})
    confidence = round(sum(day["confidence_percent"] for day in days) / len(days)) if days else 0
    return {
        "available": True,
        "reason": None,
        "days": days,
        "confidence_percent": confidence,
        "note": "Presence confidence measures supporting evidence only; it does not approve hours. Missing or away states do not disprove reported work.",
    }
