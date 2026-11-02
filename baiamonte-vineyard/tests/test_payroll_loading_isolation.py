from unittest.mock import Mock

from starlette.requests import Request

from app import main, intelligence
from app.domains.admin_routes import admin_payroll
from app.access import authorize_admin


def test_payroll_route_is_admin_only():
    route = next(route for route in main.app.routes if getattr(route, "path", "") == "/api/v1/admin/payroll")
    assert route.methods == {"GET"}
    assert route.dependencies[0].dependency is authorize_admin


def test_payroll_reads_ledger_without_live_services_or_runtime(monkeypatch):
    for name in (
        "admin_control_foundation", "home_assistant_people", "home_assistant_state_map",
        "home_assistant_local_only_user_ids", "home_assistant_manager_camera_catalog",
        "ai_cost_summary", "ai_service_summary", "operational_data_quality",
    ):
        monkeypatch.setattr(main, name, Mock(side_effect=AssertionError(f"Unexpected dependency: {name}")))
    monkeypatch.setattr(main, "fetch_all", lambda *args: [])
    monkeypatch.setattr(main, "fetch_one", lambda *args: {})
    monkeypatch.setattr(main, "estate_id", lambda: "estate")
    monkeypatch.setattr(main, "retired_labor_workers", lambda: {})
    monkeypatch.setattr(main, "people_profiles", lambda: {})
    monkeypatch.setattr(main, "_labor_identity_links", lambda: {})
    monkeypatch.setattr(main, "_labor_card_payment_totals", lambda *args: {})
    monkeypatch.setattr(main, "_attach_labor_invoice_payments", lambda *args: None)
    monkeypatch.setattr(main, "_labor_payment_integrity", lambda *args: {"paid_ledger_mismatches": 0})
    expected = {"ready_to_pay": 430, "payments_recorded": 1700, "outstanding_exposure_eur": 430}
    monkeypatch.setattr(main, "_payroll_summary", lambda *args: expected)
    monkeypatch.setattr(main, "cached_home_assistant_directory", lambda: {"states": {}, "local_only_user_ids": set()})
    result = admin_payroll(Request({"type": "http", "headers": []}))
    assert result["payroll"] == expected
    assert result["payment_integrity"]["paid_ledger_mismatches"] == 0
    assert result["scope"] == "payroll"
    assert result["labor_reconciliation"]
    assert all(person["current_status"] == "uncertain" for person in result["labor_reconciliation"])
    assert "people_directory" not in result


def test_cached_directory_never_waits_for_live_refresh(monkeypatch):
    monkeypatch.setattr(intelligence.time, "monotonic", lambda: 1000)
    monkeypatch.setattr(intelligence, "_ha_states_cache", (990, [{"entity_id": "person.giancarlo", "state": "home"}]))
    monkeypatch.setattr(intelligence, "_ha_users_cache", (990, [{"id": "service", "local_only": True}]))
    monkeypatch.setattr(intelligence, "_ha_get", Mock(side_effect=AssertionError("live HA called")))
    result = intelligence.cached_home_assistant_directory()
    assert result["states"]["person.giancarlo"]["state"] == "home"
    assert result["local_only_user_ids"] == {"service"}
    monkeypatch.setattr(intelligence, "_ha_states_cache", (800, [{"entity_id": "person.giancarlo", "state": "home"}]))
    assert intelligence.cached_home_assistant_directory()["states"] == {}
