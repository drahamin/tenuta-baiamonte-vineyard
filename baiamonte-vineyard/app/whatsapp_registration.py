from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from .access import authorize_admin
from .config import RUNTIME_OPTIONS_PATH
from .db import transaction
from .intelligence import clear_whatsapp_cache, register_whatsapp_phone_number, whatsapp_diagnostics
from .service import audit

router = APIRouter()


def _write_runtime_options(values: dict[str, Any]) -> None:
    current: dict[str, Any] = {}
    try:
        current.update(json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        pass
    current.update(values)
    RUNTIME_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME_OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(RUNTIME_OPTIONS_PATH)


def complete_whatsapp_registration(phone_number_id: str, pin: str, actor: str) -> dict[str, Any]:
    """Register and activate a verified sender without retaining its two-step PIN."""
    sender_id = re.sub(r"\D", "", phone_number_id)
    registration = register_whatsapp_phone_number(sender_id, pin)
    if not registration.get("registered"):
        raise ValueError("Meta did not confirm WhatsApp Cloud API registration")
    runtime_values: dict[str, Any] = {}
    try:
        runtime_values = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    runtime_values["whatsapp_active_phone_number_id"] = sender_id
    runtime_values["whatsapp_active_business_account_id"] = re.sub(r"\D", "", str(registration.get("business_account_id") or ""))
    _write_runtime_options(runtime_values)
    clear_whatsapp_cache()
    with transaction() as (_, cursor):
        audit(cursor, "register", "whatsapp_sender", sender_id, {"display_phone_number": registration.get("display_phone_number"), "verified_name": registration.get("verified_name"), "pin_persisted": False}, actor)
    return {**registration, "active": True, "diagnostics": whatsapp_diagnostics(force=True)}


@router.post("/api/v1/communications/whatsapp/register", dependencies=[Depends(authorize_admin)])
def communication_register_whatsapp_sender(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return complete_whatsapp_registration(str(payload.get("phone_number_id") or ""), str(payload.get("pin") or ""), request.headers.get("X-Remote-User-Name") or "api")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
