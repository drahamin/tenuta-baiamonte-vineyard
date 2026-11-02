from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access import authorize_admin
from app.domains import payroll, payroll_admin_routes


def owner_row(**changes):
    row = {
        "id": "owner-1", "estate_id": "estate-1",
        "entry_source": "owner_reconciliation",
        "source_labor_id": payroll.OWNER_LABOR_SOURCE_PREFIX + "-vincenzo-part-time",
        "worker_username": None, "person_or_crew": "Vincenzo (part-time)",
        "work_date": date(2026, 10, 1), "regular_hours": Decimal("45.00"),
        "overtime_hours": None, "hourly_rate_eur": Decimal("10.00"),
        "labor_cost_eur": Decimal("450.00"), "other_cost_eur": Decimal("12.00"),
        "expense_amount_eur": None, "pay_due_date": None,
        "approval_status": "draft", "payment_status": "unknown",
        "locked_at": None, "paid_at": None, "approved_by": None,
        "notes": "October monthly aggregate; overtime unknown", "payroll_scope": "part_time",
    }
    row.update(changes)
    return row


class OwnerCursor:
    def __init__(self, row, payment_count=0):
        self.row, self.payment_count = row, payment_count
        self.executed = []
        self.result = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith("SELECT * FROM labor_entries"):
            self.result = self.row
        elif sql.startswith("SELECT COUNT(*)"):
            self.result = {"payment_count": self.payment_count}

    def fetchone(self):
        return self.result


@pytest.fixture
def setup_approval(monkeypatch):
    def setup(row, payment_count=0):
        cursor, audits, events = OwnerCursor(row, payment_count), [], []

        @contextmanager
        def transaction():
            events.append("begin")
            try:
                yield None, cursor
            except Exception:
                events.append("rollback")
                raise
            else:
                events.append("commit")

        def audit(*args):
            assert events == ["begin"]
            audits.append(args)

        monkeypatch.setattr(payroll, "transaction", transaction)
        monkeypatch.setattr(payroll, "audit", audit)
        return cursor, audits, events
    return setup


def payload(row):
    return {"review_revision": payroll.owner_labor_review_revision(row),
            "verified_wages": True, "review_note": "Verified October source wages"}


def test_approval_only_locks_existing_wages_and_keeps_unknowns(setup_approval):
    row = owner_row()
    before = dict(row)
    cursor, audits, events = setup_approval(row)
    result = payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert result["payment_status"] == "unpaid"
    assert row == before
    assert cursor.executed[0][0].endswith("FOR UPDATE")
    writes = [(sql, params) for sql, params in cursor.executed if sql.startswith(("UPDATE", "INSERT"))]
    assert len(writes) == 1
    sql, params = writes[0]
    assert sql == ("UPDATE labor_entries SET approval_status='approved',approved_by=%s,locked_at=NOW(6),review_note=%s,payment_status='unpaid' "
                   "WHERE id=%s AND estate_id=%s")
    assert params == ("owner", payload(row)["review_note"], "owner-1", "estate-1")
    assert audits[0][0] is cursor
    assert audits[0][4]["before"]["overtime_hours"] is None
    assert events == ["begin", "commit"]


@pytest.mark.parametrize("changes", [
    {"person_or_crew": "Giancarlo Pafumi", "regular_hours": Decimal("157"), "hourly_rate_eur": None, "labor_cost_eur": None},
    {"labor_cost_eur": None}, {"labor_cost_eur": 0}, {"labor_cost_eur": -1},
    {"hourly_rate_eur": None}, {"regular_hours": None}, {"hourly_rate_eur": Decimal("NaN")},
    {"approval_status": "approved"}, {"approval_status": "rejected"},
    {"payment_status": "paid"}, {"payment_status": "verification_needed"},
    {"locked_at": "2026-11-02"}, {"paid_at": "2026-11-02"}, {"approved_by": "someone"},
    {"entry_source": "manual"}, {"source_labor_id": "OWNER-RECON-OCT2026-202611020-other"},
    {"worker_username": "worker"},
])
def test_ineligible_rows_fail_closed_without_writes(changes, setup_approval):
    row = owner_row(**changes)
    cursor, audits, events = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert not any(sql.startswith(("UPDATE", "INSERT")) for sql, _ in cursor.executed)
    assert audits == []
    assert events == ["begin", "rollback"]


@pytest.mark.parametrize("field,value", [("regular_hours", 44), ("notes", "changed"),
    ("other_cost_eur", 13), ("person_or_crew", "Vincenzo harvest"), ("overtime_hours", 0)])
def test_stale_review_rejects_any_changed_record(field, value, setup_approval):
    row = owner_row()
    reviewed = payload(row)
    row[field] = value
    cursor, audits, _ = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError, match="changed") as error:
        payroll.approve_owner_labor_record("owner-1", reviewed, "owner", "estate-1")
    assert error.value.status_code == 409
    assert len(cursor.executed) == 1
    assert not audits


def test_payment_history_blocks_approval(setup_approval):
    row = owner_row()
    cursor, audits, _ = setup_approval(row, payment_count=1)
    with pytest.raises(payroll.PayrollDomainError, match="payment history"):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.executed)
    assert not audits


def test_missing_record_and_audit_failure_roll_back(setup_approval, monkeypatch):
    row = owner_row()
    cursor, _, events = setup_approval(None)
    with pytest.raises(payroll.PayrollDomainError) as error:
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert error.value.status_code == 404
    assert events == ["begin", "rollback"]
    cursor, _, events = setup_approval(row)
    def fail_audit(*args):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(payroll, "audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert events == ["begin", "rollback"]


@pytest.mark.parametrize("name,hours,amount,suffix", [
    ("Vincenzo (part-time)", 45, 450, "VINCENZO-PART-TIME"),
    ("Vincenzo (harvest)", 8, 80, "VINCENZO-HARVEST-20261027"),
    ("Carmela", 7, 70, "CARMELA-20261029"),
])
def test_distinct_workers_and_month_anchors_remain_intact(name, hours, amount, suffix, setup_approval):
    row = owner_row(person_or_crew=name, regular_hours=hours, labor_cost_eur=amount,
                    source_labor_id=payroll.OWNER_LABOR_SOURCE_PREFIX + "-" + suffix)
    cursor, audits, _ = setup_approval(row)
    payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert audits[0][4]["before"]["person_or_crew"] == name
    assert audits[0][4]["before"]["work_date"] == "2026-10-01"
    assert not any("app_settings" in sql or "worker_accounts" in sql for sql, _ in cursor.executed)


@pytest.mark.parametrize("extra", [{"verified_wages": False}, {"review_note": ""},
    {"review_revision": ""}, {"hourly_rate_eur": 10}, {"payment_status": "paid"}])
def test_requires_explicit_review_and_disallows_corrections(extra, setup_approval):
    row = owner_row()
    cursor, _, _ = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError):
        payroll.approve_owner_labor_record("owner-1", {**payload(row), **extra}, "owner", "estate-1")
    assert not cursor.executed


def test_review_returns_revision_of_exact_persisted_row(monkeypatch):
    row = owner_row()
    monkeypatch.setattr(payroll, "fetch_one", lambda sql, params: row)
    result = payroll.owner_labor_review("owner-1", "estate-1")
    assert result["review_revision"] == payload(row)["review_revision"]
    assert result["record"]["work_date"] == "2026-10-01"
    assert result["record"]["overtime_hours"] is None


def test_routes_are_admin_only_and_translate_conflicts(monkeypatch):
    routes = [route for route in payroll_admin_routes.router.routes if "/owner-labor/" in route.path]
    assert len(routes) == 2
    assert all(authorize_admin in {dep.dependency for dep in route.dependencies} for route in routes)
    def fail(*args):
        raise payroll.PayrollDomainError("Reload review", 409)
    monkeypatch.setattr(payroll_admin_routes, "approve_owner_labor_record", fail)
    monkeypatch.setattr(payroll_admin_routes, "estate_id", lambda: "estate-1")
    app = FastAPI()
    app.include_router(payroll_admin_routes.router)
    app.dependency_overrides[authorize_admin] = lambda: None
    response = TestClient(app).post("/api/v1/admin/owner-labor/owner-1/approve", json={})
    assert response.status_code == 409
    assert response.json() == {"detail": "Reload review"}
