from app.intelligence import _camera_health_evidence_trusted


def test_disconnected_bridge_suppresses_per_camera_outage_alerts():
    payload = {
        "summary": {"total": 12, "offline": 12},
        "integration": {"bridge_online": False},
    }

    assert _camera_health_evidence_trusted(payload) is False


def test_connected_bridge_allows_real_camera_outage_alerts():
    assert _camera_health_evidence_trusted(
        {"integration": {"bridge_online": True}}
    ) is True


def test_legacy_inventory_without_bridge_sensor_remains_supported():
    assert _camera_health_evidence_trusted({"integration": {}}) is True
