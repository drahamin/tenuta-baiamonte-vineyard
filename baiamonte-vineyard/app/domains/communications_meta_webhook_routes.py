"""Signed Meta WhatsApp webhook ingestion routes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pymysql.err import IntegrityError

from ..config import Settings, get_settings
from ..db import transaction
from ..intelligence import (
    analyze_intake,
    download_whatsapp_media,
    quarantine_intake,
    save_intake_file,
    whatsapp_phone_number_id,
)
from ..service import estate_id, new_id
from .communications_meta import remember_contact as _remember_whatsapp_contact
from .communications_meta import sender_profile as _whatsapp_sender_profile
from .communications_whatsapp_assistant import (
    _handle_whatsapp_assistant,
    _handle_whatsapp_voice,
    _send_whatsapp_assistant_reply,
)
from .messaging import event_payload as _event_payload
from .whatsapp_people import sender_is_allowed as _whatsapp_sender_is_allowed


router = APIRouter(tags=["communications"])
logger = logging.getLogger("baiamonte.communications.whatsapp")
_background_tasks: set[asyncio.Task[Any]] = set()


def _background_task_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        logger.exception("WhatsApp background task failed")


def _start_background_task(awaitable: Any) -> asyncio.Task[Any]:
    task = asyncio.create_task(awaitable)
    _background_tasks.add(task)
    task.add_done_callback(_background_task_done)
    return task


async def _analyze_intake_background(record_id: str) -> None:
    await asyncio.to_thread(analyze_intake, record_id)


def _whatsapp_message_body(message: dict[str, Any]) -> str:
    """Return the visible user choice from text and Meta interactive replies."""
    text = str((message.get("text") or {}).get("body") or "").strip()
    if text:
        return text
    message_type = str(message.get("type") or "")
    typed = message.get(message_type) or {}
    if not isinstance(typed, dict):
        return ""
    caption = str(typed.get("caption") or "").strip()
    if caption:
        return caption
    if message_type == "button":
        return str(typed.get("text") or typed.get("payload") or "").strip()
    if message_type == "interactive":
        reply_type = str(typed.get("type") or "")
        reply = typed.get(reply_type) or typed.get("button_reply") or typed.get("list_reply") or {}
        if isinstance(reply, dict):
            return str(reply.get("title") or reply.get("id") or reply.get("description") or "").strip()
    return ""


def _whatsapp_control_event(message: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Identify Meta system interactions that are not messages for the assistant."""
    if str(message.get("type") or "") != "interactive":
        return None
    interactive = message.get("interactive") or {}
    if not isinstance(interactive, dict):
        return None
    interaction_type = str(interactive.get("type") or "").strip()
    if interaction_type != "call_permission_reply":
        return None
    permission = interactive.get("call_permission_reply") or {}
    if not isinstance(permission, dict):
        permission = {}
    return interaction_type, {
        "response": str(permission.get("response") or "unknown")[:60],
        "is_permanent": bool(permission.get("is_permanent")),
        "response_source": str(permission.get("response_source") or "")[:120] or None,
    }


@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    if hub_mode == "subscribe" and settings.whatsapp_verify_token and hmac.compare_digest(hub_verify_token or "", settings.whatsapp_verify_token):
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(403, "Webhook verification failed")


@router.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not settings.whatsapp_app_secret:
        raise HTTPException(503, "WhatsApp App Secret is required before accepting webhook messages")
    expected = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid webhook signature")
    payload = json.loads(raw or b"{}")
    allowed = {number.strip().replace("+", "") for number in settings.whatsapp_allowed_numbers.split(",") if number.strip()}
    expected_receiver_phone_number_id = re.sub(r"\D", "", str(whatsapp_phone_number_id() or ""))
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            receiver_phone_number_id = re.sub(r"\D", "", str((value.get("metadata") or {}).get("phone_number_id") or ""))
            field = str(change.get("field") or "")
            if receiver_phone_number_id and expected_receiver_phone_number_id and receiver_phone_number_id != expected_receiver_phone_number_id:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                        "VALUES (%s,'whatsapp-channel','inbound','receiver_ignored',%s,'processed',%s)",
                        (estate_id(), receiver_phone_number_id[:190], json.dumps({"field": field, "reason": "receiver_phone_number_id_mismatch"})),
                    )
                continue
            if field in {"group_lifecycle_update", "group_participants_update", "group_settings_update", "group_status_update"}:
                group_external_id = str(value.get("group_id") or value.get("id") or new_id())[:190]
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                        "VALUES (%s,'whatsapp-channel','inbound',%s,%s,'received',%s)",
                        (estate_id(), field, group_external_id, json.dumps(value)),
                    )
            for status_item in value.get("statuses", []):
                message_id = str(status_item.get("id") or "")[:190] or None
                delivery_status = str(status_item.get("status") or "unknown")[:60]
                event_status = "failed" if delivery_status == "failed" else "processed" if delivery_status in {"sent", "delivered", "read"} else "received"
                errors = status_item.get("errors") or []
                with transaction() as (_, cursor):
                    cursor.execute(
                        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
                        "AND event_type='message_sent' AND external_id=%s ORDER BY id DESC LIMIT 1 FOR UPDATE",
                        (estate_id(), message_id),
                    )
                    sent_row = cursor.fetchone()
                    if sent_row:
                        sent_payload = _event_payload(sent_row.get("payload"))
                        current_status = str(sent_payload.get("delivery_status") or "accepted").lower()
                        ranks = {"accepted": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
                        if ranks.get(delivery_status, -1) >= ranks.get(current_status, -1):
                            sent_payload["delivery_status"] = delivery_status
                            sent_payload["delivery_timestamp"] = status_item.get("timestamp")
                            if status_item.get("conversation"):
                                sent_payload["conversation"] = status_item.get("conversation")
                            if status_item.get("pricing"):
                                sent_payload["pricing"] = status_item.get("pricing")
                            cursor.execute(
                                "UPDATE integration_events SET status=%s,payload=%s,error_message=%s WHERE id=%s",
                                (event_status, json.dumps(sent_payload), json.dumps(errors)[:1000] if errors else None, sent_row["id"]),
                            )
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload,error_message) VALUES (%s,'whatsapp-channel','inbound','message_status',%s,%s,%s,%s)",
                        (estate_id(), message_id, event_status, json.dumps(status_item), json.dumps(errors)[:1000] if errors else None),
                    )
            contacts = {contact.get("wa_id"): (contact.get("profile") or {}).get("name") for contact in value.get("contacts", [])}
            for message in value.get("messages", []):
                sender = str(message.get("from") or "").replace("+", "")
                sender_assignment = _whatsapp_sender_profile(sender)
                sender_allowed = _whatsapp_sender_is_allowed(sender, allowed, sender_assignment)
                _remember_whatsapp_contact(sender, contacts.get(sender))
                message_type = message.get("type") or "unknown"
                message_id = str(message.get("id") or new_id())
                control_event = _whatsapp_control_event(message)
                if control_event:
                    control_type, control_details = control_event
                    with transaction() as (_, cursor):
                        cursor.execute(
                            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                            "VALUES (%s,'whatsapp-channel','inbound',%s,%s,'processed',%s)",
                            (
                                estate_id(),
                                control_type,
                                message_id[:190],
                                json.dumps({"sender": sender, **control_details}),
                            ),
                        )
                    continue
                typed_content = message.get(message_type)
                media = typed_content if isinstance(typed_content, dict) else {}
                body = _whatsapp_message_body(message)
                group_id = str(message.get("group_id") or "")[:300]
                source_title = f"WhatsApp group {group_id[-10:]} · {message_type}" if group_id else f"WhatsApp {message_type}"
                saved_any = False
                if body:
                    try:
                        record_id = save_intake_file(body.encode(), f"whatsapp-{message_id}.txt", "text/plain", "whatsapp", source_title, body, message_id + ":body", contacts.get(sender), sender)
                        saved_any = True
                        if sender_allowed:
                            if group_id and settings.openai_api_key:
                                _start_background_task(_analyze_intake_background(record_id))
                            else:
                                _start_background_task(_handle_whatsapp_assistant(sender, body, message_id, record_id, group_id))
                        else:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                    except IntegrityError:
                        pass
                media_id = str(media.get("id") or "") if message_type in {"image", "document", "audio", "video", "sticker"} else ""
                if media_id:
                    try:
                        data, generated_name, content_type = await asyncio.to_thread(download_whatsapp_media, media_id)
                        filename = str(media.get("filename") or generated_name)
                        media_title = f"{source_title}: {filename}"
                        record_id = save_intake_file(data, filename, content_type, "whatsapp", media_title, body, message_id + ":media", contacts.get(sender), sender)
                        saved_any = True
                        if not sender_allowed:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                        visual_analysis_started = bool(sender_allowed and settings.openai_api_key and message_type in {"image", "video"})
                        if visual_analysis_started:
                            _start_background_task(_analyze_intake_background(record_id))
                        if message_type == "audio" and not group_id and settings.openai_api_key and sender_assignment["profile"] in {"manager", "reporter"}:
                            _start_background_task(_handle_whatsapp_voice(sender, data, filename, message_id, contacts.get(sender) or sender, group_id, record_id))
                        elif not body and not group_id:
                            media_prompt = {
                                "image": "Photo received for vineyard review",
                                "document": "Document received for vineyard review",
                                "video": "Video received for vineyard review",
                                "sticker": "Sticker received",
                                "audio": "Voice note received for vineyard review",
                            }.get(message_type, "Attachment received for vineyard review")
                            _start_background_task(_handle_whatsapp_assistant(sender, media_prompt, message_id, record_id, group_id))
                        elif settings.openai_api_key and not visual_analysis_started:
                            _start_background_task(_analyze_intake_background(record_id))
                    except IntegrityError:
                        pass
                    except Exception as error:
                        with transaction() as (_, cursor):
                            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message) VALUES (%s,'whatsapp-channel','inbound','media_download',%s,'failed',%s)", (estate_id(), message_id[:190], str(error)[:1000]))
                        if sender_allowed and not group_id:
                            _start_background_task(_send_whatsapp_assistant_reply(sender, "Allegato ricevuto, ma il download non è riuscito. L'errore è stato registrato." if sender_assignment["language"] == "it" else "Attachment received, but download failed. The error was logged.", sender_assignment))
                if not body and not media_id:
                    fallback = json.dumps({"message_type": message_type, "content": typed_content, "context": message.get("context")}, ensure_ascii=False, default=str)[:12000]
                    try:
                        record_id = save_intake_file(fallback.encode(), f"whatsapp-{message_id}-{message_type}.json", "application/json", "whatsapp", source_title, fallback, message_id + ":unsupported", contacts.get(sender), sender)
                        saved_any = True
                        if not sender_allowed:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                        elif not group_id:
                            _start_background_task(_handle_whatsapp_assistant(sender, f"WhatsApp {message_type} message received for review", message_id, record_id, group_id))
                    except IntegrityError:
                        pass
                if saved_any:
                    route = "quarantine" if not sender_allowed else "group_review" if group_id else sender_assignment["profile"] if sender_assignment["profile"] != "off" else "administrator_review"
                    with transaction() as (_, cursor):
                        cursor.execute(
                            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','message_received',%s,'received',%s)",
                            (estate_id(), message_id[:190], json.dumps({"sender": sender, "sender_allowed": sender_allowed, "message_type": message_type, "route": route, "group_id": group_id or None, "phone_number_id": receiver_phone_number_id or None})),
                        )
    return {"received": True}
