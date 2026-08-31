"""Camera-route and cistern-rise evidence for estate water deliveries."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from ..access import people_profiles
from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import estate_id, new_id
from .worker_evidence_archive import archive_camera_frame, purge_expired_evidence
from .worker_vehicle_presence import _camera_zone


DEFAULT_WATER_DELIVERY_CAMERAS = [
    "camera.rear_gate", "camera.t8171t1025291b5f", "camera.top_vineyard_360", "camera.cistern_360",
]
DEFAULT_WATER_DELIVERY_PROFILE = {
    "person_entity": "person.nunzio_testa",
    "name": "Nunzio Testa",
    "water_delivery_tracking_enabled": True,
    "water_delivery_camera_entities": DEFAULT_WATER_DELIVERY_CAMERAS,
}
WATER_SCAN_INTERVAL_MINUTES = 20
MIN_CONFIDENCE = 0.62
MIN_LEVEL_RISE_POINTS = 3.0


def _delivery_profiles() -> list[dict[str, Any]]:
    saved = people_profiles()
    entity = DEFAULT_WATER_DELIVERY_PROFILE["person_entity"]
    configured = [
        {"person_entity": person_entity, **profile}
        for person_entity, profile in saved.items()
        if isinstance(profile, dict) and profile.get("water_delivery_tracking_enabled")
    ]
    default_saved = saved.get(entity) or {}
    if not configured and default_saved.get("water_delivery_tracking_enabled", True):
        configured = [{**DEFAULT_WATER_DELIVERY_PROFILE, **default_saved, "person_entity": entity}]
    # Preserve the default after a Home Assistant rename by recognizing the
    # supplier's saved display name, but allow an explicit off switch.
    result = []
    for profile in configured:
        cameras = []
        for value in profile.get("water_delivery_camera_entities") or DEFAULT_WATER_DELIVERY_CAMERAS:
            camera = str(value or "").strip()
            if camera.startswith("camera.") and camera not in cameras:
                cameras.append(camera)
        result.append({**profile, "water_delivery_camera_entities": cameras or list(DEFAULT_WATER_DELIVERY_CAMERAS)})
    return result


def configured_water_delivery_cameras() -> set[str]:
    return {camera for profile in _delivery_profiles() for camera in profile["water_delivery_camera_entities"]}


def _latest_level(before: datetime | None = None) -> dict[str, Any] | None:
    clause = " AND observed_at<=%s" if before else ""
    params: tuple[Any, ...] = (estate_id(), before) if before else (estate_id(),)
    return fetch_one(
        "SELECT id,observed_at,level_percent,confidence FROM cistern_level_estimates "
        f"WHERE estate_id=%s{clause} ORDER BY observed_at DESC,id DESC LIMIT 1",
        params,
    )


def _reconcile_delivery(provider: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = fetch_all(
        "SELECT * FROM water_delivery_observations WHERE estate_id=%s AND provider_person_entity=%s "
        "AND delivery_id IS NULL AND review_status<>'rejected' AND observed_at>=%s ORDER BY observed_at",
        (estate_id(), provider, now - timedelta(hours=12)),
    )
    likely = [row for row in rows if row.get("likely_water_delivery") and float(row.get("confidence_pct") or 0) >= 62]
    if not likely:
        return {"status": "no_candidate"}
    started = likely[0]["observed_at"]
    latest = _latest_level()
    before = _latest_level(started - timedelta(minutes=1))
    before_level = float(before["level_percent"]) if before and before.get("level_percent") is not None else None
    after_level = float(latest["level_percent"]) if latest and latest.get("level_percent") is not None else None
    rise = round(after_level - before_level, 2) if before_level is not None and after_level is not None else None
    cameras = sorted({str(row.get("camera_entity_id") or "") for row in likely})
    has_cistern = any(camera == "camera.cistern_360" or row.get("delivery_stage") == "filling" for row in likely for camera in [str(row.get("camera_entity_id") or "")])
    confirmed = len(cameras) >= 2 and has_cistern and rise is not None and rise >= MIN_LEVEL_RISE_POINTS
    if not confirmed:
        return {
            "status": "candidate", "observations": len(likely), "cameras": cameras,
            "level_before_pct": before_level, "level_after_pct": after_level, "level_increase_pct": rise,
            "needs": "two route cameras, a cistern-side/filling view, and a 3-point water-level increase",
        }
    delivery_id = new_id()
    confidence = round(min(100.0, sum(float(row.get("confidence_pct") or 0) for row in likely) / len(likely) + min(12, rise)), 2)
    evidence = {
        "route_cameras": cameras, "visual_observation_ids": [row["id"] for row in likely],
        "level_before_estimate_id": before.get("id") if before else None,
        "level_after_estimate_id": latest.get("id") if latest else None,
        "confirmation_rule": "multi-camera route plus cistern rise",
        "provider_is_expected_not_visually_identified": True,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO water_deliveries (id,estate_id,provider_person_entity,arrived_at,completed_at,"
            "level_before_pct,level_after_pct,level_increase_pct,camera_count,observation_count,confidence_pct,status,evidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s)",
            (delivery_id, estate_id(), provider, started, now, before_level, after_level, rise,
             len(cameras), len(likely), confidence, json.dumps(evidence)),
        )
        cursor.execute(
            "UPDATE water_delivery_observations SET delivery_id=%s,review_status='confirmed' "
            "WHERE estate_id=%s AND id IN (" + ",".join(["%s"] * len(likely)) + ")",
            (delivery_id, estate_id(), *(row["id"] for row in likely)),
        )
    return {"status": "confirmed", "delivery_id": delivery_id, "level_increase_pct": rise, "confidence_pct": confidence}


def refresh_water_delivery_tracking(force: bool = False, event_triggers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    profiles = _delivery_profiles()
    if not profiles:
        return {"configured": False, "updated": False}
    profile = profiles[0]
    cameras = profile["water_delivery_camera_entities"]
    relevant = [row for row in (event_triggers or []) if str(row.get("camera_entity_id") or "") in cameras]
    trigger = sorted(relevant, key=lambda row: str(row.get("detected_at") or ""), reverse=True)[0] if relevant else None
    if trigger:
        camera = str(trigger.get("camera_entity_id"))
    else:
        activity = {str(row.get("camera_entity_id") or ""): row.get("observed_at") for row in fetch_all(
            "SELECT camera_entity_id,MAX(observed_at) observed_at FROM water_delivery_observations "
            "WHERE estate_id=%s GROUP BY camera_entity_id", (estate_id(),),
        )}
        camera = min(cameras, key=lambda value: activity.get(value) or datetime.min)
        observed = activity.get(camera)
        if not force and isinstance(observed, datetime) and datetime.now(timezone.utc).replace(tzinfo=None) - observed < timedelta(minutes=WATER_SCAN_INTERVAL_MINUTES):
            return {"configured": True, "updated": False, "deferred": True, "camera": camera}
    settings = get_settings()
    if not settings.openai_api_key:
        return {"configured": True, "updated": False, "reason": "Visual delivery analysis is not configured"}
    from ..intelligence import (
        _home_assistant_image, _openai_json_request, _openai_response_body, _response_text,
        home_assistant_camera_snapshot, record_ai_usage,
    )
    try:
        if trigger:
            token = home_assistant_token()
            if not token:
                raise RuntimeError("Home Assistant image access is unavailable")
            image, content_type = _home_assistant_image(token, str(trigger["event_image_entity_id"]), image_entity=True)
            snapshot = {"data": image, "content_type": content_type, "fresh": True}
        else:
            snapshot = home_assistant_camera_snapshot(camera)
            image = bytes(snapshot["data"])
            if not snapshot.get("fresh"):
                raise RuntimeError("Fresh camera frame unavailable")
    except Exception as error:
        return {"configured": True, "updated": False, "camera": camera, "reason": f"Delivery camera unavailable: {type(error).__name__}"}
    digest = hashlib.sha256(image).hexdigest()
    if fetch_one("SELECT id FROM water_delivery_observations WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s", (estate_id(), camera, digest)):
        return {"configured": True, "updated": False, "deferred": True, "camera": camera, "reason": "Frame already analyzed"}
    camera_name = str((trigger or {}).get("camera_name") or camera)
    zone = "cistern" if camera == "camera.cistern_360" else _camera_zone(camera, camera_name)
    spatial = (
        "On Main Parking, a visible vehicle whose front points right supports ARRIVAL; front pointing left supports DEPARTURE. "
        "On Cistern 360, the cistern access/entry path is on the RIGHT side of the image; activity there supports approach or filling. "
        "Rear Gate then Rear Gate 360 then Rear Entrance Path 360 then Cistern 360 is the expected inbound route; "
        "Rear Entrance Path 360 is the final approach view immediately before Cistern 360."
    )
    prompt = (
        "Inspect one estate camera frame for a possible bulk water delivery truck and delivery activity. "
        "Do not identify people, faces, license plates, ownership, or intent. The configured supplier is expected context only. "
        + spatial + " Return JSON only: {truck_visible:boolean,likely_water_delivery:boolean,"
        "delivery_stage:'arrival'|'transit'|'filling'|'departure'|'none'|'uncertain',"
        "path_direction:'left'|'right'|'stationary'|'unknown',confidence:0..1,reason:string}. "
        "Only call it likely water delivery when the vehicle/body or hose/filling activity supports that conclusion; ordinary cars are not deliveries. "
        f"Camera: {camera_name} ({camera}), operational zone: {zone}."
    )
    encoded = base64.b64encode(image).decode()
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{snapshot['content_type']};base64,{encoded}", "detail": "high"},
        ]}], "text": {"format": {"type": "json_object"}},
    })
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        result = _openai_json_request(request, 60, "water_delivery_tracking")
        record_ai_usage("water_delivery_tracking", result, digest[:24])
        parsed = json.loads(_response_text(result) or "{}")
    except Exception as error:
        return {"configured": True, "updated": False, "camera": camera, "reason": f"Delivery analysis unavailable: {type(error).__name__}"}
    stage = str(parsed.get("delivery_stage") or "uncertain")
    if stage not in {"arrival", "transit", "filling", "departure", "none", "uncertain"}:
        stage = "uncertain"
    direction = str(parsed.get("path_direction") or "unknown")
    if direction not in {"left", "right", "stationary", "unknown"}:
        direction = "unknown"
    try:
        confidence = round(max(0, min(100, float(parsed.get("confidence") or 0) * 100)), 2)
    except (TypeError, ValueError):
        confidence = 0
    likely = bool(parsed.get("likely_water_delivery")) and confidence >= MIN_CONFIDENCE * 100
    # A likely filling frame should produce a contemporaneous level reading,
    # rather than waiting for the normal low-frequency cistern schedule.
    if likely and stage == "filling":
        try:
            from ..intelligence import refresh_cistern_level
            refresh_cistern_level()
        except Exception:
            pass
    level = _latest_level()
    try:
        evidence_id = archive_camera_frame(
            image, content_type=str(snapshot.get("content_type") or "image/jpeg"), camera_entity_id=camera,
            observation_zone=zone,
            captured_at=datetime.fromisoformat(str(trigger.get("detected_at")).replace("Z", "+00:00")) if trigger and trigger.get("detected_at") else None,
            source_kind="water_delivery_event" if trigger else "water_delivery_cadence",
        )
        purge_expired_evidence()
    except Exception:
        evidence_id = None
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT IGNORE INTO water_delivery_observations (estate_id,provider_person_entity,camera_entity_id,observation_zone,"
            "observed_at,truck_visible,likely_water_delivery,delivery_stage,path_direction,confidence_pct,cistern_level_pct,"
            "frame_sha256,evidence_id,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (estate_id(), profile["person_entity"], camera, zone, datetime.now(timezone.utc).replace(tzinfo=None),
             bool(parsed.get("truck_visible")), likely, stage, direction, confidence,
             level.get("level_percent") if level else None, digest, evidence_id,
             json.dumps({"reason": str(parsed.get("reason") or "")[:400], "event_trigger": bool(trigger),
                         "expected_provider": profile.get("name"), "provider_identity_not_visually_proven": True,
                         "spatial_rule_applied": True})),
        )
        saved = int(cursor.rowcount > 0)
    reconciliation = _reconcile_delivery(profile["person_entity"])
    return {"configured": True, "updated": bool(saved), "camera": camera, "likely_delivery": likely, "stage": stage, "reconciliation": reconciliation}


def water_delivery_summary(person_entity: str, days: int = 90) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, min(days, 365)))
    try:
        deliveries = fetch_all(
            "SELECT id,arrived_at,completed_at,level_before_pct,level_after_pct,level_increase_pct,camera_count,"
            "observation_count,confidence_pct,status FROM water_deliveries WHERE estate_id=%s AND provider_person_entity=%s "
            "AND completed_at>=%s ORDER BY completed_at DESC LIMIT 60", (estate_id(), person_entity, cutoff),
        )
        observations = fetch_all(
            "SELECT id,camera_entity_id,observation_zone,observed_at,truck_visible,likely_water_delivery,delivery_stage,"
            "path_direction,confidence_pct,cistern_level_pct,evidence_id,review_status FROM water_delivery_observations "
            "WHERE estate_id=%s AND provider_person_entity=%s AND observed_at>=%s ORDER BY observed_at DESC LIMIT 60",
            (estate_id(), person_entity, cutoff),
        )
    except Exception:
        deliveries, observations = [], []
    return {
        "available": bool(deliveries or observations), "confirmed_deliveries": len(deliveries),
        "latest_delivery": deliveries[0] if deliveries else None, "deliveries": deliveries,
        "recent_observations": observations,
        "policy": "A delivery is confirmed only when the multi-camera route agrees with a cistern-level rise. Nunzio is the expected supplier, not a visual identity claim.",
    }
