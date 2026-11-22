from scripts.solar_dashboard_alignment import LOCAL, OBSERVED, SOLCAST, align_storage_dashboard


def test_dashboard_alignment_updates_known_solar_views_and_retains_explicit_comparison():
    solar = {"path": "solar", "cards": [
        {"type": "entities", "title": "Solar Forecast", "entities": [{"entity": SOLCAST, "name": "Today"}]},
        {"type": "custom:apexcharts-card", "header": {"title": "Actual and estimated solar production"},
         "series": [{"entity": SOLCAST}, {"entity": "sensor.total_dc_input_power"}]},
        {"type": "entities", "title": "Solcast Health", "entities": [SOLCAST]},
    ]}
    unrelated = {"path": "network", "cards": [{"type": "entities", "entities": [SOLCAST]}]}
    original = {"views": [solar, {"path": "display-view-energy"}, unrelated]}
    updated = align_storage_dashboard(original)
    cards = updated["views"][0]["cards"]
    assert cards[0]["entities"] == [{"entity": LOCAL, "name": "Local forecast today"}]
    assert set(row["entity"] for row in cards[1]["series"]) == {OBSERVED, LOCAL, SOLCAST}
    assert all(row["unit"] == "W" for row in cards[1]["series"])
    assert cards[2] == solar["cards"][2]
    assert updated["views"][2] == unrelated
    assert align_storage_dashboard(updated) == updated


def test_garage_alignment_only_rebinds_named_cards_on_legacy_camera_page():
    from scripts.solar_dashboard_alignment import align_storage_garage_dashboard

    garage = {"type": "picture-glance", "title": "Garage", "camera_image": "camera.indoor_cam"}
    fox_den = {**garage, "title": "Fox Den"}
    config = {"views": [
        {"path": "new-cameras", "cards": [{"type": "grid", "cards": [garage, fox_den]}]},
        {"path": "another-view", "cards": [garage]},
    ]}
    aligned = align_storage_garage_dashboard(config)
    assert aligned["views"][0]["cards"][0]["cards"] == [
        {**garage, "camera_image": "camera.garage"}, fox_den,
    ]
    assert aligned["views"][1] == config["views"][1]
    assert align_storage_garage_dashboard(aligned) == aligned


def test_camera_locations_match_the_live_ha_device_bindings_and_are_idempotent():
    from scripts.solar_dashboard_alignment import align_storage_garage_dashboard
    cards = [
        {"type": "picture-glance", "title": "Back Driveway Mid", "camera_image": "camera.topvineyard"},
        {"type": "picture-glance", "title": "Backyard", "camera_image": "camera.rear_gate_360"},
        {"type": "picture-glance", "title": "Front Yard", "camera_image": "camera.front_yard"},
        {"type": "picture-glance", "title": "Inside Front Gate", "camera_image": "camera.front_gate"},
    ]
    original = {"views": [{"path": "new-cameras", "cards": cards}, {"path": "custom", "cards": cards}]}
    updated = align_storage_garage_dashboard(original)
    assert [card["camera_image"] for card in updated["views"][0]["cards"]] == [
        "camera.rear_gate_360", "camera.topvineyard", "camera.front_gate", "camera.front_yard"]
    assert updated["views"][1] == original["views"][1]
    assert align_storage_garage_dashboard(updated) == updated
