from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_harvest_extension_exports_shared_render_helpers_without_patch_artifacts() -> None:
    javascript = (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()

    assert "\nfunction known(" in javascript
    assert "\nfunction renderProjections(" in javascript
    assert not any(line.startswith("+") for line in javascript.splitlines())


def test_operations_and_tv_use_the_same_evidence_driven_scenario_range() -> None:
    main = (ROOT / "app" / "main.py").read_text() + (ROOT / "app" / "domains" / "projections.py").read_text()
    display = (ROOT / "app" / "display_data.py").read_text()
    calculation = 'float(forecast_evidence.get("recommended_scenario_range_pct") or 15) / 100'

    assert calculation in main
    assert calculation in display
    assert '(("Downside", 0.85), ("Working", 1.0), ("Upside", 1.15))' not in display


def test_projection_screen_clears_stale_content_and_labels_selected_year() -> None:
    javascript = (ROOT / "app" / "static" / "app.js").read_text() + (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()
    html = (ROOT / "app" / "static" / "index.html").read_text()

    assert 'id="projectionAllocationHeading"' in html
    assert 'id="projectionOutlookHeading"' in html
    assert "compactRows('projectionAllocations',[],()=>'', 'No allocation plan.')" in javascript
    assert "stackedBarChart('projectionChart',[],[]" in javascript
    assert "allocationHeading.textContent=`${p.year} allocation`" in javascript
    assert "outlookHeading.textContent=forecastYears.length?" in javascript


def test_projection_screen_exposes_forecast_method_sources_and_live_list_state() -> None:
    javascript = (ROOT / "app" / "static" / "app.js").read_text() + (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()
    main = (ROOT / "app" / "main.py").read_text() + (ROOT / "app" / "domains" / "projections.py").read_text()
    display = (ROOT / "app" / "display_data.py").read_text()

    assert "p.production_forecast_method" in javascript
    assert "Sources: ${sourceNames.join(', ')}." in javascript
    assert "varietyNode.classList.toggle('empty',!varieties.length)" in javascript
    assert "Database planning records; not a learned forecast model." in main
    assert "vintage-isolated, approved damage assessments" in display
    assert "Workbook planning projections" not in main
    assert "Workbook planning projections" not in display


def test_projection_totals_expose_variety_composition_and_exact_breakdowns() -> None:
    javascript = (ROOT / "app" / "static" / "assets" / "analytics.js").read_text() + (ROOT / "app" / "static" / "assets" / "harvest.js").read_text()
    html = (ROOT / "app" / "static" / "index.html").read_text()

    assert "function stackedBarChart(" in javascript
    assert "function reconciledProjectionParts(" in javascript
    assert "projectionHistoryLegend" in html
    assert "projectionBreakdown" in html
    assert "projectionHistoryBreakdown" in html
    assert "Unallocated" in javascript
    assert "Mamma Fiamma · Nerello/Grenache" in javascript
    assert "mamma\\s+fiamma" in javascript


def test_historical_variety_rows_keep_recorded_wine_volume_for_chart_breakdowns() -> None:
    source = (ROOT / "app" / "historical_dashboard.py").read_text()

    assert 'row["wine_l"] = summary.get("wine_l")' in source


def test_2024_final_total_removes_false_unallocated_volume_without_splitting_blend() -> None:
    migration = (ROOT / "db" / "migrations" / "214_reconcile_2024_final_wine_total.sql").read_text()

    assert "886 L Grecanico plus 881 L Mamma Fiamma" in migration
    assert "wine_l=1767.000" in migration
    assert "unallocated_l',0" in migration
    assert "component split is unknown" in migration
