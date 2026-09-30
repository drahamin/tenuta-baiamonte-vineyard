from pathlib import Path

from app.domains.enology_process import canonical_enology_analyte
from app.domains.laffort_catalog import _sequence_lab_driven_alcohol_adjustment


ROOT = Path(__file__).resolve().parents[1]


def test_italian_malic_and_reducing_sugar_labels_route_without_warning():
    assert canonical_enology_analyte("Acido L-Malico", "Acido L-Malico", "g/L")["code"] == "malic_acid"
    assert canonical_enology_analyte(
        "unmapped-lab-label", "Zuccheri Riduttori (Glucosio+ Fruttosio)", "g/l"
    )["code"] == "residual_sugar"


def test_lab_driven_alcohol_adjustment_follows_completed_cellar_work():
    recipe = {
        "used_products": [
            {"operational_status": "applied", "recipe_role": "fermentation_nutrition", "step_order": 40},
            {"operational_status": "applied", "recipe_role": "fermentation_support", "step_order": 50},
        ],
        "current_actions": [{
            "recipe_role": "alcohol_consistency", "step_order": 20,
            "working_recommendation": {"status": "recommended_now", "quantity": 26.34},
        }],
        "provisional_actions": [], "next_actions": [], "required_inputs": [],
    }
    _sequence_lab_driven_alcohol_adjustment(recipe)
    action = recipe["current_actions"][0]
    assert action["step_order"] == 51
    assert action["process_position"] == "current_lab_driven_adjustment"
    assert "after current laboratory result" in action["process_step"]


def test_compact_lab_request_and_products_used_workspace_are_shipped():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/enology-process.js").read_text()
    css = (ROOT / "app/static/app.css").read_text()
    assert 'data-winemaking-section-button="products"' in html
    assert 'id="copyLabRequest"' in html
    assert 'id="copyProductsUsed"' in html
    assert "renderCompactLabQueue(data,nextNode)" in javascript
    assert "labRequestText(data,tests)" in javascript
    assert "renderEnologyProductsUsed(lot)" in javascript
    assert "streamlined_recipe?.used_products" in javascript
    assert ".compact-lab-lot" in css
    assert ".enology-products-used-list" in css
