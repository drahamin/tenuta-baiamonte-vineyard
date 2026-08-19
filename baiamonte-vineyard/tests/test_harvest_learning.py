from datetime import date, timedelta

from app.harvest_learning import (
    HARVEST_ANCHORS,
    build_gdd_curves,
    canonical_variety,
    daily_gdd,
    fit_harvest_model,
    prepare_training_rows,
)


def weather_rows(year: int, through: date) -> list[dict]:
    start = date(year, 3, 1)
    return [
        {"weather_date": start + timedelta(days=offset), "temp_min_c": 12, "temp_avg_c": 18, "temp_max_c": 24}
        for offset in range((through - start).days + 1)
    ]


def test_gdd_is_standardized_to_daily_minimum_and_maximum() -> None:
    assert daily_gdd({"temp_min_c": 12, "temp_avg_c": 17, "temp_max_c": 24}) == 8
    assert daily_gdd({"temp_min_c": None, "temp_avg_c": 17, "temp_max_c": None}) == 7
    assert daily_gdd({"temp_min_c": 2, "temp_avg_c": 7, "temp_max_c": 8}) == 0


def test_training_requires_exact_supported_variety_dates_and_weather() -> None:
    curves = build_gdd_curves(weather_rows(2025, date(2025, 9, 30)))
    records = prepare_training_rows(
        [],
        [
            {"vintage_year": 2025, "variety_name": "Granache", "pick_date": date(2025, 9, 14)},
            {"vintage_year": 2025, "variety_name": "Unknown blend", "pick_date": date(2025, 9, 14)},
        ],
        curves,
        HARVEST_ANCHORS,
    )
    assert len(records) == 1
    assert records[0]["variety"] == "grenache"
    assert canonical_variety("Nerello Mascalese / red") == "nerello mascalese"


def test_model_refuses_to_claim_learning_from_one_vintage() -> None:
    curves = build_gdd_curves(weather_rows(2025, date(2025, 9, 30)))
    records = prepare_training_rows(
        [],
        [{"vintage_year": 2025, "variety_name": "Nerello", "pick_date": date(2025, 9, 23)}],
        curves,
        HARVEST_ANCHORS,
    )
    result = fit_harvest_model(records, "Nerello Mascalese", 2026, date(2026, 9, 21), curves)
    assert result["ready"] is False
    assert result["training_samples"] == 1
    assert result["missing_evidence"]


def test_model_learns_date_and_reports_backtest_error() -> None:
    rows = []
    summaries = []
    for year, variety, pick in [
        (2023, "Grecanico", date(2023, 9, 8)),
        (2024, "Grenache", date(2024, 9, 15)),
        (2025, "Nerello Mascalese", date(2025, 9, 22)),
    ]:
        rows.extend(weather_rows(year, date(year, 10, 10)))
        summaries.append({"vintage_year": year, "variety_name": variety, "pick_date": pick})
    rows.extend(weather_rows(2026, date(2026, 10, 10)))
    curves = build_gdd_curves(rows)
    records = prepare_training_rows([], summaries, curves, HARVEST_ANCHORS)
    result = fit_harvest_model(records, "Grecanico", 2026, date(2026, 9, 7), curves)
    assert result["ready"] is True
    assert result["predicted_date"] is not None
    assert result["training_years"] == [2023, 2024, 2025]
    assert result["backtest_predictions"] == 3
    assert result["backtest_mae_days"] is not None


def test_two_complete_vintages_support_bidirectional_backtesting() -> None:
    rows = []
    summaries = []
    for year, dates in {
        2023: {"Grecanico": (9, 23), "Grenache": (9, 17), "Nerello Mascalese": (10, 8)},
        2025: {"Grecanico": (9, 11), "Grenache": (9, 17), "Nerello Mascalese": (9, 23)},
    }.items():
        rows.extend(weather_rows(year, date(year, 10, 31)))
        summaries.extend(
            {"vintage_year": year, "variety_name": variety, "pick_date": date(year, *month_day)}
            for variety, month_day in dates.items()
        )
    rows.extend(weather_rows(2026, date(2026, 10, 31)))
    curves = build_gdd_curves(rows)
    records = prepare_training_rows([], summaries, curves, HARVEST_ANCHORS)
    result = fit_harvest_model(records, "Grenache", 2026, date(2026, 9, 14), curves)
    assert result["ready"] is True
    assert result["training_samples"] == 6
    assert result["training_years"] == [2023, 2025]
    assert result["backtest_predictions"] == 6


def test_authoritative_three_vintage_matrix_trains_nine_observations() -> None:
    rows = []
    summaries = []
    for year, dates in {
        2023: {"Grecanico": (9, 23), "Grenache": (9, 24), "Nerello Mascalese": (10, 8)},
        2024: {"Grecanico": (9, 11), "Grenache": (9, 23), "Nerello Mascalese": (9, 23)},
        2025: {"Grecanico": (9, 11), "Grenache": (9, 17), "Nerello Mascalese": (9, 23)},
    }.items():
        rows.extend(weather_rows(year, date(year, 10, 31)))
        summaries.extend(
            {"vintage_year": year, "variety_name": variety, "pick_date": date(year, *month_day)}
            for variety, month_day in dates.items()
        )
    rows.extend(weather_rows(2026, date(2026, 10, 31)))
    curves = build_gdd_curves(rows)
    records = prepare_training_rows([], summaries, curves, HARVEST_ANCHORS)
    result = fit_harvest_model(records, "Nerello Mascalese", 2026, date(2026, 9, 21), curves)
    assert result["ready"] is True
    assert result["training_samples"] == 9
    assert result["training_years"] == [2023, 2024, 2025]
    assert result["backtest_predictions"] == 9
