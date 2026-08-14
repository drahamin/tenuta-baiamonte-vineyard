import json

from app.ha_entities import find_lte_status, find_network_equipment, home_assistant_inventory, solar_energy_summary


def sensor(entity_id, state, unit="", **attributes):
    return {
        "entity_id": entity_id,
        "state": str(state),
        "attributes": {"unit_of_measurement": unit, "friendly_name": entity_id.split(".", 1)[-1], **attributes},
    }


def test_solar_summary_keeps_actual_and_forecast_sources_separate():
    states = [
        sensor("sensor.growatt_kcm7fyd01d_pv1_watts", 400, "W"),
        sensor("sensor.growatt_kcm7fyd01d_pv2_watts", 600, "W"),
        sensor("sensor.growatt_kcm7fyd01d_pv1_kwh_today", 1.2, "kWh"),
        sensor("sensor.growatt_kcm7fyd01d_pv2_kwh_today", 0.8, "kWh"),
        sensor("sensor.solcast_pv_forecast_power_now", 850, "W"),
        sensor(
            "sensor.solcast_pv_forecast_forecast_today",
            6.5,
            "kWh",
            estimate10=4.8,
            estimate90=8.2,
            analysis={"confidence": 0.76},
            detailedHourly=[{"period_start": "2026-08-14T10:00:00+02:00", "pv_estimate10": 0.3, "pv_estimate": 0.5, "pv_estimate90": 0.8}],
        ),
        sensor("sensor.solcast_pv_forecast_forecast_remaining_today", 4.0, "kWh", estimate10=2.9, estimate90=5.3),
        sensor("sensor.solcast_pv_forecast_forecast_tomorrow", 7.1, "kWh", estimate10=5.0, estimate90=9.4),
    ]

    result = solar_energy_summary(states)

    assert result["current_power"]["value"] == 1000
    assert result["current_power"]["source"] == "Growatt live"
    assert result["energy_today"]["value"] == 2
    assert result["forecast_energy_today"]["value"] == 6.5
    assert result["forecast_points"] == [{"observed_at": "2026-08-14T10:00:00+02:00", "power_w": 500.0, "low_w": 300.0, "high_w": 800.0}]
    assert result["forecast_energy_remaining"]["value"] == 4.0
    assert result["forecast_energy_tomorrow"]["value"] == 7.1
    assert result["forecast_range_today"] == {
        "low": 4.8,
        "likely": 6.5,
        "high": 8.2,
        "spread": 3.4,
        "confidence_percent": 76.0,
        "unit": "kWh",
        "basis": "Solcast P10 / P50 / P90",
    }
    assert result["actual_source"] == "Growatt"
    assert result["forecast_source"] == "Solcast"


def test_solar_summary_uses_solcast_now_only_as_fallback():
    result = solar_energy_summary([sensor("sensor.solcast_pv_forecast_power_now", 725, "W")])

    assert result["current_power"]["value"] == 725
    assert result["current_power"]["source"] == "Solcast estimate"
    assert result["actual_source"] is None
    assert result["forecast_source"] == "Solcast"


def test_solar_summary_finds_renamed_solcast_entities():
    result = solar_energy_summary([
        sensor("sensor.baiamonte_solcast_power_now", 510, "W", friendly_name="Baiamonte Solcast Power Now"),
        sensor("sensor.baiamonte_solcast_forecast_today", 5.4, "kWh", friendly_name="Baiamonte Solcast Forecast Today", estimate10=3.7, estimate90=7.0),
    ])

    assert result["current_power"]["value"] == 510
    assert result["forecast_energy_today"]["value"] == 5.4
    assert result["forecast_range_today"]["low"] == 3.7
    assert result["forecast_range_today"]["high"] == 7.0


def test_inventory_reports_dashboard_gaps_and_unavailable_entities(tmp_path):
    storage = tmp_path / ".storage"
    dashboards = tmp_path / "baiamonte_dashboards"
    storage.mkdir()
    dashboards.mkdir()
    (storage / "core.entity_registry").write_text(json.dumps({"data": {"entities": [
        {"entity_id": "sensor.growatt_power", "disabled_by": None},
        {"entity_id": "camera.cistern", "disabled_by": None},
    ]}}))
    (storage / "core.device_registry").write_text(json.dumps({"data": {"devices": [
        {"id": "one", "disabled_by": None, "manufacturer": "Growatt"},
    ]}}))
    (dashboards / "overview.yaml").write_text("- entity: sensor.growatt_power\n- entity: sensor.missing\n")
    states = [sensor("sensor.growatt_power", 500, "W"), sensor("camera.cistern", "unavailable")]

    result = home_assistant_inventory(states, tmp_path)

    assert result["device_count"] == 1
    assert result["entity_count"] == 2
    assert result["available_entities"] == 1
    assert result["unavailable_entities"] == 1
    assert result["missing_dashboard_references"] == ["sensor.missing"]


def test_network_health_does_not_treat_problem_off_or_unused_port_as_failure():
    states = [
        sensor("binary_sensor.miami_multimode_gateway_problem", "off", device_class="problem"),
        sensor("binary_sensor.router_main_port_1_internet_link", "on", device_class="connectivity"),
        sensor("binary_sensor.router_main_port_3_lan_status", "off"),
    ]

    result = find_network_equipment(states)

    assert not any("miami" in item["code"] for item in result)
    assert next(item for item in result if "internet_link" in item["code"])["state"] == "green"
    assert not any("port_3" in item["code"] for item in result)

    configured = find_network_equipment(states, "binary_sensor.router_main_port_3_lan_status")
    assert next(item for item in configured if "port_3" in item["code"])["state"] == "off"


def test_lte_prefers_live_internet_link_over_unavailable_wan_status():
    states = [
        sensor("binary_sensor.router_main_wan_status", "unavailable", device_class="connectivity"),
        sensor("binary_sensor.router_main_port_1_internet_link", "on", device_class="connectivity"),
    ]

    result = find_lte_status(states)

    assert result["state"] == "green"
    assert result["code"] == "lte"
    assert "internet_link" in result["detail"]


def test_network_health_omits_stale_discoveries_but_keeps_explicit_one():
    states = [sensor("binary_sensor.router_main_wan_status", "unavailable", device_class="connectivity")]

    assert find_network_equipment(states) == []
    configured = find_network_equipment(states, "binary_sensor.router_main_wan_status")
    assert configured[0]["state"] == "red"
