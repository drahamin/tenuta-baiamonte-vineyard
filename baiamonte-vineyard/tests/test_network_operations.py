from pathlib import Path

from app.domains.network_operations import build_network_operations_payload
from app.ha_entities import camera_health_inventory, network_operations_entities


ROOT = Path(__file__).resolve().parents[1]


def test_network_discovery_is_categorized_and_does_not_expose_attributes():
    states = [
        {"entity_id": "binary_sensor.starlink_connected", "state": "on", "attributes": {"friendly_name": "Starlink connected", "device_class": "connectivity", "password": "secret"}},
        {"entity_id": "sensor.main_router_latency", "state": "18", "attributes": {"friendly_name": "Main Router Latency", "unit_of_measurement": "ms"}},
        {"entity_id": "switch.kitchen_refrigerator", "state": "on", "attributes": {"friendly_name": "Kitchen refrigerator"}},
    ]
    rows = network_operations_entities(states)
    assert [row["category"] for row in rows] == ["routing", "wan"]
    assert all("attributes" not in row and "password" not in row for row in rows)
    assert next(row for row in rows if row["category"] == "wan")["health"] == "good"


def test_camera_inventory_includes_every_camera_and_safe_nearby_telemetry():
    states = [
        {"entity_id": "camera.cistern", "state": "streaming", "attributes": {"friendly_name": "Cistern", "access_token": "hidden"}},
        {"entity_id": "sensor.cistern_wifi_rssi", "state": "-61", "attributes": {"unit_of_measurement": "dBm"}},
        {"entity_id": "camera.rear_gate", "state": "unavailable", "attributes": {"friendly_name": "Rear Gate"}},
    ]
    rows = camera_health_inventory(states)
    assert len(rows) == 2
    assert rows[0]["telemetry"]["signal"] == {"value": "-61", "unit": "dBm"}
    assert rows[1]["health"] == "offline"
    assert all("attributes" not in row for row in rows)


def test_network_payload_reports_real_metrics_and_instrumentation_gaps():
    home_assistant = {
        "available": True,
        "network_entities": [
            {"entity_id": "sensor.starlink_latency", "name": "Starlink latency", "category": "wan", "state": "22", "unit": "ms", "numeric_value": 22.0, "health": "good", "available": True},
            {"entity_id": "binary_sensor.router_connected", "name": "Router connected", "category": "routing", "state": "off", "unit": "", "numeric_value": None, "health": "offline", "available": False},
        ],
        "camera_health": [{"entity_id": "camera.gate", "name": "Gate", "state": "streaming", "health": "good", "available": True}],
        "network_equipment": [],
        "lte_status": {"code": "lte", "name": "LTE", "state": "green", "detail": "connected"},
    }
    status = {"services": [
        {"code": "database", "name": "Database", "state": "green", "detail": "Connected"},
        {"code": "publisher", "name": "Public feed", "state": "green", "detail": "Current"},
    ]}
    payload = build_network_operations_payload(home_assistant, status, [], [])
    assert payload["overall"] == "red"
    assert payload["kpis"]["critical_offline"] == 1
    assert payload["metrics"][0]["kind"] == "latency"
    assert next(row for row in payload["categories"] if row["code"] == "switching")["instrumented"] is False
    assert any(row["code"] == "vineyard_api" for row in payload["endpoints"])


def test_admin_network_page_is_dedicated_and_responsive():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/network-operations.js").read_text()
    css = (ROOT / "app/static/assets/network-operations.css").read_text()
    assert 'data-view="admin-network"' in html
    assert 'id="view-admin-network"' in html
    assert "api/v1/admin/network" in javascript
    assert "Not instrumented" in javascript
    assert "@media(max-width:650px)" in css
