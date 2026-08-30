from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.domains.worker_vehicle_presence import _inside_capture_window, vehicle_presence_summary
from app.intelligence import _worker_vehicle_event_triggers


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


def test_gate_and_doorbell_events_with_images_trigger_vehicle_screening():
    payload = {"cameras": [
        {
            "entity_id": "camera.rear_gate", "name": "Rear Gate", "event_image_available": True,
            "event_image_entity_id": "image.rear_gate_camera",
            "detections": {"motion": {"active": True, "last_changed": "2026-08-29T10:00:00Z"}},
        },
        {
            "entity_id": "camera.gate_doorbell", "name": "Gate Doorbell", "event_image_available": True,
            "event_image_entity_id": "image.gate_doorbell_camera",
            "detections": {"ringing": {"active": True, "last_changed": "2026-08-29T10:01:00Z"}},
        },
        {
            "entity_id": "camera.main_parking", "name": "Main Parking", "event_image_available": True,
            "event_image_entity_id": "image.main_parking_camera",
            "detections": {"motion": {"active": True, "last_changed": "2026-08-29T10:02:00Z"}},
        },
        {
            "entity_id": "camera.front_gate", "name": "Front Gate", "event_image_available": False,
            "detections": {"vehicle": {"active": True, "last_changed": "2026-08-29T10:03:00Z"}},
        },
    ]}
    triggers = _worker_vehicle_event_triggers(payload)
    assert [row["camera_entity_id"] for row in triggers] == ["camera.rear_gate", "camera.gate_doorbell"]
    assert triggers[0]["event_types"] == ["motion"]
    assert triggers[1]["event_types"] == ["ringing"]


def test_vehicle_event_check_migration_deduplicates_frames_without_retaining_images():
    migration = open("db/migrations/131_worker_vehicle_event_checks.sql", encoding="utf-8").read()
    assert "UNIQUE KEY uq_worker_vehicle_event_frame" in migration
    assert "frame_sha256" in migration
    assert "BLOB" not in migration
