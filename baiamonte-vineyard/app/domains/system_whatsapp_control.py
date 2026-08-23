"""Configuration and status assembly for linked system WhatsApp accounts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from ..db import fetch_one, transaction
from ..service import estate_id
from ..system_whatsapp import system_whatsapp_accounts
from .messaging import event_payload


def system_whatsapp_settings() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='system_whatsapp_accounts'",
        (estate_id(),),
    ) or {}
    saved = event_payload(row.get("setting_value"))
    stored = {int(item.get("slot") or 0): item for item in saved.get("accounts", []) if isinstance(item, dict)}
    accounts = []
    for slot in (1, 2):
        item = stored.get(slot, {})
        accounts.append({
            "slot": slot,
            "label": str(item.get("label") or f"System account {slot}")[:80],
            "enabled": bool(item.get("enabled", True)),
            "ingest_direct": bool(item.get("ingest_direct", True)),
            "ingest_groups": bool(item.get("ingest_groups", True)),
            "contact_scope": "selected" if str(item.get("contact_scope") or "all") == "selected" else "all",
            "selected_contact_ids": [str(value)[:190] for value in item.get("selected_contact_ids", []) if str(value).strip()][:250],
            "monitor_all": bool(item.get("monitor_all", False)),
            "selected_chat_ids": [str(value)[:190] for value in item.get("selected_chat_ids", []) if str(value).strip()][:250],
            "send_enabled": bool(item.get("send_enabled", False)),
        })
    return {"accounts": accounts}


def save_system_whatsapp_settings(payload: dict[str, Any]) -> dict[str, Any]:
    raw = {int(item.get("slot") or 0): item for item in payload.get("accounts", []) if isinstance(item, dict)}
    accounts = []
    for slot in (1, 2):
        item = raw.get(slot, {})
        accounts.append({
            "slot": slot,
            "label": str(item.get("label") or f"System account {slot}").strip()[:80],
            "enabled": bool(item.get("enabled", True)),
            "ingest_direct": bool(item.get("ingest_direct", True)),
            "ingest_groups": bool(item.get("ingest_groups", True)),
            "contact_scope": "selected" if str(item.get("contact_scope") or "all") == "selected" else "all",
            "selected_contact_ids": list(dict.fromkeys(str(value).strip()[:190] for value in item.get("selected_contact_ids", []) if str(value).strip()))[:250],
            "monitor_all": bool(item.get("monitor_all", False)),
            "selected_chat_ids": list(dict.fromkeys(str(value).strip()[:190] for value in item.get("selected_chat_ids", []) if str(value).strip()))[:250],
            "send_enabled": bool(item.get("send_enabled", False)),
        })
    stored = {"accounts": accounts, "updated_at": datetime.now(timezone.utc).isoformat()}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'system_whatsapp_accounts',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
    return stored


def system_whatsapp_chat_allowed(account: dict[str, Any], chat_id: str, is_group: bool | None = None) -> bool:
    group = chat_id.endswith("@g.us") if is_group is None else is_group
    if group:
        return bool(account["monitor_all"]) or chat_id in account["selected_chat_ids"]
    return account["contact_scope"] == "all" or chat_id in account["selected_contact_ids"]


def _saved_contact_names() -> dict[str, str]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts'",
        (estate_id(),),
    ) or {}
    book = event_payload(row.get("setting_value"))
    return {
        re.sub(r"\D", "", str(contact.get("number") or "")): str(contact.get("name") or "").strip()
        for contact in book.get("contacts", [])
        if re.sub(r"\D", "", str(contact.get("number") or "")) and str(contact.get("name") or "").strip()
    }


def system_whatsapp_center(settings: Settings) -> dict[str, Any]:
    configured = system_whatsapp_settings()
    if not settings.system_whatsapp_enabled:
        return {
            "available": False,
            "error": "System WhatsApp accounts are disabled in Home Assistant configuration",
            **configured,
        }
    try:
        live = system_whatsapp_accounts()
        by_slot = {int(item.get("slot") or 0): item for item in live.get("accounts", [])}
        saved_names = _saved_contact_names()
        accounts = []
        for item in configured["accounts"]:
            account = {**item, **by_slot.get(item["slot"], {})}
            account["contacts"] = [
                {
                    **contact,
                    "name": saved_names.get(re.sub(r"\D", "", str(contact.get("number") or ""))) or contact.get("name"),
                }
                for contact in account.get("contacts", [])
            ]
            accounts.append(account)
        return {"available": True, "accounts": accounts}
    except Exception as error:
        return {"available": False, "error": str(error)[:300], **configured}
