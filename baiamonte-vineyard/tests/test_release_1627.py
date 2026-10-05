from pathlib import Path

from app.domains.laffort_catalog import additive_prediction_pipeline


ROOT = Path(__file__).resolve().parents[1]


def _mlf_protocol(trigger: str) -> dict:
    return {
        "id": trigger,
        "product_catalog_id": trigger,
        "manufacturer": "TEST",
        "product_name": "MLF product",
        "product_class": "bacteria" if trigger == "mlf_inoculation" else "nutrient",
        "trigger_code": trigger,
        "protocol_name": "MLF",
        "purpose": "Malolactic fermentation",
        "wine_colors": "white,red",
        "process_stages": "post-fermentation",
        "dose_min": 10,
        "dose_max": 10,
        "dose_unit": "g/hL",
        "dose_verified": 1,
    }


def test_white_mlf_intent_is_persisted_and_exposed():
    assert 'version: "1.10.32"' in (ROOT / "config.yaml").read_text()
    migration = (ROOT / "db/migrations/200_enology_white_mlf_intent.sql").read_text()
    backend = (ROOT / "app/domains/enology_process.py").read_text()
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "ADD COLUMN mlf_intent" in migration
    assert '@router.put("/api/v1/enology/recipe-mlf-intent"' in backend
    assert "White-wine malolactic fermentation" in frontend
    assert "data-mlf-intent" in frontend


def test_white_mlf_products_wait_for_explicit_allow():
    protocols = [_mlf_protocol("mlf_inoculation"), _mlf_protocol("mlf_activation")]
    base = {"id": "white", "wine_color": "white", "stage": "post-fermentation", "volume_l": 1000}
    undecided = additive_prediction_pipeline(base, protocols, [], [])["decisions"]
    blocked = additive_prediction_pipeline({**base, "mlf_intent": "block"}, protocols, [], [])["decisions"]
    allowed = additive_prediction_pipeline({**base, "mlf_intent": "allow"}, protocols, [], [])["decisions"]
    assert all(item["timing_status"] == "not_indicated" for item in undecided)
    assert all(item["timing_status"] == "not_indicated" for item in blocked)
    assert all(item["timing_status"] == "due" for item in allowed)
