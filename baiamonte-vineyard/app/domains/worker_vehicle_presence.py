"""Advisory worker-presence evidence from configured parking-lot vehicles."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..access import people_profiles
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import estate_id
from .camera_naming import canonical_camera_name
from .worker_evidence_archive import archive_camera_frame, purge_expired_evidence


ROME = ZoneInfo("Europe/Rome")
TRACKING_INTERVAL_MINUTES = 15
DEFAULT_CAMERA = "camera.vineyard_north"
DAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_VEHICLE_PROFILES: dict[str, dict[str, Any]] = {
    "person.giancarlo": {
        "vehicle_tracking_enabled": True,
        "vehicle_make": "Volkswagen", "vehicle_model": "Golf",
        "vehicle_type": "hatchback", "vehicle_color": "silver",
        "vehicle_camera_entity": DEFAULT_CAMERA,
        "vehicle_always_analyze_camera_entities": [DEFAULT_CAMERA],
        "vehicles": [{"make": "Volkswagen", "model": "Golf", "type": "hatchback", "color": "silver"}],
        "normal_work_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "normal_start_time": "07:00", "normal_end_time": "14:00",
    },
    "person.carmela": {
        "vehicle_tracking_enabled": True,
        "vehicle_make": "Fiat", "vehicle_model": "Punto",
        "vehicle_type": "car", "vehicle_color": "blue",
        "vehicle_camera_entity": DEFAULT_CAMERA,
        "vehicles": [{"make": "Fiat", "model": "Punto", "type": "car", "color": "blue"}],
    },
    "person.luca_schiliro_cognato": {
        "vehicle_tracking_enabled": True,
        "vehicle_make": "Renault", "vehicle_model": "Kangoo",
        "vehicle_type": "small van", "vehicle_color": "white",
        "vehicle_camera_entity": DEFAULT_CAMERA,
        "vehicles": [
            {"make": "Renault", "model": "Kangoo", "type": "small van", "color": "white"},
            {"make": "Fiat", "model": "Panda", "type": "car", "color": "red", "notes": "older model"},
        ],
    },
}

# This entity predates its current friendly name. Its operational purpose is
# Main Parking even though the stable Home Assistant entity id says vineyard.
CAMERA_ZONE_OVERRIDES = {"camera.vineyard_north": "main_parking"}


def _camera_zone(entity_id: str, name: str = "") -> str:
    """Return a stable operational zone without requiring camera-specific code."""
    if entity_id in CAMERA_ZONE_OVERRIDES:
        return CAMERA_ZONE_OVERRIDES[entity_id]
    value = f"{entity_id} {name}".casefold().replace("_", " ")
    if any(term in value for term in ("rear gate", "rear entrance")):
        return "rear_gate"
    if any(term in value for term in ("front gate", "main entrance", "doorbell", "driveway")):
        return "front_gate"
    if any(term in value for term in ("parking", "car park", "parcheggio", "front yard")):
        return "main_parking"
    if any(term in value for term in ("vineyard", "vigneto", "field", "etna")):
        return "vineyard"
    if any(term in value for term in ("cellar", "palmento", "cantina")):
        return "cellar"
    if any(term in value for term in ("kitchen", "house", "office", "building")):
        return "buildings"
    return "estate"


def _profile_cameras(profile: dict[str, Any]) -> list[str]:
    """Accept a future wired-camera list while retaining the original camera field."""
    raw = profile.get("vehicle_camera_entities")
    values = raw if isinstance(raw, list) else []
    primary = str(profile.get("vehicle_camera_entity") or "").strip()
    if primary:
        values = [primary, *values]
    result = []
    for value in values or [DEFAULT_CAMERA]:
        entity_id = str(value or "").strip()
        if entity_id.startswith("camera.") and entity_id not in result:
            result.append(entity_id)
    return result or [DEFAULT_CAMERA]


def _priority_cameras(profiles: list[dict[str, Any]]) -> list[str]:
    """Return changeable primaries and explicit battery overrides ahead of supporting views."""
    result: list[str] = []
    for profile in profiles:
        values = [profile.get("vehicle_camera_entity"), *(profile.get("vehicle_always_analyze_camera_entities") or [])]
        for value in values:
            entity_id = str(value or "").strip()
            if entity_id.startswith("camera.") and entity_id not in result:
                result.append(entity_id)
    return result or [DEFAULT_CAMERA]


def _identity_value(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _match_person_label(label: str, profiles: list[dict[str, Any]]) -> str | None:
    """Link an on-device familiar-person label only when exactly one profile matches."""
    wanted = _identity_value(label)
    if not wanted:
        return None
    matches = []
    for profile in profiles:
        entity_id = str(profile.get("person_entity") or "")
        names = {
            _identity_value(profile.get("name")),
            _identity_value(entity_id.removeprefix("person.")),
            *(_identity_value(value) for value in (profile.get("person_aliases") or []) if value),
        }
        # A unique first name is useful for the short labels Eufy commonly emits.
        names.update(name.split()[0] for name in list(names) if name)
        if wanted in names:
            matches.append(entity_id)
    return matches[0] if len(set(matches)) == 1 else None


def _record_eufy_people(event_triggers: list[dict[str, Any]], profiles: list[dict[str, Any]]) -> int:
    """Persist cheap secondary Eufy identity evidence; never perform facial inference."""
    saved = 0
    with transaction() as (_, cursor):
        for trigger in event_triggers[:12]:
            label = str(trigger.get("person_name") or "").strip()
            if not label:
                continue
            person_entity = _match_person_label(label, profiles)
            detected_at = str(trigger.get("detected_at") or "")
            try:
                observed = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
                observed = observed.astimezone(timezone.utc).replace(tzinfo=None) if observed.tzinfo else observed
            except ValueError:
                observed = datetime.now(timezone.utc).replace(tzinfo=None)
            camera = str(trigger.get("camera_entity_id") or "")
            source_key = hashlib.sha256(f"{camera}|{detected_at}|{label}".encode()).hexdigest()
            source_kind = "eufy_familiar_person" if person_entity else "eufy_person"
            cursor.execute(
                "INSERT IGNORE INTO worker_person_observations "
                "(estate_id,person_entity,observed_label,camera_entity_id,camera_name,observation_zone,observed_at,"
                "source_kind,confidence_pct,source_key,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), person_entity, label[:160], camera, canonical_camera_name(camera, trigger.get("camera_name"))[:180],
                 _camera_zone(camera, str(trigger.get("camera_name") or "")), observed, source_kind,
                 100 if person_entity else 0, source_key,
                 json.dumps({"on_device_label": True, "event_types": list(trigger.get("event_types") or [])})),
            )
            saved += int(cursor.rowcount > 0)
    return saved


def _tracked_profiles() -> list[dict[str, Any]]:
    result = []
    saved_profiles = people_profiles()
    # The Admin/People page and the analyzer must use the same candidates. The
    # defaults remain active when a profile has not yet been explicitly saved;
    # saved values (including an explicit disabled flag) always win.
    person_entities = dict.fromkeys((*DEFAULT_VEHICLE_PROFILES, *saved_profiles))
    for person_entity in person_entities:
        saved = saved_profiles.get(person_entity, {})
        if not isinstance(saved, dict):
            saved = {}
        profile = {**DEFAULT_VEHICLE_PROFILES.get(person_entity, {}), **saved}
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


def _profiles_for_capture(
    tracked: list[dict[str, Any]], *, force: bool, event_trigger: dict[str, Any] | None, now: datetime
) -> list[dict[str, Any]]:
    """Select candidates without letting a manual administrator scan be blocked by a schedule."""
    if event_trigger or force:
        return tracked
    return [item for item in tracked if _inside_capture_window(item, now)]


def refresh_worker_vehicle_presence(force: bool = False, event_triggers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check a fresh parking frame or a new gate/doorbell event; never identify a driver."""
    settings = get_settings()
    tracked = _tracked_profiles()
    triggers = sorted(
        (row for row in (event_triggers or []) if isinstance(row, dict) and row.get("event_image_entity_id")),
        key=lambda row: str(row.get("detected_at") or ""), reverse=True,
    )
    named_people_saved = _record_eufy_people(triggers, tracked) if triggers else 0
    event_trigger = triggers[0] if triggers else None
    profiles = _profiles_for_capture(
        tracked, force=force, event_trigger=event_trigger, now=datetime.now(ROME)
    )
    if not profiles:
        return {
            "configured": bool(tracked), "updated": bool(named_people_saved),
            "named_people_observations": named_people_saved,
            "reason": "Outside configured work windows",
        }
    if not settings.openai_api_key:
        return {
            "configured": True, "updated": bool(named_people_saved),
            "named_people_observations": named_people_saved,
            "reason": "Visual vehicle analysis is not configured",
        }
    from ..intelligence import (
        _home_assistant_image, _openai_json_request, _openai_response_body, _response_text,
        home_assistant_camera_snapshot, record_ai_usage,
    )

    if event_trigger:
        camera = str(event_trigger.get("camera_entity_id") or DEFAULT_CAMERA)
    else:
        cameras = _priority_cameras(profiles)
        camera_activity = {
            str(row.get("camera_entity_id") or ""): row.get("observed_at")
            for row in fetch_all(
                "SELECT camera_entity_id,MAX(observed_at) observed_at FROM worker_vehicle_observations "
                "WHERE estate_id=%s GROUP BY camera_entity_id",
                (estate_id(),),
            )
        }
        camera = min(cameras, key=lambda entity: camera_activity.get(entity) or datetime.min)
        observed_at = camera_activity.get(camera)
        if (
            not force and isinstance(observed_at, datetime)
            and datetime.now(timezone.utc).replace(tzinfo=None) - observed_at < timedelta(minutes=TRACKING_INTERVAL_MINUTES)
        ):
            return {
                "configured": True, "updated": bool(named_people_saved), "deferred": True,
                "named_people_observations": named_people_saved, "camera": camera,
            }
        profiles = [profile for profile in profiles if camera in _profile_cameras(profile)]
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
    zone = _camera_zone(camera, str((event_trigger or {}).get("camera_name") or ""))
    try:
        captured_at = None
        if event_trigger and event_trigger.get("detected_at"):
            captured_at = datetime.fromisoformat(str(event_trigger["detected_at"]).replace("Z", "+00:00"))
        evidence_id = archive_camera_frame(
            image,
            content_type=str(snapshot.get("content_type") or "image/jpeg"),
            camera_entity_id=camera,
            observation_zone=zone,
            captured_at=captured_at,
            source_kind="eufy_event" if event_trigger else "scheduled_vehicle_check",
        )
        purge_expired_evidence()
    except Exception:
        # Evidence storage must not turn a camera/AI outage into a scheduler outage.
        evidence_id = None
    duplicate_table = "worker_vehicle_event_checks" if event_trigger else "worker_vehicle_observations"
    duplicate = fetch_one(
        f"SELECT id FROM {duplicate_table} WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s LIMIT 1",
        (estate_id(), camera, digest),
    )
    if event_trigger and duplicate:
        if evidence_id:
            with transaction() as (_, cursor):
                cursor.execute(
                    "UPDATE worker_vehicle_event_checks SET evidence_id=COALESCE(evidence_id,%s) "
                    "WHERE estate_id=%s AND id=%s",
                    (evidence_id, estate_id(), duplicate["id"]),
                )
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
        "Return JSON only: {vehicle_visible:boolean,vehicles:[{person_entity,status:'present'|'absent'|'uncertain',"
        "confidence:0..1,matched_vehicle_index:integer|null,front_direction:'left'|'right'|'toward_camera'|'away_from_camera'|'unclear',"
        "movement_state:'arriving'|'leaving'|'parked'|'uncertain',reason:string}]}. "
        "A candidate may have more than one valid vehicle; present means any one listed vehicle matches. "
        "Determine the direction the vehicle front is pointing from visible vehicle geometry whenever possible. "
        "For the fixed Main Parking view specifically, front pointing RIGHT means ARRIVING and front pointing LEFT means LEAVING; "
        "do not reverse that site-specific rule. A stationary vehicle already in a parking position is parked. "
        "At a fixed wide parking view, matching color and body style are sufficient for present when no other configured candidate shares both; "
        "visible make/model detail is supporting evidence but is not required at long distance. Use uncertain for occlusion, glare, a body-style mismatch, "
        "multiple configured candidates with the same color and body style, or genuinely insufficient detail. Do not infer presence from the schedule. Candidates: "
        + json.dumps(candidates, ensure_ascii=False)
    )
    encoded = base64.b64encode(image).decode()
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{snapshot['content_type']};base64,{encoded}", "detail": "high"},
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
                "(estate_id,camera_entity_id,event_image_entity_id,detected_at,frame_sha256,evidence_id,vehicle_visible,matched_observations,event_types) "
                "VALUES (%s,%s,%s,%s,%s,%s,FALSE,0,%s)",
                (estate_id(), camera, event_trigger.get("event_image_entity_id"), event_trigger.get("detected_at"),
                 digest, evidence_id, json.dumps(list(event_trigger.get("event_types") or []))),
            )
        return {
            "configured": True, "updated": bool(named_people_saved), "screened": True,
            "named_people_observations": named_people_saved,
            "reason": "Motion image contained no vehicle", "camera": camera,
        }
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
            try:
                matched_index = int(row.get("matched_vehicle_index"))
            except (TypeError, ValueError):
                matched_index = 0
            vehicles = [vehicle for vehicle in profile.get("vehicles") or [] if isinstance(vehicle, dict)]
            matched_vehicle = vehicles[matched_index] if 0 <= matched_index < len(vehicles) else (vehicles[0] if vehicles else {})
            front_direction = str(row.get("front_direction") or "unclear")
            if front_direction not in {"left", "right", "toward_camera", "away_from_camera", "unclear"}:
                front_direction = "unclear"
            movement_state = str(row.get("movement_state") or "uncertain")
            if movement_state not in {"arriving", "leaving", "parked", "uncertain"}:
                movement_state = "uncertain"
            cursor.execute(
                "INSERT IGNORE INTO worker_vehicle_observations "
                "(estate_id,person_entity,worker_key,camera_entity_id,observed_at,presence_status,confidence_pct,"
                "vehicle_make,vehicle_model,vehicle_type,vehicle_color,frame_sha256,model_version,evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), profile["person_entity"], str(profile.get("worker_key") or profile["person_entity"].removeprefix("person.")),
                 camera, now_utc, status, confidence, matched_vehicle.get("make") or profile.get("vehicle_make"),
                 matched_vehicle.get("model") or profile.get("vehicle_model"),
                 matched_vehicle.get("type") or profile.get("vehicle_type"),
                 matched_vehicle.get("color") or profile.get("vehicle_color"), digest, settings.openai_model,
                 json.dumps({
                     "reason": str(row.get("reason") or "")[:300], "fresh_frame": True,
                     "event_trigger": bool(event_trigger),
                     "event_types": list((event_trigger or {}).get("event_types") or []),
                     "source_kind": "eufy_event_vehicle_match" if event_trigger else "scheduled_camera_vehicle_match",
                     "observation_zone": zone,
                     "matched_vehicle_index": matched_index if matched_vehicle else None,
                     "front_direction": front_direction,
                     "movement_state": movement_state,
                     "main_parking_direction_rule": "front_right_arriving_front_left_leaving" if zone == "main_parking" else None,
                     "evidence_id": evidence_id,
                 })),
            )
            saved += int(cursor.rowcount > 0)
        if event_trigger:
            cursor.execute(
                "INSERT IGNORE INTO worker_vehicle_event_checks "
                "(estate_id,camera_entity_id,event_image_entity_id,detected_at,frame_sha256,evidence_id,vehicle_visible,matched_observations,event_types) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (estate_id(), camera, event_trigger.get("event_image_entity_id"), event_trigger.get("detected_at"),
                 digest, evidence_id, vehicle_visible, saved, json.dumps(list(event_trigger.get("event_types") or []))),
            )
    return {
        "configured": True, "updated": bool(saved or named_people_saved), "observations": saved, "camera": camera,
        "screened": bool(event_trigger), "source": "camera_event" if event_trigger else "parking_cadence",
        "named_people_observations": named_people_saved,
    }


def vehicle_presence_summary(person_entity: str, aliases: tuple[str, ...] = (), days: int = 45) -> dict[str, Any]:
    """Return retained daily evidence and a non-authoritative timesheet comparison."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 365)))
    rows = fetch_all(
        "SELECT id,observed_at,presence_status,confidence_pct,review_status,evidence,camera_entity_id,"
        "vehicle_make,vehicle_model,vehicle_type,vehicle_color FROM worker_vehicle_observations "
        "WHERE estate_id=%s AND person_entity=%s AND observed_at>=%s ORDER BY observed_at",
        (estate_id(), person_entity, cutoff),
    )
    daily: dict[str, dict[str, Any]] = {}
    timeline: list[dict[str, Any]] = []
    for row in rows:
        observed = row.get("observed_at")
        if not isinstance(observed, datetime):
            continue
        local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        item = daily.setdefault(local.date().isoformat(), {"present": [], "absent": [], "uncertain": []})
        try:
            evidence = json.loads(row.get("evidence") or "{}") if not isinstance(row.get("evidence"), dict) else row["evidence"]
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        observation = {
            "id": row.get("id"), "kind": "vehicle", "observed_at": local,
            "camera_entity_id": row.get("camera_entity_id"),
            "zone": str(evidence.get("observation_zone") or _camera_zone(str(row.get("camera_entity_id") or ""))),
            "source_kind": str(evidence.get("source_kind") or "vehicle_match"),
            "status": str(row.get("presence_status") or "uncertain"),
            "confidence_percent": float(row.get("confidence_pct") or 0),
            "review_status": str(row.get("review_status") or "unreviewed"),
            "vehicle": " ".join(str(row.get(key) or "").strip() for key in
                                ("vehicle_color", "vehicle_make", "vehicle_model", "vehicle_type")).strip(),
            "reason": str(evidence.get("reason") or "")[:300],
            "front_direction": str(evidence.get("front_direction") or "unclear"),
            "movement_state": str(evidence.get("movement_state") or "uncertain"),
            "evidence_id": str(evidence.get("evidence_id") or "") or None,
        }
        item[observation["status"]].append(observation)
        timeline.append(observation)

    try:
        person_rows = fetch_all(
            "SELECT id,observed_at,confidence_pct,review_status,camera_entity_id,observation_zone,source_kind,observed_label "
            "FROM worker_person_observations WHERE estate_id=%s AND person_entity=%s AND observed_at>=%s ORDER BY observed_at",
            (estate_id(), person_entity, cutoff),
        )
    except Exception:
        person_rows = []
    for row in person_rows:
        observed = row.get("observed_at")
        if not isinstance(observed, datetime):
            continue
        local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        timeline.append({
            "id": row.get("id"), "kind": "person", "observed_at": local,
            "camera_entity_id": row.get("camera_entity_id"),
            "zone": str(row.get("observation_zone") or "estate"),
            "source_kind": str(row.get("source_kind") or "eufy_familiar_person"),
            "status": "present", "confidence_percent": float(row.get("confidence_pct") or 0),
            "review_status": str(row.get("review_status") or "unreviewed"),
            "vehicle": "", "reason": f"Eufy on-device label: {row.get('observed_label') or 'known person'}",
        })
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
        present = sorted(evidence["present"], key=lambda row: row["observed_at"])
        first = present[0]["observed_at"] if present else None
        last = present[-1]["observed_at"] if present else None
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
            "confidence_percent": round(sum(row["confidence_percent"] for row in present) / len(present)) if present else 0,
        })
    latest = history[0] if history else None
    # Only vehicle matches may generate attendance/location transitions. A named
    # Eufy person event is useful corroboration, but must never become the primary
    # presence clock or silently create worked time.
    strong = sorted(
        (
            row for row in timeline
            if row["kind"] == "vehicle"
            and row["status"] == "present"
            and row["review_status"] != "rejected"
            and row["confidence_percent"] >= (80 if row["source_kind"] == "eufy_event_vehicle_match" else 70)
        ),
        key=lambda row: row["observed_at"],
    )
    movements = []
    inside_zones = {"main_parking", "vineyard", "cellar", "buildings", "estate"}
    gate_zones = {"front_gate", "rear_gate"}
    for before, after in zip(strong, strong[1:]):
        if before["zone"] == after["zone"] or after["observed_at"] - before["observed_at"] > timedelta(hours=4):
            continue
        direction = "movement"
        if before["zone"] in gate_zones and after["zone"] in inside_zones:
            direction = "arrival"
        elif before["zone"] in inside_zones and after["zone"] in gate_zones:
            direction = "departure"
        movements.append({
            "observed_at": after["observed_at"].isoformat(), "direction": direction,
            "from_zone": before["zone"], "to_zone": after["zone"],
            "confidence_percent": round(min(before["confidence_percent"], after["confidence_percent"])),
        })
    latest_observation = strong[-1] if strong else None
    latest_person = next((row for row in sorted(timeline, key=lambda row: row["observed_at"], reverse=True)
                          if row["kind"] == "person" and row["status"] == "present"), None)
    reviewed = [row for row in timeline if row["review_status"] in {"confirmed", "rejected"}]
    confirmed = sum(row["review_status"] == "confirmed" for row in reviewed)
    camera_learning: dict[str, dict[str, Any]] = {}
    for row in timeline:
        camera = str(row.get("camera_entity_id") or "unknown")
        stats = camera_learning.setdefault(camera, {"observations": 0, "reviewed": 0, "confirmed": 0})
        stats["observations"] += 1
        if row["review_status"] in {"confirmed", "rejected"}:
            stats["reviewed"] += 1
            stats["confirmed"] += int(row["review_status"] == "confirmed")
    for stats in camera_learning.values():
        stats["review_accuracy_percent"] = round(stats["confirmed"] / stats["reviewed"] * 100) if stats["reviewed"] else None
    recent = sorted(timeline, key=lambda row: row["observed_at"], reverse=True)[:30]
    return {
        "available": bool(rows or person_rows), "latest": latest, "history": history,
        "current_location": {
            "state": "recently_seen" if latest_observation and datetime.now(ROME) - latest_observation["observed_at"] <= timedelta(hours=3) else "historical_only",
            "zone": latest_observation["zone"] if latest_observation else None,
            "observed_at": latest_observation["observed_at"].isoformat() if latest_observation else None,
            "source_kind": latest_observation["source_kind"] if latest_observation else None,
            "confidence_percent": round(latest_observation["confidence_percent"]) if latest_observation else 0,
        },
        "secondary_person_evidence": {
            "available": bool(latest_person),
            "zone": latest_person["zone"] if latest_person else None,
            "observed_at": latest_person["observed_at"].isoformat() if latest_person else None,
            "source_kind": latest_person["source_kind"] if latest_person else None,
            "confidence_percent": round(latest_person["confidence_percent"]) if latest_person else 0,
        },
        "movements": movements[-30:][::-1],
        "recent_observations": [{**row, "observed_at": row["observed_at"].isoformat()} for row in recent],
        "learning": {
            "reviewed": len(reviewed), "confirmed": confirmed,
            "review_accuracy_percent": round(confirmed / len(reviewed) * 100) if reviewed else None,
            "camera_stats": camera_learning,
            "vehicle_observations": len(rows), "named_person_observations": len(person_rows),
        },
        "note": "Vehicle sightings are the primary supporting evidence. They do not identify the driver, prove worked time, or change payroll automatically. Eufy familiar-person labels are secondary corroboration.",
    }
