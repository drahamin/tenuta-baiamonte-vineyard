from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, new_id


def consolidate_labor_people(
    people: list[dict[str, Any]], canonical_keys: set[str]
) -> list[dict[str, Any]]:
    """Merge seeded workers with authoritative Home Assistant people."""
    normalized_canonical_keys = sorted(
        ((re.sub(r"\W+", "_", str(key).casefold()).strip("_"), key) for key in canonical_keys),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    consolidated: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for person in people:
        raw_key = re.sub(r"\W+", "_", str(person.get("key") or "").casefold()).strip("_")
        identity = next(
            (canonical_key for normalized_key, canonical_key in normalized_canonical_keys
             if raw_key == normalized_key or raw_key.startswith(f"{normalized_key}_")),
            re.sub(r"\W+", " ", str(person.get("name") or raw_key).casefold()).strip(),
        )
        existing = consolidated.get(identity)
        if not existing:
            consolidated[identity] = dict(person)
            ordered_keys.append(identity)
            continue
        if person.get("person_entity"):
            existing["name"] = person.get("name") or existing.get("name")
            existing["person_entity"] = person["person_entity"]
            if person.get("gps_entity"):
                existing["gps_entity"] = person["gps_entity"]
        for field in ("role", "payment_schedule"):
            if person.get(field) and not existing.get(field):
                existing[field] = person[field]
        existing["name_aliases"] = tuple(dict.fromkeys((*existing.get("name_aliases", ()), *person.get("name_aliases", ()))))
        existing["camera_aliases"] = tuple(dict.fromkeys((*existing.get("camera_aliases", ()), *person.get("camera_aliases", ()))))
    return [consolidated[key] for key in ordered_keys]


def worker_pay_due(name: str, work_day: date) -> date | None:
    if "giancarlo" not in name.casefold():
        return None
    next_month = (work_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month.replace(day=15)


def worker_payment_batch_key(row: dict[str, Any]) -> str:
    """Keep records from one reviewed source together through payment."""
    source_id = str(row.get("source_labor_id") or "")
    timesheet_match = re.match(r"^TIMESHEET-([^-]+)-", source_id, re.IGNORECASE)
    if timesheet_match:
        return f"timesheet:{timesheet_match.group(1).casefold()}"
    expense_match = re.match(r"^([^:]+):expense:\d+$", source_id, re.IGNORECASE)
    if expense_match:
        return f"timesheet:{expense_match.group(1)[:8].casefold()}"
    notes_match = re.search(r"timesheet\s+([0-9a-f-]{8,36})", str(row.get("notes") or ""), re.IGNORECASE)
    if notes_match:
        return f"timesheet:{notes_match.group(1)[:8].casefold()}"
    worker = re.sub(
        r"[^a-z0-9]+", "-",
        str(row.get("person_or_crew") or row.get("worker_username") or "worker").casefold(),
    ).strip("-") or "worker"
    work_month = str(row.get("work_date") or "")[:7]
    if re.fullmatch(r"\d{4}-\d{2}", work_month):
        return f"period:{worker}:{work_month}"
    return f"record:{row.get('id')}"


def attach_labor_invoice_payments(submissions: list[dict[str, Any]], estate: str) -> None:
    """Attach audited payment history and balances to open labor invoices."""
    record_ids = [str(row["id"]) for row in submissions]
    payments: list[dict[str, Any]] = []
    if record_ids:
        placeholders = ",".join(["%s"] * len(record_ids))
        payments = fetch_all(
            f"SELECT id,labor_entry_id,amount_eur,payment_date,payment_type,payment_method,payment_reference,notes,created_by,created_at "
            f"FROM labor_invoice_payments WHERE estate_id=%s AND voided_at IS NULL AND labor_entry_id IN ({placeholders}) "
            "ORDER BY payment_date,created_at",
            (estate, *record_ids),
        )
    by_entry: dict[str, list[dict[str, Any]]] = {}
    for payment in payments:
        by_entry.setdefault(str(payment["labor_entry_id"]), []).append(payment)
    for submission in submissions:
        submission["payments"] = by_entry.get(str(submission["id"]), [])
        invoice_total = round(float(submission.get("labor_cost_eur") or 0) + float(submission.get("other_cost_eur") or 0), 2)
        amount_paid = round(sum(float(payment.get("amount_eur") or 0) for payment in submission["payments"]), 2)
        submission["invoice_total_eur"] = invoice_total
        submission["amount_paid_eur"] = amount_paid
        submission["balance_due_eur"] = round(max(0, invoice_total - amount_paid), 2)


def worker_payment_totals(estate: str, username: str, worker_name: str) -> dict[str, Any]:
    """Return actual paid and remaining balances, including partial payments."""
    return fetch_one(
        "SELECT "
        "COALESCE(SUM(CASE WHEN YEAR(l.work_date)=YEAR(CURDATE()) AND l.payment_status='paid' THEN COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0) WHEN YEAR(l.work_date)=YEAR(CURDATE()) THEN COALESCE(p.amount_paid,0) ELSE 0 END),0) year_paid_pay,"
        "COALESCE(SUM(CASE WHEN YEAR(l.work_date)=YEAR(CURDATE()) AND l.payment_status IN ('unpaid','part_paid') THEN GREATEST(COALESCE(l.labor_cost_eur,0)+COALESCE(l.other_cost_eur,0)-COALESCE(p.amount_paid,0),0) ELSE 0 END),0) year_due_pay "
        "FROM labor_entries l LEFT JOIN (SELECT estate_id,labor_entry_id,SUM(amount_eur) amount_paid FROM labor_invoice_payments WHERE voided_at IS NULL GROUP BY estate_id,labor_entry_id) p ON p.estate_id=l.estate_id AND p.labor_entry_id=l.id "
        "WHERE l.estate_id=%s AND (l.worker_username=%s OR (l.worker_username IS NULL AND LOWER(l.person_or_crew)=LOWER(%s))) AND l.approval_status='approved'",
        (estate, username, worker_name),
    ) or {}


def record_labor_invoice_payment(row: dict[str, Any], payload: dict[str, Any], actor: str, estate: str) -> dict[str, Any]:
    """Record one deposit/payment and update the invoice balance atomically."""
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    with transaction() as (_, cursor):
        cursor.execute("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s FOR UPDATE", (row["id"], estate))
        locked = cursor.fetchone()
        if not locked or locked.get("approval_status") != "approved":
            raise ValueError("Approve and lock the labor record before payment")
        total = (Decimal(str(locked.get("labor_cost_eur") or 0)) + Decimal(str(locked.get("other_cost_eur") or 0))).quantize(Decimal("0.01"))
        cursor.execute("SELECT COALESCE(SUM(amount_eur),0) amount_paid FROM labor_invoice_payments WHERE estate_id=%s AND labor_entry_id=%s AND voided_at IS NULL", (estate, row["id"]))
        amount_paid = Decimal(str((cursor.fetchone() or {}).get("amount_paid") or 0)).quantize(Decimal("0.01"))
        remaining = max(Decimal("0.00"), total - amount_paid)
        if remaining == 0 or locked.get("payment_status") == "paid":
            return {"saved": True, "id": row["id"], "payment_status": "paid", "paid_at": locked.get("paid_at"), "already_paid": True, "amount_paid_eur": amount_paid, "balance_due_eur": 0}
        try:
            raw_amount = payload.get("amount_eur")
            amount = remaining if raw_amount in (None, "") else Decimal(str(raw_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Enter a valid payment amount") from error
        if amount <= 0 or amount > remaining:
            raise ValueError(f"Enter a payment between €0.01 and €{remaining:.2f}")
        try:
            payment_date = date.fromisoformat(str(payload.get("payment_date") or now.date()))
        except ValueError as error:
            raise ValueError("Enter a valid payment date") from error
        payment_type = str(payload.get("payment_type") or ("payment" if amount == remaining else "deposit")).casefold()
        if payment_type not in {"deposit", "payment"}:
            raise ValueError("Choose deposit or payment")
        new_paid, payment_id = amount_paid + amount, new_id()
        completed = new_paid >= total
        cursor.execute(
            "INSERT INTO labor_invoice_payments (id,estate_id,labor_entry_id,amount_eur,payment_date,payment_type,payment_method,payment_reference,notes,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (payment_id, estate, row["id"], amount, payment_date, payment_type, str(payload.get("payment_method") or "").strip()[:80] or None, str(payload.get("payment_reference") or "").strip()[:180] or None, str(payload.get("notes") or "").strip()[:2000] or None, actor),
        )
        cursor.execute(
            "UPDATE labor_entries SET payment_status=%s,paid_at=%s,pay_due_date=COALESCE(pay_due_date,%s) WHERE id=%s AND estate_id=%s AND approval_status='approved'",
            ("paid" if completed else "part_paid", now if completed else None, payment_date, row["id"], estate),
        )
        balance = max(Decimal("0.00"), total - new_paid)
        audit(cursor, "record_payment", "labor", str(row["id"]), {"payment_id": payment_id, "amount_eur": amount, "payment_date": payment_date, "payment_type": payment_type, "payment_status": "paid" if completed else "part_paid", "amount_paid_eur": new_paid, "balance_due_eur": balance}, actor)
    return {"saved": True, "id": row["id"], "payment_id": payment_id, "payment_status": "paid" if completed else "part_paid", "paid_at": now if completed else None, "amount_paid_eur": new_paid, "balance_due_eur": balance}


def normalize_contractor_job_lines(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate fixed-price contractor lines and map them to one payable record."""
    lines = payload.get("job_lines")
    if not isinstance(lines, list) or not lines or len(lines) > 50:
        raise ValueError("Add between 1 and 50 contractor job lines")
    cleaned: list[dict[str, Any]] = []
    dates: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Each contractor job must be a line item")
        description = str(line.get("description") or "").strip()
        if not description:
            raise ValueError("Each contractor job needs a description")
        try:
            amount = round(float(line.get("amount_eur") or 0), 2)
        except (TypeError, ValueError) as error:
            raise ValueError("Each contractor job needs a valid amount") from error
        if amount <= 0 or amount > 100000:
            raise ValueError("Contractor job amounts must be between €0.01 and €100,000")
        line_date = str(line.get("date") or "").strip()
        if line_date:
            try:
                line_date = date.fromisoformat(line_date).isoformat()
            except ValueError as error:
                raise ValueError("Use a valid date on each dated contractor job") from error
            dates.append(line_date)
        cleaned.append({"date": line_date or None, "description": description[:500], "amount_eur": amount})
    total = round(sum(line["amount_eur"] for line in cleaned), 2)
    note = str(payload.get("notes") or "").strip()
    return {
        "work_date": max(dates) if dates else date.today().isoformat(),
        "regular_hours": 0, "overtime_hours": 0, "hourly_rate_eur": None,
        "labor_cost_eur": 0, "other_cost_eur": total, "expense_amount_eur": total,
        "expense_category": "contractor_job",
        "expense_notes": json.dumps({"version": 1, "kind": "contractor_job_lines", "job_lines": cleaned, "note": note or None}, ensure_ascii=False),
        "work_category": "one_off_charge", "entry_source": "manual_job", "payroll_scope": "contractor",
        "work_performed": str(payload.get("work_performed") or "Contractor services").strip()[:500],
    }
