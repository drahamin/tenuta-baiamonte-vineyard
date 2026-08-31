"""Administrator-only estate security and vehicle movement intelligence."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.request
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_admin, people_profiles, request_username
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import audit, estate_id
from .camera_naming import canonical_camera_name
from .worker_evidence_archive import archive_camera_frame, extend_evidence_review, purge_expired_evidence
from .worker_vehicle_presence import _camera_zone, _tracked_profiles


ROME = ZoneInfo("Europe/Rome")
router = APIRouter(prefix="/api/v1/admin/security", tags=["estate security"])
SOURCE_ROLES = {"entry_exit", "parking", "doorbell", "perimeter", "supporting"}
DIRECTION_RULES = {"none", "front_right_entry", "front_left_entry", "toward_entry", "away_entry"}
MOVEMENTS = {"entry", "exit", "parked", "passing", "unknown"}
SUBJECT_CATEGORIES = {"staff", "contractor", "visitor", "delivery", "service", "unknown", "other"}


def security_camera_sources(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    where = " AND enabled=1" if enabled_only else ""
    return fetch_all(
        "SELECT id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order "
        f"FROM estate_security_cameras WHERE estate_id=%s{where} ORDER BY sort_order,display_name",
        (estate_id(),),
    )


def configured_security_camera_ids() -> set[str]:
    return {str(row["camera_entity_id"]) for row in security_camera_sources(enabled_only=True)}


def _camera_catalog() -> list[dict[str, Any]]:
    try:
        from ..intelligence import home_assistant_manager_camera_catalog
        return home_assistant_manager_camera_catalog()
    except Exception:
        return []


def _staff_candidates() -> list[dict[str, Any]]:
    saved = people_profiles()
    candidates = []
    for profile in _tracked_profiles():
        person_entity = str(profile.get("person_entity") or "")
        vehicles = []
        for vehicle in profile.get("vehicles") or []:
            if not isinstance(vehicle, dict):
                continue
            vehicles.append({
                key: str(vehicle.get(key) or "").strip()[:120]
                for key in ("make", "model", "type", "color", "plate", "notes")
            })
        candidates.append({
            "person_entity": person_entity,
            "name": str((saved.get(person_entity) or {}).get("name") or profile.get("name") or person_entity.removeprefix("person.").replace("_", " ").title())[:180],
            "vehicles": vehicles,
        })
    return candidates


def _known_vehicle_candidates() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,license_plate,plate_country,"
        "person_entity,person_name,subject_category,flagged,flag_reason,confirmed_observations,last_seen_at "
        "FROM estate_known_vehicles WHERE estate_id=%s AND active=1 ORDER BY last_seen_at DESC,display_name LIMIT 250",
        (estate_id(),),
    )
    for row in rows:
        for key in ("first_seen_at", "last_seen_at"):
            value = row.get(key)
            if isinstance(value, datetime):
                row[key] = value.replace(tzinfo=timezone.utc).astimezone(ROME)
    return rows


def _percent(value: Any) -> float:
    try:
        number = float(value or 0)
        return round(max(0.0, min(100.0, number * 100 if number <= 1 else number)), 2)
    except (TypeError, ValueError):
        return 0.0


def _plate(value: Any) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9 -]+", "", str(value or "").upper()).strip()
    return cleaned[:40] or None


def _captured_at(value: Any = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _analyze_frame(
    image: bytes, content_type: str, source: dict[str, Any], trigger: dict[str, Any] | None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"updated": False, "reason": "Visual security analysis is not configured"}
    from ..intelligence import _openai_json_request, _openai_response_body, _response_text, record_ai_usage

    candidates = _staff_candidates()
    known = _known_vehicle_candidates()
    edge_person = str((trigger or {}).get("person_name") or "").strip() or None
    prompt = (
        "Inspect this estate security camera frame. Return JSON only as "
        "{vehicle_visible:boolean,vehicles:[{vehicle_type:string,make:string,model:string,color:string,"
        "license_plate:string|null,plate_country:string|null,plate_confidence:0..1,"
        "front_direction:'left'|'right'|'toward_camera'|'away_from_camera'|'unclear',"
        "movement_state:'entry'|'exit'|'parked'|'passing'|'unknown',confidence:0..1,"
        "staff_person_entity:string|null,known_vehicle_id:string|null,staff_match_confidence:0..1,reason:string}]}. "
        "Read a license plate only when characters are genuinely legible; never guess hidden characters. "
        "Do not identify a face or infer a driver. A staff link may use an exact configured plate, or a distinctive vehicle appearance "
        "when only one candidate fits; otherwise return null. Eufy's on-device familiar-person label may be supporting context but is not proof of the driver. "
        f"Camera: {source['display_name']}; role: {source['source_role']}; direction rule: {source['direction_rule']}. "
        "For front_right_entry, a moving vehicle front pointing right is entry and left is exit. "
        "For front_left_entry use the reverse. For toward_entry, toward camera is entry and away is exit; for away_entry use the reverse. "
        "A stationary vehicle is parked, not an entry or exit. "
        f"On-device label: {edge_person or 'none'}. Staff vehicle candidates: {json.dumps(candidates, ensure_ascii=False)}. "
        f"Administrator-confirmed known vehicles: {json.dumps(known, ensure_ascii=False, default=str)}"
    )
    encoded = base64.b64encode(image).decode("ascii")
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{content_type};base64,{encoded}", "detail": "high"},
        ]}],
        "text": {"format": {"type": "json_object"}},
    })
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        result = _openai_json_request(request, 60, "estate_vehicle_security")
        record_ai_usage("estate_vehicle_security", result, hashlib.sha256(image).hexdigest()[:24])
        return {"updated": True, "model": str(result.get("model") or settings.openai_model), "analysis": json.loads(_response_text(result) or "{}")}
    except Exception as error:
        return {"updated": False, "reason": f"Security analysis unavailable: {type(error).__name__}"}


def _save_analysis(
    source: dict[str, Any], image: bytes, content_type: str, trigger: dict[str, Any] | None,
) -> dict[str, Any]:
    digest = hashlib.sha256(image).hexdigest()
    camera = str(source["camera_entity_id"])
    duplicate = fetch_one(
        "SELECT id FROM estate_vehicle_movements WHERE estate_id=%s AND camera_entity_id=%s AND evidence_id=%s LIMIT 1",
        (estate_id(), camera, digest),
    )
    if duplicate:
        return {"updated": False, "duplicate": True, "camera": camera, "reason": "Frame already analyzed"}
    observed_at = _captured_at((trigger or {}).get("detected_at"))
    zone = _camera_zone(camera, str(source.get("display_name") or ""))
    evidence_id = archive_camera_frame(
        image, content_type=content_type, camera_entity_id=camera, observation_zone=zone,
        captured_at=observed_at, source_kind="security_event" if trigger else "security_manual_scan",
    )
    outcome = _analyze_frame(image, content_type, source, trigger)
    if not outcome.get("updated"):
        return {**outcome, "camera": camera, "evidence_id": evidence_id}
    parsed = outcome.get("analysis") or {}
    if not parsed.get("vehicle_visible"):
        return {"updated": False, "screened": True, "camera": camera, "evidence_id": evidence_id, "reason": "No vehicle visible"}

    candidates = {row["person_entity"]: row for row in _staff_candidates()}
    known_candidates = {str(row["id"]): row for row in _known_vehicle_candidates()}
    rows = [row for row in parsed.get("vehicles") or [] if isinstance(row, dict)][:12]
    saved = 0
    with transaction() as (_, cursor):
        for index, row in enumerate(rows):
            movement = str(row.get("movement_state") or "unknown").casefold()
            movement = movement if movement in MOVEMENTS else "unknown"
            direction = str(row.get("front_direction") or "unclear").casefold()
            if direction not in {"left", "right", "toward_camera", "away_from_camera", "unclear"}:
                direction = "unclear"
            person_entity = str(row.get("staff_person_entity") or "").strip()
            person = candidates.get(person_entity)
            if not person:
                person_entity = None
            known_vehicle_id = str(row.get("known_vehicle_id") or "").strip()
            known_vehicle = known_candidates.get(known_vehicle_id)
            if not known_vehicle:
                known_vehicle_id = None
            if not person_entity and known_vehicle and known_vehicle.get("person_entity"):
                person_entity = str(known_vehicle["person_entity"])
                person = candidates.get(person_entity) or {"name": known_vehicle.get("person_name")}
            source_key = hashlib.sha256(f"{camera}|{digest}|{index}".encode()).hexdigest()
            cursor.execute(
                "INSERT IGNORE INTO estate_vehicle_movements "
                "(id,estate_id,source_key,camera_entity_id,camera_name,observation_zone,observed_at,movement_state,front_direction,vehicle_index,"
                "vehicle_type,vehicle_make,vehicle_model,vehicle_color,license_plate,plate_country,plate_confidence_pct,staff_person_entity,staff_name,"
                "staff_match_confidence_pct,known_vehicle_id,subject_category,tag_label,flagged,flag_reason,confidence_pct,edge_event_types,evidence_id,model_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()), estate_id(), source_key, camera, str(source.get("display_name") or canonical_camera_name(camera)), zone,
                    observed_at, movement, direction, index, str(row.get("vehicle_type") or "")[:120] or None,
                    str(row.get("make") or "")[:120] or None, str(row.get("model") or "")[:120] or None,
                    str(row.get("color") or "")[:80] or None, _plate(row.get("license_plate")),
                    str(row.get("plate_country") or "")[:80] or None, _percent(row.get("plate_confidence")),
                    person_entity, str((person or {}).get("name") or "")[:180] or None,
                    _percent(row.get("staff_match_confidence")), known_vehicle_id,
                    str((known_vehicle or {}).get("subject_category") or ("staff" if person_entity else "unknown")),
                    str((known_vehicle or {}).get("display_name") or "")[:180] or None,
                    bool((known_vehicle or {}).get("flagged")), str((known_vehicle or {}).get("flag_reason") or "")[:500] or None,
                    _percent(row.get("confidence")),
                    json.dumps(list((trigger or {}).get("event_types") or [])), evidence_id, str(outcome.get("model") or "")[:120] or None,
                ),
            )
            saved += int(cursor.rowcount > 0)
    purge_expired_evidence()
    return {"updated": bool(saved), "movements": saved, "camera": camera, "evidence_id": evidence_id}


def refresh_estate_vehicle_security(
    *, event_triggers: list[dict[str, Any]] | None = None, force: bool = False,
) -> dict[str, Any]:
    sources = security_camera_sources(enabled_only=True)
    by_entity = {str(row["camera_entity_id"]): row for row in sources}
    triggers = [
        row for row in (event_triggers or [])
        if isinstance(row, dict) and str(row.get("camera_entity_id") or "") in by_entity and row.get("event_image_entity_id")
    ]
    token = home_assistant_token()
    if not token:
        return {"configured": bool(sources), "updated": False, "reason": "Home Assistant image access is unavailable"}
    from ..intelligence import _home_assistant_image

    results = []
    for trigger in sorted(triggers, key=lambda row: str(row.get("detected_at") or ""), reverse=True)[:4]:
        source = by_entity[str(trigger["camera_entity_id"])]
        try:
            image, content_type = _home_assistant_image(token, str(trigger["event_image_entity_id"]), image_entity=True)
            results.append(_save_analysis(source, image, content_type, trigger))
        except Exception as error:
            results.append({"updated": False, "camera": source["camera_entity_id"], "reason": f"Event image unavailable: {type(error).__name__}"})
    if force and not triggers:
        preferred = sorted(sources, key=lambda row: (not bool(row.get("always_analyze")), int(row.get("sort_order") or 0)))
        if not preferred:
            return {"configured": False, "updated": False, "reason": "Add at least one security camera"}
        source = preferred[0]
        try:
            image, content_type = _home_assistant_image(token, str(source["camera_entity_id"]), image_entity=False)
            results.append(_save_analysis(source, image, content_type, None))
        except Exception as error:
            results.append({"updated": False, "camera": source["camera_entity_id"], "reason": f"Camera unavailable: {type(error).__name__}"})
    return {
        "configured": bool(sources), "updated": any(row.get("updated") for row in results),
        "movements": sum(int(row.get("movements") or 0) for row in results), "results": results,
        "reason": "No new selected camera event" if not results else None,
    }


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=ROME).astimezone(timezone.utc).replace(tzinfo=None)
    end = datetime.combine(day, time.max, tzinfo=ROME).astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


@router.get("/dashboard", dependencies=[Depends(authorize_admin)])
def security_dashboard(day: date | None = None) -> dict[str, Any]:
    selected_day = day or datetime.now(ROME).date()
    start, end = _day_bounds(selected_day)
    rows = fetch_all(
        "SELECT id,camera_entity_id,camera_name,observation_zone,observed_at,movement_state,front_direction,vehicle_type,vehicle_make,vehicle_model,"
        "vehicle_color,license_plate,plate_country,plate_confidence_pct,staff_person_entity,staff_name,staff_match_confidence_pct,subject_category,"
        "known_vehicle_id,tag_label,flagged,flag_reason,confidence_pct,evidence_id,review_status,reviewed_by,reviewed_at,review_notes,edge_event_types "
        "FROM estate_vehicle_movements WHERE estate_id=%s AND observed_at BETWEEN %s AND %s ORDER BY observed_at DESC LIMIT 500",
        (estate_id(), start, end),
    )
    for row in rows:
        try:
            row["edge_event_types"] = json.loads(row.get("edge_event_types") or "[]")
        except (TypeError, ValueError):
            row["edge_event_types"] = []
        observed = row.get("observed_at")
        if isinstance(observed, datetime):
            row["observed_at"] = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
    entries = sum(row.get("movement_state") == "entry" and row.get("review_status") != "rejected" for row in rows)
    exits = sum(row.get("movement_state") == "exit" and row.get("review_status") != "rejected" for row in rows)
    known = _known_vehicle_candidates()
    return {
        "day": selected_day.isoformat(),
        "summary": {
            "entries": entries, "exits": exits, "vehicles": len(rows),
            "known_staff": sum(bool(row.get("staff_person_entity")) for row in rows),
            "plates": sum(bool(row.get("license_plate")) for row in rows),
            "flagged": sum(bool(row.get("flagged")) for row in rows),
            "needs_review": sum(row.get("review_status") == "unreviewed" for row in rows),
            "known_vehicles": len(known),
            "known_flagged": sum(bool(row.get("flagged")) for row in known),
            "known_observations": sum(int(row.get("confirmed_observations") or 0) for row in known),
        },
        "movements": rows, "cameras": security_camera_sources(), "camera_catalog": _camera_catalog(),
        "known_vehicles": known,
        "staff": _staff_candidates(),
        "policy": "Security evidence is administrator-only and retention-limited. Tags support estate auditing; payroll remains separately approved.",
    }


@router.put("/cameras", dependencies=[Depends(authorize_admin)])
def save_security_cameras(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    values = payload.get("cameras")
    if not isinstance(values, list) or len(values) > 32:
        raise HTTPException(422, "Provide a list of no more than 32 cameras")
    cleaned = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("camera_entity_id") or "").strip()
        if not entity_id.startswith("camera."):
            continue
        role = str(item.get("source_role") or "supporting")
        rule = str(item.get("direction_rule") or "none")
        cleaned.append({
            "camera_entity_id": entity_id[:255],
            "display_name": str(item.get("display_name") or canonical_camera_name(entity_id))[:180],
            "source_role": role if role in SOURCE_ROLES else "supporting",
            "direction_rule": rule if rule in DIRECTION_RULES else "none",
            "enabled": bool(item.get("enabled", True)), "always_analyze": bool(item.get("always_analyze")),
            "sort_order": index * 10,
        })
    with transaction() as (_, cursor):
        keep = [row["camera_entity_id"] for row in cleaned]
        if keep:
            placeholders = ",".join(["%s"] * len(keep))
            cursor.execute(
                f"DELETE FROM estate_security_cameras WHERE estate_id=%s AND camera_entity_id NOT IN ({placeholders})",
                (estate_id(), *keep),
            )
        else:
            cursor.execute("DELETE FROM estate_security_cameras WHERE estate_id=%s", (estate_id(),))
        for row in cleaned:
            cursor.execute(
                "INSERT INTO estate_security_cameras (id,estate_id,camera_entity_id,display_name,source_role,direction_rule,enabled,always_analyze,sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),source_role=VALUES(source_role),"
                "direction_rule=VALUES(direction_rule),enabled=VALUES(enabled),always_analyze=VALUES(always_analyze),sort_order=VALUES(sort_order)",
                (str(uuid4()), estate_id(), row["camera_entity_id"], row["display_name"], row["source_role"], row["direction_rule"],
                 row["enabled"], row["always_analyze"], row["sort_order"]),
            )
        audit(cursor, "update", "estate_security_cameras", "camera-list", {"count": len(cleaned)}, request_username(request))
    return {"saved": True, "cameras": security_camera_sources()}


@router.post("/scan", dependencies=[Depends(authorize_admin)])
def scan_security_camera(request: Request) -> dict[str, Any]:
    result = refresh_estate_vehicle_security(force=True)
    with transaction() as (_, cursor):
        audit(cursor, "run", "estate_vehicle_security", "manual", result, request_username(request))
    return result


@router.patch("/movements/{movement_id}", dependencies=[Depends(authorize_admin)])
def update_vehicle_movement(movement_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    current = fetch_one(
        "SELECT * FROM estate_vehicle_movements WHERE estate_id=%s AND id=%s", (estate_id(), movement_id),
    )
    if not current:
        raise HTTPException(404, "Vehicle movement not found")
    review_status = str(payload.get("review_status") or "unreviewed")
    if review_status not in {"unreviewed", "confirmed", "rejected"}:
        raise HTTPException(422, "Invalid review status")
    movement = str(payload.get("movement_state") or "unknown")
    category = str(payload.get("subject_category") or "unknown")
    if movement not in MOVEMENTS or category not in SUBJECT_CATEGORIES:
        raise HTTPException(422, "Invalid movement or category")
    person_entity = str(payload.get("staff_person_entity") or "").strip()[:255] or None
    staff = {row["person_entity"]: row for row in _staff_candidates()}.get(person_entity or "")
    plate = _plate(payload.get("license_plate"))
    tag_label = str(payload.get("tag_label") or "")[:180] or None
    known_vehicle_id = current.get("known_vehicle_id")
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE estate_vehicle_movements SET movement_state=%s,license_plate=%s,staff_person_entity=%s,staff_name=%s,subject_category=%s,"
            "tag_label=%s,flagged=%s,flag_reason=%s,review_status=%s,reviewed_by=%s,reviewed_at=NOW(6),review_notes=%s WHERE estate_id=%s AND id=%s",
            (movement, plate, person_entity, str((staff or {}).get("name") or "")[:180] or None, category,
             tag_label, bool(payload.get("flagged")),
             str(payload.get("flag_reason") or "")[:500] or None, review_status, request_username(request),
             str(payload.get("review_notes") or "")[:1000] or None, estate_id(), movement_id),
        )
        if review_status == "confirmed":
            identity_basis = (
                f"plate:{plate}" if plate else f"tag:{tag_label.casefold().strip()}" if tag_label else
                "|".join(str(value or "").casefold().strip() for value in (
                    person_entity, current.get("vehicle_color"), current.get("vehicle_make"),
                    current.get("vehicle_model"), current.get("vehicle_type"),
                ))
            )
            identity_key = hashlib.sha256(identity_basis.encode()).hexdigest()
            known_vehicle_id = str(known_vehicle_id or uuid4())
            display_name = tag_label or str((staff or {}).get("name") or "").strip() or " ".join(
                str(current.get(key) or "").strip() for key in ("vehicle_color", "vehicle_make", "vehicle_model")
            ).strip() or "Known vehicle"
            cursor.execute(
                "INSERT INTO estate_known_vehicles (id,estate_id,identity_key,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,"
                "license_plate,plate_country,person_entity,person_name,subject_category,flagged,flag_reason,notes,first_seen_at,last_seen_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),vehicle_type=COALESCE(VALUES(vehicle_type),vehicle_type),"
                "vehicle_make=COALESCE(VALUES(vehicle_make),vehicle_make),vehicle_model=COALESCE(VALUES(vehicle_model),vehicle_model),"
                "vehicle_color=COALESCE(VALUES(vehicle_color),vehicle_color),license_plate=COALESCE(VALUES(license_plate),license_plate),"
                "plate_country=COALESCE(VALUES(plate_country),plate_country),person_entity=COALESCE(VALUES(person_entity),person_entity),"
                "person_name=COALESCE(VALUES(person_name),person_name),subject_category=VALUES(subject_category),flagged=VALUES(flagged),"
                "flag_reason=VALUES(flag_reason),notes=COALESCE(VALUES(notes),notes),confirmed_observations=confirmed_observations+1,"
                "first_seen_at=LEAST(COALESCE(first_seen_at,VALUES(first_seen_at)),VALUES(first_seen_at)),last_seen_at=GREATEST(COALESCE(last_seen_at,VALUES(last_seen_at)),VALUES(last_seen_at)),active=1",
                (known_vehicle_id, estate_id(), identity_key, display_name[:180], current.get("vehicle_type"), current.get("vehicle_make"),
                 current.get("vehicle_model"), current.get("vehicle_color"), plate, current.get("plate_country"), person_entity,
                 str((staff or {}).get("name") or "")[:180] or None, category, bool(payload.get("flagged")),
                 str(payload.get("flag_reason") or "")[:500] or None, str(payload.get("review_notes") or "")[:1000] or None,
                 current.get("observed_at"), current.get("observed_at")),
            )
            cursor.execute("SELECT id FROM estate_known_vehicles WHERE estate_id=%s AND identity_key=%s", (estate_id(), identity_key))
            saved_known = cursor.fetchone()
            if saved_known:
                known_vehicle_id = str(saved_known["id"])
                cursor.execute("UPDATE estate_vehicle_movements SET known_vehicle_id=%s WHERE estate_id=%s AND id=%s", (known_vehicle_id, estate_id(), movement_id))
        audit(cursor, "review", "estate_vehicle_movement", movement_id, {"status": review_status, "category": category, "flagged": bool(payload.get("flagged"))}, request_username(request))
    if current.get("evidence_id"):
        extend_evidence_review(str(current["evidence_id"]), review_status)
    return {"saved": True, "id": movement_id, "known_vehicle_id": known_vehicle_id}


@router.delete("/known-vehicles/{vehicle_id}", dependencies=[Depends(authorize_admin)])
def archive_known_vehicle(vehicle_id: str, request: Request) -> dict[str, Any]:
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE estate_known_vehicles SET active=0 WHERE estate_id=%s AND id=%s", (estate_id(), vehicle_id),
        )
        if not changed:
            raise HTTPException(404, "Known vehicle not found")
        audit(cursor, "archive", "estate_known_vehicle", vehicle_id, {}, request_username(request))
    return {"saved": True, "id": vehicle_id, "active": False}
