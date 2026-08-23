from pathlib import Path
from tests.source_helpers import backend_source


ROOT = Path(__file__).resolve().parents[1]


def test_history_api_includes_baiamonte_expenses():
    source = backend_source(ROOT)
    index = (ROOT / "app" / "static" / "index.html").read_text()
    assert 'queries["historical_costs"] = "SELECT record_year year' in source
    assert "/api/v1/admin/import-workbooks" not in source
    assert "workbookImportForm" not in index


def test_existing_legacy_dates_and_hours_are_backfilled_by_migrations():
    dates = (ROOT / "db" / "migrations" / "042_repair_legacy_work_dates.sql").read_text()
    hours = (ROOT / "db" / "migrations" / "043_historical_labor_hours.sql").read_text()
    assert "STR_TO_DATE(raw_date,'%d/%m/%y')" in dates
    assert "ADD COLUMN IF NOT EXISTS labor_hours" in hours


def test_proclama_payroll_adds_labor_without_duplicating_costs_or_payment_claims():
    migration = (ROOT / "db" / "migrations" / "049_giancarlo_proclama_labor.sql").read_text()
    assert "Proclama payroll archive" in migration
    assert "0,45.50,'payment_not_verified',0" in migration
    assert "0,123.50,'payment_not_verified',0" in migration
    assert "'2025-11-30',2025,'month'" in migration
    assert "15 worked days, hours not stated" in migration
    assert "0,NULL,'payment_not_verified',0" in migration
    assert migration.count(";") == 1


def test_production_image_cannot_parse_retired_workbooks():
    dockerfile = (ROOT / "Dockerfile").read_text()
    requirements = (ROOT / "requirements.txt").read_text().lower()
    assert "COPY scripts scripts" not in dockerfile
    assert "import_legacy_costs.py" not in dockerfile
    assert "import_vineyard_history.py" not in dockerfile
    assert "openpyxl" not in requirements
