from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id


RESERVATION_STATUSES = (
    "inquiry", "requested", "confirmed", "arrived", "completed", "cancelled", "declined", "no_show",
)
ACTIVE_CAPACITY_STATUSES = ("confirmed", "arrived")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _date_time(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as error:
        raise HTTPException(422, f"Enter a valid {field}") from error
    return parsed.replace(tzinfo=None)


def _package(package_id: str | None) -> dict[str, Any]:
    if not package_id:
        return {}
    row = fetch_one(
        "SELECT * FROM hospitality_packages WHERE estate_id=%s AND id=%s",
        (estate_id(), package_id),
    )
    if not row:
        raise HTTPException(422, "Choose a valid hospitality package")
    return row


def _conflict(start_at: datetime, end_at: datetime, exclude_id: str = "") -> dict[str, Any] | None:
    return fetch_one(
        "SELECT id,confirmation_code,guest_name,start_at,end_at,status FROM hospitality_reservations "
        "WHERE estate_id=%s AND status IN ('confirmed','arrived') AND id<>%s "
        "AND start_at<%s AND end_at>%s ORDER BY start_at LIMIT 1",
        (estate_id(), exclude_id, end_at, start_at),
    )


def dashboard(from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    start = from_date or date.today()
    end = to_date or (start + timedelta(days=120))
    packages = fetch_all(
        "SELECT * FROM hospitality_packages WHERE estate_id=%s ORDER BY active DESC,sort_order,name",
        (estate_id(),),
    )
    reservations = fetch_all(
        "SELECT r.*,p.name package_name,p.experience_type,p.duration_minutes,p.min_guests,p.max_guests,"
        "(r.quoted_total_eur-r.deposit_received_eur) balance_due_eur "
        "FROM hospitality_reservations r LEFT JOIN hospitality_packages p ON p.id=r.package_id "
        "WHERE r.estate_id=%s AND DATE(r.start_at) BETWEEN %s AND %s ORDER BY r.start_at",
        (estate_id(), start, end),
    )
    communications = fetch_all(
        "SELECT c.* FROM hospitality_communications c JOIN hospitality_reservations r ON r.id=c.reservation_id "
        "WHERE c.estate_id=%s ORDER BY c.created_at DESC LIMIT 40",
        (estate_id(),),
    )
    active = [row for row in reservations if row["status"] not in {"cancelled", "declined", "no_show"}]
    return json_ready({
        "from_date": start, "to_date": end,
        "operating_model": "One private guest party at a time",
        "packages": packages, "reservations": reservations, "communications": communications,
        "summary": {
            "upcoming": len([row for row in active if row["start_at"].date() >= date.today()]),
            "awaiting_confirmation": len([row for row in active if row["status"] in {"inquiry", "requested"}]),
            "confirmed_guests": sum(int(row.get("guest_count") or 0) for row in active if row["status"] == "confirmed"),
            "quoted_revenue_eur": sum(Decimal(row.get("quoted_total_eur") or 0) for row in active),
            "deposits_eur": sum(Decimal(row.get("deposit_received_eur") or 0) for row in active),
        },
    })


def save_package(payload: dict[str, Any], actor: str, package_id: str | None = None) -> dict[str, Any]:
    name = _text(payload.get("name"), 180)
    experience_type = _text(payload.get("experience_type"), 30)
    price_basis = _text(payload.get("price_basis"), 30)
    if not name:
        raise HTTPException(422, "Enter a package name")
    if experience_type not in {"tasting", "private_dinner", "event"}:
        raise HTTPException(422, "Choose tasting, private dinner, or event")
    if price_basis not in {"per_person", "flat", "quote"}:
        raise HTTPException(422, "Choose a valid price basis")
    minimum, maximum = int(payload.get("min_guests") or 1), int(payload.get("max_guests") or 1)
    duration = int(payload.get("duration_minutes") or 90)
    if minimum < 1 or maximum < minimum or maximum > 40:
        raise HTTPException(422, "Guest limits must be between 1 and 40")
    if duration < 30 or duration > 720:
        raise HTTPException(422, "Duration must be between 30 minutes and 12 hours")
    package_id = package_id or new_id()
    values = (
        name, experience_type, _text(payload.get("description"), 4000), duration, minimum, maximum,
        price_basis, Decimal(str(payload.get("price_eur") or 0)), Decimal(str(payload.get("deposit_eur") or 0)),
        _text(payload.get("inclusions"), 4000), bool(payload.get("active", True)),
        int(payload.get("sort_order") or 0),
    )
    with transaction() as (_, cursor):
        cursor.execute("SELECT id FROM hospitality_packages WHERE estate_id=%s AND id=%s", (estate_id(), package_id))
        exists = cursor.fetchone()
        if exists:
            cursor.execute(
                "UPDATE hospitality_packages SET name=%s,experience_type=%s,description=%s,duration_minutes=%s,min_guests=%s,max_guests=%s,"
                "price_basis=%s,price_eur=%s,deposit_eur=%s,inclusions=%s,active=%s,sort_order=%s WHERE estate_id=%s AND id=%s",
                (*values, estate_id(), package_id),
            )
        else:
            cursor.execute(
                "INSERT INTO hospitality_packages (id,estate_id,name,experience_type,description,duration_minutes,min_guests,max_guests,price_basis,price_eur,deposit_eur,inclusions,active,sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (package_id, estate_id(), *values),
            )
        audit(cursor, "update" if exists else "create", "hospitality_package", package_id, payload, actor)
    return json_ready(fetch_one("SELECT * FROM hospitality_packages WHERE estate_id=%s AND id=%s", (estate_id(), package_id)))


def save_reservation(payload: dict[str, Any], actor: str, reservation_id: str | None = None) -> dict[str, Any]:
    existing = fetch_one(
        "SELECT * FROM hospitality_reservations WHERE estate_id=%s AND id=%s",
        (estate_id(), reservation_id),
    ) if reservation_id else None
    package_id = _text(payload.get("package_id") or (existing or {}).get("package_id"), 36) or None
    package = _package(package_id)
    start_at = _date_time(payload.get("start_at") or (existing or {}).get("start_at"), "start time")
    duration = int(package.get("duration_minutes") or 90)
    end_at = _date_time(payload.get("end_at"), "end time") if payload.get("end_at") else start_at + timedelta(minutes=duration)
    if end_at <= start_at:
        raise HTTPException(422, "End time must be after the start time")
    status = _text(payload.get("status") or (existing or {}).get("status") or "inquiry", 30)
    if status not in RESERVATION_STATUSES:
        raise HTTPException(422, "Choose a valid reservation status")
    guest_count = int(payload.get("guest_count") or (existing or {}).get("guest_count") or 1)
    if guest_count < 1 or guest_count > 40:
        raise HTTPException(422, "Guest count must be between 1 and 40")
    if package and not int(package["min_guests"]) <= guest_count <= int(package["max_guests"]):
        raise HTTPException(422, f"{package['name']} allows {package['min_guests']}–{package['max_guests']} guests")
    if status in ACTIVE_CAPACITY_STATUSES:
        conflict = _conflict(start_at, end_at, reservation_id or "")
        if conflict:
            raise HTTPException(409, f"This overlaps confirmed booking {conflict['confirmation_code']} for {conflict['guest_name']}")
    guest_name = _text(payload.get("guest_name") or (existing or {}).get("guest_name"), 180)
    if not guest_name:
        raise HTTPException(422, "Enter the guest or party name")
    reservation_id = reservation_id or new_id()
    confirmation = str((existing or {}).get("confirmation_code") or f"TB-{start_at:%y%m%d}-{secrets.token_hex(2).upper()}")
    values = (
        package_id, status, start_at, end_at, guest_count, guest_name,
        _text(payload.get("guest_email") if "guest_email" in payload else (existing or {}).get("guest_email"), 320),
        _text(payload.get("guest_phone") if "guest_phone" in payload else (existing or {}).get("guest_phone"), 80),
        _text(payload.get("preferred_language") or (existing or {}).get("preferred_language") or "en", 12),
        _text(payload.get("dietary_restrictions") if "dietary_restrictions" in payload else (existing or {}).get("dietary_restrictions"), 4000),
        _text(payload.get("celebration_details") if "celebration_details" in payload else (existing or {}).get("celebration_details"), 4000),
        _text(payload.get("guest_preferences") if "guest_preferences" in payload else (existing or {}).get("guest_preferences"), 4000),
        _text(payload.get("source") or (existing or {}).get("source") or "direct", 80),
        _text(payload.get("public_notes") if "public_notes" in payload else (existing or {}).get("public_notes"), 4000),
        _text(payload.get("internal_notes") if "internal_notes" in payload else (existing or {}).get("internal_notes"), 4000),
        Decimal(str(payload.get("quoted_total_eur") if "quoted_total_eur" in payload else (existing or {}).get("quoted_total_eur") or 0)),
        Decimal(str(payload.get("deposit_received_eur") if "deposit_received_eur" in payload else (existing or {}).get("deposit_received_eur") or 0)),
        _text(payload.get("assigned_manager_entity") if "assigned_manager_entity" in payload else (existing or {}).get("assigned_manager_entity"), 255),
    )
    with transaction() as (_, cursor):
        if existing:
            cursor.execute(
                "UPDATE hospitality_reservations SET package_id=%s,status=%s,start_at=%s,end_at=%s,guest_count=%s,guest_name=%s,guest_email=%s,guest_phone=%s,preferred_language=%s,"
                "dietary_restrictions=%s,celebration_details=%s,guest_preferences=%s,source=%s,public_notes=%s,internal_notes=%s,quoted_total_eur=%s,deposit_received_eur=%s,assigned_manager_entity=%s "
                "WHERE estate_id=%s AND id=%s",
                (*values, estate_id(), reservation_id),
            )
        else:
            cursor.execute(
                "INSERT INTO hospitality_reservations (id,estate_id,confirmation_code,package_id,status,start_at,end_at,guest_count,guest_name,guest_email,guest_phone,preferred_language,dietary_restrictions,celebration_details,guest_preferences,source,public_notes,internal_notes,quoted_total_eur,deposit_received_eur,assigned_manager_entity,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (reservation_id, estate_id(), confirmation, *values, actor),
            )
        audit(cursor, "update" if existing else "create", "hospitality_reservation", reservation_id, {**payload, "confirmation_code": confirmation}, actor)
    return reservation(reservation_id)


def reservation(reservation_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT r.*,p.name package_name,p.experience_type,(r.quoted_total_eur-r.deposit_received_eur) balance_due_eur "
        "FROM hospitality_reservations r LEFT JOIN hospitality_packages p ON p.id=r.package_id WHERE r.estate_id=%s AND r.id=%s",
        (estate_id(), reservation_id),
    )
    if not row:
        raise HTTPException(404, "Hospitality reservation not found")
    row["communications"] = fetch_all(
        "SELECT * FROM hospitality_communications WHERE estate_id=%s AND reservation_id=%s ORDER BY created_at DESC",
        (estate_id(), reservation_id),
    )
    return json_ready(row)


def communication_draft(reservation_id: str, channel: str, actor: str, subject: str = "", body: str = "") -> dict[str, Any]:
    booking = reservation(reservation_id)
    if channel not in {"email", "whatsapp", "phone", "note"}:
        raise HTTPException(422, "Choose email, WhatsApp, phone, or note")
    if not body.strip():
        when = datetime.fromisoformat(booking["start_at"]).strftime("%A, %d %B at %H:%M")
        body = (
            f"Dear {booking['guest_name']},\n\nYour {booking.get('package_name') or 'private experience'} at "
            f"Tenuta Baiamonte is confirmed for {when} for {booking['guest_count']} guests. "
            f"Confirmation: {booking['confirmation_code']}.\n\nWe look forward to welcoming you."
        )
    return {"channel": channel, "subject": subject or f"Tenuta Baiamonte · {booking['confirmation_code']}", "body": body, "reservation": booking, "actor": actor}


def log_communication(reservation_id: str, payload: dict[str, Any], actor: str, status: str) -> dict[str, Any]:
    communication_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO hospitality_communications (id,estate_id,reservation_id,channel,direction,subject,body,delivery_status,sent_by,sent_at) "
            "VALUES (%s,%s,%s,%s,'outbound',%s,%s,%s,%s,IF(%s='sent',NOW(6),NULL))",
            (communication_id, estate_id(), reservation_id, payload["channel"], payload.get("subject"), payload["body"], status, actor, status),
        )
        audit(cursor, "communicate", "hospitality_reservation", reservation_id, {"channel": payload["channel"], "status": status}, actor)
    return json_ready(fetch_one("SELECT * FROM hospitality_communications WHERE id=%s", (communication_id,)))
