from app import fattureincloud
from app.domains import enology_process


def test_enodoro_identity_and_article_code_detection():
    invoice = {"entity": {"name": "ENODORO SRL", "vat_number": "02035140819"}}
    assert fattureincloud._enodoro_invoice(invoice)
    assert fattureincloud._supplier_article_code({"code": "epc852"}) == "EPC852"
    assert fattureincloud._supplier_article_code({"description": "EPE919 NUTRIFERM ADVANCE KG.1"}) == "EPE919"
    assert fattureincloud.ENODORO_ENOLOGY_PRODUCTS["EPC852"][:2] == ("enartiszym color plus", fattureincloud.Decimal("250"))


def test_enodoro_summary_is_hydrated_with_detailed_invoice_lines(monkeypatch):
    summary = {"id": 2751, "entity": {"name": "ENODORO SRL"}, "date": "2026-09-30"}
    calls = []

    def fake_get(path, parameters):
        calls.append((path, parameters))
        return {"data": {"items_list": [{"code": "EPE919", "description": "NUTRIFERM ADVANCE KG.1"}]}}

    monkeypatch.setattr(fattureincloud, "_get", fake_get)
    result = fattureincloud._hydrate_enodoro_purchase("company", "received_documents", summary)
    assert result["date"] == "2026-09-30"
    assert result["items_list"][0]["code"] == "EPE919"
    assert calls == [("/c/company/received_documents/2751", {"fieldset": "detailed"})]


def test_non_enodoro_summary_is_not_hydrated(monkeypatch):
    monkeypatch.setattr(fattureincloud, "_get", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected call")))
    result = fattureincloud._hydrate_enodoro_purchase("company", "received_documents", {"id": 1, "entity": {"name": "Other"}})
    assert result["id"] == 1


def test_purchase_reconciliation_counts_known_and_unquantified_use(monkeypatch):
    monkeypatch.setattr(enology_process, "estate_id", lambda: "estate")
    monkeypatch.setattr(enology_process, "fetch_all", lambda *_args, **_kwargs: [{
        "product_catalog_id": "p1", "manufacturer": "ENARTIS", "product_name": "NUTRIFERM ADVANCE",
        "normalized_name": "nutriferm advance", "invoice_number": "2751/00/2026", "invoice_date": "2026-09-30",
        "supplier_article_code": "EPE919", "purchased_quantity": 1000, "purchased_unit": "g",
        "taxable_amount_eur": 16.39, "match_status": "matched",
    }])
    additions = [
        {"event_status": "applied", "additive_name": "NUTRIFERM ADVANCE", "quantity": 400, "unit": "g", "wine_lot_id": "lot-1"},
        {"event_status": "applied", "additive_name": "NUTRIFERM ADVANCE", "quantity": None, "unit": None, "wine_lot_id": "lot-2"},
    ]
    row = enology_process._enology_purchase_reconciliation(2026, additions)[0]
    assert row["purchased_g"] == 1000
    assert row["used_g"] == 400
    assert row["remaining_g"] == 600
    assert row["unquantified_use_count"] == 1
    assert row["status"] == "usage_unquantified"


def test_year_end_recipe_uses_actual_additions_only():
    lots = [{"id": "l1", "code": "NM-2026-01", "variety_summary": "Nerello Mascalese", "volume_l": 1600,
             "additive_prediction_pipeline": {"streamlined_recipe": {"used_products": [
                 {"product_name": "NUTRIFERM ADVANCE", "actual_quantity": 400, "actual_unit": "g"}
             ]}}}]
    recipe = enology_process._year_end_batch_recipes(2026, lots)[0]
    assert recipe["recipe_status"] == "complete"
    assert recipe["products"][0]["product_name"] == "NUTRIFERM ADVANCE"


def test_release_version_is_1_10_44():
    from pathlib import Path
    assert 'version: "1.10.48"' in (Path(__file__).parents[1] / "config.yaml").read_text()


def test_all_enodoro_invoice_articles_are_seeded():
    from pathlib import Path
    sql = (Path(__file__).parents[1] / "db/migrations/204_enology_purchase_reconciliation.sql").read_text()
    for code in ("EPE919", "EPC852", "ENA026", "EPE548", "EPE178", "EPC497", "EPC436", "EPC399", "EPC843", "EPE787", "ENA029"):
        assert code in sql
