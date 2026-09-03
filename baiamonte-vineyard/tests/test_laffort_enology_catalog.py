from pathlib import Path

from app.domains.laffort_catalog import (
    LAFFORT_RANGES,
    additive_prediction_pipeline,
    normalize_product_name,
    parse_laffort_range,
    project_product_quantity,
    suggest_products,
)
from app.domains.enology_process import canonical_enology_analyte, enology_testing_pipeline, normalize_fermentation_overlay_rows


ROOT = Path(__file__).resolve().parents[1]


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


def test_additive_prediction_blocks_unmeasured_nutrition_and_laccase_use():
    protocols = [
        {"id": "nutrition", "product_name": "NUTRISTART THIOLS", "product_class": "nutrient", "protocol_name": "Nutrition", "purpose": "Nutrition", "wine_colors": "red", "trigger_code": "density_drop_30", "dose_min": 20, "dose_max": 60, "dose_unit": "g/hL"},
        {"id": "laccase", "product_name": "TANIN VR SUPRA", "product_class": "tannin", "protocol_name": "Laccase", "purpose": "Laccase", "wine_colors": "red", "trigger_code": "sanitary_evidence", "dose_min": 30, "dose_max": 80, "dose_unit": "g/hL"},
    ]
    result = additive_prediction_pipeline({"wine_color": "red", "stage": "fermentation", "volume_l": 500, "fruit_condition": "sound"}, protocols, [], [])
    assert result["blocked_count"] == 2
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
    assert "for(const delay of [1500,3000])" in application
    assert "state.enologyProcess=recovered;renderEnologyProcess()" in application
    assert "Loading product catalog…" in page
    assert "Catalog load failed. Select Refresh to retry." in renderer
    assert "Catalog refresh pending." not in page


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


def test_professional_cellar_analyte_names_and_post_fermentation_tests_are_canonical():
    assert canonical_enology_analyte("acidita_volatile", unit="g/L")["name"] == "Volatile acidity / Acidità volatile"
    assert canonical_enology_analyte("so2_libera")["unit"] == "mg/L"
    assert canonical_enology_analyte("zuccheri_residui", unit="g/L")["code"] == "residual_sugar"
    codes = {row["code"] for row in enology_testing_pipeline("post-fermentation")}
    assert {"residual_sugar", "volatile_acidity", "malic_acid", "lactic_acid", "free_so2", "total_so2"} <= codes
