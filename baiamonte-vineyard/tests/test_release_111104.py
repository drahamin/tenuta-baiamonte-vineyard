from pathlib import Path

from app.domains.enology_process import mlf_purchase_plan
from app.domains.laffort_catalog import additive_prediction_pipeline


ROOT = Path(__file__).resolve().parents[1]


def test_vp41_purchase_math_preserves_provisional_volume_provenance():
    nerello = mlf_purchase_plan({
        "wine_color": "red", "mlf_volume_min_l": 1600, "mlf_volume_max_l": 1600,
        "mlf_volume_basis": "old_must_estimate", "small_sachet_coverage_l": 250,
    })
    assert nerello["equivalent_small_doses_min"] == 6.4
    assert nerello["whole_small_sachets_min"] == nerello["whole_small_sachets_max"] == 7
    assert nerello["dosing_blocked"] is True

    grenache = mlf_purchase_plan({
        "wine_color": "red", "mlf_volume_min_l": 240, "mlf_volume_max_l": 300,
        "mlf_volume_basis": "illustrative_yield_range", "small_sachet_coverage_l": 250,
    })
    assert grenache["equivalent_small_doses_min"] == 0.96
    assert grenache["equivalent_small_doses_max"] == 1.2
    assert grenache["whole_small_sachets_min"] == 1
    assert grenache["whole_small_sachets_max"] == 2


def test_red_mlf_is_planned_but_dosing_stays_evidence_gated():
    protocol = {
        "id": "vp41", "product_catalog_id": "vp41", "manufacturer": "LALLEMAND OENOLOGY",
        "product_name": "LALVIN VP41 MBR", "product_class": "bacteria", "protocol_name": "VP41 MBR",
        "purpose": "MLF", "wine_colors": "red", "trigger_code": "mlf_inoculation",
        "required_lab_analytes": "ph,malic_acid,lactic_acid,total_so2,free_so2,actual_alcohol,residual_sugar",
        "lab_max_age_days": 3,
    }
    metrics = {code: {"code": code, "value": value, "age_days": 0} for code, value in {
        "ph": 3.35, "malic_acid": 2.0, "lactic_acid": 0.2, "total_so2": 35,
        "free_so2": 5, "actual_alcohol": 13.5, "residual_sugar": 1.0,
    }.items()}
    lot = {
        "wine_color": "red", "stage": "post-fermentation", "volume_l": 1600, "mlf_intent": "allow",
        "mlf_purchase_plan": {"volume_basis": "old_must_estimate", "exact_label_confirmed": False, "suitability_confirmed": False},
    }
    decision = additive_prediction_pipeline(
        lot, [protocol], [{"observed_at": "2026-11-05T10:00:00", "temp_c": 19}], [],
        lab_evidence={"status": "linked", "metrics": metrics, "candidates": []},
    )["decisions"][0]
    joined = " ".join(decision["blockers"])
    assert "exact sachet coverage on the VP41 MBR label" in joined
    assert "current measured wine volume" in joined
    assert "Sebastiano" in joined
    assert decision["operational_status"] == "data_needed"


def test_red_recipe_exposes_explicit_mlf_decision_and_purchase_plan():
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    migration = (ROOT / "db/migrations/235_red_malolactic_vp41_plans.sql").read_text()
    assert "Red-wine malolactic fermentation':'White-wine malolactic fermentation" in frontend
    assert "provisional purchase plan" in frontend
    assert "The 450 L figure included skins and is excluded" in migration
    assert "VP41 1-STEP" in migration
    assert "NM-2026-01','GRN-2026-01" in migration
