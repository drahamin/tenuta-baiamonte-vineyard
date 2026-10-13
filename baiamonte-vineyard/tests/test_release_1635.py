from pathlib import Path

from app.production_capability import summarize_production_capability


ROOT = Path(__file__).parents[1]


def test_production_capability_separates_actuals_vessels_and_legal_scenarios():
    result = summarize_production_capability(
        [{"variety_name": "Grenache", "fruit_kg": 1477.25, "estate_fruit_kg": 399.25, "purchased_fruit_kg": 1078}],
        [{"variety_name": "Grenache", "measured_wine_l": 280, "lot_count": 2, "unmeasured_lot_count": 1}],
        [{"capacity_l": 1000, "occupied_l": 1000}, {"capacity_l": 500, "occupied_l": 280}],
        [{"scenario_code": "conditional", "eligibility_status": "conditional_unverified"}],
    )
    assert result["fruit_received_kg"] == 1477.25
    assert result["measured_wine_l"] == 280
    assert result["full_bottle_equivalents"] == 373
    assert result["streams"][0]["purchased_fruit_kg"] == 1078
    assert result["streams"][0]["observed_l_per_kg"] == 0.19
    assert result["vessels"]["nominal_capacity_l"] == 1500
    assert result["vessels"]["working_capacity_l"] == 1350
    assert result["vessels"]["available_working_capacity_l"] == 70
    assert any("live SIAN" in warning for warning in result["warnings"])


def test_wendy_october_reconciliation_preserves_conflicts_and_unknowns():
    migration = (ROOT / "db/migrations/205_production_capability_and_wendy_october.sql").read_text()
    assert "1164.950" in migration
    assert "1078.000" in migration
    assert "1,079.55" in migration
    assert "1.55 kg discrepancy" in migration
    assert "T-39" in migration
    assert "Babo 17 and 22 C" in migration
    assert "Destination tanks after pressing were blank and remain unrecorded" in migration
    assert "conditional_unverified" in migration
    assert "INSERT IGNORE INTO production_capacity_references" in migration
    assert "FROM estates e\nCROSS JOIN (" in migration
    history_fix = (ROOT / "db/migrations/206_wendy_purchased_crate_history.sql").read_text()
    assert "61 purchased-fruit crates" in history_fix
    assert "excluded from estate vineyard yield/completion" in history_fix


def test_production_capability_is_shown_in_harvest_and_cellar():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/production-capability.js").read_text()
    assert 'id="grapeProductionCapability"' in html
    assert 'id="cellarProductionCapability"' in html
    assert "function renderProductionCapability" in javascript
    assert "Measured production stays separate from planning and documentary maximums" in javascript


def test_release_version_is_1_10_42():
    assert 'version: "1.10.49"' in (ROOT / "config.yaml").read_text()
