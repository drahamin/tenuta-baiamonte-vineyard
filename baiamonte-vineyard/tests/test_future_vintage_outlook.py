from datetime import date
from pathlib import Path

from app.domains.dashboard_routes import build_future_phenology_outlook, build_future_vintage_outlook


ROOT = Path(__file__).resolve().parents[1]


def test_future_vintage_outlook_uses_estate_forecast_and_prior_pick_dates() -> None:
    varieties = [{"id": "grecanico", "name": "Grecanico"}]
    history = [
        {"vintage_year": 2024, "variety_name": "Grecanico", "first_pick_date": "2024-09-11"},
        {"vintage_year": 2025, "variety_name": "Grecanico", "first_pick_date": "2025-09-11"},
        {"vintage_year": 2026, "variety_name": "Grecanico", "first_pick_date": "2026-09-09"},
    ]
    production = [{"variety_name": "Grecanico", "grape_kg": 2929.316, "source": "database planning"}]

    row = build_future_vintage_outlook(2027, varieties, history, production)["grecanico"]

    assert row["predicted_date"] == date(2027, 9, 11)
    assert row["window_start"] == date(2027, 9, 4)
    assert row["window_end"] == date(2027, 9, 18)
    assert row["projected_kg"] == 2929.316
    assert row["purchased_fruit_assumed_kg"] == 0
    assert row["confidence"] == "medium"


def test_future_outlook_never_carries_purchased_receipts_into_next_year() -> None:
    result = build_future_vintage_outlook(
        2027,
        [{"id": "grenache", "name": "Grenache"}],
        [{"vintage_year": 2026, "variety_name": "Grenache", "first_pick_date": "2026-09-10", "purchased_fruit_kg": 1078}],
        [{"variety_name": "Grenache", "grape_kg": 794.758, "source": "database planning"}],
    )["grenache"]

    assert result["projected_kg"] == 794.758
    assert result["purchased_fruit_assumed_kg"] == 0


def test_future_phenology_uses_recorded_calendar_timing() -> None:
    rows = [
        {"stage_code": "veraison", "stage_name": "Veraison", "observed_date": "2025-08-03"},
        {"stage_code": "veraison", "stage_name": "Veraison", "observed_date": "2026-08-05"},
        {"stage_code": "fruit_set", "stage_name": "Fruit set", "observed_date": "2026-06-10"},
    ]

    result = build_future_phenology_outlook(2027, rows)

    assert [row["stage_code"] for row in result] == ["fruit_set", "veraison"]
    assert result[1]["estimated_date"] == date(2027, 8, 4)
    assert result[1]["confidence"] == "medium"


def test_future_outlook_is_visible_and_distinguishes_forecast_from_actual() -> None:
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in (
        "app/static/app.js", "app/static/assets/harvest.js",
    ))

    assert 'id="futureVintageOutlook"' in html
    assert "EARLY VINTAGE OUTLOOK · FORECAST" in javascript
    assert "Purchased</span><b>Not assumed" in javascript
    assert "Crop, agronomy &amp; enology planning" in javascript
    assert "$('grapeCompletion').textContent='Planning'" in javascript


def test_future_outlook_exposes_agronomy_and_enology_learning_states() -> None:
    dashboard = (ROOT / "app/domains/dashboard_routes.py").read_text()
    enology = (ROOT / "app/domains/enology_process.py").read_text()
    main = (ROOT / "app/main.py").read_text()

    assert '"pick_date_model": "active"' in dashboard
    assert '"awaiting_phenology_history"' in dashboard
    assert '"predicted_full_bottles_750ml"' in dashboard
    assert '"learning_status": "active"' in enology
    assert '"yield_historical_results"' in enology
    assert '"type": "future_season_learning"' in main
    assert "Current-year weather is not reused" in main
