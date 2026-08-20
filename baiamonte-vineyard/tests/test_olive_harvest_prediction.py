from datetime import date
from pathlib import Path

from app.domains.olives import apply_harvest_style, default_harvest_preference, estimate_harvest_date, harvest_style_models


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


def test_green_priority_shifts_estate_prediction_without_fixed_calendar_date():
    baseline = estimate_harvest_date([
        {"record_date": "2023-10-30", "activity": "Olive harvest", "olives_harvested_kg": 1937},
        {"record_date": "2025-11-08", "activity": "Raccolta olive", "olives_harvested_kg": 1162},
    ], 2026, date(2026, 8, 20))
    greener = apply_harvest_style(baseline, "green_priority")
    assert greener["estimated_date"] == baseline["estimated_date"] - date.resolution * 35
    assert greener["window_start"] == baseline["window_start"] - date.resolution * 35
    assert greener["style_offset_days"] == -35
    assert "earlier than" in greener["basis"]


def test_recorded_harvest_is_not_shifted_by_a_style_model():
    actual = estimate_harvest_date([
        {"record_date": "2026-10-22", "activity": "Olive harvest", "olives_harvested_kg": 500},
    ], 2026)
    styled = apply_harvest_style(actual, "green_priority")
    assert styled["estimated_date"] == date(2026, 10, 22)
    assert styled["status"] == "recorded"


def test_olive_harvest_styles_are_selectable_and_explain_tradeoffs():
    models = harvest_style_models()
    assert [model["code"] for model in models] == ["green_priority", "green_balanced", "estate_calendar"]
    assert [model["offset_days"] for model in models] == [-35, -21, 0]
    assert all(model["fruit_target"] and model["oil_style"] and model["tradeoff"] for model in models)
    assert default_harvest_preference(2026)["style_code"] == "green_priority"


def test_harvest_preference_is_database_backed_without_a_fixed_september_date():
    migration = (ROOT / "db/migrations/071_olive_harvest_style_preference.sql").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/olive_routes.py").read_text(encoding="utf-8")
    markup = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS olive_harvest_preferences" in migration
    assert "target_start" not in migration
    assert "2026-09" not in migration
    assert '@router.put("/harvest-preference/{year}"' in routes
    assert 'id="oliveHarvestPreferenceForm"' in markup
    assert "harvest_style_models" in javascript


def test_olive_and_vineyard_treatment_sources_are_migrated_separately():
    migration = (ROOT / "db/migrations/065_separate_olive_treatments.sql").read_text(encoding="utf-8")
    assert "crop_scope ENUM('vineyard','olives')" in migration
    assert "OWNER-OLIVE-TREATMENT-2026-01" in migration
    assert "WORKBOOK-OLIVE-TREATMENT-2025-02" in migration
    assert "WORKBOOK-OLIVE-TREATMENT-2025-03" in migration
    assert "TRATTAMENTO VIGNETO TENUTA BAIAMONTE" in migration
    assert "actual_details_confirmed=1" in migration
