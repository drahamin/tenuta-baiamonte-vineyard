from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_official_registry_keeps_complete_area_authoritative():
    migration = (ROOT / "db/migrations/146_official_document_registry.sql").read_text()
    assert "official_vineyard_area_m2',9144" in migration
    assert "coverage_status','incomplete_new_system_extract" in migration
    assert "authoritative_current_area_m2',9144" in migration
    assert "expected_productive_year',2027" in migration
    assert "projected_productive_area_ha_2027',1.2144" in migration
    assert "2026,'reference'" in migration
    assert "estate-baiamonte" not in migration


def test_all_seeded_original_pdfs_are_bundled():
    migrations = "\n".join(path.read_text() for path in (ROOT / "db/migrations").glob("*.sql"))
    files = list((ROOT / "docs/official").glob("*.pdf"))
    assert len(files) >= 7
    for path in files:
        assert path.name in migrations
        assert path.read_bytes().startswith(b"%PDF-")


def test_parcel_78_registration_receipt_is_source_backed():
    migration = (ROOT / "db/migrations/216_register_parcel_78_comodato_receipt.sql").read_text()

    assert "26100609245919455-000001" in migration
    assert "'002876'" in migration
    assert "'2026-01-02'" in migration
    assert "'2046-12-31'" in migration
    assert "JSON_ARRAY('83/78')" in migration


def test_admin_registry_and_atlas_links_are_wired():
    routes = (ROOT / "app/domains/official_documents.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    ui = (ROOT / "app/static/index.html").read_text()
    assert 'prefix="/official-documents"' in routes
    assert '"official_documents": official_documents' in main
    assert '"official_sources"' in main
    assert 'id="officialDocsList"' in ui
    assert 'id="atlasAreaMetrics"' in ui
