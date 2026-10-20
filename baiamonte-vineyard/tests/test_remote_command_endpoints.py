from contextlib import contextmanager
import json
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app import main
from app.models import TaskStatusUpdate


def request(headers: dict[str, str], host: str = "127.0.0.1") -> Request:
    return Request({
        "type": "http", "method": "PATCH", "path": "/api/v1/tasks/task-1/status",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "client": (host, 12345), "server": ("127.0.0.1", 8101), "scheme": "http",
        "query_string": b"",
    })


def command_request(expected: int = 7, host: str = "127.0.0.1") -> Request:
    return request({
        "X-API-Key": "local-secret",
        "X-Baiamonte-Command-ID": "10000000-0000-4000-8000-000000000001",
        "X-Baiamonte-Record-ID": "task-1",
        "X-Baiamonte-Expected-Revision": str(expected),
    }, host)


class Cursor:
    def __init__(self, prior: dict | None = None):
        self.prior = prior
        self.last_sql = ""
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql, parameters=()):
        self.last_sql = sql
        self.executed.append((sql, parameters))
        return 1

    def fetchone(self):
        if "FROM audit_events" in self.last_sql and self.prior is not None:
            return {"after_data": json.dumps({"result": self.prior})}
        return None


def install_transaction(monkeypatch, cursor: Cursor):
    @contextmanager
    def transaction():
        yield None, cursor
    monkeypatch.setattr(main, "transaction", transaction)


def test_remote_command_headers_require_loopback_and_local_api_key(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(api_key="local-secret"))
    parsed = main._remote_command_headers(command_request(), "task-1")
    assert parsed == ("10000000-0000-4000-8000-000000000001", 7, "task-1")
    try:
        main._remote_command_headers(command_request(host="192.168.0.55"), "task-1")
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("non-loopback remote command headers were accepted")


def test_task_remote_update_is_revision_checked_and_durably_deduplicated(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(api_key="local-secret"))
    monkeypatch.setattr(main, "estate_id", lambda: "estate-1")
    monkeypatch.setattr(main, "locked_reporting_record", lambda *_args: ({"id": "task-1"}, 7))
    monkeypatch.setattr(main, "publish_task_to_google", lambda _task_id: {"published": False, "reason": "test"})
    audits = []
    monkeypatch.setattr(main, "audit", lambda _cursor, action, entity_type, entity_id, after, actor="home-assistant": audits.append((action, entity_type, entity_id, after, actor)))
    cursor = Cursor()
    install_transaction(monkeypatch, cursor)

    result = main.update_task_status("task-1", TaskStatusUpdate(status="done"), command_request())
    assert result["ok"] is True
    assert any("UPDATE tasks SET status" in sql for sql, _ in cursor.executed)
    assert audits[-1][0:3] == ("remote_command_applied", "remote_command", "10000000-0000-4000-8000-000000000001")
    assert audits[-1][-1] == "remote-erp"

    prior = {"ok": True, "deduplicated": True}
    cursor = Cursor(prior)
    install_transaction(monkeypatch, cursor)
    assert main.update_task_status("task-1", TaskStatusUpdate(status="done"), command_request()) == prior
    assert not any("UPDATE tasks SET status" in sql for sql, _ in cursor.executed)


def test_task_remote_update_returns_conflict_before_write(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(api_key="local-secret"))
    monkeypatch.setattr(main, "estate_id", lambda: "estate-1")
    monkeypatch.setattr(main, "locked_reporting_record", lambda *_args: ({"id": "task-1"}, 9))
    cursor = Cursor()
    install_transaction(monkeypatch, cursor)
    try:
        main.update_task_status("task-1", TaskStatusUpdate(status="done"), command_request(expected=7))
    except HTTPException as error:
        assert error.status_code == 409
        assert error.detail == {"reason": "revision_conflict", "expected_revision": 7, "actual_revision": 9}
    else:
        raise AssertionError("stale revision was applied")
    assert not any("UPDATE tasks SET status" in sql for sql, _ in cursor.executed)
