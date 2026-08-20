from pathlib import Path

from app.fattureincloud import _agriplanet_invoice, _stock_product_match


ROOT = Path(__file__).resolve().parents[1]


def test_only_agriplanet_is_automatic_treatment_stock_source():
    assert _agriplanet_invoice({"entity": {"name": "AGRIPLANET S.R.L."}})
    assert _agriplanet_invoice({"entity": {"name": "Supplier", "vat_number": "IT03995580879"}})
    assert not _agriplanet_invoice({"entity": {"name": "Another agricultural supplier"}})


def test_recognized_invoice_lines_map_to_canonical_stock_products():
    cases = {
        "30008h SACRON 45 WG KG 1 CIMOXANIL45%": ("SACRON 45 WG", "1", "kg", "plant_protection", "candidate"),
        "30038d OSSICLOR 35 WG KG. 10 BIO": ("OSSICLOR 35 WG", "10", "kg", "plant_protection", "candidate"),
        "27046 IMPULSIVE LT 1": ("IMPULSIVE PREMIUM", "1", "L", "fertilizer", "support"),
        "27040 RESOLVE X 5 LT": ("RESOLVE", "5", "kg", "fertilizer", "support"),
        "28020 TERRAPLUS SOLUB NPK 8-7-6 15 KG": ("TERRAPLUS SOLUB NPK 8-7-6", "15", "kg", "fertilizer", "support"),
        "27043 GEL DI SILICE X 5 KG": ("GEL DI SILICE", "5", "L", "fertilizer", "support"),
        "31027 DURACID GRANULARE KG 1 MICROGRANULI": ("DURACID GRANULARE", "1", "kg", "plant_protection", "support"),
        "31133 DRAKER 10.2 INSETT. LT. 1": ("DRAKER 10.2", "1", "L", "plant_protection", "support"),
        "20012d CONC. NOVATEC CLASSIC 12-8-16 KG 25": ("NOVATEC CLASSIC 12-8-16", "1", "kg", "fertilizer", "support"),
    }
    for description, expected in cases.items():
        match = _stock_product_match({"description": description})
        assert match is not None
        assert (match[0], str(match[1]), match[2], match[3], match[4]) == expected
    assert _stock_product_match({"description": "FUSTO IN PLASTICA 50 L"}) is None
    assert _stock_product_match({"description": "PIANTA AROMATICA VASO"}) is None


def test_sync_posts_recognized_lines_idempotently_to_local_stock():
    source = (ROOT / "app/fattureincloud.py").read_text(encoding="utf-8")
    assert 'fieldset": "detailed"' in source
    assert "items_list" in source
    assert "_upsert_agriplanet_stock(cursor, item)" in source
    assert '"treatment_stock_lines"' in source
    assert "reference_type=VALUES(reference_type)" in source
    assert "invoice_number" in source
    assert "STOCK_BASELINE_DATE = date(2026, 1, 1)" in source
    assert "historical_stock_closed_2026_baseline" in source
    assert '"q": f"date >= \'{year}-01-01\' and date <= \'{year}-12-31\'"' in source
    assert '"treatment_stock_review_lines"' in source
    assert "convert_inventory_quantity" in source
    assert "excluded from on-hand" in source


def test_2026_stock_starts_at_zero_and_invoices_post_on_actual_dates():
    migration = (ROOT / "db/migrations/068_authoritative_2026_opening_stock.sql").read_text(encoding="utf-8")
    assert '"opening_quantity":0' in migration
    assert "Every Agriplanet invoice dated in 2026 adds stock on its invoice date" in migration
    assert "UPDATE inventory_movements" not in migration
