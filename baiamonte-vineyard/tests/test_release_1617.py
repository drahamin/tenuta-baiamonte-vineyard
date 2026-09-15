from pathlib import Path
from tests.source_helpers import backend_source


ROOT = Path(__file__).resolve().parents[1]


def test_laboratory_selector_explains_series_identity():
    javascript = (ROOT / "app/static/assets/lab-outlook.js").read_text()
    assert "row.sample_type||'other'" in javascript
    assert "row.stage?' / '" in javascript
    assert "row.analyte_name||row.analyte_code" in javascript


def test_release_version_is_consistent():
    assert 'version: "1.9.4"' in (ROOT / "config.yaml").read_text()
    assert 'version="1.9.4"' in (ROOT / "app/main.py").read_text()


def test_yan_candidates_show_values_and_shared_must_can_link_to_multiple_lots():
    catalog = (ROOT / "app/domains/laffort_catalog.py").read_text()
    frontend = (ROOT / "app/static/assets/enology-process.js").read_text()
    migration = (ROOT / "db/migrations/160_multi_lot_lab_sample_links.sql").read_text()
    assert "linked_wine_lot_ids" in catalog
    assert '"metrics": {}' in catalog
    assert "YAN/APA ${fmt(candidateYan.metric.value)}" in frontend
    assert "data-link-lab-sample" in frontend
    assert "CREATE TABLE IF NOT EXISTS lab_sample_wine_lots" in migration
    assert "GRC-2026-01-P','GRC-2026-01-T" in migration


def test_trusted_email_and_whatsapp_lab_reports_ingest_without_approval_click():
    intelligence = (ROOT / "app/intelligence.py").read_text()
    intake = (ROOT / "app/domains/alerts_intake_routes.py").read_text()
    assert 'source == "whatsapp" or sender in _trusted_gmail_senders(settings)' in intelligence
    assert "automatic_lab_ingest = auto_ingest_complete_lab_report(record_id)" in intelligence
    assert "def auto_ingest_complete_lab_report" in intake
    assert "Complete trusted laboratory report ingested automatically" in intake
    assert "auto_ingest_report" in intake


def test_owner_nerello_plan_and_sparse_lab_weighting_are_protected():
    migration = (ROOT / "db/migrations/159_nerello_september_23_working_plan.sql").read_text()
    learning = (ROOT / "app/harvest_learning.py").read_text()
    assert "'2026-09-23'" in migration
    assert "owner working harvest plan" in migration
    assert '{"low": 0.2, "medium": 0.5, "high": 0.7}' in learning
    dashboard = (ROOT / "app/domains/dashboard_routes.py").read_text()
    assert 'row["planned_pick_date"] = preferred_plan.get("planned_pick_date")' in dashboard


def test_finance_intake_and_duplicate_harvest_crews_are_removed_from_labor():
    backend = (ROOT / "app/main.py").read_text()
    migration = (ROOT / "db/migrations/157_finance_intake_and_harvest_crew_deduplication.sql").read_text()
    assert "LOWER(COALESCE(source,'')) NOT IN ('fattureincloud','fatture_in_cloud')" in backend
    assert "COALESCE(l.regular_hours,0)+COALESCE(l.overtime_hours,0)>0" in backend
    assert "merge_duplicate" in migration


def test_mustalone_has_dedicated_cellar_artwork():
    application = (ROOT / "app/static/app.js").read_text()
    cellar = (ROOT / "app/static/assets/cellar.js").read_text()
    styles = (ROOT / "app/static/app.css").read_text()
    assert "if(/mustalone/.test(value))return'mustalone'" in application
    assert "tank.name||''" in application
    assert "row.name||''" in cellar
    assert ".tank-gauge.vessel-mustalone" in styles
    assert ".tank-type-icon.mustalone" in styles


def test_application_starts_only_after_feature_renderers_are_registered():
    application = (ROOT / "app/static/app.js").read_text()
    bootstrap = (ROOT / "app/static/bootstrap.js").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    assert "setupYears();loadAll();" not in application
    assert "if (typeof setupYears === 'function') setupYears();" in bootstrap
    assert "if (typeof loadInitial === 'function') void loadInitial();" in bootstrap
    assert html.rfind('src="assets/bootstrap.js') > html.rfind('src="assets/assets/fertilization.js')


def test_embedded_weather_cleanup_observer_has_a_document_root_guard():
    backend = backend_source(ROOT)
    assert "const root=document.body||document.documentElement;if(root)new MutationObserver" in backend


def test_laboratory_defaults_to_comparable_series_and_uses_matching_endpoints():
    outlook = (ROOT / "app/static/assets/lab-outlook.js").read_text()
    dashboard = (ROOT / "app/static/app.js").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    assert 'Comparable history available' in outlook
    assert "sampleKey=row=>" in outlook
    assert "matching=ordered.filter" in outlook
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
    assert 'id="labOutlookSample"' in html
    assert 'id="labAiProjection"' in html
    assert 'id="labFindingHeadline"' in html
    assert "current_trajectory_14_day" in (ROOT / "app/domains/laboratory.py").read_text()
    assert "labAutoRefreshBusy" in outlook
    assert "60000" in outlook


def test_enologist_approval_saves_and_clears_source_review_state():
    backend = backend_source(ROOT)
    frontend = (ROOT / "app/static/app.js").read_text()
    assert "UPDATE lab_samples SET needs_review=0" in backend
    assert "if is_approval:" in backend
    assert "Saving approval…" in frontend
    assert "form.requestSubmit()" in frontend


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
