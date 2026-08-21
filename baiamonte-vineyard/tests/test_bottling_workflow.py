from pathlib import Path

from app import fattureincloud


ROOT = Path(__file__).resolve().parents[1]


class Cursor:
    def __init__(self):
        self.query = ""

    def execute(self, query, _params):
        self.query = query

    def fetchone(self):
        return {"id": "packaging-product"}


def test_fatture_line_recognizes_bottling_packaging(monkeypatch):
    monkeypatch.setattr(fattureincloud, "estate_id", lambda: "estate")
    cursor = Cursor()
    assert fattureincloud._packaging_product(cursor, {"description": "BORG. VIRGO CL.75 bottles"}) == "packaging-product"
    assert "products" in cursor.query


def test_bottling_migration_preserves_trace_and_finished_inventory():
    source = (ROOT / "db/migrations/097_bottling_traceability_and_costs.sql").read_text()
    for table in ("bottling_runs", "bottling_run_sources", "bottling_run_parcels", "finished_wine_lots", "finished_wine_inventory_movements"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source
    assert "2023 vintage_year,5610.000 grapes_kg,3755.000 wine_l,5007 bottles" in source
    assert "2024,NULL,2357.000,3143" in source
    assert "2025,5236.000,3998.000,5333" in source


def test_bottling_page_is_an_enology_workspace():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/bottling.js").read_text()
    assert 'data-view="bottling"' in html
    assert 'id="view-bottling"' in html
    assert "Complete bottling &amp; post inventory" in html
    assert "container_ids=data.getAll('container_ids')" in javascript
    assert "newest Fatture" not in javascript  # phrasing is rendered from source status, not a fabricated value
