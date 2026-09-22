from datetime import date

from app.domains.laboratory import _build_lab_decision_support, _decision_analyte_key


def _result(code: str, name: str, value: float, unit: str) -> dict:
    return {
        "analyte_code": code,
        "analyte_name": name,
        "numeric_value": value,
        "unit": unit,
    }


def test_latest_nerello_report_produces_harvest_and_apa_decision_support() -> None:
    sample = {
        "id": "nerello-2026-09-21",
        "sample_name": "Nerello Mascalese",
        "canonical_sample_name": "nerello mascalese",
        "sample_type": "grape",
        "lab_date": date(2026, 9, 21),
        "laboratory": "New laboratory",
    }
    current = [
        _result("babo", "Grado Babo", 20.60, "°Babo"),
        _result("alcol_potenziale", "Alcol potenziale", 13.60, "% vol"),
        _result("ph", "pH", 3.31, "pH"),
        _result("acidita_totale", "Acidità totale", 7.75, "g/L"),
        _result("acido_malico", "Acido malico", 2.22, "g/L"),
        _result("apa", "APA", 149.20, "mg/L"),
        _result("potassio", "Potassio", 1541, "mg/L"),
        _result("acido_tartarico", "Acido tartarico", 9.19, "g/L"),
    ]
    previous = [
        {**_result("babo", "Grado Babo", 20.45, "°Babo"), "lab_date": date(2026, 9, 14), "vintage_year": 2026},
        {**_result("ph", "pH", 3.26, "pH"), "lab_date": date(2026, 9, 14), "vintage_year": 2026},
        {**_result("acidita_totale", "Acidità totale", 8.20, "g/L"), "lab_date": date(2026, 9, 14), "vintage_year": 2026},
        {**_result("acido_malico", "Acido malico", 2.26, "g/L"), "lab_date": date(2026, 9, 14), "vintage_year": 2026},
    ]
    historical = [
        {**_result("babo", "Grado Babo", 20.40, "°Babo"), "lab_date": date(2025, 9, 22), "vintage_year": 2025},
        {**_result("ph", "pH", 3.16, "pH"), "lab_date": date(2025, 9, 22), "vintage_year": 2025},
    ]

    decision = _build_lab_decision_support(
        sample,
        current,
        previous,
        historical,
        {"planned_pick_date": date(2026, 9, 25), "status": "planned", "weather_risk": "Recheck rain"},
        {
            "final_forecast_date": date(2026, 9, 24),
            "confidence": "low",
            "calibration_evidence": '{"forecast_rain_7d_mm": 4.2, "forecast_high_7d_c": 27}',
        },
    )

    assert decision["status"] == "supports_near_term_harvest"
    assert "2026-09-25" in decision["overall_assessment"]
    assert decision["apa_yan"]["value"] == 149.2
    assert decision["apa_yan"]["category"] == "adequate_to_borderline"
    assert decision["apa_yan"]["automatic_addition_approved"] is False
    assert decision["harvest"]["model_pick_date"] == "2026-09-24"
    assert decision["harvest"]["weather"]["forecast_rain_7d_mm"] == 4.2
    assert any("Phenolic maturity" in item for item in decision["missing_evidence"])
    assert any("representative must" in item for item in decision["next_actions"])
    babo = next(item for item in decision["measurements"] if item["decision_key"] == "babo")
    assert round(babo["change"], 2) == 0.15
    assert babo["historical_value"] == 20.4


def test_new_laboratory_italian_labels_normalize_for_decision_support() -> None:
    assert _decision_analyte_key(_result("alcol_potenziale", "Alcol potenziale", 13.6, "% vol")) == "potential_alcohol"
    assert _decision_analyte_key(_result("acidita_totale", "Acidità totale", 7.75, "g/L")) == "total_acidity"
    assert _decision_analyte_key(_result("azoto_prontamente_assimilabile", "APA", 149.2, "mg/L")) == "yan"
    assert _decision_analyte_key(_result("potassio", "Potassio", 1541, "mg/L")) == "potassium"


def test_white_apa_uses_white_thresholds_without_authorizing_addition() -> None:
    decision = _build_lab_decision_support(
        {
            "id": "white",
            "sample_name": "Grecanico",
            "canonical_sample_name": "grecanico",
            "sample_type": "must",
            "lab_date": date(2026, 9, 10),
        },
        [_result("apa", "APA", 149, "mg/L")],
        [],
        [],
    )
    assert decision["apa_yan"]["category"] == "low"
    assert decision["apa_yan"]["automatic_addition_approved"] is False
    assert decision["status"] == "process_review"
