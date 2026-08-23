from types import SimpleNamespace

from starlette.requests import Request

from app import main
from app.domains import alerts_intake_routes


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
