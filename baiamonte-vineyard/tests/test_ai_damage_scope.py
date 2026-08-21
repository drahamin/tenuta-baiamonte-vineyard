import json

from app.intelligence import _damage_event_photo_prompt, _observation_photo_patch, _photo_analysis_prompt


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
    assert "Agronomist approval" in prompt
