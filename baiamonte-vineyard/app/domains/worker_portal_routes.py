"""Private worker portal, time submission, expenses, and supporting photos."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..access import authorize_worker, people_profiles, profile_access_level, request_username, worker_accounts
from ..config import Settings, get_settings
from ..db import fetch_all, fetch_one, transaction
from ..display_data import weather_context_payload
from ..service import audit, estate_id, json_ready, new_id, season_for_year
from .payroll import worker_pay_due, worker_payment_totals
from .people_roles import worker_profile
from .attachments import MAX_ATTACHMENT_BYTES, store_attachment
from .water_delivery_tracking import submit_water_delivery_claim, water_delivery_summary


router = APIRouter(tags=["worker-portal"])


def _worker_identity(request: Request, settings: Settings) -> tuple[str, str]:
    username = request_username(request)
    workers = worker_accounts(settings)
    name = workers.get(username)
    if not name and profile_access_level(username) in {"worker", "contractor"}:
        name = (request.headers.get("X-Remote-User-Display-Name") or username).strip()
    if not name:
        raise HTTPException(403, "Worker account is not assigned")
    return username, name


def _worker_labor_row(record_id: str, username: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s AND worker_username=%s",
        (record_id, estate_id(), username),
    )
    if not row:
        raise HTTPException(404, "Work record not found")
    return row


@router.get("/api/v1/worker-portal", dependencies=[Depends(authorize_worker)])
def worker_portal(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    person_entity, profile = next(
        ((entity, saved) for entity, saved in people_profiles().items()
         if str(saved.get("username") or "").strip().casefold() == username),
        (None, {}),
    )
    portal_mode = "contractor" if profile_access_level(username) == "contractor" else "worker"
    active = fetch_one(
        "SELECT * FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_in_at IS NOT NULL AND clock_out_at IS NULL "
        "AND approval_status='draft' ORDER BY clock_in_at DESC LIMIT 1",
        (estate_id(), username),
    )
    pending = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND l.worker_username=%s AND l.approval_status IN ('draft','submitted','rejected') "
        "ORDER BY COALESCE(l.clock_in_at,CAST(l.work_date AS DATETIME)) DESC LIMIT 40",
        (estate_id(), username),
    )
    history = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND (l.worker_username=%s OR (l.worker_username IS NULL AND LOWER(l.person_or_crew)=LOWER(%s))) "
        "AND l.approval_status='approved' ORDER BY l.work_date DESC,l.id DESC LIMIT 120",
        (estate_id(), username, worker_name),
    )
    totals = fetch_one(
        "SELECT COALESCE(SUM(regular_hours+overtime_hours),0) total_hours,COALESCE(SUM(COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0)),0) total_pay,"
        "COALESCE(SUM(CASE WHEN work_date=CURDATE() THEN regular_hours+overtime_hours ELSE 0 END),0) today_approved_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND MONTH(work_date)=MONTH(CURDATE()) THEN regular_hours+overtime_hours ELSE 0 END),0) month_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN regular_hours+overtime_hours ELSE 0 END),0) year_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_pay,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND payment_status='paid' THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_paid_pay,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND payment_status='unpaid' THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_due_pay,"
        "COUNT(DISTINCT CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN work_date END) year_days "
        "FROM labor_entries WHERE estate_id=%s AND (worker_username=%s OR (worker_username IS NULL AND LOWER(person_or_crew)=LOWER(%s))) AND approval_status='approved'",
        (estate_id(), username, worker_name),
    ) or {}
    queue_totals = fetch_one(
        "SELECT COALESCE(SUM(CASE WHEN work_date=CURDATE() AND clock_out_at IS NOT NULL THEN regular_hours+overtime_hours ELSE 0 END),0) today_submitted_hours,"
        "COALESCE(SUM(CASE WHEN approval_status IN ('submitted','rejected') THEN regular_hours+overtime_hours ELSE 0 END),0) pending_hours,"
        "COALESCE(SUM(CASE WHEN approval_status IN ('submitted','rejected') THEN expense_amount_eur ELSE 0 END),0) pending_charges_eur,"
        "SUM(approval_status IN ('submitted','rejected')) pending_entries "
        "FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND approval_status IN ('draft','submitted','rejected')",
        (estate_id(), username),
    ) or {}
    totals.update(queue_totals)
    totals.update(worker_payment_totals(estate_id(), username, worker_name))
    work = fetch_all(
        "SELECT id,title,due_date,priority,status,source,notes FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
        "ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date LIMIT 5",
        (estate_id(),),
    )
    delivery = water_delivery_summary(person_entity, 365) if person_entity and profile.get("water_delivery_tracking_enabled") else {
        "available": False, "confirmed_deliveries": 0, "deliveries": [], "recent_observations": [],
        "payment_queue": [], "pending_payments": 0,
    }
    return json_ready({
        "username": username,
        "worker_name": worker_name,
        "person_entity": person_entity,
        "portal_mode": portal_mode,
        "estate_role": profile.get("role"),
        "active": active,
        "pending": pending,
        "history": history,
        "totals": totals,
        "weather": weather_context_payload(),
        "work": work,
        "water_delivery": delivery,
        "server_time": datetime.now(ZoneInfo("Europe/Rome")),
    })


@router.post("/api/v1/worker-portal/work-items", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_add_work_item(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    title = str(payload.get("title") or "").strip()[:220]
    if not title:
        raise HTTPException(422, "Enter the work or item needed")
    category = str(payload.get("category") or "general").strip().casefold()[:100] or "general"
    allowed_categories = {"general", "water", "delivery", "maintenance", "materials", "transport", "vineyard", "cellar", "olives"}
    if category not in allowed_categories:
        category = "general"
    priority = str(payload.get("priority") or "normal").strip().casefold()
    if priority not in {"low", "normal", "high", "urgent"}:
        priority = "normal"
    due_date = None
    if payload.get("due_date"):
        try:
            due_date = date.fromisoformat(str(payload["due_date"]))
        except ValueError as error:
            raise HTTPException(422, "Enter a valid due date") from error
    note = str(payload.get("notes") or "").strip()[:1600]
    requester = f"Added by {worker_name} from the contractor portal ({username})."
    notes = f"{requester}\n{note}" if note else requester
    today_rome = datetime.now(ZoneInfo("Europe/Rome")).date()
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO tasks (id,estate_id,season_id,title,category,status,priority,due_date,notes,source) "
            "VALUES (%s,%s,%s,%s,%s,'planned',%s,%s,%s,'contractor_portal')",
            (record_id, estate_id(), season_for_year((due_date or today_rome).year), title, category, priority, due_date, notes),
        )
        audit(cursor, "contractor_work_item_add", "task", record_id, {
            "worker": worker_name, "username": username, "title": title, "category": category,
            "priority": priority, "due_date": due_date, "notes": note,
        }, username)
    return {"saved": True, "id": record_id, "status": "planned", "requested_by": worker_name}


@router.post("/api/v1/worker-portal/water-delivery-claims", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_add_water_delivery_claim(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    person_entity, profile = next(
        ((entity, saved) for entity, saved in people_profiles().items()
         if str(saved.get("username") or "").strip().casefold() == username),
        (None, {}),
    )
    if not person_entity or not profile.get("water_delivery_tracking_enabled"):
        raise HTTPException(403, "Water-delivery tracking is not enabled for this contractor")
    try:
        service_at = datetime.fromisoformat(str(payload.get("service_at") or ""))
    except ValueError as error:
        raise HTTPException(422, "Enter a valid delivery date and time") from error
    now_rome = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    if service_at > now_rome + timedelta(hours=1) or service_at < now_rome - timedelta(days=30):
        raise HTTPException(422, "Delivery time must be within the last 30 days")
    amount = payload.get("amount_eur")
    try:
        amount = None if amount in (None, "") else round(float(amount), 2)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid amount") from error
    if amount is not None and not 0 < amount <= 10000:
        raise HTTPException(422, "Enter an amount between €0.01 and €10,000")
    result = submit_water_delivery_claim(
        person_entity, username, service_at, str(payload.get("notes") or ""), amount,
    )
    return {**result, "message": "Matched to the existing delivery" if result["matched_existing"] else "Delivery reported; automatic evidence will attach to this record"}


@router.post("/api/v1/worker-portal/clock-in", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_clock_in(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    profile = worker_profile(worker_name)
    existing = fetch_one(
        "SELECT id,clock_in_at FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft' LIMIT 1",
        (estate_id(), username),
    )
    if existing:
        raise HTTPException(409, "You are already clocked in / Sei già registrato")
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    record_id = new_id()
    values = {
        "work_category": str(payload.get("work_category") or "general")[:100],
        "work_performed": str(payload.get("work_performed") or "").strip()[:500] or None,
        "location_text": str(payload.get("location_text") or "Tenuta Baiamonte")[:180],
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO labor_entries (id,estate_id,season_id,work_date,person_or_crew,role,start_time,regular_hours,overtime_hours,payroll_scope,payment_status,entry_source,worker_username,clock_in_at,approval_status,work_category,work_performed,location_text,pay_due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,0,0,%s,'verification_needed','worker_portal',%s,%s,'draft',%s,%s,%s,%s)",
            (record_id, estate_id(), season_for_year(now.year), now.date(), worker_name, profile["role"], now.time(), profile["payroll_scope"], username, now, values["work_category"], values["work_performed"], values["location_text"], worker_pay_due(worker_name, now.date())),
        )
        audit(cursor, "clock_in", "labor", record_id, {"worker": worker_name, "clock_in_at": now, **values}, username)
    return {"saved": True, "id": record_id, "clock_in_at": now.isoformat()}


@router.post("/api/v1/worker-portal/clock-out", dependencies=[Depends(authorize_worker)])
def worker_clock_out(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = fetch_one(
        "SELECT * FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft' ORDER BY clock_in_at DESC LIMIT 1",
        (estate_id(), username),
    )
    if not row:
        raise HTTPException(409, "No open shift / Nessun turno aperto")
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    started = row.get("clock_in_at")
    hours = round(max(0.0, min(24.0, (now - started).total_seconds() / 3600)), 2) if started else 0
    if hours <= 0:
        raise HTTPException(422, "The shift is too short to submit")
    expense = payload.get("expense_amount_eur")
    expense = None if expense in (None, "") else round(float(expense), 2)
    if expense is not None and (expense < 0 or expense > 10000):
        raise HTTPException(422, "Enter a valid expense amount")
    changes = {
        "clock_out_at": now,
        "end_time": now.time(),
        "regular_hours": hours,
        "approval_status": "submitted",
        "submitted_at": now,
        "work_performed": str(payload.get("work_performed") or row.get("work_performed") or "").strip()[:500] or None,
        "notes": str(payload.get("notes") or "").strip() or None,
        "expense_amount_eur": expense,
        "expense_category": str(payload.get("expense_category") or "").strip()[:100] or None,
        "expense_notes": str(payload.get("expense_notes") or "").strip() or None,
        "review_note": None,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE labor_entries SET clock_out_at=%s,end_time=%s,regular_hours=%s,approval_status=%s,submitted_at=%s,work_performed=%s,notes=%s,expense_amount_eur=%s,expense_category=%s,expense_notes=%s,review_note=%s WHERE id=%s AND estate_id=%s",
            (*changes.values(), row["id"], estate_id()),
        )
        audit(cursor, "clock_out_submit", "labor", row["id"], changes, username)
    return {"saved": True, "id": row["id"], "hours": hours, "approval_status": "submitted"}


@router.post("/api/v1/worker-portal/charge", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_one_off_charge(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    profile = worker_profile(worker_name)
    description = str(payload.get("description") or "").strip()[:500]
    if not description:
        raise HTTPException(422, "Enter what was delivered or provided")
    try:
        amount = round(float(payload.get("amount_eur")), 2)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid charge amount") from error
    if not 0 < amount <= 10000:
        raise HTTPException(422, "Enter a charge between €0.01 and €10,000")
    try:
        service_date = date.fromisoformat(str(payload.get("service_date") or ""))
    except ValueError as error:
        raise HTTPException(422, "Enter a valid service date") from error
    if service_date > datetime.now(ZoneInfo("Europe/Rome")).date():
        raise HTTPException(422, "The service date cannot be in the future")
    category = str(payload.get("category") or "Other service").strip()[:100] or "Other service"
    if category.casefold() == "water delivery":
        raise HTTPException(409, "Use Report a water delivery so camera and cistern evidence can merge into one record")
    notes = str(payload.get("notes") or "").strip()[:2000] or None
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO labor_entries (id,estate_id,season_id,work_date,person_or_crew,role,regular_hours,overtime_hours,payroll_scope,payment_status,entry_source,worker_username,approval_status,submitted_at,work_category,work_performed,notes,expense_amount_eur,expense_category,expense_notes,location_text,pay_due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,0,0,%s,'verification_needed','worker_portal_charge',%s,'submitted',%s,'one_off_charge',%s,%s,%s,%s,%s,'Tenuta Baiamonte',%s)",
            (record_id, estate_id(), season_for_year(service_date.year), service_date, worker_name, profile["role"], profile["payroll_scope"], username, now, description, notes, amount, category, notes, worker_pay_due(worker_name, service_date)),
        )
        audit(cursor, "worker_charge_submit", "labor", record_id, {"worker": worker_name, "service_date": service_date, "amount_eur": amount, "category": category, "description": description}, username)
    return {"saved": True, "id": record_id, "approval_status": "submitted", "queue": "services", "amount_eur": amount}


@router.patch("/api/v1/worker-portal/entries/{record_id}", dependencies=[Depends(authorize_worker)])
def worker_edit_entry(record_id: str, request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = _worker_labor_row(record_id, username)
    if row.get("approval_status") == "approved" or row.get("locked_at"):
        raise HTTPException(409, "Approved records are locked / I record approvati sono bloccati")
    allowed = {"work_performed", "notes", "expense_amount_eur", "expense_category", "expense_notes"}
    values = {key: payload.get(key) for key in allowed if key in payload}
    adjusted_times = False
    if "clock_in_at" in payload or "clock_out_at" in payload:
        try:
            started = datetime.fromisoformat(str(payload.get("clock_in_at") or row.get("clock_in_at")))
            ended = datetime.fromisoformat(str(payload.get("clock_out_at") or row.get("clock_out_at")))
        except (TypeError, ValueError) as error:
            raise HTTPException(422, "Enter valid clock-in and clock-out times") from error
        if ended <= started or (ended - started).total_seconds() > 24 * 3600:
            raise HTTPException(422, "Clock-out must be after clock-in and within 24 hours")
        values.update({"clock_in_at": started, "clock_out_at": ended, "work_date": started.date(), "start_time": started.time(), "end_time": ended.time(), "regular_hours": round((ended - started).total_seconds() / 3600, 2), "time_adjusted_by_worker": 1})
        adjusted_times = True
    if "expense_amount_eur" in values:
        values["expense_amount_eur"] = None if values["expense_amount_eur"] in (None, "") else round(float(values["expense_amount_eur"]), 2)
        if values["expense_amount_eur"] is not None and not 0 <= values["expense_amount_eur"] <= 10000:
            raise HTTPException(422, "Enter a valid expense amount")
    if not values:
        raise HTTPException(422, "Enter a change")
    if row.get("approval_status") == "rejected":
        values.update({"approval_status": "submitted", "submitted_at": datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)})
    with transaction() as (_, cursor):
        cursor.execute(f"UPDATE labor_entries SET {','.join(f'{key}=%s' for key in values)},review_note=NULL WHERE id=%s AND estate_id=%s", (*values.values(), record_id, estate_id()))
        audit(cursor, "worker_time_edit" if adjusted_times else "worker_edit", "labor", record_id, {"before": json_ready(row), "changes": values}, username)
    return {"saved": True, "id": record_id, "time_adjusted": adjusted_times}


@router.post("/api/v1/worker-portal/entries/{record_id}/photo", status_code=201, dependencies=[Depends(authorize_worker)])
async def worker_add_photo(record_id: str, request: Request, file: UploadFile = File(...), caption: str = Form(""), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = _worker_labor_row(record_id, username)
    if row.get("approval_status") == "approved" or row.get("locked_at"):
        raise HTTPException(409, "Approved records are locked")
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    await file.close()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "Photo must be 15 MB or smaller")
    media_type = file.content_type or "application/octet-stream"
    if not media_type.startswith("image/"):
        raise HTTPException(422, "Choose a photo")
    attachment_id = new_id()
    stored = store_attachment(data, attachment_id, file.filename or "", "work-photo")
    try:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,'labor',%s,%s,%s,%s,%s,%s,%s)", (attachment_id, estate_id(), record_id, stored.filename, str(stored.path), media_type, stored.sha256, caption or None, username))
            audit(cursor, "worker_photo", "labor", record_id, {"attachment_id": attachment_id, "filename": stored.filename}, username)
    except Exception:
        stored.discard()
        raise
    return {"saved": True, "id": attachment_id, "entity_id": record_id}
