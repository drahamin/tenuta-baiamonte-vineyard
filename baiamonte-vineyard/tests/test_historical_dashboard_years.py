from pathlib import Path

from app.historical_dashboard import (
    historical_harvest_rows,
    merge_cellar_history,
    merge_variety_history,
    merge_variety_summaries,
    reconciled_vintage_values,
)


ROOT = Path(__file__).resolve().parents[1]


def sample_rows():
    return [
        {"vintage_year": 2024, "variety_name": "Grecanico", "grapes_kg": 1200, "wine_l": 650, "cassette_count": 80},
        {"vintage_year": 2024, "variety_name": "Nerello Mascalese / red", "grapes_kg": 2020, "wine_l": 1117, "cassette_count": 135},
        {"vintage_year": 2024, "variety_name": "Vintage total", "grapes_kg": 3220, "wine_l": 1767, "cassette_count": 215},
    ]


def test_reconciled_total_is_not_double_counted():
    assert reconciled_vintage_values(sample_rows()) == {"grapes_kg": 3220.0, "wine_l": 1767.0, "cassette_count": 215.0}


def test_historical_rows_and_varieties_are_display_only_fallbacks():
    rows = historical_harvest_rows(sample_rows())
    assert [row["variety_name"] for row in rows] == ["Grecanico", "Nerello Mascalese"]
    assert all(row["historical_summary"] and row["first_pick_date"] is None for row in rows)
    varieties = merge_variety_summaries([{"id": "g", "name": "Grecanico", "harvested_kg": None}], sample_rows())
    assert next(row for row in varieties if row["name"] == "Grecanico")["harvested_kg"] == 1200
    assert next(row for row in varieties if row["name"] == "Nerello Mascalese")["historical_summary"] is True


def test_exact_note_harvest_date_flows_to_historical_cards():
    rows = [{"vintage_year": 2025, "variety_name": "Nerello", "grapes_kg": 3036, "cassette_count": 164, "first_pick_date": "2025-09-23", "last_pick_date": "2025-09-23", "harvest_date_precision": "day", "source_note_name": "2025 Harvest Nerello 9/23"}]
    harvest = historical_harvest_rows(rows)
    assert harvest[0]["first_pick_date"] == "2025-09-23"
    varieties = merge_variety_summaries([], rows)
    assert varieties[0]["first_pick_date"] == "2025-09-23"
    assert varieties[0]["source_note_name"] == "2025 Harvest Nerello 9/23"


def test_color_suffix_merges_into_canonical_variety_without_duplicate():
    varieties = [{"id": "nm", "name": "Nerello Mascalese", "harvested_kg": None}]
    merged = merge_variety_summaries(varieties, sample_rows())
    nerello = [row for row in merged if row["name"] == "Nerello Mascalese"]
    assert len(nerello) == 1
    assert nerello[0]["harvested_kg"] == 2020


def test_historical_cellar_and_variety_charts_receive_prior_years():
    cellar = merge_cellar_history([{"vintage_year": 2026, "volume_l": 500}], sample_rows())
    assert next(row for row in cellar if row["vintage_year"] == 2024)["volume_l"] == 1767.0
    history = merge_variety_history([], sample_rows())
    assert len(history) == 2
    assert sum(float(row["harvested_kg"]) for row in history) == 3220


def test_year_selection_is_applied_to_operational_dashboard_queries():
    source = (ROOT / "app/main.py").read_text()
    script = (ROOT / "app/static/app.js").read_text()
    historical_source = (ROOT / "app/historical_dashboard.py").read_text()
    assert "YEAR(a.activity_date)=%s" in historical_source
    assert "YEAR(weather_date)=%s" in historical_source
    assert "vintage_year=%s ORDER BY variety_name" in historical_source
    assert "state.year!==new Date().getFullYear()" in script
    assert "selected_dashboard_activities(year, season_id)" in source
    assert "historical_work_records" in source
    assert "harvest date not recorded in source" in script
    assert "Historical source · " in script


def test_apple_notes_migration_keeps_facts_auditable():
    migration = (ROOT / "db/migrations/044_apple_notes_history.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS historical_note_facts" in migration
    assert "2025-09-23" in migration
    assert "maturity evidence, not a confirmed harvest date" in migration
    assert "The same note states a 7,500 kg total" in migration


def test_laboratory_reports_follow_selected_year():
    source = (ROOT / "app/main.py").read_text()
    laboratory = (ROOT / "app/domains/laboratory.py").read_text()
    script = (ROOT / "app/static/app.js").read_text()
    assert "def lab_decision_board(year:" in source
    assert "COALESCE(s.vintage_year,YEAR(s.lab_date))=%s" in laboratory
    assert "labs/history?from_year=${state.year}&to_year=${state.year}" in script
    assert "labs/decision-board?year=${state.year}" in script
    migration = (ROOT / "db/migrations/044_apple_notes_history.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS vintage_year" in migration
    assert "WHEN wine_season.vintage_year IS NOT NULL" in migration
    assert "WHEN s.sample_type IN ('grape','must') THEN YEAR(s.lab_date)" in migration


def test_future_predictions_include_all_valid_historical_evidence():
    history = (ROOT / "app/historical_dashboard.py").read_text()
    intelligence = (ROOT / "app/intelligence.py").read_text()
    assert '"laboratory_years": lab_years' in history
    assert '"maturity_years": maturity_years' in history
    assert '"exact_pick_years": exact_pick_years' in history
    assert '"historical_grape_labs"' in intelligence
    assert '"historical_estate_grape_labs"' in intelligence
    assert '"historical_maturity"' in intelligence
    assert "vs.harvest_date_precision='day'" in intelligence


def test_forecast_conversion_uses_weighted_historical_production_and_weather():
    source = (ROOT / "app/historical_dashboard.py").read_text()
    assert "conversion = wine / grapes" in source
    assert '"conversion_method"' in source
    assert "SUM(gdd_base10) gdd_base10" in source


def test_today_ticker_uses_slower_reading_speed():
    script = (ROOT / "app/static/display.js").read_text()
    assert "ticker.length*.68" in script
