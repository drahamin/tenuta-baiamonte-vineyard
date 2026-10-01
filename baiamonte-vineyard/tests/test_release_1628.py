from pathlib import Path

from app.domains.laffort_catalog import additive_prediction_pipeline


ROOT = Path(__file__).resolve().parents[1]


def test_passed_stage_recommendations_leave_the_working_recipe():
    protocol = {
        "id": "yeast", "product_catalog_id": "yeast", "manufacturer": "TEST",
        "product_name": "Primary yeast", "product_class": "yeast",
        "protocol_name": "Primary inoculation", "purpose": "Fermentation",
        "wine_colors": "red", "process_stages": "must", "trigger_code": "inoculation",
        "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL", "dose_verified": 1,
    }
    recipe = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "post-fermentation", "volume_l": 1000},
        [protocol], [], [],
    )["streamlined_recipe"]
    assert recipe["current_actions"] == []
    assert recipe["next_actions"] == []
    assert recipe["required_inputs"] == []
    assert recipe["evaluated_actions"] == []
    assert recipe["passed_gate_count"] == 1


def test_variety_recipe_bases_are_decision_sequences_not_product_lists():
    recipe = additive_prediction_pipeline(
        {"variety_summary": "Nerello Mascalese", "wine_color": "red", "stage": "fermentation", "volume_l": 1600},
        [], [], [],
    )["streamlined_recipe"]
    basis = recipe["recipe_basis"]
    assert basis["name"] == "Structured, age-worthy Etna red"
    assert basis["variety_fit"] == "Nerello Mascalese"
    assert any("only" in step for step in basis["decision_sequence"])


def test_actionable_catalog_migration_uses_official_sources_and_gates():
    assert 'version: "1.10.31"' in (ROOT / "config.yaml").read_text()
    migration = (ROOT / "db/migrations/201_actionable_enology_recipe_bases.sql").read_text()
    for product in ("enartisferm es181", "zymaflore f83", "lalvin icv d254", "enartispro tinto", "nutriferm advance"):
        assert product in migration
    assert "Do not recommend merely from variety" in migration
    assert "Do not add after the early fermentation gate" in migration
    assert "Do not repeat automatically" in migration
