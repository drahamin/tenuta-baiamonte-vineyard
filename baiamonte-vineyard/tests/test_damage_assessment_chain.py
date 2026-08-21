from pathlib import Path

from app.production_impact import apply_damage_adjustments


ROOT = Path(__file__).resolve().parents[1]


def _forecast():
    return [{"variety_name": "Nerello Mascalese", "grape_kg": 1000}]


def test_latest_approved_follow_up_replaces_prior_event_estimate_without_compounding():
    impacts = [
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-27", "estate_yield_loss_pct": 30, "yield_impact_review_status": "approved", "yield_impact_confidence": "medium"},
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-30", "estate_yield_loss_pct": 40, "yield_impact_review_status": "approved", "yield_impact_confidence": "medium"},
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-08-06", "estate_yield_loss_pct": 12, "yield_impact_review_status": "approved", "yield_impact_confidence": "high"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 880
    assert result["damage_reduction_pct"] == 12
    assert result["damage_evidence_count"] == 1
    assert result["damage_status"] == "approved"


def test_latest_approved_report_without_supported_percentage_clears_prior_model_effect():
    impacts = [
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-30", "estate_yield_loss_pct": 40, "yield_impact_review_status": "approved"},
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-08-06", "estate_yield_loss_pct": None, "yield_impact_review_status": "approved"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 1000
    assert result["damage_reduction_pct"] == 0
    assert result["damage_evidence_count"] == 0


def test_damage_chain_is_database_backed_and_editable_in_agronomy():
    migration = (ROOT / "db" / "migrations" / "079_damage_assessment_chain.sql").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    routes = (ROOT / "app" / "domains" / "damage_routes.py").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "assets" / "cellar.js").read_text(encoding="utf-8")
    assert "vineyard_damage_assessments" in migration
    assert "2026-06-27" in migration and "2026-06-30" in migration and "2026-08-06" in migration
    assert '@router.patch("/{assessment_id}"' in routes
    assert '@router.delete("/{assessment_id}"' in routes
    assert 'id="agronomyDamageAssessments"' in html
    assert "data-delete-damage" in script
    assert '"damage_assessment": "vineyard_damage_assessments"' in main
