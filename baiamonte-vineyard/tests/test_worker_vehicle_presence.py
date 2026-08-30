from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.domains.worker_vehicle_presence import _inside_capture_window, vehicle_presence_summary


ROME = ZoneInfo("Europe/Rome")


def test_giancarlo_schedule_bounds_capture_but_unscheduled_workers_are_observation_only():
    giancarlo = {
        "normal_work_days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "normal_start_time": "07:00",
        "normal_end_time": "14:00",
    }
    assert _inside_capture_window(giancarlo, datetime(2026, 8, 31, 6, 0, tzinfo=ROME))
    assert not _inside_capture_window(giancarlo, datetime(2026, 8, 30, 9, 0, tzinfo=ROME))
    assert _inside_capture_window({}, datetime(2026, 8, 30, 23, 0, tzinfo=ROME))


@patch("app.domains.worker_vehicle_presence.estate_id", return_value="estate-1")
@patch("app.domains.worker_vehicle_presence.fetch_all")
def test_presence_summary_compares_retained_sightings_without_claiming_worked_hours(fetch_all, _estate):
    fetch_all.side_effect = [
        [
            {"observed_at": datetime(2026, 8, 29, 5, 5), "presence_status": "present", "confidence_pct": 90},
            {"observed_at": datetime(2026, 8, 29, 12, 0), "presence_status": "present", "confidence_pct": 86},
        ],
        [{"work_date": "2026-08-29", "hours": 7}],
    ]
    result = vehicle_presence_summary("person.giancarlo", ("Giancarlo Pafumi", "giancarlo"))
    day = result["history"][0]
    assert day["present_observations"] == 2
    assert day["timesheet_hours"] == 7
    assert day["reconciliation"] == "consistent"
    assert "do not identify the driver" in result["note"]


def test_worker_vehicle_migration_seeds_all_known_vehicles():
    migration = open("db/migrations/130_worker_vehicle_presence.sql", encoding="utf-8").read()
    assert "Volkswagen','model','Golf" in migration
    assert "Fiat','model','Punto" in migration
    assert "Renault','model','Kangoo" in migration
    assert "Fiat','model','Panda" in migration
    assert "frame_sha256" in migration
