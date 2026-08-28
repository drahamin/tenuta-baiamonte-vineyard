from pathlib import Path

from app.historical_dashboard import (
    FIRST_ESTATE_VINTAGE,
    forecast_conversion_audit,
    historical_cellar_summary,
    historical_harvest_rows,
    historical_activity_audit,
    merge_cellar_history,
    merge_variety_history,
    merge_variety_summaries,
    reconciled_vintage_values,
    reconciled_vintage_history,
    variety_vintage_history,
)
from tests.source_helpers import backend_source


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


def test_historical_harvest_sequence_puts_sourced_dates_before_unknown_dates():
    rows = [
        {"vintage_year": 2025, "variety_name": "Grecanico", "grapes_kg": 1800, "first_pick_date": None},
        {"vintage_year": 2025, "variety_name": "Nerello", "grapes_kg": 3036, "first_pick_date": "2025-09-23"},
        {"vintage_year": 2025, "variety_name": "Grenache", "grapes_kg": 400, "first_pick_date": None},
    ]
    assert [row["variety_name"] for row in historical_harvest_rows(rows)] == ["Nerello", "Grecanico", "Grenache"]


def test_historical_work_audit_never_turns_missing_hours_into_zero_hours():
    audit = historical_activity_audit([
        {"record_date": "2024-11-01", "date_precision": "day", "labor_hours": 47},
        {"record_date": "2024-12-01", "date_precision": "month", "labor_hours": None},
        {"record_date": None, "date_precision": "year", "labor_hours": None},
    ])
    assert audit == {
        "records": 3, "known_hours": 47.0, "known_hour_records": 1, "hour_status": "partial",
        "exact_date_records": 1, "month_date_records": 1, "broad_date_records": 1,
    }


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


def test_tank_wine_history_matches_only_recorded_grape_types():
    history = variety_vintage_history("Nerello Mascalese / Grenache", sample_rows() + [
        {"vintage_year": 2023, "variety_name": "Grenache", "grapes_kg": 400, "wine_l": 220},
    ])
    assert history["grape_types"] == ["Nerello Mascalese", "Grenache"]
    assert [row["variety_name"] for row in history["vintages"]] == ["Nerello Mascalese / red", "Grenache"]
    assert all(row["variety_name"] != "Grecanico" for row in history["vintages"])


def test_cellar_source_bottle_facts_are_visible_without_replacing_reconciled_totals(monkeypatch):
    monkeypatch.setattr("app.historical_dashboard.fetch_all", lambda *_: [{"quantity_value": 2310, "quantity_unit": "750ml bottles"}])
    summary = historical_cellar_summary(2024, sample_rows())
    assert summary["grapes_kg"] == 3220
    assert summary["wine_l"] == 1767
    assert summary["bottled_750ml"] == 2310
    assert len(summary["source_facts"]) == 1


def test_year_selection_is_applied_to_operational_dashboard_queries():
    source = backend_source(ROOT)
    script = (ROOT / "app/static/app.js").read_text()
    historical_source = (ROOT / "app/historical_dashboard.py").read_text()
    assert "YEAR(a.activity_date)=%s" in historical_source
    assert "YEAR(weather_date)=%s" in historical_source
    assert "vintage_year=%s ORDER BY variety_name" in historical_source
    assert "state.year!==estateYear" in script
    assert "timeZone:'Europe/Rome'" in script
    assert "selected_dashboard_activities(year, season_id)" in source
    assert "historical_note_facts(year)" in source
    assert "YEAR(work_date)=%s" in historical_source
    assert 'row["labor_entry"] = True' in historical_source
    assert "historical_work_records" in source
    assert "historical_work_audit" in source
    assert "record_year IS NULL AND period_start_year<=%s AND period_end_year>=%s" in historical_source
    assert "source records · hours not recorded" in script
    assert "harvest date not recorded in source" in script
    assert "Historical source · " in script
    assert "renderHistoricalEvidence()" in script
    assert "750 ml bottles" in script
    assert "status IN ('open','monitoring') AND opened_date<=%s" in source
    assert "closed_date BETWEEN %s AND %s" in source
    assert "closed_date IS NULL AND opened_date BETWEEN %s AND %s" in source


def test_apple_notes_migration_keeps_facts_auditable():
    migration = (ROOT / "db/migrations/044_apple_notes_history.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS historical_note_facts" in migration
    assert "2025-09-23" in migration
    assert "maturity evidence, not a confirmed harvest date" in migration
    assert "The same note states a 7,500 kg total" in migration
    inside_literal = False
    for character in migration:
        if character == "'":
            inside_literal = not inside_literal
        assert not (character == ";" and inside_literal)


def test_laboratory_reports_follow_selected_year():
    source = backend_source(ROOT)
    laboratory = (ROOT / "app/domains/laboratory.py").read_text()
    script = (ROOT / "app/static/app.js").read_text()
    assert "def lab_decision_board(year:" in source
    assert "COALESCE(s.vintage_year,YEAR(s.lab_date))=%s" in laboratory
    assert "labs/history?from_year=${year}&to_year=${year}" in script
    assert "labs/decision-board?year=${year}" in script
    migration = (ROOT / "db/migrations/044_apple_notes_history.sql").read_text()
    assert "ADD COLUMN IF NOT EXISTS vintage_year" in migration
    assert "WHEN wine_season.vintage_year IS NOT NULL" in migration
    assert "WHEN s.sample_type IN ('grape','must') THEN YEAR(s.lab_date)" in migration
    dedupe = (ROOT / "db/migrations/045_dedupe_apple_note_labs.sql").read_text()
    assert "JOIN lab_samples original" in dedupe
    assert "original.lab_date=imported.lab_date" in dedupe
    assert "original.sample_name" in dedupe


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


def test_forecast_audit_excludes_disputed_volume_and_backtests_trusted_years():
    vintages = [
        {"vintage_year": 2022, "grapes_kg": 8000, "wine_l": 5570, "evidence_status": "Apple Notes"},
        {"vintage_year": 2023, "grapes_kg": 5610, "wine_l": 3755, "evidence_status": "Reported"},
        {"vintage_year": 2024, "grapes_kg": 3220, "wine_l": 1767, "evidence_status": "Reconciled total"},
        {"vintage_year": 2025, "grapes_kg": 5236, "wine_l": 4000, "evidence_status": "Reported - review", "reconciliation_note": "Use cautiously"},
        {"vintage_year": 2026, "grapes_kg": 9999, "wine_l": 9999, "evidence_status": "future leakage"},
    ]
    conversion, audit = forecast_conversion_audit(2026, vintages)
    assert round(conversion, 4) == round((3755 + 1767) / (5610 + 3220), 4)
    assert audit["production_vintages"] == [2023, 2024]
    assert audit["excluded_production_vintages"] == [{"vintage_year": 2025, "reason": "Reported liquid volume requires reconciliation before model use"}]
    assert [row["vintage_year"] for row in audit["conversion_backtest"]] == [2024]
    assert audit["recommended_scenario_range_pct"] == 25
    assert audit["production_model_confidence"] == "low"


def test_reconciled_history_keeps_one_row_per_vintage():
    history = reconciled_vintage_history(sample_rows())
    assert history == [{
        "vintage_year": 2024,
        "grapes_kg": 3220.0,
        "wine_l": 1767.0,
        "cassette_count": 215.0,
        "evidence_status": "",
        "reconciliation_note": "",
    }]


def test_pre_operation_vintages_never_enter_dashboard_history():
    history = reconciled_vintage_history([
        {"vintage_year": 2022, "variety_name": "Incorrect", "grapes_kg": 9999, "wine_l": 9999},
        *sample_rows(),
    ])
    assert FIRST_ESTATE_VINTAGE == 2023
    assert [row["vintage_year"] for row in history] == [2024]


def test_operational_dashboard_enforces_the_2023_boundary_in_ui_and_api():
    source = backend_source(ROOT)
    script = (ROOT / "app/static/app.js").read_text()
    historical = (ROOT / "app/historical_dashboard.py").read_text()
    assert "ge=FIRST_ESTATE_VINTAGE" in source
    assert "from_year = max(FIRST_ESTATE_VINTAGE, from_year)" in source
    assert "year>=firstEstateVintage" in script
    assert "state.year=Math.max(firstEstateVintage,state.year)" in script
    assert "vintage_year>=%s" in historical


def test_lab_creation_and_trends_follow_linked_vintage_not_calendar_year():
    source = (ROOT / "app/domains/laboratory_routes.py").read_text()
    assert "linked_vintage = int(linked_lot[\"vintage_year\"])" in source
    assert "sample_year = linked_vintage or" in source
    laboratory = (ROOT / "app/domains/laboratory.py").read_text()
    assert laboratory.count("COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) result_year") >= 2


def test_lab_audit_preserves_overlap_year_evidence_and_counts_by_vintage():
    migration = (ROOT / "db/migrations/048_audit_lab_vintages.sql").read_text()
    importer = (ROOT / "scripts/import_workbook.py").read_text()
    source = backend_source(ROOT)
    laboratory = (ROOT / "app/domains/laboratory.py").read_text()
    mcp = (ROOT / "app/mcp_server.py").read_text()
    script = (ROOT / "app/static/app.js").read_text()

    assert "vintage_assignment_confidence" in migration
    assert "LAB-20240507-01" in migration and "s.vintage_year=2023" in migration
    assert "LAB-20250509-01" in migration and "sample_identity" in migration
    assert "LAB-20251027-01" in migration and "malolactic sequence" in migration
    assert 'test_id.startswith("LAB-20250509-")' in importer
    assert "COALESCE(vintage_year,YEAR(lab_date)) year,COUNT(*) lab_samples" in source
    assert '"audit": fetch_all(' in laboratory
    assert "vintage_assignment_evidence" in laboratory
    assert "COALESCE(s.vintage_year,se.vintage_year)=%s" in mcp
    assert "Source reports" in script and "vintage inferred" in script


def test_forecast_separates_completed_treatment_clearance_from_overdue_plans():
    migration = (ROOT / "db/migrations/046_reconcile_confirmed_treatments.sql").read_text()
    intelligence = (ROOT / "app/intelligence.py").read_text()
    assert "completion confirmed by user" in migration
    assert "status='completed'" in migration
    assert '"treatment_clearance": fetch_all(' in intelligence
    assert '"scheduler": "harvest-learning-v1"' in intelligence
    assert '"learned_model": learned_model' in intelligence
    assert '"treatment_clearance": item.get("treatment_clearance")' in intelligence


def test_today_ticker_uses_slower_reading_speed():
    script = (ROOT / "app/static/display.js").read_text()
    assert "ticker.length*.68" in script


def test_history_chart_uses_estate_year_for_incomplete_current_vintage():
    enhancements = (ROOT / "app/static/assets/operations-enhancements.js").read_text()

    assert "Number(row.year)!==estateYear" in enhancements
    assert "Number(row.year)===estateYear" in enhancements
    assert "new Date().getFullYear()" not in enhancements
