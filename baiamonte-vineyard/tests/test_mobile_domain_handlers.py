import json
from contextlib import contextmanager
from datetime import datetime

import pytest

from app import mobile_domain_handlers as handlers
from app.remote_erp import reporting_row_revision


ESTATE = "00000000-0000-4000-8000-000000000001"
ACTION = "11111111-1111-4111-8111-111111111111"
SHIFT = "22222222-2222-4222-8222-222222222222"
PERSON = "33333333-3333-4333-8333-333333333333"


class Cursor:
    def __init__(self, records=None, receipt=None):
        self.records = records or {}
        self.receipt = receipt
        self.current = None
        self.current_all = []
        self.executed = []
        self.rowcount = 1

    def execute(self, sql, params=()):
        self.executed.append((sql, params)); self.current = None; self.current_all = []; self.rowcount = 1
        if sql.startswith("SELECT workflow,payload_sha256"):
            self.current = self.receipt
        elif "FROM people" in sql:
            self.current = {"id": PERSON, "name": "Estate Worker", "role": "Field worker"}
        elif "FROM mobile_timeclock_events" in sql:
            self.current_all = list(self.records.get("events", []))
        elif "FROM labor_entries" in sql:
            self.current = self.records.get("open_shift")
        elif "FROM seasons" in sql:
            self.current = {"id": "season-1"}
        elif sql.startswith("SELECT `"):
            table = sql.split("FROM `", 1)[1].split("`", 1)[0]
            self.current = self.records.get((table, params[0]))
        elif "SUM(quantity_delta)" in sql:
            self.current = {"quantity": 100}
        return self.rowcount

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current_all


def use_cursor(monkeypatch, cursor):
    @contextmanager
    def fake_transaction():
        yield None, cursor
    monkeypatch.setattr(handlers, "transaction", fake_transaction)
    monkeypatch.setattr(handlers, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(handlers, "audit", lambda *args, **kwargs: None)


def timeclock_item():
    actor = {"username": "worker", "server_role": "admin"}
    payload = {
        "contract": "baiamonte.mobile-timeclock.v1", "event_uuid": ACTION, "idempotency_key": ACTION,
        "estate_id": ESTATE, "event_type": "clock_in", "shift_uuid": SHIFT,
        "occurred_at": "2026-10-20T06:00:00.000000Z", "client_created_at": "2026-10-20T06:00:02.000000Z",
        "source_timezone": "Europe/Rome", "expected_shift_revision": None, "note": "Start round",
        "correction_of_event_uuid": None,
        "actor": {"user_id": "user-1", "username": "worker", "person_id": PERSON, "server_role": "admin"},
        "status": "pending_validation", "applied": False, "payroll_approved": False,
        "location_collected": False, "side_effects": [],
    }
    return {"contract": "baiamonte.mobile-pending-domain.v1", "action_uuid": ACTION, "workflow": "timeclock", "authoritative_handler": handlers.HANDLERS["timeclock"], "estate_id": ESTATE, "actor": actor, "payload": payload}


def racking_item(monkeypatch):
    source = {"id": "tank-a", "estate_id": ESTATE, "capacity_l": 1000, "status": "active"}
    target = {"id": "tank-b", "estate_id": ESTATE, "capacity_l": 600, "status": "active"}
    lot = {"id": "lot-1", "estate_id": ESTATE, "season_id": "season-1", "current_container_id": "tank-a", "volume_l": 500, "stage": "aging"}
    columns = {"cellar_containers": list(source), "wine_lots": list(lot), "products": ["id", "estate_id", "unit", "active"]}
    monkeypatch.setattr(handlers, "_safe_columns", lambda _cursor: columns)
    payload = {
        "contract": "baiamonte.mobile-cellar-operation.v1", "operation_uuid": ACTION, "idempotency_key": ACTION,
        "kind": "racking.v1", "estate_id": ESTATE, "occurred_at": "2026-10-20T08:00:00.000000Z",
        "client_created_at": "2026-10-20T08:00:02.000000Z", "source_timezone": "Europe/Rome",
        "expected_revisions": {"source_container_id": str(reporting_row_revision(source)), "target_container_id": str(reporting_row_revision(target)), "wine_lot_id": str(reporting_row_revision(lot))},
        "payload": {"source_container_id": "tank-a", "target_container_id": "tank-b", "wine_lot_id": "lot-1", "transfer_volume_l": 500.0, "expected_loss_l": 5.0, "note": "Rack"},
        "correction_of_operation_uuid": None, "actor": {"user_id": "user-1", "username": "owner", "server_role": "admin"},
        "status": "pending_validation", "applied": False, "inventory_committed": False, "device_control": False, "side_effects": [],
    }
    item = {"contract": "baiamonte.mobile-pending-domain.v1", "action_uuid": ACTION, "workflow": "cellar", "authoritative_handler": handlers.HANDLERS["cellar"], "estate_id": ESTATE, "actor": {"username": "owner", "server_role": "admin"}, "payload": payload}
    return item, {("cellar_containers", "tank-a"): source, ("cellar_containers", "tank-b"): target, ("wine_lots", "lot-1"): lot}


def test_timeclock_handler_creates_reviewable_labor_shift_and_durable_receipt(monkeypatch):
    cursor = Cursor(); use_cursor(monkeypatch, cursor)
    result = handlers.handle_mobile_domain_action(timeclock_item())
    assert result.status == "accepted"
    assert result.result["actual_revisions"] == {"shift_uuid": "1"}
    assert result.result["inventory_committed"] is False
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "INSERT INTO labor_entries" in sql
    assert "INSERT INTO mobile_timeclock_events" in sql
    assert "UPDATE mobile_domain_action_receipts" in sql
    assert "payroll" not in result.result["reason"] or result.result["reason"] == "recorded"


def test_completed_receipt_replays_without_second_domain_write(monkeypatch):
    payload = timeclock_item()["payload"]
    digest = handlers.hashlib.sha256(handlers._canonical(payload).encode()).hexdigest()
    stored = {"authoritative_record_ids": [ACTION, SHIFT], "actual_revisions": {"shift_uuid": "1"}, "reason": "recorded", "transaction_uuid": None, "inventory_committed": False, "atomic": False}
    cursor = Cursor(receipt={"workflow": "timeclock", "payload_sha256": digest, "status": "accepted", "result_json": json.dumps(stored)})
    use_cursor(monkeypatch, cursor)
    assert handlers.handle_mobile_domain_action(timeclock_item()).result == stored
    assert not any("INSERT INTO labor_entries" in sql for sql, _ in cursor.executed)


def test_racking_handler_checks_exact_revisions_and_commits_one_transaction(monkeypatch):
    item, records = racking_item(monkeypatch)
    cursor = Cursor(records); use_cursor(monkeypatch, cursor)
    monkeypatch.setattr(handlers, "new_id", lambda: "44444444-4444-4444-8444-444444444444")
    result = handlers.handle_mobile_domain_action(item)
    assert result.status == "accepted"
    assert result.result["transaction_uuid"] == "44444444-4444-4444-8444-444444444444"
    assert result.result["inventory_committed"] is True and result.result["atomic"] is True
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "UPDATE wine_lots SET current_container_id" in sql
    assert "INSERT INTO cellar_operations" in sql
    assert "inventory_movements" not in sql


def test_racking_revision_conflict_is_durable_and_has_no_source_write(monkeypatch):
    item, records = racking_item(monkeypatch)
    item["payload"]["expected_revisions"]["source_container_id"] = "1"
    cursor = Cursor(records); use_cursor(monkeypatch, cursor)
    result = handlers.handle_mobile_domain_action(item)
    assert result.status == "conflict" and result.result["reason"] == "expected_revision_conflict"
    assert not any("UPDATE wine_lots" in sql or "INSERT INTO cellar_operations" in sql for sql, _ in cursor.executed)


def test_malformed_cellar_references_are_durably_rejected(monkeypatch):
    item, records = racking_item(monkeypatch)
    del item["payload"]["expected_revisions"]["wine_lot_id"]
    cursor = Cursor(records); use_cursor(monkeypatch, cursor)
    result = handlers.handle_mobile_domain_action(item)
    assert result.status == "rejected" and result.result["reason"] == "cellar_references_invalid"
    assert any("UPDATE mobile_domain_action_receipts" in sql for sql, _ in cursor.executed)
    assert not any("UPDATE wine_lots" in sql or "INSERT INTO cellar_operations" in sql for sql, _ in cursor.executed)


def test_handlers_are_source_disabled_and_proposed_schema_is_not_a_migration():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    sync = (root / "app" / "mobile_intake_sync.py").read_text(encoding="utf-8")
    assert "mobile_domain_handlers" not in main
    assert "mobile_domain_handlers" not in sync
    assert (root / "db" / "proposed" / "mobile_domain_handlers.sql").is_file()
    assert not (root / "db" / "migrations" / "234_mobile_domain_handlers.sql").exists()
