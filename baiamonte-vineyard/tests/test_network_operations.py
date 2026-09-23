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


def test_network_discovery_does_not_turn_missing_optional_telemetry_into_an_outage():
    states = [
        {"entity_id": "binary_sensor.router_main_port_3_lan_status", "state": "off", "attributes": {"friendly_name": "Router Main Port 3 LAN status"}},
        {"entity_id": "binary_sensor.router_main_port_6_online_detection", "state": "off", "attributes": {"friendly_name": "Main Router Port 6 online detection", "device_class": "connectivity"}},
        {"entity_id": "sensor.router_main_wan_status", "state": "unavailable", "attributes": {"friendly_name": "Router Main WAN status"}},
        {"entity_id": "device_tracker.starlink_device_location", "state": "unknown", "attributes": {"friendly_name": "Starlink device location"}},
    ]
    rows = {row["entity_id"]: row for row in network_operations_entities(states)}
    assert rows["binary_sensor.router_main_port_3_lan_status"]["category"] == "switching"
    assert rows["binary_sensor.router_main_port_3_lan_status"]["health"] == "neutral"
    assert rows["binary_sensor.router_main_port_6_online_detection"]["category"] == "switching"
    assert rows["binary_sensor.router_main_port_6_online_detection"]["health"] == "offline"
    assert rows["sensor.router_main_wan_status"]["health"] == "attention"
    assert rows["device_tracker.starlink_device_location"]["health"] == "neutral"


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


def test_camera_inventory_uses_shared_operational_names():
    rows = camera_health_inventory([{"entity_id": "camera.topvineyard", "state": "idle", "attributes": {"friendly_name": "Top Vineyard"}}])
    assert rows[0]["name"] == "Back Driveway Mid"


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


def test_network_payload_does_not_report_missing_optional_metric_as_incident():
    home_assistant = {
        "available": True,
        "network_entities": [
            {"entity_id": "binary_sensor.router_connected", "name": "Router connected", "category": "routing", "state": "on", "unit": "", "numeric_value": None, "health": "good", "available": True},
            {"entity_id": "sensor.router_wan_status", "name": "Router WAN status", "category": "routing", "state": "unavailable", "unit": "", "numeric_value": None, "health": "attention", "available": True},
        ],
        "camera_health": [], "network_equipment": [], "lte_status": {},
    }
    status = {"services": [{"code": "database", "name": "Database", "state": "green", "detail": "Connected"}]}
    payload = build_network_operations_payload(home_assistant, status, [], [])
    assert payload["overall"] == "amber"  # Other network layers are not instrumented.
    assert payload["kpis"]["critical_offline"] == 0
    assert payload["incidents"] == []


def test_admin_network_page_is_dedicated_and_responsive():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/network-operations.js").read_text()
    app_javascript = (ROOT / "app/static/app.js").read_text()
    css = (ROOT / "app/static/assets/network-operations.css").read_text()
    assert 'data-view="admin-network"' in html
    assert 'id="view-admin-network"' in html
    assert 'href="assets/assets/network-operations.css?v=__ASSET_VERSION__"' in html
    assert 'src="assets/assets/network-operations.js?v=__ASSET_VERSION__"' in html
    assert "api/v1/admin/network" in javascript
    assert "Not instrumented" in javascript
    assert "if(view==='admin-network')window.loadAdminNetwork?.()" in app_javascript
    assert "if($('view-admin-network')?.classList.contains('active'))load()" in javascript
    assert "function renderError(error)" in javascript
    assert "@media(max-width:650px)" in css


def test_overview_uses_compact_time_and_homebase_cards():
    dashboard = (ROOT / "dashboards/vineyard-overview.yaml").read_text()
    top = dashboard.split("- type: entities", 1)[0]
    assert "type: markdown" in top
    assert "Rome time" in top
    assert "type: tile" in top
    assert "name: HomeBase Pro" in top
    assert "type: alarm-modes" in top
    assert "armed_home" in top
    assert "type: clock" not in top
    assert "type: alarm-panel" not in top
