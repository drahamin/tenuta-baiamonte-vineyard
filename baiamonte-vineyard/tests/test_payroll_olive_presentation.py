import copy
import json
from pathlib import Path
import subprocess

import pytest

from app.domains.olives import calculate_cost_analysis


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "OWNER-RECON-OCT2026-20261102-"


def model():
    return {"cost_model_version": "workflow_v2", "record_year": 2026,
            "harvest_labor_hours": 70, "labor_hourly_rate_eur": 10,
            "harvest_labor_eur": 700, "equipment_allocation_eur": 120,
            "press_rate_eur_per_kg": .18, "package_500ml_count": 118,
            "package_3l_count": 10, "package_3l_unit_cost_eur": 4.27}


def evidence():
    return [{"source_record_id": PREFIX + "HARVEST", "record_year": 2026,
             "status": "owner_confirmed", "labor_hours": 70,
             "details": "Harvest total70h at EUR10/h = EUR700. Part-time EUR450 is separate; combined EUR1150."},
            {"source_record_id": PREFIX + "SHAKER-HIRE", "record_year": 2026,
             "status": "owner_confirmed", "details": "Additional shaker hire EUR120, separate from labor."}]


def analysis(cost_model=None, records=None):
    return calculate_cost_analysis({"olives_kg": 695, "oil_liters": 89.5},
                                   model() if cost_model is None else cost_model,
                                   evidence() if records is None else records)


def test_mixed_subtotal_is_evidence_backed_not_final_actual_or_paid():
    result = analysis()
    assert result["confirmed_cost_eur"] == 820
    assert result["estimated_cost_eur"] == 167.80
    assert result["unverified_cost_eur"] == 0
    assert result["known_cost_eur"] == 987.80
    assert result["is_final_actual_cost"] is False
    assert result["total_cost_eur"] is None
    assert len(result["missing_cost_inputs"]) == 6
    assert {line["label"] for line in result["cost_basis_lines"] if line["basis"] == "owner_confirmed"} == {"Harvest labor", "Equipment allocation"}
    assert not any("paid" in key or "payment" in key for key in result)


@pytest.mark.parametrize("change", ["missing", "duplicate", "status", "year", "amount", "hours", "rate"])
def test_confirmation_fails_closed_when_evidence_or_model_does_not_match(change):
    cost_model, records = model(), evidence()
    if change == "missing": records = []
    elif change == "duplicate": records += copy.deepcopy(records)
    elif change == "status":
        for row in records: row["status"] = "draft"
    elif change == "year":
        for row in records: row["record_year"] = 2025
    elif change == "amount": cost_model.update(harvest_labor_eur=10, equipment_allocation_eur=12)
    elif change == "hours": cost_model["harvest_labor_hours"] = 71
    elif change == "rate": cost_model["labor_hourly_rate_eur"] = 11
    result = analysis(cost_model, records)
    assert result["confirmed_cost_eur"] == (120 if change in {"hours", "rate"} else 0)
    assert result["is_final_actual_cost"] is False
    assert result["unverified_cost_eur"] > 0


def test_explicit_but_unsupported_invoice_is_not_automatically_confirmed():
    cost_model = {**model(), "mill_cost_eur": 150}
    result = analysis(cost_model)
    line = next(line for line in result["cost_basis_lines"] if line["label"] == "Mill / pressing")
    assert line["basis"] == "unverified_input"
    assert result["confirmed_cost_eur"] == 820
    assert result["estimated_cost_eur"] == 42.70
    assert result["unverified_cost_eur"] == 150


def test_complete_model_with_estimates_is_still_not_final_actual():
    cost_model = {**model(), **dict.fromkeys(["transport_cost_eur", "filtering_cost_eur",
                  "package_500ml_unit_cost_eur", "packaging_other_eur", "analysis_storage_eur", "other_cost_eur"], 0)}
    result = analysis(cost_model)
    assert result["cost_complete"] is True  # Input completeness is not evidence finality.
    assert result["is_final_actual_cost"] is False
    assert result["reconciliation_status"] == "partial"
    assert result["total_cost_eur"] is None
    assert result["cost_per_liter_eur"] is None
    assert result["cost_per_actual_bottle_eur"] is None


def test_zero_valued_unverified_lines_do_not_become_confirmed():
    cost_model = {**model(), **dict.fromkeys(["transport_cost_eur", "filtering_cost_eur",
                  "package_500ml_count", "package_3l_count", "package_500ml_unit_cost_eur",
                  "package_3l_unit_cost_eur", "packaging_other_eur", "analysis_storage_eur",
                  "other_cost_eur", "mill_cost_eur"], 0)}
    result = analysis(cost_model)
    assert result["cost_complete"] is True
    assert result["estimated_cost_eur"] == result["unverified_cost_eur"] == 0
    assert any(line["basis"] != "owner_confirmed" for line in result["cost_basis_lines"])
    assert result["is_final_actual_cost"] is False
    assert result["reconciliation_status"] == "partial"
    assert result["total_cost_eur"] is result["cost_per_liter_eur"] is result["cost_per_actual_bottle_eur"] is None


def run_js(script):
    return json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)


def test_actual_cost_basis_card_renders_split_and_truthful_labels():
    source = (ROOT / "app/static/assets/olives-planning.js").read_text()
    functions = source[source.index("function eurPrecise"):source.index("function renderOliveContractRates")]
    result = run_js(functions + "\nconst esc=String; console.log(JSON.stringify(oliveCostBasisCard(" + json.dumps(analysis()) + "))); ")
    assert "820.00" in result and "confirmed" in result
    assert "167.80" in result and "estimated" in result
    assert "Mixed subtotal — not final actual cost" in result
    assert "6 unknown inputs" in result
    assert "Equipment allocation" in result and "120.00" in result
    assert "Owner confirmation is not proof of payment" in result


def test_review_period_counts_drafts_without_turning_them_into_payables():
    source = (ROOT / "app/static/assets/owner-labor-review.js").read_text()
    functions = source[source.index("let payrollReviewPeriod"):source.index("function ownerLaborReviewCard")]
    owners = [{"id": "part", "person_or_crew": "Vincenzo (part-time)", "work_date": "2026-10-01"},
              {"id": "harvest", "person_or_crew": "Vincenzo (one-time olive harvest)", "work_date": "2026-10-27"},
              {"id": "giancarlo", "person_or_crew": "Giancarlo Pafumi", "work_date": "2026-10-01"}]
    data = {"owner_labor_reviews": owners, "worker_submissions": [
        {"id": "pending", "work_date": "2026-10-12", "approval_status": "submitted"},
        {"id": "nov", "work_date": "2026-11-02", "approval_status": "submitted"},
        {"id": "paid-ready", "work_date": "2026-09-03", "approval_status": "approved"}]}
    result = run_js(functions + "\nconst data=" + json.dumps(data) + ";console.log(JSON.stringify({oct:payrollReviewProjection(data,'2026-10'),nov:payrollReviewProjection(data,'2026-11'),all:payrollReviewProjection(data,'all'),default:payrollReviewProjection(data),data}));")
    assert result["oct"]["reviewCount"] == 4
    assert result["oct"]["ownerRows"] == owners
    assert result["nov"]["reviewCount"] == 1
    assert result["nov"]["ownerRows"] == []
    assert result["all"]["reviewCount"] == 5
    assert result["default"]["period"] == "2026-10"
    for period in ("oct", "nov", "all"):
        assert [row["id"] for row in result[period]["approvedRows"]] == ["paid-ready"]
    assert result["data"] == data  # No status or identity mutation.


def test_review_unknown_date_is_not_invented_as_a_shift():
    source = (ROOT / "app/static/assets/owner-labor-review.js").read_text()
    functions = source[source.index("let payrollReviewPeriod"):source.index("function ownerLaborReviewCard")]
    result = run_js(functions + "\nconsole.log(JSON.stringify(payrollReviewProjection({owner_labor_reviews:[{id:'unknown',work_date:null}]},'unknown')));")
    assert result["reviewCount"] == 1
    assert result["ownerRows"][0]["work_date"] is None
