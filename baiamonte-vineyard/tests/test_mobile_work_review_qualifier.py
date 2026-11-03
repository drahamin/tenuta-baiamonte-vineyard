from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import threading

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app.domains import mobile_work_review_qualifier as qualifier


ESTATE = "11111111-1111-4111-8111-111111111111"
SETTINGS = SimpleNamespace(db_host="core-mariadb", db_port=3306, db_name="baiamonte_vineyard", estate_id=ESTATE,
                           db_user="synthetic", db_password="never-print-synthetic-password", trust_home_assistant_ingress=True)


class Connection:
    def __init__(self, *, missing=None, count=1, failure=False, duplicate=False, wrong_estate=False):
        self.calls = []; self.rollbacks = 0; self.closed = 0
        self.missing = missing; self.count = count; self.failure = failure
        self.duplicate = duplicate; self.wrong_estate = wrong_estate
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, sql, params=()):
        self.calls.append((sql, params)); self.sql = sql
        if self.failure and sql.startswith("SELECT"):
            raise RuntimeError("never-print-synthetic-password or SQL parameter")
    def fetchall(self):
        if "information_schema.columns" in self.sql:
            return [{"table_name": name, "column_name": field, "table_type": "VIEW" if spec["view"] else "BASE TABLE"}
                    for name, spec in qualifier.SOURCE_SPECS.items() for field in spec["fields"] if (name, field) != self.missing]
        name = next(name for name in qualifier.SOURCE_SPECS if f"FROM `{name}`" in self.sql)
        spec = qualifier.SOURCE_SPECS[name]
        rows = []
        for index in range(self.count):
            row = {field: None for field in spec["fields"]}
            row.update({"estate_id": "other-estate" if self.wrong_estate else ESTATE,
                        spec["identity"]: f"sensitive-id-{0 if self.duplicate else index}"})
            if "title" in row: row["title"] = 1
            if spec["clock"]: row[spec["clock"]] = 1
            rows.append(row)
        return rows
    def rollback(self): self.rollbacks += 1
    def close(self): self.closed += 1


def collect(connection, **kwargs):
    return qualifier.collect_qualification(SETTINGS, connection_factory=lambda _: connection, monotonic=lambda: 0.0, **kwargs)


def test_fixed_six_source_reads_are_bounded_rollback_only_and_redacted():
    connection = Connection()
    result = collect(connection)
    assert result["ok"] and len(result["sources"]) == 6
    assert connection.rollbacks == 1 and connection.closed == 1
    assert connection.calls[:4] == [("SET SESSION max_statement_time=2", ()), ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", ()), ("SET TRANSACTION READ ONLY", ()), ("START TRANSACTION WITH CONSISTENT SNAPSHOT", ())]
    reads = [(sql, params) for sql, params in connection.calls if sql.startswith("SELECT") and "information_schema" not in sql]
    assert len(reads) == 6
    assert all("WHERE estate_id=%s" in sql and "LIMIT 2001" in sql and "SELECT *" not in sql and params == (ESTATE,) for sql, params in reads)
    assert all("LEFT(`estate_id`,192)" in sql and "CASE WHEN" in sql for sql, _ in reads)
    assert all(not result["sources"][name]["source_clock_timezone_verified"] for name in qualifier.SOURCE_SPECS)
    assert "full_reporting_token_provenance" in result["not_verified"]
    for secret in (ESTATE, "sensitive-id", "sensitive-record-content", SETTINGS.db_password): assert secret not in str(result)


def test_standalone_qualifier_allowlist_matches_frozen_projection_contract():
    import json
    fixture = Path(__file__).parent / "fixtures/mobile_work_review_qualification_fields_v1.json"
    assert {name: list(fields) for name, fields in qualifier._SAFE_FIELDS.items()} == json.loads(fixture.read_text())


def test_missing_filtered_view_column_is_not_replaced_by_underlying_view():
    connection = Connection(missing=("ro_lab_decision_queue", "sample_id"))
    result = collect(connection)
    assert not result["ok"] and result["sources"]["ro_lab_decision_queue"]["missing_required_columns"] == ["sample_id"]
    assert not any("FROM `ro_lab_decision_queue`" in sql or "v_lab_decision_queue" in sql for sql, _ in connection.calls)


@pytest.mark.parametrize("kwargs", [{"count": 2001}, {"count": 2, "duplicate": True}, {"wrong_estate": True}])
def test_over_bound_duplicate_and_scope_discrepancies_fail_closed(kwargs):
    assert collect(Connection(**kwargs))["ok"] is False


def test_query_exception_always_rollback_close():
    connection = Connection(failure=True)
    with pytest.raises(RuntimeError): collect(connection)
    assert connection.rollbacks == 1 and connection.closed == 1


def test_metadata_cap_fails_without_reading_source_rows():
    class Excess(Connection):
        def fetchall(self): return super().fetchall() * 10
    connection = Excess()
    with pytest.raises(qualifier.QualificationFailure): collect(connection)
    assert connection.rollbacks == 1 and connection.closed == 1
    assert not any("WHERE estate_id=%s" in sql for sql, _ in connection.calls)


def test_budget_failure_always_rollback_close():
    connection = Connection(); ticks = iter([0, 13])
    with pytest.raises(qualifier.QualificationFailure):
        qualifier.collect_qualification(SETTINGS, connection_factory=lambda _: connection, monotonic=lambda: next(ticks))
    assert connection.rollbacks == 1 and connection.closed == 1


def test_off_scope_settings_never_open_connection():
    settings = SimpleNamespace(**{**vars(SETTINGS), "db_host": "unapproved-host"})
    with pytest.raises(qualifier.QualificationFailure):
        qualifier.collect_qualification(settings, connection_factory=lambda _: pytest.fail("connected"))


@pytest.mark.parametrize("window", [None, {}, {"issued_at": 1, "expires_at": 2},
    {"issued_at": "2026-11-03", "expires_at": "2026-11-04"},
    {"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T13:00:00Z"},
    {"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T12:01:00Z"}])
def test_activation_default_off_expired_or_too_long(window):
    assert not qualifier.active_window(window, datetime(2026, 11, 3, 12, 2, tzinfo=timezone.utc))


def test_valid_short_window():
    assert qualifier.active_window({"issued_at": "2026-11-03T12:00:00Z", "expires_at": "2026-11-03T12:15:00Z"}, datetime(2026, 11, 3, 12, 2, tzinfo=timezone.utc))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(qualifier, "_attempt_used", False)
    monkeypatch.setattr(qualifier, "_attempt_lock", threading.Lock())
    monkeypatch.setattr(qualifier, "get_settings", lambda: SETTINGS)
    app = FastAPI(); app.include_router(qualifier.router)
    # Override only existing Admin classification, not ingress/window gates.
    monkeypatch.setattr(qualifier, "authorize_admin", lambda *args, **kwargs: None)
    with TestClient(app) as value: yield value


def enable(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(qualifier, "runtime_option", lambda *_: {"issued_at": (now - timedelta(seconds=1)).isoformat(), "expires_at": (now + timedelta(seconds=60)).isoformat()})
    monkeypatch.setattr(qualifier, "trusted_ingress_request", lambda _: True)


HEADERS = {"X-Ingress-Path": "/api/hassio_ingress/synthetic", "X-Remote-User-Id": "ha-synthetic-001", "X-Remote-User-Name": "synthetic-admin"}


def test_disabled_route_never_reads_source(client, monkeypatch):
    monkeypatch.setattr(qualifier, "runtime_option", lambda *_: None)
    monkeypatch.setattr(qualifier, "collect_qualification", lambda *_: pytest.fail("source accessed"))
    response = client.get(qualifier.PATH, headers=HEADERS)
    assert response.status_code == 404 and response.headers["cache-control"] == "no-store"


def test_ingress_required_no_api_key_or_direct_mobile_bearer_access(client, monkeypatch):
    enable(monkeypatch)
    for headers in ({"X-API-Key": "synthetic"}, {"Authorization": "Bearer " + "A" * 43},
                    {**HEADERS, "X-Ingress-Path": "/api/baiamonte_mobile/v1"}):
        assert client.get(qualifier.PATH, headers=headers).status_code == 401
    monkeypatch.setattr(qualifier, "trusted_ingress_request", lambda _: False)
    assert client.get(qualifier.PATH, headers=HEADERS).status_code == 401


def test_non_admin_denial_precedes_source_read(client, monkeypatch):
    enable(monkeypatch)
    def denied(*args, **kwargs): raise HTTPException(403, "Admin required")
    monkeypatch.setattr(qualifier, "authorize_admin", denied)
    monkeypatch.setattr(qualifier, "collect_qualification", lambda *_: pytest.fail("source accessed"))
    response = client.get(qualifier.PATH, headers=HEADERS)
    assert response.status_code == 403 and response.headers["cache-control"] == "no-store"


def test_one_attempt_no_cache_no_parameters_and_no_exception_text(client, monkeypatch):
    enable(monkeypatch)
    assert client.get(qualifier.PATH + "?object=tasks", headers=HEADERS).status_code == 422
    assert client.post(qualifier.PATH, headers=HEADERS).status_code == 405
    def failed(_): raise RuntimeError("never-print-synthetic-password")
    monkeypatch.setattr(qualifier, "collect_qualification", failed)
    response = client.get(qualifier.PATH, headers=HEADERS)
    assert response.status_code == 503 and "never-print" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get(qualifier.PATH, headers=HEADERS).status_code == 410


def test_concurrent_attempt_rejected_without_read(client, monkeypatch):
    enable(monkeypatch)
    qualifier._attempt_lock.acquire()
    try:
        response = client.get(qualifier.PATH, headers=HEADERS)
        assert response.status_code == 429 and response.headers["retry-after"] == "60"
    finally: qualifier._attempt_lock.release()


def test_success_is_uncached_one_attempt_and_existing_admin_gets_no_api_key_bypass(client, monkeypatch):
    enable(monkeypatch)
    seen = []
    monkeypatch.setattr(qualifier, "authorize_admin", lambda *args, **kwargs: seen.append(kwargs["x_api_key"]))
    result = collect(Connection())
    monkeypatch.setattr(qualifier, "collect_qualification", lambda _: result)
    assert client.request("GET", qualifier.PATH, headers=HEADERS, content="x").status_code == 422
    response = client.get(qualifier.PATH, headers={**HEADERS, "X-API-Key": "not-used"})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert response.headers["cache-control"] == "no-store" and seen == [None, None]
    assert client.get(qualifier.PATH, headers=HEADERS).status_code == 410


def test_packaged_qualifier_default_off_and_core_allowlist_unchanged():
    root = Path(qualifier.__file__).parents[1]
    assert "app.include_router(work_review_qualifier_router)" in (root / "main.py").read_text()
    assert "mobile-work-review-qualification" not in (root.parent / "custom_components/baiamonte_branding/mobile_proxy.py").read_text()
    import yaml
    config = yaml.safe_load((root.parent / "config.yaml").read_text())
    assert config["options"]["mobile_work_review_qualification_window"] == {"issued_at": "", "expires_at": ""}
    assert not qualifier.active_window(config["options"]["mobile_work_review_qualification_window"], datetime.now(timezone.utc))
    assert config["schema"]["mobile_work_review_qualification_window"] == {"issued_at": "str", "expires_at": "str"}
    # Pure helpers now support only the separately gated Admin validator; their
    # presence must not register mobile parity or expand issued role ceilings.
    mobile = (root / "domains/mobile_site_routes.py").read_text()
    assert "mobile_work_review_projection" not in mobile and "mobile_work_review_source" not in mobile
    assert "mobile-work-review-tasks-validation" not in (root.parent / "custom_components/baiamonte_branding/mobile_proxy.py").read_text()
    from app.domains.mobile_site_routes import _ROLE_CAPABILITIES
    assert _ROLE_CAPABILITIES["admin"] == {"session", "status", "catalog", "records", "weather", "work", "review", "energy", "etna"}
    assert not (root / "domains/mobile_work_review_optin.py").exists()
