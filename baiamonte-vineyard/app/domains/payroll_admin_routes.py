"""Administrative labor review, reconciliation, payment, and timesheet routes."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_admin, worker_accounts
from ..config import Settings, get_settings
from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready
from .payroll import (
    PayrollDomainError,
    normalize_contractor_job_lines,
    record_labor_invoice_payment,
    record_labor_payment_batch,
    review_worker_labor_record,
    worker_payment_batch_key,
)
from .payroll_presence import PresenceValidationError, labor_identity_links, timesheet_presence
from ..intelligence import home_assistant_people
from ..service import new_id, season_for_year


router = APIRouter(prefix="/api/v1/admin", tags=["payroll-admin"])


def _timesheet_presence(worker: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return timesheet_presence(worker, entries)
    except PresenceValidationError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/worker-labor/{record_id}/review", dependencies=[Depends(authorize_admin)])
def review_worker_labor(record_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return review_worker_labor_record(record_id, payload, actor, estate_id())
    except PayrollDomainError as error:
        raise HTTPException(error.status_code, str(error)) from error


@router.post("/worker-labor/{record_id}/pay", dependencies=[Depends(authorize_admin)])
def pay_worker_labor(record_id: str, request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Worker payment record not found")
    if row.get("approval_status") != "approved":
        raise HTTPException(409, "Approve and lock the labor record before payment")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return record_labor_invoice_payment(row, payload or {}, actor, estate_id())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/labor-payment-batches/pay", dependencies=[Depends(authorize_admin)])
def pay_worker_labor_batch(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    record_ids = list(dict.fromkeys(str(value).strip() for value in (payload.get("record_ids") or []) if str(value).strip()))
    if not record_ids or len(record_ids) > 200:
        raise HTTPException(422, "Choose between 1 and 200 payment records")
    placeholders = ",".join(["%s"] * len(record_ids))
    rows = fetch_all(f"SELECT * FROM labor_entries WHERE estate_id=%s AND id IN ({placeholders})", (estate_id(), *record_ids))
    if len(rows) != len(record_ids):
        raise HTTPException(404, "One or more payment records were not found")
    if any(row.get("approval_status") != "approved" for row in rows):
        raise HTTPException(409, "Every record in the timesheet must be approved before payment")
    if any(row.get("payment_status") == "part_paid" for row in rows):
        raise HTTPException(409, "Finish partially paid invoices individually so each deposit remains allocated correctly")
    if any(row.get("payment_status") == "verification_needed" for row in rows):
        raise HTTPException(409, "Resolve every verification hold before paying the timesheet")
    batch_keys = {worker_payment_batch_key(row) for row in rows}
    workers = {str(row.get("person_or_crew") or "").strip().casefold() for row in rows}
    if len(batch_keys) != 1 or len(workers) != 1:
        raise HTTPException(409, "The selected records do not belong to one employee timesheet")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return record_labor_payment_batch(rows, record_ids, next(iter(batch_keys)), actor, estate_id())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/worker-labor/{record_id}/presence", dependencies=[Depends(authorize_admin)])
def worker_labor_presence(record_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s AND worker_username IS NOT NULL", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Worker submission not found")
    return json_ready(_timesheet_presence(str(row.get("person_or_crew") or ""), [{"work_date": row.get("work_date"), "hours": row.get("regular_hours")}]))


@router.patch("/labor/{record_id}", dependencies=[Depends(authorize_admin)])
def update_labor_record(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed = {
        "work_date", "person_or_crew", "regular_hours", "overtime_hours",
        "hourly_rate_eur", "work_performed", "notes",
        "role", "work_category", "payroll_scope", "entry_source",
        "expense_amount_eur", "other_cost_eur", "expense_category",
        "expense_notes",
    }
    resolve_verification = payload.get("resolve_verification") is True
    values = {key: payload.get(key) for key in allowed if key in payload}
    job_lines = payload.get("job_lines") if "job_lines" in payload else None
    if job_lines is not None:
        try:
            values.update(normalize_contractor_job_lines(payload))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    if not values and not resolve_verification:
        raise HTTPException(422, "Enter a labor correction")
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Labor entry not found")
    if "work_date" in values:
        try:
            values["work_date"] = date.fromisoformat(str(values["work_date"])).isoformat()
        except ValueError as error:
            raise HTTPException(422, "Use a valid work date") from error
    if "person_or_crew" in values and not str(values["person_or_crew"] or "").strip():
        raise HTTPException(422, "Worker name is required")
    for key in ("regular_hours", "overtime_hours"):
        if key in values:
            values[key] = float(values[key] or 0)
            if values[key] < 0 or (job_lines is None and values[key] > 24):
                raise HTTPException(422, "Hours must be between 0 and 24")
    if "hourly_rate_eur" in values:
        values["hourly_rate_eur"] = None if values["hourly_rate_eur"] in (None, "") else float(values["hourly_rate_eur"])
        if values["hourly_rate_eur"] is not None and values["hourly_rate_eur"] < 0:
            raise HTTPException(422, "Hourly rate cannot be negative")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s FOR UPDATE", (record_id, estate_id()))
        locked = cursor.fetchone()
        if not locked:
            raise HTTPException(404, "Labor entry not found")
        cursor.execute(
            "SELECT COALESCE(SUM(amount_eur),0) amount_paid FROM labor_invoice_payments WHERE estate_id=%s AND labor_entry_id=%s AND voided_at IS NULL",
            (estate_id(), record_id),
        )
        amount_paid = float((cursor.fetchone() or {}).get("amount_paid") or 0)
        protected_fields = {
            "work_date", "person_or_crew", "regular_hours", "overtime_hours", "hourly_rate_eur",
            "labor_cost_eur", "other_cost_eur", "expense_amount_eur", "expense_category",
            "expense_notes", "work_category", "payroll_scope", "entry_source",
        }
        if (amount_paid > 0 or locked.get("payment_status") in {"part_paid", "paid"}) and protected_fields.intersection(values):
            raise HTTPException(409, "This invoice already has a payment. Financial and ownership fields are locked; only notes and description may be corrected.")
        merged = {**locked, **values}
        if job_lines is None and merged.get("hourly_rate_eur") is not None:
            values["labor_cost_eur"] = round((float(merged.get("regular_hours") or 0) + float(merged.get("overtime_hours") or 0)) * float(merged["hourly_rate_eur"]), 2)
        if resolve_verification:
            if locked.get("approval_status") != "approved" or locked.get("payment_status") != "verification_needed":
                raise HTTPException(409, "Only an approved verification hold can be released")
            if amount_paid > 0:
                raise HTTPException(409, "This held invoice already has payment history and needs ledger reconciliation before release")
            invoice_total = float(values.get("labor_cost_eur", merged.get("labor_cost_eur")) or 0) + float(values.get("other_cost_eur", merged.get("other_cost_eur")) or 0)
            if invoice_total <= 0:
                raise HTTPException(422, "Enter and verify a positive invoice amount before releasing payment")
            values["payment_status"] = "unpaid"
            values["paid_at"] = None
        assignments = ",".join(f"{key}=%s" for key in values)
        if resolve_verification:
            assignments += ",approved_by=COALESCE(NULLIF(approved_by,''),%s),locked_at=COALESCE(locked_at,NOW(6))"
            params = (*values.values(), actor, record_id, estate_id())
        else:
            params = (*values.values(), record_id, estate_id())
        cursor.execute(f"UPDATE labor_entries SET {assignments} WHERE id=%s AND estate_id=%s", params)
        audit(cursor, "resolve_verification" if resolve_verification else "correct", "labor", record_id, {"before": json_ready(locked), "changes": values, "amount_paid_eur": amount_paid}, actor)
    return {"saved": True, "id": record_id, "labor_cost_eur": values.get("labor_cost_eur"), "payment_status": values.get("payment_status", row.get("payment_status"))}


@router.delete("/labor/{record_id}", dependencies=[Depends(authorize_admin)])
def delete_labor_record(record_id: str, request: Request) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Labor entry not found")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("SELECT COUNT(*) payment_count FROM labor_invoice_payments WHERE estate_id=%s AND labor_entry_id=%s", (estate_id(), record_id))
        if int((cursor.fetchone() or {}).get("payment_count") or 0) or row.get("payment_status") in {"part_paid", "paid"}:
            raise HTTPException(409, "This labor record has payment history and cannot be deleted. Retain it for audit and correct its notes instead.")
        audit(cursor, "delete", "labor", record_id, {"before": json_ready(row)}, actor)
        cursor.execute("DELETE FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    return {"deleted": True, "id": record_id}


@router.post("/labor/reassign-worker", dependencies=[Depends(authorize_admin)])
def reassign_unidentified_worker(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    current_name = str(payload.get("current_name") or "").strip()
    new_name = str(payload.get("new_name") or "").strip()
    if not current_name.casefold().startswith("unidentified part-time worker"):
        raise HTTPException(422, "Only unidentified worker records can be reassigned here")
    if not new_name or new_name.casefold().startswith("unidentified part-time worker"):
        raise HTTPException(422, "Enter the worker's real name")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("UPDATE labor_entries SET person_or_crew=%s,approved_by=%s WHERE estate_id=%s AND LOWER(person_or_crew)=LOWER(%s)", (new_name[:200], actor, estate_id(), current_name))
        changed = cursor.rowcount
        audit(cursor, "reassign_worker", "labor_worker", current_name, {"from": current_name, "to": new_name[:200], "records_updated": changed}, actor)
    if not changed:
        raise HTTPException(404, "No labor records were found for that unidentified worker")
    return {"saved": True, "from": current_name, "to": new_name[:200], "records_updated": changed}


@router.put("/labor-identities/{worker_key}/home-assistant-person", dependencies=[Depends(authorize_admin)])
def link_labor_identity(worker_key: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker_key = worker_key.strip()
    person_entity = str(payload.get("person_entity") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", worker_key):
        raise HTTPException(422, "Choose a valid payroll worker")
    if worker_key.startswith("seasonal-worker-"):
        raise HTTPException(422, "Identify the historical worker before linking a Home Assistant Person")
    ha_person = next((item for item in home_assistant_people() if item.get("entity_id") == person_entity), None)
    if not ha_person:
        raise HTTPException(422, "Choose an existing Home Assistant Person")
    links = labor_identity_links()
    conflict = next((key for key, entity in links.items() if key != worker_key and entity == person_entity), None)
    if conflict:
        raise HTTPException(409, "That Home Assistant Person is already linked to another payroll worker")
    links[worker_key] = person_entity
    actor = request.headers.get("X-Remote-User-Name") or "api"
    attributes = ha_person.get("attributes") or {}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'labor_identity_links',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(links, ensure_ascii=False)),
        )
        audit(cursor, "link", "labor_identity", worker_key, {"worker_key": worker_key, "person_entity": person_entity, "home_assistant_name": attributes.get("friendly_name")}, actor)
    return {"saved": True, "worker_key": worker_key, "person_entity": person_entity, "name": attributes.get("friendly_name") or person_entity.removeprefix("person.").replace("_", " ").title()}


@router.post("/labor/monthly", dependencies=[Depends(authorize_admin)])
def save_monthly_labor_total(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker = str(payload.get("worker") or "").strip()
    month_text = str(payload.get("month") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    if not worker:
        raise HTTPException(422, "Worker name is required")
    try:
        month_start = date.fromisoformat(f"{month_text}-01")
        hours = float(payload.get("hours"))
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid month and total hours") from error
    if hours <= 0 or hours > 744:
        raise HTTPException(422, "Monthly hours must be greater than 0 and no more than 744")
    rate_value = payload.get("hourly_rate_eur")
    rate = None if rate_value in (None, "") else float(rate_value)
    if rate is None and "giancarlo" in worker.casefold():
        rate = 10.0
    if rate is not None and rate < 0:
        raise HTTPException(422, "Hourly rate cannot be negative")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    source_id = f"MONTHLY-{worker.casefold().replace(' ', '-')}-{month_text}"
    cost = round(hours * rate, 2) if rate is not None else None
    existing = fetch_one("SELECT * FROM labor_entries WHERE estate_id=%s AND source_labor_id=%s LIMIT 1", (estate_id(), source_id))
    record_id = existing.get("id") if existing else new_id()
    values = {"work_date": month_start, "shift_label": f"Monthly total {month_text}", "person_or_crew": worker, "regular_hours": hours, "hourly_rate_eur": rate, "labor_cost_eur": cost, "approved_by": actor, "notes": notes or f"Monthly attendance total for {month_text}; daily dates were not reported."}
    with transaction() as (_, cursor):
        if existing:
            cursor.execute("UPDATE labor_entries SET work_date=%s,shift_label=%s,person_or_crew=%s,regular_hours=%s,overtime_hours=0,hourly_rate_eur=%s,labor_cost_eur=%s,approved_by=%s,notes=%s WHERE id=%s AND estate_id=%s", (*values.values(), record_id, estate_id()))
            audit(cursor, "correct", "monthly_labor", record_id, {"before": json_ready(existing), "changes": values}, actor)
        else:
            cursor.execute("INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,regular_hours,overtime_hours,hourly_rate_eur,labor_cost_eur,approved_by,payment_status,payroll_scope,entry_source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,'Estate manager',%s,0,%s,%s,%s,'unknown','part_time','monthly_total',%s)", (record_id, estate_id(), season_for_year(month_start.year), source_id, *values.values()))
            audit(cursor, "create", "monthly_labor", record_id, values, actor)
    return {"saved": True, "id": record_id, "worker": worker, "month": month_text, "hours": hours, "updated": bool(existing)}


def _normalize_timesheet_expenses(raw_expenses: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_expenses, list):
        raise HTTPException(422, "Reimbursable expenses must be entered as separate rows")
    normalized = []
    allowed_categories = {"contractor_job", "water_delivery", "equipment", "transport", "materials", "fuel", "tools", "delivery", "service", "other"}
    for raw in raw_expenses:
        if not isinstance(raw, dict):
            raise HTTPException(422, "Every reimbursable expense must be a separate row")
        amount_value = raw.get("amount_eur")
        if amount_value in (None, ""):
            continue
        try:
            amount = round(float(amount_value), 2)
            expense_date = date.fromisoformat(str(raw.get("expense_date") or raw.get("date") or "")[:10])
        except (TypeError, ValueError) as error:
            raise HTTPException(422, "Every reimbursable expense needs a valid date and amount") from error
        if expense_date > datetime.now(ZoneInfo("Europe/Rome")).date():
            raise HTTPException(422, "A reimbursable expense cannot be dated in the future")
        if amount <= 0 or amount > 10000:
            raise HTTPException(422, "Each reimbursable expense must be greater than €0 and no more than €10,000")
        category = str(raw.get("category") or "other").strip().casefold()
        if category not in allowed_categories:
            raise HTTPException(422, "Choose a valid reimbursement category")
        description = str(raw.get("description") or raw.get("notes") or "").strip()
        if not description:
            raise HTTPException(422, "Describe each reimbursable expense")
        normalized.append({"expense_date": expense_date.isoformat(), "category": category, "description": description[:500], "amount_eur": amount})
    return normalized


@router.patch("/timesheets/{record_id}", dependencies=[Depends(authorize_admin)])
def save_timesheet_draft(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker, entries = str(payload.get("worker") or "").strip(), payload.get("entries") or []
    if not worker or not isinstance(entries, list):
        raise HTTPException(422, "Enter a worker and day or month lines")
    for row in entries:
        if not isinstance(row, dict):
            raise HTTPException(422, "Every timesheet line must be a day or monthly total")
        period_type = str(row.get("period_type") or "day").strip().casefold()
        if period_type not in {"day", "month"}:
            raise HTTPException(422, "Choose Day or Month total for every timesheet line")
        period_value = row.get("work_month") if period_type == "month" else row.get("work_date") or row.get("date")
        if not str(period_value or "").strip():
            raise HTTPException(422, f"Every {period_type} line needs a valid {period_type}")
        row_worker = str(row.get("person_or_crew") or row.get("worker") or worker).strip()
        if row_worker.casefold() != worker.casefold():
            raise HTTPException(422, "Save and approve one employee at a time; split mixed-worker hours into separate reviews")
    expenses = _normalize_timesheet_expenses(payload.get("expenses") or [])
    draft = {"person_or_crew": worker, "hourly_rate_eur": payload.get("hourly_rate_eur"), "timesheet_entries": entries, "reimbursable_expenses": expenses}
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE intake_items SET extracted_data=%s,review_status='ready_for_review',review_reason=%s WHERE id=%s AND estate_id=%s AND review_status IN ('new','ready_for_review')", (json.dumps(draft, default=str), "Timesheet edited in Operations Control; awaiting approval", record_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Pending timesheet not found")
        audit(cursor, "edit", "timesheet_review", record_id, draft, request.headers.get("X-Remote-User-Name") or "api")
    return {"saved": True, "id": record_id}


@router.post("/timesheets/{record_id}/presence", dependencies=[Depends(authorize_admin)])
def check_timesheet_presence(record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not fetch_one("SELECT id FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id())):
        raise HTTPException(404, "Timesheet not found")
    return json_ready(_timesheet_presence(str(payload.get("worker") or ""), payload.get("entries") or []))


@router.post("/timesheets/{record_id}/approve", dependencies=[Depends(authorize_admin)])
def approve_timesheet(record_id: str, payload: dict[str, Any], request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    item = fetch_one("SELECT * FROM intake_items WHERE id=%s AND estate_id=%s AND review_status IN ('new','ready_for_review')", (record_id, estate_id()))
    if not item:
        raise HTTPException(404, "Pending timesheet not found")
    worker, raw_entries = str(payload.get("worker") or "").strip(), payload.get("entries") or []
    if not worker or not isinstance(raw_entries, list) or not raw_entries:
        raise HTTPException(422, "Enter the worker and at least one day or month line")
    expenses = _normalize_timesheet_expenses(payload.get("expenses") or [])
    rate = None if payload.get("hourly_rate_eur") in (None, "") else float(payload["hourly_rate_eur"])
    if rate is not None and rate < 0:
        raise HTTPException(422, "Hourly rate cannot be negative")
    entries = []
    for row in raw_entries:
        period_type = str(row.get("period_type") or "day").strip().casefold()
        if period_type not in {"day", "month"}:
            raise HTTPException(422, "Choose Day or Month total for every timesheet line")
        try:
            if period_type == "month":
                month_text = str(row.get("work_month") or row.get("month") or "")[:7]
                work_date = date.fromisoformat(f"{month_text}-01")
            else:
                month_text = None
                work_date = date.fromisoformat(str(row.get("work_date") or row.get("date")))
            hours = float(row.get("hours") if row.get("hours") is not None else row.get("regular_hours"))
        except (AttributeError, TypeError, ValueError) as error:
            raise HTTPException(422, "Every timesheet line needs a valid day or month and hours") from error
        maximum = 744 if period_type == "month" else 24
        if hours <= 0 or hours > maximum:
            raise HTTPException(422, f"{'Monthly' if period_type == 'month' else 'Daily'} hours must be greater than 0 and no more than {maximum}")
        entries.append({"period_type": period_type, "work_date": work_date, "work_month": month_text, "hours": hours, "notes": str(row.get("notes") or "").strip() or None})
    entry_keys = [(row["period_type"], row["work_month"] or row["work_date"].isoformat()) for row in entries]
    if len(set(entry_keys)) != len(entry_keys):
        raise HTTPException(422, "Combine duplicate day or month lines before approval")
    seasons = {year: season_for_year(year) for year in {row["work_date"].year for row in entries}}
    presence_rows = [{**row, "work_date": row["work_date"].isoformat()} for row in entries if row["period_type"] == "day"]
    presence = _timesheet_presence(worker, presence_rows)
    if any(row["period_type"] == "month" for row in entries):
        presence["monthly_note"] = "Monthly totals are retained as aggregate attendance; no unsupported daily presence is inferred."
    actor = request.headers.get("X-Remote-User-Name") or "api"
    worker_username = next((username for username, display_name in worker_accounts(settings).items() if display_name.casefold() == worker.casefold()), None)
    inserted, duplicates, expenses_inserted, expense_duplicates = [], [], [], []
    with transaction() as (_, cursor):
        for row in entries:
            if row["period_type"] == "month":
                cursor.execute("SELECT id,COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) hours FROM labor_entries WHERE estate_id=%s AND YEAR(work_date)=%s AND MONTH(work_date)=%s AND LOWER(person_or_crew)=LOWER(%s) AND work_category='monthly_total' ORDER BY id", (estate_id(), row["work_date"].year, row["work_date"].month, worker))
            else:
                cursor.execute("SELECT id,COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) hours FROM labor_entries WHERE estate_id=%s AND work_date=%s AND LOWER(person_or_crew)=LOWER(%s) AND COALESCE(work_category,'')<>'monthly_total' ORDER BY id", (estate_id(), row["work_date"], worker))
            matches = cursor.fetchall() or []
            exact = next((match for match in matches if abs(float(match.get("hours") or 0) - row["hours"]) < .001), None)
            if exact:
                duplicates.append({"period_type": row["period_type"], "work_date": row["work_date"].isoformat(), "work_month": row["work_month"], "hours": row["hours"], "existing_id": exact["id"]})
                continue
            period_key = row["work_month"] if row["period_type"] == "month" else row["work_date"].isoformat()
            labor_id, source_id = new_id(), f"TIMESHEET-{record_id[:8]}-{row['period_type'].upper()}-{period_key}"
            cost = round(row["hours"] * rate, 2) if rate is not None else None
            work_category = "monthly_total" if row["period_type"] == "month" else None
            shift_label = f"Monthly total {row['work_month']}" if row["period_type"] == "month" else None
            default_note = f"Monthly attendance total for {row['work_month']}; daily dates were not reported." if row["period_type"] == "month" else f"Approved from {item.get('source') or 'incoming'} timesheet {record_id}"
            cursor.execute(
                "INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,work_category,regular_hours,hourly_rate_eur,labor_cost_eur,approved_by,payment_status,payroll_scope,entry_source,notes,worker_username) VALUES (%s,%s,%s,%s,%s,%s,%s,'Contractor',%s,%s,%s,%s,%s,'unpaid','contractor',%s,%s,%s)",
                (labor_id, estate_id(), seasons[row["work_date"].year], source_id, row["work_date"], shift_label, worker, work_category, row["hours"], rate, cost, actor, item.get("source") or "timesheet", row["notes"] or default_note, worker_username),
            )
            inserted.append({"id": labor_id, "period_type": row["period_type"], "work_date": row["work_date"].isoformat(), "work_month": row["work_month"], "hours": row["hours"]})
        for index, expense in enumerate(expenses, start=1):
            source_id = f"{record_id}:expense:{index}"
            cursor.execute("SELECT id FROM labor_entries WHERE estate_id=%s AND source_labor_id=%s LIMIT 1", (estate_id(), source_id))
            existing_expense = cursor.fetchone()
            if existing_expense:
                expense_duplicates.append({"id": existing_expense["id"], **expense})
                continue
            expense_id = new_id()
            expense_date = date.fromisoformat(expense["expense_date"])
            cursor.execute(
                "INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,person_or_crew,role,work_category,work_performed,regular_hours,overtime_hours,labor_cost_eur,other_cost_eur,expense_amount_eur,expense_category,expense_notes,approved_by,approval_status,payment_status,payroll_scope,entry_source,notes,worker_username) VALUES (%s,%s,%s,%s,%s,%s,'Contractor','reimbursable_expense',%s,0,0,0,%s,%s,%s,%s,%s,'approved','unpaid','contractor',%s,%s,%s)",
                (expense_id, estate_id(), season_for_year(expense_date.year), source_id, expense_date, worker, expense["description"], expense["amount_eur"], expense["amount_eur"], expense["category"], expense["description"], actor, item.get("source") or "timesheet", f"Approved reimbursement from timesheet {record_id}", worker_username),
            )
            expenses_inserted.append({"id": expense_id, **expense})
        review = {"person_or_crew": worker, "hourly_rate_eur": rate, "timesheet_entries": [{**row, "work_date": row["work_date"].isoformat()} for row in entries], "reimbursable_expenses": expenses}
        cursor.execute("UPDATE intake_items SET extracted_data=%s,review_status='approved',review_reason=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (json.dumps(review, default=str), f"Timesheet approved: {len(inserted)} work rows and {len(expenses_inserted)} reimbursements added", actor, record_id, estate_id()))
        audit(cursor, "approve", "timesheet_review", record_id, {"worker": worker, "inserted": inserted, "duplicates": duplicates, "expenses_inserted": expenses_inserted, "expense_duplicates": expense_duplicates, "presence_evidence": presence}, actor)
    labor_total = None if rate is None else round(sum(row["hours"] for row in entries) * rate, 2)
    reimbursement_total = round(sum(row["amount_eur"] for row in expenses_inserted), 2)
    return {"approved": True, "inserted": inserted, "duplicates": duplicates, "expenses_inserted": expenses_inserted, "expense_duplicates": expense_duplicates, "labor_total_eur": labor_total, "reimbursement_total_eur": reimbursement_total, "total_payable_eur": None if labor_total is None else round(labor_total + reimbursement_total, 2), "presence_evidence": presence, "total_hours": sum(row["hours"] for row in entries)}
