import json
from datetime import date
from pathlib import Path

from app.domains.product_catalog import (
    CATALOG_WRITE_BATCH,
    administrative_status,
    ministry_overlay_allows_projection,
    normalize_product_name,
    normalize_registration,
    parse_catalog,
)


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_write_batch_stays_below_live_mariadb_query_timeout_threshold():
    assert CATALOG_WRITE_BATCH <= 50


def test_ministry_catalog_normalizes_identity_without_collapsing_registration():
    assert normalize_registration(" 123-45 ") == "012345"
    assert normalize_product_name("Zòlfó 80% WG") == "ZOLFO 80 WG"


def test_ministry_catalog_parses_the_official_shape_and_status():
    source = [{
        "num_registrazione": str(10000 + index),
        "denominazione_prodotto": f"Prodotto {index}",
        "ragione_sociale": "Holder",
        "data_scadenza_autorizzazione": "31/12/2099",
        "stato_amministrativo": "Autorizzato",
        "sostanze_attive": "Zolfo",
        "codice_formulazione": "WG",
    } for index in range(100)]
    rows = parse_catalog(json.dumps(source).encode())
    assert len(rows) == 100
    assert rows[0]["administrative_status"] == "authorized"
    assert rows[0]["active_substances"] == "Zolfo"


def test_ministry_overlay_blocks_trusted_revoked_or_expired_products():
    base = {"ministry_match_method": "exact_registration", "ministry_review_status": "automatic_exact"}
    assert ministry_overlay_allows_projection({**base, "ministry_status": "authorized", "ministry_expires_on": date(2099, 1, 1)})
    assert not ministry_overlay_allows_projection({**base, "ministry_status": "revoked"})
    assert not ministry_overlay_allows_projection({**base, "ministry_status": "authorized", "ministry_expires_on": date(2020, 1, 1)})
    assert not ministry_overlay_allows_projection({**base, "ministry_status": "authorized", "ministry_present": 0})
    assert administrative_status("Sospeso") == "suspended"


def test_name_only_overlay_does_not_silently_override_a_local_profile():
    assert ministry_overlay_allows_projection({
        "ministry_match_method": "normalized_name",
        "ministry_review_status": "needs_review",
        "ministry_status": "revoked",
    })


def test_catalog_routes_ui_scheduler_and_migration_are_connected():
    routes = (ROOT / "app/domains/treatment_routes.py").read_text()
    engine = (ROOT / "app/domains/treatments.py").read_text()
    process = (ROOT / "app/process_control.py").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    migration = (ROOT / "db/migrations/125_ministry_product_catalog.sql").read_text()
    assert "/api/v1/treatments/product-catalog/search" in routes
    assert "/authorize-use" in routes
    assert "ministry_overlay_allows_projection" in engine
    assert '"product_catalog"' in process
    assert 'id="ministryProductCatalog"' in html
    assert "CREATE TABLE IF NOT EXISTS ministry_product_catalog" in migration
