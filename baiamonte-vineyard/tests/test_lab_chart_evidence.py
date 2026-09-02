from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lab_chart_has_harvest_markers_and_report_point_navigation() -> None:
    app = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    analytics = (ROOT / "app/static/assets/analytics.js").read_text(encoding="utf-8")
    outlook = (ROOT / "app/static/assets/lab-outlook.js").read_text(encoding="utf-8")

    assert "function drawLabChart" in app
    assert "function labHarvestMarkers" in outlook
    assert "first_pick_date" in outlook
    assert "Harvest · dashed = forecast" in outlook
    assert "function openLabChartEvidence" in outlook
    assert "onPointClick:openLabChartEvidence" in outlook
    assert "options.markers" in analytics
    assert "hitTargets" in analytics
    assert "pointData" in outlook


def test_lab_routes_return_retained_report_links() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    laboratory = (ROOT / "app/domains/laboratory.py").read_text(encoding="utf-8")

    assert "entity_type='lab_sample'" in main
    assert '"report": {' in main
    assert '"report_url": row.get("report_url")' in laboratory
