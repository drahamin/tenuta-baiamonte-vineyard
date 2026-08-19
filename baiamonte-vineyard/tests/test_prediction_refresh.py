from datetime import date
from pathlib import Path

from app.harvest_learning import summarize_lab_series


ROOT = Path(__file__).resolve().parents[1]


def test_lab_statistics_are_fresh_bounded_and_trended() -> None:
    summary = summarize_lab_series(
        [
            {"lab_date": "2026-08-12", "analyte_code": "brix", "analyte_name": "Brix", "numeric_value": 18.0, "unit": "°Bx"},
            {"lab_date": "2026-08-18", "analyte_code": "brix", "analyte_name": "Brix", "numeric_value": 19.2, "unit": "°Bx"},
            {"lab_date": "2026-07-01", "analyte_code": "ta", "analyte_name": "TA", "numeric_value": 10.0, "unit": "g/L"},
        ],
        date(2026, 8, 19),
    )
    assert summary["usable"] is True
    assert set(summary["analytes"]) == {"brix"}
    assert summary["analytes"]["brix"]["age_days"] == 1
    assert summary["analytes"]["brix"]["change_per_day"] == 0.2


def test_prediction_writes_queue_refresh_and_workbook_runtime_is_retired() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    mcp = (ROOT / "app/mcp_server.py").read_text(encoding="utf-8")
    intelligence = (ROOT / "app/intelligence.py").read_text(encoding="utf-8")
    index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert 'payload.sample_type == "grape" and not payload.variety_id' in main
    assert 'request_harvest_refresh("lab_sample"' in main
    assert "harvest_refresh_pending()" in intelligence
    assert '"lab_statistics": lab_statistics' in intelligence
    assert '"workbook_runtime_dependency": False' in intelligence
    assert "A grape laboratory sample requires variety_name" in mcp
    assert "/api/v1/admin/import-workbooks" not in main
    assert "workbookImportForm" not in index
