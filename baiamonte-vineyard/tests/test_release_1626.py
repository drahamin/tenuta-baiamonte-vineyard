from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_and_selected_lot_laboratory_scope():
    assert 'version: "1.10.27"' in (ROOT / "config.yaml").read_text()
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    markup = (ROOT / "app/static/index.html").read_text()
    assert "function scopedEnologyData(data,lot)" in frontend
    assert "renderEnologyDecisionTable(scoped.lots)" in frontend
    assert "renderCompactLabQueue(scoped,$('enologyNextLabTests'))" in frontend
    assert "renderScheduledEnologyTests(scoped)" in frontend
    assert "Current recipe inputs · selected wine lot" in markup
    assert "selected wine lot only" in markup


def test_red_recipe_separates_press_mlf_racking_and_aging():
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    assert "title:'Press & separate'" in frontend
    assert "roles:[]" in frontend
    assert "title:'Malolactic fermentation'" in frontend
    assert "title:'Settle, rack & assess'" in frontend
    assert "title:'Stabilize & age'" in frontend
    assert "Seven ordered red-wine stages" in frontend
    assert "title:'Press, finish & age'" not in frontend
