"""Linked system WhatsApp control-plane and authenticated intake routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pymysql.err import IntegrityError

from ..access import authorize_admin
from ..config import Settings, get_settings
from ..db import fetch_one, transaction
from ..intelligence import analyze_intake, save_intake_file
from ..service import audit, estate_id, json_ready, new_id
from ..system_whatsapp import (
    system_whatsapp_add_contact,
    system_whatsapp_backup,
    system_whatsapp_chat,
    system_whatsapp_connect,
    system_whatsapp_decide_membership,
    system_whatsapp_disconnect,
    system_whatsapp_import_contacts,
    system_whatsapp_refresh_catalog,
    system_whatsapp_refresh_membership,
    system_whatsapp_relink,
    system_whatsapp_rename_contact,
    system_whatsapp_send,
    system_whatsapp_sync_history,
)
from .system_whatsapp_control import (
    save_system_whatsapp_settings,
    system_whatsapp_center,
    system_whatsapp_chat_allowed,
    system_whatsapp_settings,
)


router = APIRouter(tags=["communications"])


def _slot(slot: int) -> int:
    if slot not in (1, 2):
        raise HTTPException(404, "Unknown system WhatsApp account")
    return slot


@router.get("/api/v1/communications/system-whatsapp", dependencies=[Depends(authorize_admin)])
def communication_system_whatsapp(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return json_ready(system_whatsapp_center(settings))


@router.put("/api/v1/communications/system-whatsapp/settings", dependencies=[Depends(authorize_admin)])
def communication_save_system_whatsapp(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    stored = save_system_whatsapp_settings(payload)
    with transaction() as (_, cursor):
        audit(
            cursor,
            "update",
            "system_whatsapp_accounts",
            estate_id(),
            stored,
            request.headers.get("X-Remote-User-Name") or "home-assistant",
        )
    return json_ready(system_whatsapp_center(get_settings()))


@router.post("/api/v1/communications/system-whatsapp/{slot}/connect", dependencies=[Depends(authorize_admin)])
def communication_connect_system_whatsapp(slot: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_connect(_slot(slot), bool((payload or {}).get("restart", False))))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/disconnect", dependencies=[Depends(authorize_admin)])
def communication_disconnect_system_whatsapp(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_disconnect(_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/relink", dependencies=[Depends(authorize_admin)])
def communication_relink_system_whatsapp(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_relink(_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.get("/api/v1/communications/system-whatsapp/{slot}/backup", dependencies=[Depends(authorize_admin)])
def communication_backup_system_whatsapp(slot: int) -> JSONResponse:
    slot = _slot(slot)
    try:
        return JSONResponse(
            json_ready(system_whatsapp_backup(slot)),
            headers={"Content-Disposition": f'attachment; filename="baiamonte-whatsapp-account-{slot}-backup.json"'},
        )
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/contacts", dependencies=[Depends(authorize_admin)])
def communication_add_system_whatsapp_contact(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    slot = _slot(slot)
    name = str(payload.get("name") or "").strip()[:120]
    number = re.sub(r"\D", "", str(payload.get("number") or ""))
    if len(number) < 7 or len(number) > 15:
        raise HTTPException(422, "Enter the complete international number without a leading +")
    try:
        result = system_whatsapp_add_contact(slot, name, number)
        with transaction() as (_, cursor):
            audit(
                cursor,
                "create",
                "system_whatsapp_contact",
                str(result.get("contact", {}).get("contact_id") or number),
                {"account_slot": slot, "name": name, "number": number},
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/contacts/import", dependencies=[Depends(authorize_admin)])
def communication_import_system_whatsapp_contacts(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    contacts = []
    for row in (payload.get("contacts") or [])[:2000]:
        name = str(row.get("name") or "").strip()[:120]
        number = re.sub(r"\D", "", str(row.get("number") or ""))
        if name and 7 <= len(number) <= 15:
            contacts.append({"name": name, "number": number})
    if not contacts:
        raise HTTPException(422, "No usable named phone contacts were found in that file")
    try:
        result = system_whatsapp_import_contacts(_slot(slot), contacts)
        with transaction() as (_, cursor):
            audit(
                cursor,
                "import",
                "system_whatsapp_contacts",
                str(slot),
                {"account_slot": slot, "imported": result.get("imported"), "paired": result.get("paired")},
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/catalog/refresh", dependencies=[Depends(authorize_admin)])
def communication_refresh_system_whatsapp_catalog(slot: int) -> dict[str, Any]:
    try:
        system_whatsapp_refresh_catalog(_slot(slot))
        return json_ready(system_whatsapp_center(get_settings()))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.put("/api/v1/communications/system-whatsapp/{slot}/contacts/{contact_id:path}", dependencies=[Depends(authorize_admin)])
def communication_rename_system_whatsapp_contact(
    slot: int, contact_id: str, payload: dict[str, Any], request: Request,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(422, "Enter a contact name")
    try:
        result = system_whatsapp_rename_contact(_slot(slot), contact_id, name)
        with transaction() as (_, cursor):
            audit(
                cursor,
                "update",
                "system_whatsapp_contact",
                contact_id,
                {"account_slot": slot, "name": name},
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/history/sync", dependencies=[Depends(authorize_admin)])
def communication_sync_system_whatsapp_history(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_sync_history(_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.get("/api/v1/communications/system-whatsapp/{slot}/chats/{chat_id:path}", dependencies=[Depends(authorize_admin)])
def communication_system_whatsapp_chat(slot: int, chat_id: str) -> dict[str, Any]:
    if not chat_id or len(chat_id) > 190:
        raise HTTPException(422, "Choose a visible chat")
    try:
        return json_ready(system_whatsapp_chat(_slot(slot), chat_id))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/membership/refresh", dependencies=[Depends(authorize_admin)])
def communication_refresh_system_whatsapp_membership(slot: int) -> dict[str, Any]:
    try:
        system_whatsapp_refresh_membership(_slot(slot))
        return json_ready(system_whatsapp_center(get_settings()))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/membership/{request_id:path}", dependencies=[Depends(authorize_admin)])
def communication_decide_system_whatsapp_membership(
    slot: int, request_id: str, payload: dict[str, Any], request: Request,
) -> dict[str, Any]:
    slot = _slot(slot)
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(422, "Choose approve or reject")
    try:
        result = system_whatsapp_decide_membership(slot, request_id[:500], decision)
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                "VALUES (%s,'system-whatsapp-channel','internal','membership_decision',%s,'processed',%s)",
                (estate_id(), request_id[:190], json.dumps({"account_slot": slot, "request_id": request_id[:500], "decision": decision})),
            )
            audit(
                cursor,
                decision,
                "system_whatsapp_membership",
                request_id[:190],
                {"account_slot": slot, "decision": decision},
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/api/v1/communications/system-whatsapp/{slot}/send", dependencies=[Depends(authorize_admin)])
def communication_send_system_whatsapp(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    slot = _slot(slot)
    account = next(item for item in system_whatsapp_settings()["accounts"] if item["slot"] == slot)
    if not account["send_enabled"]:
        raise HTTPException(403, "Sending is disabled for this linked system account")
    chat_id = str(payload.get("chat_id") or "").strip()[:190]
    body = str(payload.get("body") or "").strip()
    if not chat_id or not body or len(body) > 4096:
        raise HTTPException(422, "Choose a visible chat and enter a message of 1 to 4096 characters")
    if not system_whatsapp_chat_allowed(account, chat_id):
        raise HTTPException(403, "This contact or group is outside the interaction scope for this system account")
    try:
        result = system_whatsapp_send(slot, chat_id, body)
        metadata = {"account_slot": slot, "chat_id": chat_id, "message_id": result.get("message_id"), "preview": body[:180]}
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                "VALUES (%s,'system-whatsapp-channel','outbound','message_sent',%s,'processed',%s)",
                (estate_id(), str(result.get("message_id") or new_id())[:190], json.dumps(metadata)),
            )
            audit(
                cursor,
                "send",
                "system_whatsapp_message",
                str(result.get("message_id") or chat_id),
                metadata,
                request.headers.get("X-Remote-User-Name") or "home-assistant",
            )
        return json_ready(result)
    except HTTPException:
        raise
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,error_message,payload) "
                "VALUES (%s,'system-whatsapp-channel','outbound','message_sent','failed',%s,%s)",
                (estate_id(), str(error)[:1000], json.dumps({"account_slot": slot, "chat_id": chat_id, "preview": body[:180]})),
            )
        raise HTTPException(502, str(error)[:300]) from error


@router.post("/internal/system-whatsapp/inbound")
def system_whatsapp_inbound(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    x_system_whatsapp_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    expected = os.environ.get("SYSTEM_WHATSAPP_BRIDGE_TOKEN", "")
    if not expected or not x_system_whatsapp_token or not hmac.compare_digest(expected, x_system_whatsapp_token):
        raise HTTPException(403, "Forbidden")
    slot = _slot(int(payload.get("account_slot") or 0))
    account = next(item for item in system_whatsapp_settings()["accounts"] if item["slot"] == slot)
    chat_id = str(payload.get("chat_id") or "").strip()[:190]
    is_group = bool(payload.get("is_group"))
    source_enabled = account["ingest_groups"] if is_group else account["ingest_direct"]
    allowed = account["enabled"] and source_enabled and system_whatsapp_chat_allowed(account, chat_id, is_group)
    if not allowed:
        return {"accepted": False, "reason": "Chat is not selected for ingestion"}
    message_id = re.sub(r"[^A-Za-z0-9_.:@=-]", "", str(payload.get("message_id") or ""))[:150]
    if not message_id:
        raise HTTPException(422, "Message ID is required")
    attachment = payload.get("attachment") if isinstance(payload.get("attachment"), dict) else None
    text = str(payload.get("text") or "").strip()
    sender_address = re.sub(r"(?::\d+)?@.+$", "", str(payload.get("sender_id") or chat_id)).strip()[:190]
    try:
        received_at = datetime.fromisoformat(str(payload.get("received_at") or "").replace("Z", "+00:00"))
        received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        received_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        if attachment:
            data = base64.b64decode(str(attachment.get("data_base64") or ""), validate=True)
            filename = str(attachment.get("filename") or f"system-whatsapp-{message_id}")[:180]
            media_type = str(attachment.get("content_type") or "application/octet-stream")[:120]
        else:
            data = text.encode("utf-8")
            filename = f"system-whatsapp-{slot}-{message_id}.txt"
            media_type = "text/plain"
        if not data and not text:
            return {"accepted": False, "reason": "Empty message"}
        digest = hashlib.sha256(data).hexdigest()
        duplicate = fetch_one(
            "SELECT id FROM intake_items WHERE estate_id=%s AND source='whatsapp' AND ABS(TIMESTAMPDIFF(SECOND,received_at,%s))<=120 "
            "AND ((sender_address=%s AND message_text=%s) OR (file_sha256=%s AND file_sha256 IS NOT NULL)) LIMIT 1",
            (estate_id(), received_at, sender_address, text, digest),
        )
        if duplicate:
            return {"accepted": True, "duplicate": True, "record_id": duplicate["id"]}
        record_id = save_intake_file(
            data,
            filename,
            media_type,
            "whatsapp",
            title=f"{account['label']} · {str(payload.get('chat_name') or 'WhatsApp chat')[:120]}",
            message_text=text or str(payload.get("attachment_error") or "Attachment received"),
            external_id=f"system-wa:{slot}:{message_id}",
            sender_name=str(payload.get("sender_name") or "WhatsApp contact")[:160],
            sender_address=sender_address,
        )
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET received_at=%s WHERE id=%s", (received_at, record_id))
    except IntegrityError:
        return {"accepted": True, "duplicate": True}
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)[:300]) from error
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,'system-whatsapp-channel','inbound','message_received',%s,'received',%s)",
            (estate_id(), message_id, json.dumps({"account_slot": slot, "chat_id": chat_id, "is_group": is_group, "record_id": record_id, "message_type": payload.get("message_type")})),
        )
    if settings.openai_api_key:
        background_tasks.add_task(analyze_intake, record_id)
    return {"accepted": True, "record_id": record_id}
