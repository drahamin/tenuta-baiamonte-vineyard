"""Official Meta WhatsApp aggregate, outbound, contact and assistant-admin routes."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from ..access import admin_usernames, authorize, authorize_admin, request_username
from ..config import RUNTIME_OPTIONS_PATH, Settings, get_settings
from ..db import fetch_all, transaction
from ..intelligence import (
    clear_whatsapp_cache,
    create_whatsapp_group,
    gmail_mailbox_status,
    home_assistant_manager_camera_catalog,
    home_assistant_manager_devices,
    send_whatsapp_media,
    send_whatsapp_message,
    whatsapp_diagnostics,
    whatsapp_group_invite_link,
    whatsapp_native_groups,
    whatsapp_phone_number_id,
    whatsapp_phone_numbers,
    whatsapp_templates,
)
from ..mailbox import gmail_cached_status
from ..service import audit, estate_id, json_ready
from ..whatsapp_policy import approved_whatsapp_template
from .communications_meta import assistant_settings, contact_book, sender_profile
from .communications_twilio_voice_routes import twilio_voice_status
from .messaging import event_payload, whatsapp_delivery_status
from .system_whatsapp_control import system_whatsapp_center


router = APIRouter(tags=["communications"])


def _write_runtime_options(values: dict[str, Any]) -> None:
    RUNTIME_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    try:
        loaded = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            current.update(loaded)
    except (OSError, ValueError, TypeError):
        pass
    current.update(values)
    temporary = RUNTIME_OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(RUNTIME_OPTIONS_PATH)


@router.get("/api/v1/communications", dependencies=[Depends(authorize)])
def communication_center(
    request: Request,
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    system_admin = request_username(request) in admin_usernames(settings) | {"api"}
    try:
        mailbox_status = gmail_mailbox_status() if refresh else gmail_cached_status()
    except Exception as error:
        mailbox_status = {
            "configured": bool(settings.gmail_address and settings.gmail_app_password),
            "address": settings.gmail_address or None,
            "folder": settings.gmail_folder or "INBOX",
            "total": None,
            "unread": None,
            "error": str(error)[:240],
        }
    gmail_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,message_text,original_filename,classification,review_status,review_reason,reviewed_by,reviewed_at,ai_summary,processing_error FROM intake_items WHERE estate_id=%s AND source='gmail' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    whatsapp_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,message_text,classification,review_status,review_reason,reviewed_by,reviewed_at,ai_summary,processing_error FROM intake_items WHERE estate_id=%s AND source='whatsapp' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    sent_rows = fetch_all(
        "SELECT id,integration_name,status,payload,error_message,occurred_at FROM integration_events WHERE estate_id=%s AND integration_name IN ('gmail-mailbox','whatsapp-channel','system-whatsapp-channel') AND event_type='message_sent' ORDER BY occurred_at DESC LIMIT 120",
        (estate_id(),),
    )
    gmail_sent = [
        {**row, "details": event_payload(row.get("payload"))}
        for row in sent_rows if row["integration_name"] == "gmail-mailbox"
    ]
    if not system_admin:
        return json_ready({
            "gmail": {"status": mailbox_status, "received": gmail_received, "sent": gmail_sent},
            "whatsapp": {
                "admin_only": True,
                "system_accounts": {"admin_only": True, "available": False, "accounts": [], "sent": []},
            },
        })

    receipt_rows = fetch_all(
        "SELECT external_id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='message_status' AND external_id IS NOT NULL ORDER BY id DESC LIMIT 360",
        (estate_id(),),
    )
    latest_receipts: dict[str, dict[str, Any]] = {}
    receipt_ranks = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
    for receipt in receipt_rows:
        message_id = str(receipt.get("external_id") or "")
        payload = event_payload(receipt.get("payload"))
        current = latest_receipts.get(message_id) or {}
        if message_id and receipt_ranks.get(str(payload.get("status") or "").lower(), 0) >= receipt_ranks.get(str(current.get("status") or "").lower(), 0):
            latest_receipts[message_id] = payload

    book = contact_book()
    contacts = list(book.get("contacts", []))
    contact_numbers = {re.sub(r"\D", "", str(item.get("number") or "")) for item in contacts}
    for message in whatsapp_received:
        number = re.sub(r"\D", "", str(message.get("sender_address") or ""))
        if len(number) >= 8 and number not in contact_numbers:
            contacts.append({
                "name": str(message.get("sender_name") or number), "number": number, "role": "",
                "assistant": "off", "language": "auto", "reply_mode": "match",
            })
            contact_numbers.add(number)

    diagnostics = whatsapp_diagnostics(force=refresh)
    whatsapp_sent = []
    for row in sent_rows:
        if row["integration_name"] != "whatsapp-channel":
            continue
        details = event_payload(row.get("payload"))
        receipt = latest_receipts.get(str(details.get("message_id") or "")) or {}
        delivery_status = str(
            receipt.get("status") or details.get("delivery_status") or whatsapp_delivery_status(row)
        ).lower()
        whatsapp_sent.append({**row, "details": details, "delivery_status": delivery_status})

    active_sender_id = whatsapp_phone_number_id()
    test_sender_id = re.sub(r"\D", "", str(settings.whatsapp_test_phone_number_id or ""))
    inbound_event_rows = fetch_all(
        "SELECT payload,occurred_at FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='message_received' ORDER BY occurred_at DESC LIMIT 180",
        (estate_id(),),
    )
    selected_inbound = []
    for row in inbound_event_rows:
        details = event_payload(row.get("payload"))
        receiver_id = re.sub(r"\D", "", str(details.get("phone_number_id") or ""))
        if receiver_id and receiver_id == active_sender_id:
            selected_inbound.append({**row, "details": details})
    selected_outbound = [
        row for row in whatsapp_sent
        if re.sub(r"\D", "", str((row.get("details") or {}).get("phone_number_id") or "")) == active_sender_id
    ]

    activity_by_number: dict[str, dict[str, Any]] = {}
    for message in whatsapp_received:
        number = re.sub(r"\D", "", str(message.get("sender_address") or ""))
        if number and message.get("received_at"):
            activity = activity_by_number.setdefault(number, {})
            if not activity.get("last_inbound_at") or message["received_at"] > activity["last_inbound_at"]:
                activity["last_inbound_at"] = message["received_at"]
    for message in whatsapp_sent:
        details = message.get("details") or {}
        number = re.sub(r"\D", "", str(details.get("recipient") or ""))
        if number and message.get("occurred_at"):
            activity = activity_by_number.setdefault(number, {})
            if not activity.get("last_outbound_at") or message["occurred_at"] > activity["last_outbound_at"]:
                activity["last_outbound_at"] = message["occurred_at"]
                activity["delivery_status"] = message.get("delivery_status")
    now = datetime.now()
    for contact in contacts:
        activity = activity_by_number.get(re.sub(r"\D", "", str(contact.get("number") or ""))) or {}
        inbound_at, outbound_at = activity.get("last_inbound_at"), activity.get("last_outbound_at")
        last_activity = max((value for value in (inbound_at, outbound_at) if value), default=None)
        window_open = bool(inbound_at and now - inbound_at <= timedelta(hours=24))
        recently_active = bool(last_activity and now - last_activity <= timedelta(days=7))
        contact["presence"] = {
            **activity,
            "last_activity_at": last_activity,
            "conversation_window_open": window_open,
            "recently_active": recently_active,
            "label": "Conversation open" if window_open else "Recent activity" if recently_active else "No recent activity",
        }

    diagnostics["sender_verified"] = bool(diagnostics.get("connected") and diagnostics.get("registered") is not False)
    diagnostics["inbound_verified"] = bool(selected_inbound) or bool(
        whatsapp_received and active_sender_id and active_sender_id != test_sender_id
    )
    diagnostics["inbound_last_at"] = selected_inbound[0].get("occurred_at") if selected_inbound else None
    diagnostics["outbound_verified"] = any(
        row.get("status") == "processed" and str(row.get("delivery_status") or "").lower() in {"sent", "delivered", "read"}
        for row in selected_outbound
    )
    diagnostics["outbound_last_at"] = selected_outbound[0].get("occurred_at") if selected_outbound else None
    latest_selected = selected_outbound[0] if selected_outbound else None
    latest_failure = latest_selected if (latest_selected or {}).get("status") == "failed" else None
    diagnostics["outbound_error"] = str((latest_failure or {}).get("error_message") or "")[:300] or None
    diagnostics["operational"] = bool(
        diagnostics.get("sender_verified") and (diagnostics["inbound_verified"] or diagnostics["outbound_verified"])
    )

    templates = whatsapp_templates(force=refresh)
    sender_catalog = whatsapp_phone_numbers(force=refresh)
    native_groups = whatsapp_native_groups(force=refresh) if settings.whatsapp_native_groups_enabled else {"configured": False, "groups": []}
    assistants = assistant_settings()
    try:
        assistants["home_assistant_device_catalog"] = home_assistant_manager_devices()
        assistants["home_assistant_camera_catalog"] = home_assistant_manager_camera_catalog()
    except Exception:
        assistants["home_assistant_device_catalog"] = []
        assistants["home_assistant_camera_catalog"] = []
    return json_ready({
        "gmail": {"status": mailbox_status, "received": gmail_received, "sent": gmail_sent},
        "whatsapp": {
            "configured": bool(settings.whatsapp_access_token and whatsapp_phone_number_id()),
            "diagnostics": diagnostics,
            "templates": templates.get("templates") or [],
            "templates_error": templates.get("error"),
            "phone_number_id": whatsapp_phone_number_id() or None,
            "senders": sender_catalog.get("senders") or [],
            "senders_error": sender_catalog.get("error"),
            "received": whatsapp_received,
            "sent": whatsapp_sent,
            "contacts": contacts,
            "groups": book.get("groups", []),
            "native_groups": native_groups,
            "assistants": assistants,
            "calling": twilio_voice_status(settings),
            "system_accounts": {
                **system_whatsapp_center(settings),
                "sent": [
                    {**row, "details": event_payload(row.get("payload"))}
                    for row in sent_rows if row["integration_name"] == "system-whatsapp-channel"
                ],
                "separate_from_meta": True,
                "notice": "Linked system accounts are independent from the official Meta Business API.",
            },
        },
    })


@router.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_admin)])
def communication_send_whatsapp(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return send_whatsapp_message(
            str(payload.get("recipient") or ""), str(payload.get("body") or ""),
            str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"),
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp send failed: " + str(error)[:300]) from error


@router.put("/api/v1/communications/whatsapp/sender", dependencies=[Depends(authorize_admin)])
def communication_select_whatsapp_sender(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    phone_number_id = re.sub(r"\D", "", str(payload.get("phone_number_id") or ""))
    catalog = whatsapp_phone_numbers(force=True)
    allowed = {str(item.get("id") or "") for item in catalog.get("senders") or []}
    if not phone_number_id or phone_number_id not in allowed:
        raise HTTPException(422, "Choose a registered number from this WhatsApp Business Account")
    selected = next((item for item in catalog.get("senders") or [] if str(item.get("id")) == phone_number_id), {})
    business_account_id = re.sub(r"\D", "", str(selected.get("business_account_id") or ""))
    if not business_account_id:
        raise HTTPException(422, "The selected sender is not linked to a WhatsApp Business Account")
    _write_runtime_options({
        "whatsapp_active_phone_number_id": phone_number_id,
        "whatsapp_active_business_account_id": business_account_id,
    })
    clear_whatsapp_cache()
    with transaction() as (_, cursor):
        audit(
            cursor, "update", "whatsapp_sender", phone_number_id,
            {"business_account_id": business_account_id, "display_phone_number": selected.get("display_phone_number"), "verified_name": selected.get("verified_name"), "is_test": bool(selected.get("is_test"))},
            request.headers.get("X-Remote-User-Name") or "api",
        )
    return {
        "saved": True, "phone_number_id": phone_number_id, "business_account_id": business_account_id,
        "diagnostics": whatsapp_diagnostics(force=True), "templates": whatsapp_templates(force=True),
    }


@router.post("/api/v1/communications/whatsapp/send-file", dependencies=[Depends(authorize_admin)])
async def communication_send_whatsapp_file(
    recipient: str = Form(...), body: str = Form(""), recipient_type: str = Form("individual"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        data = await file.read(20 * 1024 * 1024 + 1)
        return send_whatsapp_media(recipient, data, file.filename or "attachment", file.content_type or "application/octet-stream", body, recipient_type)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp attachment failed: " + str(error)[:300]) from error


@router.post("/api/v1/communications/whatsapp/broadcast", dependencies=[Depends(authorize_admin)])
def communication_send_whatsapp_list(payload: dict[str, Any]) -> dict[str, Any]:
    group_id = re.sub(r"[^a-zA-Z0-9_.:@-]", "", str(payload.get("group_id") or ""))
    if group_id:
        try:
            result = send_whatsapp_message(group_id, str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"), "group")
            return {"completed": True, "sent": 1, "failed": 0, "native_group": True, "results": [result]}
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(502, "WhatsApp group send failed: " + str(error)[:300]) from error
    recipients = []
    for value in (payload.get("recipients") or [])[:20]:
        number = re.sub(r"\D", "", str(value))
        if len(number) >= 8 and number not in recipients:
            recipients.append(number)
    if not recipients:
        raise HTTPException(422, "Choose at least one contact")
    results = []
    for number in recipients:
        try:
            results.append({"recipient": number, "sent": True, "result": send_whatsapp_message(number, str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"))})
        except Exception as error:
            results.append({"recipient": number, "sent": False, "error": str(error)[:300]})
    return {"completed": True, "sent": sum(1 for row in results if row["sent"]), "failed": sum(1 for row in results if not row["sent"]), "results": results}


@router.get("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize_admin)])
def communication_whatsapp_groups(refresh: bool = False) -> dict[str, Any]:
    return json_ready(whatsapp_native_groups(force=refresh))


@router.post("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize_admin)])
def communication_create_whatsapp_group(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        result = create_whatsapp_group(str(payload.get("subject") or ""), str(payload.get("description") or ""), str(payload.get("join_approval_mode") or "auto_approve"))
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload) VALUES (%s,'whatsapp-channel','outbound','group_create','processed',%s)",
                (estate_id(), json.dumps(result)),
            )
            audit(cursor, "create", "whatsapp_group", str(result.get("id") or result.get("group_id") or "pending"), result, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp group creation failed: " + str(error)[:300]) from error


@router.get("/api/v1/communications/whatsapp/groups/{group_id}/invite-link", dependencies=[Depends(authorize_admin)])
def communication_whatsapp_group_invite(group_id: str) -> dict[str, Any]:
    try:
        return json_ready(whatsapp_group_invite_link(group_id))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp invite link failed: " + str(error)[:300]) from error


@router.put("/api/v1/communications/whatsapp/contacts", dependencies=[Depends(authorize_admin)])
def save_whatsapp_contacts(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    contacts = []
    existing_contacts = {
        re.sub(r"\D", "", str(item.get("number") or "")): item for item in contact_book()["contacts"]
    }
    for row in (payload.get("contacts") or [])[:100]:
        name = str((row or {}).get("name") or "").strip()[:180]
        number = re.sub(r"\D", "", str((row or {}).get("number") or ""))
        role = str((row or {}).get("role") or "").strip()[:180]
        assistant = str((row or {}).get("assistant") or "off").lower()
        language = str((row or {}).get("language") or "auto").lower()
        reply_mode = str((row or {}).get("reply_mode") or "match").lower()
        administrator = bool((row or {}).get("administrator"))
        if assistant not in {"off", "reception", "reporter", "manager"}: assistant = "off"
        if language not in {"auto", "en", "it"}: language = "auto"
        if reply_mode not in {"text", "voice", "both", "match"}: reply_mode = "match"
        if name and len(number) >= 8:
            retained = existing_contacts.get(number) or {}
            contacts.append({
                "name": name, "number": number, "role": role, "assistant": assistant,
                "language": language, "reply_mode": reply_mode, "reply_mode_explicit": True,
                "administrator": administrator,
                **{key: retained[key] for key in (
                    "person_entity", "voice", "ivr_learning_enabled", "ivr_personalized_menu_enabled",
                    "ivr_same_location_enabled", "ivr_ai_fallback_enabled", "ivr_learning_min_completed",
                ) if key in retained},
            })
    known_numbers = {contact["number"] for contact in contacts}
    groups = []
    for row in (payload.get("groups") or [])[:30]:
        name = str((row or {}).get("name") or "").strip()[:180]
        group_id = re.sub(r"[^a-zA-Z0-9_.:@-]", "", str((row or {}).get("group_id") or ""))[:250]
        members = []
        for value in (row or {}).get("members") or []:
            number = re.sub(r"\D", "", str(value))
            if number in known_numbers and number not in members: members.append(number)
        if name and (members or group_id):
            groups.append({"name": name, "members": members, "group_id": group_id or None, "kind": "native_group" if group_id else "delivery_list"})
    stored = {"contacts": contacts, "groups": groups, "updated_by": request.headers.get("X-Remote-User-Name") or "api"}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
    return {"saved": True, "contacts": contacts, "groups": groups}


@router.get("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize_admin)])
def get_whatsapp_assistants() -> dict[str, Any]:
    try:
        catalog, camera_catalog = home_assistant_manager_devices(), home_assistant_manager_camera_catalog()
    except Exception:
        catalog, camera_catalog = [], []
    return json_ready({**assistant_settings(), "home_assistant_device_catalog": catalog, "home_assistant_camera_catalog": camera_catalog})


@router.put("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize_admin)])
def save_whatsapp_assistants(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        safe_catalog = {item["entity_id"] for item in home_assistant_manager_devices()}
        safe_camera_catalog = {item["entity_id"] for item in home_assistant_manager_camera_catalog()}
    except Exception as error:
        raise HTTPException(503, "Home Assistant devices are temporarily unavailable; settings were not changed") from error
    previous = assistant_settings()
    stored = {
        "reception_enabled": bool(payload.get("reception_enabled")),
        "manager_enabled": bool(payload.get("manager_enabled")),
        "unknown_reception": bool(payload.get("unknown_reception")),
        "trusted_ingestion": bool(payload.get("trusted_ingestion")),
        "manager_controls": [code for code in payload.get("manager_controls", []) if code in {"full_refresh", "weather", "cistern", "disease", "public_feed"}],
        "reply_limit_unknown": min(20, max(1, int(payload.get("reply_limit_unknown") or 6))),
        "reply_limit_manager": min(100, max(1, int(payload.get("reply_limit_manager") or 30))),
        "calling_public_reception": bool(payload.get("calling_public_reception", previous.get("calling_public_reception", True))),
        "calling_live_estate_data": bool(payload.get("calling_live_estate_data", previous.get("calling_live_estate_data", True))),
        "calling_guest_language": str(payload.get("calling_guest_language") or previous.get("calling_guest_language") or "auto") if str(payload.get("calling_guest_language") or previous.get("calling_guest_language") or "auto") in {"auto", "en", "it"} else "auto",
        "voice": str(payload.get("voice") or "marin") if str(payload.get("voice") or "marin") in {"marin", "coral", "shimmer", "nova"} else "marin",
        "home_assistant_entities": [str(value) for value in payload.get("home_assistant_entities", []) if str(value) in safe_catalog][:100],
        "home_assistant_camera_entities": [str(value) for value in payload.get("home_assistant_camera_entities", []) if str(value) in safe_camera_catalog][:100],
        "updated_by": request.headers.get("X-Remote-User-Name") or "api",
    }
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_assistants',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (estate_id(), json.dumps(stored)))
        audit(cursor, "update", "whatsapp_assistants", "configuration", {key: value for key, value in stored.items() if key != "updated_by"}, stored["updated_by"])
    return {"saved": True, **assistant_settings()}


@router.put("/api/v1/communications/twilio/voice/preferences", dependencies=[Depends(authorize_admin)])
def save_twilio_voice_preferences(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Save non-secret company-call behavior without touching protected credentials."""
    current = assistant_settings()
    stored = {
        key: value for key, value in current.items()
        if key not in {"ivr", "home_assistant_device_catalog", "home_assistant_camera_catalog"}
    }
    language = str(payload.get("calling_guest_language") or "auto")
    stored.update({
        "calling_public_reception": bool(payload.get("calling_public_reception")),
        "calling_live_estate_data": bool(payload.get("calling_live_estate_data")),
        "calling_guest_language": language if language in {"auto", "en", "it"} else "auto",
        "updated_by": request.headers.get("X-Remote-User-Name") or "api",
    })
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_assistants',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
        audit(cursor, "update", "twilio_voice_preferences", "configuration", {
            key: stored[key] for key in ("calling_public_reception", "calling_live_estate_data", "calling_guest_language")
        }, stored["updated_by"])
    return {"saved": True, **assistant_settings()}


@router.post("/api/v1/communications/whatsapp/assistants/invite", dependencies=[Depends(authorize_admin)])
def invite_whatsapp_manager(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    recipient = re.sub(r"\D", "", str(payload.get("recipient") or ""))
    assignment = sender_profile(recipient)
    if assignment["profile"] not in {"manager", "reporter"}:
        raise HTTPException(422, "Assign this contact as Reporter or Manager and save the address book first")
    catalog = whatsapp_templates(force=True)
    if catalog.get("error"):
        raise HTTPException(503, "Approved WhatsApp templates could not be checked: " + str(catalog["error"])[:220])
    template = approved_whatsapp_template(catalog.get("templates") or [], str(payload.get("template_name") or ""), str(payload.get("template_language") or ""))
    if not template:
        raise HTTPException(422, "Choose an approved Meta template and language for first contact")
    try:
        result = send_whatsapp_message(recipient, template_name=template["name"], template_language=template["language"])
    except Exception as error:
        raise HTTPException(502, "Approved invitation could not be sent: " + str(error)[:260]) from error
    with transaction() as (_, cursor):
        audit(cursor, "send", "whatsapp_assistant_invitation", recipient[-6:], {"profile": assignment["profile"], "contact_language": assignment["language"], "template_name": template["name"], "template_language": template["language"]}, request.headers.get("X-Remote-User-Name") or "home-assistant")
    return {"sent": True, "recipient": recipient, "profile": assignment["profile"], "template_name": template["name"], "template_language": template["language"], "awaiting_reply": True, "result": result}
