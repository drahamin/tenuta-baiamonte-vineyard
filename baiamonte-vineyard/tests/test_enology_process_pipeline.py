from datetime import datetime, timedelta
from pathlib import Path

from app.domains.enology_process import (
    ENOLOGY_ANALYTES,
    additive_volume_projections,
    canonical_enology_analyte,
    fermentation_outlook,
    potential_alcohol_from_babo,
    enology_testing_pipeline,
    next_recommended_lab_tests,
    winemaking_workflow,
)
from app.domains.lab_analyte_mapping import _validated_proposal, mapping_key


ROOT = Path(__file__).resolve().parents[1]


def test_tomorrow_pipeline_contains_exact_requested_tests_and_calculation_boundary():
    pipeline = {item["code"]: item for item in enology_testing_pipeline("pre-harvest")}
    assert set(pipeline) == {"ph", "total_acidity", "babo", "potential_alcohol", "potassium"}
    assert pipeline["potential_alcohol"]["method"] == "calculate_from_babo"
    assert all(pipeline[code]["method"] == "measure" for code in ("ph", "total_acidity", "babo", "potassium"))


def test_enology_analyte_names_are_canonical_bilingual_and_preserve_reported_units():
    assert canonical_enology_analyte("pH") == {"code": "ph", "name": "pH", "unit": "pH"}
    assert canonical_enology_analyte("acidità totale", unit="g/L as tartaric acid") == {
        "code": "total_acidity", "name": "Total acidity / Acidità totale", "unit": "g/L as tartaric acid"
    }
    assert canonical_enology_analyte("grado Babo") == {"code": "babo", "name": "Babo", "unit": "°Babo"}
    assert canonical_enology_analyte("potassio", unit="mg/L")["name"] == "Potassium / Potassio"
    assert canonical_enology_analyte("alcol potenziale calcolato")["unit"] == "% vol"
    assert canonical_enology_analyte("NTU") == {"code": "turbidity", "name": "Turbidity / Torbidità", "unit": "NTU"}
    assert canonical_enology_analyte("catechine")["code"] == "catechins"


def test_new_lab_analyte_ai_mapping_requires_high_confidence_and_safe_units():
    definitions = {"yan": ENOLOGY_ANALYTES["yan"]}
    row = {"numeric_value": 0.124}
    accepted = _validated_proposal(
        {"canonical_code": "yan", "canonical_unit": "mg/L", "conversion_multiplier": 1000, "confidence": 0.97},
        row, definitions,
    )
    assert accepted and accepted["canonical_code"] == "yan"
    assert _validated_proposal(
        {"canonical_code": "yan", "canonical_unit": "kg/L", "conversion_multiplier": 1, "confidence": 0.99},
        row, definitions,
    ) is None
    assert _validated_proposal(
        {"canonical_code": "yan", "canonical_unit": "mg/L", "conversion_multiplier": 1000, "confidence": 0.7},
        row, definitions,
    ) is None
    assert mapping_key("Acidità totale") == "acidita_totale"


def test_enologist_views_keep_each_analyte_and_unit_in_its_own_chart():
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text(encoding="utf-8")
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "`${row.metric_code}|${row.display_unit" in frontend
    assert "enologyChemistryCharts" in page
    assert "enologyFermentationCharts" in page
    assert "enologyAdditiveLedger" in page
    for label in ("Specific gravity", "°Brix", "Temperature", "pH"):
        assert label in frontend


def test_prefermentation_adds_yan_gate_before_nutrient_prediction():
    pipeline = {item["code"] for item in enology_testing_pipeline("pre-fermentation")}
    assert "yan" in pipeline
    assert "turbidity" in pipeline
    assert "catechins" in pipeline


def test_every_recognized_lab_analyte_is_routed_to_a_relative_enology_pipeline():
    routed = {
        item["code"]
        for stage in ("pre-harvest", "pre-fermentation", "fermentation", "post-fermentation")
        for item in enology_testing_pipeline(stage)
    }
    assert set(ENOLOGY_ANALYTES).issubset(routed)


def test_next_lab_panel_includes_necessary_tests_and_does_not_repeat_fresh_ntu():
    tests = next_recommended_lab_tests(
        {"id": "lot-1", "code": "GRC-2026-01-P", "stage": "fermentation", "wine_color": "white"},
        {"metrics": {"yan": {"value": 124, "age_days": 1}, "turbidity": {"value": 90, "unit": "NTU", "age_days": 1}}},
        [{"observed_at": "2026-09-15T18:00:00", "babo": 12.2}],
        now=datetime(2026, 9, 16, 8),
    )
    assert {item["analyte_code"] for item in tests} >= {"ph", "total_acidity", "volatile_acidity"}
    assert all(item["analyte_code"] not in {"yan", "turbidity"} for item in tests)


def test_near_dry_recommendations_are_unique_and_persisted_malo_stage_is_supported():
    near_dry = next_recommended_lab_tests(
        {"id": "lot-1", "code": "RED", "stage": "fermentation", "wine_color": "red"},
        {"metrics": {}},
        [{"observed_at": "2026-09-10T08:00:00", "babo": 18}, {"observed_at": "2026-09-15T08:00:00", "babo": 2}],
        now=datetime(2026, 9, 15, 12),
    )
    codes = [item["analyte_code"] for item in near_dry]
    assert len(codes) == len(set(codes))
    malo = next_recommended_lab_tests(
        {"id": "lot-1", "code": "RED", "stage": "malo", "wine_color": "red"},
        {"metrics": {}}, [], now=datetime(2026, 9, 15, 12),
    )
    assert {item["analyte_code"] for item in malo} >= {"malic_acid", "lactic_acid", "volatile_acidity"}

    pressing = next_recommended_lab_tests(
        {"id": "lot-1", "code": "WHITE", "stage": "fermentation", "process_stage": "pressing", "wine_color": "white"},
        {"metrics": {}}, [], now=datetime(2026, 9, 15, 12),
    )
    pressing_codes = {item["analyte_code"] for item in pressing}
    assert {"turbidity", "catechins", "volatile_acidity"}.issubset(pressing_codes)
    assert "yan" not in pressing_codes


def test_invalid_lab_unit_is_recommended_again_instead_of_satisfying_gate():
    tests = next_recommended_lab_tests(
        {"id": "lot-1", "code": "WHITE", "stage": "must", "wine_color": "white"},
        {"metrics": {"yan": {"value": 0.124, "unit": "kg/L", "age_days": 0, "decision_usable": False, "validation_error": "expected mg/L"}}},
        [], now=datetime(2026, 9, 15, 12),
    )
    yan = next(item for item in tests if item["analyte_code"] == "yan")
    assert yan["result_state"] == "invalid_unit"
    assert "mg/L" in yan["validation_error"]


def test_potential_alcohol_uses_estate_pairs_and_discloses_factor():
    result = potential_alcohol_from_babo(17.0, [
        {"babo": 16.15, "potential_alcohol": 10.65},
        {"babo": 16.71, "potential_alcohol": 11.03},
        {"babo": 16.21, "potential_alcohol": 10.70},
    ])
    assert result["status"] == "calculated"
    assert result["evidence_count"] == 3
    assert result["confidence"] == "medium"
    assert 11.1 < result["value_pct_vol"] < 11.3
    assert result["factor"] > 0


def test_potential_alcohol_refuses_an_unsupported_default_factor():
    result = potential_alcohol_from_babo(17.0, [])
    assert result["status"] == "insufficient_data"
    assert result["value_pct_vol"] is None


def test_fermentation_prediction_requires_two_dated_density_readings():
    result = fermentation_outlook([{"observed_at": "2026-09-03T08:00:00", "density_sg": 1.080}])
    assert result["status"] == "insufficient_data"
    assert result["is_automatic_instruction"] is False


def test_fermentation_prediction_flags_flat_density_for_review():
    start = datetime(2026, 9, 3, 8)
    result = fermentation_outlook([
        {"observed_at": start, "density_sg": 1.080},
        {"observed_at": start + timedelta(days=2), "density_sg": 1.080},
    ], now=start + timedelta(days=2))
    assert result["status"] == "stalled_review"
    assert result["requires_enologist_review"] is True


def test_aging_lot_does_not_show_a_false_active_fermentation_alarm():
    start = datetime(2026, 9, 3, 8)
    result = fermentation_outlook([
        {"observed_at": start, "density_sg": 0.995},
        {"observed_at": start + timedelta(days=2), "density_sg": 0.998},
    ], now=start + timedelta(days=2), stage="aging")
    assert result["status"] == "not_applicable"
    assert result["requires_enologist_review"] is False
    assert "aging" in result["message"]


def test_additive_projection_uses_lot_volume_only_for_supported_g_per_hl_rates():
    lot = {"wine_color": "white", "volume_l": 850}
    catalog = [
        {"id": "yeast", "name": "Zymaflor Alpha", "additive_type": "yeast", "wine_color": "white", "proposed_rate": 30, "proposed_rate_unit": "g/hL"},
        {"id": "nutrient", "name": "Yeast nutrient", "additive_type": "nutrient", "wine_color": "any", "proposed_rate": 20, "proposed_rate_unit": "g/hL"},
    ]
    projections = {row["id"]: row for row in additive_volume_projections(lot, catalog, [])}
    assert projections["yeast"]["projected_quantity"] == 255
    assert projections["yeast"]["projected_unit"] == "g"
    assert projections["yeast"]["requires_enologist_approval"] is False
    assert projections["yeast"]["operator_record_is_authoritative"] is True
    assert projections["nutrient"]["projected_quantity"] is None
    assert projections["nutrient"]["projection_status"] == "waiting_for_rule"


def test_winemaking_workflow_blocks_yan_dependent_steps_and_adds_red_pre_press_gate():
    lot = {"wine_color": "red", "volume_l": 1000, "container_code": "T-01", "yan_mg_l": None}
    workflow = {stage["code"]: stage for stage in winemaking_workflow(lot, [], [], [])}
    assert workflow["intake_traceability"]["stage_status"] == "ready"
    assert workflow["must_analysis"]["stage_status"] == "blocked"
    assert workflow["inoculation"]["stage_status"] == "blocked"
    assert workflow["red_pre_press"]["stage_status"] == "blocked"
    assert "PLAUD 2026-09-02" in workflow["red_pre_press"]["source_reference"]


def test_migration_seeds_tomorrow_request_without_faking_results():
    migration = (ROOT / "db/migrations/141_enology_process_models.sql").read_text(encoding="utf-8")
    for analyte in ("ph", "total_acidity", "babo", "potassium", "potential_alcohol"):
        assert analyte in migration
    assert "2026-09-03 07:00:00" in migration
    assert "result_sample_id CHAR(36) NULL" in migration
    assert "do not combine red and white results" in migration


def test_winemaking_stage_migration_and_page_are_present():
    migration = (ROOT / "db/migrations/142_winemaking_stage_control.sql").read_text(encoding="utf-8")
    page = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS enology_stage_events" in migration
    assert "UNIQUE KEY uq_enology_lot_stage" in migration
    assert 'data-enology-panel="winemaking"' in page
    assert 'id="winemakingStageTimeline"' in page
    assert 'id="winemakingAdditiveProjections"' in page
    assert "data-stage-action" in frontend
