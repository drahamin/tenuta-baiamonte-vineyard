from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_hospitality, request_username
from ..intelligence import poll_gmail_once, send_gmail_message, send_whatsapp_message
from ..service import json_ready
from .hospitality import (
    communication_draft, dashboard, delete_partner_payment, delete_reservation, log_communication,
    partner_commission, partner_dashboard, reservation, review_partner_commission, save_package,
    save_partner, save_partner_payment, save_reservation,
)
from .hospitality_inbox import (
    delete_inquiry, hospitality_settings, inquiry, record_inquiry_response,
    save_hospitality_settings, sync_hospitality_inquiries, update_inquiry,
)


router = APIRouter(prefix="/api/v1/hospitality", dependencies=[Depends(authorize_hospitality)])


@router.get("/dashboard")
def hospitality_dashboard(from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    return dashboard(from_date, to_date)


@router.post("/packages")
def create_package(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_package(payload, request_username(request))


@router.put("/packages/{package_id}")
def update_package(package_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_package(payload, request_username(request), package_id)


@router.get("/partners")
def hospitality_partners(year: int | None = None) -> dict[str, Any]:
    return partner_dashboard(year)


@router.post("/partners")
def create_partner(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_partner(payload, request_username(request))


@router.put("/partners/{partner_id}")
def update_partner(partner_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_partner(payload, request_username(request), partner_id)


@router.get("/partner-commissions/{commission_id}")
def get_partner_commission(commission_id: str) -> dict[str, Any]:
    return partner_commission(commission_id)


@router.put("/partner-commissions/{commission_id}")
def update_partner_commission(commission_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return review_partner_commission(commission_id, payload, request_username(request))


@router.post("/partner-commissions/{commission_id}/payments")
def create_partner_payment(commission_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_partner_payment(commission_id, payload, request_username(request))


@router.put("/partner-commissions/{commission_id}/payments/{payment_id}")
def update_partner_payment(commission_id: str, payment_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_partner_payment(commission_id, payload, request_username(request), payment_id)


@router.delete("/partner-payments/{payment_id}")
def remove_partner_payment(payment_id: str, request: Request) -> dict[str, bool]:
    delete_partner_payment(payment_id, request_username(request))
    return {"ok": True}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return hospitality_settings()


@router.put("/settings")
def update_settings(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_hospitality_settings(payload, request_username(request))


@router.post("/inquiries/sync")
def sync_inquiries() -> dict[str, Any]:
    downloaded = poll_gmail_once()
    routed = sync_hospitality_inquiries()
    return {"ok": True, "downloaded": downloaded, "routed": routed}


@router.get("/inquiries/{inquiry_id}")
def get_inquiry(inquiry_id: str) -> dict[str, Any]:
    return inquiry(inquiry_id)


@router.put("/inquiries/{inquiry_id}")
def change_inquiry(inquiry_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return update_inquiry(inquiry_id, payload, request_username(request))


@router.delete("/inquiries/{inquiry_id}")
def remove_inquiry(inquiry_id: str, request: Request) -> dict[str, bool]:
    delete_inquiry(inquiry_id, request_username(request))
    return {"ok": True}


@router.post("/inquiries/{inquiry_id}/response")
def respond_to_inquiry(inquiry_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request_username(request)
    row = inquiry(inquiry_id)
    recipient = str(row.get("sender_address") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not recipient or "@" not in recipient:
        raise HTTPException(422, "This inquiry does not have a valid reply address")
    if not subject or not body:
        raise HTTPException(422, "Reply subject and message are required")
    try:
        delivery = send_gmail_message([recipient], subject, body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, f"Hospitality email delivery failed: {str(error)[:240]}") from error
    return {"ok": True, "inquiry": record_inquiry_response(inquiry_id, subject, body, actor), "delivery": json_ready(delivery)}


@router.post("/reservations")
def create_reservation(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_reservation(payload, request_username(request))


@router.get("/reservations/{reservation_id}")
def get_reservation(reservation_id: str) -> dict[str, Any]:
    return reservation(reservation_id)


@router.put("/reservations/{reservation_id}")
def update_reservation(reservation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_reservation(payload, request_username(request), reservation_id)


@router.delete("/reservations/{reservation_id}")
def remove_reservation(reservation_id: str, request: Request) -> dict[str, bool]:
    delete_reservation(reservation_id, request_username(request))
    return {"ok": True}


@router.post("/reservations/{reservation_id}/communication")
def send_communication(reservation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request_username(request)
    channel = str(payload.get("channel") or "email").strip().casefold()
    draft = communication_draft(
        reservation_id, channel, actor, str(payload.get("subject") or ""), str(payload.get("body") or ""),
    )
    booking = draft["reservation"]
    try:
        if channel == "email":
            recipient = str(booking.get("guest_email") or "").strip()
            if not recipient:
                raise ValueError("This guest does not have an email address")
            result = send_gmail_message([recipient], draft["subject"], draft["body"])
        elif channel == "whatsapp":
            recipient = re.sub(r"[^\d+]", "", str(booking.get("guest_phone") or ""))
            if not recipient:
                raise ValueError("This guest does not have a phone number")
            result = send_whatsapp_message(recipient, draft["body"])
        elif channel in {"phone", "note"}:
            result = {"recorded": True}
        else:
            raise ValueError("Choose email, WhatsApp, phone, or note")
        communication = log_communication(
            reservation_id, draft, actor, "sent" if channel in {"email", "whatsapp"} else "recorded",
        )
        return {"ok": True, "communication": communication, "delivery": json_ready(result)}
    except ValueError as error:
        log_communication(reservation_id, draft, actor, "failed")
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        log_communication(reservation_id, draft, actor, "failed")
        raise HTTPException(502, f"Hospitality {channel} delivery failed: {str(error)[:240]}") from error
