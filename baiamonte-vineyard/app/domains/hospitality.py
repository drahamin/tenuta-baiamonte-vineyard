from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id
from .hospitality_inbox import hospitality_settings, inquiries, link_inquiry_to_reservation, sync_hospitality_inquiries


RESERVATION_STATUSES = (
    "inquiry", "requested", "confirmed", "arrived", "completed", "cancelled", "declined", "no_show",
)
ACTIVE_CAPACITY_STATUSES = ("confirmed", "arrived")
COMMISSION_TYPES = ("percentage", "fixed_per_guest", "fixed_per_reservation")
COMMISSION_STATUSES = ("estimated", "due", "approved", "partially_paid", "paid", "void")


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


def _partner(partner_id: str | None) -> dict[str, Any]:
    if not partner_id:
        return {}
    row = fetch_one(
        "SELECT * FROM hospitality_partners WHERE estate_id=%s AND id=%s",
        (estate_id(), partner_id),
    )
    if not row:
        raise HTTPException(422, "Choose a valid hospitality partner")
    return row


def calculate_partner_commission(
    basis_amount_eur: Decimal, guest_count: int, commission_type: str, commission_value: Decimal,
) -> Decimal:
    if commission_type == "percentage":
        amount = basis_amount_eur * commission_value / Decimal("100")
    elif commission_type == "fixed_per_guest":
        amount = commission_value * guest_count
    elif commission_type == "fixed_per_reservation":
        amount = commission_value
    else:
        raise HTTPException(422, "Choose a valid partner commission rule")
    return max(Decimal("0"), amount.quantize(Decimal("0.01")))


def _sync_reservation_commission(
    cursor: Any, reservation_id: str, partner: dict[str, Any], reservation_status: str,
    basis_amount: Decimal, guest_count: int, end_at: datetime, payload: dict[str, Any], actor: str,
) -> None:
    cursor.execute(
        "SELECT c.*,COALESCE(SUM(p.amount_eur),0) paid_eur FROM hospitality_partner_commissions c "
        "LEFT JOIN hospitality_partner_payments p ON p.commission_id=c.id "
        "WHERE c.estate_id=%s AND c.reservation_id=%s GROUP BY c.id",
        (estate_id(), reservation_id),
    )
    existing = cursor.fetchone()
    if not partner:
        if existing and Decimal(existing.get("paid_eur") or 0) > 0:
            raise HTTPException(409, "This reservation has partner payments; keep the partner assigned")
        if existing:
            cursor.execute("UPDATE hospitality_partner_commissions SET status='void' WHERE id=%s", (existing["id"],))
        return
    commission_type = _text(
        payload.get("commission_type") or (existing or {}).get("commission_type")
        or partner.get("default_commission_type") or "percentage", 30,
    )
    if commission_type not in COMMISSION_TYPES:
        raise HTTPException(422, "Choose a valid partner commission rule")
    commission_value = Decimal(str(
        payload.get("commission_value") if "commission_value" in payload
        else (existing or {}).get("commission_value", partner.get("default_commission_value") or 0)
    ))
    amount = calculate_partner_commission(basis_amount, guest_count, commission_type, commission_value)
    terms = int(partner.get("payment_terms_days") or 0)
    due_date = end_at.date() + timedelta(days=terms)
    automatic = (
        "estimated" if reservation_status in {"inquiry", "requested"}
        else "void" if reservation_status in {"cancelled", "declined", "no_show"}
        else "due"
    )
    paid = Decimal((existing or {}).get("paid_eur") or 0)
    previous_status = str((existing or {}).get("status") or "")
    if paid >= amount and amount > 0:
        status = "paid"
    elif paid > 0:
        status = "partially_paid"
    elif previous_status == "approved" and automatic != "void":
        status = "approved"
    else:
        status = automatic
    if existing:
        cursor.execute(
            "UPDATE hospitality_partner_commissions SET partner_id=%s,basis_amount_eur=%s,commission_type=%s,commission_value=%s,"
            "commission_amount_eur=%s,status=%s,due_date=%s WHERE id=%s",
            (partner["id"], basis_amount, commission_type, commission_value, amount, status, due_date, existing["id"]),
        )
        commission_id = existing["id"]
    else:
        commission_id = new_id()
        cursor.execute(
            "INSERT INTO hospitality_partner_commissions (id,estate_id,partner_id,reservation_id,basis_amount_eur,commission_type,commission_value,commission_amount_eur,status,due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (commission_id, estate_id(), partner["id"], reservation_id, basis_amount, commission_type, commission_value, amount, status, due_date),
        )
    audit(cursor, "calculate", "hospitality_partner_commission", commission_id, {
        "reservation_id": reservation_id, "amount_eur": str(amount), "status": status,
    }, actor)


def _conflict(start_at: datetime, end_at: datetime, exclude_id: str = "") -> dict[str, Any] | None:
    return fetch_one(
        "SELECT id,confirmation_code,guest_name,start_at,end_at,status FROM hospitality_reservations "
        "WHERE estate_id=%s AND status IN ('confirmed','arrived') AND id<>%s "
        "AND start_at<%s AND end_at>%s ORDER BY start_at LIMIT 1",
        (estate_id(), exclude_id, end_at, start_at),
    )


def dashboard(from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    sync_hospitality_inquiries()
    start = from_date or date.today()
    end = to_date or (start + timedelta(days=120))
    packages = fetch_all(
        "SELECT * FROM hospitality_packages WHERE estate_id=%s ORDER BY active DESC,sort_order,name",
        (estate_id(),),
    )
    reservations = fetch_all(
        "SELECT r.*,p.name package_name,p.experience_type,p.duration_minutes,p.min_guests,p.max_guests,"
        "hp.name partner_name,hpc.id commission_id,hpc.status commission_status,hpc.commission_type,hpc.commission_value,hpc.commission_amount_eur,"
        "COALESCE(hpp.paid_eur,0) commission_paid_eur,"
        "GREATEST(hpc.commission_amount_eur-COALESCE(hpp.paid_eur,0),0) commission_balance_eur,"
        "(r.quoted_total_eur-r.deposit_received_eur) balance_due_eur "
        "FROM hospitality_reservations r LEFT JOIN hospitality_packages p ON p.id=r.package_id "
        "LEFT JOIN hospitality_partners hp ON hp.id=r.partner_id "
        "LEFT JOIN hospitality_partner_commissions hpc ON hpc.reservation_id=r.id "
        "LEFT JOIN (SELECT commission_id,SUM(amount_eur) paid_eur FROM hospitality_partner_payments GROUP BY commission_id) hpp ON hpp.commission_id=hpc.id "
        "WHERE r.estate_id=%s AND DATE(r.start_at) BETWEEN %s AND %s ORDER BY r.start_at",
        (estate_id(), start, end),
    )
    communications = fetch_all(
        "SELECT c.* FROM hospitality_communications c JOIN hospitality_reservations r ON r.id=c.reservation_id "
        "WHERE c.estate_id=%s ORDER BY c.created_at DESC LIMIT 40",
        (estate_id(),),
    )
    guest_inquiries = inquiries()
    active = [row for row in reservations if row["status"] not in {"cancelled", "declined", "no_show"}]
    return json_ready({
        "from_date": start, "to_date": end,
        "operating_model": "One private guest party at a time",
        "packages": packages, "reservations": reservations, "communications": communications,
        "inquiries": guest_inquiries, "settings": hospitality_settings(),
        "summary": {
            "upcoming": len([row for row in active if row["start_at"].date() >= date.today()]),
            "awaiting_confirmation": len([row for row in active if row["status"] in {"inquiry", "requested"}])
            + len([row for row in guest_inquiries if row["status"] in {"new", "responded"}]),
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
    partner_id = _text(payload.get("partner_id") if "partner_id" in payload else (existing or {}).get("partner_id"), 36) or None
    partner = _partner(partner_id)
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
        package_id, partner_id,
        _text(payload.get("partner_referral_code") if "partner_referral_code" in payload else (existing or {}).get("partner_referral_code"), 100),
        status, start_at, end_at, guest_count, guest_name,
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
                "UPDATE hospitality_reservations SET package_id=%s,partner_id=%s,partner_referral_code=%s,status=%s,start_at=%s,end_at=%s,guest_count=%s,guest_name=%s,guest_email=%s,guest_phone=%s,preferred_language=%s,"
                "dietary_restrictions=%s,celebration_details=%s,guest_preferences=%s,source=%s,public_notes=%s,internal_notes=%s,quoted_total_eur=%s,deposit_received_eur=%s,assigned_manager_entity=%s "
                "WHERE estate_id=%s AND id=%s",
                (*values, estate_id(), reservation_id),
            )
        else:
            cursor.execute(
                "INSERT INTO hospitality_reservations (id,estate_id,confirmation_code,package_id,partner_id,partner_referral_code,status,start_at,end_at,guest_count,guest_name,guest_email,guest_phone,preferred_language,dietary_restrictions,celebration_details,guest_preferences,source,public_notes,internal_notes,quoted_total_eur,deposit_received_eur,assigned_manager_entity,created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (reservation_id, estate_id(), confirmation, *values, actor),
            )
        _sync_reservation_commission(
            cursor, reservation_id, partner, status, values[-3], guest_count, end_at, payload, actor,
        )
        inquiry_id = _text(payload.get("inquiry_id"), 36)
        if inquiry_id:
            link_inquiry_to_reservation(inquiry_id, reservation_id, cursor, actor)
        audit(cursor, "update" if existing else "create", "hospitality_reservation", reservation_id, {**payload, "confirmation_code": confirmation}, actor)
    return reservation(reservation_id)


def delete_reservation(reservation_id: str, actor: str) -> None:
    before = reservation(reservation_id)
    paid = fetch_one(
        "SELECT COUNT(*) payment_count FROM hospitality_partner_payments p JOIN hospitality_partner_commissions c ON c.id=p.commission_id "
        "WHERE c.estate_id=%s AND c.reservation_id=%s", (estate_id(), reservation_id),
    )
    if int((paid or {}).get("payment_count") or 0):
        raise HTTPException(409, "This reservation has partner payments. Cancel it instead so the payment history is preserved.")
    with transaction() as (_, cursor):
        audit(cursor, "delete", "hospitality_reservation", reservation_id, before, actor)
        cursor.execute(
            "UPDATE hospitality_inquiries SET status='responded',reservation_id=NULL WHERE estate_id=%s AND reservation_id=%s",
            (estate_id(), reservation_id),
        )
        cursor.execute("DELETE FROM hospitality_reservations WHERE estate_id=%s AND id=%s", (estate_id(), reservation_id))


def reservation(reservation_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT r.*,p.name package_name,p.experience_type,hp.name partner_name,hpc.id commission_id,hpc.status commission_status,"
        "hpc.commission_type,hpc.commission_value,hpc.commission_amount_eur,COALESCE(hpp.paid_eur,0) commission_paid_eur,"
        "GREATEST(hpc.commission_amount_eur-COALESCE(hpp.paid_eur,0),0) commission_balance_eur,"
        "(r.quoted_total_eur-r.deposit_received_eur) balance_due_eur "
        "FROM hospitality_reservations r LEFT JOIN hospitality_packages p ON p.id=r.package_id "
        "LEFT JOIN hospitality_partners hp ON hp.id=r.partner_id LEFT JOIN hospitality_partner_commissions hpc ON hpc.reservation_id=r.id "
        "LEFT JOIN (SELECT commission_id,SUM(amount_eur) paid_eur FROM hospitality_partner_payments GROUP BY commission_id) hpp ON hpp.commission_id=hpc.id "
        "WHERE r.estate_id=%s AND r.id=%s",
        (estate_id(), reservation_id),
    )
    if not row:
        raise HTTPException(404, "Hospitality reservation not found")
    row["communications"] = fetch_all(
        "SELECT * FROM hospitality_communications WHERE estate_id=%s AND reservation_id=%s ORDER BY created_at DESC",
        (estate_id(), reservation_id),
    )
    return json_ready(row)


def partner_dashboard(year: int | None = None) -> dict[str, Any]:
    selected_year = year or date.today().year
    partners = fetch_all(
        "SELECT hp.*,COUNT(DISTINCT r.id) reservation_count,COALESCE(SUM(CASE WHEN c.status<>'void' THEN c.commission_amount_eur ELSE 0 END),0) earned_eur,"
        "COALESCE(SUM(pp.paid_eur),0) paid_eur FROM hospitality_partners hp "
        "LEFT JOIN hospitality_reservations r ON r.partner_id=hp.id AND YEAR(r.start_at)=%s "
        "LEFT JOIN hospitality_partner_commissions c ON c.reservation_id=r.id "
        "LEFT JOIN (SELECT commission_id,SUM(amount_eur) paid_eur FROM hospitality_partner_payments GROUP BY commission_id) pp ON pp.commission_id=c.id "
        "WHERE hp.estate_id=%s GROUP BY hp.id ORDER BY hp.active DESC,hp.name",
        (selected_year, estate_id()),
    )
    commissions = fetch_all(
        "SELECT c.*,hp.name partner_name,r.confirmation_code,r.guest_name,r.guest_count,r.start_at,pkg.name package_name,"
        "COALESCE(pp.paid_eur,0) paid_eur,GREATEST(c.commission_amount_eur-COALESCE(pp.paid_eur,0),0) balance_eur "
        "FROM hospitality_partner_commissions c JOIN hospitality_partners hp ON hp.id=c.partner_id "
        "JOIN hospitality_reservations r ON r.id=c.reservation_id LEFT JOIN hospitality_packages pkg ON pkg.id=r.package_id "
        "LEFT JOIN (SELECT commission_id,SUM(amount_eur) paid_eur FROM hospitality_partner_payments GROUP BY commission_id) pp ON pp.commission_id=c.id "
        "WHERE c.estate_id=%s AND YEAR(r.start_at)=%s ORDER BY FIELD(c.status,'approved','partially_paid','due','estimated','paid','void'),c.due_date,r.start_at",
        (estate_id(), selected_year),
    )
    payments = fetch_all(
        "SELECT p.*,hp.name partner_name,r.confirmation_code,r.guest_name FROM hospitality_partner_payments p "
        "JOIN hospitality_partners hp ON hp.id=p.partner_id JOIN hospitality_partner_commissions c ON c.id=p.commission_id "
        "JOIN hospitality_reservations r ON r.id=c.reservation_id WHERE p.estate_id=%s AND YEAR(p.paid_on)=%s ORDER BY p.paid_on DESC,p.created_at DESC",
        (estate_id(), selected_year),
    )
    summary = {
        "estimated_eur": sum(Decimal(row.get("balance_eur") or 0) for row in commissions if row["status"] == "estimated"),
        "due_eur": sum(Decimal(row.get("balance_eur") or 0) for row in commissions if row["status"] == "due"),
        "ready_to_pay_eur": sum(Decimal(row.get("balance_eur") or 0) for row in commissions if row["status"] in {"approved", "partially_paid"}),
        "outstanding_eur": sum(Decimal(row.get("balance_eur") or 0) for row in commissions if row["status"] in {"due", "approved", "partially_paid"}),
        "paid_eur": sum(Decimal(row.get("amount_eur") or 0) for row in payments),
    }
    return json_ready({"year": selected_year, "partners": partners, "commissions": commissions, "payments": payments, "summary": summary})


def save_partner(payload: dict[str, Any], actor: str, partner_id: str | None = None) -> dict[str, Any]:
    name = _text(payload.get("name"), 220)
    if not name:
        raise HTTPException(422, "Enter the partner name")
    partner_type = _text(payload.get("partner_type") or "other", 30)
    if partner_type not in {"travel_agent", "travel_advisor", "hotel", "concierge", "event_planner", "tour_operator", "restaurant", "venue", "other"}:
        raise HTTPException(422, "Choose a valid partner type")
    rule = _text(payload.get("default_commission_type") or "percentage", 30)
    if rule not in COMMISSION_TYPES:
        raise HTTPException(422, "Choose a valid commission rule")
    value = Decimal(str(payload.get("default_commission_value") or 0))
    terms = int(payload.get("payment_terms_days") or 0)
    if value < 0 or terms < 0 or terms > 365:
        raise HTTPException(422, "Commission and payment terms cannot be negative")
    partner_id = partner_id or new_id()
    values = (
        name, partner_type, _text(payload.get("contact_name"), 180), _text(payload.get("email"), 320),
        _text(payload.get("phone"), 80), _text(payload.get("tax_id"), 100), _text(payload.get("payment_details"), 4000),
        rule, value, terms, bool(payload.get("active", True)), _text(payload.get("notes"), 4000),
    )
    with transaction() as (_, cursor):
        cursor.execute("SELECT id FROM hospitality_partners WHERE estate_id=%s AND id=%s", (estate_id(), partner_id))
        exists = cursor.fetchone()
        if exists:
            cursor.execute(
                "UPDATE hospitality_partners SET name=%s,partner_type=%s,contact_name=%s,email=%s,phone=%s,tax_id=%s,payment_details=%s,"
                "default_commission_type=%s,default_commission_value=%s,payment_terms_days=%s,active=%s,notes=%s WHERE estate_id=%s AND id=%s",
                (*values, estate_id(), partner_id),
            )
        else:
            cursor.execute(
                "INSERT INTO hospitality_partners (id,estate_id,name,partner_type,contact_name,email,phone,tax_id,payment_details,default_commission_type,default_commission_value,payment_terms_days,active,notes) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (partner_id, estate_id(), *values),
            )
        audit(cursor, "update" if exists else "create", "hospitality_partner", partner_id, payload, actor)
    return json_ready(fetch_one("SELECT * FROM hospitality_partners WHERE estate_id=%s AND id=%s", (estate_id(), partner_id)))


def review_partner_commission(commission_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM hospitality_partner_commissions WHERE estate_id=%s AND id=%s", (estate_id(), commission_id))
    if not row:
        raise HTTPException(404, "Partner commission not found")
    status = _text(payload.get("status") or row["status"], 30)
    if status not in {"estimated", "due", "approved", "void"}:
        raise HTTPException(422, "Use payments to set partially paid or paid status")
    amount = Decimal(str(payload.get("commission_amount_eur") if "commission_amount_eur" in payload else row["commission_amount_eur"]))
    if amount < 0:
        raise HTTPException(422, "Commission cannot be negative")
    paid = fetch_one("SELECT COALESCE(SUM(amount_eur),0) paid_eur FROM hospitality_partner_payments WHERE commission_id=%s", (commission_id,))
    paid_amount = Decimal((paid or {}).get("paid_eur") or 0)
    if amount < paid_amount:
        raise HTTPException(409, "Commission cannot be lower than payments already recorded")
    if paid_amount > 0 and status in {"estimated", "due", "void"}:
        raise HTTPException(409, "A commission with recorded payments must remain approved")
    due_date = payload.get("due_date") or row.get("due_date")
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE hospitality_partner_commissions SET commission_amount_eur=%s,status=%s,due_date=%s,notes=%s,"
            "approved_by=IF(%s='approved',%s,approved_by),approved_at=IF(%s='approved',NOW(6),approved_at) WHERE estate_id=%s AND id=%s",
            (amount, status, due_date, _text(payload.get("notes") if "notes" in payload else row.get("notes"), 4000), status, actor, status, estate_id(), commission_id),
        )
        _refresh_commission_payment_status(cursor, commission_id)
        audit(cursor, "review", "hospitality_partner_commission", commission_id, payload, actor)
    return partner_commission(commission_id)


def partner_commission(commission_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT c.*,hp.name partner_name,r.confirmation_code,r.guest_name,r.start_at,pkg.name package_name,COALESCE(pp.paid_eur,0) paid_eur,"
        "GREATEST(c.commission_amount_eur-COALESCE(pp.paid_eur,0),0) balance_eur FROM hospitality_partner_commissions c "
        "JOIN hospitality_partners hp ON hp.id=c.partner_id JOIN hospitality_reservations r ON r.id=c.reservation_id "
        "LEFT JOIN hospitality_packages pkg ON pkg.id=r.package_id LEFT JOIN (SELECT commission_id,SUM(amount_eur) paid_eur FROM hospitality_partner_payments GROUP BY commission_id) pp ON pp.commission_id=c.id "
        "WHERE c.estate_id=%s AND c.id=%s", (estate_id(), commission_id),
    )
    if not row:
        raise HTTPException(404, "Partner commission not found")
    row["payments"] = fetch_all("SELECT * FROM hospitality_partner_payments WHERE commission_id=%s ORDER BY paid_on DESC,created_at DESC", (commission_id,))
    return json_ready(row)


def _refresh_commission_payment_status(cursor: Any, commission_id: str) -> None:
    cursor.execute(
        "SELECT c.commission_amount_eur,c.status,COALESCE(SUM(p.amount_eur),0) paid_eur FROM hospitality_partner_commissions c "
        "LEFT JOIN hospitality_partner_payments p ON p.commission_id=c.id WHERE c.id=%s GROUP BY c.id", (commission_id,),
    )
    row = cursor.fetchone()
    paid, amount = Decimal(row.get("paid_eur") or 0), Decimal(row.get("commission_amount_eur") or 0)
    baseline = str(row.get("status") or "approved")
    if baseline in {"paid", "partially_paid"}:
        baseline = "approved"
    status = "paid" if amount > 0 and paid >= amount else "partially_paid" if paid > 0 else baseline
    cursor.execute("UPDATE hospitality_partner_commissions SET status=%s WHERE id=%s", (status, commission_id))


def save_partner_payment(commission_id: str, payload: dict[str, Any], actor: str, payment_id: str | None = None) -> dict[str, Any]:
    commission = partner_commission(commission_id)
    if commission["status"] in {"estimated", "due", "void"}:
        raise HTTPException(409, "Approve this commission before recording a payment")
    amount = Decimal(str(payload.get("amount_eur") or 0))
    if amount <= 0:
        raise HTTPException(422, "Payment amount must be greater than zero")
    existing = fetch_one(
        "SELECT * FROM hospitality_partner_payments WHERE estate_id=%s AND commission_id=%s AND id=%s",
        (estate_id(), commission_id, payment_id),
    ) if payment_id else None
    if payment_id and not existing:
        raise HTTPException(404, "Partner payment not found")
    other_paid = Decimal(commission.get("paid_eur") or 0) - Decimal((existing or {}).get("amount_eur") or 0)
    if other_paid + amount > Decimal(commission["commission_amount_eur"]):
        raise HTTPException(409, "Payment exceeds the remaining partner commission balance")
    try:
        paid_on = date.fromisoformat(str(payload.get("paid_on") or date.today()))
    except ValueError as error:
        raise HTTPException(422, "Enter a valid payment date") from error
    payment_id = payment_id or new_id()
    with transaction() as (_, cursor):
        if existing:
            cursor.execute(
                "UPDATE hospitality_partner_payments SET amount_eur=%s,paid_on=%s,method=%s,reference=%s,notes=%s WHERE estate_id=%s AND id=%s",
                (amount, paid_on, _text(payload.get("method"), 80), _text(payload.get("reference"), 160), _text(payload.get("notes"), 4000), estate_id(), payment_id),
            )
        else:
            cursor.execute(
                "INSERT INTO hospitality_partner_payments (id,estate_id,partner_id,commission_id,amount_eur,paid_on,method,reference,notes,recorded_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (payment_id, estate_id(), commission["partner_id"], commission_id, amount, paid_on, _text(payload.get("method"), 80), _text(payload.get("reference"), 160), _text(payload.get("notes"), 4000), actor),
            )
        _refresh_commission_payment_status(cursor, commission_id)
        audit(cursor, "update" if existing else "payment", "hospitality_partner_commission", commission_id, {**payload, "payment_id": payment_id}, actor)
    return partner_commission(commission_id)


def delete_partner_payment(payment_id: str, actor: str) -> None:
    row = fetch_one("SELECT * FROM hospitality_partner_payments WHERE estate_id=%s AND id=%s", (estate_id(), payment_id))
    if not row:
        raise HTTPException(404, "Partner payment not found")
    with transaction() as (_, cursor):
        cursor.execute("DELETE FROM hospitality_partner_payments WHERE estate_id=%s AND id=%s", (estate_id(), payment_id))
        _refresh_commission_payment_status(cursor, row["commission_id"])
        audit(cursor, "delete", "hospitality_partner_payment", payment_id, row, actor)


def partner_finance_summary(year: int) -> dict[str, Any]:
    data = partner_dashboard(year)
    return {"summary": data["summary"], "queue": [row for row in data["commissions"] if row["status"] in {"due", "approved", "partially_paid"}], "payments": data["payments"]}


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
