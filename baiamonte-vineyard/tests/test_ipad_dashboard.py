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
        "sensor.solcast_pv_forecast_power_now",
        "sensor.wifi_din_rail_40a_main_power",
        "switch.wifi_din_rail_40a_main",
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
    assert "sensor.solcast_pv_forecast_power_now" in text
    assert "binary_sensor.baiamonte_cistern_low_water" in text
    assert "Estate people map" in text
    assert "person.wendy_creque" in text
    assert "/0c04eef6_baiamonte_vineyard?view=admin&focus=labor" in text
    assert "/0c04eef6_baiamonte_vineyard?view=quick" in text
    assert "name: Full labor log" in text
    assert "tap_action:\n                  action: more-info" in text


def test_managed_dashboards_do_not_reference_retired_entities() -> None:
    retired = {
        "sensor.baiamonte_total_output_power",
        "sensor.baiamonte_total_energy_today",
        "sensor.baiamonte_total_lifetime_energy_output",
        "sensor.baiamonte_total_maximum_power",
        "sensor.blitzortung_lightning_distance",
        "sensor.rfbridge433_rssi",
        "binary_sensor.gate_doorbell_connected",
        "camera.gate_doorbell",
        "binary_sensor.gate_doorbell_motion_detected",
        "binary_sensor.gate_doorbell_person_detected",
        "binary_sensor.gate_doorbell_ringing",
        "image.gate_doorbell_event_image",
        "update.a0d7b954_uptime_kuma_uptime_kuma_version",
        "sensor.baiamonte_open_tasks",
        "sensor.baiamonte_alerts",
        "sensor.baiamonte_disease_pressure",
        "sensor.baiamonte_inbox_reviews",
        "sensor.wifi_din_rail_40a_main_daily_consumption",
        "sensor.wifi_din_rail_10a_cameras_power_2",
        "sensor.wifi_din_rail_10a_lights_power_3",
        "sensor.wifi_din_rail_10a_outlets_power_3",
        "sensor.wifi_din_rail_10a_nokia_lte_power_2",
        "sensor.bluetti_main_breaker_power",
    }
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "dashboards").glob("*.yaml"))
    assert not retired.intersection(combined.split())
    assert "camera.gate_doorbell_2" in combined
    assert "Front Gate Doorbell" in combined


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
    for label in ("Refresh", "HomeBase Pro", "PTZ", "Health", "Wall"):
        assert f"name: {label}" in camera_navigation
    for long_label in ("Refresh Images", "Eufy HomeBase", "PTZ Cameras", "Camera Health", "Camera Wall"):
        assert f"name: {long_label}" not in camera_navigation


def test_eufy_camera_cards_use_the_camera_frame_not_event_thumbnails() -> None:
    """The image entity is a low-resolution event thumbnail, not the app-style cover."""
    for path in (
        ROOT / "dashboards" / "vineyard-overview.yaml",
        ROOT.parent / "dashboard" / "tenuta-baiamonte-dashboard-integrated.yaml",
    ):
        text = path.read_text(encoding="utf-8")
        assert "image_entity:" not in text
        assert "camera_image: camera.vineyard_north" in text
        assert "camera_image: camera.rear_gate" in text


def test_camera_wall_overviews_do_not_start_background_live_streams() -> None:
    for path in (
        ROOT / "dashboards" / "vineyard-overview.yaml",
        ROOT.parent / "dashboard" / "tenuta-baiamonte-dashboard-integrated.yaml",
    ):
        text = path.read_text(encoding="utf-8")
        access = text.split("title: Access & Arrival", 1)[1].split("title: Estate & Service", 1)[0]
        camera_page = text.split("title: Camera Navigation", 1)[1].split("title: Camera Health", 1)[0]
        for entity in ("camera.front_yard", "camera.vineyard_north", "camera.kitchen", "camera.vineyard_north_2"):
            card = camera_page.split(f"camera_image: {entity}", 1)[1].split("- type: picture-glance", 1)[0]
            assert "camera_view: live" not in card
        rear_gate = access.split("camera_image: camera.rear_gate", 1)[1].split("- type: picture-glance", 1)[0]
        assert "camera_view: live" not in rear_gate


def test_solar_wall_light_cameras_use_snapshot_cards() -> None:
    for path in (
        ROOT / "dashboards" / "vineyard-overview.yaml",
        ROOT.parent / "dashboard" / "tenuta-baiamonte-dashboard-integrated.yaml",
    ):
        text = path.read_text(encoding="utf-8")
        for entity in ("camera.solar_wall_light_cam", "camera.solar_wall_light_cam_2"):
            blocks = text.split(f"camera_image: {entity}")[1:]
            assert blocks
            for block in blocks:
                assert "camera_view: live" not in block.split("- type: picture-glance", 1)[0]


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
