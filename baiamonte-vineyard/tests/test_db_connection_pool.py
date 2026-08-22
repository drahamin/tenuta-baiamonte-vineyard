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


def test_large_api_responses_enable_gzip():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")
    display_source = (root / "app" / "display_server.py").read_text(encoding="utf-8")

    assert "GZipMiddleware, minimum_size=1000" in main_source
    assert "GZipMiddleware, minimum_size=1000" in display_source
