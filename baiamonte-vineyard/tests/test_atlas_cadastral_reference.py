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
    assert "let cadastral=null,cadastralFailed=false" in source
    assert "Optional cadastral reference could not initialize" in source
    assert "if(cadastral)overlays['Official cadastral reference']=cadastral" in source


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


def test_atlas_mobile_map_keeps_saved_land_visible_and_controls_compact():
    source = (ROOT / "app" / "static" / "app.js").read_text()
    performance = (ROOT / "app" / "static" / "assets" / "performance.js").read_text()
    styles = (ROOT / "app" / "static" / "app.css").read_text()

    assert "function geometryCenter" in performance
    assert "geometryCenter(row.geometry_geojson)" in source
    assert "${boundaryParcels.length}/${parcels.length} official land" in source
    assert "${registeredParcels.length} with registered vineyard area" in source
    assert "collapsed:compactMap" in source
    assert "if(!savedView||compactMap)fitLand()" in source
    assert "attributionControl:false" in source
    assert "prefix:false" in source
    assert ".estate-parcel-map .leaflet-control-attribution" in styles
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in styles


def test_legacy_svg_styles_do_not_override_leaflet_parcel_positioning():
    source = (ROOT / "app" / "static" / "app.js").read_text()
    styles = (ROOT / "app" / "static" / "control-center.css").read_text()

    assert "permanent:true" in source
    assert "official land boundaries saved" in source
    assert ".estate-parcel-map>svg{" in styles
    assert ".estate-parcel-map svg{" not in styles
    assert ".estate-parcel-map polygon" not in styles


def test_atlas_separates_official_land_parcels_from_building_units():
    backend = (ROOT / "app" / "main.py").read_text()
    prediction_sources = (ROOT / "app" / "prediction_sources.py").read_text()
    migration = (ROOT / "db" / "migrations" / "215_reconcile_cadastral_land_and_buildings.sql").read_text()

    assert '"buildings": buildings' in backend
    assert "record_type='land'" in backend
    assert "record_type='land'" in prediction_sources
    assert "parcel_number IN ('94','95')" in migration
    assert "'83','78','land'" in migration
    assert "contract_protocol,tenure_start" in backend
    assert "Registration / contract protocol" in (ROOT / "app" / "static" / "app.js").read_text()
