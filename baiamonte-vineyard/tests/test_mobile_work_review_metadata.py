"""Synthetic metadata only; no production settings, rows or connections."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import threading

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app.domains import mobile_work_review_metadata as metadata


NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
SETTINGS = SimpleNamespace(db_host="core-mariadb", db_port=3306, db_name="baiamonte_vineyard", db_user="synthetic", db_password="synthetic-do-not-print", trust_home_assistant_ingress=True)
DEFINITION = "select synthetic_id from synthetic_source where synthetic_predicate = 1"


class Connection:
    def __init__(self, *, fail=None, overflow=False, denied=False, wrong_database=False, wrong_object=False, cleanup_fail=False):
        self.calls = []; self.rolled_back = False; self.closed = False
        self.fail, self.overflow, self.denied = fail, overflow, denied
        self.wrong_database, self.wrong_object, self.cleanup_fail = wrong_database, wrong_object, cleanup_fail
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=None):
        self.calls.append((sql, params)); self.sql = sql
        if self.fail and self.fail in sql: raise RuntimeError("synthetic-do-not-print SQL private parameter")
    def fetchone(self):
        return {"database_name": "wrong" if self.wrong_database else "baiamonte_vineyard", "session_time_zone": "SYSTEM",
                "global_time_zone": "SYSTEM", "system_time_zone": "UTC", "database_utc_now": NOW.replace(tzinfo=None)}
    def fetchall(self):
        if "information_schema.columns" in self.sql:
            rows = [{"table_name": name, "column_name": column, "data_type": "enum" if column == "status" else "varchar",
                     "enum_declaration": "enum('planned','closed')" if column == "status" else None,
                     "is_nullable": "NO", "table_type": "VIEW" if name in metadata.VIEWS else "BASE TABLE",
                     "engine": None if name in metadata.VIEWS else "InnoDB", "character_maximum_length": 36,
                     "numeric_precision": None, "numeric_scale": None, "datetime_precision": None}
                    for name in metadata.OBJECTS for column in ("estate_id", "id", "status", "password", "cost_eur")]
            if self.wrong_object: rows[0]["table_name"] = "excluded_source"
            return rows * 9 if self.overflow else rows
        if "information_schema.views" in self.sql:
            return [{"object_name": name, "definition_bytes": None if self.denied else len(DEFINITION.encode()),
                     "view_definition": None if self.denied else DEFINITION, "check_option": "NONE", "security_type": "DEFINER"}
                    for name in metadata.VIEWS]
        pytest.fail("unexpected metadata SQL")
    def rollback(self):
        self.rolled_back = True
        if self.cleanup_fail: raise RuntimeError("synthetic-do-not-print rollback")
    def close(self): self.closed = True
    def commit(self): pytest.fail("metadata collector committed")


def collect(connection=None, **kwargs):
    connection = connection or Connection()
    return metadata.collect_metadata(SETTINGS, connection_factory=lambda _settings: connection, **kwargs)


@pytest.fixture(autouse=True)
def reset_attempt(monkeypatch):
    monkeypatch.setattr(metadata, "_used", False)
    monkeypatch.setattr(metadata, "_lock", threading.Lock())


def client(monkeypatch, *, permitted=True):
    if permitted:
        monkeypatch.setattr(metadata, "require_metadata_admin", lambda _request: None)
    monkeypatch.setattr(metadata, "get_settings", lambda: SETTINGS)
    app = FastAPI(); app.include_router(metadata.router)
    return TestClient(app)


def test_exact_three_metadata_selects_no_source_rows_or_underlying_fallback():
    connection = Connection(); result = collect(connection)
    assert result["ok"] and result["source_record_reads"] == 0
    assert connection.rolled_back and connection.closed
    selects = [(sql, params) for sql, params in connection.calls if sql.startswith("SELECT")]
    assert len(selects) == 3
    assert selects[1][1] == metadata.OBJECTS and selects[2][1] == metadata.VIEWS
    assert all("information_schema" in sql or "DATABASE()" in sql for sql, _ in selects)
    assert not any(f"FROM `{name}`" in sql for sql, _ in selects for name in metadata.OBJECTS)
    assert "LIMIT 257" in selects[1][0] and "LIMIT 3" in selects[2][0]
    assert "OCTET_LENGTH(view_definition)<=65536" in selects[2][0]
    assert [sql for sql, _ in connection.calls[:4]] == ["SET SESSION max_statement_time=2", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", "SET TRANSACTION READ ONLY", "START TRANSACTION WITH CONSISTENT SNAPSHOT"]


def test_only_permitted_column_metadata_and_private_view_sql_are_returned():
    result = collect()
    serialized = json.dumps(result)
    assert "password" not in serialized and "cost_eur" not in serialized
    assert "synthetic-do-not-print" not in serialized
    assert set(result["sources"]) == set(metadata.OBJECTS)
    assert set(result["views"]) == set(metadata.VIEWS)
    for name, view in result["views"].items():
        assert view["view_definition"] == DEFINITION and len(view["fingerprint"]) == 64
        assert view["review_status"] == "requires_private_semantic_review"
    assert result["timezone_settings"]["database_utc_now"] == "2026-11-03T12:00:00Z"
    assert "historical_source_timezone" in result["not_verified"]


@pytest.mark.parametrize("fail", ["DATABASE()", "information_schema.columns", "information_schema.views"])
def test_failure_always_rolls_back_and_closes(fail):
    connection = Connection(fail=fail)
    with pytest.raises(RuntimeError): collect(connection)
    assert connection.rolled_back and connection.closed


@pytest.mark.parametrize("kwargs", [{"overflow": True}, {"wrong_object": True}, {"wrong_database": True}])
def test_metadata_overflow_scope_or_actual_database_mismatch_fails_closed(kwargs):
    connection = Connection(**kwargs)
    with pytest.raises(metadata.MetadataFailure): collect(connection)
    assert connection.rolled_back and connection.closed
    if kwargs.get("wrong_database"):
        assert not any("information_schema" in sql for sql, _ in connection.calls)


def test_denied_view_definition_is_unavailable_and_never_falls_back():
    connection = Connection(denied=True); result = collect(connection)
    assert not result["ok"] and all(not view["available"] for view in result["views"].values())
    assert len(connection.calls) == 7


def test_response_and_cooperative_time_budget_fail_before_return(monkeypatch):
    connection = Connection(); monkeypatch.setattr(metadata, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(metadata.MetadataFailure): collect(connection)
    assert connection.closed and connection.rolled_back
    ticks = iter([0, 13]); connection = Connection()
    with pytest.raises(metadata.MetadataFailure): collect(connection, monotonic=lambda: next(ticks))
    assert connection.closed and connection.rolled_back


def test_close_runs_when_rollback_fails():
    connection = Connection(cleanup_fail=True)
    with pytest.raises(RuntimeError): collect(connection)
    assert connection.closed


@pytest.mark.parametrize("changes", [{"db_host": "localhost"}, {"db_port": 3307}, {"db_name": "other"}])
def test_declared_scope_mismatch_never_connects(changes):
    settings = SimpleNamespace(**{**vars(SETTINGS), **changes})
    with pytest.raises(metadata.MetadataFailure):
        metadata.collect_metadata(settings, connection_factory=lambda _settings: pytest.fail("connected"))


def test_connector_uses_existing_scope_and_short_nonpooled_timeouts(monkeypatch):
    observed = {}
    monkeypatch.setattr(metadata.pymysql, "connect", lambda **kwargs: observed.update(kwargs))
    metadata._connection(SETTINGS)
    assert observed["host"] == "core-mariadb" and observed["database"] == "baiamonte_vineyard"
    assert observed["connect_timeout"] == observed["read_timeout"] == observed["write_timeout"] == 3
    assert not observed["autocommit"]


@pytest.mark.parametrize("raw", [None, {}, {"issued_at": "", "expires_at": ""},
    {"issued_at": "2026-11-03T12:00:00+00:00", "expires_at": "2026-11-03T12:10:00+00:00"},
    {"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T12:10:01Z"},
    {"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T12:10:00Z", "extra": True},
    {"issued_at": "2026-02-30T12:00:00Z", "expires_at": "2026-02-30T12:10:00Z"}])
def test_invalid_or_overlong_or_nonliteral_utc_window_denied(raw):
    assert not metadata.active_window(raw, NOW)


def test_exact_ten_minute_window_boundaries():
    raw = {"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T12:10:00Z"}
    assert metadata.active_window(raw, NOW)
    assert not metadata.active_window(raw, NOW - timedelta(seconds=1))
    assert not metadata.active_window(raw, NOW + timedelta(minutes=10))


def test_default_off_route_no_settings_auth_or_connection_lookup(monkeypatch):
    monkeypatch.setattr(metadata, "runtime_option", lambda name, fallback: None)
    monkeypatch.setattr(metadata, "get_settings", lambda: pytest.fail("settings lookup"))
    app = FastAPI(); app.include_router(metadata.router)
    response = TestClient(app).get(metadata.PATH)
    assert response.status_code == 404 and not metadata._used
    assert response.headers["cache-control"] == "no-store"


def test_success_is_one_attempt_and_failure_is_consumed_without_retry(monkeypatch):
    calls = []
    monkeypatch.setattr(metadata, "collect_metadata", lambda _settings: calls.append(1) or {"ok": True})
    with client(monkeypatch) as browser:
        assert browser.get(metadata.PATH).status_code == 200
        assert browser.get(metadata.PATH).status_code == 410
    assert calls == [1]
    metadata._used = False
    def fail(_settings): raise RuntimeError("synthetic-do-not-print SQL")
    monkeypatch.setattr(metadata, "collect_metadata", fail)
    with client(monkeypatch) as browser:
        response = browser.get(metadata.PATH)
        assert response.status_code == 503 and "synthetic-do-not-print" not in response.text
        assert browser.get(metadata.PATH).status_code == 410


def test_concurrent_call_denied_without_collection(monkeypatch):
    monkeypatch.setattr(metadata, "collect_metadata", lambda _settings: pytest.fail("collection"))
    metadata._lock.acquire()
    try:
        response = client(monkeypatch).get(metadata.PATH)
        assert response.status_code == 429 and response.headers["retry-after"] == "60" and not metadata._used
    finally: metadata._lock.release()


@pytest.mark.parametrize("method,kwargs,expected", [
    ("GET", {"params": {"object": "tasks"}}, 422), ("GET", {"content": b"x"}, 422),
    ("GET", {"headers": {"Transfer-Encoding": "chunked"}}, 422), ("POST", {}, 405), ("HEAD", {}, 405)])
def test_no_parameters_payload_or_unsupported_methods_and_no_store(monkeypatch, method, kwargs, expected):
    monkeypatch.setattr(metadata, "collect_metadata", lambda _settings: pytest.fail("collection"))
    response = client(monkeypatch).request(method, metadata.PATH, **kwargs)
    assert response.status_code == expected and response.headers["cache-control"] == "no-store"
    assert not metadata._used


def test_ingress_and_existing_admin_checks_cannot_be_replaced_by_api_key(monkeypatch):
    from starlette.requests import Request
    monkeypatch.setattr(metadata, "runtime_option", lambda _name, _fallback: {"issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    monkeypatch.setattr(metadata, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(metadata, "trusted_ingress_request", lambda _request: False)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"synthetic")], "method": "GET", "path": metadata.PATH})
    with pytest.raises(HTTPException) as caught: metadata.require_metadata_admin(request)
    assert caught.value.status_code == 401
    monkeypatch.setattr(metadata, "trusted_ingress_request", lambda _request: True)
    seen = []
    monkeypatch.setattr(metadata, "authorize_admin", lambda _request, **kwargs: seen.append(kwargs["x_api_key"]))
    request = Request({"type": "http", "headers": [(b"x-ingress-path", b"/api/hassio_ingress/synthetic/"), (b"x-remote-user-id", b"synthetic-ha-id")], "method": "GET", "path": metadata.PATH})
    metadata.require_metadata_admin(request)
    assert seen == [None]


def test_new_scope_is_not_legacy_window_or_mobile_allowlist():
    root = Path(__file__).parents[1]
    assert metadata.WINDOW_OPTION != "mobile_work_review_qualification_window"
    assert "mobile-work-review-metadata" not in (root / "custom_components/baiamonte_branding/mobile_proxy.py").read_text()
    text = Path(metadata.__file__).read_text()
    assert "column_default" not in text and "SHOW CREATE" not in text and "SELECT *" not in text
