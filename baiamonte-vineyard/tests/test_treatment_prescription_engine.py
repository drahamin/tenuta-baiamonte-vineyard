from datetime import date
from pathlib import Path

from app.domains.treatments import calculate_area_mix, select_application_window
from app.intelligence import predict_next_treatment


ROOT = Path(__file__).resolve().parents[1]


def test_area_rate_is_converted_to_total_and_per_100_l_tank_rate():
    result = calculate_area_mix(area_ha=.643, water_l=500, rate_kg_ha=2)
    assert result == {"area_ha": .643, "water_l": 500.0, "rate_kg_ha": 2, "total_kg": 1.286, "per_100_l_g": 257.2}


def test_sulfur_window_rejects_rain_heat_and_high_wind():
    result = select_application_window([
        {"datetime": "2026-08-22", "temperature": 27, "precipitation": 1.5, "wind_speed": 8},
        {"datetime": "2026-08-23", "temperature": 31, "precipitation": 0, "wind_speed": 8},
        {"datetime": "2026-08-24", "temperature": 27, "precipitation": 0, "wind_speed": 18},
    ], date(2026, 8, 22), date(2026, 8, 26), sulfur=True)
    assert result["status"] == "no_suitable_window"
    assert result["recommended_date"] is None


def test_overdue_plan_keeps_current_disease_target_for_new_engine():
    result = predict_next_treatment(
        [{"id": "t5", "status": "planned", "purpose": "Treatment 5", "planned_application_date": "2026-06-26"}],
        [{"id": "pressure", "disease_code": "powdery_mildew", "disease_name": "Powdery mildew", "risk_score": 37.5, "risk_level": "moderate", "input_snapshot": {"weather_observation_count": 554, "temp_avg_c": 24.3}}],
        date(2026, 8, 19),
    )
    assert result["type"] == "overdue_verification"
    assert result["target_code"] == "powdery_mildew"
    assert result["current_risk_score"] == 37.5


def test_purchase_and_label_migration_is_auditable_and_resets_treatment_five():
    migration = (ROOT / "db/migrations/066_treatment_prescription_engine.sql").read_text(encoding="utf-8")
    for invoice, product, quantity in [
        ("1478", "SACRON 45 WG", "1,'kg'"),
        ("1478", "OSSICLOR 35 WG", "10,'kg'"),
        ("1919", "IMPULSIVE", "5,'L'"),
        ("1919", "RESOLVE", "5,'L'"),
        ("1919", "TERRAPLUS SOLUB", "15,'kg'"),
        ("1919", "GEL DI SILICE", "5,'kg'"),
    ]:
        assert invoice in migration
        assert product in migration
        assert quantity in migration
    assert "authorization_status='expired'" in migration
    assert "authorization_expires_on='2026-08-15'" in migration
    assert "LOWER(TRIM(purpose))='treatment 5' AND status='planned'" in migration
    assert "status='cancelled'" in migration
    assert "This is not a completed application" in migration
