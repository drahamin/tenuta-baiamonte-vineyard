from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_hospitality, request_username
from ..intelligence import send_gmail_message, send_whatsapp_message
from ..service import json_ready
from .hospitality import communication_draft, dashboard, log_communication, reservation, save_package, save_reservation


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


@router.post("/reservations")
def create_reservation(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_reservation(payload, request_username(request))


@router.get("/reservations/{reservation_id}")
def get_reservation(reservation_id: str) -> dict[str, Any]:
    return reservation(reservation_id)


@router.put("/reservations/{reservation_id}")
def update_reservation(reservation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return save_reservation(payload, request_username(request), reservation_id)


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
