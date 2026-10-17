from datetime import date
import io
from unittest.mock import patch

from PIL import Image

from app.domains.security import (
    _camera_configuration_audit,
    _day_bounds,
    _known_vehicle_identity_basis,
    _merge_plate_patterns,
    _plate_crop,
    _plate,
    _review_status_for_finding,
    configured_security_camera_ids,
)


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


def test_known_vehicle_identity_uses_stable_evidence_not_free_text_tags():
    golf = _known_vehicle_identity_basis(None, "person.giancarlo", "silver", "Volkswagen", "Golf", "hatchback")
    assert golf == "appearance:person.giancarlo|silver|volkswagen|golf|hatchback"
    assert _known_vehicle_identity_basis("AB123CD", "person.giancarlo", None, None, None, None) == "plate:AB123CD"
    assert _known_vehicle_identity_basis(None, "person.giancarlo", "white", "unknown", "unknown", "vehicle") is None


def test_plate_crop_uses_original_frame_and_enlarges_the_plate_region():
    source = Image.new("RGB", (1600, 900), "navy")
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", quality=95)

    cropped = _plate_crop(buffer.getvalue(), [400, 600, 600, 680])

    assert cropped is not None
    result = Image.open(io.BytesIO(cropped))
    assert result.width >= 1200
    assert result.height > 100
    assert _plate_crop(buffer.getvalue(), [500, 500, 500, 600]) is None


def test_plate_learning_combines_only_consistent_multi_frame_patterns():
    assert _merge_plate_patterns(["AB?23CD", "A?123CD"]) == "AB123CD"
    assert _merge_plate_patterns(["AB?23CD"]) is None
    assert _merge_plate_patterns(["AB?23CD", "AX123CD"]) is None
    assert _merge_plate_patterns(["AB?????", "??123CD"]) is None


def test_plate_learning_migration_retains_distinct_frame_evidence():
    migration = open("db/migrations/219_vehicle_plate_learning.sql", encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS estate_vehicle_plate_reads" in migration
    assert "frame_sha256 CHAR(64)" in migration
    assert "vehicle_identity_key VARCHAR(128)" in migration
    assert "UNIQUE KEY uq_estate_vehicle_plate_source" in migration


def test_only_routine_high_confidence_known_vehicles_clear_automatically():
    known = {"id": "vehicle-1", "flagged": False}
    assert _review_status_for_finding(known, "entry", 94) == "confirmed"
    assert _review_status_for_finding(known, "unknown", 99) == "unreviewed"
    assert _review_status_for_finding(known, "parked", 89.99) == "unreviewed"
    assert _review_status_for_finding({**known, "flagged": True}, "entry", 99) == "unreviewed"
    assert _review_status_for_finding(None, "entry", 99) == "unreviewed"


def test_security_day_uses_rome_bounds_converted_to_utc():
    start, end = _day_bounds(date(2026, 8, 31))
    assert start.isoformat().startswith("2026-08-30T22:00")
    assert end.isoformat().startswith("2026-08-31T21:59:59")


def test_security_camera_audit_reports_unavailable_and_renamed_sources():
    sources = [{"camera_entity_id": "camera.gate", "display_name": "Old Gate", "enabled": 1}]
    catalog = [{"entity_id": "camera.gate", "name": "Front Gate", "available": False}]
    audit = _camera_configuration_audit(sources, catalog)
    assert audit["status"] == "attention"
    assert len(audit["unavailable"]) == 1
    assert audit["name_drift"][0]["current_name"] == "Front Gate"


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
    assert "saveSecurityReview" in script
    assert "502|503|504" in script
    assert "cache:'no-store'" in script
    assert "securityActionStatus" in page
    assert "Analyze cameras" in page


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


def test_presence_coverage_migration_adds_front_gate_dedup_and_owner_vehicle_corrections():
    migration = open("db/migrations/217_presence_camera_coverage.sql", encoding="utf-8").read()
    assert "CREATE TABLE IF NOT EXISTS estate_vehicle_frame_checks" in migration
    assert "camera.gate_doorbell_2','Front Gate Doorbell'" in migration
    assert "Giancarlo · silver Volkswagen Golf" in migration
    assert "Nunzio · blue Fiat 160 truck" in migration
    assert "Historical rental · white Peugeot 4000 wagon" in migration


def test_giancarlo_duplicate_vehicle_correction_preserves_the_rental_history():
    migration = open("db/migrations/218_reconcile_giancarlo_vehicle_duplicate.sql", encoding="utf-8").read()
    assert "person_entity='person.giancarlo'" in migration
    assert "LOWER(COALESCE(vehicle_color,''))='white'" in migration
    assert "Historical rental · white Peugeot 4000 wagon" in migration
    assert "movement.staff_person_entity='person.david_rahamin'" in migration
    assert "SET active=0" in migration


def test_security_scheduler_uses_recurring_sources_and_frame_deduplication():
    source = open("app/domains/security.py", encoding="utf-8").read()
    assert "if not triggers:" in source
    assert "if bool(row.get(\"always_analyze\"))" in source
    assert "estate_vehicle_frame_checks" in source
    assert "Inactive vehicles are historical context only" in source
    assert "all_recurring=True" in source
    assert 'response.headers["Cache-Control"] = "private, no-store, max-age=0"' in source
