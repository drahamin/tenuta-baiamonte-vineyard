from datetime import date
from pathlib import Path

from app.domains.olives import estimate_harvest_date


ROOT = Path(__file__).resolve().parents[1]


def test_olive_harvest_prediction_uses_only_exact_harvest_records():
    result = estimate_harvest_date([
        {"record_date": "2023-10-30", "record_year": 2023, "activity": "Olive harvest", "olives_harvested_kg": 1937},
        {"record_date": None, "record_year": 2024, "activity": "Olive harvest", "olives_harvested_kg": 332},
        {"record_date": "2025-11-08", "record_year": 2025, "activity": "Raccolta olive", "olives_harvested_kg": 1162},
    ], 2026, date(2026, 8, 19))
    assert result["status"] == "estimated"
    assert result["estimated_date"] == date(2026, 11, 4)
    assert result["training_samples"] == 2
    assert result["confidence"] == "low"


def test_current_olive_harvest_date_is_shown_as_recorded_not_predicted():
    result = estimate_harvest_date([
        {"record_date": "2026-10-22", "activity": "Olive harvest", "olives_harvested_kg": 500},
    ], 2026)
    assert result["status"] == "recorded"
    assert result["estimated_date"] == date(2026, 10, 22)


def test_olive_and_vineyard_treatment_sources_are_migrated_separately():
    migration = (ROOT / "db/migrations/065_separate_olive_treatments.sql").read_text(encoding="utf-8")
    assert "crop_scope ENUM('vineyard','olives')" in migration
    assert "OWNER-OLIVE-TREATMENT-2026-01" in migration
    assert "WORKBOOK-OLIVE-TREATMENT-2025-02" in migration
    assert "WORKBOOK-OLIVE-TREATMENT-2025-03" in migration
    assert "TRATTAMENTO VIGNETO TENUTA BAIAMONTE" in migration
    assert "actual_details_confirmed=1" in migration
