from pathlib import Path


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
    js = read("app/static/app.js")
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
    assert 'version: "1.1.5"' in config
    assert "8102/tcp" in config
