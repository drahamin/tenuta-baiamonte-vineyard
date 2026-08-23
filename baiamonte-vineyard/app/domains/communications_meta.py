"""Shared state and normalization for the official Meta WhatsApp channel."""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import get_settings
from ..db import fetch_one, transaction
from ..service import estate_id
from ..whatsapp_observations import ivr_status
from .messaging import event_payload
from .whatsapp_people import sender_profile as build_sender_profile


def contact_book() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts'",
        (estate_id(),),
    ) or {}
    book = event_payload(row.get("setting_value"))
    return {"contacts": list(book.get("contacts") or []), "groups": list(book.get("groups") or [])}


def assistant_settings() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_assistants'",
        (estate_id(),),
    ) or {}
    saved = event_payload(row.get("setting_value"))
    controls = [
        code for code in saved.get("manager_controls", [])
        if code in {"full_refresh", "weather", "cistern", "disease", "public_feed"}
    ]
    ha_entities = [
        str(value) for value in saved.get("home_assistant_entities", [])
        if re.fullmatch(r"(?:light|switch|input_boolean|fan|media_player)\.[a-z0-9_]+", str(value))
    ]
    camera_entities = [
        str(value) for value in saved.get("home_assistant_camera_entities", [])
        if re.fullmatch(r"camera\.[a-z0-9_]+", str(value))
    ]
    return {
        "reception_enabled": bool(saved.get("reception_enabled", False)),
        "manager_enabled": bool(saved.get("manager_enabled", False)),
        "unknown_reception": bool(saved.get("unknown_reception", False)),
        "trusted_ingestion": bool(saved.get("trusted_ingestion", True)),
        "manager_controls": controls or ["weather", "cistern", "disease", "public_feed"],
        "reply_limit_unknown": min(20, max(1, int(saved.get("reply_limit_unknown", 6)))),
        "reply_limit_manager": min(100, max(1, int(saved.get("reply_limit_manager", 30)))),
        "voice": (
            str(saved.get("voice") or "marin")
            if str(saved.get("voice") or "marin") in {"marin", "coral", "shimmer", "nova"}
            else "marin"
        ),
        "home_assistant_entities": ha_entities[:100],
        "home_assistant_camera_entities": camera_entities[:100],
        "ivr": ivr_status(bool(get_settings().openai_api_key)),
    }


def sender_profile(number: str) -> dict[str, Any]:
    return build_sender_profile(number, assistant_settings())


def remember_contact(number: str, name: str | None = None) -> None:
    normalized = re.sub(r"\D", "", number)
    if len(normalized) < 8:
        return
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE",
            (estate_id(),),
        )
        row = cursor.fetchone() or {}
        book = event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        groups = list(book.get("groups") or [])
        existing = next(
            (item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == normalized),
            None,
        )
        if existing:
            if name and (not existing.get("name") or existing.get("name") == normalized):
                existing["name"] = name[:180]
        else:
            assistants = assistant_settings()
            contacts.append({
                "name": (name or normalized)[:180],
                "number": normalized,
                "role": "",
                "assistant": "reception" if assistants.get("unknown_reception") else "off",
                "language": "auto",
                "reply_mode": "match",
                "administrator": False,
            })
        stored = {"contacts": contacts[:100], "groups": groups[:30], "updated_by": "WhatsApp inbound"}
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
