import json

from app.ha_entities import home_assistant_inventory, solar_energy_summary


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
            detailedHourly=[{"period_start": "2026-08-14T10:00:00+02:00", "pv_estimate": 0.5}],
        ),
    ]

    result = solar_energy_summary(states)

    assert result["current_power"]["value"] == 1000
    assert result["current_power"]["source"] == "Growatt live"
    assert result["energy_today"]["value"] == 2
    assert result["forecast_energy_today"]["value"] == 6.5
    assert result["forecast_points"] == [{"observed_at": "2026-08-14T10:00:00+02:00", "power_w": 500.0}]
    assert result["actual_source"] == "Growatt"
    assert result["forecast_source"] == "Solcast"


def test_solar_summary_uses_solcast_now_only_as_fallback():
    result = solar_energy_summary([sensor("sensor.solcast_pv_forecast_power_now", 725, "W")])

    assert result["current_power"]["value"] == 725
    assert result["current_power"]["source"] == "Solcast estimate"
    assert result["actual_source"] is None
    assert result["forecast_source"] == "Solcast"


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
