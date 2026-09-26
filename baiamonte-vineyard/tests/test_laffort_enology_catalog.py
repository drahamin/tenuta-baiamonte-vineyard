from pathlib import Path

from app.domains.laffort_catalog import (
    LAFFORT_RANGES,
    _normalized_lab_code,
    additive_prediction_pipeline,
    lot_lab_evidence,
    normalize_product_name,
    parse_laffort_range,
    project_product_quantity,
    lot_with_lab_measurements,
    suggest_products,
)
from app.enology_measurements import normalize_enology_measurement
from app.domains.enology_process import canonical_enology_analyte, enology_testing_pipeline, normalize_fermentation_overlay_rows


ROOT = Path(__file__).resolve().parents[1]


def test_ntu_lab_code_routes_to_turbidity_decisions():
    assert _normalized_lab_code("NTU") == "turbidity"
    assert _normalized_lab_code("Torbidità NTU") == "turbidity"


def test_laffort_range_parser_keeps_official_identity_description_and_documents():
    html = '''
    <h2><a href="https://laffort.com/en/products/lafazym-press/">LAFAZYM™ PRESS</a></h2>
    <p>Specific enzyme for white and rosé pressing.</p>
    <a href="/wp-content/uploads/FP/FP_EN_Lafazym_Press.pdf">Consult our product datasheet</a>
    <a href="/wp-content/uploads/SDS/SDS_EN_Lafazym_Press.pdf">Consult our safety datasheet</a>
    '''
    rows = parse_laffort_range(html, range_code="enzymes", range_name="Enzymes", product_class="enzyme", source_url="https://laffort.com/en/ranges/enzyme/")
    assert len(rows) == 1
    assert rows[0]["product_name"] == "LAFAZYM™ PRESS"
    assert rows[0]["normalized_name"] == "lafazym press"
    assert rows[0]["description"] == "Specific enzyme for white and rosé pressing."
    assert rows[0]["pds_url"].endswith("FP_EN_Lafazym_Press.pdf")
    assert rows[0]["sds_url"].endswith("SDS_EN_Lafazym_Press.pdf")


def test_projection_requires_verified_unit_safe_dose():
    product = {"dose_verified": True, "dose_min": 10, "dose_max": 20, "dose_unit": "g/hL", "dose_basis": "official PDS"}
    assert project_product_quantity(850, product) == {"status": "calculated", "minimum": 85.0, "maximum": 170.0, "unit": "g", "basis": "official PDS"}
    assert project_product_quantity(850, {**product, "dose_verified": False})["status"] == "technical_sheet_required"
    assert project_product_quantity(850, {**product, "dose_unit": "drops/barrel"})["status"] == "unsupported_unit"
    assert project_product_quantity(None, product)["status"] == "lot_basis_required"
    fruit_product = {**product, "dose_min": 2, "dose_max": 5, "dose_unit": "g/100kg"}
    assert project_product_quantity(None, fruit_product, fruit_kg=1000) == {
        "status": "calculated", "minimum": 20.0, "maximum": 50.0, "unit": "g", "basis": "official PDS"
    }
    ton_product = {**product, "dose_min": 100, "dose_max": 200, "dose_unit": "g/ton"}
    assert project_product_quantity(None, ton_product, fruit_kg=399.25) == {
        "status": "calculated", "minimum": 39.92, "maximum": 79.85, "unit": "g", "basis": "official PDS"
    }
    enrichment = {**product, "dose_min": 1.68, "dose_max": 1.68, "dose_unit": "kg/hL/%vol"}
    assert project_product_quantity(1069.8, enrichment) == {
        "status": "calculated", "minimum": 17.97, "maximum": 17.97, "unit": "kg", "basis": "official PDS"
    }


def test_alcohol_consistency_recommendation_accounts_for_recorded_grape_must_sugar():
    protocol = {
        "id": "sugar", "product_catalog_id": "sugar-product", "manufacturer": "NATURALIA INGREDIENTS",
        "product_name": "crystalMUSTGRAPE", "product_class": "treatment",
        "protocol_name": "Alcohol consistency", "purpose": "Match estate alcohol target", "wine_colors": "any",
        "process_stages": "must,pre-fermentation,fermentation", "trigger_code": "alcohol_consistency",
        "dose_min": 1.68, "dose_max": 1.68, "dose_unit": "kg/hL/%vol", "dose_basis": "official product sheet",
    }
    lot = {
        "wine_color": "white", "stage": "fermentation", "volume_l": 1069.8,
        "potential_alcohol_pct": 11.5, "target_potential_alcohol_pct": 12.0,
    }
    additions = [{
        "additive_name": "Naturalia crystalMUSTGRAPE solid rectified concentrated grape must",
        "event_status": "applied", "applied_at": "2026-09-17T00:00:00", "quantity": 10, "unit": "kg",
    }]
    labs = {"status": "linked", "candidates": [], "metrics": {
        "potential_alcohol": {"code": "potential_alcohol", "value": 11.5, "unit": "% vol", "sampled_at": "2026-09-16T09:00:00", "age_days": 2},
    }}
    decision = additive_prediction_pipeline(lot, [protocol], [], additions, lab_evidence=labs)["decisions"][0]
    working = decision["working_recommendation"]
    assert working["already_applied_kg_since_measurement"] == 10
    assert working["calculated_current_potential_alcohol_pct"] == 12.056
    assert working["quantity"] == 0
    assert working["status"] == "not_indicated"
    assert working["post_addition_test_recommended"] is True
    assert decision["operational_status"] == "not_indicated"


def test_alcohol_consistency_quantity_is_not_suppressed_by_compliance_warning():
    protocol = {
        "id": "sugar", "product_catalog_id": "sugar-product", "manufacturer": "NATURALIA INGREDIENTS",
        "product_name": "crystalMUSTGRAPE", "product_class": "treatment",
        "protocol_name": "Alcohol consistency", "purpose": "Match estate alcohol target", "wine_colors": "any",
        "process_stages": "must,pre-fermentation,fermentation", "trigger_code": "alcohol_consistency",
        "dose_min": 1.68, "dose_max": 1.68, "dose_unit": "kg/hL/%vol", "dose_basis": "official product sheet",
    }
    result = additive_prediction_pipeline({
        "wine_color": "white", "stage": "must", "volume_l": 225,
        "potential_alcohol_pct": 11.2, "target_potential_alcohol_pct": 12.0,
    }, [protocol], [], [])
    working = result["decisions"][0]["working_recommendation"]
    assert working["quantity"] == 3.02
    assert working["projected_potential_alcohol_pct"] == 12.0
    assert working["status"] == "recommended_now"
    assert "does not alter this calculation" in working["compliance_warning"]


def test_decision_measurements_convert_known_units_and_quarantine_bad_units():
    assert normalize_enology_measurement("yan", 0.124, "g/L") == {
        "usable": True, "value": 124.0, "unit": "mg/L", "reason": None
    }
    assert normalize_enology_measurement("turbidity", 90, "mg/L")["usable"] is False
    lot = lot_with_lab_measurements({}, {"metrics": {
        "yan": {"value": 124, "decision_usable": True},
        "turbidity": {"value": 90, "decision_usable": False},
    }})
    assert lot["yan_mg_l"] == 124
    assert "must_turbidity_ntu" not in lot


def test_suggestions_are_lot_specific_and_nutrients_wait_for_yan():
    products = [
        {"id": "red", "manufacturer": "LAFFORT", "product_name": "ZYMAFLORE F83", "range_name": "Yeast", "product_class": "yeast", "wine_colors": "red", "description": "Mediterranean red yeast for Grenache", "dose_verified": False},
        {"id": "white", "manufacturer": "LAFFORT", "product_name": "ZYMAFLORE X16", "range_name": "Yeast", "product_class": "yeast", "wine_colors": "white,rose", "description": "Aromatic white wine yeast", "dose_verified": False},
        {"id": "nutrient", "manufacturer": "LAFFORT", "product_name": "NUTRISTART", "range_name": "Nutrients", "product_class": "nutrient", "wine_colors": "any", "description": "Fermentation nutrient", "dose_verified": False},
    ]
    suggestions = suggest_products({"wine_color": "red", "variety_summary": "Grenache", "volume_l": 850, "yan_mg_l": None}, products)
    assert suggestions[0]["id"] == "red"
    assert all(row["id"] != "white" for row in suggestions)
    nutrient = next(row for row in suggestions if row["id"] == "nutrient")
    assert "blocked until YAN/APA is measured" in nutrient["suggestion_reason"]
    assert nutrient["is_automatic_instruction"] is False


def test_additive_prediction_forecasts_density_gate_and_quantity_range():
    protocol = {
        "id": "nutrition", "product_name": "NUTRISTART THIOLS", "product_class": "nutrient",
        "protocol_name": "First-third fermentation nutrition", "purpose": "Nutrition", "wine_colors": "white,rose",
        "trigger_code": "density_drop_30", "dose_min": 20, "dose_max": 60, "dose_unit": "g/hL",
        "dose_basis": "Official PDS", "preparation": "Dissolve in must", "application_instructions": "Add at the gate",
    }
    lot = {"wine_color": "white", "stage": "fermentation", "volume_l": 1000, "yan_mg_l": 120, "potential_alcohol_pct": 13, "must_turbidity_ntu": 90}
    result = additive_prediction_pipeline(lot, [protocol], [
        {"observed_at": "2026-09-03T08:00:00", "density_sg": 1.080},
        {"observed_at": "2026-09-04T08:00:00", "density_sg": 1.060},
    ], [], now=__import__("datetime").datetime(2026, 9, 4, 8))
    decision = result["decisions"][0]
    assert decision["decision_status"] == "forecast"
    assert decision["projection"]["minimum"] == 200
    assert decision["projection"]["maximum"] == 600
    assert decision["density_drop_points"] == 20
    assert decision["predicted_for"].isoformat() == "2026-09-04T20:00:00"


def test_babo_progress_drives_dynamic_white_nutrition_and_rejects_unneeded_restart_product():
    protocols = [
        {
            "id": "special", "product_catalog_id": "special", "manufacturer": "ENARTIS",
            "product_name": "NUTRIFERM SPECIAL", "product_class": "nutrient", "protocol_name": "First-third nutrition",
            "purpose": "Nutrition", "wine_colors": "white", "trigger_code": "density_drop_30",
            "dose_min": 30, "dose_max": 40, "dose_unit": "g/hL", "required_lab_analytes": "yan,potential_alcohol,turbidity",
        },
        {
            "id": "no-stop", "product_catalog_id": "no-stop", "manufacturer": "ENARTIS",
            "product_name": "NUTRIFERM NO STOP", "product_class": "nutrient", "protocol_name": "Restart",
            "purpose": "Sluggish fermentation", "wine_colors": "white", "trigger_code": "sluggish_fermentation",
            "dose_min": 40, "dose_max": 40, "dose_unit": "g/hL",
        },
    ]
    labs = {"status": "linked", "candidates": [], "metrics": {
        "yan": {"code": "yan", "value": 124, "age_days": 4},
        "potential_alcohol": {"code": "potential_alcohol", "value": 11.82, "age_days": 4},
    }}
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 1069.8, "yan_mg_l": 124, "potential_alcohol_pct": 11.82},
        protocols,
        [
            {"observed_at": "2026-09-13T00:00:00", "babo": 19},
            {"observed_at": "2026-09-15T18:00:00", "babo": 12.2},
        ], [], lab_evidence=labs,
    )
    decisions = {row["product_name"]: row for row in result["decisions"]}
    assert result["babo_progress_pct"] == 35.8
    assert decisions["NUTRIFERM SPECIAL"]["operational_status"] == "recommended_now"
    assert decisions["NUTRIFERM SPECIAL"]["projection"]["minimum"] == 320.94
    assert decisions["NUTRIFERM NO STOP"]["operational_status"] == "not_indicated"


def test_operator_ready_recipe_recommends_a_working_quantity_inside_the_verified_range():
    protocol = {
        "id": "yeast", "product_catalog_id": "yeast", "manufacturer": "ENARTIS",
        "product_name": "EnartisFerm D20", "product_class": "yeast",
        "protocol_name": "Red inoculation", "purpose": "Fermentation", "wine_colors": "red",
        "process_stages": "must,pre-fermentation", "trigger_code": "inoculation",
        "dose_min": 20, "dose_max": 40, "dose_unit": "g/hL", "dose_basis": "Official PDS",
    }
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "must", "volume_l": 500, "yan_mg_l": 140,
         "yan_target_mg_l": 150, "potential_alcohol_pct": 15, "fruit_condition": "sound"},
        [protocol], [], [],
    )
    decision = result["decisions"][0]
    assert decision["approval_required"] is False
    assert decision["working_recommendation"]["rate"] == 40
    assert decision["working_recommendation"]["quantity"] == 200
    assert decision["working_recommendation"]["unit"] == "g"


def test_nutriferm_special_uses_sheet_yan_contribution_for_working_rate():
    protocol = {
        "id": "special", "product_catalog_id": "special", "manufacturer": "ENARTIS",
        "product_name": "NUTRIFERM SPECIAL", "product_class": "nutrient",
        "protocol_name": "Inoculation nutrition", "purpose": "Nutrition", "wine_colors": "white",
        "process_stages": "must,pre-fermentation", "trigger_code": "inoculation",
        "dose_min": 30, "dose_max": 40, "dose_unit": "g/hL", "dose_basis": "Official PDS",
    }
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "must", "volume_l": 300, "yan_mg_l": 90,
         "yan_target_mg_l": 150, "potential_alcohol_pct": 12.5},
        [protocol], [], [],
    )
    recommendation = result["decisions"][0]["working_recommendation"]
    assert recommendation["rate"] == 37.5
    assert recommendation["quantity"] == 112.5
    assert "16 mg/L YAN per 10 g/hL" in recommendation["rationale"]


def test_enology_write_routes_do_not_require_a_second_approval_gate():
    source = (ROOT / "app/domains/enology_process.py").read_text()
    assert "require_discipline_approval" not in source
    assert "operator_record_is_authoritative" in source


def test_babo_progress_uses_first_reading_and_complete_recipe_keeps_stage_status():
    protocols = [
        {"id": "must", "product_name": "Must enzyme", "product_class": "enzyme", "protocol_name": "Press", "purpose": "Pressing", "wine_colors": "white", "process_stages": "must,pre-fermentation", "trigger_code": "pressing", "dose_min": 1, "dose_max": 1, "dose_unit": "g/hL"},
        {"id": "ferment", "product_name": "Fermentation nutrient", "product_class": "nutrient", "protocol_name": "Nutrition", "purpose": "Nutrition", "wine_colors": "white", "process_stages": "fermentation", "trigger_code": "density_drop_30", "dose_min": 20, "dose_max": 20, "dose_unit": "g/hL"},
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 1000, "yan_mg_l": 120}, protocols,
        [{"observed_at": "2026-09-10T08:00:00", "babo": 18}, {"observed_at": "2026-09-11T08:00:00", "babo": 20}, {"observed_at": "2026-09-12T08:00:00", "babo": 12}], [],
    )
    assert result["babo_start"] == 18
    assert {item["product_name"] for item in result["decisions"]} == {"Fermentation nutrient", "Must enzyme"}
    press = next(item for item in result["decisions"] if item["product_name"] == "Must enzyme")
    assert press["operational_status"] == "not_current"


def test_manual_tank_updates_preserve_omitted_values_and_queries_use_latest_non_null():
    backend = (ROOT / "app/domains/cellar_routes.py").read_text()
    whatsapp = (ROOT / "app/whatsapp_tanks.py").read_text()
    assert "manual_babo=COALESCE(VALUES(manual_babo),manual_babo)" in backend
    assert "f.babo IS NOT NULL ORDER BY f.observed_at DESC" in backend
    assert "f.babo IS NOT NULL ORDER BY f.observed_at DESC" in whatsapp


def test_prediction_refresh_bulk_loads_and_deduplicates_snapshots():
    backend = (ROOT / "app/domains/laffort_catalog.py").read_text()
    migration = (ROOT / "db/migrations/161_enology_professional_correctness.sql").read_text()
    assert "readings_by_lot" in backend and "additions_by_lot" in backend
    assert "INSERT IGNORE INTO enology_additive_prediction_snapshots" in backend
    assert "uq_enology_prediction_input" in migration


def test_ai_analyte_mapping_preserves_raw_results_and_is_applied_at_read_time():
    migration = (ROOT / "db/migrations/162_ai_enology_analyte_mapping.sql").read_text()
    mapper = (ROOT / "app/domains/lab_analyte_mapping.py").read_text()
    evidence = (ROOT / "app/domains/laffort_catalog.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS enology_analyte_mappings" in migration
    assert "ADD COLUMN IF NOT EXISTS analyte_mapping_id" in migration
    assert "confidence" in mapper and "< 0.9" in mapper
    assert "COALESCE(m.canonical_code,r.analyte_code)" in evidence
    assert "reported_analyte_code" in evidence


def test_batch_recipe_ui_keeps_one_primary_product_and_step_alternatives():
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "data-recipe-alternative" in script
    assert "Evidence-supported recommendation" in script
    assert "Planning started · laboratory result pending" in script
    assert "from all manufacturers" in script
    assert "No product addition is currently supported" in script
    assert 'type="range"' in script
    assert "Inoculate & support yeast" in script
    assert "One valid YAN / APA result is enough" in script
    assert "api/v1/enology/recipe-preference" in script


def test_style_target_changes_primary_product_without_changing_verified_quantity_math():
    protocols = [
        {
            "id": "fresh", "product_catalog_id": "fresh", "manufacturer": "MAKER A",
            "product_name": "Aromatic Yeast", "product_class": "yeast", "protocol_name": "Primary yeast",
            "purpose": "Fresh floral varietal expression", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 20, "dose_unit": "g/hL",
        },
        {
            "id": "structured", "product_catalog_id": "structured", "manufacturer": "MAKER B",
            "product_name": "Structure Yeast", "product_class": "yeast", "protocol_name": "Primary yeast",
            "purpose": "Structure body and ageing potential", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 20, "dose_unit": "g/hL",
        },
    ]
    products = [
        {"id": "fresh", "description": "Fresh aromatic fruit and floral varietal expression"},
        {"id": "structured", "description": "Structure, body, mouthfeel and aging support"},
    ]
    base = {"wine_color": "red", "stage": "must", "volume_l": 500, "variety_summary": "Nerello Mascalese", "potential_alcohol_pct": 13.0}
    fresh = additive_prediction_pipeline({**base, "recipe_style_intensity": 0}, protocols, [], [], products=products)["streamlined_recipe"]
    structured = additive_prediction_pipeline({**base, "recipe_style_intensity": 100}, protocols, [], [], products=products)["streamlined_recipe"]
    assert fresh["current_actions"][0]["product_name"] == "Aromatic Yeast"
    assert structured["current_actions"][0]["product_name"] == "Structure Yeast"
    assert fresh["current_actions"][0]["working_recommendation"]["quantity"] == 100
    assert structured["current_actions"][0]["working_recommendation"]["quantity"] == 100


def test_unambiguous_primary_tank_lab_report_is_used_without_manual_linking():
    rows = [{
        "sample_id": "sample-primary", "sample_name": "Grecanico — Primary tank (BT)",
        "sample_type": "must", "lab_date": "2026-09-11", "sampled_at": None,
        "wine_lot_id": None, "linked_wine_lot_ids": None, "variety_name": "Grecanico",
        "analyte_code": "turbidity", "analyte_name": "Torbidità", "numeric_value": 78.1,
        "unit": "NTU", "reported_numeric_value": 78.1, "reported_unit": "NTU",
        "reported_analyte_code": "ntu", "reported_analyte_name": "Torbidità", "report_url": "report",
        "flag": None, "text_value": None,
    }]
    evidence = lot_lab_evidence({
        "id": "lot-primary", "code": "GRC-2026-01-P", "name": "Grecanico 2026 — Primary",
        "container_code": "T-03", "variety_summary": "Grecanico",
    }, 2026, rows=rows)
    assert evidence["status"] == "auto_matched"
    assert evidence["metrics"]["turbidity"]["value"] == 78.1
    assert evidence["auto_matched_sample_ids"] == ["sample-primary"]
    assert evidence["candidates"] == []


def test_complete_recipe_keeps_lab_supported_white_fining_red_tannin_and_tartaric_acid():
    white_protocols = [
        {
            "id": "claril", "product_catalog_id": "claril", "manufacturer": "ENARTIS",
            "product_name": "CLARIL AF", "product_class": "fining", "protocol_name": "White-must fining bench trial",
            "purpose": "Clarification", "wine_colors": "white", "process_stages": "must,clarification",
            "trigger_code": "bench_trial", "dose_min": 50, "dose_max": 90, "dose_unit": "g/hL",
            "required_lab_analytes": "ph,total_acidity,turbidity,catechins",
        },
        {
            "id": "acid", "product_catalog_id": "acid", "manufacturer": "ENODORO",
            "product_name": "Acido L(+) Tartarico Naturale E334", "product_class": "treatment",
            "protocol_name": "Acidification bench-trial calculator", "purpose": "Acid balance",
            "wine_colors": "any", "process_stages": "must,wine", "trigger_code": "acidification_bench_trial",
            "dose_min": None, "dose_max": None, "dose_unit": None,
            "required_lab_analytes": "ph,total_acidity,potassium,tartaric_acid",
        },
    ]
    metrics = {code: {"code": code, "value": value, "unit": unit, "age_days": 0} for code, value, unit in (
        ("ph", 3.31, "pH"), ("total_acidity", 7.2, "g/L"), ("turbidity", 78.1, "NTU"),
        ("catechins", 13.9, "mg/L"), ("potassium", 1100, "mg/L"), ("tartaric_acid", 3.1, "g/L"),
    )}
    white = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 1069.8}, white_protocols, [], [],
        lab_evidence={"status": "linked", "metrics": metrics},
    )["streamlined_recipe"]
    assert {item["recipe_role"] for item in white["required_inputs"]} == {"fining", "acidification"}

    tannin = {
        "id": "tannin", "product_catalog_id": "tannin", "manufacturer": "LAFFORT",
        "product_name": "TANIN VR SUPRA", "product_class": "tannin", "protocol_name": "Structural tannin",
        "purpose": "Structure", "wine_colors": "red", "process_stages": "must,fermentation",
        "trigger_code": "first_pump_over", "dose_min": 10, "dose_max": 20, "dose_unit": "g/hL",
        "required_lab_analytes": "ph,total_acidity,potential_alcohol,anthocyanins,total_polyphenols",
    }
    red_metrics = {code: {"code": code, "value": value, "unit": unit, "age_days": 0} for code, value, unit in (
        ("ph", 3.4, "pH"), ("total_acidity", 6.5, "g/L"), ("potential_alcohol", 13.2, "% vol"),
        ("anthocyanins", 520, "mg/L"), ("total_polyphenols", 55, "index"),
    )}
    red = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "fermentation", "volume_l": 280}, [tannin],
        [{"observed_at": "2026-09-20T12:00:00", "babo": 3, "temp_c": 27}], [],
        lab_evidence={"status": "linked", "metrics": red_metrics},
    )["streamlined_recipe"]
    assert red["current_actions"][0]["recipe_role"] == "tannin_program"


def test_complete_recipe_migration_joins_protocol_product_class_through_catalog():
    migration = (ROOT / "db/migrations/174_complete_lab_driven_enology_recipe.sql").read_text()
    assert "JOIN enology_product_catalog product ON product.id=protocol.product_catalog_id" in migration
    assert "WHERE product.product_class='tannin'" in migration
    recipe_source = (ROOT / "app/domains/laffort_catalog.py").read_text()
    assert '"required_inputs": required_inputs,' in recipe_source
    assert '"evaluated_actions": evaluated_actions,' in recipe_source


def test_streamlined_recipe_selects_one_product_per_purpose_and_keeps_all_manufacturer_options():
    protocols = [
        {
            "id": "nutrient-a", "product_catalog_id": "nutrient-a", "manufacturer": "LAFFORT",
            "product_name": "Nutrient A", "product_class": "nutrient", "protocol_name": "Inoculation nutrition",
            "purpose": "Nutrition", "wine_colors": "white", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
            "pds_url": "https://example.test/a.pdf",
        },
        {
            "id": "nutrient-b", "product_catalog_id": "nutrient-b", "manufacturer": "ENARTIS",
            "product_name": "Nutrient B", "product_class": "nutrient", "protocol_name": "Inoculation nutrition",
            "purpose": "Nutrition", "wine_colors": "white", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        },
        {
            "id": "nutrient-c", "product_catalog_id": "nutrient-c", "manufacturer": "LALLEMAND OENOLOGY",
            "product_name": "Nutrient C", "product_class": "nutrient", "protocol_name": "Inoculation nutrition",
            "purpose": "Nutrition", "wine_colors": "white", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        },
        {
            "id": "yeast-a", "product_catalog_id": "yeast-a", "manufacturer": "IOC",
            "product_name": "Yeast A", "product_class": "yeast", "protocol_name": "Primary yeast",
            "purpose": "Inoculation", "wine_colors": "white", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 25, "dose_unit": "g/hL",
        },
    ]
    products = [
        {"id": "nutrient-b", "in_cellar": True, "stock": [{"package_size": 1, "package_unit": "kg"}]},
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "must", "volume_l": 1000, "yan_mg_l": 90,
         "yan_target_mg_l": 150, "potential_alcohol_pct": 12.5},
        protocols, [], [], products=products,
    )
    recipe = result["streamlined_recipe"]
    assert len(recipe["current_actions"]) == 2
    assert {item["recipe_role"] for item in recipe["current_actions"]} == {"primary_yeast", "fermentation_nutrition"}
    nutrition = next(item for item in recipe["current_actions"] if item["recipe_role"] == "fermentation_nutrition")
    assert nutrition["product_name"] == "Nutrient A"
    assert {item["manufacturer"] for item in nutrition["alternatives"]} == {"ENARTIS", "LALLEMAND OENOLOGY"}
    assert any(item["in_cellar"] for item in nutrition["alternatives"])
    assert "regardless of cellar stock" in recipe["selection_policy"]


def test_applied_products_remain_in_recipe_after_their_process_stage_has_passed():
    protocol = {
        "id": "yeast", "product_catalog_id": "yeast", "manufacturer": "ENARTIS",
        "product_name": "EnartisFerm ES181", "product_class": "yeast", "protocol_name": "Primary inoculation",
        "purpose": "Inoculation", "wine_colors": "white", "process_stages": "must,pre-fermentation",
        "trigger_code": "inoculation", "dose_min": 20, "dose_max": 25, "dose_unit": "g/hL",
    }
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 1000}, [protocol], [],
        [{
            "id": "addition-1", "additive_name": "EnartisFerm ES181", "additive_type": "yeast",
            "event_status": "applied", "quantity": 500, "unit": "g",
            "applied_at": "2026-09-11T08:00:00", "product_lot": "ES181-2026",
            "reason_text": "Primary inoculation",
        }],
    )
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["operational_status"] == "applied"
    used = result["streamlined_recipe"]["used_products"]
    assert len(used) == 1
    assert used[0]["recipe_role"] == "primary_yeast"
    assert used[0]["step_order"] == 30
    assert used[0]["actual_quantity"] == 500
    assert used[0]["actual_unit"] == "g"
    assert used[0]["product_lot"] == "ES181-2026"


def test_applied_product_suppresses_duplicate_unsubstantiated_recipe_placeholder():
    protocols = [{
        "id": "claril", "product_catalog_id": "claril", "manufacturer": "ENARTIS",
        "product_name": "CLARIL AF", "product_class": "fining", "protocol_name": "White-must fining bench trial",
        "purpose": "Clarification", "wine_colors": "white", "process_stages": "must,fermentation",
        "trigger_code": "bench_trial", "dose_min": None, "dose_max": None, "dose_unit": None,
    }]
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 275}, protocols, [],
        [{
            "id": "claril-addition", "additive_name": "CLARIL AF", "additive_type": "fining",
            "event_status": "applied", "quantity": 60, "unit": "g",
            "applied_at": "2026-09-24T12:00:00", "reason_text": "Added before first racking",
        }],
    )
    recipe = result["streamlined_recipe"]
    assert [item["product_name"] for item in recipe["used_products"]] == ["CLARIL AF"]
    assert recipe["required_inputs"] == []
    assert result["blocked_count"] == 0
    assert result["candidate_blocked_count"] == 0


def test_operational_counts_follow_streamlined_recipe_not_catalog_alternatives():
    protocols = [
        {
            "id": f"yeast-{index}", "product_catalog_id": f"yeast-{index}", "manufacturer": maker,
            "product_name": f"Yeast {index}", "product_class": "yeast", "protocol_name": "Primary inoculation",
            "purpose": "Inoculation", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        }
        for index, maker in enumerate(("ENARTIS", "LAFFORT", "LALLEMAND OENOLOGY"), start=1)
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "must", "volume_l": 1600, "potential_alcohol_pct": 13.0},
        protocols, [], [],
    )
    assert result["candidate_due_count"] == 3
    assert result["due_count"] == 1
    assert len(result["streamlined_recipe"]["current_actions"]) == 1


def test_primary_fermentation_does_not_present_mlf_or_filterability_as_due_now():
    protocols = [
        {
            "id": "mlf", "product_catalog_id": "mlf", "manufacturer": "LAFFORT",
            "product_name": "MLF bacteria", "product_class": "bacteria", "protocol_name": "MLF",
            "purpose": "Malolactic fermentation", "wine_colors": "red", "process_stages": "fermentation,post-fermentation",
            "trigger_code": "mlf_inoculation", "dose_min": 1, "dose_max": 1, "dose_unit": "dose/hL",
        },
        {
            "id": "clear", "product_catalog_id": "clear", "manufacturer": "LAFFORT",
            "product_name": "Filter enzyme", "product_class": "enzyme", "protocol_name": "Filterability",
            "purpose": "Post-fermentation clarification", "wine_colors": "red", "process_stages": "fermentation,post-fermentation",
            "trigger_code": "clarification_enzyme", "dose_min": 1, "dose_max": 2, "dose_unit": "g/hL",
        },
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "fermentation", "volume_l": 1600}, protocols, [], [],
    )
    assert result["due_count"] == 0
    assert result["blocked_count"] == 0
    assert all(item["operational_status"] == "not_current" for item in result["decisions"])


def test_applied_product_shows_observed_whole_tank_rate_separately_from_protocol_range():
    protocol = {
        "id": "claril", "product_catalog_id": "claril", "manufacturer": "ENARTIS",
        "product_name": "CLARIL AF", "product_class": "fining", "protocol_name": "White must clarification",
        "purpose": "Clarification", "wine_colors": "white", "process_stages": "must,fermentation",
        "trigger_code": "turbidity", "dose_min": 50, "dose_max": 90, "dose_unit": "g/hL",
    }
    result = additive_prediction_pipeline(
        {"wine_color": "white", "stage": "fermentation", "volume_l": 275}, [protocol], [],
        [{
            "id": "claril-addition", "additive_name": "CLARIL AF", "additive_type": "other",
            "event_status": "applied", "quantity": 60, "unit": "g",
            "applied_at": "2026-09-24T12:00:00", "product_lot": "1148296",
            "reason_text": "Owner-confirmed bench-trial dose",
        }],
    )
    used = result["streamlined_recipe"]["used_products"]
    assert used[0]["actual_quantity"] == 60
    assert used[0]["actual_rate_g_hl"] == 21.82
    assert used[0]["actual_rate_unit"] == "g/hL"
    assert "275 L" in used[0]["actual_rate_basis"]


def test_recipe_ui_labels_calculated_actual_rate_as_observed():
    source = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "actual_rate_g_hl" in source
    assert "g/hL'} observed" in source
    assert "Applied · quantity not recorded" in source


def test_started_yan_test_builds_a_provisional_nerello_plan_without_category_filler():
    protocols = [
        {
            "id": "yeast", "product_catalog_id": "yeast", "manufacturer": "LAFFORT",
            "product_name": "ZYMAFLORE F83", "product_class": "yeast", "protocol_name": "Red inoculation",
            "purpose": "Mediterranean red fermentation", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        },
        {
            "id": "nutrient", "product_catalog_id": "nutrient", "manufacturer": "ENARTIS",
            "product_name": "NUTRIFERM SPECIAL", "product_class": "nutrient", "protocol_name": "Inoculation nutrition",
            "purpose": "YAN-supported nutrition", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "inoculation", "dose_min": 30, "dose_max": 40, "dose_unit": "g/hL",
        },
        {
            "id": "tannin", "product_catalog_id": "tannin", "manufacturer": "ENARTIS",
            "product_name": "Generic tannin", "product_class": "tannin", "protocol_name": "Pump-over tannin",
            "purpose": "Optional structure", "wine_colors": "red", "process_stages": "must",
            "trigger_code": "crusher_or_fermentation", "dose_min": 5, "dose_max": 10, "dose_unit": "g/hL",
        },
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "must", "volume_l": 800, "variety_summary": "Nerello Mascalese",
         "potential_alcohol_pct": 13.5, "yan_mg_l": None},
        protocols, [], [], test_requests=[{"status": "sampled", "analytes_json": '["yan"]'}],
    )
    recipe = result["streamlined_recipe"]
    assert recipe["status"] == "ready"
    assert {item["recipe_role"] for item in recipe["current_actions"]} == {"primary_yeast"}
    assert {item["recipe_role"] for item in recipe["provisional_actions"]} == {"fermentation_nutrition"}
    assert recipe["provisional_actions"][0]["awaiting_analytes"] == ["yan"]
    assert all(item["recipe_role"] != "tannin_program" for item in recipe["provisional_actions"])
    assert "Active laboratory plan: yan sampled" in recipe["provisional_actions"][0]["recommendation_basis"]


def test_preharvest_recipe_keeps_supported_yeast_visible_while_batch_size_is_pending():
    protocols = [{
        "id": "d20", "product_catalog_id": "d20", "manufacturer": "ENARTIS",
        "product_name": "EnartisFerm D20", "product_class": "yeast", "protocol_name": "Red inoculation",
        "purpose": "Nerello red fermentation", "wine_colors": "red", "process_stages": "must,pre-fermentation",
        "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        "required_lab_analytes": "ph,potential_alcohol,yan",
    }]
    evidence = {"status": "preharvest_planning", "metrics": {
        "ph": {"code": "ph", "name": "pH", "value": 3.31, "unit": "pH", "age_days": 1},
        "potential_alcohol": {"code": "potential_alcohol", "name": "Potential alcohol", "value": 13.6, "unit": "% vol", "age_days": 1},
        "yan": {"code": "yan", "name": "YAN / APA", "value": 149.2, "unit": "mg/L", "age_days": 1},
    }}
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "pre-harvest", "process_stage": "pre-fermentation",
         "volume_l": None, "fruit_kg": None, "variety_summary": "Nerello Mascalese",
         "potential_alcohol_pct": 13.6, "yan_mg_l": 149.2},
        protocols, [], [], lab_evidence=evidence,
    )
    recipe = result["streamlined_recipe"]
    assert recipe["status"] == "inputs_needed"
    assert len(recipe["required_inputs"]) == 1
    assert recipe["required_inputs"][0]["product_name"] == "EnartisFerm D20"
    assert any("volume or grape weight" in item for item in recipe["required_inputs"][0]["blockers"])


def test_yeast_recommendation_does_not_require_repeated_yan_results():
    protocol = {
        "id": "d20", "product_catalog_id": "d20", "manufacturer": "ENARTIS",
        "product_name": "EnartisFerm D20", "product_class": "yeast", "protocol_name": "Red inoculation",
        "purpose": "Nerello red fermentation", "wine_colors": "red", "process_stages": "must,pre-fermentation",
        "trigger_code": "inoculation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
        "required_lab_analytes": "ph,potential_alcohol,yan",
    }
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "must", "volume_l": 500, "variety_summary": "Nerello Mascalese"},
        [protocol], [], [], lab_evidence={"status": "linked", "metrics": {}},
    )
    decision = result["decisions"][0]
    assert decision["operational_status"] == "recommended_now"
    assert decision["decision_status"] == "review_due"
    assert not decision["blockers"]
    assert any("one valid result is sufficient" in item for item in decision["advisory"])
    assert result["streamlined_recipe"]["current_actions"][0]["product_name"] == "EnartisFerm D20"


def test_laboratory_page_can_start_a_batch_test_and_provisional_recipe_plan():
    backend = (ROOT / "app/domains/enology_process.py").read_text()
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert '@router.post("/api/v1/enology/test-requests"' in backend
    assert 'test_requests=test_requests or []' in backend
    assert "data-start-lab-test" in frontend
    assert "Start test & recipe plan" in frontend
    assert "provisional yeast/nutrition planning is active" in frontend


def test_enologist_chemistry_charts_are_unit_safe_and_open_source_evidence():
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "`${row.metric_code}|${row.display_unit||'unit not reported'}`" in script
    assert "onPointClick:openLabChartEvidence" in script
    assert "report_url:row.report_url" in script


def test_additive_prediction_blocks_unmeasured_nutrition_and_laccase_use():
    protocols = [
        {"id": "nutrition", "product_name": "NUTRISTART THIOLS", "product_class": "nutrient", "protocol_name": "Nutrition", "purpose": "Nutrition", "wine_colors": "red", "trigger_code": "density_drop_30", "dose_min": 20, "dose_max": 60, "dose_unit": "g/hL"},
        {"id": "laccase", "product_name": "TANIN VR SUPRA", "product_class": "tannin", "protocol_name": "Laccase", "purpose": "Laccase", "wine_colors": "red", "trigger_code": "sanitary_evidence", "dose_min": 30, "dose_max": 80, "dose_unit": "g/hL"},
    ]
    result = additive_prediction_pipeline({"wine_color": "red", "stage": "fermentation", "volume_l": 500, "fruit_condition": "sound"}, protocols, [], [])
    assert result["blocked_count"] == 0
    assert result["candidate_blocked_count"] == 2
    assert all(item["decision_status"] == "blocked" for item in result["decisions"])
    assert any("YAN/APA" in blocker for blocker in result["decisions"][0]["blockers"])
    assert any("laccase" in blocker for blocker in result["decisions"][1]["blockers"])


def test_catalog_covers_all_official_enology_range_families_and_ui():
    assert len(LAFFORT_RANGES) == 18
    assert {item[2] for item in LAFFORT_RANGES} >= {"yeast", "enzyme", "bacteria", "nutrient", "tannin", "fining", "stabilizer", "cleaning", "filtration", "preservation", "laboratory", "equipment"}
    migration = (ROOT / "db/migrations/143_laffort_enology_catalog.sql").read_text()
    page = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    process = (ROOT / "app/process_control.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS enology_product_catalog" in migration
    assert "Enology product database" in page
    assert "enologyProductCatalog" in script
    assert "View product data sheet" in script
    assert "Safety sheet" in script
    assert '"enology_catalog"' in process
    assert normalize_product_name("ZYMAFLORE™ ALPHA") == "zymaflore alpha"
    assert normalize_product_name("ZYMAFLORE™ ALPHA TD N. SACCH") == "zymaflore alpha"


def test_projection_ready_catalog_expansion_uses_official_ranges_and_protocol_gates():
    migration = (ROOT / "db/migrations/166_expand_projection_ready_enology_catalog.sql").read_text()
    backend = (ROOT / "app/domains/laffort_catalog.py").read_text()
    process = (ROOT / "app/domains/enology_process.py").read_text()
    assert migration.count("SELECT 'LAFFORT'") >= 20
    assert migration.count("(UUID(),'ENARTIS'") >= 7
    assert "'nutristart arom',20,60,'g/hL'" in migration
    assert "'nutriflow',50,250,'mL/hL'" in migration
    assert "'oenobrett org',4,10,'g/hL'" in migration
    assert "'lafazym cl','free_run_settling'" in migration
    assert "required_lab_analytes" in migration
    assert 'trigger == "clarification_enzyme"' in backend
    assert 'trigger == "mlf_activation"' in backend
    assert 'trigger == "microbial_control"' in backend
    assert '"brettanomyces"' in process


def test_new_projection_triggers_remain_lab_and_timing_gated():
    protocols = [
        {
            "id": "mlf", "product_catalog_id": "mlf", "manufacturer": "LAFFORT",
            "product_name": "MALOBOOST", "product_class": "nutrient", "protocol_name": "MLF activation",
            "purpose": "MLF", "wine_colors": "red", "process_stages": "post-fermentation,aging",
            "trigger_code": "mlf_activation", "dose_min": 20, "dose_max": 30, "dose_unit": "g/hL",
            "required_lab_analytes": "ph,actual_alcohol,malic_acid", "lab_max_age_days": 3,
        },
        {
            "id": "brett", "product_catalog_id": "brett", "manufacturer": "LAFFORT",
            "product_name": "OENOBRETT ORG", "product_class": "stabilizer", "protocol_name": "Brett control",
            "purpose": "Microbial control", "wine_colors": "red", "process_stages": "post-fermentation,aging",
            "trigger_code": "microbial_control", "dose_min": 4, "dose_max": 10, "dose_unit": "g/hL",
            "required_lab_analytes": "brettanomyces,ph,free_so2", "lab_max_age_days": 3,
        },
    ]
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "post-fermentation", "volume_l": 500}, protocols, [], [],
        lab_evidence={"status": "missing", "metrics": {}, "candidates": []},
    )
    decisions = {row["product_name"]: row for row in result["decisions"]}
    assert decisions["MALOBOOST"]["projection"]["minimum"] == 100
    assert decisions["MALOBOOST"]["operational_status"] == "data_needed"
    assert any("malic acid" in blocker for blocker in decisions["MALOBOOST"]["blockers"])
    assert decisions["OENOBRETT ORG"]["projection"]["maximum"] == 50
    assert any("brettanomyces" in blocker for blocker in decisions["OENOBRETT ORG"]["blockers"])


def test_catalog_load_retries_after_parallel_dashboard_failure():
    application = (ROOT / "app/static/app.js").read_text()
    page = (ROOT / "app/static/index.html").read_text()
    renderer = (ROOT / "app/static/assets/enology-process.js").read_text()
    loader = application.split("async function loadAll()", 1)[1].split(
        "function activateViewButton", 1
    )[0]
    assert "let [dashboard,reference,tasks,grapes,cellar,enologyProcess" in loader
    assert "if(!enologyProcess)" in loader
    assert loader.count("enology/process?year=${year}") == 2
    assert "recoverEnologyProcess(request,year)" in loader
    assert loader.index("recoverEnologyProcess(request,year)") < loader.index("render();")
    assert "for(const delay of [1500,3000,6000,10000])" in application
    assert "state.enologyProcess=recovered;renderEnologyProcess()" in application
    assert "Loading product catalog…" in page
    assert "Catalog load failed. Select Refresh to retry." in renderer
    assert "Catalog refresh pending." not in page
    assert "'enzime':'enzyme'" in renderer
    assert "mode==='suggested'&&!term" in renderer


def test_today_startup_deferred_loader_includes_enology_catalog():
    performance = (ROOT / "app/static/assets/performance.js").read_text()
    deferred = performance.split("async function loadDeferredData", 1)[1].split(
        "async function loadInitial", 1
    )[0]
    assert "cellar,enologyProcess,agronomy" in deferred
    assert "optionalApi(`api/v1/enology/process?year=${year}`,null)" in deferred
    assert "Object.assign(state,{reference,grapes,cellar,enologyProcess" in deferred
    assert "recoverEnologyProcess(request,year)" in deferred


def test_recipe_protocol_and_prediction_pipeline_are_release_managed():
    migration = (ROOT / "db/migrations/144_enology_additive_prediction_pipeline.sql").read_text()
    page = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    process = (ROOT / "app/process_control.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS enology_product_protocols" in migration
    assert "CREATE TABLE IF NOT EXISTS enology_additive_prediction_snapshots" in migration
    assert "preparation" in migration and "incompatibilities" in migration
    assert "Additive decision pipeline" in page
    assert "renderEnologyPredictionPipeline" in script
    assert '"enology_predictions"' in process


def test_fermentation_vintage_overlay_aligns_each_lot_without_inventing_points():
    rows = [
        {"vintage_year": 2025, "wine_lot_id": "old", "lot_code": "R25", "variety_summary": "Nerello", "observed_at": "2025-09-01T08:00:00", "density_sg": 1.090},
        {"vintage_year": 2025, "wine_lot_id": "old", "lot_code": "R25", "variety_summary": "Nerello", "observed_at": "2025-09-02T07:00:00", "density_sg": 1.070},
        {"vintage_year": 2026, "wine_lot_id": "new", "lot_code": "R26", "variety_summary": "Nerello", "observed_at": "2026-09-04T12:00:00", "density_sg": 1.088},
        {"vintage_year": 2026, "wine_lot_id": "new", "lot_code": "R26", "variety_summary": "Nerello", "observed_at": "2026-09-05T00:00:00", "density_sg": None},
    ]
    normalized = normalize_fermentation_overlay_rows(rows)
    assert [row["elapsed_12h_bucket"] for row in normalized] == [0, 24, 0, 12]
    assert normalized[0]["series_name"] == "2025 · R25"
    assert normalized[2]["comparison_group"] == "Nerello"
    assert normalized[3]["density_sg"] is None


def test_winemaking_professional_overlay_and_yoy_views_are_release_managed():
    page = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    backend = (ROOT / "app/domains/enology_process.py").read_text()
    assert "Vintage-over-vintage fermentation overlay" in page
    assert "Vintage-over-vintage must chemistry" in page
    assert "enologyFermentationYoyGroup" in page
    assert "enologyChemistryYoySeries" in page
    assert "renderEnologyFermentationYoy" in script
    assert "renderEnologyChemistryYoy" in script
    assert "fermentation_vintage_overlay" in backend
    assert "chemistry_vintage_overlay" in backend
    assert "elapsed_12h_bucket" in backend


def test_enartis_inventory_lab_gates_and_manufacturer_recipes_are_release_managed():
    migration = (ROOT / "db/migrations/152_enartis_cellar_products_and_lab_gates.sql").read_text()
    page = (ROOT / "app/static/index.html").read_text()
    script = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "CREATE TABLE IF NOT EXISTS enology_product_stock" in migration
    assert "EnartisFerm D20" in migration
    assert "NUTRIFERM SPECIAL" in migration
    assert "Acido L(+) Tartarico Naturale E334" in migration
    assert "required_lab_analytes" in migration and "lab_max_age_days" in migration
    assert "Guided batch recipe" in page
    assert "best evidence fit" in page.casefold()
    assert "renderEnologyBatchRecipe" in script
    assert "manufacturer_recipes" in (ROOT / "app/domains/laffort_catalog.py").read_text()


def test_premium_specialist_catalog_and_decision_protocols_are_release_managed():
    migration = (ROOT / "db/migrations/154_premium_enology_decision_catalog.sql").read_text()
    for manufacturer in ("LALLEMAND OENOLOGY", "PERDOMINI-IOC", "OENOBRANDS", "ENARTIS"):
        assert manufacturer in migration
    for product in ("LALVIN ICV D254", "LALVIN VP41", "IOC DYNAMIX", "Rapidase Clear", "Anchor Nourish", "EnartisStab CLK+"):
        assert product in migration
    assert migration.count("(UUID(),'") == 20
    assert migration.count("UNION ALL SELECT") == 20
    assert "required_lab_analytes" in migration
    assert "Marketing rank claims are intentionally not stored" in migration


def test_mlf_and_pre_bottling_decisions_remain_blocked_until_specific_evidence_is_recorded():
    protocols = [
        {
            "id": "vp41", "product_catalog_id": "vp41", "manufacturer": "LALLEMAND OENOLOGY",
            "product_name": "LALVIN VP41", "product_class": "bacteria", "protocol_name": "VP41 MLF",
            "purpose": "MLF", "wine_colors": "red", "trigger_code": "mlf_inoculation",
            "dose_min": None, "dose_max": None, "dose_unit": None,
            "required_lab_analytes": "ph,malic_acid,total_so2,potential_alcohol", "lab_max_age_days": 3,
        },
        {
            "id": "clk", "product_catalog_id": "clk", "manufacturer": "ENARTIS",
            "product_name": "EnartisStab CLK+", "product_class": "stabilizer", "protocol_name": "CLK+ trial",
            "purpose": "Tartrate stability", "wine_colors": "red", "trigger_code": "pre_bottling_bench",
            "dose_min": 5, "dose_max": 15, "dose_unit": "g/hL", "required_lab_analytes": "ph,potassium",
            "lab_max_age_days": 30,
        },
    ]
    metrics = {
        code: {"code": code, "value": 1, "age_days": 1}
        for code in ("ph", "malic_acid", "total_so2", "potential_alcohol", "potassium")
    }
    result = additive_prediction_pipeline(
        {"wine_color": "red", "stage": "aging", "volume_l": 500}, protocols, [], [],
        lab_evidence={"status": "linked", "metrics": metrics, "candidates": []},
    )
    decisions = {item["product_name"]: item for item in result["decisions"]}
    vp41, clk = decisions["LALVIN VP41"], decisions["EnartisStab CLK+"]
    assert clk["decision_status"] == "blocked"
    assert any("bench-trial result" in blocker for blocker in clk["blockers"])
    assert vp41["decision_status"] == "blocked"
    assert any("sachet coverage" in blocker for blocker in vp41["blockers"])


def test_single_recorded_yan_is_enough_for_yeast_recommendation():
    protocol = {
        "id": "d20", "product_catalog_id": "d20-product", "manufacturer": "ENARTIS",
        "product_name": "EnartisFerm D20", "product_class": "yeast", "protocol_name": "Red inoculation",
        "purpose": "Fermentation", "wine_colors": "red", "trigger_code": "inoculation",
        "dose_min": 20, "dose_max": 40, "dose_unit": "g/hL", "required_lab_analytes": "ph,total_acidity,potential_alcohol,yan",
        "lab_max_age_days": 7,
    }
    lot = {"wine_color": "red", "stage": "must", "volume_l": 500, "yan_mg_l": 160, "potential_alcohol_pct": 13}
    result = additive_prediction_pipeline(lot, [protocol], [], [], lab_evidence={
        "status": "linked", "metrics": {
            "ph": {"code": "ph", "value": 3.2, "age_days": 2},
            "total_acidity": {"code": "total_acidity", "value": 5.2, "age_days": 2},
            "potential_alcohol": {"code": "potential_alcohol", "value": 12.8, "age_days": 2},
        }, "candidates": [],
    })
    decision = result["decisions"][0]
    assert decision["projection"]["minimum"] == 100
    assert decision["decision_status"] == "review_due"
    assert decision["operational_status"] == "recommended_now"
    assert not decision["blockers"]
    assert any("does not block the yeast recommendation" in note for note in decision["advisory"])


def test_professional_cellar_analyte_names_and_post_fermentation_tests_are_canonical():
    assert canonical_enology_analyte("acidita_volatile", unit="g/L")["name"] == "Volatile acidity / Acidità volatile"
    assert canonical_enology_analyte("so2_libera")["unit"] == "mg/L"
    assert canonical_enology_analyte("zuccheri_residui", unit="g/L")["code"] == "residual_sugar"
    codes = {row["code"] for row in enology_testing_pipeline("post-fermentation")}
    assert {"residual_sugar", "volatile_acidity", "malic_acid", "lactic_acid", "free_so2", "total_so2"} <= codes
