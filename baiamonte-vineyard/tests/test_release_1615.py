from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_laboratory_outlook_is_safe_before_its_bundle_loads():
    javascript = (ROOT / "app/static/app.js").read_text()
    draw_lab_chart = javascript.split("function drawLabChart()", 1)[1].split(
        "function renderLabTrends()", 1
    )[0]
    assert "window.renderLabOutlook?.()" in draw_lab_chart
    assert "renderLabOutlook();" not in draw_lab_chart


def test_requested_route_waits_for_session_permissions():
    javascript = (ROOT / "app/static/app.js").read_text()
    load_all = javascript.split("async function loadAll()", 1)[1].split(
        "function activateViewButton", 1
    )[0]
    assert load_all.count("activateRequestedView();") == 1
    assert load_all.index("applyAccess();") < load_all.index("activateRequestedView();")
    startup_tail = javascript.split("function loadEtna(refresh=false)", 1)[1]
    assert "activateRequestedView();" not in startup_tail


def test_release_1615_is_recorded():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert "## 1.6.15" in changelog
