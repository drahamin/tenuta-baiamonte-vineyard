from pathlib import Path

from app.domains.people_roles import natural_person_first_name


ROOT = Path(__file__).resolve().parents[1]


def test_human_greeting_requires_full_real_name():
    assert natural_person_first_name("Rahamin Rahamin") == "Rahamin"
    assert natural_person_first_name("Sebastiano Vinci") == "Sebastiano"
    assert natural_person_first_name("admin") is None
    assert natural_person_first_name("Tablet 1") is None
    assert natural_person_first_name("MQTT Service") is None


def test_ui_has_resilient_docs_refresh_uptime_and_device_health():
    app = (ROOT / "app/static/app.js").read_text()
    cellar = (ROOT / "app/static/assets/cellar.js").read_text()
    css = (ROOT / "app/static/app.css").read_text()
    labels = (ROOT / "app/tank_labels.py").read_text()
    assert "systemDocsLoadPromise" in app
    assert "current.textContent='Refresh'" in app
    assert "renderTodayGreeting" in app and "Europe/Rome" in app
    assert "adminUptimeValue" in app and "adminRuntimeObservedAt" in app
    assert "device-health" in cellar and "device-health" in css
    assert "last_seen_seconds" in labels and "connection_status" in labels
