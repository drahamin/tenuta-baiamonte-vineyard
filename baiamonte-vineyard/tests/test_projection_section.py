from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_operations_and_tv_use_the_same_evidence_driven_scenario_range() -> None:
    main = (ROOT / "app" / "main.py").read_text()
    display = (ROOT / "app" / "display_data.py").read_text()
    calculation = 'float(forecast_evidence.get("recommended_scenario_range_pct") or 15) / 100'

    assert calculation in main
    assert calculation in display
    assert '(("Downside", 0.85), ("Working", 1.0), ("Upside", 1.15))' not in display


def test_projection_screen_clears_stale_content_and_labels_selected_year() -> None:
    javascript = (ROOT / "app" / "static" / "app.js").read_text()
    html = (ROOT / "app" / "static" / "index.html").read_text()

    assert 'id="projectionAllocationHeading"' in html
    assert 'id="projectionOutlookHeading"' in html
    assert "compactRows('projectionAllocations',[],()=>'', 'No allocation plan.')" in javascript
    assert "barChart('projectionChart',[],[]" in javascript
    assert "allocationHeading.textContent=`${p.year} allocation`" in javascript
    assert "outlookHeading.textContent=forecastYears.length?" in javascript


def test_projection_screen_exposes_forecast_method_sources_and_live_list_state() -> None:
    javascript = (ROOT / "app" / "static" / "app.js").read_text()
    main = (ROOT / "app" / "main.py").read_text()
    display = (ROOT / "app" / "display_data.py").read_text()

    assert "p.production_forecast_method" in javascript
    assert "Sources: ${sourceNames.join(', ')}." in javascript
    assert "varietyNode.classList.toggle('empty',!varieties.length)" in javascript
    assert "Database planning records; not a learned forecast model." in main
    assert "Database planning records; not a learned forecast model." in display
    assert "Workbook planning projections" not in main
    assert "Workbook planning projections" not in display
