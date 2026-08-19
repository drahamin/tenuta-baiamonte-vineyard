from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.domains import payroll


ROOT = Path(__file__).resolve().parents[1]


class InvoiceCursor:
    def __init__(self, locked, paid=Decimal("0.00")):
        self.locked = locked
        self.paid = paid
        self.result = None
        self.rowcount = 0
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith("SELECT * FROM labor_entries"):
            self.result = self.locked
        elif sql.startswith("SELECT COALESCE(SUM(amount_eur)"):
            self.result = {"amount_paid": self.paid}
        elif sql.startswith("UPDATE labor_entries SET payment_status"):
            self.rowcount = 1
        return 1

    def fetchone(self):
        return self.result


def transaction_for(cursor):
    @contextmanager
    def fake_transaction():
        yield None, cursor

    return fake_transaction


def approved_invoice(**overrides):
    row = {
        "id": "invoice-1",
        "approval_status": "approved",
        "payment_status": "unpaid",
        "labor_cost_eur": Decimal("100.00"),
        "other_cost_eur": Decimal("0.00"),
        "paid_at": None,
    }
    row.update(overrides)
    return row


def test_partial_payment_posts_ledger_and_status_atomically(monkeypatch):
    cursor = InvoiceCursor(approved_invoice())
    monkeypatch.setattr(payroll, "transaction", transaction_for(cursor))
    monkeypatch.setattr(payroll, "new_id", lambda: "payment-1")
    monkeypatch.setattr(payroll, "audit", lambda *args, **kwargs: None)

    result = payroll.record_labor_invoice_payment(
        {"id": "invoice-1"},
        {"amount_eur": "40.00", "payment_date": "2026-08-19", "payment_type": "deposit"},
        "admin",
        "estate-1",
    )

    assert result["payment_status"] == "part_paid"
    assert result["amount_paid_eur"] == Decimal("40.00")
    assert result["balance_due_eur"] == Decimal("60.00")
    assert any(sql.startswith("INSERT INTO labor_invoice_payments") for sql, _ in cursor.executed)
    update = next(params for sql, params in cursor.executed if sql.startswith("UPDATE labor_entries SET payment_status"))
    assert update[0] == "part_paid"


def test_verification_hold_cannot_be_paid(monkeypatch):
    cursor = InvoiceCursor(approved_invoice(payment_status="verification_needed"))
    monkeypatch.setattr(payroll, "transaction", transaction_for(cursor))

    with pytest.raises(ValueError, match="Resolve the verification hold"):
        payroll.record_labor_invoice_payment(
            {"id": "invoice-1"}, {"amount_eur": "100.00"}, "admin", "estate-1"
        )

    assert not any(sql.startswith("INSERT INTO labor_invoice_payments") for sql, _ in cursor.executed)


def test_zero_value_invoice_cannot_be_paid(monkeypatch):
    cursor = InvoiceCursor(approved_invoice(labor_cost_eur=0, other_cost_eur=0))
    monkeypatch.setattr(payroll, "transaction", transaction_for(cursor))

    with pytest.raises(ValueError, match="positive amount"):
        payroll.record_labor_invoice_payment(
            {"id": "invoice-1"}, {}, "admin", "estate-1"
        )


def test_payroll_summary_uses_ledger_and_separates_holds(monkeypatch):
    captured = {}

    def fake_fetch_one(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return {"ready_to_pay": 440, "verification_hold_eur": 1640, "payments_recorded": 5855}

    monkeypatch.setattr(payroll, "fetch_one", fake_fetch_one)
    result = payroll.labor_payment_summary("estate-1", 2026)

    assert result["ready_to_pay"] == 440
    assert "invoice.payment_status IN ('unknown','unpaid','part_paid')" in captured["sql"]
    assert "invoice.payment_status='verification_needed'" in captured["sql"]
    assert "SUM(invoice.amount_paid)" in captured["sql"]
    assert captured["params"] == (2026, 2026, 2026, 2026, "estate-1")


def test_admin_controls_protect_paid_records_and_surface_holds():
    backend = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    frontend = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    payroll_ui = (ROOT / "app" / "static" / "assets" / "payroll.js").read_text(encoding="utf-8")
    migration = (ROOT / "db" / "migrations" / "057_payroll_payment_integrity.sql").read_text(encoding="utf-8")

    assert '"worker_payment_holds": worker_payment_holds' in backend
    assert '"payroll": payroll_summary(date.today().year)' in backend
    assert "Financial and ownership fields are locked" in backend
    assert "has payment history and cannot be deleted" in backend
    assert "worker-verification-queue" in frontend
    assert "Recorded payments" in frontend
    assert "resolve_verification" in payroll_ui
    assert "WHERE amount_eur<=0 AND voided_at IS NULL" in migration
    assert "CHECK (amount_eur > 0 OR voided_at IS NOT NULL)" in migration
