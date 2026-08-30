from pathlib import Path

from app.domains import utility_routes
from app.ha_entities import estate_utility_entities


ROOT = Path(__file__).resolve().parents[1]


def test_operations_has_dedicated_water_and_solar_workspaces():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/utilities.js").read_text()
    assert 'data-view="water"' in html
    assert 'data-view="solar"' in html
    assert 'id="view-water"' in html
    assert 'id="view-solar"' in html
    assert "loadWaterWorkspace" in javascript
    assert "loadSolarWorkspace" in javascript
    assert "missing telemetry is never interpreted as zero" in javascript


def test_utility_entity_inventory_is_safe_and_separated():
    states = [
        {"entity_id": "sensor.cistern_pressure", "state": "2.4", "last_updated": "now", "attributes": {"friendly_name": "Cistern Pressure", "unit_of_measurement": "bar"}},
        {"entity_id": "sensor.growatt_battery_soc", "state": "76", "last_updated": "now", "attributes": {"friendly_name": "Growatt Battery SOC", "unit_of_measurement": "%", "secret": "not public"}},
        {"entity_id": "sensor.david_s_iphone_battery_level", "state": "100", "last_updated": "now", "attributes": {"friendly_name": "David's iPhone Battery Level", "unit_of_measurement": "%"}},
        {"entity_id": "switch.solar_wall_light_cam_camera_enabled", "state": "on", "last_updated": "now", "attributes": {"friendly_name": "BBQ Front Camera enabled"}},
        {"entity_id": "camera.cistern", "state": "streaming", "attributes": {"friendly_name": "Cistern"}},
    ]
    water = estate_utility_entities(states, "water")
    solar = estate_utility_entities(states, "solar")
    assert [row["entity_id"] for row in water] == ["sensor.cistern_pressure"]
    assert [row["entity_id"] for row in solar] == ["sensor.growatt_battery_soc"]
    assert "secret" not in solar[0]


def test_energy_learning_never_enables_control_without_approved_loads(monkeypatch):
    monkeypatch.setattr(utility_routes, "fetch_all", lambda *_: [
        {"observed_at": "2026-08-29T22:00:00", "estate_load_w": 500, "battery_soc_pct": 80}
        for _ in range(15)
    ])
    settings = {"battery_capacity_kwh": 10.24, "reserve_floor_pct": 30, "critical_floor_pct": 20,
                "automatic_control_enabled": True, "approved_controllable_loads": []}
    result = utility_routes._energy_learning({"battery_soc_pct": 80, "estate_load_w": 500, "battery_power_w": 100}, settings)
    assert result["learned_night_load_w"] == 500
    assert result["control_eligible"] is False
    assert result["control_enabled"] is False
    assert result["estimated_hours_above_reserve"] > 10


def test_solcast_estimate_is_not_stored_as_actual_pv():
    status = {"solar": {"current_power": {"value": 900, "unit": "W", "source": "Solcast estimate"}}, "solar_entities": []}
    assert utility_routes._energy_snapshot(status)["pv_power_w"] is None


def test_personal_device_battery_is_never_estate_storage():
    status = {"solar": {}, "solar_entities": estate_utility_entities([
        {"entity_id": "sensor.david_s_iphone_battery_level", "state": "100", "attributes": {"friendly_name": "David's iPhone Battery Level", "unit_of_measurement": "%"}},
    ], "solar")}
    assert utility_routes._energy_snapshot(status)["battery_soc_pct"] is None


def test_energy_process_is_scheduled_and_database_backed():
    process = (ROOT / "app/process_control.py").read_text()
    backend = (ROOT / "app/intelligence.py").read_text()
    migration = (ROOT / "db/migrations/132_estate_energy_learning.sql").read_text()
    assert '"energy": {"enabled": True, "interval_minutes": 5}' in process
    assert '"energy": ("estate-energy-learning", refresh_estate_energy_learning)' in backend
    assert "estate_energy_observations" in migration
    assert "automatic_control_enabled',FALSE" in migration
