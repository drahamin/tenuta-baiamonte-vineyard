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
        {"vintage_year": 2024, "variety_name": "Nerello", "grapes_kg": 2020, "wine_l": 1117, "cassette_count": 135},
        {"vintage_year": 2024, "variety_name": "Vintage total", "grapes_kg": 3220, "wine_l": 1767, "cassette_count": 215},
    ]


def test_reconciled_total_is_not_double_counted():
    assert reconciled_vintage_values(sample_rows()) == {"grapes_kg": 3220.0, "wine_l": 1767.0, "cassette_count": 215.0}


def test_historical_rows_and_varieties_are_display_only_fallbacks():
    rows = historical_harvest_rows(sample_rows())
    assert [row["variety_name"] for row in rows] == ["Grecanico", "Nerello"]
    assert all(row["historical_summary"] and row["first_pick_date"] is None for row in rows)
    varieties = merge_variety_summaries([{"id": "g", "name": "Grecanico", "harvested_kg": None}], sample_rows())
    assert next(row for row in varieties if row["name"] == "Grecanico")["harvested_kg"] == 1200
    assert next(row for row in varieties if row["name"] == "Nerello")["historical_summary"] is True


def test_historical_cellar_and_variety_charts_receive_prior_years():
    cellar = merge_cellar_history([{"vintage_year": 2026, "volume_l": 500}], sample_rows())
    assert next(row for row in cellar if row["vintage_year"] == 2024)["volume_l"] == 1767.0
    history = merge_variety_history([], sample_rows())
    assert len(history) == 2
    assert sum(float(row["harvested_kg"]) for row in history) == 3220


def test_year_selection_is_applied_to_operational_dashboard_queries():
    source = (ROOT / "app/main.py").read_text()
    script = (ROOT / "app/static/app.js").read_text()
    assert "YEAR(a.activity_date)=%s" in source
    historical_source = (ROOT / "app/historical_dashboard.py").read_text()
    assert "YEAR(weather_date)=%s" in historical_source
    assert "vintage_year=%s ORDER BY variety_name" in historical_source
    assert "state.year!==new Date().getFullYear()" in script


def test_today_ticker_uses_slower_reading_speed():
    script = (ROOT / "app/static/display.js").read_text()
    assert "ticker.length*.68" in script
