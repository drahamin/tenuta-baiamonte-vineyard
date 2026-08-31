from datetime import datetime
from unittest.mock import patch

from app.domains.water_delivery_tracking import (
    DEFAULT_WATER_DELIVERY_CAMERAS,
    NUNZIO_STANDARD_DELIVERY_L,
    _delivery_profiles,
    configured_water_delivery_cameras,
    water_delivery_summary,
)


def test_nunzio_water_delivery_defaults_use_the_three_live_route_cameras():
    assert NUNZIO_STANDARD_DELIVERY_L == 5000.0
    assert DEFAULT_WATER_DELIVERY_CAMERAS == [
        "camera.rear_gate", "camera.t8171t1025291b5f", "camera.top_vineyard_360", "camera.cistern_360",
    ]


@patch("app.domains.water_delivery_tracking.people_profiles", return_value={})
def test_nunzio_water_delivery_watch_is_enabled_by_default(_profiles):
    profile = _delivery_profiles()[0]
    assert profile["person_entity"] == "person.nunzio_testa"
    assert profile["water_delivery_camera_entities"] == DEFAULT_WATER_DELIVERY_CAMERAS
    assert configured_water_delivery_cameras() == set(DEFAULT_WATER_DELIVERY_CAMERAS)


@patch("app.domains.water_delivery_tracking.people_profiles", return_value={
    "person.nunzio_testa": {"water_delivery_tracking_enabled": False},
})
def test_water_delivery_watch_can_be_explicitly_disabled(_profiles):
    assert _delivery_profiles() == []


@patch("app.domains.water_delivery_tracking.estate_id", return_value="estate-1")
@patch("app.domains.water_delivery_tracking.fetch_all")
def test_water_delivery_summary_keeps_camera_and_level_evidence(fetch_all, _estate):
    fetch_all.side_effect = [
        [{"id": "delivery-1", "completed_at": datetime(2026, 8, 31, 9), "level_increase_pct": 24, "status": "confirmed"}],
        [{"id": 7, "camera_entity_id": "camera.cistern_360", "delivery_stage": "filling", "confidence_pct": 94}],
        [{"id": "job-1", "delivery_id": "WATER-DELIVERY-delivery-1", "provider_name": "Nunzio", "status": "verification_needed"}],
    ]
    result = water_delivery_summary("person.nunzio_testa")
    assert result["confirmed_deliveries"] == 1
    assert result["latest_delivery"]["level_increase_pct"] == 24
    assert result["recent_observations"][0]["delivery_stage"] == "filling"
    assert result["pending_payments"] == 1
    assert result["payment_queue"][0]["provider_name"] == "Nunzio"
    assert result["standard_delivery_l"] == 5000.0


def test_water_delivery_schema_requires_route_and_level_evidence():
    source = open("db/migrations/135_water_delivery_tracking.sql", encoding="utf-8").read()
    assert "water_delivery_observations" in source
    assert "water_deliveries" in source
    assert "level_increase_pct" in source
    assert "delivery_stage" in source
    assert "BLOB" not in source
    reconciliation = open("db/migrations/137_water_delivery_claim_reconciliation.sql", encoding="utf-8").read()
    assert "reported_by_username" in reconciliation
    assert "declared_amount_eur" in reconciliation
    volume = open("db/migrations/140_cistern_physical_volume_calibration.sql", encoding="utf-8").read()
    assert "delivery_volume_l" in volume
    assert "implied_cistern_capacity_l" in volume
    assert "5000.00" in volume


def test_confirmed_delivery_requires_two_cameras_and_level_change_before_payment_queue():
    source = open("app/domains/water_delivery_tracking.py", encoding="utf-8").read()
    assert "len(cameras) >= 2" in source
    assert "rise >= MIN_LEVEL_RISE_POINTS" in source
    assert "INSERT IGNORE INTO labor_entries" in source
    assert "'one_off_charge'" in source
    assert "'water_delivery'" in source
    assert "'verification_needed'" in source
    assert "never sends or marks money paid automatically" in source
    assert "submit_water_delivery_claim" in source
    assert "contractor_claim_reconciled" in source
    assert "physical_volume_calibration" in source
    assert "5,000 L" in source


def test_vehicle_prompt_stores_site_specific_direction_rules():
    source = open("app/domains/worker_vehicle_presence.py", encoding="utf-8").read()
    assert "front pointing RIGHT means ARRIVING" in source
    assert "front_right_arriving_front_left_leaving" in source
    delivery = open("app/domains/water_delivery_tracking.py", encoding="utf-8").read()
    assert "access/entry path is on the RIGHT side" in delivery
    assert "final approach view immediately before Cistern 360" in delivery
