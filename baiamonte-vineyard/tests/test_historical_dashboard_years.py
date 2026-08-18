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


def test_forecast_conversion_uses_weighted_historical_production_and_weather():
    source = (ROOT / "app/historical_dashboard.py").read_text()
    assert "conversion = wine / grapes" in source
    assert '"conversion_method"' in source
    assert "SUM(gdd_base10) gdd_base10" in source


def test_today_ticker_uses_slower_reading_speed():
    script = (ROOT / "app/static/display.js").read_text()
    assert "ticker.length*.68" in script
