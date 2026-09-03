from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t04_owner_correction_moves_real_wine_to_2025_without_emptying_it():
    migration = (ROOT / "db/migrations/145_2025_documented_bottling_and_grenache.sql").read_text()
    assert "c.code='T-04'" in migration
    assert "s25.vintage_year=2025" in migration
    assert "w.volume_l=225" in migration
    assert "w.stage='aging'" in migration
    assert "2025-GRN-C01" in migration


def test_ddt_bottling_is_documentary_and_does_not_invent_inventory():
    migration = (ROOT / "db/migrations/145_2025_documented_bottling_and_grenache.sql").read_text()
    assert "2916,2187.000,NULL,NULL,6,486" in migration
    assert "1176,882.000,NULL,NULL,6,192" in migration
    assert "4092" in migration
    assert "3,069 L bottled" in migration
    assert "INSERT INTO finished_wine_lots" not in migration
    assert "INSERT INTO finished_wine_inventory_movements" not in migration


def test_live_cellar_uses_the_lots_actual_vintage():
    source = (ROOT / "app/domains/cellar_routes.py").read_text()
    assert "ws.vintage_year" in source
    assert 'tank["vintage_year"] = int(tank["vintage_year"])' in source


def test_documentary_bottling_ui_distinguishes_delivery_and_source_evidence():
    source = (ROOT / "app/static/assets/bottling.js").read_text()
    assert "event_date_kind==='delivery'" in source
    assert "Inventory not inferred" in source
    assert "View ${esc(item.caption" in source
