from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domains import mobile_work_review_connection as connection
from test_mobile_work_review_source import ESTATE


def settings(**changes):
    return SimpleNamespace(db_host="core-mariadb", db_port=3306, db_name="baiamonte_vineyard",
                           db_user="synthetic-app", db_password="synthetic-never-export", estate_id=ESTATE, **changes)


def test_factory_is_lazy_and_uses_only_exact_scope_with_dedicated_timeouts(monkeypatch):
    calls = []
    monkeypatch.setattr(connection.pymysql, "connect", lambda **kwargs: calls.append(kwargs) or object())
    boundary = connection.SourceBoundary(ESTATE)
    factory = connection.make_connection_factory(settings(), boundary)
    assert calls == []
    assert factory() is not factory()
    assert len(calls) == 2
    for call in calls:
        assert (call["host"], call["port"], call["database"]) == ("core-mariadb", 3306, "baiamonte_vineyard")
        assert call["connect_timeout"] == call["read_timeout"] == call["write_timeout"] == 3
        assert call["cursorclass"] is connection.ProfilingDictCursor and not call["autocommit"]


@pytest.mark.parametrize("field,value", [("db_host", "localhost"), ("db_port", 3307), ("db_name", "other"), ("db_user", ""), ("db_password", None), ("estate_id", "different-estate")])
def test_bad_existing_settings_never_connect(monkeypatch, field, value):
    monkeypatch.setattr(connection.pymysql, "connect", lambda **_kwargs: pytest.fail("connected"))
    data = settings(); setattr(data, field, value)
    with pytest.raises(connection.SourceUnavailable): connection.make_connection_factory(data, connection.SourceBoundary(ESTATE))


@pytest.mark.parametrize("boundary", [connection.SourceBoundary("invalid"), connection.SourceBoundary(ESTATE, db_host="localhost")])
def test_boundary_cannot_override_existing_source(boundary):
    with pytest.raises(connection.SourceUnavailable): connection.make_connection_factory(settings(), boundary)


def test_factory_is_not_registered_or_using_global_settings_or_pool():
    root = Path(__file__).parents[1]
    assert "mobile_work_review_connection" not in (root / "app/main.py").read_text()
    assert "mobile_work_review_connection" not in (root / "app/domains/mobile_site_routes.py").read_text()
    text = Path(connection.__file__).read_text()
    for forbidden in ("get_settings(", "runtime_option(", "_acquire_connection", "transaction(", "print(", "logger."):
        assert forbidden not in text
