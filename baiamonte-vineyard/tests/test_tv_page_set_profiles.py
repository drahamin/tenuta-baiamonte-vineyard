from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_original_and_estate_default_are_device_assignable_in_admin():
    backend = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    admin = (STATIC / "index.html").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    tv_config = (STATIC / "assets" / "tv-config.js").read_text(encoding="utf-8")
    assert '"id": "original", "name": "Original"' in backend
    assert '"id": "estate-default", "name": "Estate default"' in backend
    assert '"id": "office-samsung", "name": "Office Samsung"' in backend
    assert 'defaults["office-samsung"] = "estate-default"' in backend
    assert "display_assignments = _tv_display_assignments()" in backend
    assert '"page_set": display_assignments[device["id"]]' in backend
    assert 'id="tvDisplayProfiles"' in admin
    assert 'id="tvDisplayAssignments"' in admin
    assert "data-tv-display-assignment" in tv_config
    assert "payload.tv_display_assignments" in script
    assert "TV configuration loading" in script
    assert "Loading TV settings and Home Assistant cameras" in tv_config


def test_display_profile_is_resolved_server_side_with_rollback_default():
    server = (ROOT / "app" / "display_server.py").read_text(encoding="utf-8")
    markup = (STATIC / "display.html").read_text(encoding="utf-8")
    assert 'TV_PAGE_SETS = {"original", "estate-default"}' in server
    assert 'runtime_option("tv_display_assignments", {})' in server
    assert 'device_id == "office-samsung"' in server
    assert 'page_set = "estate-default"' in server
    assert 'page_set = "original"' in server
    assert 'X-Baiamonte-TV-Page-Set' in server
    assert 'data-page-set="__TV_PAGE_SET__"' in markup
    assert 'assets/display-estate-default.css' in markup


def test_estate_default_preserves_live_weather_traffic_cameras_and_remote_control():
    markup = (STATIC / "display.html").read_text(encoding="utf-8")
    script = (STATIC / "display.js").read_text(encoding="utf-8")
    assert 'traffic-app/adsb/?tv=map&amp;weather=1&amp;zoom=2' in markup
    assert 'id="weatherRadarFrame"' in markup
    assert "function estateCameraPages" in script
    assert "(d.camera_pages||[]).forEach" in script
    assert "refreshTraffic('adsb')" in script
    assert "refreshTraffic('ais')" in script
    assert "registerKeyBatch" in script
    assert "tvPageSet!=='estate-default'" in script


def test_estate_default_styles_are_scoped_and_do_not_change_original():
    styles = (STATIC / "assets" / "display-estate-default.css").read_text(encoding="utf-8")
    assert 'html[data-page-set="estate-default"]' in styles
    assert "html[data-page-set=\"original\"]" not in styles


def test_admin_menu_wraps_into_readable_rows_on_desktop():
    styles = (STATIC / "control-center.css").read_text(encoding="utf-8")
    assert ".tabs>.tab-row-admin" in styles
    assert "repeat(8,minmax(96px,1fr))" in styles
    assert "repeat(6,minmax(96px,1fr))" in styles


def test_admin_tv_response_contains_each_device_assignment(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "_read_addon_options", lambda: {})
    monkeypatch.setattr(main, "home_assistant_manager_camera_catalog", lambda: [])
    payload = main.get_tv_config(main.get_settings())
    devices = {item["id"]: item for item in payload["display_devices"]}
    assert devices["office-samsung"]["page_set"] == "estate-default"
    assert devices["samsung-frame-32"]["page_set"] == "original"
    assert devices["vineyard-kiosk"]["page_set"] == "original"
