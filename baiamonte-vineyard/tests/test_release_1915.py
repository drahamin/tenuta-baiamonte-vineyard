from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_vintage_tank_identity_is_uniform_and_history_safe():
    migration = (ROOT / "db/migrations/163_uniform_current_vintage_tank_identity.sql").read_text(encoding="utf-8")
    assert "SET code='T-03'" in migration
    assert "Tank 3 · Grecanico 2026 · Primary" in migration
    assert "Tank 44 · Grecanico 2026 · Final Press" in migration
    assert "Mustalone 500 L · Grenache 2026" in migration
    assert "SET vessel_name='T-03'" in migration
    assert "SET vessel_name='T-06'" not in migration

    collision = (ROOT / "db/migrations/164_reconcile_physical_tank_3_collision.sql").read_text(encoding="utf-8")
    assert "code='ARCHIVE-T-03'" in collision
    assert "id='b125e0fc-9dd2-406b-b8e7-63ed935ff7ad'" in collision
    assert "id='05dd268e-89fd-4b1c-b486-cb19c95274eb'" in collision
    assert "SET code='T-03'" in collision


def test_digital_tag_refresh_exposes_the_complete_manual_reading_set():
    javascript = (ROOT / "app/static/assets/tank-label.js").read_text(encoding="utf-8")
    server = (ROOT / "app/tank_label_server.py").read_text(encoding="utf-8")
    for field in ("d.temp_c", "d.babo", "d.density_sg", "d.brix", "d.ph"):
        assert field in javascript
    assert 'DISPLAY_ASSET_VERSION = "1.4.47"' in server


def test_cellar_labels_have_a_complete_server_rendered_fallback():
    server = (ROOT / "app/tank_label_server.py").read_text(encoding="utf-8")
    css = (ROOT / "app/static/assets/tank-label.css").read_text(encoding="utf-8")
    assert 'data-server-fallback="true"' in server
    for field in ("level_pct", "volume_l", "capacity_l", "content_description", "vintage_year", "processing_phase", "temp_c", "babo"):
        assert field in server
    assert ".server-label-summary" in css

    from app.tank_label_server import _kiosk_page
    page = _kiosk_page("T-03 · Grecanico", "safe-token", True, data={
        "code": "T-03", "level_pct": 42.3, "volume_l": 1069.8, "capacity_l": 2531.1,
        "content_description": "Grecanico", "vintage_year": 2026, "processing_phase": "Primary",
        "temp_c": 18.4, "babo": 16.9,
    })
    assert 'data-server-fallback="true"' in page
    assert "1069.8 L / 2531.1 L" in page
    assert "Grecanico" in page


def test_compact_cellar_label_reserves_space_between_vessel_and_percentage():
    css = (ROOT / "app/static/assets/tank-label.css").read_text(encoding="utf-8")
    assert "grid-template-columns:minmax(126px,1fr) minmax(132px,1fr)" in css
    assert "padding:0 14px;gap:20px" in css
    assert ".level-callout strong{font-size:42px;white-space:nowrap}" in css


def test_short_cellar_label_does_not_clip_multi_line_legal_fields():
    javascript = (ROOT / "app/static/assets/tank-label.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/assets/tank-label.css").read_text(encoding="utf-8")
    assert javascript.count("field wide field-detail") == 4
    assert "html.label-short .field-detail,html.label-short .field-detail.wide{min-height:50px}" in css
    assert "html.label-compact .field>span{display:block;margin-top:2px" in css
    assert "white-space:normal" in css
    assert "overflow-y:auto;overscroll-behavior:contain" in css


def test_current_readings_merge_into_trends_and_grenache_lot_is_linked():
    labels = (ROOT / "app/tank_labels.py").read_text(encoding="utf-8")
    migration = (ROOT / "db/migrations/165_link_grenache_mustalone_current_lot.sql").read_text(encoding="utf-8")
    assert 'current_point = {' in labels
    assert 'matching[key] = current_point[key]' in labels
    assert "w.code='GRN-2026-01'" in migration
    assert "c.code='M-01'" in migration
    assert "w.current_container_id=c.id" in migration
    assert "not measured pressed-juice volume" in migration
    assert "COALESCE(wx.volume_l,wx.initial_l,0)>0" not in labels
