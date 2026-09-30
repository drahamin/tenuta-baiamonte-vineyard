from pathlib import Path

from app.domains.alerts_intake_routes import _classify_fermentation_report
from app.domains.laffort_catalog import lot_lab_evidence, lot_with_lab_measurements, working_dose_recommendation


ROOT = Path(__file__).resolve().parents[1]


def test_latest_fermentation_panel_is_classified_as_wine():
    results = [
        {"analyte_code": "total_alcohol"},
        {"analyte_code": "actual_alcohol"},
        {"analyte_code": "glucose_fructose"},
    ]
    assert _classify_fermentation_report("other", results) == "wine"
    assert _classify_fermentation_report("water", results) == "water"


def test_total_alcohol_drives_current_fermentation_recipe_and_keeps_correction(monkeypatch):
    rows = [
        {"sample_id": "new", "sample_name": "Nerello Mascalese", "sample_type": "wine", "lab_date": "2026-09-30", "sampled_at": None, "needs_review": 0, "wine_lot_id": "lot", "linked_wine_lot_ids": None, "variety_name": None, "analyte_code": "total_alcohol", "analyte_name": "Alcol Complessivo", "numeric_value": 12.52, "text_value": None, "unit": "% Vol.", "flag": None, "reported_analyte_code": "total_alcohol", "reported_analyte_name": "Alcol Complessivo", "reported_numeric_value": 12.52, "reported_unit": "% Vol.", "report_url": "report-new"},
        {"sample_id": "new", "sample_name": "Nerello Mascalese", "sample_type": "wine", "lab_date": "2026-09-30", "sampled_at": None, "needs_review": 0, "wine_lot_id": "lot", "linked_wine_lot_ids": None, "variety_name": None, "analyte_code": "potential_alcohol", "analyte_name": "Alcol Potenziale", "numeric_value": 6.06, "text_value": None, "unit": "% Vol.", "flag": None, "reported_analyte_code": "potential_alcohol", "reported_analyte_name": "Alcol Potenziale", "reported_numeric_value": 6.06, "reported_unit": "% Vol.", "report_url": "report-new"},
        {"sample_id": "new", "sample_name": "Nerello Mascalese", "sample_type": "wine", "lab_date": "2026-09-30", "sampled_at": None, "needs_review": 0, "wine_lot_id": "lot", "linked_wine_lot_ids": None, "variety_name": None, "analyte_code": "actual_alcohol", "analyte_name": "Alcol Svolto", "numeric_value": 6.46, "text_value": None, "unit": "% Vol.", "flag": None, "reported_analyte_code": "actual_alcohol", "reported_analyte_name": "Alcol Svolto", "reported_numeric_value": 6.46, "reported_unit": "% Vol.", "report_url": "report-new"},
        {"sample_id": "new", "sample_name": "Nerello Mascalese", "sample_type": "wine", "lab_date": "2026-09-30", "sampled_at": None, "needs_review": 0, "wine_lot_id": "lot", "linked_wine_lot_ids": None, "variety_name": None, "analyte_code": "glucose_fructose", "analyte_name": "Glucosio + Fruttosio", "numeric_value": 102, "text_value": None, "unit": "g/L", "flag": None, "reported_analyte_code": "glucose_fructose", "reported_analyte_name": "Glucosio + Fruttosio", "reported_numeric_value": 102, "reported_unit": "g/L", "report_url": "report-new"},
        {"sample_id": "old", "sample_name": "Nerello Mascalese must", "sample_type": "must", "lab_date": "2026-09-26", "sampled_at": None, "needs_review": 0, "wine_lot_id": "lot", "linked_wine_lot_ids": None, "variety_name": None, "analyte_code": "potential_alcohol", "analyte_name": "Alcol Potenziale", "numeric_value": 13.45, "text_value": None, "unit": "% Vol.", "flag": None, "reported_analyte_code": "potential_alcohol", "reported_analyte_name": "Alcol Potenziale", "reported_numeric_value": 13.45, "reported_unit": "% Vol.", "report_url": "report-old"},
    ]
    evidence = lot_lab_evidence({"id": "lot", "variety_summary": "Nerello Mascalese"}, 2026, rows=rows)
    output = lot_with_lab_measurements({"id": "lot", "stage": "fermentation"}, evidence)
    assert output["potential_alcohol_pct"] == 12.52
    assert output["alcohol_progress"] == {"lab_date": "2026-09-30", "total_projected_pct": 12.52, "developed_pct": 6.46, "remaining_potential_pct": 6.06, "glucose_fructose_g_l": 102.0, "basis": "The fermentation report separates alcohol already developed from remaining potential; total projected alcohol is the correct current recipe basis."}
    assert evidence["corrections"][0]["superseded_sample_id"] == "old"


def test_owner_disposition_and_nerello_trace_migrations_are_explicit():
    demijohns = (ROOT / "db/migrations/194_close_grecanico_tail_in_demijohns.sql").read_text()
    latest_lab = (ROOT / "db/migrations/195_link_latest_nerello_fermentation_report.sql").read_text()
    trace = (ROOT / "db/migrations/196_link_nerello_harvest_trace.sql").read_text()
    assert "aging_no_intervention" in demijohns
    assert "individual demijohn capacities and fills were not supplied" in demijohns
    assert "s.sample_type='wine'" in latest_lab
    assert "supersedes the 2026-09-26 baseline" in latest_lab
    assert "BLOCK-NM-01" in trace
    assert "invented_values',FALSE" in trace


def test_recipe_ui_shows_latest_alcohol_components_and_correction():
    javascript = (ROOT / "app/static/assets/enology-process.js").read_text()
    backend = (ROOT / "app/domains/laffort_catalog.py").read_text()
    assert "Total projected alcohol" in javascript
    assert "remaining potential" in javascript
    assert "enology-evidence-correction" in javascript
    assert '"corrections": (lab_evidence or {}).get("corrections")' in backend
    assert '"status": "aging_no_intervention" if no_intervention' in backend


def test_sugar_quantity_uses_corrected_total_alcohol_and_saved_target():
    recommendation = working_dose_recommendation(
        {
            "volume_l": 1600,
            "potential_alcohol_pct": 12.52,
            "target_potential_alcohol_pct": 13.5,
        },
        {"trigger_code": "alcohol_consistency", "product_name": "Naturalia crystalMUSTGRAPE", "dose_min": 1.68},
        {},
        [],
        [],
        "due",
        additions=[],
        lab_evidence={"metrics": {"potential_alcohol": {"lab_date": "2026-09-30"}}},
    )
    assert recommendation["measured_potential_alcohol_pct"] == 12.52
    assert recommendation["target_potential_alcohol_pct"] == 13.5
    assert recommendation["raw_alcohol_gap_pct"] == 0.98
    assert recommendation["quantity"] == 26.34
    assert recommendation["status"] == "recommended_now"
