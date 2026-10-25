from contextlib import contextmanager
import json
from pathlib import Path

from app.domains import payroll_admin_routes as routes


ROOT = Path(__file__).resolve().parents[1]


def test_retirement_registry_accepts_mariadb_json_and_rejects_bad_shapes(monkeypatch):
    monkeypatch.setattr(routes, "estate_id", lambda: "estate")
    monkeypatch.setattr(routes, "fetch_one", lambda *_: {
        "setting_value": json.dumps({"mattia": {"name": "Mattia", "retired_at": "2026-10-25"}})
    })
    assert routes.retired_labor_workers()["mattia"]["name"] == "Mattia"
    monkeypatch.setattr(routes, "fetch_one", lambda *_: {"setting_value": ["bad"]})
    assert routes.retired_labor_workers() == {}


def test_retirement_is_reversible_and_preserves_labor_rows(monkeypatch):
    calls = []

    class Cursor:
        def execute(self, sql, params):
            calls.append((sql, params))
            return 1

    @contextmanager
    def fake_transaction():
        yield None, Cursor()

    monkeypatch.setattr(routes, "estate_id", lambda: "estate")
    monkeypatch.setattr(routes, "retired_labor_workers", lambda: {})
    monkeypatch.setattr(routes, "transaction", fake_transaction)
    monkeypatch.setattr(routes, "audit", lambda *args: calls.append(("AUDIT", args)))
    request = type("Request", (), {"headers": {"X-Remote-User-Name": "David"}})()
    result = routes.set_labor_worker_retirement(
        "mattia", {"worker_name": "Mattia", "retired": True, "reason": "Season ended"}, request,
    )
    assert result == {
        "saved": True, "worker_key": "mattia", "worker_name": "Mattia",
        "retired": True, "history_preserved": True,
    }
    sql = "\n".join(item[0] for item in calls if item[0] != "AUDIT")
    assert "app_settings" in sql
    assert "labor_entries" not in sql
    saved = json.loads(next(params[2] for statement, params in calls if statement != "AUDIT"))
    assert saved["mattia"]["reason"] == "Season ended"


def test_admin_ui_has_active_and_closed_worker_views():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    payroll = (ROOT / "app/static/assets/payroll.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'id="adminRetiredLabor"' in html
    assert "Closed worker archive" in html
    assert "/labor-workers/${encodeURIComponent(person.key)}/retirement" in javascript
    assert "Historical hours and payments will remain unchanged" in javascript
    assert "history_preserved" in (ROOT / "app/domains/payroll_admin_routes.py").read_text(encoding="utf-8")
    assert '"retired_labor_workers"' in backend
    assert "retired_labor_workers" in payroll


def test_active_worker_cards_explain_presence_evidence_and_archived_cards_do_not():
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert '"presence_evidence"' in backend
    assert '"presence_note": presence_note' in backend
    assert "camera_evidence = recent_camera_match" in backend
    assert "person.presence_note" in javascript
    assert "labor-presence-note" in javascript
    archived = javascript.split("const retired=state.adminControl?.retired_labor_workers", 1)[1]
    assert "person.presence_note" not in archived.split("const renderSystemLightsCore", 1)[0]
