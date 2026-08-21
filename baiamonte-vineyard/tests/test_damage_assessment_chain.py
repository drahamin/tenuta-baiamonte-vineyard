from pathlib import Path

from app.production_impact import apply_damage_adjustments, build_scouting_damage_proposal
from app.domains import projections as projection_domain


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


def test_later_qualitative_report_does_not_erase_prior_approved_percentage():
    impacts = [
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-30", "estate_yield_loss_pct": 40, "yield_impact_review_status": "approved"},
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-08-06", "estate_yield_loss_pct": None, "yield_impact_review_status": "approved"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 600
    assert result["damage_reduction_pct"] == 40
    assert result["damage_evidence_count"] == 1


def test_structured_ai_first_estimate_guides_forecast_until_agronomist_confirms():
    impacts = [{
        "damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-27",
        "estate_yield_loss_pct": 35, "yield_impact_review_status": "draft", "source_type": "photo_ai_chain",
        "yield_impact_confidence": "low",
    }]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 650
    assert result["damage_reduction_pct"] == 35
    assert result["damage_status"] == "provisional"
    assert result["damage_forecast_basis"] == "ai_provisional"
    assert result["damage_confirmation_required"] is True


def test_later_system_recalculation_does_not_replace_approved_chain_final():
    impacts = [
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-27",
         "estate_yield_loss_pct": 40, "yield_impact_review_status": "approved", "source_type": "field_report",
         "yield_impact_confidence": "medium"},
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-08-21",
         "estate_yield_loss_pct": 25, "yield_impact_review_status": "draft", "source_type": "photo_ai_chain",
         "yield_impact_confidence": "high"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 600
    assert result["damage_reduction_pct"] == 40
    assert result["damage_status"] == "approved"
    assert result["damage_forecast_basis"] == "approved_assessment"
    assert result["damage_confirmation_required"] is False


def test_unstructured_draft_never_changes_the_forecast():
    impacts = [{
        "damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-27",
        "estate_yield_loss_pct": 35, "yield_impact_review_status": "draft", "source_type": "field_report",
    }]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 1000
    assert result["damage_evidence_count"] == 0


def test_damage_is_isolated_to_the_matching_vintage():
    forecasts = [
        {"vintage_year": 2026, "variety_name": "Nerello Mascalese", "grape_kg": 1000},
        {"vintage_year": 2027, "variety_name": "Nerello Mascalese", "grape_kg": 1000},
    ]
    impacts = [{
        "damage_event_id": "hail-2026", "vintage_year": 2026, "damage_type": "hail",
        "observed_date": "2026-08-06", "estate_yield_loss_pct": 20,
        "yield_impact_review_status": "approved",
    }]
    result = apply_damage_adjustments(forecasts, impacts)
    assert result[0]["adjusted_grape_kg"] == 800
    assert result[1]["adjusted_grape_kg"] == 1000
    assert result[1]["damage_evidence_count"] == 0


def test_provisional_or_unkeyed_scouting_never_changes_production():
    impacts = [
        {"block_id": "B1", "damage_type": "hail", "observed_date": "2026-06-27", "severity": "high", "affected_area_pct": 100, "estimated_yield_loss_pct": 45, "yield_impact_review_status": "provisional"},
        {"block_id": "B1", "damage_type": "hail", "observed_date": "2026-06-30", "severity": "high", "affected_area_pct": 100, "estimated_yield_loss_pct": 45, "yield_impact_review_status": "approved"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts, {"Nerello Mascalese": 1})[0]
    assert result["adjusted_grape_kg"] == 1000
    assert result["damage_reduction_pct"] == 0
    assert result["damage_evidence_count"] == 0


def test_scouting_photo_estimate_builds_review_only_block_variety_proposal():
    proposal = build_scouting_damage_proposal(
        {
            "block_id": "B1", "observed_at": "2026-08-20 09:00:00", "damage_type": "hail",
            "affected_area_pct": 40, "estimated_yield_loss_pct": 50,
            "yield_impact_confidence": "medium", "yield_impact_source": "photo_ai",
        },
        [{
            "block_code": "N1", "variety_id": "V1", "variety_name": "Nerello Mascalese",
            "block_variety_area_ha": 0.5, "total_variety_area_ha": 2.0,
        }],
        "hail-2026",
    )
    option = proposal["recommended_option"]
    assert proposal["review_status"] == "provisional"
    assert option["proposed_variety_loss_pct"] == 20
    assert option["proposed_estate_loss_pct"] == 5
    assert "does not change harvest quantities" in proposal["guardrail"]


def test_reported_zone_area_scales_the_local_ai_percentage():
    proposal = build_scouting_damage_proposal(
        {
            "block_id": "B1", "damage_scope": "zone", "reported_zone_area_ha": 0.1,
            "observed_at": "2026-08-20 09:00:00", "damage_type": "hail",
            "affected_area_pct": 40, "estimated_yield_loss_pct": 50,
        },
        [{
            "block_code": "N1", "variety_id": "V1", "variety_name": "Nerello Mascalese",
            "block_variety_area_ha": 0.5, "total_variety_area_ha": 2.0,
        }],
        "hail-2026",
    )
    option = proposal["recommended_option"]
    assert option["scope_label"] == "Reported sub-zone"
    assert option["block_variety_area_ha"] == 0.1
    assert option["proposed_variety_loss_pct"] == 20
    assert option["proposed_estate_loss_pct"] == 1


def test_whole_estate_representative_survey_creates_estate_scope_proposal():
    proposal = build_scouting_damage_proposal(
        {
            "damage_scope": "estate", "representative_survey": 1,
            "observed_at": "2026-08-20 09:00:00", "damage_type": "hail",
            "affected_area_pct": 30, "estimated_yield_loss_pct": 50,
        },
        [],
        "hail-2026-06-27",
    )
    option = proposal["recommended_option"]
    assert option["scope_type"] == "estate"
    assert option["variety_id"] is None
    assert option["proposed_estate_loss_pct"] == 15
    assert proposal["event_key"] == "hail-2026-06-27"


def test_overlapping_estate_loss_assessments_use_the_strongest_not_compounding():
    impacts = [
        {"damage_event_id": "hail-2026", "damage_type": "hail", "observed_date": "2026-06-30", "estate_yield_loss_pct": 20, "yield_impact_review_status": "approved"},
        {"damage_event_id": "heat-2026", "damage_type": "sunburn_heat", "observed_date": "2026-07-15", "estate_yield_loss_pct": 10, "yield_impact_review_status": "approved"},
    ]
    result = apply_damage_adjustments(_forecast(), impacts)[0]
    assert result["adjusted_grape_kg"] == 800
    assert result["damage_reduction_pct"] == 20


def test_approved_variety_scope_affects_only_the_selected_variety():
    forecasts = [
        {"vintage_year": 2026, "variety_name": "Nerello Mascalese", "grape_kg": 1000},
        {"vintage_year": 2026, "variety_name": "Grecanico", "grape_kg": 1000},
    ]
    impacts = [{
        "damage_event_id": "hail-2026", "vintage_year": 2026, "damage_type": "hail",
        "scope_type": "variety", "variety_name": "Nerello Mascalese",
        "affected_area_pct": 50, "estimated_yield_loss_pct": 40,
        "yield_impact_review_status": "approved",
    }]
    result = apply_damage_adjustments(forecasts, impacts)
    assert result[0]["adjusted_grape_kg"] == 800
    assert result[1]["adjusted_grape_kg"] == 1000


def test_latest_block_supplement_replaces_prior_report_and_scales_by_variety_area():
    impacts = [
        {
            "damage_event_id": "hail-2026", "vintage_year": 2026, "damage_type": "hail",
            "scope_type": "block_variety", "block_id": "B1", "variety_name": "Nerello Mascalese",
            "variety_area_ha": 0.5, "observed_date": "2026-06-30",
            "affected_area_pct": 100, "estimated_yield_loss_pct": 40,
            "yield_impact_review_status": "approved",
        },
        {
            "damage_event_id": "hail-2026", "vintage_year": 2026, "damage_type": "hail",
            "scope_type": "block_variety", "block_id": "B1", "variety_name": "Nerello Mascalese",
            "variety_area_ha": 0.5, "observed_date": "2026-08-06",
            "affected_area_pct": 50, "estimated_yield_loss_pct": 20,
            "yield_impact_review_status": "approved",
        },
    ]
    result = apply_damage_adjustments(_forecast(), impacts, {"Nerello Mascalese": 2.0})[0]
    assert result["adjusted_grape_kg"] == 975
    assert result["damage_reduction_pct"] == 2.5
    assert result["damage_evidence_count"] == 1


def test_projection_consumers_reconcile_to_adjusted_blend(monkeypatch):
    monkeypatch.setattr(projection_domain, "adjust_production_forecasts", lambda rows, year: rows)
    blend_program = {
        "settings": {"expected_yield_l_per_kg": 0.7, "crate_weight_kg": 15, "grecanico_variety_name": "Grecanico", "nerello_variety_name": "Nerello Mascalese", "grenache_variety_name": "Grenache"},
        "planning": {
            "nerello_kg": 800, "grenache_available_kg": 200, "grecanico_kg": 500,
            "required_grenache_kg": 80, "remaining_grenache_kg": 120, "nerello_pct": 90,
            "wines": [
                {"finished_wine": "Nerello blend", "composition": "90/10", "grape_kg": 880, "wine_l": 616, "bottles_750ml": 821},
                {"finished_wine": "Grecanico", "composition": "100%", "grape_kg": 500, "wine_l": 350, "bottles_750ml": 466},
                {"finished_wine": "Grenache", "composition": "100%", "grape_kg": 120, "wine_l": 84, "bottles_750ml": 112},
            ],
        },
    }
    payload = projection_domain.build_operational_projections(
        2026,
        {"vintages": [], "blend_plans": [{"target_grapes_kg": 2000, "estimated_volume_l": 1400, "estimated_crates": 134}], "metrics": {"planned_kg": 2000, "harvested_kg": 0}, "varieties": []},
        blend_program,
        0.6,
        {"recommended_scenario_range_pct": 15},
        [{"vintage_year": 2026, "variety_name": "Nerello Mascalese", "grape_kg": 800}, {"vintage_year": 2026, "variety_name": "Grenache", "grape_kg": 200}, {"vintage_year": 2026, "variety_name": "Grecanico", "grape_kg": 500}],
    )
    assert next(row for row in payload["scenarios"] if row["name"] == "Working")["grapes_kg"] == 1500
    assert payload["production_forecast_totals"][0]["grape_kg"] == 1500
    assert sum(row["total_kg"] for row in payload["grape_allocations"]) == 1500
    assert sum(row["grape_kg"] for row in payload["wine_outputs"]) == 1500
    assert sum(row["wine_l"] for row in payload["wine_outputs"]) == 1050


def test_damage_chain_is_database_backed_and_editable_in_agronomy():
    migration = (ROOT / "db" / "migrations" / "079_damage_assessment_chain.sql").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    routes = (ROOT / "app" / "domains" / "damage_routes.py").read_text(encoding="utf-8")
    production = (ROOT / "app" / "production_impact.py").read_text(encoding="utf-8")
    reliability_migration = (ROOT / "db" / "migrations" / "080_reliable_damage_reduction.sql").read_text(encoding="utf-8")
    proposal_migration = (ROOT / "db" / "migrations" / "081_damage_reduction_proposals.sql").read_text(encoding="utf-8")
    scope_migration = (ROOT / "db" / "migrations" / "082_ai_damage_zone_scope.sql").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "assets" / "cellar.js").read_text(encoding="utf-8")
    assert "vineyard_damage_assessments" in migration
    assert "2026-06-27" in migration and "2026-06-30" in migration and "2026-08-06" in migration
    assert '@router.patch("/{assessment_id}"' in routes
    assert "request_harvest_refresh" in routes
    assert '"prediction_refresh_queued"' in routes
    assert '"forecast_impact"' in routes
    assert "Enter the Agronomist final yield-loss percentage before approving" in routes
    assert '@router.delete("/{assessment_id}"' in routes
    assert 'require_discipline_approval(request, "agronomy")' in routes
    assert "Assessment date cannot be in the future" in routes
    assert "scope_type ENUM('estate','variety','block_variety')" in reliability_migration
    assert "damage_proposal_json JSON" in proposal_migration
    assert "source_scouting_id CHAR(36)" in proposal_migration
    assert "damage_scope ENUM('zone','block','variety','estate')" in scope_migration
    assert "CREATE TABLE IF NOT EXISTS scouting_damage_scopes" in scope_migration
    assert "REFERENCES scouting_observations(id) ON DELETE CASCADE" in scope_migration
    assert "ALTER TABLE scouting_observations" not in scope_migration
    assert "the 2026 hailstorm event chain is estate-wide" in scope_migration
    confirmation_migration = (ROOT / "db" / "migrations" / "085_hail_damage_confirmation_semantics.sql").read_text(encoding="utf-8")
    assert "affected_area_pct=100.00" in confirmation_migration
    assert "Photo evidence confirms visible hail damage" in confirmation_migration
    assert "Estate coverage is not a 100% harvest loss" in confirmation_migration
    assert "estate_yield_loss_pct=40.00" in confirmation_migration
    assert "Authoritative Agronomist estimate" in confirmation_migration
    intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert "geographic event coverage is 100% of the estate" in intelligence
    assert "always provide a" in intelligence and "provisional central estimate and low/high bounds" in intelligence
    assert "100.0 if scope_type == \"estate\" else damage" in intelligence
    assert "damage_event_photo_analysis_retry" in intelligence
    assert "Estimate crop-unit damage incidence and loss severity" in intelligence
    assert 'retry_parsed["first_pass"] = parsed' in intelligence
    assert "waiting_for_sibling_photos" in intelligence
    assert '"damage_prediction": damage_chain_result' in intelligence
    assert 'analyze_damage_event_evidence(' in intelligence
    assert '"approved_prior": prior_estimate' in intelligence
    assert '"independent_photo_estimate_pct": independent_reduction' in intelligence
    assert 'posterior_yield_loss_pct' in intelligence
    forecast_adjustment = production.split("def adjust_production_forecasts", 1)[1]
    assert "FROM scouting_observations" not in forecast_adjustment
    assert "FROM vineyard_damage_assessments" in forecast_adjustment
    assert 'id="agronomyDamageAssessments"' in html
    assert 'id="agronomyDamageProposals"' in html
    assert 'id="agronomyDamageEventChains"' in html
    assert '@router.post("/from-scouting/{observation_id}"' in routes
    assert '@router.post("/event-ai-assessment"' in routes
    assert "calculate_only" in routes
    assert "data-delete-damage" in script
    assert "data-promote-proposal" in script
    assert "Supplementary assessment created" in script
    assert "Re-run independent system assessment" in script
    assert "change_from_previous_ai_pct_points" in script
    assert "Independent system estimate" in script
    assert "Re-run independent system assessment" in script
    assert "photos are not repeated here" in script
    assert "isSystemAssessment?rowPct:systemPct" in script
    assert "Approved chain final" in script
    assert "Approve as new final" in script
    assert "Agronomist approved yield loss %" in script
    assert "Agronomist value saved; yield and harvest forecasts recalculated" in script
    assert "recalculation creates a proposal and never replaces the approved final automatically" in script
    assert "System refinement" in script
    assert "refinementMap" in script
    assert 'data-view="damage"' in html
    assert 'id="view-damage"' in html
    assert "This report · Agronomist result" in script
    assert "This report · system estimate" in script
    assert "Change from prior report" in script
    damage_view = html.split('id="view-damage"', 1)[1].split('id="view-agronomy"', 1)[0]
    field_view = html.split('id="view-agronomy"', 1)[1].split('id="view-projections"', 1)[0]
    assert 'id="agronomyDamageAssessments"' in damage_view
    assert 'id="agronomyDamageAssessments"' not in field_view
    assert '"report_count": len(chain["reports"])' in routes
    assert '"photo_count": len(evidence_urls)' in routes
    assert '"forecast_basis": "agronomist_approved" if agronomist else "ai_provisional" if ai else "none"' in routes
    assert "proposal_pending_approval" in routes
    assert "Agronomist final" in script
    assert "Independent system estimate" in script
    assert "estimate_comparison" in routes
    assert 'name="scope_type"' in script
    assert 'name="affected_area_pct"' in script
    assert "approvedInput.readOnly=true" in script
    assert '"damage_assessment": "vineyard_damage_assessments"' in main


def test_authoritative_hail_occurrence_and_treatment_five_are_reconciled():
    migration = (ROOT / "db" / "migrations" / "094_authoritative_hail_date_and_treatment_5.sql").read_text(encoding="utf-8")
    routes = (ROOT / "app" / "domains" / "damage_routes.py").read_text(encoding="utf-8")
    reference_chains = (ROOT / "app" / "domains" / "reference_chains.py").read_text(encoding="utf-8")
    treatment_domain = (ROOT / "app" / "domains" / "treatments.py").read_text(encoding="utf-8")
    script = (ROOT / "app" / "static" / "assets" / "cellar.js").read_text(encoding="utf-8")

    assert "event_key='hail-2026-06-26'" in migration
    assert "event_date='2026-06-26'" in migration
    assert "application_date='2026-06-27 12:00:00'" in migration
    assert "water_volume_l=400" in migration
    assert "status='completed'" in migration
    assert "SELECT 'RESOLVE' product_name,500 dose_amount,'g/100 L' dose_unit,2000 total_used" in migration
    assert "SELECT 'MICROTHIOL DISPERSS',450,'g/100 L',1800" in migration
    assert "SELECT 'OSSICLOR 35 WG',340,'g/100 L',1360" in migration
    assert "SELECT 'FRONTIERE',150,'ml/100 L',600" in migration
    assert "SELECT 'REPENTE',300,'ml/100 L',1200" in migration
    assert "SELECT 'GEL DI SILICE',450,'ml/100 L',1800" in migration
    assert "INSERT INTO inventory_movements" in migration
    assert '"event_date": row.get("event_date")' in routes
    assert "MIN(a.event_date) first_date" in reference_chains
    assert "a.event_date,a.damage_type issue_type" in treatment_domain
    assert "Occurred ${new Date" in script
    nutrition_migration = (ROOT / "db" / "migrations" / "095_annual_vineyard_nutrition_baseline.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS crop_nutrition_baselines" in nutrition_migration
    assert "crop_scope ENUM('vineyard','olives')" in nutrition_migration
    assert "annual evidence-and-review baseline" in nutrition_migration
    assert "operator_name=NULL" in nutrition_migration
    nutrition_reliability = (ROOT / "db" / "migrations" / "096_nutrition_workspace_reliability.sql").read_text(encoding="utf-8")
    assert "actual_details_confirmed=0" in nutrition_reliability
    assert "scope, operator and safety details pending" in nutrition_reliability
    assert "FROM treatment_product_options WHERE estate_id=%s AND crop_scope=%s" in treatment_domain
    assert "FROM product_authorized_uses WHERE crop_scope=%s AND active=1 GROUP BY product_id" not in treatment_domain
