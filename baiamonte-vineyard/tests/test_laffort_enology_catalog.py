from pathlib import Path

from app.domains.laffort_catalog import (
    LAFFORT_RANGES,
    normalize_product_name,
    parse_laffort_range,
    project_product_quantity,
    suggest_products,
)


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
