from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..access import authorize, authorize_admin, authorize_write, request_username
from ..db import fetch_all, transaction
from ..ha_auth import home_assistant_token
from ..intelligence import _ha_get, _ha_post
from ..service import estate_id


router = APIRouter(prefix="/api/v1/cameras", tags=["cameras"])

DETECTION_SUFFIXES = {
    "motion": "motion_detected",
    "person": "person_detected",
    "vehicle": "vehicle_detected",
    "pet": "pet_detected",
    "ringing": "ringing",
}
CONTROL_SUFFIXES = {
    "camera_enabled": "camera_enabled",
    "light": "light",
    "motion_detection": "motion_detection",
    "motion_tracking": "motion_tracking",
    "auto_nightvision": "auto_nightvision",
    "audio_recording": "audio_recording",
}
SENSOR_SUFFIXES = {
    "battery": "battery",
    "charging": "charging_status",
    "wifi": "wifi_rssi",
    "stream": "stream_status",
    "person_name": "person_name",
}
PTZ_DIRECTIONS = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT", "rotate360": "ROTATE360"}
_image_cache: dict[str, tuple[float, bytes, str]] = {}


def _event_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return datetime.utcnow()


def _event_source_key(camera: dict[str, Any], event_type: str, detected_at: datetime) -> str:
    raw = f"{camera['entity_id']}|{event_type}|{detected_at.isoformat(timespec='seconds')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state_on(row: dict[str, Any] | None) -> bool:
    return str((row or {}).get("state") or "").casefold() in {"on", "true", "detected", "ringing"}


def _entity(index: dict[str, dict[str, Any]], domain: str, base: str, suffix: str) -> dict[str, Any] | None:
    return index.get(f"{domain}.{base}_{suffix}")


def _related_entity(
    index: dict[str, dict[str, Any]],
    domain: str,
    base: str,
    suffix: str,
    device_key: str | None,
) -> dict[str, Any] | None:
    """Resolve a related entity by stable device key, with legacy ID fallback."""
    if device_key:
        candidates = [
            row for entity_id, row in index.items()
            if entity_id.startswith(f"{domain}.")
            and str((row.get("attributes") or {}).get("baiamonte_device_key") or "") == device_key
        ]
        exact_property = next(
            (
                row for row in candidates
                if str((row.get("attributes") or {}).get("baiamonte_property") or "").casefold()
                == suffix.casefold()
            ),
            None,
        )
        if exact_property:
            return exact_property
        suffix_match = next(
            (row for row in candidates if str(row.get("entity_id") or "").endswith(f"_{suffix}")),
            None,
        )
        if suffix_match:
            return suffix_match
    return _entity(index, domain, base, suffix)


def _area(name: str) -> str:
    value = name.casefold()
    if any(word in value for word in ("gate", "entrance", "driveway", "parking", "road")):
        return "access"
    if any(word in value for word in ("vineyard", "etna", "fox", "giangreco")):
        return "vineyard"
    if any(word in value for word in ("cistern", "solar", "generator", "kitchen", "palmento", "bbq")):
        return "buildings"
    return "estate"


def _capabilities(camera: dict[str, Any]) -> dict[str, bool]:
    attrs = camera.get("attributes") or {}
    raw = attrs.get("capabilities") if isinstance(attrs.get("capabilities"), dict) else {}
    return {
        "streaming": bool(raw.get("streaming")),
        "rtsp": bool(raw.get("rtsp")),
        "ptz": bool(raw.get("ptz")),
        "rotate_360": bool(raw.get("rotate_360")),
        "presets": bool(raw.get("presets")),
        "save_presets": bool(raw.get("save_presets")),
        "delete_presets": bool(raw.get("delete_presets")),
        "calibrate": bool(raw.get("calibrate")),
        "quick_response": bool(raw.get("quick_response")),
    }


def _camera_row(camera: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entity_id = str(camera.get("entity_id") or "")
    base = entity_id.partition(".")[2]
    attrs = camera.get("attributes") or {}
    device_key = str(attrs.get("baiamonte_device_key") or "") or None
    detections: dict[str, dict[str, Any]] = {}
    for key, suffix in DETECTION_SUFFIXES.items():
        related = _related_entity(index, "binary_sensor", base, suffix, device_key)
        detections[key] = {
            "active": _state_on(related),
            "last_changed": (related or {}).get("last_changed"),
        }
    battery_low = _related_entity(index, "binary_sensor", base, "battery_low", device_key)
    connected = _related_entity(index, "binary_sensor", base, "connected", device_key)
    sensors = {
        key: (_related_entity(index, "sensor", base, suffix, device_key) or {}).get("state")
        for key, suffix in SENSOR_SUFFIXES.items()
    }
    controls: dict[str, dict[str, Any]] = {}
    for key, suffix in CONTROL_SUFFIXES.items():
        related = _related_entity(index, "switch", base, suffix, device_key)
        controls[key] = {
            "available": bool(related and related.get("state") not in {"unavailable", "unknown"}),
            "on": _state_on(related),
            "entity_id": (related or {}).get("entity_id"),
        }
    event_image = _related_entity(index, "image", base, "camera", device_key) or index.get(f"image.{base}_event_image")
    camera_available = camera.get("state") not in {"unavailable", "unknown"}
    connected_state = str((connected or {}).get("state") or "").casefold()
    # Battery Eufy cameras intentionally sleep between events.  A sleeping
    # device remains healthy and must not be presented as an outage.
    sleeping = camera_available and connected is not None and connected_state in {"off", "false"}
    availability = "unavailable" if not camera_available else "sleeping" if sleeping else "online"
    event_attrs = (event_image or {}).get("attributes") or {}
    event_image_available = bool(
        event_image
        and (
            event_attrs.get("event_image_available") is True
            or event_image.get("state") not in {"unavailable", "unknown", None, ""}
        )
    )
    return {
        "entity_id": entity_id,
        "name": attrs.get("friendly_name") or base.replace("_", " ").title(),
        "model": attrs.get("model"),
        "area": _area(str(attrs.get("friendly_name") or base)),
        "online": camera_available,
        "availability": availability,
        "sleeping": sleeping,
        "last_updated": camera.get("last_updated"),
        "capabilities": _capabilities(camera),
        "detections": detections,
        "battery": sensors["battery"],
        "battery_low": _state_on(battery_low),
        "battery_low_changed_at": (battery_low or {}).get("last_changed"),
        "charging": sensors["charging"],
        "wifi": sensors["wifi"],
        "stream_status": sensors["stream"],
        "person_name": sensors["person_name"] if sensors["person_name"] not in {None, "unknown", "unavailable"} else None,
        "controls": controls,
        "event_image_available": event_image_available,
        "event_image_entity_id": (event_image or {}).get("entity_id"),
        "event_image_url": f"api/v1/cameras/{urllib.parse.quote(entity_id, safe='')}/event-image",
        "snapshot_url": f"api/v1/cameras/{urllib.parse.quote(entity_id, safe='')}/snapshot",
    }


def camera_dashboard() -> dict[str, Any]:
    try:
        states = _ha_get("/states") or []
    except Exception as error:
        raise HTTPException(503, f"Home Assistant camera data is unavailable: {error}") from error
    index = {str(row.get("entity_id")): row for row in states if isinstance(row, dict)}
    bridge = next(
        (row for entity_id, row in index.items() if entity_id.startswith("binary_sensor.") and "bridge_connection" in entity_id),
        None,
    )
    catalog = next(
        (
            row for entity_id, row in index.items()
            if entity_id.startswith("sensor.")
            and ("catalog_coverage" in entity_id or "catalog_research_coverage" in entity_id)
        ),
        None,
    )
    cameras = [
        _camera_row(row, index)
        for row in states
        if str(row.get("entity_id") or "").startswith("camera.")
        and bool((row.get("attributes") or {}).get("baiamonte_eufy"))
    ]
    # Compatibility during the one-time 9.1.0 -> 9.1.1 integration reload.
    if not cameras:
        eufy_bases = {
            entity_id.removeprefix("binary_sensor.").removesuffix("_motion_detected")
            for entity_id in index
            if entity_id.startswith("binary_sensor.") and entity_id.endswith("_motion_detected")
        }
        cameras = [_camera_row(index[f"camera.{base}"], index) for base in sorted(eufy_bases) if f"camera.{base}" in index]
    cameras.sort(key=lambda row: (row["area"], row["name"].casefold()))
    active = [(camera, kind) for camera in cameras for kind, value in camera["detections"].items() if value["active"]]
    attention = [camera for camera in cameras if camera["availability"] == "unavailable" or camera["battery_low"]]
    if active:
        names = ", ".join(f"{camera['name']} ({kind})" for camera, kind in active[:4])
        finding = {"level": "active", "title": "Camera activity detected", "message": names}
    elif attention:
        names = ", ".join(camera["name"] for camera in attention[:4])
        finding = {"level": "attention", "title": "Camera attention needed", "message": names}
    else:
        finding = {"level": "clear", "title": "No active camera finding", "message": "All reporting cameras are quiet and no low-battery condition is active."}
    return {
        "summary": {
            "total": len(cameras),
            "online": sum(camera["online"] for camera in cameras),
            "sleeping": sum(camera["sleeping"] for camera in cameras),
            "offline": sum(camera["availability"] == "unavailable" for camera in cameras),
            "active": len({camera["entity_id"] for camera, _ in active}),
            "low_battery": sum(camera["battery_low"] for camera in cameras),
            "ptz": sum(camera["capabilities"]["ptz"] for camera in cameras),
        },
        "finding": finding,
        "cameras": cameras,
        "integration": {
            "bridge_online": _state_on(bridge) if bridge else None,
            "catalog_coverage": (catalog or {}).get("state"),
            "native_catalogs": ((catalog or {}).get("attributes") or {}).get("effective_native_catalogs"),
            "structured_ai_fields": ((catalog or {}).get("attributes") or {}).get("ai_structured_diagnostic_fields"),
        },
        "updated_at": max((camera["last_updated"] or "" for camera in cameras), default=None),
        "privacy": "On-device Eufy classifications only; no new identity or facial inference is performed.",
    }


def sync_camera_security_events(payload: dict[str, Any]) -> dict[str, int]:
    """Persist edge classifications and durable health transitions idempotently."""
    active_keys: set[tuple[str, str]] = set()
    inserted = 0
    updated = 0
    with transaction() as (_, cursor):
        for camera in payload.get("cameras") or []:
            observations: list[tuple[str, bool, Any, str]] = []
            for kind, detection in (camera.get("detections") or {}).items():
                observations.append((kind, bool(detection.get("active")), detection.get("last_changed"), "info"))
            observations.extend(
                [
                    ("camera_unavailable", camera.get("availability") == "unavailable", camera.get("last_updated"), "warning"),
                    ("battery_low", bool(camera.get("battery_low")), camera.get("battery_low_changed_at") or camera.get("last_updated"), "warning"),
                ]
            )
            for event_type, active, changed_at, severity in observations:
                pair = (str(camera["entity_id"]), event_type)
                if not active:
                    cursor.execute(
                        "UPDATE camera_security_events SET ended_at=COALESCE(ended_at,%s),last_seen_at=GREATEST(last_seen_at,%s) "
                        "WHERE estate_id=%s AND camera_entity_id=%s AND event_type=%s AND ended_at IS NULL",
                        (_event_time(changed_at), _event_time(changed_at), estate_id(), camera["entity_id"], event_type),
                    )
                    updated += int(cursor.rowcount or 0)
                    continue
                active_keys.add(pair)
                detected_at = _event_time(changed_at)
                source_key = _event_source_key(camera, event_type, detected_at)
                evidence_url = camera.get("event_image_url") if camera.get("event_image_available") else None
                metadata = {
                    "model": camera.get("model"),
                    "availability": camera.get("availability"),
                    "battery": camera.get("battery"),
                    "wifi": camera.get("wifi"),
                    "edge_classification": event_type not in {"camera_unavailable", "battery_low"},
                }
                cursor.execute(
                    "INSERT INTO camera_security_events "
                    "(id,estate_id,source_key,camera_entity_id,camera_name,area,event_type,severity,detected_at,last_seen_at,evidence_url,metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),%s,%s) "
                    "ON DUPLICATE KEY UPDATE last_seen_at=NOW(6),ended_at=NULL,evidence_url=COALESCE(VALUES(evidence_url),evidence_url),metadata=VALUES(metadata)",
                    (
                        str(uuid4()), estate_id(), source_key, camera["entity_id"], camera["name"], camera["area"],
                        event_type, severity, detected_at, evidence_url, json.dumps(metadata),
                    ),
                )
                if cursor.rowcount == 1:
                    inserted += 1
                else:
                    updated += 1
        # Only close disappeared states after receiving a complete, connected
        # inventory.  A bridge restart must not falsely resolve open incidents.
        if payload.get("cameras") and (payload.get("integration") or {}).get("bridge_online") is not False:
            cursor.execute(
                "SELECT id,camera_entity_id,event_type FROM camera_security_events WHERE estate_id=%s AND ended_at IS NULL",
                (estate_id(),),
            )
            for row in cursor.fetchall():
                pair = (str(row["camera_entity_id"]), str(row["event_type"]))
                if pair not in active_keys:
                    cursor.execute("UPDATE camera_security_events SET ended_at=NOW(6) WHERE id=%s", (row["id"],))
                    updated += 1
    return {"inserted": inserted, "updated": updated}


def recent_camera_events(limit: int = 24) -> list[dict[str, Any]]:
    safe_limit = min(100, max(1, int(limit)))
    return fetch_all(
        "SELECT id,camera_entity_id,camera_name,area,event_type,severity,detected_at,last_seen_at,ended_at,"
        "review_status,reviewed_by,reviewed_at,evidence_url,linked_type,linked_id "
        "FROM camera_security_events WHERE estate_id=%s ORDER BY detected_at DESC LIMIT %s",
        (estate_id(), safe_limit),
    )


def _camera_from_dashboard(entity_id: str) -> dict[str, Any]:
    camera = next((row for row in camera_dashboard()["cameras"] if row["entity_id"] == entity_id), None)
    if not camera:
        raise HTTPException(404, "Eufy camera not found")
    return camera


def _proxy_image(entity_id: str, cache_seconds: int) -> Response:
    cached = _image_cache.get(entity_id)
    if cached and time.monotonic() - cached[0] < cache_seconds:
        return Response(cached[1], media_type=cached[2], headers={"Cache-Control": f"private, max-age={cache_seconds}", "X-Baiamonte-Camera": "cache"})
    token = home_assistant_token()
    if not token:
        raise HTTPException(503, "Home Assistant camera access is unavailable")
    request = urllib.request.Request(
        "http://supervisor/core/api/"
        + ("image_proxy/" if entity_id.startswith("image.") else "camera_proxy/")
        + urllib.parse.quote(entity_id, safe="."),
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as upstream:
            content = upstream.read()
            media_type = upstream.headers.get_content_type() or "image/jpeg"
    except Exception as error:
        if cached:
            return Response(cached[1], media_type=cached[2], headers={"Cache-Control": "private, max-age=30", "X-Baiamonte-Camera": "stale-cache"})
        raise HTTPException(503, f"Camera image is unavailable: {error}") from error
    _image_cache[entity_id] = (time.monotonic(), content, media_type)
    return Response(content, media_type=media_type, headers={"Cache-Control": f"private, max-age={cache_seconds}", "X-Baiamonte-Camera": "fresh"})


@router.get("/dashboard", dependencies=[Depends(authorize)])
def get_camera_dashboard() -> dict[str, Any]:
    payload = camera_dashboard()
    try:
        payload["recent_events"] = recent_camera_events()
        payload["event_summary"] = {
            "new": sum(row.get("review_status") == "new" for row in payload["recent_events"]),
            "active": sum(row.get("ended_at") is None for row in payload["recent_events"]),
        }
    except Exception:
        # The camera inventory remains useful during first boot before migrations.
        payload["recent_events"] = []
        payload["event_summary"] = {"new": 0, "active": 0}
    return payload


@router.get("/events", dependencies=[Depends(authorize)])
def list_camera_events(limit: int = 50) -> list[dict[str, Any]]:
    return recent_camera_events(limit)


@router.patch("/events/{event_id}", dependencies=[Depends(authorize_write)])
def review_camera_event(event_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = str(payload.get("status") or "").casefold()
    if status not in {"reviewed", "dismissed"}:
        raise HTTPException(422, "Status must be reviewed or dismissed")
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE camera_security_events SET review_status=%s,reviewed_by=%s,reviewed_at=NOW(6) "
            "WHERE id=%s AND estate_id=%s",
            (status, request_username(request), event_id, estate_id()),
        )
    if not changed:
        raise HTTPException(404, "Camera event not found")
    return {"ok": True}


@router.get("/{entity_id:path}/event-image", dependencies=[Depends(authorize)])
def event_image(entity_id: str) -> Response:
    camera = _camera_from_dashboard(entity_id)
    if not camera["event_image_available"]:
        raise HTTPException(404, "No cached event image is available")
    image_entity_id = camera.get("event_image_entity_id")
    if not image_entity_id:
        raise HTTPException(404, "No cached event image entity is available")
    return _proxy_image(str(image_entity_id), 120)


@router.get("/{entity_id:path}/snapshot", dependencies=[Depends(authorize)])
def camera_snapshot(entity_id: str) -> Response:
    _camera_from_dashboard(entity_id)
    return _proxy_image(entity_id, 30)


@router.get("/{entity_id:path}/live", dependencies=[Depends(authorize)])
def camera_live(entity_id: str) -> StreamingResponse:
    camera = _camera_from_dashboard(entity_id)
    if not camera["capabilities"]["streaming"]:
        raise HTTPException(422, "This camera does not advertise live streaming")
    token = home_assistant_token()
    if not token:
        raise HTTPException(503, "Home Assistant camera access is unavailable")

    def stream():
        try:
            _ha_post("/services/eufy_security/start_p2p_livestream", {"entity_id": entity_id})
            request = urllib.request.Request(
                "http://supervisor/core/api/camera_proxy_stream/" + urllib.parse.quote(entity_id, safe="."),
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=45) as upstream:
                while True:
                    chunk = upstream.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                _ha_post("/services/eufy_security/stop_p2p_livestream", {"entity_id": entity_id})
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control": "no-store"})


@router.post("/{entity_id:path}/admin-action", dependencies=[Depends(authorize_admin)])
def camera_admin_action(entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    camera = _camera_from_dashboard(entity_id)
    action = str(payload.get("action") or "").strip().casefold()
    capabilities = camera["capabilities"]
    service_payload: dict[str, Any] = {"entity_id": entity_id}
    if action in {"save_preset", "delete_preset"}:
        capability = "save_presets" if action == "save_preset" else "delete_presets"
        if not capabilities[capability]:
            raise HTTPException(422, "This camera does not advertise that preset capability")
        position = int(payload.get("position", -1))
        if position not in range(4):
            raise HTTPException(422, "Preset must be 0, 1, 2 or 3")
        service_payload["position"] = position
        service = f"eufy_security/{'save' if action == 'save_preset' else 'delete'}_preset_position"
    elif action == "quick_response":
        if not capabilities["quick_response"]:
            raise HTTPException(422, "This camera does not advertise quick responses")
        voice_id = int(payload.get("voice_id", -1))
        if voice_id < 0 or voice_id > 255:
            raise HTTPException(422, "Quick-response voice ID is invalid")
        service_payload["voice_id"] = voice_id
        service = "eufy_security/quick_response"
    else:
        raise HTTPException(422, "Unsupported administrator camera action")
    try:
        result = _ha_post(f"/services/{service}", service_payload)
    except Exception as error:
        raise HTTPException(503, f"Camera administrator command failed: {error}") from error
    return {"ok": True, "entity_id": entity_id, "action": action, "result_count": len(result or []) if isinstance(result, list) else 0}


@router.post("/{entity_id:path}/action", dependencies=[Depends(authorize_write)])
def camera_action(entity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    camera = _camera_from_dashboard(entity_id)
    action = str(payload.get("action") or "").strip().casefold()
    capabilities = camera["capabilities"]
    service: str
    service_payload: dict[str, Any] = {"entity_id": entity_id}
    if action in PTZ_DIRECTIONS:
        if not capabilities["ptz"]:
            raise HTTPException(422, "This camera does not advertise PTZ support")
        service = "eufy_security/ptz"
        service_payload["direction"] = PTZ_DIRECTIONS[action]
    elif action == "preset":
        if not capabilities["presets"]:
            raise HTTPException(422, "This camera does not advertise preset support")
        position = int(payload.get("position", -1))
        if position not in range(4):
            raise HTTPException(422, "Preset must be 0, 1, 2 or 3")
        service = "eufy_security/preset_position"
        service_payload["position"] = position
    elif action == "calibrate":
        if not capabilities["calibrate"]:
            raise HTTPException(422, "This camera does not advertise calibration support")
        service = "eufy_security/calibrate"
    elif action == "refresh_snapshot":
        service = "eufy_security/generate_image"
        _image_cache.pop(entity_id, None)
    elif action == "stop_stream":
        if not capabilities["streaming"]:
            raise HTTPException(422, "This camera does not advertise streaming support")
        # Compatibility for a browser/Companion page that was already open
        # during an upgrade. The /live generator owns the real stop in its
        # finally block; acknowledging this legacy action avoids a second Eufy
        # command while allowing the cached client to close its dialog.
        return {"ok": True, "entity_id": entity_id, "action": action, "service": "stream.owner", "result_count": 0}
    elif action == "start_stream":
        if not capabilities["streaming"]:
            raise HTTPException(422, "This camera does not advertise streaming support")
        service = "eufy_security/start_p2p_livestream"
    elif action.startswith("set_"):
        control = action.removeprefix("set_")
        control_state = camera["controls"].get(control)
        if not control_state or not control_state["available"] or not control_state["entity_id"]:
            raise HTTPException(422, "This camera does not expose that safe control")
        service = f"homeassistant/turn_{'on' if bool(payload.get('value')) else 'off'}"
        service_payload = {"entity_id": control_state["entity_id"]}
    else:
        raise HTTPException(422, "Unsupported camera action")
    try:
        result = _ha_post(f"/services/{service}", service_payload)
    except Exception as error:
        raise HTTPException(503, f"Camera command failed: {error}") from error
    return {"ok": True, "entity_id": entity_id, "action": action, "service": service.replace("/", "."), "result_count": len(result or []) if isinstance(result, list) else 0}
