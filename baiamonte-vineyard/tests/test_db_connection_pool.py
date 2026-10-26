from pathlib import Path

import pytest

from app import db


class FakeCursor:
    def __init__(self, row=None):
        self.row = row or {"value": 1}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=()):
        return 1

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, *, ping_error=False):
        self.ping_error = ping_error
        self.pings = 0
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        return FakeCursor()

    def ping(self, reconnect=True):
        self.pings += 1
        if self.ping_error:
            raise RuntimeError("stale")

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


@pytest.fixture(autouse=True)
def empty_connection_pool():
    db.close_connection_pool()
    yield
    db.close_connection_pool()


def test_sequential_queries_reuse_one_healthy_connection(monkeypatch):
    connection = FakeConnection()
    created = []

    def fake_connect(database=None):
        created.append(database)
        return connection

    monkeypatch.setattr(db, "connect", fake_connect)

    assert db.fetch_one("SELECT 1") == {"value": 1}
    assert db.fetch_one("SELECT 1") == {"value": 1}

    assert created == [None]
    assert connection.commits == 2
    assert connection.pings == 1
    assert connection.closes == 0


def test_failed_transaction_rolls_back_and_returns_connection(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(db, "connect", lambda database=None: connection)

    with pytest.raises(ValueError, match="stop"):
        with db.transaction():
            raise ValueError("stop")

    assert connection.rollbacks == 1
    assert connection.closes == 0
    assert db.fetch_one("SELECT 1") == {"value": 1}
    assert connection.pings == 1


def test_stale_connection_is_closed_and_replaced(monkeypatch):
    stale = FakeConnection(ping_error=True)
    fresh = FakeConnection()
    db._connection_pool.put_nowait(stale)
    monkeypatch.setattr(db, "connect", lambda database=None: fresh)

    assert db.fetch_one("SELECT 1") == {"value": 1}

    assert stale.closes == 1
    assert fresh.commits == 1


def test_shutdown_closes_an_active_lease_and_does_not_repool_it(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(db, "connect", lambda database=None: connection)

    leased = db._acquire_connection()
    db.close_connection_pool()
    db._release_connection(leased, reusable=True)

    assert connection.closes >= 1
    assert db._connection_pool.empty()
    assert id(connection) not in db._leased_connections


def test_large_api_responses_enable_gzip():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")
    display_source = (root / "app" / "display_server.py").read_text(encoding="utf-8")

    assert "GZipMiddleware, minimum_size=1000" in main_source
    assert "GZipMiddleware, minimum_size=1000" in display_source


def test_query_profile_attributes_parameter_free_metrics_to_endpoint():
    token = db.set_query_context("GET /api/v1/example/{id}")
    try:
        db._record_query(
            "SELECT * FROM financial_documents WHERE estate_id=%s AND gross_total=125.50 AND notes='private'",
            0.375,
            succeeded=True,
        )
    finally:
        db.reset_query_context(token)

    profile = db.database_profile_snapshot()
    endpoint = next(item for item in profile["endpoints"] if item["endpoint"] == "GET /api/v1/example/{id}")
    query = next(item for item in profile["queries"] if item["endpoint"] == "GET /api/v1/example/{id}")
    assert endpoint["slow_query_count"] == 1
    assert endpoint["max_query_ms"] == 375.0
    assert query["label"] == "SELECT financial_documents"
    assert "125.50" not in query["statement"]
    assert "private" not in query["statement"]


def test_main_closes_database_pool_during_lifespan_shutdown():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "main.py").read_text(encoding="utf-8")
    shutdown = source.split("yield", 1)[1].split('app = FastAPI', 1)[0]
    assert "finally:" in shutdown
    assert "close_connection_pool()" in shutdown


def test_measured_database_hot_paths_have_targeted_indexes():
    root = Path(__file__).resolve().parents[1]
    migration = (root / "db" / "migrations" / "226_database_hot_path_indexes.sql").read_text(encoding="utf-8")
    assert "ix_integration_estate_time (estate_id,occurred_at,id)" in migration
    assert "ix_integration_estate_status_time (estate_id,status,occurred_at,id)" in migration
    assert "ix_integration_estate_stream_time (estate_id,integration_name,event_type,occurred_at,id)" in migration
    assert "ix_gdd_estate_season_dates (estate_id,season_id,final_forecast_date,predicted_date)" in migration
    assert "ix_gdd_estate_variety_computed (estate_id,variety_id,computed_at)" in migration


def test_follow_up_profiles_use_latest_forecasts_and_indexable_audit_dates():
    root = Path(__file__).resolve().parents[1]
    migration = (root / "db" / "migrations" / "227_latest_forecast_and_audit_indexes.sql").read_text(encoding="utf-8")
    treatments = (root / "app" / "domains" / "treatments.py").read_text(encoding="utf-8")
    routes = (root / "app" / "domains" / "treatment_routes.py").read_text(encoding="utf-8")
    assert "ix_gdd_estate_season_variety_computed (estate_id,season_id,variety_id,computed_at)" in migration
    assert "ix_audit_estate_entity_time (estate_id,entity_type,occurred_at)" in migration
    assert "MAX(newer.computed_at)" in treatments
    assert "YEAR(occurred_at)=%s" not in routes
    assert "occurred_at>=%s AND occurred_at<%s" in routes


def test_every_python_database_service_drains_its_pool_on_shutdown():
    root = Path(__file__).resolve().parents[1]
    for relative in ("app/main.py", "app/display_server.py", "app/tank_label_server.py", "app/mcp_server.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "close_connection_pool" in source, relative
        assert "finally:" in source, relative
