from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.domains.treatments import (
    existing_treatment_safety_audits,
    field_review_guidance,
    inventory_readiness,
    mixture_signature,
    simulated_prediction,
    treatment_record_evidence_gaps,
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


def test_hail_field_review_uses_counts_and_optional_repeat_photos():
    result = field_review_guidance("hail_wound_followup", event_type="hail")
    assert result["minimum_photo_set"] == 0
    assert result["recommended_photo_set"] == 6
    assert result["photos_optional"] is True
    assert any("24–72" in item for item in result["photos"])
    assert any("count damaged and total" in item.lower() for item in result["measurements"])
    assert "Photos are optional" in result["ai_accuracy_rule"]


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
        patch("app.domains.treatments.fetch_all", side_effect=[items, equipment, [], harvest]),
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


def test_cancelled_treatment_is_retained_but_excluded_from_active_safety_counts():
    rows = [{"id": "cancelled-1", "status": "cancelled", "application_date": "2026-06-26"}]
    with (
        patch("app.domains.treatments.fetch_all", side_effect=[[], [], [], []]),
        patch("app.domains.treatments.treatment_inventory_reconciliation", return_value={"complete": True, "issues": []}),
    ):
        result = existing_treatment_safety_audits(rows, 2026)
    assert result["summary"]["records"] == 1
    assert result["summary"]["active_records"] == 0
    assert result["summary"]["inactive"] == 1
    assert result["summary"]["attention"] == 0
    assert result["rows"]["cancelled-1"]["status"] == "inactive"
    assert result["rows"]["cancelled-1"]["checks"] == []


def test_olive_phi_uses_the_supplied_olive_harvest_not_grape_forecasts():
    rows = [{
        "id": "olive-1", "status": "completed", "application_date": "2026-09-01",
        "label_legal_confirmed": 1, "actual_details_confirmed": 1, "phi_checked": 1,
    }]
    items = [{
        "application_id": "olive-1", "item_id": "i1", "product_id": "p1", "product_name": "A",
        "dose_amount": 1, "total_used": 1, "dose_unit": "L/ha", "phi_days": 30,
        "verification_status": "verified", "estate_authorization_status": "confirmed", "label_verified_on": date(2026, 8, 1),
    }]
    with (
        patch("app.domains.treatments.fetch_all", side_effect=[items, [], []]),
        patch("app.domains.treatments.treatment_inventory_reconciliation", return_value={"complete": True, "issues": []}),
    ):
        result = existing_treatment_safety_audits(rows, 2026, crop_scope="olives", harvest_date="2026-10-20")
    phi = next(check for check in result["rows"]["olive-1"]["checks"] if check["code"] == "phi")
    assert phi["earliest_harvest"] == date(2026, 10, 20)
    assert phi["status"] == "verified"


def test_exact_mixture_approval_is_bound_to_current_products_rates_and_totals():
    rows = [{
        "id": "treatment-2", "status": "completed", "application_date": "2026-05-19",
        "label_legal_confirmed": 1, "actual_details_confirmed": 1, "phi_checked": 1,
    }]
    items = [
        {"application_id": "treatment-2", "item_id": "i1", "product_id": "p1", "product_name": "A", "dose_amount": 100, "total_used": 400, "dose_unit": "g/100 L", "phi_days": 10, "verification_status": "verified", "estate_authorization_status": "confirmed", "label_verified_on": date(2026, 8, 1)},
        {"application_id": "treatment-2", "item_id": "i2", "product_id": "p2", "product_name": "B", "dose_amount": 50, "total_used": 200, "dose_unit": "ml/100 L", "phi_days": 7, "verification_status": "verified", "estate_authorization_status": "confirmed", "label_verified_on": date(2026, 8, 1)},
    ]
    equipment = [{"application_id": "treatment-2", "calibration_status": "verified", "nozzle_setup": "cone", "flow_l_min": 4, "operating_pressure_bar": 8, "travel_speed_kph": 3, "carrier_rate_l_ha": 500}]
    approvals = [{
        "application_id": "treatment-2", "mixture_signature": mixture_signature(items), "status": "verified",
        "jar_test_status": "passed", "current_labels_confirmed": 1, "exact_combination_confirmed": 1,
        "compatibility_basis": "Current labels and Agronomist review", "sequence_notes": "A then B under agitation",
        "approved_by": "agronomist", "approved_at": "2026-08-21 09:00:00",
    }]
    with (
        patch("app.domains.treatments.fetch_all", side_effect=[items, equipment, approvals, [{"first_pick_date": date(2026, 10, 1)}]]),
        patch("app.domains.treatments.treatment_inventory_reconciliation", return_value={"complete": True, "issues": []}),
    ):
        result = existing_treatment_safety_audits(rows, 2026)
    mixture = next(check for check in result["rows"]["treatment-2"]["checks"] if check["code"] == "mixture")
    assert mixture["status"] == "verified"
    assert result["rows"]["treatment-2"]["status"] == "verified"


def test_treatment_reliability_repairs_are_database_backed_and_crop_selection_persists():
    migration = (ROOT / "db/migrations/083_treatment_audit_reliability.sql").read_text()
    routes = (ROOT / "app/domains/treatment_routes.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    javascript = (ROOT / "app/static/app.js").read_text()
    tools = (ROOT / "app/static/assets/treatment-tools.js").read_text()

    assert "CREATE TABLE IF NOT EXISTS treatment_mixture_approvals" in migration
    assert "i.total_used/1000" in migration
    assert '/api/v1/treatments/{treatment_id}/mixture-approval' in routes
    assert "_latest_treatment_hail_followup(year, crop_scope)" in main
    assert "vineyard_damage_assessments" in (ROOT / "app/domains/treatments.py").read_text()
    assert '"completed": len(completed_rows)' in main
    assert "baiamonte-treatment-crop" in javascript
    assert "treatmentScopedPath" in javascript
    assert "Review exact mixture" in tools


def test_missing_numbered_treatment_is_a_source_gap_not_a_fake_completed_record():
    rows = [
        {"purpose": "Treatment 2", "status": "completed"},
        {"purpose": "Treatment 3", "status": "completed"},
        {"purpose": "Treatment 4", "status": "completed"},
        {"purpose": "Treatment 5", "status": "cancelled"},
    ]
    assert treatment_record_evidence_gaps(rows, "vineyard") == [{
        "code": "missing_vineyard_treatment_1",
        "treatment_number": 1,
        "title": "Treatment 1 record needed",
        "status": "source_required",
        "detail": "Do not mark this treatment completed until an authoritative field record supplies the date, products, rates, water, scope and actual quantities used.",
    }]


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
