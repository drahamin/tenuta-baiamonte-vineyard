from pathlib import Path

import pytest

from app.designation_planning import simulate_designation
from app.quick_entry import validate_cellar_lot_designation


ROOT = Path(__file__).parents[1]


def capability():
    return {
        "streams": [
            {"variety_name": "Nerello Mascalese", "estate_fruit_kg": 1000, "purchased_fruit_kg": 0, "predictive_l_per_kg": 0.67},
            {"variety_name": "Grenache", "estate_fruit_kg": 500, "purchased_fruit_kg": 100, "predictive_l_per_kg": 0.64},
            {"variety_name": "Grecanico", "estate_fruit_kg": 800, "purchased_fruit_kg": 0, "predictive_l_per_kg": 0.68},
        ],
        "legal_scenarios": [
            {"scenario_code": "full-listed-igt-conditional", "scenario_label": "All listed · conditional", "denomination": "Terre Siciliane IGT", "eligibility_status": "conditional_unverified", "grapes_kg": 9106.2, "wine_l": 7284.96, "full_bottles_750ml": 9712},
            {"scenario_code": "grecanico-superiore-conditional", "scenario_label": "Grecanico Superiore", "denomination": "Sicilia DOC Grecanico Superiore", "eligibility_status": "conditional_unverified", "grapes_kg": 1843, "wine_l": 1290.1, "full_bottles_750ml": 1720},
        ],
        "cellar_lots": [],
    }


def test_etna_doc_candidate_supports_documented_one_kg_cappuccio_purchase():
    result = simulate_designation(2026, {
        "designation_code": "etna_doc_rosso",
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "kg": 999},
            {"variety_name": "Nerello Cappuccio", "source_type": "planned_purchase", "kg": 1, "eligibility_documented": True},
        ],
    }, capability())
    assert result["composition_pass"] is True
    assert result["can_lock"] is True
    assert result["legal_entitlement_confirmed"] is False
    assert result["components"][1]["share_pct"] == 0.1


def test_grenache_is_not_silently_allowed_in_etna_doc():
    result = simulate_designation(2026, {
        "designation_code": "etna_doc_rosso",
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "kg": 900},
            {"variety_name": "Grenache", "source_type": "estate", "kg": 100},
        ],
    }, capability())
    assert result["can_lock"] is False
    assert any("Alicante is the recognized Grenache synonym" in error for error in result["errors"])


def test_final_nerello_grenache_blend_can_use_igt_planning_path():
    result = simulate_designation(2026, {
        "designation_code": "terre_siciliane_igt",
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "kg": 1000},
            {"variety_name": "Grenache", "source_type": "estate", "kg": 500},
            {"variety_name": "Grenache", "source_type": "purchased", "kg": 100, "eligibility_documented": True},
        ],
    }, capability())
    assert result["can_lock"] is True
    assert result["predicted_wine_l"] == pytest.approx(1054)


def test_grenache_is_split_between_nerello_blend_and_separate_single_wine():
    result = simulate_designation(2026, {
        "wine_name": "Nerello blend",
        "designation_code": "terre_siciliane_igt",
        "secondary_wine_name": "Grenache single wine",
        "secondary_designation_code": "terre_siciliane_igt",
        "blend_parameters": {"grenache_pct": 10, "estate_grenache_pct": 70},
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "allocation": "final_wine", "kg": 900},
            {"variety_name": "Grenache", "source_type": "estate", "allocation": "final_wine", "kg": 73.28125},
            {"variety_name": "Grenache", "source_type": "purchased", "allocation": "final_wine", "kg": 31.40625, "eligibility_documented": True},
            {"variety_name": "Grenache", "source_type": "estate", "allocation": "grenache_single", "kg": 426.71875},
            {"variety_name": "Grenache", "source_type": "purchased", "allocation": "grenache_single", "kg": 68.59375, "eligibility_documented": True},
        ],
    }, capability())
    assert result["can_lock"] is True
    assert result["total_grapes_kg"] == pytest.approx(1004.688)
    assert result["blend_parameters"]["actual_grenache_pct"] == 10
    assert result["blend_parameters"]["actual_estate_grenache_pct"] == 70
    assert result["secondary_products"][0]["grapes_kg"] == pytest.approx(495.313)
    assert result["all_allocated_grapes_kg"] == 1500
    assert result["legal_production_scenarios"][0]["scenario_code"] == "full-listed-igt-conditional"


def test_combined_allocations_cannot_exceed_one_source_inventory():
    result = simulate_designation(2026, {
        "designation_code": "terre_siciliane_igt",
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "kg": 900},
            {"variety_name": "Grenache", "source_type": "estate", "allocation": "final_wine", "kg": 300},
            {"variety_name": "Grenache", "source_type": "estate", "allocation": "grenache_single", "kg": 300},
        ],
    }, capability())
    assert result["can_lock"] is False
    assert any("600 kg allocated exceeds the 500 kg received" in error for error in result["errors"])


def test_measured_source_lots_drive_blend_then_tails_and_racking_losses():
    source = capability()
    source["cellar_lots"] = [
        {"id": "nm-1", "code": "NM-1", "name": "Nerello 1", "variety_summary": "Nerello Mascalese", "volume_l": 1640},
        {"id": "nm-2", "code": "NM-2", "name": "Nerello 2", "variety_summary": "Nerello Mascalese", "volume_l": 300},
        {"id": "al-1", "code": "AL-1", "name": "Alicante 1", "variety_summary": "Alicante", "volume_l": 250},
        {"id": "al-2", "code": "AL-2", "name": "Alicante 2", "variety_summary": "Grenache", "volume_l": 385},
    ]
    result = simulate_designation(2026, {
        "designation_code": "terre_siciliane_igt",
        "blend_parameters": {"grenache_pct": 10, "estate_grenache_pct": 70},
        "loss_parameters": {"tails_pct": 5, "racking_pct": 3},
        "source_lot_ids": {"nerello": ["nm-1", "nm-2"], "grenache": ["al-1", "al-2"]},
        "components": [
            {"variety_name": "Nerello Mascalese", "source_type": "estate", "kg": 900},
            {"variety_name": "Grenache", "source_type": "estate", "kg": 70},
            {"variety_name": "Grenache", "source_type": "purchased", "kg": 30, "eligibility_documented": True},
        ],
    }, source)
    assert result["output_basis"] == "measured_source_lots"
    assert result["predicted_gross_wine_l"] == pytest.approx(2155.556, abs=.001)
    assert result["loss_waterfall"]["tails_loss_l"] == pytest.approx(107.778, abs=.001)
    assert result["loss_waterfall"]["racking_loss_l"] == pytest.approx(61.433, abs=.001)
    assert result["predicted_finished_wine_l"] == pytest.approx(1986.344, abs=.001)
    assert sum(row["remaining_separate_wine_l"] for row in result["source_lots"] if row["role"] == "grenache") == pytest.approx(419.444, abs=.002)
    assert result["can_lock"] is True


def test_grecanico_can_back_off_superiore_without_a_lab_report():
    result = simulate_designation(2026, {
        "designation_code": "sicilia_doc_grecanico",
        "components": [{"variety_name": "Grecanico", "source_type": "estate", "kg": 800}],
    }, capability())
    assert result["can_lock"] is True
    assert any("does not require a laboratory report" in warning for warning in result["warnings"])


def test_cellar_batch_rejects_grenache_as_etna_doc():
    values = {"designation_intent": "etna_doc_rosso", "variety_summary": "Nerello Mascalese + Grenache"}
    with pytest.raises(ValueError, match="cannot be assigned"):
        validate_cellar_lot_designation(values)


def test_release_contains_prominent_designation_planner_and_reconciliation_evidence():
    html = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/designation-planner.js").read_text()
    migration = (ROOT / "db/migrations/223_vintage_designation_planning.sql").read_text()
    source_migration = (ROOT / "db/migrations/224_designation_source_lots_and_losses.sql").read_text()
    assert "Designation decision simulator" in html
    assert "Back off Superiore" in html
    assert "Sebastian reconciliation" in html
    assert "designation-plans" in script
    assert "1 kg planned purchased Nerello Cappuccio" in script
    assert "blend_grenache_pct" in script
    assert "estateBlendGrenache" in script
    assert "grenache_single" in script
    assert "designationLiveAllocation" in html
    assert "DOCUMENTARY LEGAL PRODUCTION AMOUNT" in script
    assert "designation-reconciliation-compact" in script
    assert "current official Etna Rosso specification" in script
    assert "nerello_source_lot_ids" in script
    assert "tails_loss_pct" in script
    assert "vintage_designation_plan_source_lots" in source_migration
    assert "Sebastian 2026 cellar reconciliation" in migration


def test_tv_cellar_hides_empty_containers_and_prioritizes_full_ones():
    script = (ROOT / "app/static/display.js").read_text()
    assert "allTanks.filter(tank=>Number(tank.volume_l||0)>0||Number(tank.level_pct||0)>0)" in script
    assert "Number(b.level_pct||0)-Number(a.level_pct||0)" in script
    assert "empty containers hidden" in script
