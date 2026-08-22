from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import cellar_demo
from app.domains.hospitality_inbox import hospitality_message_matches


def test_clear_guest_tasting_inquiry_routes_without_exact_saved_phrase():
    settings = {"inbound_subjects": ["Inquiry about Reserve Tasting"], "inbound_labels": ["Hospitality"]}
    assert hospitality_message_matches("Inquiry about Classic Tasting at the Estate", [], settings)
    assert hospitality_message_matches("Availability request", [], settings, "Can we book a vineyard tour?")
    assert not hospitality_message_matches("Supplier inquiry", [], settings, "Please review our tractor catalog")


def test_empty_tanks_do_not_emit_cellar_guard_alerts(monkeypatch):
    monkeypatch.setattr(cellar_demo, "fetch_all", lambda *_args, **_kwargs: [])
    settings = SimpleNamespace(
        cellar_temp_min_c=8, cellar_temp_max_c=30,
        cellar_level_min_pct=5, cellar_level_max_pct=98,
        cellar_ph_min=2.8, cellar_ph_max=4.2,
        cellar_density_min_sg=0.98, cellar_density_max_sg=1.2,
    )
    empty = {"id": "empty", "volume_l": 0, "level_pct": 0, "temp_c": 40, "ph": 5, "sensor_issues": ["sensor.tank"]}
    occupied = {"id": "occupied", "volume_l": 100, "level_pct": 2, "temp_c": 20}
    alerts = cellar_demo.evaluate_cellar_tanks([empty, occupied], settings)
    assert empty["guard_state"] == "empty"
    assert empty["guard_messages"] == []
    assert empty["guard_suppressed"] == "empty_tank"
    assert [row["tank_id"] for row in alerts] == ["occupied"]


def test_finance_summary_cards_open_source_backed_details():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/finance-details.js").read_text()
    backend = (ROOT / "app/domains/finance.py").read_text()
    for detail in ("revenue", "cost", "result", "cash", "labor-cost", "labor-paid", "labor-due"):
        assert f'data-finance-detail="{detail}"' in html
    assert "openFinanceMetricDetails" in javascript
    assert "labor_records" in backend
    assert "balance_due_eur" in backend


def test_year_switch_restores_the_workspace_module_before_the_page():
    javascript = (ROOT / "app/static/app.js").read_text()
    setup = javascript.split("function setupYears()", 1)[1].split("let workerTimer", 1)[0]
    assert "setNavMode(moduleForView(activeView))" in setup
    assert "activeButton" in setup


def test_paypal_protected_options_reach_the_register_api_process():
    entrypoint = (ROOT / "entrypoint.py").read_text()
    for option, environment in {
        "paypal_client_id": "PAYPAL_CLIENT_ID",
        "paypal_client_secret": "PAYPAL_CLIENT_SECRET",
        "paypal_it_client_id": "PAYPAL_IT_CLIENT_ID",
        "paypal_it_client_secret": "PAYPAL_IT_CLIENT_SECRET",
        "paypal_environment": "PAYPAL_ENVIRONMENT",
        "paypal_us_environment": "PAYPAL_US_ENVIRONMENT",
        "paypal_it_environment": "PAYPAL_IT_ENVIRONMENT",
    }.items():
        assert f'"{option}": "{environment}"' in entrypoint
    assert ".paypal_account_environments_migrated" in entrypoint
    assert 'cleaned["paypal_us_environment"] = legacy_paypal_environment' in entrypoint
    assert 'cleaned["paypal_it_environment"] = legacy_paypal_environment' in entrypoint


def test_deleted_guest_inquiry_is_tombstoned_and_not_routed_again():
    inbox = (ROOT / "app/domains/hospitality_inbox.py").read_text()
    migration = (ROOT / "db/migrations/114_hospitality_inquiry_tombstones.sql").read_text()
    assert "status='deleted'" in inbox
    assert "h.status<>'deleted'" in inbox
    assert "'deleted'" in migration
    assert "LEFT JOIN hospitality_inquiries h" in inbox
