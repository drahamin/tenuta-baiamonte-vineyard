from datetime import date
from pathlib import Path

from app.intelligence import predict_next_treatment
from app.prediction_evidence import maturity_evidence_sql, maturity_has_evidence
from tests.source_helpers import backend_source


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_placeholder_maturity_is_not_evidence():
    assert not maturity_has_evidence({
        "sampled_at": "2026-08-15T12:00:00",
        "decision": "monitor",
        "notes": "Replace this template row with first sample.",
    })
    assert maturity_has_evidence({"decision": "monitor", "brix": 19.4})
    assert maturity_has_evidence({"decision": "hold", "notes": None})


def test_maturity_sql_excludes_templates_and_escapes_bound_percent_signs():
    predicate = maturity_evidence_sql("candidate")
    assert "candidate.brix IS NOT NULL" in predicate
    assert "NOT LIKE '%%template%%'" in predicate


def test_treatment_prediction_requires_weather_evidence():
    result = predict_next_treatment([], [{"disease_code": "downy_mildew", "risk_score": 90}], date(2026, 8, 19))
    assert result["type"] == "insufficient_data"
    assert result["risk_level"] == "unknown"


def test_treatment_prediction_is_a_review_not_an_application_instruction():
    assessment = {
        "id": "assessment-1",
        "disease_code": "powdery_mildew",
        "disease_name": "Powdery mildew",
        "risk_score": 36.3,
        "risk_level": "moderate",
        "input_snapshot": {"weather_observation_count": 10, "temp_avg_c": 24.4},
        "evidence_summary": "current weather evidence",
        "suggested_action": "Scout the vineyard.",
    }
    result = predict_next_treatment([], [assessment], date(2026, 8, 19))
    assert result["type"] == "field_review"
    assert result["window_start"] == date(2026, 8, 22)
    assert result["window_end"] == date(2026, 8, 26)
    assert result["requires_agronomist_approval"] is True


def test_rejected_disease_assessment_stops_driving_treatment_prediction():
    assessment = {
        "id": "assessment-rejected", "disease_code": "powdery_mildew", "disease_name": "Powdery mildew",
        "risk_score": 90, "risk_level": "critical", "agronomist_status": "rejected",
        "input_snapshot": {"weather_observation_count": 10, "temp_avg_c": 24.4},
    }
    result = predict_next_treatment([], [assessment], date(2026, 8, 19))
    assert result["type"] == "insufficient_data"
    assert result["risk_level"] == "unknown"


def test_old_overdue_treatment_never_disappears_from_reconciliation():
    result = predict_next_treatment([
        {"id": "old-plan", "status": "planned", "purpose": "Treatment 5", "planned_application_date": "2026-06-01"}
    ], [], date(2026, 8, 19))
    assert result["type"] == "overdue_verification"
    assert result["source_record_id"] == "old-plan"


def test_olive_prediction_never_reuses_vineyard_disease_pressure():
    assessment = {
        "disease_code": "powdery_mildew", "risk_score": 90, "risk_level": "critical",
        "input_snapshot": {"weather_observation_count": 10, "temp_avg_c": 24},
    }
    result = predict_next_treatment([], [assessment], date(2026, 8, 19), crop_scope="olives")
    assert result["type"] == "insufficient_data"
    assert result["risk_level"] == "unknown"
    assert "Vineyard disease-pressure" in result["why"]


def test_prediction_source_contracts_cover_cadence_rain_and_review_filters():
    intelligence = read("app/intelligence.py")
    controls = read("app/process_control.py")
    main = backend_source(ROOT)
    display = read("app/display_data.py")
    assert "CURDATE()-INTERVAL 2 DAY" in intelligence
    assert "FROM maturity_samples m WHERE m.season_id=%s AND m.variety_id=%s" in intelligence
    assert 'maturity_evidence_sql("m")' in intelligence
    assert "stage_name,percent_complete,notes FROM phenology_observations" in intelligence
    assert "sds.ai_zone_yield_reduction_pct" in intelligence
    assert "s.sample_type='grape' AND s.needs_review=0" in intelligence
    assert 'PROCESS_MAX_MINUTES = {"disease": 30}' in controls
    assert "s.sample_type='grape' AND s.needs_review=0" in main
    assert "model_version<>'evidence-screen-v2'" in main
    assert "model_version<>'evidence-screen-v2'" in display
    assert "Database planning records; not a learned forecast model." in main
    assert '"treatments": treatment_dashboard(year, "vineyard", 400.0)' in main
