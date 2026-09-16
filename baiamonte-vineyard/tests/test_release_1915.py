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


def test_digital_tag_refresh_exposes_the_complete_manual_reading_set():
    javascript = (ROOT / "app/static/assets/tank-label.js").read_text(encoding="utf-8")
    server = (ROOT / "app/tank_label_server.py").read_text(encoding="utf-8")
    for field in ("d.temp_c", "d.babo", "d.density_sg", "d.brix", "d.ph"):
        assert field in javascript
    assert 'DISPLAY_ASSET_VERSION = "1.4.40"' in server
