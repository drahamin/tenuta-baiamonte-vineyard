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


def test_direct_felicity_bank_has_priority_and_exposes_both_packs():
    rows = [
        {"entity_id": "sensor.old_battery_soc", "name": "Battery SOC", "state": "91", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_soc", "name": "Baiamonte Battery Bank SOC", "state": "28", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Baiamonte Battery Bank Power", "state": "190", "unit": "W", "available": True},
        {"entity_id": "binary_sensor.baiamonte_can_bank_all_batteries_online", "name": "Bank online", "state": "on", "unit": "", "available": True},
        {"entity_id": "sensor.baiamonte_can_battery_1_battery_soc", "name": "Battery 1 SOC", "state": "31", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_battery_2_battery_soc", "name": "Battery 2 SOC", "state": "25", "unit": "%", "available": True},
    ]
    status = {"solar": {}, "solar_entities": rows}
    snapshot = utility_routes._energy_snapshot(status)
    bank = utility_routes._battery_bank(rows)
    assert snapshot["battery_soc_pct"] == 28
    assert snapshot["battery_power_w"] == 190
    assert bank["connected"] is True
    assert [pack["soc_pct"] for pack in bank["packs"]] == [31, 25]


def test_total_load_uses_meter_then_calculates_from_energy_balance():
    base = [
        {"entity_id": "sensor.total_dc_input_power", "name": "Solar DC", "state": "1200", "unit": "W", "available": True},
        {"entity_id": "sensor.generator_main_breaker_phase_a_power", "name": "Generator", "state": "1800", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Battery", "state": "-1900", "unit": "W", "available": True},
    ]
    calculated = utility_routes._energy_snapshot({"solar": {}, "solar_entities": base})
    assert calculated["estate_load_w"] == 1100
    assert calculated["load_method"] == "calculated"
    assert calculated["load_confidence"] == "medium"
    metered = utility_routes._energy_snapshot({"solar": {}, "solar_entities": base + [
        {"entity_id": "sensor.wifi_din_rail_40a_main_power", "name": "Estate main", "state": "950", "unit": "W", "available": True},
    ]})
    assert metered["estate_load_w"] == 950
    assert metered["load_method"] == "measured"
    assert metered["calculated_load_w"] == 1100


def test_overnight_readiness_exposes_native_ha_forecast():
    rows = [
        {"entity_id": "sensor.baiamonte_overnight_readiness", "state": "Add 2.5 kWh", "available": True},
        {"entity_id": "sensor.baiamonte_overnight_coverage", "state": "62.4", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_overnight_energy_requirement", "state": "3.4", "unit": "kWh", "available": True},
        {"entity_id": "sensor.baiamonte_overnight_target_energy", "state": "6.472", "unit": "kWh", "available": True},
        {"entity_id": "sensor.baiamonte_energy_needed_until_sunrise", "state": "2.5", "unit": "kWh", "available": True},
        {"entity_id": "sensor.baiamonte_required_net_charging_power", "state": "625", "unit": "W", "available": True},
    ]
    result = utility_routes._overnight_readiness(rows)
    assert result == {"status": "Add 2.5 kWh", "coverage_pct": 62.4,
                      "energy_required_kwh": 3.4, "target_energy_kwh": 6.472,
                      "energy_needed_kwh": 2.5, "required_net_charge_w": 625,
                      "ready": False}


def test_core_energy_meters_are_kept_even_with_generic_device_names():
    rows = estate_utility_entities([
        {"entity_id": "sensor.total_dc_input_power", "state": "1500", "attributes": {"friendly_name": "Total DC Input Power", "unit_of_measurement": "W"}},
        {"entity_id": "sensor.wifi_din_rail_40a_main_power", "state": "800", "attributes": {"friendly_name": "WiFi DIN Rail 40A Main Power", "unit_of_measurement": "W"}},
    ], "solar")
    assert {row["entity_id"] for row in rows} == {"sensor.total_dc_input_power", "sensor.wifi_din_rail_40a_main_power"}


def test_direct_bms_entities_are_not_truncated_by_large_energy_inventory():
    states = [
        {"entity_id": f"sensor.baiamonte_can_battery_1_cell_{index}_voltage", "state": "3.2", "attributes": {"friendly_name": f"Felicity Battery 1 Cell {index} Voltage", "unit_of_measurement": "V"}}
        for index in range(1, 101)
    ]
    states.append({"entity_id": "sensor.baiamonte_can_battery_2_battery_soc", "state": "25", "attributes": {"friendly_name": "Felicity Battery 2 State of Charge", "unit_of_measurement": "%"}})
    rows = estate_utility_entities(states, "solar")
    assert rows[0]["entity_id"] == "sensor.baiamonte_can_battery_2_battery_soc"


def test_overnight_forecast_is_not_truncated_by_large_bms_inventory():
    states = [
        {"entity_id": f"sensor.baiamonte_can_battery_1_cell_{index}_voltage", "state": "3.2", "attributes": {"friendly_name": f"Felicity Battery 1 Cell {index} Voltage", "unit_of_measurement": "V"}}
        for index in range(1, 101)
    ]
    states.append({"entity_id": "sensor.baiamonte_overnight_coverage", "state": "82", "attributes": {"friendly_name": "Baiamonte Overnight Coverage", "unit_of_measurement": "%"}})
    rows = estate_utility_entities(states, "solar")
    assert rows[0]["entity_id"] == "sensor.baiamonte_overnight_coverage"


def test_energy_process_is_scheduled_and_database_backed():
    process = (ROOT / "app/process_control.py").read_text()
    backend = (ROOT / "app/intelligence.py").read_text()
    migration = (ROOT / "db/migrations/132_estate_energy_learning.sql").read_text()
    assert '"energy": {"enabled": True, "interval_minutes": 5}' in process
    assert '"energy": ("estate-energy-learning", refresh_estate_energy_learning)' in backend
    assert "estate_energy_observations" in migration
    assert "automatic_control_enabled',FALSE" in migration
