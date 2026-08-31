from app.domains.camera_naming import canonical_camera_name


def test_operational_camera_names_override_legacy_names():
    assert canonical_camera_name("camera.vineyard_north", "Vineyard North") == "Main Parking"
    assert canonical_camera_name("camera.t8171t1025291b5f", "T8171T1025291B5F") == "Rear Gate 360"
    assert canonical_camera_name("camera.top_vineyard_360", "Top Vineyard 360") == "Rear Entrance Path 360"
    assert canonical_camera_name("camera.cistern_360", "Water Camera") == "Cistern 360"


def test_unknown_camera_keeps_clean_home_assistant_name():
    assert canonical_camera_name("camera.garage", " Garage  /  Fox Den ") == "Garage / Fox Den"
    assert canonical_camera_name("camera.generator_room") == "generator room"
