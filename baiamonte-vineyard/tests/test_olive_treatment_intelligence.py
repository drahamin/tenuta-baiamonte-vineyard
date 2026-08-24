from datetime import date
from pathlib import Path

from app.intelligence import calculate_olive_pressure, predict_next_treatment
from app.observation_catalog import reference_catalog


ROOT = Path(__file__).resolve().parents[1]


def test_olive_weather_opens_monitoring_but_not_an_application_score():
    rows = calculate_olive_pressure({
        "temp_avg_c": 24,
        "temp_max_c": 30,
        "humidity_avg_pct": 78,
        "rain_72h_mm": 8,
        "rain_7d_mm": 16,
        "leaf_wetness_avg_pct": 70,
        "olive_growth_stage": "olive_fruit_set",
        "assessment_month": 8,
        "scouting": [],
    })
    assert {row["disease_code"] for row in rows} == {"olive_fly", "olive_peacock_spot"}
    assert all(row["weather_only"] for row in rows)
    assert all(row["risk_score"] <= 44 for row in rows)


def test_matching_olive_field_evidence_can_drive_agronomist_review():
    fly = next(row for row in calculate_olive_pressure({
        "temp_avg_c": 24,
        "temp_max_c": 29,
        "humidity_avg_pct": 65,
        "olive_growth_stage": "olive_fruit_set",
        "assessment_month": 8,
        "scouting": [{
            "issue_type": "olive_fly_trap_activity",
            "severity": "high",
            "incidence_pct": 20,
            "notes": "Olive fly found in trap and fruit checks",
        }],
    }) if row["disease_code"] == "olive_fly")
    assert fly["field_evidence_count"] == 1
    assert fly["weather_only"] is False
    assessment = {
        **fly,
        "id": "olive-assessment",
        "input_snapshot": {
            "weather_observation_count": 7,
            "temp_avg_c": 24,
            "scouting": [{"issue_type": "olive_fly_trap_activity", "notes": "fly in trap"}],
        },
        "evidence_summary": "Olive weather plus current trap and fruit evidence.",
    }
    prediction = predict_next_treatment([], [assessment], date(2026, 8, 24), crop_scope="olives")
    assert prediction["type"] == "field_review"
    assert prediction["target_code"] == "olive_fly"
    assert prediction["weather_only"] is False
    assert prediction["requires_agronomist_approval"] is True


def test_olive_scouting_markers_are_available_to_entry_and_learning():
    issue_codes = {row["code"] for row in reference_catalog()["scouting_issues"]}
    assert {"olive_fly_trap_activity", "olive_fly_fruit_damage", "olive_peacock_spot"} <= issue_codes


def test_olive_dashboard_and_simulator_are_not_short_circuited():
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    tools = (ROOT / "app/static/assets/treatment-tools.js").read_text(encoding="utf-8")
    scouting = (ROOT / "app/static/assets/scouting.js").read_text(encoding="utf-8")
    assert 'pressure = [] if crop_scope == "olives"' not in main
    assert 'treatment_scouting_workflows(year, crop_scope)' in main
    assert "oliveStages" in tools
    assert "olive_fly_trap_activity" in scouting
