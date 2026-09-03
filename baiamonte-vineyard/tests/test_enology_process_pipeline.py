from datetime import datetime, timedelta
from pathlib import Path

from app.domains.enology_process import (
    canonical_enology_analyte,
    fermentation_outlook,
    potential_alcohol_from_babo,
    enology_testing_pipeline,
)


ROOT = Path(__file__).resolve().parents[1]


def test_tomorrow_pipeline_contains_exact_requested_tests_and_calculation_boundary():
    pipeline = {item["code"]: item for item in enology_testing_pipeline("pre-harvest")}
    assert set(pipeline) == {"ph", "total_acidity", "babo", "potential_alcohol", "potassium"}
    assert pipeline["potential_alcohol"]["method"] == "calculate_from_babo"
    assert all(pipeline[code]["method"] == "measure" for code in ("ph", "total_acidity", "babo", "potassium"))


def test_enology_analyte_names_are_canonical_bilingual_and_preserve_reported_units():
    assert canonical_enology_analyte("pH") == {"code": "ph", "name": "pH", "unit": "pH"}
    assert canonical_enology_analyte("acidità totale", unit="g/L as tartaric acid") == {
        "code": "total_acidity", "name": "Total acidity / Acidità totale", "unit": "g/L as tartaric acid"
    }
    assert canonical_enology_analyte("grado Babo") == {"code": "babo", "name": "Babo", "unit": "°Babo"}
    assert canonical_enology_analyte("potassio", unit="mg/L")["name"] == "Potassium / Potassio"
    assert canonical_enology_analyte("alcol potenziale calcolato")["unit"] == "% vol"


def test_enologist_views_keep_each_analyte_and_unit_in_its_own_chart():
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text(encoding="utf-8")
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "`${row.metric_code}|${row.display_unit" in frontend
    assert "enologyChemistryCharts" in page
    assert "enologyFermentationCharts" in page
    assert "enologyAdditiveLedger" in page
    for label in ("Specific gravity", "°Brix", "Temperature", "pH"):
        assert label in frontend


def test_prefermentation_adds_yan_gate_before_nutrient_prediction():
    pipeline = {item["code"] for item in enology_testing_pipeline("pre-fermentation")}
    assert "yan" in pipeline


def test_potential_alcohol_uses_estate_pairs_and_discloses_factor():
    result = potential_alcohol_from_babo(17.0, [
        {"babo": 16.15, "potential_alcohol": 10.65},
        {"babo": 16.71, "potential_alcohol": 11.03},
        {"babo": 16.21, "potential_alcohol": 10.70},
    ])
    assert result["status"] == "calculated"
    assert result["evidence_count"] == 3
    assert result["confidence"] == "medium"
    assert 11.1 < result["value_pct_vol"] < 11.3
    assert result["factor"] > 0


def test_potential_alcohol_refuses_an_unsupported_default_factor():
    result = potential_alcohol_from_babo(17.0, [])
    assert result["status"] == "insufficient_data"
    assert result["value_pct_vol"] is None


def test_fermentation_prediction_requires_two_dated_density_readings():
    result = fermentation_outlook([{"observed_at": "2026-09-03T08:00:00", "density_sg": 1.080}])
    assert result["status"] == "insufficient_data"
    assert result["is_automatic_instruction"] is False


def test_fermentation_prediction_flags_flat_density_for_review():
    start = datetime(2026, 9, 3, 8)
    result = fermentation_outlook([
        {"observed_at": start, "density_sg": 1.080},
        {"observed_at": start + timedelta(days=2), "density_sg": 1.080},
    ], now=start + timedelta(days=2))
    assert result["status"] == "stalled_review"
    assert result["requires_enologist_review"] is True


def test_migration_seeds_tomorrow_request_without_faking_results():
    migration = (ROOT / "db/migrations/141_enology_process_models.sql").read_text(encoding="utf-8")
    for analyte in ("ph", "total_acidity", "babo", "potassium", "potential_alcohol"):
        assert analyte in migration
    assert "2026-09-03 07:00:00" in migration
    assert "result_sample_id CHAR(36) NULL" in migration
    assert "do not combine red and white results" in migration
