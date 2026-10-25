from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import display_server


def test_tv_cache_age_comes_from_source_capture_time(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(display_server, "CAMERA_CACHE_DIR", tmp_path)
    captured_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()

    display_server._remember_camera("camera.example", b"\xff\xd8\xffimage", captured_at)
    headers = display_server._camera_headers("camera.example", "scheduled-cache")

    assert headers["X-Baiamonte-Camera-Captured-At"] == captured_at
    assert 10_700 <= int(headers["X-Baiamonte-Camera-Age"]) <= 10_900


def test_tv_cache_without_source_time_does_not_invent_an_age(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(display_server, "CAMERA_CACHE_DIR", tmp_path)

    display_server._remember_camera("camera.example", b"\xff\xd8\xffimage")
    headers = display_server._camera_headers("camera.example", "scheduled-cache")

    assert "X-Baiamonte-Camera-Captured-At" not in headers
    assert "X-Baiamonte-Camera-Age" not in headers


def test_tv_configuration_keeps_camera_pages_visible_and_save_reachable() -> None:
    html = (display_server.static_dir / "index.html").read_text()
    css = (display_server.static_dir / "control-center.css").read_text()

    assert '<section id="tvCameraPages"' in html
    assert 'id="tvConfigActions"' in html
    assert 'href="#tvConfigActions"' in html
    assert ".tv-config-camera{grid-column:1/-1;grid-row:1}" in css

