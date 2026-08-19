from pathlib import Path
from types import SimpleNamespace
import base64

from fastapi.testclient import TestClient

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


def test_tablet_enrollment_keeps_device_identity_private_and_pairing_temporary():
    sql = read("db/migrations/037_cellar_tablet_enrollment.sql")
    assert "CREATE TABLE IF NOT EXISTS cellar_label_enrollments" in sql
    assert "device_key_hash CHAR(64)" in sql
    assert "pairing_code CHAR(6)" in sql
    assert "expires_at DATETIME(6)" in sql
    assert "display_name VARCHAR(160)" in sql
    assert "device_role VARCHAR(24)" in sql
    assert "destination_url VARCHAR(500)" in sql
    assert "UNIQUE KEY uq_cellar_label_enrollment_device" in sql


def test_label_service_has_per_tank_and_reassignable_kiosk_routes():
    server = read("app/tank_label_server.py")
    assert '@display_app.get("/tank/{token}"' in server
    assert '@display_app.get("/kiosk/{token}"' in server
    assert '@display_app.get("/api/tank/{token}"' in server
    assert '@display_app.get("/api/kiosk/{token}"' in server
    assert '@display_app.get("/enroll/{device_key}"' in server
    assert '@display_app.get("/api/enroll/{device_key}"' in server
    assert "hmac.compare_digest" in server
    assert "cellar_label_enrollment_key" in server
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
    assert '@app.get("/api/v1/agronomy/label-provisioning"' in api
    assert '@app.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/approve"' in api
    assert '@app.delete("/api/v1/agronomy/label-enrollments/{enrollment_id}"' in api
    assert '@app.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/reprovision"' in api
    assert 'id="agronomyEnrollmentList"' in html
    assert 'id="agronomyProvisionedDeviceList"' in html
    assert 'value="label">Tank label' in js
    assert 'value="ipad">Vineyard Operations · ipad' in js
    assert "data-reprovision-device" in js
    assert "Any existing tank-label URL for it will be retired" in js


def test_label_visual_is_branded_animated_and_motion_safe():
    css = read("app/static/assets/tank-label.css")
    js = read("app/static/assets/tank-label.js")
    assert "@keyframes" in css
    assert "prefers-reduced-motion" in css
    assert ".vessel-bubbles" in css
    assert ".wine-fill" in css
    for vessel in ("tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other"):
        assert f".vessel-visual.vessel-{vessel}" in css
    assert "const vesselType" in js
    assert "d.capacity_l" in js
    assert "Livello calcolato" in js
    assert "active-fermentation" in js
    assert "etnaPlume" in css and "etnaSparks" in css
    assert "brand-eruption" in read("app/tank_label_server.py")
    assert "cantiniere_telephone" in js
    assert "sparkline" in js and "d.trends" in js
    assert "+39 340 9695752" in read("app/tank_labels.py")
    assert "Azienda Agricola Tenuta Baiamonte S.S." in read("app/tank_labels.py")
    assert "Azienda Agricola Tenuta Baiamonte S.S." in read("db/migrations/038_label_legal_identity.sql")
    assert "html.print-a4 .legal-card" in css
    assert "html.print-thermal .trend-panel" in css
    assert "orientation:portrait" in css
    assert "DISPLAY_ASSET_VERSION" in read("app/tank_label_server.py")
    assert '"/assets/"' in read("app/tank_label_server.py")
    assert "window.visualViewport" in js
    assert 'classList.toggle("label-compact"' in js
    assert 'classList.toggle("label-short"' in js
    assert "--label-visible-height" in css
    assert "-webkit-overflow-scrolling:touch" in css
    assert "touch-action:pan-y" in css
    assert "html.label-compact .fields" in css
    assert "html.label-short .micro-chart" in css
    assert ".vessel-visual::after,.vessel-visual .wine-fill span{display:none!important}" in css
    assert "/brand/logo.png" in read("app/tank_label_server.py")
    assert "setInterval(refresh,30000)" in "".join(js.split())
    assert "BAIAMONTE_KIOSK_TOKEN" in js


def test_display_identity_is_installable_and_available_everywhere():
    server = read("app/tank_label_server.py")
    proxy = read("custom_components/baiamonte_branding/label_proxy.py")
    dockerfile = read("Dockerfile")
    manifest = read("app/static/site.webmanifest")
    for page in ("app/static/index.html", "app/static/display.html", "app/static/crew.html"):
        source = read(page)
        assert 'rel="icon"' in source
        assert 'rel="apple-touch-icon"' in source
        assert 'rel="manifest"' in source
        assert 'apple-mobile-web-app-capable' in source
    assert '@display_app.get("/brand/icon.png")' in server
    assert '@display_app.get("/manifest/{display_kind}/{token}.webmanifest"' in server
    assert 'purpose": "any maskable"' in server
    assert 'rel="apple-touch-icon"' in server
    assert 'rel="manifest"' in server
    assert "brand/(?:(?:logo|icon)" in proxy
    assert "manifest/(?:tank|kiosk|enroll)" in proxy
    assert "COPY icon.png app/static/icon.png" in dockerfile
    assert '"display_override": ["fullscreen", "standalone"]' in manifest


def test_fully_provisioning_keeps_manual_url_and_adds_local_qr():
    html_source = read("app/static/index.html")
    js = read("app/static/assets/cellar.js")
    api = read("app/main.py")
    qr_builder = read("app/display_provisioning.py")
    requirements = read("requirements.txt")
    assert 'id="agronomyProvisioningUrl"' in html_source
    assert 'id="agronomyCopyProvisioning"' in html_source
    assert 'id="agronomyShowProvisioningQr"' in html_source
    assert 'Show Start URL &amp; QR' in html_source
    assert "cloud.fully-kiosk.com/cloud/expressProvisioning" in html_source
    assert "label-provisioning/qr" in js
    assert "provisioningQr.hidden=false" in js
    assert "window.prompt('Copy this link',value)" in js
    assert "Clipboard blocked — copy the selected link" in js
    assert '@app.get("/api/v1/agronomy/label-provisioning/qr"' in api
    assert "segno.make(start_url" in qr_builder
    assert 'start_url = f"{origin}/enroll/$deviceID"' in qr_builder
    assert "segno==" in requirements


def test_release_exposes_label_port():
    config = read("config.yaml")
    version_line = next(line for line in config.splitlines() if line.startswith("version:"))
    version = tuple(int(part) for part in version_line.split('"')[1].split("."))
    assert version >= (1, 2, 4)
    assert "8102/tcp" in config


def test_startup_backfills_labels_for_every_active_tank():
    api = read("app/main.py")
    start = api.index("def _ensure_current_manual_tanks")
    end = api.index('@app.post("/api/v1/agronomy/tanks"', start)
    startup_import = api[start:end]
    assert "SELECT id FROM cellar_containers WHERE estate_id=%s AND active=1" in startup_import
    assert 'ensure_tank_label(cursor, tank["id"])' in startup_import


def test_admin_label_links_use_configured_public_origin_with_lan_fallback():
    js = frontend_source(ROOT)
    api = read("app/main.py")
    assert "legal_label_options?.origin" in js
    assert "cellar_label_public_origin" in api
    assert 'return "http://192.168.0.10:8102"' in api
    assert "location.hostname}:8102" not in js


def test_nabu_gateway_is_public_read_only_and_path_aware():
    proxy = read("custom_components/baiamonte_branding/label_proxy.py")
    integration = read("custom_components/baiamonte_branding/__init__.py")
    api = read("app/main.py")
    label_js = read("app/static/assets/tank-label.js")
    enroll_js = read("app/static/assets/tank-enroll.js")
    assert 'PUBLIC_PREFIX = "/api/baiamonte_labels"' in proxy
    assert "requires_auth = False" in proxy
    assert "async def get(" in proxy
    assert "async def post(" not in proxy
    assert "async def delete(" not in proxy
    assert "api/v1" not in proxy
    assert "8100" not in proxy and "8099" not in proxy and "8123" not in proxy
    assert "BaiamonteLabelProxyView" in integration
    assert "parsed.query or parsed.fragment" in api
    assert 'location.pathname.startsWith("/api/baiamonte_labels/")' in label_js
    assert 'window.location.pathname.startsWith("/api/baiamonte_labels/")' in enroll_js
    assert "publicDestination(payload.destination_url || payload.kiosk_url)" in enroll_js


def test_fully_profile_uses_device_id_and_supports_external_ipad_dashboard():
    api = read("app/main.py")
    config = read("config.yaml")
    entrypoint = read("entrypoint.py")
    provisioning = read("app/display_provisioning.py")
    service = read("app/tank_labels.py")
    assert 'enroll/$deviceID"' in provisioning
    assert '"basic_auth_username": "baiamonte-enroll"' in provisioning
    assert "cellar_label_enrollment_key: password?" in config
    assert "cellar_ipad_dashboard_url" in config
    assert '"cellar_label_public_origin": "CELLAR_LABEL_PUBLIC_ORIGIN"' in entrypoint
    assert '"cellar_label_enrollment_key": "CELLAR_LABEL_ENROLLMENT_KEY"' in entrypoint
    assert '"cellar_ipad_dashboard_url": "CELLAR_IPAD_DASHBOARD_URL"' in entrypoint
    assert 'device_role not in {"label", "ipad"}' in service
    assert '"device_role": "ipad"' in service


def test_public_enrollment_requires_bootstrap_key_and_never_caches(monkeypatch):
    from app import tank_label_server

    monkeypatch.setattr(
        tank_label_server,
        "get_settings",
        lambda: SimpleNamespace(cellar_label_enrollment_key="private-bootstrap-key"),
    )
    monkeypatch.setattr(
        tank_label_server,
        "request_kiosk_enrollment",
        lambda device_key: {"status": "pending", "pairing_code": "482913", "device_hint": "A1B2C3D4"},
    )
    client = TestClient(tank_label_server.display_app)
    wrong = base64.b64encode(b"baiamonte-enroll:wrong").decode()
    valid = base64.b64encode(b"baiamonte-enroll:private-bootstrap-key").decode()
    assert client.get("/enroll/device-A1B2C3D4", headers={"Authorization": f"Basic {wrong}"}).status_code == 401
    response = client.get("/enroll/device-A1B2C3D4", headers={"Authorization": f"Basic {valid}"})
    assert response.status_code == 200
    assert "482913" in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_approved_ipad_enrollment_redirects_to_external_dashboard(monkeypatch):
    from app import tank_label_server

    monkeypatch.setattr(
        tank_label_server,
        "get_settings",
        lambda: SimpleNamespace(cellar_label_enrollment_key="private-bootstrap-key"),
    )
    monkeypatch.setattr(
        tank_label_server,
        "request_kiosk_enrollment",
        lambda device_key: {
            "status": "approved",
            "device_role": "ipad",
            "destination_url": "https://example.ui.nabu.casa/vineyard-ipad/home",
        },
    )
    client = TestClient(tank_label_server.display_app)
    valid = base64.b64encode(b"baiamonte-enroll:private-bootstrap-key").decode()
    response = client.get(
        "/enroll/device-A1B2C3D4",
        headers={"Authorization": f"Basic {valid}"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.ui.nabu.casa/vineyard-ipad/home"


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
    assert '"Azienda Agricola Tenuta Baiamonte S.S."' in service


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
