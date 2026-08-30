"""Advisory worker-presence evidence from configured parking-lot vehicles."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..access import people_profiles
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import estate_id


ROME = ZoneInfo("Europe/Rome")
TRACKING_INTERVAL_MINUTES = 15
DEFAULT_CAMERA = "camera.vineyard_north"
DAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _tracked_profiles() -> list[dict[str, Any]]:
    result = []
    for person_entity, profile in people_profiles().items():
        if not isinstance(profile, dict) or not profile.get("vehicle_tracking_enabled"):
            continue
        if not all(str(profile.get(key) or "").strip() for key in ("vehicle_model", "vehicle_color")):
            continue
        vehicles = profile.get("vehicles") if isinstance(profile.get("vehicles"), list) else []
        if not vehicles:
            vehicles = [{key.removeprefix("vehicle_"): profile.get(key) for key in
                         ("vehicle_make", "vehicle_model", "vehicle_type", "vehicle_color")}]
        result.append({"person_entity": person_entity, **profile, "vehicles": vehicles})
    return result


def _inside_capture_window(profile: dict[str, Any], now: datetime) -> bool:
    days = profile.get("normal_work_days") or []
    if days and DAY_CODES[now.weekday()] not in days:
        return False
    try:
        start = time.fromisoformat(str(profile.get("normal_start_time") or "00:00"))
        end = time.fromisoformat(str(profile.get("normal_end_time") or "23:59"))
    except ValueError:
        start, end = time(0), time(23, 59)
    opened = datetime.combine(now.date(), start, tzinfo=ROME) - timedelta(minutes=75)
    closed = datetime.combine(now.date(), end, tzinfo=ROME) + timedelta(minutes=75)
    return opened <= now <= closed


def refresh_worker_vehicle_presence(force: bool = False, event_triggers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check a fresh parking frame or a new gate/doorbell event; never identify a driver."""
    settings = get_settings()
    tracked = _tracked_profiles()
    triggers = sorted(
        (row for row in (event_triggers or []) if isinstance(row, dict) and row.get("event_image_entity_id")),
        key=lambda row: str(row.get("detected_at") or ""), reverse=True,
    )
    event_trigger = triggers[0] if triggers else None
    profiles = tracked if event_trigger else [item for item in tracked if _inside_capture_window(item, datetime.now(ROME))]
    if not profiles:
        return {"configured": bool(tracked), "updated": False, "reason": "Outside configured work windows"}
    if not settings.openai_api_key:
        return {"configured": True, "updated": False, "reason": "Visual analysis is not configured"}
    if not event_trigger:
        last = fetch_one(
            "SELECT MAX(observed_at) observed_at FROM worker_vehicle_observations WHERE estate_id=%s",
            (estate_id(),),
        ) or {}
        observed_at = last.get("observed_at")
        if not force and isinstance(observed_at, datetime) and datetime.now(timezone.utc).replace(tzinfo=None) - observed_at < timedelta(minutes=TRACKING_INTERVAL_MINUTES):
            return {"configured": True, "updated": False, "deferred": True}

    from ..intelligence import (
        _home_assistant_image, _openai_json_request, _openai_response_body, _response_text,
        home_assistant_camera_snapshot, record_ai_usage,
    )

    camera = str((event_trigger or {}).get("camera_entity_id") or profiles[0].get("vehicle_camera_entity") or DEFAULT_CAMERA)
    if event_trigger:
        token = home_assistant_token()
        if not token:
            return {"configured": True, "updated": False, "reason": "Home Assistant image access is unavailable"}
        try:
            image, content_type = _home_assistant_image(
                token, str(event_trigger["event_image_entity_id"]), image_entity=True,
            )
        except Exception as error:
            return {"configured": True, "updated": False, "reason": f"Event image unavailable: {type(error).__name__}"}
        snapshot = {"data": image, "content_type": content_type, "fresh": True}
    else:
        try:
            snapshot = home_assistant_camera_snapshot(camera)
        except Exception as error:
            return {"configured": True, "updated": False, "reason": f"Parking camera unavailable: {type(error).__name__}"}
        if not snapshot.get("fresh"):
            return {"configured": True, "updated": False, "reason": "A fresh parking frame is not available"}
        image = bytes(snapshot["data"])
    digest = hashlib.sha256(image).hexdigest()
    duplicate_table = "worker_vehicle_event_checks" if event_trigger else "worker_vehicle_observations"
    duplicate = fetch_one(
        f"SELECT id FROM {duplicate_table} WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s LIMIT 1",
        (estate_id(), camera, digest),
    )
    if event_trigger and duplicate:
        return {"configured": True, "updated": False, "deferred": True, "reason": "Event image already checked"}
    candidates = [{
        "person_entity": item["person_entity"],
        "worker_key": str(item.get("worker_key") or item["person_entity"].removeprefix("person.")),
        "vehicles": [
            " ".join(str(vehicle.get(key) or "").strip() for key in ("color", "make", "model", "type", "notes")).strip()
            for vehicle in item.get("vehicles") or [] if isinstance(vehicle, dict)
        ],
    } for item in profiles]
    source_description = "gate or doorbell event image" if event_trigger else "fixed Main Parking camera frame"
    prompt = (
        f"Inspect this single {source_description} for the configured worker vehicles. "
        "Do not identify people, faces, drivers, license plates, ownership or intent. A vehicle match is only advisory presence evidence. "
        "Return JSON only: {vehicle_visible:boolean,vehicles:[{person_entity,status:'present'|'absent'|'uncertain',confidence:0..1,reason:string}]}. "
        "A candidate may have more than one valid vehicle; present means any one listed vehicle matches. "
        "Use present only when color, body style, and visible make/model cues reasonably match; use uncertain for occlusion, glare, distance, "
        "multiple similar vehicles or insufficient detail. Do not infer presence from the schedule. Candidates: "
        + json.dumps(candidates, ensure_ascii=False)
    )
    encoded = base64.b64encode(image).decode()
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{snapshot['content_type']};base64,{encoded}", "detail": "low"},
        ]}],
        "text": {"format": {"type": "json_object"}},
    })
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        result = _openai_json_request(request, 60, "worker_vehicle_presence")
        record_ai_usage("worker_vehicle_presence", result, digest[:24])
        parsed = json.loads(_response_text(result) or "{}")
    except Exception as error:
        return {"configured": True, "updated": False, "reason": f"Vehicle analysis unavailable: {type(error).__name__}"}
    vehicle_visible = bool(parsed.get("vehicle_visible"))
    if event_trigger and not vehicle_visible:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT IGNORE INTO worker_vehicle_event_checks "
                "(estate_id,camera_entity_id,event_image_entity_id,detected_at,frame_sha256,vehicle_visible,matched_observations,event_types) "
                "VALUES (%s,%s,%s,%s,%s,FALSE,0,%s)",
                (estate_id(), camera, event_trigger.get("event_image_entity_id"), event_trigger.get("detected_at"),
                 digest, json.dumps(list(event_trigger.get("event_types") or []))),
            )
        return {"configured": True, "updated": False, "screened": True, "reason": "Motion image contained no vehicle", "camera": camera}
    returned = {str(row.get("person_entity") or ""): row for row in parsed.get("vehicles") or [] if isinstance(row, dict)}
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    saved = 0
    with transaction() as (_, cursor):
        for profile in profiles:
            row = returned.get(profile["person_entity"], {})
            status = str(row.get("status") or "uncertain")
            if status not in {"present", "absent", "uncertain"}:
                status = "uncertain"
            # Event images are opportunistic evidence. Record only a positive
            # match; a gate view cannot prove that another worker is absent.
            if event_trigger and status != "present":
                continue
            try:
                confidence = round(max(0, min(100, float(row.get("confidence") or 0) * 100)), 2)
            except (TypeError, ValueError):
                confidence = 0
            cursor.execute(
                "INSERT IGNORE INTO worker_vehicle_observations "
                "(estate_id,person_entity,worker_key,camera_entity_id,observed_at,presence_status,confidence_pct,"
                "vehicle_make,vehicle_model,vehicle_type,vehicle_color,frame_sha256,model_version,evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), profile["person_entity"], str(profile.get("worker_key") or profile["person_entity"].removeprefix("person.")),
                 camera, now_utc, status, confidence, profile.get("vehicle_make"), profile.get("vehicle_model"),
                 profile.get("vehicle_type"), profile.get("vehicle_color"), digest, settings.openai_model,
                 json.dumps({
                     "reason": str(row.get("reason") or "")[:300], "fresh_frame": True,
                     "event_trigger": bool(event_trigger),
                     "event_types": list((event_trigger or {}).get("event_types") or []),
                 })),
            )
            saved += int(cursor.rowcount > 0)
        if event_trigger:
            cursor.execute(
                "INSERT IGNORE INTO worker_vehicle_event_checks "
                "(estate_id,camera_entity_id,event_image_entity_id,detected_at,frame_sha256,vehicle_visible,matched_observations,event_types) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), camera, event_trigger.get("event_image_entity_id"), event_trigger.get("detected_at"),
                 digest, vehicle_visible, saved, json.dumps(list(event_trigger.get("event_types") or []))),
            )
    return {
        "configured": True, "updated": bool(saved), "observations": saved, "camera": camera,
        "screened": bool(event_trigger), "source": "camera_event" if event_trigger else "parking_cadence",
    }


def vehicle_presence_summary(person_entity: str, aliases: tuple[str, ...] = (), days: int = 45) -> dict[str, Any]:
    """Return retained daily evidence and a non-authoritative timesheet comparison."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 365)))
    rows = fetch_all(
        "SELECT observed_at,presence_status,confidence_pct,review_status,evidence FROM worker_vehicle_observations "
        "WHERE estate_id=%s AND person_entity=%s AND observed_at>=%s ORDER BY observed_at",
        (estate_id(), person_entity, cutoff),
    )
    daily: dict[str, dict[str, Any]] = {}
    for row in rows:
        observed = row.get("observed_at")
        if not isinstance(observed, datetime):
            continue
        local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        item = daily.setdefault(local.date().isoformat(), {"present": [], "absent": [], "uncertain": []})
        item[str(row.get("presence_status") or "uncertain")].append((local, float(row.get("confidence_pct") or 0)))
    labor_by_day: dict[str, float] = {}
    clean_aliases = tuple(dict.fromkeys(value.casefold().strip() for value in aliases if value.strip()))
    if clean_aliases:
        clause = " OR ".join("LOWER(TRIM(person_or_crew))=%s" for _ in clean_aliases)
        labor = fetch_all(
            "SELECT work_date,SUM(COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)) hours FROM labor_entries "
            f"WHERE estate_id=%s AND ({clause}) AND work_date>=%s GROUP BY work_date",
            (estate_id(), *clean_aliases, cutoff.date()),
        )
        labor_by_day = {str(row["work_date"]): round(float(row.get("hours") or 0), 2) for row in labor}
    history = []
    for day in sorted(set(daily) | set(labor_by_day), reverse=True):
        evidence = daily.get(day, {"present": [], "absent": [], "uncertain": []})
        present = sorted(evidence["present"])
        first = present[0][0] if present else None
        last = present[-1][0] if present else None
        span = round(max(0, (last - first).total_seconds() / 3600), 2) if first and last and len(present) > 1 else None
        hours = labor_by_day.get(day)
        delta = round(span - hours, 2) if span is not None and hours is not None else None
        if present and hours is not None:
            reconciliation = "consistent" if delta is not None and abs(delta) <= 1.25 else "review"
        elif present:
            reconciliation = "timesheet_missing"
        elif hours is not None:
            reconciliation = "camera_evidence_missing"
        else:
            reconciliation = "no_evidence"
        history.append({
            "work_date": day, "first_seen": first.isoformat() if first else None,
            "last_seen": last.isoformat() if last else None, "observed_span_hours": span,
            "timesheet_hours": hours, "difference_hours": delta, "present_observations": len(present),
            "uncertain_observations": len(evidence["uncertain"]), "reconciliation": reconciliation,
            "confidence_percent": round(sum(value for _, value in present) / len(present)) if present else 0,
        })
    latest = history[0] if history else None
    return {
        "available": bool(rows), "latest": latest, "history": history,
        "note": "Vehicle sightings are supporting evidence only. They do not identify the driver, prove working time, or change payroll automatically.",
    }
