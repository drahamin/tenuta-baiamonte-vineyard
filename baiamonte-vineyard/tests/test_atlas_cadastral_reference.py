from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_atlas_uses_official_cadastral_reference_at_close_zoom():
    source = (ROOT / "app" / "static" / "app.js").read_text()

    assert "wms.cartografia.agenziaentrate.gov.it/inspire/wms/ows01.php" in source
    assert "CP.CadastralParcel,codice_plla,fabbricati" in source
    assert "code:'EPSG:4258'" in source
    assert "version:'1.1.1'" in source
    assert "minZoom:17" in source
    assert "Official cadastral reference" in source
    assert "Verified parcels & blocks" in source


def test_atlas_explains_reference_and_verified_geometry_are_distinct():
    markup = (ROOT / "app" / "static" / "index.html").read_text()

    assert "official Agenzia delle Entrate cadastral reference" in markup
    assert "Gold Baiamonte boundaries are separately saved and verified operational geometry" in markup


def test_atlas_can_trace_and_save_gold_baiamonte_boundaries():
    source = (ROOT / "app" / "static" / "app.js").read_text()
    styles = (ROOT / "app" / "static" / "app.css").read_text()

    assert "setupParcelBoundaryEditor" in source
    assert "Trace Baiamonte boundary" in source
    assert "data-boundary-undo" in source
    assert "color:'#f2cf45'" in source
    assert ".parcel-boundary-editor" in styles
