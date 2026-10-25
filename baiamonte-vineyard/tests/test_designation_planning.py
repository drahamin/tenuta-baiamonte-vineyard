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
        ]
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
    assert any("Grenache is not an admitted" in error for error in result["errors"])


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
    assert "Designation decision simulator" in html
    assert "Back off Superiore" in html
    assert "Sebastian reconciliation" in html
    assert "designation-plans" in script
    assert "1 kg planned purchased Nerello Cappuccio" in script
    assert "Sebastian 2026 cellar reconciliation" in migration


def test_tv_cellar_hides_empty_containers_and_prioritizes_full_ones():
    script = (ROOT / "app/static/display.js").read_text()
    assert "allTanks.filter(tank=>Number(tank.volume_l||0)>0||Number(tank.level_pct||0)>0)" in script
    assert "Number(b.level_pct||0)-Number(a.level_pct||0)" in script
    assert "empty containers hidden" in script
