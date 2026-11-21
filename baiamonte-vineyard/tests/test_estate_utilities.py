from datetime import date, timedelta
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
    assert "solar_chart_actual" in javascript
    assert "Solcast P50" in javascript
    assert "compatible.local_forecast" in javascript
    assert "/operations/solar/chart" in javascript
    assert "solarChartTime" in html
    assert "Local estimate" in javascript
    assert "context.arc(x, y, 3" in javascript
    assert "Actual and estimated solar production" in html


def test_selected_solar_day_uses_saved_forecast_and_recorded_power(monkeypatch):
    selected = date(2026, 10, 25)  # Europe/Rome's 25-hour day
    saved = {"target_day": str(selected), "points": [{"power_w": 700}], "total_kwh": 7.0}
    calls = []

    def read(path, body=None):
        calls.append((path, body))
        if path.startswith("history/period/"):
            return [[{"attributes": saved}]]
        return {"service_response": {"statistics": {utility_routes.SOLAR_POWER_ENTITY: [
            {"start": "2026-10-25T09:00:00+00:00", "mean": 400},
            {"start": "2026-10-25T10:00:00+00:00", "mean": None},
        ]}}}

    monkeypatch.setattr(utility_routes, "_solar_ha", read)
    result = utility_routes.solar_chart(selected)
    assert result["start"] == "2026-10-25T00:00:00+02:00"
    assert result["end"] == "2026-10-26T00:00:00+01:00"
    assert result["local"]["total_kwh"] == 7.0
    assert result["solcast"] == {}
    assert result["actual"] == [{"observed_at": "2026-10-25T09:00:00+00:00", "power_w": 400}]
    assert calls[1][1]["period"] == "hour"


def test_tomorrow_plot_uses_next_forecast_without_production_history(monkeypatch):
    tomorrow = utility_routes.datetime.now(utility_routes.SOLAR_ZONE).date() + timedelta(days=1)
    forecast = {"target_day": tomorrow.isoformat(), "total_kwh": 8.4, "points": [{"power_w": 600}]}
    calls = []

    def read(path, _body=None):
        calls.append(path)
        return {"attributes": {"tomorrow": forecast}}

    monkeypatch.setattr(utility_routes, "_solar_ha", read)
    result = utility_routes.solar_chart(tomorrow)
    assert result["local"]["total_kwh"] == 8.4
    assert not result["actual"]
    assert calls == [f"states/{utility_routes.SOLAR_FORECAST_ENTITY}"]


def test_solar_accuracy_uses_previous_day_issues_and_compares_only_matched_days(monkeypatch):
    today = utility_routes.datetime.now(utility_routes.SOLAR_ZONE).date()
    days = [today - timedelta(days=n) for n in range(1, 17)]

    def timestamp(day):
        return utility_routes.datetime.combine(
            day, utility_routes.time(23), tzinfo=utility_routes.SOLAR_ZONE,
        ).isoformat()

    received = {str(day): {
        "issued_at": timestamp(day - timedelta(days=1)),
        "local_kwh": 8 if n < 7 else 11, "solcast_kwh": 5,
    } for n, day in enumerate(days[:14])}
    received[str(days[14])] = {"issued_at": timestamp(days[14]), "local_kwh": 6, "solcast_kwh": 5}
    calls = []

    def read(path, body=None):
        calls.append(path)
        if body is None:
            return {"attributes": {"forecasts": received}}
        assert body["period"] == "day"
        return {"service_response": {"statistics": {
            utility_routes.SOLAR_ENERGY_ENTITY: [{"start": timestamp(day), "change": 7} for day in days],
            utility_routes.SOLCAST_TOMORROW_ENTITY: [
                {"start": timestamp(days[14] - timedelta(days=1)), "state": 9},
            ],
        }}}

    monkeypatch.setattr(utility_routes, "_solar_ha", read)
    result = utility_routes.solar_accuracy()
    assert len(result["days"]) == 30
    assert result["matched_days"] == 14
    assert result["recent"]["local_mae_kwh"] == 1
    assert result["recent"]["solcast_mae_kwh"] == 2
    assert result["previous"]["local_mae_kwh"] == 4
    assert result["days"][14]["local_error_kwh"] is None
    assert result["days"][14]["solcast_error_kwh"] == 2
    assert result["days"][16]["recorded_kwh"] is None
    assert calls[1].endswith(utility_routes.SOLAR_ACCURACY_ARCHIVE)


def test_solar_chart_history_exposes_observed_power_with_honest_quality(monkeypatch):
    monkeypatch.setattr(utility_routes, "estate_id", lambda: 1)
    monkeypatch.setattr(utility_routes, "fetch_all", lambda *_: [
        {"observed_at": "2026-10-14 10:15:00", "pv_power_w": 1450.4,
         "evidence": '{"source":"estimated_power_balance","quality":"estimated"}'},
    ])

    points = utility_routes._solar_chart_history(
        utility_routes.datetime(2026, 10, 14, 12, 30, tzinfo=utility_routes.timezone.utc)
    )

    assert points == [{
        "observed_at": "2026-10-14T12:15:00+02:00",
        "power_w": 1450.4,
        "quality": "estimated",
        "source": "estimated_power_balance",
    }]


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


def test_water_entities_exclude_camera_controls_and_battery_flow():
    states = [
        {"entity_id": "sensor.baiamonte_can_bank_flow_direction", "state": "charging", "attributes": {"friendly_name": "Baiamonte Battery Bank Flow Direction"}},
        {"entity_id": "sensor.cistern_360_wifi_rssi", "state": "-28", "attributes": {"friendly_name": "Cistern 360 Wifi RSSI", "unit_of_measurement": "dBm"}},
        {"entity_id": "switch.cisterna_motion_detection", "state": "on", "attributes": {"friendly_name": "Cistern Internal Motion Detection"}},
        {"entity_id": "sensor.baiamonte_cistern_water_level", "state": "45", "attributes": {"friendly_name": "Baiamonte Cistern Water Level", "unit_of_measurement": "%"}},
        {"entity_id": "switch.cistern_outlet", "state": "off", "attributes": {"friendly_name": "Cistern Outlet"}},
        {"entity_id": "sensor.irrigation_pump_pressure", "state": "2.4", "attributes": {"friendly_name": "Irrigation Pump Pressure", "unit_of_measurement": "bar"}},
    ]

    assert [row["entity_id"] for row in estate_utility_entities(states, "water")] == [
        "sensor.baiamonte_cistern_water_level",
        "switch.cistern_outlet",
        "sensor.irrigation_pump_pressure",
    ]


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


def test_continuous_solar_estimate_populates_live_energy_flow():
    rows = [{
        "entity_id": "sensor.baiamonte_growatt_solar_input_power",
        "name": "Growatt Solar Input Power",
        "state": "2093.6",
        "unit": "W",
        "available": True,
        "source": "estimated_power_balance",
        "quality": "estimated",
    }]
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": rows})
    flow = utility_routes._energy_flow(snapshot, {})

    assert snapshot["pv_power_w"] == 2093.6
    assert snapshot["pv_quality"] == "estimated"
    assert flow[0]["value_w"] == 2093.6
    assert flow[0]["detail"] == "Estimated from live power balance"


def test_solar_workspace_names_the_offline_power_balance_fallback(monkeypatch):
    status = {"checked_at": "now", "solar": {}, "power": [], "solar_entities": [
        {"entity_id": "sensor.baiamonte_growatt_solar_input_power", "name": "Growatt Solar Input Power", "state": "1100", "unit": "W", "available": True, "source": "estimated_power_balance", "quality": "estimated"},
        {"entity_id": "sensor.wifi_din_rail_40a_main_power", "name": "Estate main", "state": "270", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Battery", "state": "-830", "unit": "W", "available": True},
    ]}
    monkeypatch.setattr(utility_routes, "system_status_payload", lambda: status)
    monkeypatch.setattr(utility_routes, "_record_energy", lambda *_: None)
    monkeypatch.setattr(utility_routes, "_energy_settings", lambda: {})
    monkeypatch.setattr(utility_routes, "_energy_learning", lambda *_: {})
    monkeypatch.setattr(utility_routes, "_solar_chart_history", lambda: [])

    result = utility_routes.solar_workspace()

    assert result["solar_chart_actual_label"] == "Reconstructed solar · load + battery charge"
    assert result["commissioning"][0] == {"name": "Solar power balance fallback", "ready": True}


def test_personal_device_battery_is_never_estate_storage():
    status = {"solar": {}, "solar_entities": estate_utility_entities([
        {"entity_id": "sensor.david_s_iphone_battery_level", "state": "100", "attributes": {"friendly_name": "David's iPhone Battery Level", "unit_of_measurement": "%"}},
    ], "solar")}
    assert utility_routes._energy_snapshot(status)["battery_soc_pct"] is None


def test_direct_felicity_bank_has_priority_and_exposes_provisioned_third_pack():
    rows = [
        {"entity_id": "sensor.old_battery_soc", "name": "Battery SOC", "state": "91", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_soc", "name": "Baiamonte Battery Bank SOC", "state": "28", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Baiamonte Battery Bank Power", "state": "190", "unit": "W", "available": True},
        {"entity_id": "binary_sensor.baiamonte_can_bank_all_batteries_online", "name": "Bank online", "state": "on", "unit": "", "available": True},
        {"entity_id": "sensor.baiamonte_can_battery_1_battery_soc", "name": "Battery 1 SOC", "state": "31", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_battery_2_battery_soc", "name": "Battery 2 SOC", "state": "25", "unit": "%", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_configured_batteries", "name": "Active batteries", "state": "2", "unit": "", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_provisioned_batteries", "name": "Provisioned batteries", "state": "3", "unit": "", "available": True},
        {"entity_id": "sensor.baiamonte_can_battery_3_provisioning_status", "name": "Battery 3 provisioning", "state": "awaiting_connection", "unit": "", "available": True},
    ]
    status = {"solar": {}, "solar_entities": rows}
    snapshot = utility_routes._energy_snapshot(status)
    bank = utility_routes._battery_bank(rows)
    assert snapshot["battery_soc_pct"] == 28
    assert snapshot["battery_power_w"] == 190
    assert bank["connected"] is True
    assert [pack["soc_pct"] for pack in bank["packs"]] == [31, 25, None]
    assert bank["active_count"] == 2
    assert bank["provisioned_count"] == 3
    assert bank["packs"][2]["provisioning_status"] == "awaiting_connection"


def test_total_load_uses_meter_then_calculates_from_energy_balance():
    base = [
        {"entity_id": "sensor.total_dc_input_power", "name": "Solar DC", "state": "1200", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_generator_input_power", "name": "Verified generator input", "state": "1800", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Battery", "state": "-1900", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_grid_import_power", "name": "Grid import", "state": "0", "unit": "W", "available": True},
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


def test_estate_breakers_are_never_counted_as_generator_input():
    rows = [
        {"entity_id": "sensor.bluetti_main_breaker_power", "name": "Separate Bluetti breaker", "state": "310", "unit": "W", "available": True},
        {"entity_id": "sensor.generator_main_breaker_phase_a_power", "name": "Inverter/output breaker", "state": "328", "unit": "W", "available": True},
    ]
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": rows})
    assert snapshot["generator_power_w"] == 0
    assert snapshot["generator_source"] == "stopped_no_verified_meter"


def test_missing_grid_meter_is_unknown_not_zero():
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": []})
    assert snapshot["grid_power_w"] is None
    assert snapshot["load_components"]["grid_w"] is None


def test_missing_grid_meter_prevents_power_balance_load_inference():
    rows = [
        {"entity_id": "sensor.baiamonte_growatt_solar_input_power", "name": "Growatt solar", "state": "1800", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Battery", "state": "-1500", "unit": "W", "available": True},
    ]
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": rows})
    assert snapshot["estate_load_w"] is None
    assert snapshot["calculated_load_w"] is None
    assert snapshot["load_method"] == "unavailable"


def test_verified_generator_only_meter_is_used_when_installed():
    rows = [
        {"entity_id": "sensor.baiamonte_generator_input_power", "name": "Verified generator input", "state": "1800", "unit": "W", "available": True},
        {"entity_id": "sensor.generator_main_breaker_phase_a_power", "name": "Inverter/output breaker", "state": "328", "unit": "W", "available": True},
    ]
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": rows})
    assert snapshot["generator_power_w"] == 1800
    assert snapshot["generator_source"] == "verified_meter"


def test_solar_is_estimated_from_load_and_charging_when_growatt_is_offline():
    rows = [
        {"entity_id": "sensor.wifi_din_rail_40a_main_power", "name": "Estate main", "state": "321.8", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_can_bank_power", "name": "Battery", "state": "-2224.5", "unit": "W", "available": True},
        {"entity_id": "sensor.baiamonte_grid_import_power", "name": "Grid import", "state": "0", "unit": "W", "available": True},
        {"entity_id": "sensor.generator_main_breaker_phase_a_power", "name": "Inverter/output breaker", "state": "328", "unit": "W", "available": True},
    ]
    snapshot = utility_routes._energy_snapshot({"solar": {}, "solar_entities": rows})
    assert snapshot["pv_power_w"] == 2546.3
    assert snapshot["pv_source"] == "estimated_power_balance"
    assert snapshot["pv_quality"] == "estimated"
    assert snapshot["generator_power_w"] == 0


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
