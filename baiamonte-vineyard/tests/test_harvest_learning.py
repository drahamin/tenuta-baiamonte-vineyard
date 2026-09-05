from datetime import date, timedelta

from app.harvest_learning import (
    HARVEST_ANCHORS,
    build_gdd_curves,
    canonical_variety,
    daily_gdd,
    estimate_lab_pick_date,
    fit_harvest_model,
    fuse_harvest_dates,
    prepare_training_rows,
)


def test_lab_timing_matches_same_variety_historical_chemistry() -> None:
    current = {
        "analytes": {
            "babo": {"latest_value": 19.9, "latest_date": date(2026, 9, 4)},
            "ph": {"latest_value": 3.31, "latest_date": date(2026, 9, 4)},
            "total_acidity_tartaric": {"latest_value": 6.45, "latest_date": date(2026, 9, 4)},
        }
    }
    history = [
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Grenache", "analyte_code": "babo", "numeric_value": 20.2},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Grenache", "analyte_code": "ph", "numeric_value": 3.3},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Grenache", "analyte_code": "ta", "numeric_value": 6.45},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "babo", "numeric_value": 19.9},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "ph", "numeric_value": 3.31},
    ]
    result = estimate_lab_pick_date(
        current,
        history,
        [{"year": 2025, "variety": "grenache", "pick_date": date(2025, 9, 17)}],
        "Grenache",
    )
    assert result["usable"] is True
    assert result["estimated_days_to_harvest"] == 2
    assert result["predicted_pick_date"] == date(2026, 9, 6)
    assert result["comparisons"][0]["shared_markers"] == ["babo", "ph", "ta"]


def test_lab_timing_refuses_unpaired_or_cross_variety_evidence() -> None:
    result = estimate_lab_pick_date(
        {"analytes": {"babo": {"latest_value": 19.9, "latest_date": date(2026, 9, 4)}}},
        [{"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "babo", "numeric_value": 19.9}],
        [{"year": 2025, "variety": "nerello mascalese", "pick_date": date(2025, 9, 23)}],
        "Grenache",
    )
    assert result["usable"] is False


def test_lab_timing_uses_only_one_reference_per_vintage() -> None:
    current = {
        "analytes": {
            "babo": {"latest_value": 19.8, "latest_date": date(2026, 9, 4)},
            "ph": {"latest_value": 3.21, "latest_date": date(2026, 9, 4)},
            "ta": {"latest_value": 9.9, "latest_date": date(2026, 9, 4)},
        }
    }
    history = []
    for day, babo, ph, ta in [(15, 19.7, 3.14, 11.0), (17, 20.3, 3.1, 10.2), (22, 20.4, 3.16, 9.7)]:
        history.extend([
            {"vintage_year": 2025, "lab_date": date(2025, 9, day), "sample_name": "Nerello", "analyte_code": "babo", "numeric_value": babo},
            {"vintage_year": 2025, "lab_date": date(2025, 9, day), "sample_name": "Nerello", "analyte_code": "ph", "numeric_value": ph},
            {"vintage_year": 2025, "lab_date": date(2025, 9, day), "sample_name": "Nerello", "analyte_code": "ta", "numeric_value": ta},
        ])
    history.extend([
        {"vintage_year": 2024, "lab_date": date(2024, 9, 10), "sample_name": "Nerello Mascalese", "analyte_code": "babo", "numeric_value": 20.35},
        {"vintage_year": 2024, "lab_date": date(2024, 9, 10), "sample_name": "Nerello Mascalese", "analyte_code": "ph", "numeric_value": 3.11},
        {"vintage_year": 2024, "lab_date": date(2024, 9, 10), "sample_name": "Nerello Mascalese", "analyte_code": "ta", "numeric_value": 8.7},
    ])
    result = estimate_lab_pick_date(
        current,
        history,
        [
            {"year": 2024, "variety": "Nerello Mascalese", "pick_date": date(2024, 9, 23)},
            {"year": 2025, "variety": "Nerello Mascalese", "pick_date": date(2025, 9, 23)},
        ],
        "Nerello Mascalese",
    )
    assert result["usable"] is True
    assert result["comparison_count"] == 2
    assert result["available_comparison_count"] == 4
    assert result["vintages"] == [2024, 2025]
    assert result["confidence"] == "medium"


def test_lab_timing_does_not_double_count_derived_potential_alcohol() -> None:
    current = {"analytes": {
        "babo": {"latest_value": 19.8, "latest_date": date(2026, 9, 4)},
        "potential_alcohol": {"latest_value": 13.05, "latest_date": date(2026, 9, 4)},
        "ph": {"latest_value": 3.21, "latest_date": date(2026, 9, 4)},
    }}
    history = [
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "babo", "numeric_value": 19.7},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "potential_alcohol", "numeric_value": 13.0},
        {"vintage_year": 2025, "lab_date": date(2025, 9, 15), "sample_name": "Nerello", "analyte_code": "ph", "numeric_value": 3.14},
    ]
    result = estimate_lab_pick_date(current, history, [{"year": 2025, "variety": "Nerello", "pick_date": date(2025, 9, 23)}], "Nerello")
    assert result["usable"] is True
    assert result["comparisons"][0]["shared_markers"] == ["babo", "ph"]
    assert result["correlated_markers_excluded"] == ["potential_alcohol"]


def test_lab_timing_uses_one_coherent_latest_report_and_exposes_missing_malic_history() -> None:
    current = {"analytes": {
        "babo": {"latest_value": 19.8, "latest_date": date(2026, 9, 4)},
        "ph": {"latest_value": 3.21, "latest_date": date(2026, 9, 4)},
        "malic": {"latest_value": 3.33, "latest_date": date(2026, 9, 4)},
        "ta": {"latest_value": 8.5, "latest_date": date(2026, 8, 20)},
    }}
    history = [
        {"vintage_year": year, "lab_date": date(year, 9, 15), "sample_name": "Nerello", "analyte_code": "babo", "numeric_value": 19.7}
        for year in (2024, 2025)
    ] + [
        {"vintage_year": year, "lab_date": date(year, 9, 15), "sample_name": "Nerello", "analyte_code": "ph", "numeric_value": 3.14}
        for year in (2024, 2025)
    ]
    result = estimate_lab_pick_date(current, history, [
        {"year": 2024, "variety": "Nerello", "pick_date": date(2024, 9, 23)},
        {"year": 2025, "variety": "Nerello", "pick_date": date(2025, 9, 23)},
    ], "Nerello")
    assert result["usable"] is True
    assert result["current_markers"] == ["babo", "malic", "ph"]
    assert result["unmatched_current_markers"] == ["malic"]
    assert result["confidence"] == "low"


def test_harvest_date_fusion_applies_lab_evidence_once() -> None:
    low = fuse_harvest_dates(date(2026, 9, 20), {"usable": True, "confidence": "low", "predicted_pick_date": date(2026, 9, 10)})
    medium = fuse_harvest_dates(date(2026, 9, 20), {"usable": True, "confidence": "medium", "predicted_pick_date": date(2026, 9, 10)})
    assert low == {"date": date(2026, 9, 14), "lab_date": date(2026, 9, 10), "lab_weight": 0.6, "adjustment_days": -6}
    assert medium == {"date": date(2026, 9, 13), "lab_date": date(2026, 9, 10), "lab_weight": 0.7, "adjustment_days": -7}


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
