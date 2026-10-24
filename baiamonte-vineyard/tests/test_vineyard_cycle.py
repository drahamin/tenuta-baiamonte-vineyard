from datetime import date

from app.vineyard_cycle import vineyard_year_stage


def test_completed_current_vintage_advances_today_to_post_harvest():
    stage = vineyard_year_stage(
        today=date(2026, 10, 24),
        vintage_year=2026,
        harvested_kg=5916.38,
        varieties=[
            {"name": "Grecanico", "planned_kg": 1800, "harvested_kg": 1900, "last_pick_date": "2026-09-08"},
            {"name": "Grenache", "planned_kg": 500, "harvested_kg": 470, "last_pick_date": "2026-09-18"},
            {"name": "Nerello Mascalese", "planned_kg": 3000, "harvested_kg": 3546.38, "last_pick_date": "2026-10-05"},
        ],
    )
    assert stage["code"] == "post_harvest"
    assert stage["harvest_complete"] is True
    assert stage["next_stage"] == "Leaf fall & dormancy"
    assert stage["last_harvest_date"] == date(2026, 10, 5)


def test_unfinished_october_vintage_stays_in_harvest():
    stage = vineyard_year_stage(
        today=date(2026, 10, 2),
        vintage_year=2026,
        varieties=[
            {"name": "Grecanico", "planned_kg": 1800, "harvested_kg": 1900, "last_pick_date": "2026-09-08"},
            {"name": "Nerello Mascalese", "planned_kg": 3000, "harvested_kg": 0},
        ],
    )
    assert stage["code"] == "harvest"
    assert stage["harvest_complete"] is False


def test_historical_year_is_not_presented_as_todays_stage():
    stage = vineyard_year_stage(today=date(2026, 10, 24), vintage_year=2025, varieties=[])
    assert stage["code"] == "historical"
    assert "current year" in stage["next_stage"].lower()


def test_purchased_fruit_does_not_complete_an_unpicked_estate_variety():
    stage = vineyard_year_stage(
        today=date(2026, 10, 24),
        vintage_year=2026,
        varieties=[{"name": "Grenache", "planned_kg": 500, "harvested_kg": 470, "estate_harvested_kg": 0, "purchased_fruit_kg": 470}],
    )
    assert stage["harvest_complete"] is False
    assert stage["code"] == "harvest"
