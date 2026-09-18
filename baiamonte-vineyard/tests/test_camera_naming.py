from pathlib import Path

from app.domains.camera_naming import canonical_camera_name


ROOT = Path(__file__).resolve().parents[1]


def test_operational_camera_names_override_legacy_names():
    assert canonical_camera_name("camera.vineyard_north", "Vineyard North") == "Main Parking"
    assert canonical_camera_name("camera.t8171t1025291b5f", "T8171T1025291B5F") == "Rear Gate 360"
    assert canonical_camera_name("camera.top_vineyard_360", "Top Vineyard 360") == "Rear Entrance Path 360"
    assert canonical_camera_name("camera.cistern_360", "Water Camera") == "Cistern 360"
    assert canonical_camera_name("camera.topvineyard", "Top Vineyard") == "Back Driveway Mid"
    assert canonical_camera_name("camera.rear_gate_360", "Rear Gate 360") == "Backyard"
    assert canonical_camera_name("camera.fox_ally", "Fox Ally") == "Fox Alley"
    assert canonical_camera_name("camera.indoor_cam", "Garage / Fox Den") == "Fox Den"


def test_unknown_camera_keeps_clean_home_assistant_name():
    assert canonical_camera_name("camera.garage", " Garage  /  Fox Den ") == "Garage / Fox Den"
    assert canonical_camera_name("camera.unlisted_room") == "unlisted room"


def test_vineyard_visual_fallback_uses_the_current_vineyard_north_entity():
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    capture = source.split("def _capture_vineyard_visual_frame", 1)[1].split("\ndef ", 1)[0]
    assert 'home_assistant_camera_snapshot("camera.vineyard_north_2")' in capture
