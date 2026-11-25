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


def test_tv_memory_cache_adopts_newer_verified_disk_pixels(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(display_server, 'CAMERA_CACHE_DIR', tmp_path)
    monkeypatch.setattr(display_server, 'runtime_option', lambda _k, default: default)
    monkeypatch.setattr(display_server, 'get_settings', lambda: SimpleNamespace(tv_camera_entities='camera.example'))
    monkeypatch.setattr(display_server, '_camera_cache', {'camera.example': (display_server.time.monotonic(), b'old-memory-pixels', 'image/jpeg', old)})
    display_server._remember_camera('camera.example', b'new-disk-pixels', current)
    response = display_server.camera_snapshot('camera.example')
    assert response.body == b'new-disk-pixels'
    assert response.headers['X-Baiamonte-Camera-Captured-At'] == current


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
    monkeypatch.setattr(display_server, "_camera_cache", {"camera.example": (display_server.time.monotonic() - display_server.CAMERA_CACHE_SECONDS - 1, b"old-disk-pixels", "image/jpeg", old)})
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


def test_stale_first_proxy_read_allows_one_bounded_read_of_newer_evidence(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    setup_proxy(monkeypatch, tmp_path, [old, old, current, current])
    result = intelligence.home_assistant_camera_snapshot("camera.example", force_fresh=True)
    assert result["fresh"] is True
    assert result["captured_at"] == current
    assert saved_snapshot_evidence(tmp_path / "camera.example.image")["captured_at"] == current


def test_unknown_tv_frame_does_not_replace_verified_saved_evidence(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(display_server, 'CAMERA_CACHE_DIR', tmp_path)
    monkeypatch.setattr(display_server, 'runtime_option', lambda _k, default: default)
    monkeypatch.setattr(display_server, 'get_settings', lambda: SimpleNamespace(tv_camera_entities='camera.example'))
    monkeypatch.setattr(display_server, '_camera_cache', {})
    monkeypatch.setattr(display_server, '_camera_failures', {})
    monkeypatch.setattr(display_server, 'home_assistant_token', lambda: 'test-token')
    times = iter([current, old, current])
    monkeypatch.setattr(display_server, '_home_assistant_capture_time', lambda *_: next(times))
    class Response(BytesIO):
        def __init__(self):
            super().__init__(b'uncertain-pixels')
            self.headers = Message()
            self.headers['Content-Type'] = 'image/jpeg'
    monkeypatch.setattr(display_server.urllib.request, 'urlopen', lambda *_a, **_k: Response())
    display_server._remember_camera('camera.example', b'verified-pixels', old)
    monkeypatch.setattr(display_server, '_camera_cache', {'camera.example': (display_server.time.monotonic() - display_server.CAMERA_CACHE_SECONDS - 1, b'verified-pixels', 'image/jpeg', old)})
    response = display_server.camera_snapshot('camera.example')
    assert response.body == b'verified-pixels'
    assert response.headers['X-Baiamonte-Camera-Captured-At'] == old
    assert (tmp_path / 'camera.example.image').read_bytes() == b'verified-pixels'


def _child_cache_write(image, ready, finished):
    from app.domains.camera_snapshot_evidence import write_saved_snapshot
    ready.set()
    write_saved_snapshot(image, b'child-pixels', datetime.now(timezone.utc).isoformat())
    finished.set()


def test_cache_writer_honors_a_lock_held_by_another_process(tmp_path):
    import multiprocessing
    import fcntl
    image = tmp_path / 'camera.example.image'
    ctx = multiprocessing.get_context('spawn')
    ready, finished = ctx.Event(), ctx.Event()
    worker = ctx.Process(target=_child_cache_write, args=(image, ready, finished))
    with image.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            worker.start()
            assert ready.wait(10)
            assert not finished.wait(0.15)
            assert not image.exists()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    worker.join(10)
    if worker.is_alive():
        worker.terminate()
        worker.join()
    assert worker.exitcode == 0
    assert finished.is_set()
    assert image.read_bytes() == b'child-pixels'
    assert saved_snapshot_evidence(image)['captured_at'] is not None


def test_unknown_capture_age_is_explicit_in_both_caption_languages():
    from app.domains.camera_snapshot_evidence import camera_snapshot_caption
    captured = {"stale": True, "age_seconds": None}
    assert "capture time unknown" in camera_snapshot_caption("Example", captured)
    assert "sconosciuta" in camera_snapshot_caption("Example", captured, italian=True)
    assert "1 min" not in camera_snapshot_caption("Example", captured)
    assert "2 min old" in camera_snapshot_caption("Example", {"stale": True, "age_seconds": 120})


def test_daily_maintenance_captures_one_stale_camera_and_backs_off(monkeypatch, tmp_path):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    current = datetime.now(timezone.utc).isoformat()
    setup_proxy(monkeypatch, tmp_path, [])
    state = {"state": "idle", "attributes": {"snapshot_updated_at": old, "snapshot_time_basis": "capture"}}
    monkeypatch.setattr(intelligence, "_ha_get", lambda _: state)
    calls = []
    def capture(path, payload):
        calls.append((path, payload))
        state["attributes"]["snapshot_updated_at"] = current
    monkeypatch.setattr(intelligence, "_ha_post", capture)
    monkeypatch.setattr(intelligence, "home_assistant_camera_snapshot", lambda *_a, **_k: {"fresh": True, "captured_at": current})
    result = intelligence.refresh_camera_snapshot_cache()
    assert result["capture_requested"] is True
    assert len(calls) == 1 and calls[0][1] == {"entity_id": "camera.example"}
    state["attributes"]["snapshot_updated_at"] = old
    assert intelligence.refresh_camera_snapshot_cache()["capture_requested"] is False
    assert len(calls) == 1


def test_daily_maintenance_leaves_active_streams_alone(monkeypatch, tmp_path):
    setup_proxy(monkeypatch, tmp_path, [])
    monkeypatch.setattr(intelligence, "_ha_get", lambda _: {"state": "streaming", "attributes": {}})
    monkeypatch.setattr(intelligence, "_ha_post", lambda *_a: (_ for _ in ()).throw(AssertionError("must not capture")))
    monkeypatch.setattr(intelligence, "home_assistant_camera_snapshot", lambda *_a, **_k: {"fresh": False})
    assert intelligence.refresh_camera_snapshot_cache()["capture_requested"] is False


def test_daily_capture_failure_keeps_retained_image_and_rotates(monkeypatch, tmp_path):
    setup_proxy(monkeypatch, tmp_path, [])
    monkeypatch.setattr(intelligence, "_ha_get", lambda _: {"state": "idle", "attributes": {}})
    monkeypatch.setattr(intelligence, "_ha_post", lambda *_a: (_ for _ in ()).throw(TimeoutError()))
    monkeypatch.setattr(intelligence, "home_assistant_camera_snapshot", lambda *_a, **_k: {"fresh": False, "cached": True})
    result = intelligence.refresh_camera_snapshot_cache()
    assert result["capture_error"] is True
    assert result["updated"] is False
    assert (tmp_path / "camera.example.attempt").exists()


def test_metadata_timeout_retries_without_redating_uncertain_pixels(monkeypatch, tmp_path):
    current = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    monkeypatch.setattr(display_server, 'CAMERA_CACHE_DIR', tmp_path)
    monkeypatch.setattr(display_server, 'runtime_option', lambda _k, default: default)
    monkeypatch.setattr(display_server, 'get_settings', lambda: SimpleNamespace(tv_camera_entities='camera.example'))
    monkeypatch.setattr(display_server, '_camera_cache', {'camera.example': (display_server.time.monotonic() - display_server.CAMERA_CACHE_SECONDS - 1, b'old', 'image/jpeg', old)})
    monkeypatch.setattr(display_server, '_camera_failures', {})
    monkeypatch.setattr(display_server, 'home_assistant_token', lambda: 'test')
    values = iter([current, None, current])
    monkeypatch.setattr(display_server, '_home_assistant_capture_time', lambda *_: next(values))
    class Response(BytesIO):
        def __init__(self):
            super().__init__(b'new-pixels')
            self.headers = Message()
            self.headers['Content-Type'] = 'image/jpeg'
    monkeypatch.setattr(display_server.urllib.request, 'urlopen', lambda *_a, **_k: Response())
    display_server._remember_camera('camera.example', b'old', old)
    response = display_server.camera_snapshot('camera.example')
    assert response.body == b'new-pixels'
    assert response.headers['X-Baiamonte-Camera-Captured-At'] == current
