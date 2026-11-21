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
