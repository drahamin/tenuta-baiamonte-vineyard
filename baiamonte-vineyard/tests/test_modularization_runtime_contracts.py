from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access import authorize_admin
from app.domains import attachments, intelligence_routes, payroll, payroll_admin_routes
from app.domains.payroll_presence import PresenceValidationError, timesheet_presence
from app.main import app


EXPECTED_EXTRACTED_ROUTES = {
    "alerts_intake_routes": {
        "POST /api/v1/attachments/{entity_type}/{entity_id}", "GET /api/v1/attachments/{attachment_id}/file",
        "GET /api/v1/attachments/{attachment_id}/preview",
        "GET /api/v1/alerts", "PATCH /api/v1/alerts/{alert_id}", "GET /api/v1/alert-settings",
        "PUT /api/v1/alert-settings/cellar-thresholds", "PUT /api/v1/alert-settings/{alert_type}",
        "GET /api/v1/intake", "GET /api/v1/processing-log", "POST /api/v1/intake/gmail/check",
        "GET /api/v1/intake/{record_id}", "GET /api/v1/intake/{record_id}/file", "GET /api/v1/intake/{record_id}/preview",
        "POST /api/v1/intake/{record_id}/link", "POST /api/v1/intake/upload", "POST /api/v1/intake/mac",
        "POST /api/v1/intake/{record_id}/analyze", "PATCH /api/v1/intake/{record_id}/review",
        "POST /api/v1/intake/{record_id}/approve-lab-report",
        "POST /api/v1/intake/{record_id}/source-file",
        "POST /api/v1/intake/flush-completed", "POST /api/v1/intake/clear-routine-whatsapp",
    },
    "cellar_routes": {
        "GET /api/v1/cellar/dashboard", "POST /api/v1/agronomy/tanks",
        "PUT /api/v1/agronomy/tanks/{container_id}/legal-label", "POST /api/v1/agronomy/label-kiosks",
        "PUT /api/v1/agronomy/label-kiosks/{kiosk_id}", "GET /api/v1/agronomy/label-kiosks/{kiosk_id}/qr",
        "DELETE /api/v1/agronomy/label-kiosks/{kiosk_id}",
        "POST /api/v1/agronomy/label-enrollments/{enrollment_id}/approve",
        "DELETE /api/v1/agronomy/label-enrollments/{enrollment_id}",
        "POST /api/v1/agronomy/label-enrollments/{enrollment_id}/reprovision",
        "POST /api/v1/agronomy/tanks/{container_id}/lot-transfer",
        "PUT /api/v1/agronomy/tanks/{container_id}/mode", "POST /api/v1/agronomy/tanks/{container_id}/reading",
        "POST /api/v1/agronomy/tanks/{container_id}/empty",
        "DELETE /api/v1/agronomy/tanks/{container_id}", "POST /api/v1/agronomy/tanks/{container_id}/maintenance",
    },
    "dashboard_routes": {
        "GET /api/v1/dashboard", "GET /api/display-data", "GET /api/v1/grapes/dashboard",
        "GET /api/v1/history/overview",
    },
    "intelligence_routes": {
        "GET /api/v1/admin/ai", "POST /api/v1/admin/ai/rebuild-learning",
        "PUT /api/v1/admin/ai-cost", "PUT /api/v1/admin/ai-profile",
        "PUT /api/v1/admin/camera-ai-policy", "POST /api/v1/admin/camera-ai-policy/check",
        "POST /api/v1/admin/ai-credit-check", "POST /api/v1/assistant/ask",
        "POST /api/v1/assistant/suggestion",
    },
    "payroll_admin_routes": {
        "POST /api/v1/admin/worker-labor/{record_id}/review",
        "POST /api/v1/admin/worker-labor/{record_id}/pay", "POST /api/v1/admin/labor-payment-batches/pay",
        "POST /api/v1/admin/worker-labor/{record_id}/presence", "PATCH /api/v1/admin/labor/{record_id}",
        "DELETE /api/v1/admin/labor/{record_id}", "POST /api/v1/admin/labor/reassign-worker",
        "PUT /api/v1/admin/labor-identities/{worker_key}/home-assistant-person",
        "POST /api/v1/admin/labor/monthly", "PATCH /api/v1/admin/timesheets/{record_id}",
        "POST /api/v1/admin/timesheets/{record_id}/presence",
        "POST /api/v1/admin/timesheets/{record_id}/approve",
    },
    "public_routes": {
        "GET /public/v1/harvest.json", "GET /public/v1/harvest.ics", "GET /weather-map/{path:path}",
        "GET /", "GET /crew", "GET /display",
    },
    "worker_portal_routes": {
        "GET /api/v1/worker-portal", "POST /api/v1/worker-portal/clock-in",
        "POST /api/v1/worker-portal/clock-out", "POST /api/v1/worker-portal/charge",
        "POST /api/v1/worker-portal/work-items", "POST /api/v1/worker-portal/water-delivery-claims",
        "PATCH /api/v1/worker-portal/entries/{record_id}",
        "POST /api/v1/worker-portal/entries/{record_id}/photo",
    },
}


def test_extracted_routes_are_registered_once_with_the_expected_contracts():
    actual = {module: set() for module in EXPECTED_EXTRACTED_ROUTES}
    registered = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        methods = sorted(getattr(route, "methods", set()))
        for method in methods:
            registered.append((method, route.path))
        module = endpoint.__module__.rsplit(".", 1)[-1]
        if module in actual:
            actual[module].update(f"{method} {route.path}" for method in methods)
    assert actual == EXPECTED_EXTRACTED_ROUTES
    assert len(registered) == len(set(registered))


def test_extracted_nonpublic_routes_retain_authorization_dependencies():
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        module = endpoint.__module__.rsplit(".", 1)[-1]
        if module not in EXPECTED_EXTRACTED_ROUTES or module == "public_routes":
            continue
        dependencies = {getattr(item.dependency, "__name__", "") for item in route.dependencies}
        assert dependencies & {"authorize", "authorize_write", "authorize_admin", "authorize_worker"}, route.path


def test_payroll_presence_uses_domain_validation_errors():
    with pytest.raises(PresenceValidationError, match="one employee at a time"):
        timesheet_presence("Worker A", [{"worker": "Worker B", "work_date": "2026-08-23"}])


def test_payroll_route_translates_domain_state_errors(monkeypatch):
    def fail_review(*_args, **_kwargs):
        raise payroll.PayrollDomainError("Already locked", 409)

    monkeypatch.setattr(payroll_admin_routes, "review_worker_labor_record", fail_review)
    test_app = FastAPI()
    test_app.include_router(payroll_admin_routes.router)
    test_app.dependency_overrides[authorize_admin] = lambda: None
    response = TestClient(test_app).post(
        "/api/v1/admin/worker-labor/record-1/review",
        json={"decision": "approve"},
        headers={"X-Remote-User-Name": "reviewer"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Already locked"}


def test_intelligence_assistant_route_preserves_normalization(monkeypatch):
    calls = []

    def fake_assistant(question, language, focus):
        calls.append((question, language, focus))
        return {"answer": "Pronto"}

    monkeypatch.setattr(intelligence_routes, "ask_assistant", fake_assistant)
    test_app = FastAPI()
    test_app.include_router(intelligence_routes.router)
    test_app.dependency_overrides[intelligence_routes.authorize_write] = lambda: None
    response = TestClient(test_app).post(
        "/api/v1/assistant/ask",
        json={"question": "  Cosa facciamo?  ", "language": "Italiano", "focus": "unknown"},
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "Pronto"}
    assert calls == [("Cosa facciamo?", "it", "vineyard")]


def test_intelligence_cost_route_preserves_validation_error():
    test_app = FastAPI()
    test_app.include_router(intelligence_routes.router)
    test_app.dependency_overrides[intelligence_routes.authorize_admin] = lambda: None
    response = TestClient(test_app).put(
        "/api/v1/admin/ai-cost",
        json={"monthly_budget_usd": "not-a-number", "warning_percent": 80},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Enter a valid monthly budget and warning percentage"}


def test_worker_review_service_owns_calculation_and_transaction(monkeypatch):
    row = {
        "id": "record-1", "approval_status": "submitted", "hourly_rate_eur": 10,
        "regular_hours": 4, "overtime_hours": 1, "pay_due_date": None, "payment_status": "verification_needed",
    }
    executed = []

    class Cursor:
        def execute(self, sql, params):
            executed.append((sql, params))

    @contextmanager
    def fake_transaction():
        yield None, Cursor()

    monkeypatch.setattr(payroll, "fetch_one", lambda *_args, **_kwargs: row)
    monkeypatch.setattr(payroll, "transaction", fake_transaction)
    monkeypatch.setattr(payroll, "audit", lambda *_args, **_kwargs: None)
    result = payroll.review_worker_labor_record(
        "record-1", {"decision": "approve", "hourly_rate_eur": 12}, "reviewer", "estate-1"
    )
    assert result["approval_status"] == "approved"
    assert result["labor_cost_eur"] == 60
    assert result["payment_status"] == "unpaid"
    assert len(executed) == 1


def test_shared_attachment_storage_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, "ATTACHMENT_ROOT", tmp_path)
    stored = attachments.store_attachment(b"photo-data", "attachment-1", "bad name.jpg", "photo")
    assert stored.filename == "bad_name.jpg"
    assert stored.path.read_bytes() == b"photo-data"
    assert len(stored.sha256) == 64
    stored.discard()
    assert not stored.path.exists()
