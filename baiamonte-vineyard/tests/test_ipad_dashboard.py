from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.dashboard_manager import (
    DASHBOARDS,
    home_assistant_user_ids,
    patch_configuration,
    restrict_views_to_user,
)


def test_ipad_dashboard_is_registered_and_idempotent() -> None:
    assert DASHBOARDS["vineyard-overview"]["icon"] == "mdi:view-dashboard-outline"
    assert DASHBOARDS["vineyard-overview"]["icon"] != "mdi:fruit-grapes"
    assert DASHBOARDS["vineyard-ipad"]["filename"] == "baiamonte_dashboards/ipad-panel.yaml"
    assert DASHBOARDS["vineyard-ipad"]["show_in_sidebar"] is False
    first, _ = patch_configuration("homeassistant:\n")
    second, _ = patch_configuration(first)
    assert first == second
    assert first.count("    vineyard-ipad:\n") == 1


def test_ipad_dashboard_has_expected_touch_sections() -> None:
    text = (ROOT / "dashboards" / "ipad-panel.yaml").read_text(encoding="utf-8")
    for path in ("home", "controls", "cameras", "security", "weather", "vineyard", "media-ai"):
        assert f"path: {path}" in text
    assert "sensor.baiamonte_total_output_power" in text
    assert "sensor.solcast_pv_forecast_power_now" in text
    assert "switch.wifi_din_rail_10a_lights_switch" in text
    assert "navigation_path: /0c04eef6_baiamonte_vineyard?view=intelligence" in text
    assert "finance" not in text.casefold()


def test_display_dashboard_stays_compact_and_has_no_placeholder_sensor_tiles() -> None:
    text = (ROOT / "dashboards" / "display-panel.yaml").read_text(encoding="utf-8")
    home = text.split("  - title: Lights", 1)[0]
    assert "type: weather-forecast" not in home
    assert "type: glance" in home
    assert "columns: 4" in home
    assert "columns: 3" in home
    assert "Quick control" not in home
    assert "sensor.baiamonte_open_tasks" not in home
    assert "sensor.baiamonte_alerts" not in home
    assert "sensor.baiamonte_disease_pressure" not in home
    for entity in (
        "sensor.baiamonte_total_output_power",
        "sensor.wifi_din_rail_switch_with_metering_power",
        "switch.wifi_din_rail_switch_with_metering_switch",
        "switch.wifi_din_rail_10a_cameras_switch",
        "switch.wifi_din_rail_10a_lights_switch",
        "switch.wifi_din_rail_10a_outlets_switch",
        "switch.wifi_din_rail_10a_nokia_lte_switch",
    ):
        assert entity in text
    assert "Building electrical panels" in text
    assert "Building service outlets" in text


def test_admin_dashboard_has_operational_and_device_control_centres() -> None:
    text = (ROOT / "dashboards" / "admin.yaml").read_text(encoding="utf-8")
    for path in ("system", "operations", "devices", "network", "power", "user-tracking", "security"):
        assert f"path: {path}" in text
    assert "Operations control" in text
    assert "Inventory report" in text
    assert "sensor.baiamonte_total_output_power" in text
    assert "binary_sensor.baiamonte_cistern_low_water" in text
    assert "Estate people map" in text
    assert "person.wendy_creque" in text
    assert "/0c04eef6_baiamonte_vineyard?view=admin&focus=labor" in text
    assert "/0c04eef6_baiamonte_vineyard?view=quick" in text
    assert "name: Full labor log" in text
    assert "tap_action:\n                  action: more-info" in text


def test_vineyard_overview_top_level_views_have_icons() -> None:
    text = (ROOT / "dashboards" / "vineyard-overview.yaml").read_text(encoding="utf-8")
    blocks = re.split(r"(?m)(?=^- title: )", text)[1:]
    visible_blocks = [block for block in blocks if "\n  subview: true" not in block]
    assert visible_blocks
    for block in visible_blocks:
        title = block.splitlines()[0].removeprefix("- title: ")
        assert re.search(r"(?m)^  icon: [^\s]+$", block), f"{title} needs a top-bar icon"


def test_camera_navigation_is_phone_readable_without_five_column_squeeze() -> None:
    text = (ROOT / "dashboards" / "vineyard-overview.yaml").read_text(encoding="utf-8")
    camera_navigation = text.split("title: Camera Navigation", 1)[1].split("title: Access & Arrival", 1)[0]
    assert "columns: 5" not in camera_navigation
    assert camera_navigation.count("columns: 6") == 2
    assert camera_navigation.count("columns: 4") == 3
    assert camera_navigation.count("rows: 2") == 5
    assert camera_navigation.count("vertical: true") == 2
    for label in ("Refresh", "HomeBase", "PTZ", "Health", "Wall"):
        assert f"name: {label}" in camera_navigation
    for long_label in ("Refresh Images", "Eufy HomeBase", "PTZ Cameras", "Camera Health", "Camera Wall"):
        assert f"name: {long_label}" not in camera_navigation


def test_home_assistant_user_ids_prefers_login_username(tmp_path: Path) -> None:
    auth = tmp_path / "auth"
    auth.write_text(
        '{"data":{"users":[{"id":"display-id","name":"Wall Display"}],'
        '"credentials":[{"user_id":"display-id","data":{"username":"display"}}]}}',
        encoding="utf-8",
    )
    assert home_assistant_user_ids(auth) == {
        "display": "display-id",
        "wall display": "display-id",
    }


def test_device_dashboard_views_are_restricted_to_matching_user() -> None:
    source = "title: Device\nviews:\n  - title: Home\n    path: home\n  - title: Power\n    path: power\n"
    routed = restrict_views_to_user(source, "user-123")
    assert routed.count("      - user: user-123\n") == 2
    assert routed.count("    visible:\n") == 2
