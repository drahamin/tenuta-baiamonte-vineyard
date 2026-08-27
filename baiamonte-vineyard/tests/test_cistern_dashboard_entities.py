from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_cistern_dashboard_entities_are_recreated_after_core_restart():
    source = (ROOT / "custom_components" / "baiamonte_branding" / "__init__.py").read_text()
    assert "_async_refresh_cistern_entities" in source
    assert 'sensor.baiamonte_cistern_water_level' in source
    assert 'binary_sensor.baiamonte_cistern_low_water' in source
    assert "async_track_time_interval" in source


def test_vineyard_today_uses_supported_treatment_icon():
    dashboard = (ROOT / "dashboards" / "vineyard-overview.yaml").read_text()
    assert "icon: mdi:leaf-circle-outline\n" in dashboard
    assert "mdi:sprayer-variant" not in dashboard


def test_cistern_poll_uses_proven_lan_endpoint_not_startup_dns():
    source = (ROOT / "custom_components" / "baiamonte_branding" / "__init__.py").read_text()
    assert 'http://192.168.0.10:8099/api/v1/system/status' in source
    assert 'http://0c04eef6-baiamonte-vineyard:8099' not in source


def test_live_runtime_entities_count_as_dashboard_references():
    source = (ROOT / "app" / "ha_entities.py").read_text()
    assert "| set(state_map)" in source
