"""Administrator-only estate security and vehicle movement intelligence."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import time as time_module
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image

from ..access import authorize_admin, people_profiles, request_username
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import audit, estate_id
from .camera_naming import canonical_camera_name
from .worker_evidence_archive import archive_camera_frame, extend_evidence_review, purge_expired_evidence, read_camera_evidence
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


def _camera_configuration_audit(sources: list[dict[str, Any]], catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconcile the saved vehicle pipeline with the current HA camera inventory."""
    by_entity = {str(row.get("entity_id") or ""): row for row in catalog}
    enabled = [row for row in sources if row.get("enabled")]
    missing = [row for row in enabled if str(row.get("camera_entity_id") or "") not in by_entity]
    unavailable = [
        row for row in enabled
        if str(row.get("camera_entity_id") or "") in by_entity
        and not bool(by_entity[str(row.get("camera_entity_id") or "")].get("available"))
    ]
    name_drift = []
    for source in sources:
        entity_id = str(source.get("camera_entity_id") or "")
        current = by_entity.get(entity_id)
        if current and str(source.get("display_name") or "").strip() != str(current.get("name") or "").strip():
            name_drift.append({"entity_id": entity_id, "saved_name": source.get("display_name"), "current_name": current.get("name")})
    configured_ids = {str(row.get("camera_entity_id") or "") for row in sources}
    available_unconfigured = sum(bool(row.get("available")) and str(row.get("entity_id") or "") not in configured_ids for row in catalog)
    return {
        "status": "attention" if missing or unavailable or name_drift else "healthy",
        "enabled": len(enabled), "missing": missing, "unavailable": unavailable,
        "name_drift": name_drift, "available_unconfigured": available_unconfigured,
    }


def _stored_event_source(event: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match retained HomeBase evidence to one configured security camera."""
    from ..intelligence import _eufy_event_name

    event_name = _eufy_event_name(event.get("device_name"))
    if not event_name:
        return None
    matches: list[tuple[int, dict[str, Any]]] = []
    for source in sources:
        names = {
            _eufy_event_name(source.get("display_name")),
            _eufy_event_name(source.get("camera_entity_id")),
        } - {""}
        score = max(
            (3 if event_name == name else 2 if event_name in name or name in event_name else 0 for name in names),
            default=0,
        )
        if score:
            matches.append((score, source))
    matches.sort(key=lambda item: item[0], reverse=True)
    if not matches or (len(matches) > 1 and matches[0][0] == matches[1][0]):
        return None
    return matches[0][1]


def _unseen_stored_security_frames(
    token: str, sources: list[dict[str, Any]], *, limit: int = 4,
) -> list[tuple[dict[str, Any], bytes, str, dict[str, Any]]]:
    """Load recent saved Eufy frames that the periodic sensor poll could miss."""
    from ..intelligence import _eufy_evidence_events

    try:
        events = _eufy_evidence_events()
    except Exception:
        return []
    now = datetime.now(timezone.utc)
    candidates: list[tuple[datetime, dict[str, Any], dict[str, Any]]] = []
    for event in events:
        source = _stored_event_source(event, sources)
        media_path = str(event.get("recognition_image_url") or "")
        if not source or not media_path.startswith("/api/baiamonte_eufy/evidence/"):
            continue
        try:
            observed_at = datetime.fromisoformat(str(event.get("start") or "").replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
            observed_at = observed_at.astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if observed_at < now - timedelta(days=2) or observed_at > now + timedelta(minutes=5):
            continue
        candidates.append((observed_at, source, event))

    frames: list[tuple[dict[str, Any], bytes, str, dict[str, Any]]] = []
    for observed_at, source, event in sorted(candidates, key=lambda item: item[0], reverse=True):
        request = urllib.request.Request(
            "http://supervisor/core" + str(event["recognition_image_url"]),
            headers={"Authorization": f"Bearer {token}", "Accept": "image/jpeg,image/png,image/webp"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                image = response.read(12 * 1024 * 1024)
                content_type = str(response.headers.get_content_type() or "image/jpeg")
            if not image or not content_type.startswith("image/"):
                continue
        except Exception:
            continue
        digest = hashlib.sha256(image).hexdigest()
        if fetch_one(
            "SELECT id FROM estate_vehicle_frame_checks WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s LIMIT 1",
            (estate_id(), str(source["camera_entity_id"]), digest),
        ):
            continue
        ai = event.get("ai") if isinstance(event.get("ai"), dict) else {}
        categories = list(dict.fromkeys([
            *(event.get("ai_categories") or []), *(ai.get("categories") or []),
        ]))[:16]
        trigger = {
            "camera_entity_id": source["camera_entity_id"],
            "camera_name": source.get("display_name"),
            "detected_at": observed_at.isoformat(),
            "event_types": [
                *(f"homebase_ai:{value}" for value in categories if value),
                "image_source:homebase_stored_recording",
            ],
            "homebase_ai_categories": categories,
            "recognition_image_source": "homebase_stored_recording",
        }
        frames.append((source, image, content_type, trigger))
        if len(frames) >= max(1, min(int(limit), 8)):
            break
    return frames


def _fresh_security_camera_image(token: str, camera_entity_id: str) -> tuple[bytes, str]:
    """Request one bounded Eufy still before reading the HA camera proxy."""
    from ..intelligence import _ha_post, _home_assistant_image

    try:
        _ha_post("/services/eufy_security/capture_snapshot", {"entity_id": camera_entity_id})
        time_module.sleep(3.0)
    except Exception:
        # Wired or non-Eufy cameras do not expose this service; their normal
        # Home Assistant camera proxy remains the correct bounded fallback.
        pass
    return _home_assistant_image(token, camera_entity_id, image_entity=False)


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


def _known_vehicle_candidates(*, include_recent_inactive: bool = False) -> list[dict[str, Any]]:
    active_clause = "" if include_recent_inactive else " AND active=1"
    history_clause = " AND (active=1 OR last_seen_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 90 DAY))" if include_recent_inactive else ""
    rows = fetch_all(
        "SELECT id,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,license_plate,plate_country,"
        "person_entity,person_name,subject_category,flagged,flag_reason,confirmed_observations,last_seen_at,active,notes "
        f"FROM estate_known_vehicles WHERE estate_id=%s{active_clause}{history_clause} "
        "ORDER BY active DESC,last_seen_at DESC,display_name LIMIT 250",
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


def _review_status_for_finding(
    known_vehicle: dict[str, Any] | None, movement: str, confidence_pct: float,
) -> str:
    """Auto-clear only routine, high-confidence matches to an approved vehicle."""
    if (
        known_vehicle
        and not bool(known_vehicle.get("flagged"))
        and movement != "unknown"
        and confidence_pct >= 90
    ):
        return "confirmed"
    return "unreviewed"


def _plate(value: Any) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9 -]+", "", str(value or "").upper()).strip()
    return cleaned[:40] or None


def _plate_pattern(value: Any) -> str | None:
    pattern = re.sub(r"[^A-Z0-9?]+", "", str(value or "").upper())
    if not 4 <= len(pattern) <= 10 or sum(char != "?" for char in pattern) < 3:
        return None
    return pattern


def _merge_plate_patterns(values: list[Any]) -> str | None:
    combined = _combine_plate_patterns(values)
    return combined if combined and "?" not in combined else None


def _combine_plate_patterns(values: list[Any]) -> str | None:
    """Combine compatible views while preserving unresolved positions as question marks."""
    patterns = [pattern for value in values if (pattern := _plate_pattern(value))]
    if len(patterns) < 2:
        return None
    lengths: dict[int, list[str]] = {}
    for pattern in patterns:
        lengths.setdefault(len(pattern), []).append(pattern)
    compatible = max(lengths.values(), key=len)
    if len(compatible) < 2:
        return None
    overlap = max(
        sum(left == right and left != "?" for left, right in zip(first, second))
        for index, first in enumerate(compatible)
        for second in compatible[index + 1:]
    )
    if overlap < 2:
        return None
    resolved = []
    for index in range(len(compatible[0])):
        observed = {pattern[index] for pattern in compatible if pattern[index] != "?"}
        resolved.append(observed.pop() if len(observed) == 1 else "?")
    return _plate_pattern("".join(resolved))


def _known_vehicle_identity_basis(
    plate: str | None,
    person_entity: str | None,
    vehicle_color: Any,
    vehicle_make: Any,
    vehicle_model: Any,
    vehicle_type: Any,
) -> str | None:
    """Return a stable identity only when the evidence distinguishes a vehicle."""
    if plate:
        return f"plate:{plate}"
    appearance = [
        str(value or "").casefold().strip()
        for value in (vehicle_color, vehicle_make, vehicle_model, vehicle_type)
    ]
    meaningful = {value for value in appearance if value and value not in {"unknown", "car", "vehicle"}}
    if len(meaningful) < 2:
        return None
    return "appearance:" + "|".join([str(person_entity or "unlinked").casefold().strip(), *appearance])


def _captured_at(value: Any = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _plate_crop(image: bytes, normalized_box: Any) -> bytes | None:
    """Crop and enlarge a model-located plate from the untouched camera frame."""
    if not isinstance(normalized_box, list) or len(normalized_box) != 4:
        return None
    try:
        coords = [max(0.0, min(1000.0, float(value))) for value in normalized_box]
        source = Image.open(io.BytesIO(image)).convert("RGB")
    except (TypeError, ValueError, OSError):
        return None
    x1, y1, x2, y2 = coords
    if x2 <= x1 or y2 <= y1:
        return None
    left, top, right, bottom = (
        x1 * source.width / 1000, y1 * source.height / 1000,
        x2 * source.width / 1000, y2 * source.height / 1000,
    )
    pad_x = max(8, (right - left) * 0.45)
    pad_y = max(8, (bottom - top) * 0.9)
    bounds = (
        max(0, int(left - pad_x)), max(0, int(top - pad_y)),
        min(source.width, int(right + pad_x)), min(source.height, int(bottom + pad_y)),
    )
    crop = source.crop(bounds)
    if crop.width < 24 or crop.height < 10:
        return None
    scale = min(6, max(2, 1200 // max(crop.width, 1)))
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    crop.save(output, format="JPEG", quality=96, subsampling=0)
    return output.getvalue()


def _vehicle_plate_search_crop(image: bytes, normalized_box: Any) -> bytes | None:
    """Create a conservative lower-vehicle search crop when no tight plate box is available."""
    if not isinstance(normalized_box, list) or len(normalized_box) != 4:
        return None
    try:
        coords = [max(0.0, min(1000.0, float(value))) for value in normalized_box]
        source = Image.open(io.BytesIO(image)).convert("RGB")
    except (TypeError, ValueError, OSError):
        return None
    x1, y1, x2, y2 = coords
    if x2 <= x1 or y2 <= y1:
        return None
    width, height = x2 - x1, y2 - y1
    # Front and rear plates normally occupy the lower half of a vehicle. Keep
    # enough context for the reader to locate the plate without sending the
    # entire wide security frame a second time.
    bounds = (
        max(0, int((x1 - width * 0.08) * source.width / 1000)),
        max(0, int((y1 + height * 0.38) * source.height / 1000)),
        min(source.width, int((x2 + width * 0.08) * source.width / 1000)),
        min(source.height, int((y2 + height * 0.08) * source.height / 1000)),
    )
    crop = source.crop(bounds)
    if crop.width < 40 or crop.height < 20:
        return None
    scale = min(5, max(2, 1200 // max(crop.width, 1)))
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    crop.save(output, format="JPEG", quality=96, subsampling=0)
    return output.getvalue()


def _read_plate_crop(crop: bytes, camera_name: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    from ..intelligence import _openai_json_request, _openai_response_body, _response_text, record_ai_usage

    prompt = (
        "This is an enlarged crop containing a vehicle plate area from an estate security camera. "
        "Return JSON only as {license_plate:string|null,plate_pattern:string|null,plate_country:string|null,plate_confidence:0..1}. "
        "Transcribe only characters that are genuinely legible. plate_pattern must preserve character positions and use ? for each unreadable character, "
        "for example AB?23?D. license_plate must be null unless every character is legible. Omit spaces only when clearly decorative. "
        "Return null values with low confidence if even the character positions are unclear. Never complete or guess characters. "
        f"Camera: {camera_name}."
    )
    encoded = base64.b64encode(crop).decode("ascii")
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
        ]}],
        "text": {"format": {"type": "json_object"}},
    })
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        result = _openai_json_request(request, 45, "estate_vehicle_plate_read")
        record_ai_usage("estate_vehicle_plate_read", result, hashlib.sha256(crop).hexdigest()[:24])
        parsed = json.loads(_response_text(result) or "{}")
        pattern = _plate_pattern(parsed.get("plate_pattern") or parsed.get("license_plate"))
        plate = _plate(parsed.get("license_plate")) if pattern and "?" not in pattern else None
        confidence = float(parsed.get("plate_confidence") or 0)
        if not pattern or confidence < 0.45:
            return None
        return {
            "license_plate": plate if plate and confidence >= 0.7 else None,
            "plate_pattern": pattern,
            "plate_country": str(parsed.get("plate_country") or "")[:80] or None,
            "plate_confidence": min(1.0, confidence),
        }
    except Exception:
        return None


def _enrich_plate_reads(image: bytes, rows: list[dict[str, Any]], camera_name: str) -> list[dict[str, Any]]:
    reads = 0
    for row in rows:
        if reads >= 2 or (_plate(row.get("license_plate")) and _percent(row.get("plate_confidence")) >= 70):
            continue
        crop = _plate_crop(image, row.get("plate_box"))
        if not crop:
            crop = _vehicle_plate_search_crop(image, row.get("vehicle_box"))
        if not crop:
            continue
        row["_plate_read_attempted"] = True
        reads += 1
        plate = _read_plate_crop(crop, camera_name)
        if plate:
            row.update(plate)
    return rows


def _analyze_frame(
    image: bytes, content_type: str, source: dict[str, Any], trigger: dict[str, Any] | None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"updated": False, "reason": "Visual security analysis is not configured"}
    from ..intelligence import _openai_json_request, _openai_response_body, _response_text, record_ai_usage

    candidates = _staff_candidates()
    known = _known_vehicle_candidates(include_recent_inactive=True)
    edge_person = str((trigger or {}).get("person_name") or "").strip() or None
    homebase_ai = list((trigger or {}).get("homebase_ai_categories") or [])
    prompt = (
        "Inspect this estate security camera frame. Return JSON only as "
        "{vehicle_visible:boolean,vehicles:[{vehicle_type:string,make:string,model:string,color:string,"
        "license_plate:string|null,plate_country:string|null,plate_confidence:0..1,"
        "plate_box:[x1,y1,x2,y2]|null,vehicle_box:[x1,y1,x2,y2]|null,"
        "front_direction:'left'|'right'|'toward_camera'|'away_from_camera'|'unclear',"
        "movement_state:'entry'|'exit'|'parked'|'passing'|'unknown',confidence:0..1,"
        "staff_person_entity:string|null,known_vehicle_id:string|null,staff_match_confidence:0..1,reason:string}]}. "
        "Read a license plate only when characters are genuinely legible; never guess hidden characters. "
        "Always include a tight vehicle_box using 0..1000 coordinates. When a plate is visible, include its tight plate_box even if the characters are too small to read. "
        "Do not identify a face or infer a driver. A staff link may use an exact configured plate, or a distinctive vehicle appearance "
        "when only one candidate fits; otherwise return null. Eufy's on-device familiar-person label may be supporting context but is not proof of the driver. "
        f"Camera: {source['display_name']}; role: {source['source_role']}; direction rule: {source['direction_rule']}. "
        "For front_right_entry, a moving vehicle front pointing right is entry and left is exit. "
        "For front_left_entry use the reverse. For toward_entry, toward camera is entry and away is exit; for away_entry use the reverse. "
        "A stationary vehicle is parked, not an entry or exit. "
        f"On-device label: {edge_person or 'none'}. HomeBase AI object categories: {json.dumps(homebase_ai)}; "
        "these categories and any visible Eufy marking are supporting location hints only, not identity or plate text. "
        f"Staff vehicle candidates: {json.dumps(candidates, ensure_ascii=False)}. "
        "Inactive vehicles are historical context only: do not match them as a current recurring vehicle. "
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
        "SELECT id,vehicle_visible FROM estate_vehicle_frame_checks WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s LIMIT 1",
        (estate_id(), camera, digest),
    )
    plate_backfill = bool(duplicate and duplicate.get("vehicle_visible"))
    plate_checked = fetch_one(
        "SELECT id FROM estate_vehicle_plate_reads WHERE estate_id=%s AND frame_sha256=%s LIMIT 1",
        (estate_id(), digest),
    ) if plate_backfill else None
    if duplicate and (not plate_backfill or plate_checked):
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
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT IGNORE INTO estate_vehicle_frame_checks "
                "(estate_id,camera_entity_id,frame_sha256,evidence_id,vehicle_visible,movement_count,source_kind) "
                "VALUES (%s,%s,%s,%s,FALSE,0,%s)",
                (estate_id(), camera, digest, evidence_id, "event" if trigger else "scheduled"),
            )
        return {"updated": False, "screened": True, "camera": camera, "evidence_id": evidence_id, "reason": "No vehicle visible"}

    candidates = {row["person_entity"]: row for row in _staff_candidates()}
    known_candidates = {str(row["id"]): row for row in _known_vehicle_candidates()}
    rows = [row for row in parsed.get("vehicles") or [] if isinstance(row, dict)][:12]
    rows = _enrich_plate_reads(image, rows, str(source.get("display_name") or canonical_camera_name(camera)))
    saved = 0
    plate_updates = 0
    with transaction() as (_, cursor):
        cursor.execute(
            "DELETE FROM estate_vehicle_plate_reads WHERE estate_id=%s AND observed_at<DATE_SUB(UTC_TIMESTAMP(),INTERVAL 180 DAY)",
            (estate_id(),),
        )
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
            confidence_pct = _percent(row.get("confidence"))
            review_status = _review_status_for_finding(known_vehicle, movement, confidence_pct)
            source_key = hashlib.sha256(f"{camera}|{digest}|{index}".encode()).hexdigest()
            cursor.execute(
                "SELECT known_vehicle_id,staff_person_entity,staff_name FROM estate_vehicle_movements "
                "WHERE estate_id=%s AND source_key=%s LIMIT 1",
                (estate_id(), source_key),
            )
            existing_movement = cursor.fetchone()
            if existing_movement and existing_movement.get("known_vehicle_id"):
                known_vehicle_id = str(existing_movement["known_vehicle_id"])
                known_vehicle = known_candidates.get(known_vehicle_id)
                person_entity = str(existing_movement.get("staff_person_entity") or person_entity or "") or None
                person = candidates.get(person_entity or "") or {"name": existing_movement.get("staff_name")}
            plate = _plate(row.get("license_plate"))
            pattern = _plate_pattern(row.get("plate_pattern") or plate)
            appearance_basis = _known_vehicle_identity_basis(
                None, person_entity, row.get("color"), row.get("make"), row.get("model"), row.get("vehicle_type"),
            )
            vehicle_learning_key = f"known:{known_vehicle_id}" if known_vehicle_id else (
                f"appearance:{hashlib.sha256(appearance_basis.encode()).hexdigest()}" if appearance_basis else None
            )
            if row.get("_plate_read_attempted") or pattern:
                cursor.execute(
                    "INSERT IGNORE INTO estate_vehicle_plate_reads "
                    "(id,estate_id,source_key,camera_entity_id,frame_sha256,vehicle_identity_key,plate_pattern,plate_country,confidence_pct,observed_at,evidence_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (str(uuid4()), estate_id(), source_key, camera, digest, vehicle_learning_key, pattern,
                     str(row.get("plate_country") or "")[:80] or None, _percent(row.get("plate_confidence")), observed_at, evidence_id),
                )
            if pattern and vehicle_learning_key:
                cursor.execute(
                    "SELECT plate_pattern FROM estate_vehicle_plate_reads WHERE estate_id=%s AND vehicle_identity_key=%s AND plate_pattern IS NOT NULL "
                    "AND observed_at>=DATE_SUB(%s,INTERVAL 180 DAY) ORDER BY confidence_pct DESC,observed_at DESC LIMIT 24",
                    (estate_id(), vehicle_learning_key, observed_at),
                )
                learned_plate = _merge_plate_patterns([item["plate_pattern"] for item in cursor.fetchall()])
                if learned_plate:
                    plate = learned_plate
                    row["plate_confidence"] = max(75.0, _percent(row.get("plate_confidence")))
            if plate and known_vehicle_id:
                cursor.execute(
                    "UPDATE estate_known_vehicles SET license_plate=COALESCE(license_plate,%s),"
                    "plate_country=COALESCE(plate_country,%s) WHERE estate_id=%s AND id=%s",
                    (plate, str(row.get("plate_country") or "")[:80] or None, estate_id(), known_vehicle_id),
                )
            if plate_backfill:
                if plate and existing_movement:
                    cursor.execute(
                        "UPDATE estate_vehicle_movements SET license_plate=%s,plate_country=COALESCE(plate_country,%s),"
                        "plate_confidence_pct=GREATEST(plate_confidence_pct,%s) WHERE estate_id=%s AND source_key=%s",
                        (plate, str(row.get("plate_country") or "")[:80] or None,
                         _percent(row.get("plate_confidence")), estate_id(), source_key),
                    )
                    plate_updates += int(cursor.rowcount > 0)
                continue
            cursor.execute(
                "INSERT IGNORE INTO estate_vehicle_movements "
                "(id,estate_id,source_key,camera_entity_id,camera_name,observation_zone,observed_at,movement_state,front_direction,vehicle_index,"
                "vehicle_type,vehicle_make,vehicle_model,vehicle_color,license_plate,plate_country,plate_confidence_pct,staff_person_entity,staff_name,"
                "staff_match_confidence_pct,known_vehicle_id,subject_category,tag_label,flagged,flag_reason,confidence_pct,edge_event_types,evidence_id,model_version,"
                "review_status,reviewed_by,reviewed_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()), estate_id(), source_key, camera, str(source.get("display_name") or canonical_camera_name(camera)), zone,
                    observed_at, movement, direction, index, str(row.get("vehicle_type") or "")[:120] or None,
                    str(row.get("make") or "")[:120] or None, str(row.get("model") or "")[:120] or None,
                    str(row.get("color") or "")[:80] or None, plate,
                    str(row.get("plate_country") or "")[:80] or None, _percent(row.get("plate_confidence")),
                    person_entity, str((person or {}).get("name") or "")[:180] or None,
                    _percent(row.get("staff_match_confidence")), known_vehicle_id,
                    str((known_vehicle or {}).get("subject_category") or ("staff" if person_entity else "unknown")),
                    str((known_vehicle or {}).get("display_name") or "")[:180] or None,
                    bool((known_vehicle or {}).get("flagged")), str((known_vehicle or {}).get("flag_reason") or "")[:500] or None,
                    confidence_pct,
                    json.dumps(list((trigger or {}).get("event_types") or [])), evidence_id, str(outcome.get("model") or "")[:120] or None,
                    review_status, "automatic_known_vehicle" if review_status == "confirmed" else None,
                    observed_at if review_status == "confirmed" else None,
                ),
            )
            inserted = cursor.rowcount > 0
            saved += int(inserted)
            if inserted and review_status == "confirmed" and known_vehicle_id:
                cursor.execute(
                    "UPDATE estate_known_vehicles SET confirmed_observations=confirmed_observations+1,"
                    "last_seen_at=GREATEST(COALESCE(last_seen_at,%s),%s) WHERE estate_id=%s AND id=%s",
                    (observed_at, observed_at, estate_id(), known_vehicle_id),
                )
        cursor.execute(
            "INSERT IGNORE INTO estate_vehicle_frame_checks "
            "(estate_id,camera_entity_id,frame_sha256,evidence_id,vehicle_visible,movement_count,source_kind) "
            "VALUES (%s,%s,%s,%s,TRUE,%s,%s)",
            (estate_id(), camera, digest, evidence_id, saved, "event" if trigger else "scheduled"),
        )
    purge_expired_evidence()
    return {
        "updated": bool(saved or plate_updates), "movements": saved, "plate_updates": plate_updates,
        "camera": camera, "evidence_id": evidence_id,
    }


def _backfill_recent_plate_evidence(limit: int = 4) -> dict[str, Any] | None:
    rows = fetch_all(
        "SELECT movement.camera_entity_id,movement.camera_name,movement.evidence_id,movement.observed_at "
        "FROM estate_vehicle_movements movement "
        "LEFT JOIN estate_vehicle_plate_reads plate ON plate.estate_id=movement.estate_id AND plate.source_key=movement.source_key "
        "WHERE movement.estate_id=%s AND movement.evidence_id IS NOT NULL AND movement.license_plate IS NULL "
        "AND plate.id IS NULL ORDER BY (movement.known_vehicle_id IS NOT NULL) DESC,movement.observed_at DESC LIMIT %s",
        (estate_id(), max(1, min(int(limit), 8))),
    )
    if not rows:
        return None
    configured = {str(item["camera_entity_id"]): item for item in security_camera_sources()}
    token = home_assistant_token()
    from ..intelligence import _best_eufy_recognition_image
    results = []
    for row in rows:
        retained = read_camera_evidence(str(row["evidence_id"]))
        if not retained:
            results.append({"updated": False, "reason": "Retained plate evidence is unavailable"})
            continue
        metadata, image = retained
        camera = str(row["camera_entity_id"])
        source = configured.get(camera) or {
            "camera_entity_id": camera,
            "display_name": str(row.get("camera_name") or canonical_camera_name(camera)),
            "source_role": "supporting", "direction_rule": "none",
        }
        content_type = str(metadata.get("content_type") or "image/jpeg")
        trigger = {
            "camera_entity_id": camera,
            "camera_name": str(row.get("camera_name") or source.get("display_name") or ""),
            "detected_at": row.get("observed_at"),
        }
        if token:
            image, content_type, image_source = _best_eufy_recognition_image(
                token, trigger, image, content_type,
            )
            trigger["recognition_image_source"] = image_source
        results.append(_save_analysis(
            source, image, content_type, trigger,
        ))
    return {"updated": any(row.get("updated") for row in results), "checked": len(results), "results": results}


def refresh_estate_vehicle_security(
    *, event_triggers: list[dict[str, Any]] | None = None, force: bool = False,
    all_recurring: bool = False,
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
    from ..intelligence import _best_eufy_recognition_image, _home_assistant_image

    results = []
    for trigger in sorted(triggers, key=lambda row: str(row.get("detected_at") or ""), reverse=True)[:4]:
        source = by_entity[str(trigger["camera_entity_id"])]
        try:
            image, content_type = _home_assistant_image(token, str(trigger["event_image_entity_id"]), image_entity=True)
            image, content_type, image_source = _best_eufy_recognition_image(
                token, trigger, image, content_type,
            )
            trigger["recognition_image_source"] = image_source
            results.append(_save_analysis(source, image, content_type, trigger))
        except Exception as error:
            results.append({"updated": False, "camera": source["camera_entity_id"], "reason": f"Event image unavailable: {type(error).__name__}"})
    if not triggers:
        stored_frames = _unseen_stored_security_frames(token, sources, limit=4)
        for source, image, content_type, trigger in stored_frames:
            results.append(_save_analysis(source, image, content_type, trigger))
        if stored_frames:
            return {
                "configured": bool(sources), "updated": any(row.get("updated") for row in results),
                "movements": sum(int(row.get("movements") or 0) for row in results), "results": results,
                "reason": None,
            }
        preferred = sorted(sources, key=lambda row: (not bool(row.get("always_analyze")), int(row.get("sort_order") or 0)))
        if not preferred:
            return {"configured": False, "updated": False, "reason": "Add at least one security camera"}
        if force:
            selected_sources = [row for row in preferred if bool(row.get("always_analyze"))] if all_recurring else preferred[:1]
            selected_sources = selected_sources or preferred[:1]
        else:
            recurring = [row for row in preferred if bool(row.get("always_analyze"))]
            if not recurring:
                selected_sources = []
            else:
                activity = {
                    str(row.get("camera_entity_id") or ""): row.get("checked_at")
                    for row in fetch_all(
                        "SELECT camera_entity_id,MAX(checked_at) checked_at FROM estate_vehicle_frame_checks "
                        "WHERE estate_id=%s GROUP BY camera_entity_id",
                        (estate_id(),),
                    )
                }
                selected_sources = [min(recurring, key=lambda row: activity.get(str(row["camera_entity_id"])) or datetime.min)]
        if not selected_sources:
            return {
                "configured": bool(sources), "updated": False, "movements": 0, "results": [],
                "reason": "No recurring security camera is enabled",
            }
        for source in selected_sources:
            try:
                image, content_type = (
                    _fresh_security_camera_image(token, str(source["camera_entity_id"]))
                    if force else
                    _home_assistant_image(token, str(source["camera_entity_id"]), image_entity=False)
                )
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


def _recent_recognized_sightings(selected_day: date) -> list[dict[str, Any]]:
    """Return recent named-person evidence without pretending a vehicle match is facial ID."""
    start, _ = _day_bounds(selected_day - timedelta(days=6))
    _, end = _day_bounds(selected_day)
    people = fetch_all(
        "SELECT id,person_entity,observed_label,camera_entity_id,camera_name,observation_zone,observed_at,"
        "source_kind,confidence_pct,review_status FROM worker_person_observations "
        "WHERE estate_id=%s AND observed_at BETWEEN %s AND %s "
        "AND review_status<>'rejected' AND (person_entity IS NOT NULL OR observed_label IS NOT NULL) "
        "ORDER BY observed_at DESC LIMIT 250",
        (estate_id(), start, end),
    )
    vehicles = fetch_all(
        "SELECT id,staff_person_entity,staff_name,camera_entity_id,camera_name,observation_zone,observed_at,"
        "staff_match_confidence_pct,confidence_pct,review_status,review_notes,tag_label,vehicle_type,vehicle_color,vehicle_make,vehicle_model,"
        "movement_state,license_plate,subject_category,flagged,flag_reason,evidence_id "
        "FROM estate_vehicle_movements WHERE estate_id=%s AND observed_at BETWEEN %s AND %s "
        "AND review_status<>'rejected' AND staff_person_entity IS NOT NULL ORDER BY observed_at DESC LIMIT 250",
        (estate_id(), start, end),
    )
    sightings: list[dict[str, Any]] = []
    for row in people:
        observed = row.get("observed_at")
        if isinstance(observed, datetime):
            observed = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        sightings.append({
            "id": f"person:{row['id']}", "person_entity": row.get("person_entity"),
            "name": row.get("observed_label") or str(row.get("person_entity") or "").removeprefix("person.").replace("_", " ").title(),
            "camera_entity_id": row.get("camera_entity_id"), "camera_name": row.get("camera_name"),
            "observation_zone": row.get("observation_zone"), "observed_at": observed,
            "source_kind": row.get("source_kind"), "source_label": "Familiar-person detection",
            "confidence_pct": row.get("confidence_pct"), "review_status": row.get("review_status"),
        })
    for row in vehicles:
        observed = row.get("observed_at")
        if isinstance(observed, datetime):
            observed = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        vehicle = " ".join(str(row.get(key) or "").strip() for key in ("vehicle_color", "vehicle_make", "vehicle_model")).strip()
        sightings.append({
            "id": f"vehicle:{row['id']}", "person_entity": row.get("staff_person_entity"),
            "name": row.get("staff_name") or str(row.get("staff_person_entity") or "").removeprefix("person.").replace("_", " ").title(),
            "camera_entity_id": row.get("camera_entity_id"), "camera_name": row.get("camera_name"),
            "observation_zone": row.get("observation_zone"), "observed_at": observed,
            "source_kind": "recognized_vehicle", "source_label": f"Recognized vehicle{f' · {vehicle}' if vehicle else ''}",
            "confidence_pct": row.get("staff_match_confidence_pct") or row.get("confidence_pct"),
            "review_status": row.get("review_status"), "movement_id": row.get("id"),
            "movement": {
                key: row.get(key) for key in (
                    "id", "camera_entity_id", "camera_name", "observation_zone", "movement_state",
                    "vehicle_type", "vehicle_color", "vehicle_make", "vehicle_model", "license_plate",
                    "staff_person_entity", "staff_name", "subject_category", "tag_label", "flagged",
                    "flag_reason", "confidence_pct", "evidence_id", "review_status", "review_notes",
                )
            } | {"observed_at": observed},
        })
    return sorted(sightings, key=lambda row: row.get("observed_at") or datetime.min.replace(tzinfo=ROME), reverse=True)


@router.get("/dashboard", dependencies=[Depends(authorize_admin)])
def security_dashboard(response: Response, day: date | None = None) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
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
    cameras = security_camera_sources()
    camera_catalog = _camera_catalog()
    recognized_sightings = _recent_recognized_sightings(selected_day)
    selected_sightings = [
        row for row in recognized_sightings
        if isinstance(row.get("observed_at"), datetime) and row["observed_at"].date() == selected_day
    ]
    camera_event_count = int((fetch_one(
        "SELECT COUNT(*) total FROM camera_security_events WHERE estate_id=%s AND detected_at BETWEEN %s AND %s "
        "AND event_type IN ('vehicle','recognized person','person','motion','ringing')",
        (estate_id(), start, end),
    ) or {}).get("total") or 0)
    analysis_process = fetch_one(
        "SELECT status,error_message,occurred_at FROM integration_events WHERE estate_id=%s "
        "AND integration_name='camera-awareness' ORDER BY occurred_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    if isinstance(analysis_process.get("occurred_at"), datetime):
        analysis_process["occurred_at"] = analysis_process["occurred_at"].replace(tzinfo=timezone.utc).astimezone(ROME)
    recent_checks = fetch_all(
        "SELECT camera_entity_id,vehicle_visible,movement_count,source_kind,checked_at "
        "FROM estate_vehicle_frame_checks WHERE estate_id=%s ORDER BY checked_at DESC LIMIT 100",
        (estate_id(),),
    )
    latest_by_camera: dict[str, dict[str, Any]] = {}
    for check in recent_checks:
        camera_entity_id = str(check.get("camera_entity_id") or "")
        if camera_entity_id and camera_entity_id not in latest_by_camera:
            checked_at = check.get("checked_at")
            if isinstance(checked_at, datetime):
                check["checked_at"] = checked_at.replace(tzinfo=timezone.utc).astimezone(ROME)
            latest_by_camera[camera_entity_id] = check
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
            "recognized_people": len({row.get("person_entity") or row.get("name") for row in selected_sightings}),
            "recognized_sightings": len(selected_sightings),
            "recent_recognized_people": len({row.get("person_entity") or row.get("name") for row in recognized_sightings}),
            "recent_recognized_sightings": len(recognized_sightings),
            "camera_events": camera_event_count,
        },
        "movements": rows, "cameras": cameras, "camera_catalog": camera_catalog,
        "recent_recognized_sightings": recognized_sightings,
        "camera_audit": _camera_configuration_audit(cameras, camera_catalog),
        "camera_checks": list(latest_by_camera.values()),
        "analysis_process": analysis_process,
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
    result = refresh_estate_vehicle_security(force=True, all_recurring=True)
    result["plate_learning"] = _backfill_recent_plate_evidence()
    with transaction() as (_, cursor):
        audit(cursor, "run", "estate_vehicle_security", "manual", result, request_username(request))
    return result


@router.get("/movements/{movement_id}", dependencies=[Depends(authorize_admin)])
def get_vehicle_movement(movement_id: str) -> dict[str, Any]:
    """Load one complete movement so a seven-day sighting can always be reviewed."""
    row = fetch_one(
        "SELECT id,camera_entity_id,camera_name,observation_zone,observed_at,movement_state,front_direction,vehicle_type,vehicle_make,vehicle_model,"
        "vehicle_color,license_plate,plate_country,plate_confidence_pct,staff_person_entity,staff_name,staff_match_confidence_pct,subject_category,"
        "known_vehicle_id,tag_label,flagged,flag_reason,confidence_pct,evidence_id,review_status,reviewed_by,reviewed_at,review_notes,edge_event_types,"
        "(SELECT plate.plate_pattern FROM estate_vehicle_plate_reads plate WHERE plate.estate_id=movement.estate_id AND plate.source_key=movement.source_key "
        "ORDER BY plate.confidence_pct DESC,plate.observed_at DESC LIMIT 1) partial_plate_pattern,"
        "(SELECT plate.confidence_pct FROM estate_vehicle_plate_reads plate WHERE plate.estate_id=movement.estate_id AND plate.source_key=movement.source_key "
        "ORDER BY plate.confidence_pct DESC,plate.observed_at DESC LIMIT 1) partial_plate_confidence_pct,"
        "(SELECT plate.vehicle_identity_key FROM estate_vehicle_plate_reads plate WHERE plate.estate_id=movement.estate_id AND plate.source_key=movement.source_key "
        "ORDER BY plate.confidence_pct DESC,plate.observed_at DESC LIMIT 1) plate_identity_key "
        "FROM estate_vehicle_movements movement WHERE estate_id=%s AND id=%s",
        (estate_id(), movement_id),
    )
    if not row:
        raise HTTPException(404, "Vehicle observation not found")
    try:
        row["edge_event_types"] = json.loads(row.get("edge_event_types") or "[]")
    except (TypeError, ValueError):
        row["edge_event_types"] = []
    identity_key = str(row.pop("plate_identity_key", "") or "")
    if not identity_key and row.get("known_vehicle_id"):
        identity_key = f"known:{row['known_vehicle_id']}"
    if identity_key:
        pattern_rows = fetch_all(
            "SELECT plate_pattern,confidence_pct FROM estate_vehicle_plate_reads WHERE estate_id=%s AND vehicle_identity_key=%s "
            "AND plate_pattern IS NOT NULL AND observed_at>=DATE_SUB(UTC_TIMESTAMP(),INTERVAL 180 DAY) "
            "ORDER BY confidence_pct DESC,observed_at DESC LIMIT 24",
            (estate_id(), identity_key),
        )
        combined = _combine_plate_patterns([item.get("plate_pattern") for item in pattern_rows])
        if combined:
            row["partial_plate_pattern"] = combined
            row["partial_plate_confidence_pct"] = max(
                (float(item.get("confidence_pct") or 0) for item in pattern_rows), default=0,
            )
            row["plate_evidence_views"] = len(pattern_rows)
    row.setdefault("plate_evidence_views", 1 if row.get("partial_plate_pattern") else 0)
    observed = row.get("observed_at")
    if isinstance(observed, datetime):
        row["observed_at"] = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
    return row


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
            identity_basis = _known_vehicle_identity_basis(
                plate, person_entity, current.get("vehicle_color"), current.get("vehicle_make"),
                current.get("vehicle_model"), current.get("vehicle_type"),
            )
            display_name = tag_label or str((staff or {}).get("name") or "").strip() or " ".join(
                str(current.get(key) or "").strip() for key in ("vehicle_color", "vehicle_make", "vehicle_model")
            ).strip() or "Known vehicle"
            observation_increment = 0 if current.get("review_status") == "confirmed" else 1
            if known_vehicle_id:
                cursor.execute(
                    "UPDATE estate_known_vehicles SET display_name=%s,vehicle_type=COALESCE(%s,vehicle_type),"
                    "vehicle_make=COALESCE(%s,vehicle_make),vehicle_model=COALESCE(%s,vehicle_model),"
                    "vehicle_color=COALESCE(%s,vehicle_color),license_plate=COALESCE(%s,license_plate),"
                    "plate_country=COALESCE(%s,plate_country),person_entity=COALESCE(%s,person_entity),"
                    "person_name=COALESCE(%s,person_name),subject_category=%s,flagged=%s,flag_reason=%s,"
                    "notes=COALESCE(%s,notes),confirmed_observations=confirmed_observations+%s,"
                    "first_seen_at=LEAST(COALESCE(first_seen_at,%s),%s),last_seen_at=GREATEST(COALESCE(last_seen_at,%s),%s) "
                    "WHERE estate_id=%s AND id=%s",
                    (display_name[:180], current.get("vehicle_type"), current.get("vehicle_make"), current.get("vehicle_model"),
                     current.get("vehicle_color"), plate, current.get("plate_country"), person_entity,
                     str((staff or {}).get("name") or "")[:180] or None, category, bool(payload.get("flagged")),
                     str(payload.get("flag_reason") or "")[:500] or None, str(payload.get("review_notes") or "")[:1000] or None,
                     observation_increment, current.get("observed_at"), current.get("observed_at"),
                     current.get("observed_at"), current.get("observed_at"), estate_id(), known_vehicle_id),
                )
            elif identity_basis:
                identity_key = hashlib.sha256(identity_basis.encode()).hexdigest()
                known_vehicle_id = str(uuid4())
                cursor.execute(
                    "INSERT INTO estate_known_vehicles (id,estate_id,identity_key,display_name,vehicle_type,vehicle_make,vehicle_model,vehicle_color,"
                    "license_plate,plate_country,person_entity,person_name,subject_category,flagged,flag_reason,notes,first_seen_at,last_seen_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),vehicle_type=COALESCE(VALUES(vehicle_type),vehicle_type),"
                    "vehicle_make=COALESCE(VALUES(vehicle_make),vehicle_make),vehicle_model=COALESCE(VALUES(vehicle_model),vehicle_model),"
                    "vehicle_color=COALESCE(VALUES(vehicle_color),vehicle_color),license_plate=COALESCE(VALUES(license_plate),license_plate),"
                    "plate_country=COALESCE(VALUES(plate_country),plate_country),person_entity=COALESCE(VALUES(person_entity),person_entity),"
                    "person_name=COALESCE(VALUES(person_name),person_name),subject_category=VALUES(subject_category),flagged=VALUES(flagged),"
                    "flag_reason=VALUES(flag_reason),notes=COALESCE(VALUES(notes),notes),confirmed_observations=confirmed_observations+%s,"
                    "first_seen_at=LEAST(COALESCE(first_seen_at,VALUES(first_seen_at)),VALUES(first_seen_at)),last_seen_at=GREATEST(COALESCE(last_seen_at,VALUES(last_seen_at)),VALUES(last_seen_at)),active=1",
                    (known_vehicle_id, estate_id(), identity_key, display_name[:180], current.get("vehicle_type"), current.get("vehicle_make"),
                     current.get("vehicle_model"), current.get("vehicle_color"), plate, current.get("plate_country"), person_entity,
                     str((staff or {}).get("name") or "")[:180] or None, category, bool(payload.get("flagged")),
                     str(payload.get("flag_reason") or "")[:500] or None, str(payload.get("review_notes") or "")[:1000] or None,
                     current.get("observed_at"), current.get("observed_at"), observation_increment),
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
