from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.domains import plaato


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_plaato_v2_normalizes_batch_device_history_and_health(monkeypatch):
    batches = [{
        "id": "batch-1", "name": "Nerello 2026", "fermenterId": "ferm-1", "devices": ["pro-1"],
        "OG": 1.090, "FG": 0.995, "ABV": 12.4, "attenuation": 83.2, "enabled": True,
        "latestReading": {"time": "2026-08-28T12:00:00Z", "density": {"specificGravity": 1.050, "plato": 12.4}, "temperature": {"celsius": 22.1}},
    }]
    devices = [{"id": "pro-1", "name": "PLAATO Pro 1", "barcode": "P-1", "batteryLevel": 87, "wifiStrength": 72, "firmwareVersion": "2.0"}]
    fermenters = [{"id": "ferm-1", "name": "Fermenter 1"}]
    readings = [
        {"time": "2026-08-28T10:00:00Z", "temperature": 21.9, "density": 1.052, "frequency": 1099},
        {"time": "2026-08-28T12:00:00Z", "temperature": 22.1, "density": 1.050, "frequency": 1101},
    ]

    def fake_urlopen(request, timeout=0):
        url = request.full_url
        assert request.headers.get("X-plaato-api-key") == "secret"
        if "/devices/pro-1/readings" in url:
            return _Response(readings)
        if url.endswith("/batches"):
            return _Response(batches)
        if url.endswith("/devices"):
            return _Response(devices)
        if url.endswith("/fermenters"):
            return _Response(fermenters)
        raise AssertionError(url)

    monkeypatch.setattr(plaato.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(plaato, "runtime_option", lambda name, fallback: fallback)
    monkeypatch.setattr(plaato, "_age_minutes", lambda value: 10.0)
    plaato._CACHE.update({"at": 0.0, "payload": None, "key": None})
    settings = Settings(plaato_api_key="secret", plaato_tank_mappings="T-01|batch-1")
    result = plaato.fetch_plaato_snapshot(settings)
    reading = result["tanks"]["t-01"]
    assert result["connected"] is True
    assert reading["density_sg"] == 1.05
    assert reading["temperature_c"] == 22.1
    assert reading["plato"] == 12.4
    assert reading["fermentation_rate_msg_h"] == 1.0
    assert reading["battery_pct"] == 87
    assert reading["wifi_pct"] == 72
    assert reading["projection"]["phase"] == "active fermentation"
    assert reading["projection"]["progress_pct"] == 42.1
    assert reading["projection"]["estimated_hours_remaining"] == 55.0
    assert reading["projection"]["reading_count"] == 2


def test_projection_requires_a_real_final_gravity_target_for_eta():
    rows = [
        {"time": "2026-08-28T10:00:00Z", "temperature_c": 21.0, "density_sg": 1.052},
        {"time": "2026-08-28T12:00:00Z", "temperature_c": 22.0, "density_sg": 1.050},
    ]
    result = plaato._fermentation_projection(rows, 1.090, None, "2026-08-25T12:00:00Z", 10)
    assert result["estimated_finish_at"] is None
    assert result["estimated_hours_remaining"] is None
    assert result["progress_pct"] is None
    assert result["temperature_min_c"] == 21.0
    assert result["temperature_max_c"] == 22.0


def test_demo_key_generates_complete_local_plaato_stream_without_network(monkeypatch):
    monkeypatch.setattr(plaato, "runtime_option", lambda name, fallback: fallback)
    monkeypatch.setattr(plaato.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("demo must not use network")))
    settings = Settings(plaato_api_key="demo")
    snapshot = plaato.fetch_plaato_snapshot(settings)
    tanks = [{"id": "tank-1", "code": "T-01", "name": "Fermenter 1", "volume_l": 900, "variety_summary": "Nerello Mascalese"}]
    plaato.apply_plaato_readings(tanks, snapshot)
    reading = tanks[0]["plaato"]
    assert snapshot["demo"] is True
    assert reading["demo"] is True
    assert reading["connected"] is True
    assert len(reading["history"]) >= 160
    assert reading["temperature_c"] is not None
    assert reading["density_sg"] < reading["original_gravity"]
    assert reading["projection"]["progress_pct"] is not None
    assert reading["projection"]["estimated_finish_at"] is not None
    assert tanks[0]["volume_l"] == 900


def test_demo_key_allows_automatic_mode_without_a_mapping(monkeypatch):
    monkeypatch.setattr(plaato, "runtime_option", lambda name, fallback: fallback)
    assert plaato.plaato_tank_keys(Settings(plaato_api_key="demo", plaato_tank_mappings="")) == {"*"}


def test_plaato_overlay_never_uses_batch_volume_as_tank_level():
    tank = {"code": "T-01", "capacity_l": 5000, "volume_l": 900, "level_pct": 18, "temp_c": 19}
    snapshot = {"tanks": {"t-01": {"connected": True, "status": "live", "temperature_c": 22.1, "density_sg": 1.05, "batch_volume": 1000}}}
    plaato.apply_plaato_readings([tank], snapshot)
    assert tank["temp_c"] == 22.1
    assert tank["density_sg"] == 1.05
    assert tank["volume_l"] == 900
    assert tank["level_pct"] == 18


def test_auto_mode_requires_protected_mapping(monkeypatch):
    from app.domains import cellar

    tank = {"id": "tank-1", "code": "T-01", "name": "Fermenter 1", "container_type": "fermenter", "capacity_l": 1200}
    monkeypatch.setattr(cellar, "fetch_one", lambda *args, **kwargs: {"volume_l": 0})
    try:
        cellar.update_tank_details(tank, {"reading_mode": "auto", "capacity_l": 1200}, "tester", set(), set())
    except ValueError as error:
        assert "Tank Sensor mappings" in str(error)
    else:
        raise AssertionError("auto mode accepted without a protected Tank Sensor mapping")


def test_tank_click_opens_complete_tank_sensor_process():
    html = (ROOT / "app/static/index.html").read_text()
    cellar_js = (ROOT / "app/static/assets/cellar.js").read_text()
    dashboard_js = (ROOT / "app/static/app.js").read_text()
    assert 'id="tankProcessDialog"' in html
    assert "openTankProcessPanel" in cellar_js
    assert "Complete Tank Sensor process" in cellar_js
    assert "All Tank Sensor samples in this 7-day window" in cellar_js
    assert "forward projection" in cellar_js
    assert "Vintage & grape history" in cellar_js
    assert "Open fermentation process" not in cellar_js
    assert "bindTankProcessCards($('cellarTanks'),tanks)" in dashboard_js
    assert 'data-open-process="${esc(row.id)}"' in cellar_js
