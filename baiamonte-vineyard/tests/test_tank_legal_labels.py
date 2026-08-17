from pathlib import Path

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_schema_keeps_legal_identity_with_wine_and_tablet_link_stable():
    sql = read("db/migrations/032_tank_legal_labels.sql")
    assert "CREATE TABLE IF NOT EXISTS wine_lot_legal_profiles" in sql
    assert "UNIQUE KEY uq_wine_lot_legal_profile (wine_lot_id)" in sql
    assert "FOREIGN KEY (wine_lot_id) REFERENCES wine_lots(id) ON DELETE RESTRICT" in sql
    assert "CREATE TABLE IF NOT EXISTS cellar_tank_labels" in sql
    assert "UNIQUE KEY uq_cellar_tank_label_token (public_token)" in sql
    assert "CREATE TABLE IF NOT EXISTS cellar_label_kiosks" in sql
    assert "UNIQUE KEY uq_cellar_label_kiosk_token (public_token)" in sql
    assert "FOREIGN KEY (container_id) REFERENCES cellar_containers(id) ON DELETE SET NULL" in sql


def test_label_service_has_per_tank_and_reassignable_kiosk_routes():
    server = read("app/tank_label_server.py")
    assert '@display_app.get("/tank/{token}"' in server
    assert '@display_app.get("/kiosk/{token}"' in server
    assert '@display_app.get("/api/tank/{token}"' in server
    assert '@display_app.get("/api/kiosk/{token}"' in server
    assert "apply_live_sensor_readings" in server
    assert 'data.get("reading_mode") != "sensor"' in server
    entrypoint = read("entrypoint.py")
    assert "app.tank_label_server:display_app" in entrypoint
    assert '"8102"' in entrypoint


def test_admin_can_edit_legal_data_and_manage_tablets():
    html = read("app/static/index.html")
    js = frontend_source(ROOT)
    api = read("app/main.py")
    for field in (
        "wine_type",
        "vintage_year",
        "origin_country",
        "denomination_class",
        "content_description",
        "processing_phase",
        "racking_history",
        "legal_notes",
    ):
        assert f'name="{field}"' in html
    assert "Cellar legal labels &amp; tablets" in html
    assert "renderTankLegalLabels" in js
    assert 'api/v1/agronomy/label-kiosks' in js
    assert '@app.post("/api/v1/agronomy/label-kiosks"' in api
    assert '@app.put("/api/v1/agronomy/label-kiosks/{kiosk_id}"' in api
    assert '@app.delete("/api/v1/agronomy/label-kiosks/{kiosk_id}"' in api


def test_label_visual_is_branded_animated_and_motion_safe():
    css = read("app/static/assets/tank-label.css")
    js = read("app/static/assets/tank-label.js")
    assert "@keyframes" in css
    assert "prefers-reduced-motion" in css
    assert ".vessel-bubbles" in css
    assert ".wine-fill" in css
    assert "/brand/logo.png" in read("app/tank_label_server.py")
    assert "setInterval(refresh,30000)" in "".join(js.split())
    assert "BAIAMONTE_KIOSK_TOKEN" in js


def test_release_exposes_label_port():
    config = read("config.yaml")
    assert 'version: "1.2.1"' in config
    assert "8102/tcp" in config


def test_startup_backfills_labels_for_every_active_tank():
    api = read("app/main.py")
    start = api.index("def _ensure_current_manual_tanks")
    end = api.index('@app.post("/api/v1/agronomy/tanks"', start)
    startup_import = api[start:end]
    assert "SELECT id FROM cellar_containers WHERE estate_id=%s AND active=1" in startup_import
    assert 'ensure_tank_label(cursor, tank["id"])' in startup_import


def test_admin_label_links_always_use_vineyard_vpn_origin():
    js = frontend_source(ROOT)
    assert "const TANK_LABEL_ORIGIN='http://192.168.0.10:8102'" in js
    assert "location.hostname}:8102" not in js


def test_admin_prints_current_label_in_a4_and_thermal_formats():
    html = read("app/static/index.html")
    admin_js = frontend_source(ROOT)
    label_js = read("app/static/assets/tank-label.js")
    label_css = read("app/static/assets/tank-label.css")
    assert 'id="agronomyPrintTankLabelA4"' in html
    assert 'id="agronomyPrintTankLabelThermal"' in html
    assert "function printTankLabel(input,format)" in admin_js
    assert "url.searchParams.set('print',format)" in admin_js
    assert 'printTankLabel(form.elements.label_url,\'a4\')' in admin_js
    assert 'printTankLabel(form.elements.label_url,\'thermal\')' in admin_js
    assert 'window.print()' in label_js
    assert 'size:4in 6in' in label_js
    assert 'size:A4 landscape' in label_js
    assert '<small>Note legali</small>' in label_js
    assert 'html.print-thermal' in label_css


def test_structured_cellar_controls_and_legal_defaults_are_migrated():
    sql = read("db/migrations/034_cellar_structured_labels.sql")
    assert "MODIFY COLUMN container_type ENUM" in sql
    assert "'aging'" in sql
    assert "ADD COLUMN IF NOT EXISTS cantiniere" in sql
    service = read("app/tank_labels.py")
    assert '"fermentation"' in service
    assert '"malo"' in service
    assert '"Azienda Agricola Tenuta Baiamonte"' in service


def test_wine_color_is_stored_and_rendered_on_every_vessel_surface():
    migration = read("db/migrations/035_cellar_wine_color.sql")
    service = read("app/tank_labels.py")
    cellar_js = read("app/static/assets/cellar.js")
    vessel_js = read("app/static/assets/wine-vessels.js")
    label_js = read("app/static/assets/tank-label.js")
    assert "ADD COLUMN IF NOT EXISTS wine_color" in migration
    assert 'WINE_COLORS = ("red", "white", "rose")' in service
    assert "select.name='wine_color'" in cellar_js
    assert "#cellarTanks .tank-card-new" in vessel_js
    assert "#tvTanks .tv-tank" in vessel_js
    assert "wine-${wineColor(d)}" in label_js


def test_cellar_and_tablet_saves_preserve_the_active_admin_view():
    cellar_js = read("app/static/assets/cellar.js")
    assert "document.querySelector('.tabs button.active')" in cellar_js
    assert "button.click()" in cellar_js
    assert "window.scrollTo" in cellar_js
