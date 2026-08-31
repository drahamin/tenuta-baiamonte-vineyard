from datetime import date
from unittest.mock import patch

from app.domains.security import _day_bounds, _plate, configured_security_camera_ids


def test_security_migration_keeps_camera_pipeline_movement_ledger_and_known_cars():
    migration = open("db/migrations/139_estate_security_vehicle_pipeline.sql", encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS estate_security_cameras" in migration
    assert "CREATE TABLE IF NOT EXISTS estate_vehicle_movements" in migration
    assert "CREATE TABLE IF NOT EXISTS estate_known_vehicles" in migration
    assert "license_plate" in migration
    assert "front_right_entry" in migration
    assert "camera.vineyard_north','Main Parking'" in migration


def test_plate_normalization_never_invents_characters():
    assert _plate(" ab-123 cd ") == "AB-123 CD"
    assert _plate("IT • XY 42!") == "IT  XY 42"
    assert _plate(None) is None


def test_security_day_uses_rome_bounds_converted_to_utc():
    start, end = _day_bounds(date(2026, 8, 31))
    assert start.isoformat().startswith("2026-08-30T22:00")
    assert end.isoformat().startswith("2026-08-31T21:59:59")


@patch("app.domains.security.security_camera_sources", return_value=[
    {"camera_entity_id": "camera.main_parking"},
    {"camera_entity_id": "camera.rear_gate_360"},
])
def test_configured_security_cameras_feed_event_trigger_selection(_sources):
    assert configured_security_camera_ids() == {"camera.main_parking", "camera.rear_gate_360"}


def test_admin_security_ui_has_stats_review_camera_and_known_car_controls():
    page = open("app/static/index.html", encoding="utf-8").read()
    script = open("app/static/assets/security.js", encoding="utf-8").read()
    assert 'data-view="admin-security"' in page
    assert 'id="securityKnownStats"' in page
    assert 'id="securityReviewList"' in page
    assert 'id="securityPrimaryKpis"' in page
    assert "Camera pipeline configuration" in page
    assert 'id="securityMovementDialog"' in page
    assert "known_observations" in script
    assert "View frame" in script
    assert "Confirm and learn" in page
    assert "always_analyze" in script
    assert "renderSecurityReviewQueue" in script


def test_camera_refresh_pipeline_runs_estate_security_in_parallel_with_attendance():
    source = open("app/intelligence.py", encoding="utf-8").read()
    assert "configured_security_camera_ids" in source
    assert "refresh_estate_vehicle_security" in source
    assert '"estate_security": estate_security' in source


def test_staff_vehicle_profiles_accept_an_optional_deliberately_recorded_plate():
    main = open("app/main.py", encoding="utf-8").read()
    people = open("app/static/assets/people.js", encoding="utf-8").read()
    assert '("make", "model", "type", "color", "plate", "notes")' in main
    assert "Plate · optional" in people
    assert "vehicle_${index}_plate" in people
