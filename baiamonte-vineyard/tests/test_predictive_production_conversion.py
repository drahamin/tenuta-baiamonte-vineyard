from app.domains.projections import build_operational_projections


def test_future_output_uses_each_varietys_historical_ratio_and_sums_whole_bottles(monkeypatch):
    monkeypatch.setattr("app.domains.projections.adjust_production_forecasts", lambda rows, _year: rows)
    profiles = {
        "grecanico": {"predictive_l_per_kg": 0.6, "prediction_source": "history", "historical_vintages": [2024, 2025]},
        "grenache": {"predictive_l_per_kg": 0.5, "prediction_source": "history", "historical_vintages": [2023, 2025]},
    }
    wines = [
        {"finished_wine": "Grecanico", "grape_kg": 1, "wine_l": 0.6, "yield_l_per_kg": 0.6, "crates": 1},
        {"finished_wine": "Grenache", "grape_kg": 1, "wine_l": 0.5, "yield_l_per_kg": 0.5, "crates": 1},
    ]
    result = build_operational_projections(
        2027,
        {"vintages": [], "metrics": {"planned_kg": 2}, "varieties": []},
        {
            "settings": {"expected_yield_l_per_kg": 0.7, "expected_yield_is_configured": False, "crate_weight_kg": 15},
            "planning": {"wines": wines, "nerello_kg": 0, "grenache_kg": 1, "grecanico_kg": 1},
            "yield_profiles": profiles,
        },
        0.7,
        {"recommended_scenario_range_pct": 15, "conversion_source": "history"},
        [
            {"vintage_year": 2027, "variety_name": "Grecanico", "grape_kg": 1, "source": "test"},
            {"vintage_year": 2027, "variety_name": "Grenache", "grape_kg": 1, "source": "test"},
        ],
    )

    total = result["production_forecast_totals"][0]
    assert total["wine_l"] == 1.1
    assert total["bottles_750ml"] == 0
    assert [row["predictive_l_per_kg"] for row in total["variety_outputs"]] == [0.6, 0.5]
    assert all(row["prediction_source"] == "history" for row in total["variety_outputs"])
