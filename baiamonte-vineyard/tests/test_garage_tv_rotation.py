from scripts.garage_tv_rotation import garage_rotation_update


def options(main="camera.a,camera.b,camera.c,camera.d,camera.e,camera.east_360"):
    return {
        "tv_camera_pages_configured": True,
        "tv_camera_page_1_enabled": True,
        "tv_camera_page_2_enabled": True,
        "tv_camera_page_3_enabled": True,
        "tv_camera_page_1_entities": "camera.gate",
        "tv_camera_page_2_entities": "camera.east_360,camera.vineyard",
        "tv_camera_page_3_entities": main,
    }


def test_garage_replaces_only_duplicate_east_360():
    saved = options()
    result = garage_rotation_update(saved, "camera.garage")
    assert result == {
        "tv_camera_page_3_entities": "camera.a,camera.b,camera.c,camera.d,camera.e,camera.garage",
        "tv_camera_entities": (
            "camera.gate,camera.east_360,camera.vineyard,"
            "camera.a,camera.b,camera.c,camera.d,camera.e,camera.garage"
        ),
    }
    assert saved["tv_camera_page_3_entities"].endswith("camera.east_360")


def test_garage_uses_a_free_slot_and_preserves_full_unique_pages():
    assert garage_rotation_update(options("camera.a"), "camera.garage")[
        "tv_camera_page_3_entities"
    ] == "camera.a,camera.garage"
    assert garage_rotation_update(options("camera.garage"), "camera.garage") == {}
    assert garage_rotation_update(
        options("camera.a,camera.b,camera.c,camera.d,camera.e,camera.f"), "camera.garage"
    ) is None
    assert garage_rotation_update(
        {**options(), "tv_camera_page_2_enabled": False}, "camera.garage"
    ) is None
