from pathlib import Path

from app.intelligence import apply_disease_calibration, calculate_disease_pressure


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_disease_calibration_is_bounded_and_disease_specific():
    parameters = {"disease_corrections": {
        "downy_mildew": {"adjustment": 12.5},
        "powdery_mildew": {"adjustment": -40},
    }}
    assert apply_disease_calibration(45, "downy_mildew", parameters) == (57.5, 12.5)
    assert apply_disease_calibration(10, "powdery_mildew", parameters) == (0.0, -10.0)
    assert apply_disease_calibration(45, "botrytis", parameters) == (45.0, 0.0)


def test_rules_baseline_is_preserved_beside_calibrated_score():
    rows = calculate_disease_pressure(
        {"temp_avg_c": 24, "temp_max_c": 29, "humidity_avg_pct": 70, "rain_72h_mm": 4, "rain_7d_mm": 8},
        {"disease_corrections": {"downy_mildew": {"adjustment": 8}}},
    )
    downy = next(row for row in rows if row["disease_code"] == "downy_mildew")
    assert downy["risk_score"] == min(100, downy["base_risk_score"] + 8)
    assert downy["calibration_adjustment"] == downy["risk_score"] - downy["base_risk_score"]


def test_durable_disease_learning_is_connected_to_all_prediction_consumers():
    migration = read("db/migrations/122_disease_pressure_learning.sql")
    intelligence = read("app/intelligence.py")
    main = read("app/main.py")
    routes = read("app/domains/disease_routes.py")
    monitor = read("app/domains/learning_monitor.py")
    quick_entry = read("app/quick_entry.py")
    scouting = read("app/static/assets/scouting.js")
    assert "disease_pressure_learning_cases" in migration
    assert "disease_pressure_learning_models" in migration
    assert "def fit_disease_pressure_model" in intelligence
    assert "calculate_disease_pressure(row, disease_parameters)" in intelligence
    assert "fit_disease_pressure_model()" in quick_entry
    assert "fit_disease_pressure_model()" in main
    assert "disease_pressure_learning_status()" in monitor
    assert "/api/v1/disease-pressure/learning-status" in routes
    assert "Agronomist corrected risk score" in scouting


def test_learning_contract_uses_held_out_validation_and_guardrails():
    intelligence = read("app/intelligence.py")
    assert "leave-one-case-out calibration error" in intelligence
    assert "maximum_adjustment_points" in intelligence
    assert "shrinkage_prior_cases" in intelligence
    assert "count >= 8 and len(seasons) >= 2 and improves" in intelligence
