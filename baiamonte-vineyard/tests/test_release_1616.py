from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vintage_change_preserves_and_refreshes_active_workspace():
    javascript = (ROOT / "app/static/app.js").read_text()
    setup = javascript.split("function setupYears()", 1)[1].split(
        "function weatherDate", 1
    )[0]
    assert "document.querySelector('.view.active')" in setup
    assert "await loadAll()" in setup
    assert "activateViewButton(button)" in setup
    assert "window.loadBottling?.()" in setup
    assert "window.loadFertilization?.()" in setup
    assert "window.loadNutritionProgram?.(" in setup


def test_shared_vintage_loader_discards_stale_year_responses():
    javascript = (ROOT / "app/static/app.js").read_text()
    loader = javascript.split("async function loadAll()", 1)[1].split(
        "function activateViewButton", 1
    )[0]
    assert "const request=++loadAllRequest,year=state.year" in loader
    assert "request!==loadAllRequest||year!==state.year" in loader
    assert "dashboard?year=${year}" in loader
    assert "labs/history?from_year=${year}&to_year=${year}" in loader


def test_laboratory_outlook_stays_inside_home_assistant_ingress():
    outlook = (ROOT / "app/static/assets/lab-outlook.js").read_text()
    javascript = (ROOT / "app/static/app.js").read_text()
    assert "optionalApi(`api/v1/labs/vintage-outlook?year=${year}`" in outlook
    assert "optionalApi(`/api/v1/labs/vintage-outlook" not in outlook
    setup = javascript.split("function setupLabAnalytes()", 1)[1].split(
        "async function loadLabComparison", 1
    )[0]
    assert "window.loadLabOutlook?.()" in setup
    assert "loadLabComparison()" in setup


def test_bottling_vintage_loader_discards_stale_year_responses():
    bottling = (ROOT / "app/static/assets/bottling.js").read_text()
    assert "const request=++bottlingRequest,year=state.year" in bottling
    assert "request!==bottlingRequest||year!==state.year" in bottling
    assert "$('year')?.addEventListener('change'" not in bottling


def test_historical_bottle_backfill_remains_source_backed():
    migration = (ROOT / "db/migrations/097_bottling_traceability_and_costs.sql").read_text()
    assert "2023 vintage_year,5610.000 grapes_kg,3755.000 wine_l,5007 bottles" in migration
    assert "2024,NULL,2357.000,3143" in migration
    assert "2025,5236.000,3998.000,5333" in migration
    assert "Bottle equivalents are a 750 ml conversion" in migration


def test_release_1616_is_recorded():
    assert "## 1.6.16" in (ROOT / "CHANGELOG.md").read_text()
