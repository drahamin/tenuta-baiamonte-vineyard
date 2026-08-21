import json

from app.intelligence import _damage_event_photo_prompt, _observation_photo_patch, _photo_analysis_prompt, _photo_harvest_route


def _analysis():
    return {
        "summary": "Visible hail injury across the representative survey.",
        "confidence": 0.91,
        "image_quality": "good",
        "issue_type": "hail injury",
        "damage_type": "hail",
        "severity": "high",
        "zone_damage_pct": 30,
        "zone_damage_low_pct": 20,
        "zone_damage_high_pct": 40,
        "loss_severity_pct": 50,
        "loss_severity_low_pct": 40,
        "loss_severity_high_pct": 60,
        "observed_units": 100,
        "visibly_damaged_units": 30,
        "sample_basis": "100 clusters distributed across the declared estate survey",
        "representativeness": "representative",
        "yield_impact_confidence": "high",
        "uncertainties": ["Hidden fruit is not visible"],
    }


def test_ai_estimate_is_expressed_relative_to_declared_estate_scope():
    patch, reason = _observation_photo_patch(
        "scouting",
        {"damage_scope": "estate", "representative_survey": 1, "location_note": "Whole estate", "severity": "low", "yield_impact_review_status": "provisional"},
        _analysis(),
    )
    assert reason is None
    assert patch["ai_zone_damage_pct"] == 30
    assert patch["ai_zone_damage_low_pct"] == 20
    assert patch["ai_zone_damage_high_pct"] == 40
    assert patch["ai_zone_yield_reduction_pct"] == 15
    assert patch["ai_zone_yield_reduction_low_pct"] == 8
    assert patch["ai_zone_yield_reduction_high_pct"] == 24
    assert patch["affected_area_pct"] == 30
    assert patch["estimated_yield_loss_pct"] == 50
    saved = json.loads(patch["ai_zone_analysis_json"])
    assert saved["scope"] == "estate"
    assert saved["observed_units"] == 100


def test_closeup_cannot_create_whole_estate_percentage_without_representative_survey():
    patch, _ = _observation_photo_patch(
        "scouting",
        {"damage_scope": "estate", "representative_survey": 0, "severity": "low", "yield_impact_review_status": "provisional"},
        _analysis(),
    )
    assert "ai_zone_damage_pct" not in patch
    assert "affected_area_pct" not in patch
    assert "estimated_yield_loss_pct" not in patch


def test_prompt_requires_scope_relative_ranges_and_representative_estate_evidence():
    prompt = _photo_analysis_prompt("scouting", {"damage_scope": "estate", "representative_survey": True})
    assert "zone_damage_low_pct" in prompt
    assert "loss_severity_high_pct" in prompt
    assert "whole-estate scope" in prompt
    assert "representative_survey is true" in prompt
    assert "harvest_relevance" in prompt


def test_event_prompt_updates_the_approved_prior_without_compounding():
    prompt = _damage_event_photo_prompt(
        "hail-2026-06-27", "estate", [],
        {"estimate_pct": 40, "approved_by": "Sebastiano Vinci", "confidence": "medium"},
    )
    assert "latest approved quantitative determination as the prior estimate" in prompt
    assert "Do not restart from zero, average reports, or compound percentages" in prompt
    assert "posterior_yield_loss_pct" in prompt
    assert '"estimate_pct": 40' in prompt


def test_maturity_photo_routes_only_after_ai_finds_visible_ripening_evidence():
    current = {"issue_type": "fruit_maturity", "severity": "low"}
    analysis = {
        "confidence": 0.9,
        "image_quality": "good",
        "harvest_relevance": "maturity_progress",
        "visible_maturity_stage": "veraison",
    }
    queued, reason = _photo_harvest_route("scouting", current, analysis, {"notes": "Visible color change"})
    assert queued is True
    assert "maturity" in reason.lower()


def test_unrelated_photo_does_not_invalidate_harvest_prediction():
    queued, reason = _photo_harvest_route(
        "scouting",
        {"issue_type": "powdery_mildew"},
        {"confidence": 0.93, "image_quality": "good", "harvest_relevance": "none"},
        {"notes": "Possible leaf symptoms"},
    )
    assert queued is False
    assert "did not produce" in reason


def test_scope_aware_damage_photo_can_refresh_yield_prediction():
    queued, reason = _photo_harvest_route(
        "scouting",
        {"issue_type": "hail"},
        {"confidence": 0.91, "image_quality": "good", "harvest_relevance": "yield_risk"},
        {"ai_zone_yield_reduction_pct": 15.0},
    )
    assert queued is True
    assert "yield-risk" in reason


def test_event_chain_prompt_distinguishes_estate_extent_from_uniform_damage():
    prompt = _damage_event_photo_prompt(
        "hail-2026-06-27",
        "estate",
        [{"date": "2026-06-27", "photo_count": 6}, {"date": "2026-08-06", "photo_count": 5}],
    )
    assert "owner-confirmed geographic scope is authoritative" in prompt
    assert "establishes extent only, not uniform severity" in prompt
    assert "zone_damage_low_pct" in prompt
    assert "chronology_summary" in prompt
    assert "report_refinements" in prompt
    assert "Agronomist approval" in prompt
