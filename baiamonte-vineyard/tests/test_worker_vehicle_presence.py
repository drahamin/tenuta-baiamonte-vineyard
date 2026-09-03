from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.domains.worker_vehicle_presence import (
    _camera_zone,
    _inside_capture_window,
    _match_person_label,
    _profiles_for_capture,
    _priority_cameras,
    _profile_cameras,
    _tracked_profiles,
    vehicle_presence_summary,
)
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


def test_admin_forced_scan_includes_giancarlo_outside_the_schedule():
    tracked = [{"person_entity": "person.giancarlo", "normal_work_days": ["mon"], "normal_start_time": "07:00", "normal_end_time": "14:00"}]
    sunday = datetime(2026, 8, 30, 18, 0, tzinfo=ROME)
    assert _profiles_for_capture(tracked, force=False, event_trigger=None, now=sunday) == []
    assert _profiles_for_capture(tracked, force=True, event_trigger=None, now=sunday) == tracked


@patch("app.domains.worker_vehicle_presence.estate_id", return_value="estate-1")
@patch("app.domains.worker_vehicle_presence.fetch_all")
def test_presence_summary_compares_retained_sightings_without_claiming_worked_hours(fetch_all, _estate):
    fetch_all.side_effect = [
        [
            {"observed_at": datetime(2026, 8, 29, 5, 5), "presence_status": "present", "confidence_pct": 90},
            {"observed_at": datetime(2026, 8, 29, 12, 0), "presence_status": "present", "confidence_pct": 86},
        ],
        [],
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
            "entity_id": "camera.gate_doorbell_2", "name": "Gate Doorbell", "event_image_available": True,
            "event_image_entity_id": "image.gate_doorbell_event_image_2",
            "detections": {"ringing": {"active": True, "last_changed": "2026-08-29T10:01:00Z"}},
        },
        {
            "entity_id": "camera.main_parking", "name": "Main Parking", "event_image_available": True,
            "event_image_entity_id": "image.main_parking_camera",
            "person_name": "Giancarlo",
            "detections": {
                "recognized person": {"active": True, "last_changed": "2026-08-29T10:02:00Z"},
                "vehicle": {"active": True, "last_changed": "2026-08-29T10:02:00Z"},
            },
        },
        {
            "entity_id": "camera.front_gate", "name": "Front Gate", "event_image_available": False,
            "detections": {"vehicle": {"active": True, "last_changed": "2026-08-29T10:03:00Z"}},
        },
    ]}
    triggers = _worker_vehicle_event_triggers(payload)
    assert [row["camera_entity_id"] for row in triggers] == ["camera.rear_gate", "camera.gate_doorbell_2", "camera.main_parking"]
    assert triggers[0]["event_types"] == ["motion"]
    assert triggers[1]["event_types"] == ["ringing"]
    assert triggers[2]["edge_vehicle_detected"] is True
    assert triggers[2]["person_name"] == "Giancarlo"


def test_vehicle_alerts_are_screened_anywhere_but_generic_motion_needs_a_relevant_view():
    payload = {"cameras": [
        {
            "entity_id": "camera.remote_lane", "name": "Remote Lane", "event_image_available": True,
            "event_image_entity_id": "image.remote_lane", "detections": {
                "vehicle": {"active": True, "last_changed": "2026-08-29T10:00:00Z"},
            },
        },
        {
            "entity_id": "camera.wired_barn", "name": "Wired Barn", "event_image_available": True,
            "event_image_entity_id": "image.wired_barn", "detections": {
                "motion": {"active": True, "last_changed": "2026-08-29T10:01:00Z"},
            },
        },
        {
            "entity_id": "camera.kitchen", "name": "Kitchen", "event_image_available": True,
            "event_image_entity_id": "image.kitchen", "detections": {
                "motion": {"active": True, "last_changed": "2026-08-29T10:02:00Z"},
            },
        },
    ]}
    triggers = _worker_vehicle_event_triggers(payload, {"camera.wired_barn"})
    assert [row["camera_entity_id"] for row in triggers] == ["camera.remote_lane", "camera.wired_barn"]


def test_vehicle_event_check_migration_deduplicates_frames_without_retaining_images():
    migration = open("db/migrations/131_worker_vehicle_event_checks.sql", encoding="utf-8").read()
    assert "UNIQUE KEY uq_worker_vehicle_event_frame" in migration
    assert "frame_sha256" in migration
    assert "BLOB" not in migration


def test_wired_and_eufy_cameras_share_one_bounded_profile_list():
    profile = {
        "vehicle_camera_entity": "camera.main_parking",
        "vehicle_camera_entities": ["camera.main_parking", "camera.wired_gate", "not_a_camera"],
    }
    assert _profile_cameras(profile) == ["camera.main_parking", "camera.wired_gate"]
    assert _camera_zone("camera.wired_gate", "Rear Gate Wired") == "rear_gate"
    assert _camera_zone("camera.parking_overview") == "main_parking"
    assert _camera_zone("camera.vineyard_north") == "main_parking"


def test_primary_and_battery_overrides_are_prioritized_for_scheduled_analysis():
    profiles = [{
        "vehicle_camera_entity": "camera.main_parking",
        "vehicle_camera_entities": ["camera.wired_gate"],
        "vehicle_always_analyze_camera_entities": ["camera.battery_drive"],
    }]
    assert _priority_cameras(profiles) == ["camera.main_parking", "camera.battery_drive"]


@patch("app.domains.worker_vehicle_presence.people_profiles", return_value={
    "person.luca_schiliro_cognato": {
        "vehicle_tracking_enabled": True,
        "vehicle_model": "Kangoo", "vehicle_color": "white",
    },
})
def test_vehicle_analyzer_keeps_default_candidates_when_only_one_profile_was_saved(_profiles):
    tracked = {row["person_entity"]: row for row in _tracked_profiles()}
    assert tracked["person.giancarlo"]["vehicle_model"] == "Golf"
    assert tracked["person.giancarlo"]["vehicle_color"] == "silver"
    assert tracked["person.carmela"]["vehicle_model"] == "Punto"
    assert tracked["person.luca_schiliro_cognato"]["vehicle_model"] == "Kangoo"


@patch("app.domains.worker_vehicle_presence.people_profiles", return_value={
    "person.giancarlo": {"vehicle_tracking_enabled": False},
})
def test_explicit_vehicle_tracking_disable_overrides_default(_profiles):
    assert "person.giancarlo" not in {row["person_entity"] for row in _tracked_profiles()}


def test_eufy_familiar_person_label_requires_one_unambiguous_profile():
    profiles = [
        {"person_entity": "person.giancarlo", "name": "Giancarlo Pafumi"},
        {"person_entity": "person.luca", "name": "Luca Schiliro Cognato"},
    ]
    assert _match_person_label("Giancarlo", profiles) == "person.giancarlo"
    assert _match_person_label("Unknown visitor", profiles) is None
    assert _match_person_label("Luca", [*profiles, {"person_entity": "person.luca_two", "name": "Luca Rossi"}]) is None


def test_location_learning_schema_keeps_metadata_not_biometrics_or_images():
    migration = open("db/migrations/133_worker_location_learning.sql", encoding="utf-8").read()
    assert "worker_person_observations" in migration
    assert "observation_zone" in migration
    assert "review_status" in migration
    assert "BLOB" not in migration
    assert "face_embedding" not in migration
