from types import SimpleNamespace
from pathlib import Path

from starlette.requests import Request

from app import main
from app.domains import alerts_intake_routes


ROOT = Path(__file__).resolve().parents[1]


def test_operational_projections_retains_live_grape_dashboard_dependency(monkeypatch):
    grapes = {"vintages": [], "metrics": {}, "blend_plans": [], "varieties": []}
    monkeypatch.setattr(main, "grape_dashboard", lambda year: grapes)
    monkeypatch.setattr(main, "blend_program_payload", lambda year: {"planning": {}, "settings": {}})
    monkeypatch.setattr(main, "historical_forecast_evidence", lambda year, rows: (0.65, {}))
    monkeypatch.setattr(main, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "build_operational_projections", lambda *args: {"year": args[0], "ok": True})

    assert main.operational_projections(2026) == {"year": 2026, "ok": True}


def test_alert_settings_can_filter_approved_two_field_templates(monkeypatch):
    monkeypatch.setattr(alerts_intake_routes, "fetch_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        alerts_intake_routes,
        "alert_preference",
        lambda alert_type: {"alert_type": alert_type, "enabled": True},
    )
    monkeypatch.setattr(
        alerts_intake_routes,
        "whatsapp_templates",
        lambda: {"templates": [{"name": "estate_alert", "status": "APPROVED", "language": "en", "components": [{"type": "BODY", "text": "{{1}}: {{2}}"}]}]},
    )
    monkeypatch.setattr(alerts_intake_routes, "cellar_guardrails", lambda settings: {})
    monkeypatch.setattr(alerts_intake_routes, "home_assistant_token", lambda: None)
    settings = SimpleNamespace(
        ha_notifications_enabled=False,
        ha_notify_service="",
        gmail_address="",
        gmail_app_password="",
        whatsapp_access_token="",
        whatsapp_phone_number_id="",
    )
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)})

    payload = alerts_intake_routes.alert_settings(request, settings)

    assert payload["whatsapp_templates"] == [{"name": "estate_alert", "language": "en", "variable_count": 2}]
    assert len(payload["preferences"]) == len(alerts_intake_routes.ALERT_TYPES)


def test_mobile_dashboard_reflows_without_hiding_vintage_data():
    css = (main.static_dir / "app.css").read_text(encoding="utf-8")
    javascript = (main.static_dir / "app.js").read_text(encoding="utf-8")

    assert ".vintage-row>div:nth-child(4){display:none}" not in css
    assert "max-width:1440px" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "-webkit-text-size-adjust:100%" in css
    assert "@media(hover:none) and (pointer:coarse)" in css
    assert "Menu · ${active}" in javascript


def test_apple_home_screen_assets_use_native_touch_icon_size():
    for name in ("index.html", "crew.html", "display.html"):
        html = (main.static_dir / name).read_text(encoding="utf-8")
        assert 'rel="apple-touch-icon" sizes="180x180" href="assets/apple-touch-icon.png"' in html
    assert (main.static_dir / "apple-touch-icon.png").is_file()
    manifest = (main.static_dir / "site.webmanifest").read_text(encoding="utf-8")
    assert '"sizes": "180x180"' in manifest


def test_picture_glance_cards_use_home_assistant_camera_image_schema():
    dashboard = ROOT / "dashboards" / "vineyard-overview.yaml"
    lines = dashboard.read_text(encoding="utf-8").splitlines()
    picture_blocks = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip() != "- type: picture-glance":
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate.lstrip().startswith("- type:") and candidate_indent == indent:
                break
            if candidate and not candidate[0].isspace():
                break
            end += 1
        picture_blocks.append(lines[index:end])
        index = end

    assert picture_blocks
    for block in picture_blocks:
        child_indent = len(block[0]) - len(block[0].lstrip()) + 2
        top_level = [line.strip() for line in block[1:] if len(line) - len(line.lstrip()) == child_indent]
        assert not any(line.startswith("entity: camera.") for line in top_level)
        assert any(line.startswith(("camera_image: camera.", "image:")) for line in top_level)

    text = "\n".join(lines)
    for retired in (
        "camera.driveway_entrance",
        "camera.main_entrance",
        "camera.south_vineyard_360",
        "camera.top_east_vineyard",
        "camera.192_168_0_54",
    ):
        assert retired not in text
    assert "camera_image: camera.cisterna" in text


def test_startup_migrates_retired_cistern_and_tv_camera_options():
    entrypoint = (ROOT / "entrypoint.py").read_text(encoding="utf-8")
    assert 'amendments["cistern_camera_entity"] = "camera.cisterna"' in entrypoint
    assert '"camera.driveway_entrance": "camera.front_yard"' in entrypoint
    assert '"camera.rear_entrance_path_360": "camera.top_vineyard_360"' in entrypoint
    assert '"camera.entrance_road": "camera.mid_vineyard_north"' in entrypoint
