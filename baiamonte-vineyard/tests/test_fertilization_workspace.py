from pathlib import Path

from app.domains.fertilization import _ai_soil_values, _current_finding, _interpret


ROOT = Path(__file__).resolve().parents[1]


def test_soil_screening_is_directional_and_never_a_prescription():
    checks = _interpret({
        "ph": 8.1,
        "organic_matter_pct": 1.1,
        "phosphorus_mg_kg": 7,
        "potassium_mg_kg": 90,
        "ec_ds_m": 2.0,
    })
    assert {row["metric"] for row in checks} == {"Soil pH", "Organic matter", "Phosphorus", "Potassium", "Salinity / EC"}
    assert all(row["status"] == "review" for row in checks)
    assert not any("kg/ha" in row["direction"] for row in checks)


def test_fertilization_workspace_preserves_source_and_yoy_controls():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/fertilization.js").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/fertilization_routes.py").read_text(encoding="utf-8")
    migration = (ROOT / "db/migrations/098_annual_soil_samples_and_fertilization.sql").read_text(encoding="utf-8")
    assert 'data-view="fertilization"' in html
    assert 'id="view-fertilization"' in html
    assert 'id="soilSampleForm"' in html
    assert 'id="fertilizationYoy"' in html
    assert 'id="fertilizationFindingHeadline"' in html
    assert "api/v1/intake/upload" in script
    assert "api/v1/fertilization/soil-samples" in script
    assert "api/v1/fertilization/dashboard" in script
    assert '@router.put("/review/{year}"' in routes
    assert "CREATE TABLE IF NOT EXISTS vineyard_soil_samples" in migration
    assert "CREATE TABLE IF NOT EXISTS vineyard_fertilization_reviews" in migration
    assert "CREATE TABLE IF NOT EXISTS vineyard_fertilizer_applications" in migration
    assert "NOVATEC CLASSIC 12-8-16" in migration
    assert "'2026-03-05',500,'kg','Whole vineyard'" in migration
    assert "'fertilizer_application'" in migration
    fic = (ROOT / "app/fattureincloud.py").read_text(encoding="utf-8")
    cleanup = (ROOT / "db/migrations/099_fic_fertilizer_receipt_reconciliation.sql").read_text(encoding="utf-8")
    assert '("NOVATEC CLASSIC", "NOVATEC CLASSIC 12-8-16"' in fic
    assert "owner-confirmed-invoice-429-2026" in cleanup
    backend = (ROOT / "app/domains/fertilization.py").read_text(encoding="utf-8")
    routes_migration = (ROOT / "db/migrations/112_fertilizer_application_route.sql").read_text(encoding="utf-8")
    assert "p.fertilizer_application_route='land'" in backend
    assert "fertilizer_application_route='foliar'" in routes_migration
    assert "fertilizer_application_route='land'" in routes_migration


def test_ai_soil_values_are_bounded_to_explicit_fertilization_fields():
    extracted = _ai_soil_values({"suggested_database_records": [{"destination": "fertilization soil_sample", "fields": {"ph": 7.4, "potassium_mg_kg": 180, "fertilizer_rate": "500 kg/ha"}}]})
    assert extracted == {"ph": 7.4, "potassium_mg_kg": 180}


def test_current_finding_uses_latest_report_without_prescribing_product_or_rate():
    row = {"sampled_on": "2026-08-20", "sample_scope": "Whole vineyard", "laboratory": "Test lab", "original_filename": "soil.pdf"}
    checks = _interpret({"ph": 8.1, "potassium_mg_kg": 90})

    finding = _current_finding(row, checks)

    assert finding["status"] == "review"
    assert {item["metric"] for item in finding["review_items"]} == {"Soil pH", "Potassium"}
    assert "does not select a fertilizer" in finding["decision_boundary"]
