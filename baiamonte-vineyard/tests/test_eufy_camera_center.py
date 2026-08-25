from pathlib import Path

import pytest
from fastapi import HTTPException

from app.domains import camera_routes


ROOT = Path(__file__).resolve().parents[1]


def camera_states(ptz=True):
    return [
        {
            "entity_id": "camera.east_360",
            "state": "idle",
            "last_updated": "2026-08-25T12:00:00+00:00",
            "attributes": {
                "friendly_name": "East 360",
                "baiamonte_eufy": True,
                "model": "T8170",
                "capabilities": {"ptz": ptz, "rotate_360": ptz, "presets": ptz, "save_presets": ptz, "delete_presets": ptz, "calibrate": ptz, "streaming": True, "quick_response": False},
            },
        },
        {"entity_id": "binary_sensor.east_360_connected", "state": "on"},
        {"entity_id": "binary_sensor.east_360_motion_detected", "state": "on", "last_changed": "2026-08-25T11:59:00+00:00"},
        {"entity_id": "binary_sensor.east_360_person_detected", "state": "off"},
        {"entity_id": "binary_sensor.east_360_battery_low", "state": "off"},
        {"entity_id": "sensor.east_360_battery", "state": "86"},
        {"entity_id": "switch.east_360_motion_detection", "state": "on"},
        {"entity_id": "image.east_360_event_image", "state": "2026-08-25T11:59:00+00:00"},
        {"entity_id": "binary_sensor.baiamonte_eufy_bridge_connection", "state": "on"},
        {"entity_id": "sensor.baiamonte_eufy_mega_catalog_coverage", "state": "98.5", "attributes": {"effective_native_catalogs": 34, "ai_structured_diagnostic_fields": 7}},
    ]


def test_dashboard_uses_explicit_capabilities_and_cached_event_evidence(monkeypatch):
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: camera_states())
    payload = camera_routes.camera_dashboard()
    camera = payload["cameras"][0]
    assert payload["summary"] == {"total": 1, "online": 1, "sleeping": 0, "offline": 0, "active": 1, "low_battery": 0, "ptz": 1}
    assert camera["capabilities"]["ptz"] is True
    assert camera["detections"]["motion"]["active"] is True
    assert camera["event_image_available"] is True
    assert payload["finding"]["level"] == "active"
    assert payload["integration"] == {"bridge_online": True, "catalog_coverage": "98.5", "native_catalogs": 34, "structured_ai_fields": 7}
    assert "no new identity" in payload["privacy"].lower()


def test_ptz_command_is_sent_only_when_camera_advertises_it(monkeypatch):
    calls = []
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: camera_states())
    monkeypatch.setattr(camera_routes, "_ha_post", lambda path, payload: calls.append((path, payload)) or [])
    result = camera_routes.camera_action("camera.east_360", {"action": "left"})
    assert result["ok"] is True
    assert calls == [("/services/eufy_security/ptz", {"entity_id": "camera.east_360", "direction": "LEFT"})]


def test_ptz_command_is_rejected_for_fixed_camera(monkeypatch):
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: camera_states(ptz=False))
    with pytest.raises(HTTPException) as error:
        camera_routes.camera_action("camera.east_360", {"action": "left"})
    assert error.value.status_code == 422


def test_sleeping_battery_camera_is_healthy_not_offline(monkeypatch):
    states = camera_states()
    next(row for row in states if row["entity_id"].endswith("_connected"))["state"] = "off"
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: states)
    payload = camera_routes.camera_dashboard()
    assert payload["summary"]["offline"] == 0
    assert payload["summary"]["sleeping"] == 1
    assert payload["cameras"][0]["availability"] == "sleeping"


def test_device_key_joins_renamed_related_entities_and_cached_image(monkeypatch):
    states = camera_states()
    key = "privacy-safe-device-key"
    for row in states:
        if row["entity_id"].startswith(("camera.", "binary_sensor.east_360", "sensor.east_360", "switch.east_360", "image.east_360")):
            row.setdefault("attributes", {})["baiamonte_device_key"] = key
    battery = next(row for row in states if row["entity_id"] == "sensor.east_360_battery")
    battery["entity_id"] = "sensor.renamed_battery_level"
    battery["attributes"]["baiamonte_property"] = "battery"
    image = next(row for row in states if row["entity_id"] == "image.east_360_event_image")
    image["entity_id"] = "image.renamed_latest_evidence"
    image["state"] = "unknown"
    image["attributes"].update({"baiamonte_property": "camera", "event_image_available": True})
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: states)
    camera = camera_routes.camera_dashboard()["cameras"][0]
    assert camera["battery"] == "86"
    assert camera["event_image_available"] is True
    assert camera["event_image_entity_id"] == "image.renamed_latest_evidence"


def test_camera_workspace_does_not_expose_alarm_or_lock_controls():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/assets/cameras.js").read_text(encoding="utf-8")
    assert 'data-view="cameras"' in html
    assert 'id="view-cameras"' in html
    assert "capabilities?.ptz" in javascript
    assert "Sirens, locks, microphones and speakers are not available here" in javascript
    assert "trigger_camera_alarm" not in javascript
    assert "lock.unlock" not in javascript


def test_admin_can_save_verified_preset(monkeypatch):
    calls = []
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: camera_states())
    monkeypatch.setattr(camera_routes, "_ha_post", lambda path, payload: calls.append((path, payload)) or [])
    result = camera_routes.camera_admin_action("camera.east_360", {"action": "save_preset", "position": 2})
    assert result["ok"] is True
    assert calls == [("/services/eufy_security/save_preset_position", {"entity_id": "camera.east_360", "position": 2})]


def test_camera_event_migration_and_review_surface_exist():
    migration = (ROOT / "db/migrations/127_eufy_security_events.sql").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/assets/cameras.js").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS camera_security_events" in migration
    assert "data-camera-event-review" in javascript
    assert "Start low-load live view" in javascript


def test_live_view_has_one_stream_cleanup_owner():
    javascript = (ROOT / "app/static/assets/cameras.js").read_text(encoding="utf-8")
    live_stop = javascript.split("async function stopCameraLive()", 1)[1].split("async function startCameraLive", 1)[0]
    routes = (ROOT / "app/domains/camera_routes.py").read_text(encoding="utf-8")
    assert "stop_stream" not in live_stop
    assert "finally:" in routes
    assert "/services/eufy_security/stop_p2p_livestream" in routes


def test_stale_client_stop_is_acknowledged_without_second_eufy_command(monkeypatch):
    calls = []
    monkeypatch.setattr(camera_routes, "_ha_get", lambda _path: camera_states())
    monkeypatch.setattr(camera_routes, "_ha_post", lambda path, payload: calls.append((path, payload)) or [])
    result = camera_routes.camera_action("camera.east_360", {"action": "stop_stream"})
    assert result["ok"] is True
    assert result["service"] == "stream.owner"
    assert calls == []
