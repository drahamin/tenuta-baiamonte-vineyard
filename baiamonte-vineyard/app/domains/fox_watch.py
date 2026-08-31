"""Review-gated fox awareness for the fixed West Etna vineyard view."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..service import estate_id
from .camera_naming import canonical_camera_name
from .worker_evidence_archive import archive_camera_frame, purge_expired_evidence, read_camera_evidence
from .whatsapp_people import person_ivr


ROME = ZoneInfo("Europe/Rome")
FOX_CAMERA_ENTITY = "camera.west_etna_view"
FOX_CAMERA_NAME = "West Etna View"
WENDY_PERSON_ENTITY = "person.wendy_creque"
MIN_FOX_CONFIDENCE = 75.0
NOTIFICATION_COOLDOWN_HOURS = 6
SCHEDULED_SCAN_MINUTES = 30


def _observed_at(value: Any = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _night(observed: datetime) -> bool:
    local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
    return local.hour >= 18 or local.hour < 7


def _conversation_window_open(number: str) -> bool:
    recent = fetch_one(
        "SELECT received_at FROM intake_items WHERE estate_id=%s AND source='whatsapp' "
        "AND REPLACE(REPLACE(REPLACE(sender_address,'+',''),' ',''),'-','')=%s "
        "ORDER BY received_at DESC LIMIT 1",
        (estate_id(), number),
    ) or {}
    received = recent.get("received_at")
    return bool(isinstance(received, datetime) and datetime.now() - received <= timedelta(hours=24))


def _friendly_caption(row: dict[str, Any]) -> str:
    observed = row.get("observed_at")
    if isinstance(observed, datetime):
        local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        when = local.strftime("%A at %-I:%M %p")
    else:
        when = "recently"
    action = str(row.get("activity") or "visiting").replace("_", " ")
    risk = str(row.get("grape_risk") or "unknown")
    risk_note = " I’ll keep an extra eye on the grapes." if risk in {"moderate", "high"} else " No grape-feeding was clear in this view."
    return f"🦊 Wendy, our little four-legged visitor was spotted at Baiamonte {when}, {action} near the West Etna view.{risk_note}"


def _notify_wendy(row: dict[str, Any], image: bytes, content_type: str) -> str:
    recent = fetch_one(
        "SELECT notified_at FROM wildlife_observations WHERE estate_id=%s AND fox_visible=1 "
        "AND notified_at>=NOW()-INTERVAL 6 HOUR ORDER BY notified_at DESC LIMIT 1",
        (estate_id(),),
    )
    if recent:
        return "cooldown"
    ivr = person_ivr(WENDY_PERSON_ENTITY, "Wendy Creque")
    number = str(ivr.get("number") or "")
    if not ivr.get("linked") or not number:
        return "wendy_not_linked"
    if not _conversation_window_open(number):
        return "queued_window_closed"
    try:
        from ..intelligence import send_whatsapp_media
        send_whatsapp_media(number, image, "baiamonte-fox.jpg", content_type, _friendly_caption(row))
        return "sent"
    except Exception as error:
        return f"failed:{type(error).__name__}"


def _latest_capture_allowed(force: bool) -> bool:
    if force:
        return True
    latest = fetch_one(
        "SELECT observed_at FROM wildlife_observations WHERE estate_id=%s AND camera_entity_id=%s "
        "ORDER BY observed_at DESC LIMIT 1",
        (estate_id(), FOX_CAMERA_ENTITY),
    ) or {}
    observed = latest.get("observed_at")
    return not isinstance(observed, datetime) or datetime.now(timezone.utc).replace(tzinfo=None) - observed >= timedelta(minutes=SCHEDULED_SCAN_MINUTES)


def refresh_fox_watch(event_triggers: list[dict[str, Any]] | None = None, force: bool = False) -> dict[str, Any]:
    """Analyze a new West Etna event image, or one bounded nighttime still."""
    settings = get_settings()
    triggers = [
        row for row in (event_triggers or [])
        if str(row.get("camera_entity_id") or "") == FOX_CAMERA_ENTITY and row.get("event_image_entity_id")
    ]
    trigger = max(triggers, key=lambda row: str(row.get("detected_at") or ""), default=None)
    observed = _observed_at((trigger or {}).get("detected_at"))
    if not trigger and (not _night(observed) or not _latest_capture_allowed(force)):
        return {"configured": True, "updated": False, "deferred": True, "reason": "Fox watch scans the fixed view at night or on a new animal event"}
    if not settings.openai_api_key:
        return {"configured": False, "updated": False, "reason": "Visual fox analysis is not configured"}

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
        else:
            snapshot = home_assistant_camera_snapshot(FOX_CAMERA_ENTITY)
            if not snapshot.get("fresh"):
                return {"configured": True, "updated": False, "reason": "A fresh West Etna frame is unavailable"}
            image = bytes(snapshot["data"])
            content_type = str(snapshot.get("content_type") or "image/jpeg")
    except Exception as error:
        return {"configured": True, "updated": False, "reason": f"Fox-watch image unavailable: {type(error).__name__}"}

    digest = hashlib.sha256(image).hexdigest()
    duplicate = fetch_one(
        "SELECT id FROM wildlife_observations WHERE estate_id=%s AND camera_entity_id=%s AND frame_sha256=%s",
        (estate_id(), FOX_CAMERA_ENTITY, digest),
    )
    if duplicate:
        return {"configured": True, "updated": False, "deferred": True, "reason": "Frame already checked"}
    try:
        evidence_id = archive_camera_frame(
            image, content_type=content_type, camera_entity_id=FOX_CAMERA_ENTITY,
            observation_zone="west_etna_vineyard", captured_at=observed,
            source_kind="fox_eufy_event" if trigger else "fox_night_watch",
        )
        purge_expired_evidence()
    except Exception:
        evidence_id = None

    prompt = (
        "Inspect this fixed nighttime vineyard camera image for a fox. Return JSON only: "
        "{fox_visible:boolean,species:'fox'|'likely_fox'|'dog'|'cat'|'other'|'uncertain',confidence:0..1,"
        "activity:'walking'|'feeding'|'sniffing'|'running'|'standing'|'lying'|'unknown',"
        "grape_risk:'none'|'low'|'moderate'|'high'|'unknown',reason:string}. "
        "Confirmed Baiamonte reference sightings in this same infrared view show a small slender canid with pointed ears and muzzle, "
        "a long bushy tail, and low walking or sniffing posture. These are guidance, not proof. Do not overcall dogs, cats, glare, plants, or shadows. "
        "Use likely_fox or uncertain when the tail, muzzle, body proportions, or legs are not sufficiently visible. "
        "Feeding or sustained attention beside vines can raise grape risk; merely crossing the view does not."
    )
    body = _openai_response_body({
        "model": settings.openai_model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{content_type};base64,{base64.b64encode(image).decode()}", "detail": "high"},
        ]}],
        "text": {"format": {"type": "json_object"}},
    })
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses", data=body,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
    )
    try:
        result = _openai_json_request(request, 60, "fox_watch")
        record_ai_usage("fox_watch", result, digest[:24])
        parsed = json.loads(_response_text(result) or "{}")
    except Exception as error:
        return {"configured": True, "updated": False, "reason": f"Fox analysis unavailable: {type(error).__name__}"}

    species = str(parsed.get("species") or "uncertain")
    if species not in {"fox", "likely_fox", "dog", "cat", "other", "uncertain"}:
        species = "uncertain"
    try:
        confidence = round(max(0, min(100, float(parsed.get("confidence") or 0) * 100)), 2)
    except (TypeError, ValueError):
        confidence = 0
    fox_visible = bool(parsed.get("fox_visible")) and species in {"fox", "likely_fox"}
    activity = str(parsed.get("activity") or "unknown")
    if activity not in {"walking", "feeding", "sniffing", "running", "standing", "lying", "unknown"}:
        activity = "unknown"
    risk = str(parsed.get("grape_risk") or "unknown")
    if risk not in {"none", "low", "moderate", "high", "unknown"}:
        risk = "unknown"
    evidence = {
        "reason": str(parsed.get("reason") or "")[:600], "event_types": list((trigger or {}).get("event_types") or []),
        "source_kind": "eufy_event" if trigger else "bounded_night_scan", "reference_clips": 3,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO wildlife_observations (estate_id,camera_entity_id,camera_name,observed_at,species,fox_visible,"
            "confidence_pct,activity,grape_risk,night_observation,frame_sha256,evidence_id,model_version,evidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (estate_id(), FOX_CAMERA_ENTITY, canonical_camera_name(FOX_CAMERA_ENTITY, FOX_CAMERA_NAME), observed,
             species, fox_visible, confidence, activity, risk, _night(observed), digest, evidence_id,
             settings.openai_model, json.dumps(evidence)),
        )
        observation_id = int(cursor.lastrowid)
    notification = "not_requested"
    credible = fox_visible and confidence >= MIN_FOX_CONFIDENCE
    if credible:
        row = {"id": observation_id, "observed_at": observed, "activity": activity, "grape_risk": risk}
        notification = _notify_wendy(row, image, content_type)
        with transaction() as (_, cursor):
            cursor.execute(
                "UPDATE wildlife_observations SET notification_status=%s,notified_at=IF(%s='sent',NOW(),NULL) "
                "WHERE estate_id=%s AND id=%s",
                (notification[:80], notification, estate_id(), observation_id),
            )
        try:
            from ..intelligence import create_alert_once
            create_alert_once(
                "fox", "warning", "Fox spotted near the West Etna vines 🦊",
                f"A {species.replace('_', ' ')} was seen {activity} with {confidence:.0f}% visual confidence. Grape risk: {risk}.",
                f"fox:{digest[:24]}", {"wildlife_observation_id": observation_id, "evidence_id": evidence_id, "wendy_notification": notification},
            )
        except Exception:
            pass
    return {"configured": True, "updated": True, "observation_id": observation_id, "fox_visible": fox_visible,
            "credible_fox": credible, "confidence_pct": confidence, "species": species, "notification": notification}


def fox_watch_summary(limit: int = 12) -> dict[str, Any]:
    summary = fetch_one(
        "SELECT COUNT(*) observations,SUM(fox_visible=1 AND confidence_pct>=%s) credible_sightings,"
        "SUM(fox_visible=1 AND confidence_pct>=%s AND YEAR(observed_at)=YEAR(NOW()) AND MONTH(observed_at)=MONTH(NOW())) month_sightings,"
        "SUM(grape_risk IN ('moderate','high')) risk_sightings,MAX(observed_at) latest FROM wildlife_observations WHERE estate_id=%s",
        (MIN_FOX_CONFIDENCE, MIN_FOX_CONFIDENCE, estate_id()),
    ) or {}
    recent = fetch_all(
        "SELECT id,camera_name,observed_at,species,fox_visible,confidence_pct,activity,grape_risk,night_observation,"
        "evidence_id,review_status,notification_status FROM wildlife_observations WHERE estate_id=%s "
        "AND fox_visible=1 AND confidence_pct>=%s ORDER BY observed_at DESC LIMIT %s",
        (estate_id(), MIN_FOX_CONFIDENCE, max(1, min(limit, 50))),
    )
    latest = recent[0] if recent else None
    return {
        "camera_entity_id": FOX_CAMERA_ENTITY, "camera_name": FOX_CAMERA_NAME,
        "observations": int(summary.get("observations") or 0),
        "credible_sightings": int(summary.get("credible_sightings") or 0),
        "month_sightings": int(summary.get("month_sightings") or 0),
        "risk_sightings": int(summary.get("risk_sightings") or 0),
        "latest": latest, "recent": recent,
        "latest_image_url": "api/v1/cameras/fox-watch/latest" if latest and latest.get("evidence_id") else None,
        "policy": "Animal events and bounded nighttime stills only; uncertain dogs, cats and shadows do not alert Wendy.",
    }


def monthly_fox_update(italian: bool = False) -> str:
    status = fox_watch_summary(1)
    count = status["month_sightings"]
    latest = status.get("latest") or {}
    if not count:
        return "🦊 Questo mese la piccola pattuglia delle volpi non si è ancora fatta vedere. Continuiamo a sorvegliare con gentilezza l'uva e gli amici a quattro zampe." if italian else "🦊 No fox visits have been confirmed this month yet. We’re still keeping a kind eye on both the grapes and our four-legged friends."
    observed = latest.get("observed_at")
    if isinstance(observed, datetime):
        local = observed.replace(tzinfo=timezone.utc).astimezone(ROME)
        when = local.strftime("%d/%m alle %H:%M") if italian else local.strftime("%B %-d at %-I:%M %p")
    else:
        when = "recentemente" if italian else "recently"
    activity = str(latest.get("activity") or "visiting").replace("_", " ")
    risk = str(latest.get("grape_risk") or "unknown")
    if italian:
        return f"🦊 Aggiornamento volpi: {count} avvistament{'o' if count == 1 else 'i'} confermato questo mese. L'ultimo è stato {when}, attività: {activity}. Rischio per l'uva: {risk}. Una piccola visita simpatica, ma teniamo d'occhio i grappoli."
    return f"🦊 Fox update: {count} confirmed sighting{'s' if count != 1 else ''} this month. The latest was {when}, {activity}. Grape risk was {risk}. A charming little visitor—but we’re watching the bunches."


def latest_fox_media() -> tuple[dict[str, Any], bytes] | None:
    row = fetch_one(
        "SELECT * FROM wildlife_observations WHERE estate_id=%s AND fox_visible=1 AND confidence_pct>=%s "
        "AND evidence_id IS NOT NULL ORDER BY observed_at DESC LIMIT 1",
        (estate_id(), MIN_FOX_CONFIDENCE),
    )
    if not row:
        return None
    evidence = read_camera_evidence(str(row.get("evidence_id") or ""))
    if not evidence:
        return None
    metadata, content = evidence
    return {**row, "content_type": metadata.get("content_type") or "image/jpeg"}, content
