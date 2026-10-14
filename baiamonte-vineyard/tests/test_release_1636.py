from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cellar_graphic_hides_empty_tanks_without_removing_records():
    app = (ROOT / "app/static/app.js").read_text()
    vessels = (ROOT / "app/static/assets/wine-vessels.js").read_text()
    cellar_admin = (ROOT / "app/static/assets/cellar.js").read_text()
    assert "function cellarGraphicTankVisible" in app
    assert "volume>0" in app
    assert "(c.tanks||[]).filter(cellarGraphicTankVisible)" in app
    assert "Empty vessels remain available in Tank Records" in app
    assert "filter(row=>typeof cellarGraphicTankVisible" in vessels
    assert "const tanks=a.cellar?.tanks||[]" in cellar_admin


def test_release_version_is_1_10_50():
    assert 'version: "1.10.57"' in (ROOT / "config.yaml").read_text()
