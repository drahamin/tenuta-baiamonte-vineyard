from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.domains.treatments import (
    existing_treatment_safety_audits,
    field_review_guidance,
    inventory_readiness,
    simulated_prediction,
)


ROOT = Path(__file__).resolve().parents[1]


def test_hail_scenario_routes_to_botrytis_review_without_saving_field_fact():
    result = simulated_prediction({
        "crop_scope": "vineyard",
        "target_code": "hail_wound_followup",
        "severity": "moderate",
        "event_type": "hail",
        "growth_stage": "veraison",
        "scenario_date": "2026-08-21",
    })
    assert result["type"] == "scenario_simulation"
    assert result["target_code"] == "botrytis"
    assert result["scenario_target_code"] == "hail_wound_followup"
    assert result["requires_agronomist_approval"] is True
    assert result["window_start"] >= date(2026, 8, 21)


def test_hail_field_review_requires_representative_counts_and_repeat_photos():
    result = field_review_guidance("hail_wound_followup", event_type="hail")
    assert result["minimum_photo_set"] == 6
    assert any("24–72" in item for item in result["photos"])
    assert any("count damaged and total" in item.lower() for item in result["measurements"])
    assert "whole-estate percentage requires" in result["ai_accuracy_rule"]


def test_inventory_unknowns_block_prediction_readiness():
    result = inventory_readiness({
        "inventory_reconciliation": {"complete": False},
        "needed_list": [],
        "stock_review_list": [{"description": "unknown invoice line"}],
        "mixture": {"components": []},
    })
    assert result["status"] == "blocked"
    assert "reconcile" in result["message"]


def test_existing_treatment_audit_keeps_all_five_unknown_or_conflicting_flags_visible():
    rows = [{
        "id": "treatment-1", "status": "completed", "application_date": "2026-08-15",
        "label_legal_confirmed": 0, "actual_details_confirmed": 0, "phi_checked": 1,
    }]
    items = [
        {"application_id": "treatment-1", "item_id": "i1", "product_name": "A", "total_used": None, "dose_unit": "kg/ha", "phi_days": 10, "verification_status": "needs_container_label", "estate_authorization_status": "not_confirmed", "label_verified_on": None},
        {"application_id": "treatment-1", "item_id": "i2", "product_name": "B", "total_used": 1, "dose_unit": "kg/ha", "phi_days": 7, "verification_status": "verified", "estate_authorization_status": "confirmed", "label_verified_on": date(2026, 8, 1)},
    ]
    equipment = [{"application_id": "treatment-1", "equipment_name": "Sprayer", "calibration_status": "needs_measurement"}]
    harvest = [{"first_pick_date": date(2026, 8, 20)}]
    reconciliation = {"complete": False, "issues": [{"application_id": "treatment-1", "reason": "Exact total used is not recorded"}]}
    with (
        patch("app.domains.treatments.fetch_all", side_effect=[items, equipment, harvest]),
        patch("app.domains.treatments.treatment_inventory_reconciliation", return_value=reconciliation),
    ):
        result = existing_treatment_safety_audits(rows, 2026)
    audit = result["rows"]["treatment-1"]
    checks = {row["code"]: row for row in audit["checks"]}
    assert checks["label"]["status"] == "unverified"
    assert checks["completed_use"]["status"] == "unknown"
    assert checks["sprayer_calibration"]["status"] == "missing"
    assert checks["phi"]["status"] == "conflict"
    assert checks["mixture"]["status"] == "unverified"
    assert audit["safe_for_prediction_reuse"] is False
    assert audit["status"] == "blocked"


def test_treatment_tools_are_exposed_in_dashboard_and_are_not_automatic_orders():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "app/static/assets/treatment-tools.js").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/treatment_routes.py").read_text(encoding="utf-8")
    assert 'id="treatmentSimulatorForm"' in html
    assert 'id="treatmentFieldReviewForm"' in html
    assert "api/v1/treatments/simulate" in js
    assert "api/v1/treatments/field-review-requests" in js
    assert "Hypothetical decision support only" in routes
    assert "safe_for_prediction_reuse" in (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
