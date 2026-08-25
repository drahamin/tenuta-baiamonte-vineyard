from __future__ import annotations

import time
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response

from ..access import authorize, authorize_write
from ..ha_auth import home_assistant_token
from ..intelligence import _ha_get, _ha_post


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


def _state_on(row: dict[str, Any] | None) -> bool:
    return str((row or {}).get("state") or "").casefold() in {"on", "true", "detected", "ringing"}


def _entity(index: dict[str, dict[str, Any]], domain: str, base: str, suffix: str) -> dict[str, Any] | None:
    return index.get(f"{domain}.{base}_{suffix}")


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
    detections: dict[str, dict[str, Any]] = {}
    for key, suffix in DETECTION_SUFFIXES.items():
        related = _entity(index, "binary_sensor", base, suffix)
        detections[key] = {
            "active": _state_on(related),
            "last_changed": (related or {}).get("last_changed"),
        }
    battery_low = _entity(index, "binary_sensor", base, "battery_low")
    connected = _entity(index, "binary_sensor", base, "connected")
    sensors = {
        key: (_entity(index, "sensor", base, suffix) or {}).get("state")
        for key, suffix in SENSOR_SUFFIXES.items()
    }
    controls: dict[str, dict[str, Any]] = {}
    for key, suffix in CONTROL_SUFFIXES.items():
        related = _entity(index, "switch", base, suffix)
        controls[key] = {
            "available": bool(related and related.get("state") not in {"unavailable", "unknown"}),
            "on": _state_on(related),
            "entity_id": (related or {}).get("entity_id"),
        }
    event_image = index.get(f"image.{base}_event_image")
    online = camera.get("state") not in {"unavailable", "unknown"} and (connected is None or _state_on(connected))
    return {
        "entity_id": entity_id,
        "name": attrs.get("friendly_name") or base.replace("_", " ").title(),
        "model": attrs.get("model"),
        "area": _area(str(attrs.get("friendly_name") or base)),
        "online": online,
        "last_updated": camera.get("last_updated"),
        "capabilities": _capabilities(camera),
        "detections": detections,
        "battery": sensors["battery"],
        "battery_low": _state_on(battery_low),
        "charging": sensors["charging"],
        "wifi": sensors["wifi"],
        "stream_status": sensors["stream"],
        "person_name": sensors["person_name"] if sensors["person_name"] not in {None, "unknown", "unavailable"} else None,
        "controls": controls,
        "event_image_available": bool(event_image and event_image.get("state") not in {"unavailable", "unknown"}),
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
        (row for entity_id, row in index.items() if entity_id.startswith("sensor.") and "catalog_coverage" in entity_id),
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
    attention = [camera for camera in cameras if not camera["online"] or camera["battery_low"]]
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
            "offline": sum(not camera["online"] for camera in cameras),
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
    return camera_dashboard()


@router.get("/{entity_id:path}/event-image", dependencies=[Depends(authorize)])
def event_image(entity_id: str) -> Response:
    camera = _camera_from_dashboard(entity_id)
    if not camera["event_image_available"]:
        raise HTTPException(404, "No cached event image is available")
    base = entity_id.partition(".")[2]
    return _proxy_image(f"image.{base}_event_image", 120)


@router.get("/{entity_id:path}/snapshot", dependencies=[Depends(authorize)])
def camera_snapshot(entity_id: str) -> Response:
    _camera_from_dashboard(entity_id)
    return _proxy_image(entity_id, 30)


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
    elif action in {"start_stream", "stop_stream"}:
        if not capabilities["streaming"]:
            raise HTTPException(422, "This camera does not advertise streaming support")
        service = f"eufy_security/{'start' if action == 'start_stream' else 'stop'}_p2p_livestream"
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
