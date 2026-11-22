from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
import json
from types import SimpleNamespace
from app import intelligence, display_server
from app.domains.camera_snapshot_evidence import snapshot_evidence, saved_snapshot_evidence


def test_unknown_future_and_old_capture_times():
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    for value in [None, 'invalid', (now + timedelta(hours=1)).isoformat()]:
        assert snapshot_evidence(value, now=now) == {'captured_at': None, 'age_seconds': None, 'current': False}
    assert snapshot_evidence((now - timedelta(days=2)).isoformat(), now=now)['age_seconds'] == 172800


def setup_proxy(monkeypatch, tmp_path, times):
    monkeypatch.setattr(intelligence, 'home_assistant_manager_cameras', lambda: [{'entity_id': 'camera.example', 'name': 'Example'}])
    monkeypatch.setattr(intelligence, 'home_assistant_token', lambda: 'test-token')
    monkeypatch.setattr(intelligence, 'get_settings', lambda: SimpleNamespace(tv_camera_entities=''))
    monkeypatch.setattr(intelligence, 'runtime_option', lambda _k, default: default)
    monkeypatch.setattr(intelligence, 'Path', lambda _: tmp_path)
    values = iter(times)
    monkeypatch.setattr(intelligence, '_ha_get', lambda _: {'attributes': {'snapshot_updated_at': next(values)}})
    class Response(BytesIO):
        def __init__(self):
            super().__init__(b'new-camera-pixels')
            self.headers = Message()
            self.headers['Content-Type'] = 'image/jpeg'
    monkeypatch.setattr(intelligence.urllib.request, 'urlopen', lambda *_a, **_k: Response())


def test_http_200_old_ha_frame_does_not_become_fresh(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    setup_proxy(monkeypatch, tmp_path, [old, old])
    result = intelligence.home_assistant_camera_snapshot('camera.example', force_fresh=True)
    assert result['fresh'] is False and result['stale'] is True
    assert result['age_seconds'] >= 172799
    assert saved_snapshot_evidence(tmp_path / 'camera.example.image')['captured_at'] == old


def test_unknown_or_racing_time_cannot_retimestamp_pixels(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    for times in ([None, None], [old, new]):
        setup_proxy(monkeypatch, tmp_path, times)
        result = intelligence.home_assistant_camera_snapshot('camera.example', force_fresh=True)
        assert result['fresh'] is False and result['age_seconds'] is None
        assert result['captured_at'] is None
        assert not (tmp_path / 'camera.example.json').exists()


def test_older_source_preserves_newer_retained_pixels(monkeypatch, tmp_path):
    retained = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    image = tmp_path / 'camera.example.image'
    image.write_bytes(b'retained-pixels')
    image.with_suffix('.json').write_text(json.dumps({'captured_at': retained}))
    setup_proxy(monkeypatch, tmp_path, [old, old])
    result = intelligence.home_assistant_camera_snapshot('camera.example', force_fresh=True)
    assert result['data'] == b'retained-pixels'
    assert result['fresh'] is False and result['cached'] is True
    assert result['captured_at'] == retained
    assert image.read_bytes() == b'retained-pixels'


def test_metadata_for_different_pixels_has_no_capture_time(tmp_path):
    image = tmp_path / 'camera.example.image'
    image.write_bytes(b'old-pixels')
    image.with_suffix('.json').write_text(json.dumps({'captured_at': datetime.now(timezone.utc).isoformat(), 'sha256': '0' * 64}))
    assert saved_snapshot_evidence(image)['captured_at'] is None


def test_tv_memory_cache_keeps_its_own_time_when_disk_is_newer(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(display_server, 'CAMERA_CACHE_DIR', tmp_path)
    monkeypatch.setattr(display_server, 'runtime_option', lambda _k, default: default)
    monkeypatch.setattr(display_server, 'get_settings', lambda: SimpleNamespace(tv_camera_entities='camera.example'))
    monkeypatch.setattr(display_server, '_camera_cache', {'camera.example': (display_server.time.monotonic(), b'old-memory-pixels', 'image/jpeg', old)})
    display_server._remember_camera('camera.example', b'new-disk-pixels', current)
    response = display_server.camera_snapshot('camera.example')
    assert response.body == b'old-memory-pixels'
    assert response.headers['X-Baiamonte-Camera-Captured-At'] == old


def test_retained_time_is_checked_against_the_returned_bytes(tmp_path):
    from app.domains.camera_snapshot_evidence import write_saved_snapshot
    image = tmp_path / "camera.example.image"
    current = datetime.now(timezone.utc).isoformat()
    write_saved_snapshot(image, b"new-frame", current)
    assert saved_snapshot_evidence(image, content=b"old-frame")["captured_at"] is None
    assert saved_snapshot_evidence(image, content=b"new-frame")["captured_at"] == current


def test_tv_reads_a_newer_ha_still_even_when_disk_file_was_recently_written(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(display_server, "CAMERA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(display_server, "runtime_option", lambda _k, default: default)
    monkeypatch.setattr(display_server, "get_settings", lambda: SimpleNamespace(tv_camera_entities="camera.example"))
    monkeypatch.setattr(display_server, "_camera_cache", {})
    monkeypatch.setattr(display_server, "_camera_failures", {})
    monkeypatch.setattr(display_server, "home_assistant_token", lambda: "test-token")
    monkeypatch.setattr(display_server, "_home_assistant_capture_time", lambda *_: current)
    class Response(BytesIO):
        def __init__(self):
            super().__init__(b"new-verified-ha-image")
            self.headers = Message()
            self.headers["Content-Type"] = "image/jpeg"
    monkeypatch.setattr(display_server.urllib.request, "urlopen", lambda *_a, **_k: Response())
    display_server._remember_camera("camera.example", b"old-disk-pixels", old)
    response = display_server.camera_snapshot("camera.example")
    assert response.body == b"new-verified-ha-image"
    assert response.headers["X-Baiamonte-Camera-Captured-At"] == current


def test_receipt_time_cannot_make_a_replayed_ha_image_current(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    setup_proxy(monkeypatch, tmp_path, [])
    monkeypatch.setattr(intelligence, "_ha_get", lambda _: {"attributes": {"snapshot_updated_at": now, "snapshot_time_basis": "received"}})
    result = intelligence.home_assistant_camera_snapshot("camera.example", force_fresh=True)
    assert result["fresh"] is False
    assert result["captured_at"] is None
    assert result["age_seconds"] is None
