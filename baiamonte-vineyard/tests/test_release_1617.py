from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_laboratory_selector_explains_series_identity():
    javascript = (ROOT / "app/static/assets/lab-outlook.js").read_text()
    assert "row.sample_type||'other'" in javascript
    assert "row.stage?' / '" in javascript
    assert "row.analyte_name||row.analyte_code" in javascript


def test_release_version_is_consistent():
    assert 'version: "1.6.18"' in (ROOT / "config.yaml").read_text()
    assert 'version="1.6.18"' in (ROOT / "app/main.py").read_text()


def test_laboratory_defaults_to_comparable_series_and_uses_matching_endpoints():
    outlook = (ROOT / "app/static/assets/lab-outlook.js").read_text()
    dashboard = (ROOT / "app/static/app.js").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    assert 'Comparable history available' in outlook
    assert 'projected.length' in outlook
    assert "renderLabTrends()" in outlook
    assert "selected.historical_endpoints" in outlook
    assert "Like-for-like vintage endpoints" in outlook
    assert "Like-for-like sample summary" in outlook
    assert "Historical endpoint" in outlook
    assert "async function refreshLaboratoryData" in outlook
    assert "labHistory:history" in outlook
    assert "if(window.refreshLaboratoryData)await refreshLaboratoryData()" in dashboard
    assert 'id="labAnnualTableSubtitle"' in html
    assert 'id="labAnnualSubtitle"' in html


def test_giancarlo_prior_year_labor_is_source_backed_without_invention():
    migration = (ROOT / "db/migrations/111_giancarlo_prior_year_labor.sql").read_text()
    assert "source.source_file_id='gmail-proclama-giancarlo'" in migration
    assert "source.record_date BETWEEN '2024-12-01' AND '2025-11-30'" in migration
    assert "source.labor_hours*10.00" in migration
    assert "source.labor_hours IS NULL THEN NULL" in migration
    assert "'paid'" in migration
    assert "DATE_ADD(LAST_DAY(source.record_date),INTERVAL 15 DAY)" in migration
    assert "INSERT INTO labor_invoice_payments" in migration
    assert "'GIANCARLO-PAID-PRIOR-YEARS'" in migration
    assert "labor.labor_cost_eur>0" in migration
    assert "'verification_needed'" not in migration
    assert "'historical_import'" in migration
    assert "'migration-111'" in migration


def test_mirrored_historical_labor_is_not_double_counted():
    historical = (ROOT / "app/historical_dashboard.py").read_text()
    marker = "labor.source_labor_id=CONCAT('HISTORICAL-COST:',historical.id)"
    assert historical.count(marker) >= 2
