"""Tasks validator fixtures only: no production settings, rows or network."""
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace
import threading

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
import pytest

from app.domains import mobile_work_review_tasks_validation as validation
from app.domains.mobile_work_review_projection import SnapshotChanged, SourceUnavailable
from app.remote_erp import reporting_row_revision
from test_mobile_work_review_source import ESTATE, NOW, FakeConnection, fixture_column_contract, row


SETTINGS = SimpleNamespace(estate_id=ESTATE, db_host="core-mariadb", db_port=3306, db_name="baiamonte_vineyard",
                           db_user="synthetic", db_password="synthetic-never-output", trust_home_assistant_ingress=True)
PRINCIPAL = hashlib.sha256(b"synthetic-owner").hexdigest()


def window(connection):
    return {"issued_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reporting_columns_sha256": fixture_column_contract(connection)["tasks"]}


def fixture(monkeypatch, first=None, second=None):
    first = first or FakeConnection([row("synthetic-a", title="synthetic-title-canary", notes="synthetic-private-note"), row("synthetic-b")])
    second = second or FakeConnection(first.rows)
    pending = iter([first, second]); connects = []
    def factory(_settings, boundary):
        assert boundary.estate_id == ESTATE and boundary.db_host == "core-mariadb"
        def connect():
            connects.append(1)
            return next(pending)
        return connect
    monkeypatch.setattr(validation, "make_connection_factory", factory)
    return first, second, connects


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(validation, "_used", False)
    monkeypatch.setattr(validation, "_lock", threading.Lock())


def browser(monkeypatch, approved):
    monkeypatch.setattr(validation, "require_validation_admin", lambda _request: None)
    monkeypatch.setattr(validation, "runtime_option", lambda _name, _fallback: approved)
    monkeypatch.setattr(validation, "utc_now", lambda: NOW)
    monkeypatch.setattr(validation, "get_settings", lambda: SETTINGS)
    app = FastAPI(); app.include_router(validation.router)
    return TestClient(app)


def test_two_real_synthetic_adapter_captures_reference_every_row_and_return_only_aggregates(monkeypatch):
    first, second, connects = fixture(monkeypatch)
    checked = []
    def reference(data):
        assert "notes" in data and "owner_id" in data and "password" not in data and "cost_eur" not in data
        with pytest.raises(TypeError): data["notes"] = "mutation"
        checked.append(1)
        return reporting_row_revision(data)
    monkeypatch.setattr(validation, "authoritative_reporting_token", reference)
    result = validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=lambda: NOW)
    assert result["ok"] and result["captures_completed"] == len(connects) == 2
    assert result["row_counts"] == [2, 2] and result["reference_tokens_checked"] == len(checked) == 4
    assert result["reference_tokens_match"] and result["pagination_verified"] and result["generation_stable"]
    assert result["source_state"] == "degraded" and not result["source_payload_returned"]
    encoded = json.dumps(result)
    for forbidden in ("synthetic-a", "synthetic-b", "synthetic-title-canary", "synthetic-private-note", "synthetic-never-output", ESTATE, PRINCIPAL, "next_cursor", '"items"', '"revision"', '"generation"'):
        assert forbidden not in encoded
    for connection in (first, second):
        assert connection.rolled_back and connection.closed
        for sql, args in connection.statements:
            if "FROM `" in sql:
                assert "FROM `tasks`" in sql and args == (ESTATE,)


@pytest.mark.parametrize("count", [0, 1])
def test_small_sources_explicitly_do_not_claim_pagination_or_empty_token_evidence(monkeypatch, count):
    first, _, connects = fixture(monkeypatch, FakeConnection([row()] * count))
    result = validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=lambda: NOW)
    assert len(connects) == 2 and not result["pagination_verified"]
    assert result["evidence_status"] == "partial_insufficient_rows"
    assert result["reference_tokens_match"] is (True if count else None)


def test_reference_mismatch_fails_and_never_starts_second_capture(monkeypatch):
    first, second, connects = fixture(monkeypatch)
    monkeypatch.setattr(validation, "authoritative_reporting_token", lambda _data: -1)
    with pytest.raises(SourceUnavailable): validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=lambda: NOW)
    assert len(connects) == 1 and first.closed and first.rolled_back and not second.statements


def test_source_change_is_conflict_without_third_capture(monkeypatch):
    first = FakeConnection([row("a", notes="before"), row("b")])
    second = FakeConnection([row("a", notes="after"), row("b")])
    first, _, connects = fixture(monkeypatch, first, second)
    with pytest.raises(SnapshotChanged): validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=lambda: NOW)
    assert len(connects) == 2 and first.closed and second.closed


def test_expiry_between_captures_does_not_start_second(monkeypatch):
    first, second, connects = fixture(monkeypatch)
    clock = lambda: NOW + timedelta(minutes=11) if first.closed else NOW
    with pytest.raises(validation.ValidationWindowClosed): validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=clock)
    assert len(connects) == 1 and not second.statements


def test_request_budget_stops_before_first_capture(monkeypatch):
    first, _, connects = fixture(monkeypatch)
    monkeypatch.setattr(validation, "TOTAL_SECONDS", 0)
    with pytest.raises(SourceUnavailable): validation.collect_tasks_validation(SETTINGS, window(first), PRINCIPAL, clock=lambda: NOW)
    assert not connects


@pytest.mark.parametrize("changes", [{"reporting_columns_sha256": ""}, {"reporting_columns_sha256": "x" * 64}, {"extra": "bad"}, {"expires_at": "2026-11-03T12:10:01Z"}, {"issued_at": "2026-11-03T12:00:00+00:00"}])
def test_window_requires_distinct_exact_literal_utc_and_reviewed_hash(changes):
    assert not validation.active_window({**window(FakeConnection()), **changes}, NOW)


def test_blank_default_or_either_old_window_does_not_authorize(monkeypatch):
    monkeypatch.setattr(validation, "runtime_option", lambda name, fallback: None if name == validation.WINDOW_OPTION else window(FakeConnection()))
    monkeypatch.setattr(validation, "get_settings", lambda: pytest.fail("settings lookup"))
    app = FastAPI(); app.include_router(validation.router)
    response = TestClient(app).get(validation.PATH)
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store" and not validation._used


def test_http_success_consumed_once(monkeypatch):
    approved = window(FakeConnection())
    monkeypatch.setattr(validation, "collect_tasks_validation", lambda *_args: {"ok": True, "contract": validation.CONTRACT})
    with browser(monkeypatch, approved) as client:
        response = client.get(validation.PATH, headers={"X-Remote-User-Id": "synthetic-owner-id"})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert client.get(validation.PATH).status_code == 410


def test_http_complete_synthetic_pipeline_returns_no_record_payload(monkeypatch):
    first, _, connects = fixture(monkeypatch)
    original = validation.collect_tasks_validation
    monkeypatch.setattr(validation, "collect_tasks_validation", lambda *args: original(*args, clock=lambda: NOW))
    with browser(monkeypatch, window(first)) as client:
        response = client.get(validation.PATH, headers={"X-Remote-User-Id": "synthetic-owner-id"})
        assert response.status_code == 200 and response.json()["row_counts"] == [2, 2]
        assert "synthetic-private-note" not in response.text and "synthetic-title-canary" not in response.text
        assert len(connects) == 2 and client.get(validation.PATH).status_code == 410


def test_http_failure_consumed_once_and_error_redaction(monkeypatch):
    approved = window(FakeConnection())
    def fail(*_args): raise RuntimeError("synthetic-private-note SQL credential")
    monkeypatch.setattr(validation, "collect_tasks_validation", fail)
    with browser(monkeypatch, approved) as client:
        response = client.get(validation.PATH, headers={"X-Remote-User-Id": "synthetic-owner-id"})
        assert response.status_code == 503 and "synthetic-private-note" not in response.text
        assert client.get(validation.PATH).status_code == 410


def test_http_conflict_is_409_and_consumed_without_retry(monkeypatch):
    def conflict(*_args): raise SnapshotChanged()
    monkeypatch.setattr(validation, "collect_tasks_validation", conflict)
    with browser(monkeypatch, window(FakeConnection())) as client:
        response = client.get(validation.PATH, headers={"X-Remote-User-Id": "synthetic-owner-id"})
        assert response.status_code == 409 and response.json()["error"] == "mobile_read_snapshot_changed"
        assert client.get(validation.PATH).status_code == 410


@pytest.mark.parametrize("method,kwargs,expected", [("GET", {"params": {"dataset": "tasks"}}, 422), ("GET", {"content": "x"}, 422), ("GET", {"headers": {"Transfer-Encoding": "chunked"}}, 422), ("POST", {}, 405), ("HEAD", {}, 405)])
def test_no_input_or_other_methods_and_no_store(monkeypatch, method, kwargs, expected):
    monkeypatch.setattr(validation, "collect_tasks_validation", lambda *_args: pytest.fail("collection"))
    response = browser(monkeypatch, window(FakeConnection())).request(method, validation.PATH, **kwargs)
    assert response.status_code == expected and response.headers["cache-control"] == "no-store" and not validation._used


def test_busy_does_not_collect_or_consume_an_attempt(monkeypatch):
    validation._lock.acquire()
    try:
        response = browser(monkeypatch, window(FakeConnection())).get(validation.PATH)
        assert response.status_code == 429 and not validation._used and response.headers["retry-after"] == "60"
    finally: validation._lock.release()


def test_active_window_requires_trusted_ingress_identity_and_existing_admin_no_api_key_fallback(monkeypatch):
    monkeypatch.setattr(validation, "runtime_option", lambda _name, _fallback: window(FakeConnection()))
    monkeypatch.setattr(validation, "utc_now", lambda: NOW)
    monkeypatch.setattr(validation, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(validation, "trusted_ingress_request", lambda _request: False)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"synthetic"), (b"authorization", b"Bearer synthetic")], "method": "GET", "path": validation.PATH})
    with pytest.raises(HTTPException) as caught: validation.require_validation_admin(request)
    assert caught.value.status_code == 401 and not validation._used
    monkeypatch.setattr(validation, "trusted_ingress_request", lambda _request: True)
    request = Request({"type": "http", "headers": [(b"x-ingress-path", b"/api/hassio_ingress/synthetic/"), (b"x-remote-user-id", b"synthetic-owner-id")], "method": "GET", "path": validation.PATH})
    seen = []
    def deny(_request, **kwargs):
        seen.append(kwargs["x_api_key"])
        raise HTTPException(403, "synthetic Admin denied")
    monkeypatch.setattr(validation, "authorize_admin", deny)
    with pytest.raises(HTTPException) as caught: validation.require_validation_admin(request)
    assert caught.value.status_code == 403 and caught.value.headers["Cache-Control"] == "no-store"
    assert seen == [None] and not validation._used
