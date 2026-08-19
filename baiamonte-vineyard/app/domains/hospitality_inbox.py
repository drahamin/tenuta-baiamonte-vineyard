from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id


DEFAULT_SETTINGS = {
    "inbound_subjects": ["Inquiry about Reserve Tasting"],
    "default_reply_subject": "Re: {original_subject}",
    "default_reply_body": (
        "Dear {guest_name},\n\nThank you for your interest in visiting Tenuta Baiamonte. "
        "We would be delighted to help arrange a private experience.\n\n"
        "Please let us know your preferred date, time, and number of guests.\n\nWarm regards,\nTenuta Baiamonte"
    ),
}


def _saved_settings() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='hospitality_settings'",
        (estate_id(),),
    ) or {}
    value = row.get("setting_value") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return value if isinstance(value, dict) else {}


def hospitality_settings() -> dict[str, Any]:
    saved = _saved_settings()
    subjects = saved.get("inbound_subjects") or DEFAULT_SETTINGS["inbound_subjects"]
    if isinstance(subjects, str):
        subjects = subjects.splitlines()
    clean_subjects = list(dict.fromkeys(str(item).strip()[:300] for item in subjects if str(item).strip()))[:30]
    return {
        "inbound_subjects": clean_subjects or list(DEFAULT_SETTINGS["inbound_subjects"]),
        "default_reply_subject": str(saved.get("default_reply_subject") or DEFAULT_SETTINGS["default_reply_subject"])[:300],
        "default_reply_body": str(saved.get("default_reply_body") or DEFAULT_SETTINGS["default_reply_body"])[:12000],
        "matching_rule": "Case-insensitive subject phrase; Re: and Fwd: prefixes are ignored",
    }


def save_hospitality_settings(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    subjects = payload.get("inbound_subjects") or []
    if isinstance(subjects, str):
        subjects = subjects.splitlines()
    clean_subjects = list(dict.fromkeys(str(item).strip()[:300] for item in subjects if str(item).strip()))[:30]
    if not clean_subjects:
        raise HTTPException(422, "Enter at least one inbound email subject phrase")
    settings = {
        "inbound_subjects": clean_subjects,
        "default_reply_subject": str(payload.get("default_reply_subject") or DEFAULT_SETTINGS["default_reply_subject"]).strip()[:300],
        "default_reply_body": str(payload.get("default_reply_body") or DEFAULT_SETTINGS["default_reply_body"]).strip()[:12000],
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'hospitality_settings',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(settings)),
        )
        audit(cursor, "update", "hospitality_settings", estate_id(), settings, actor)
    return hospitality_settings()


def _normalized_subject(subject: Any) -> str:
    value = " ".join(str(subject or "").strip().casefold().split())
    while re.match(r"^(re|fw|fwd)\s*:\s*", value):
        value = re.sub(r"^(re|fw|fwd)\s*:\s*", "", value, count=1)
    return value


def hospitality_subject_matches(subject: Any) -> bool:
    return _subject_matches(subject, hospitality_settings()["inbound_subjects"])


def _subject_matches(subject: Any, phrases: list[str]) -> bool:
    normalized = _normalized_subject(subject)
    return bool(normalized) and any(
        _normalized_subject(phrase) in normalized for phrase in phrases
    )


def route_hospitality_inquiry(intake_item_id: str) -> dict[str, Any] | None:
    item = fetch_one(
        "SELECT * FROM intake_items WHERE estate_id=%s AND id=%s AND source='gmail'",
        (estate_id(), intake_item_id),
    )
    if not item or not hospitality_subject_matches(item.get("title")):
        return None
    existing = fetch_one(
        "SELECT * FROM hospitality_inquiries WHERE estate_id=%s AND intake_item_id=%s",
        (estate_id(), intake_item_id),
    )
    if existing:
        return json_ready(existing)
    inquiry_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT IGNORE INTO hospitality_inquiries "
            "(id,estate_id,intake_item_id,status,subject,sender_name,sender_address,received_at,message_text) "
            "VALUES (%s,%s,%s,'new',%s,%s,%s,%s,%s)",
            (
                inquiry_id, estate_id(), intake_item_id, str(item.get("title") or "")[:300],
                str(item.get("sender_name") or "")[:180], str(item.get("sender_address") or "")[:255],
                item.get("received_at"), str(item.get("message_text") or "")[:100000],
            ),
        )
        audit(cursor, "route", "hospitality_inquiry", inquiry_id, {"intake_item_id": intake_item_id}, "gmail-intake")
    return json_ready(fetch_one("SELECT * FROM hospitality_inquiries WHERE estate_id=%s AND intake_item_id=%s", (estate_id(), intake_item_id)))


def sync_hospitality_inquiries(limit: int = 500) -> int:
    rows = fetch_all(
        "SELECT i.id,i.title FROM intake_items i LEFT JOIN hospitality_inquiries h ON h.estate_id=i.estate_id AND h.intake_item_id=i.id "
        "WHERE i.estate_id=%s AND i.source='gmail' AND (i.external_id LIKE '%%:body' OR i.original_filename='message.txt') "
        "AND h.id IS NULL ORDER BY i.received_at DESC LIMIT %s",
        (estate_id(), max(1, min(limit, 2000))),
    )
    phrases = hospitality_settings()["inbound_subjects"]
    return sum(1 for row in rows if _subject_matches(row.get("title"), phrases) and route_hospitality_inquiry(row["id"]))


def inquiries(status: str = "") -> list[dict[str, Any]]:
    params: tuple[Any, ...] = (estate_id(),)
    clause = ""
    if status and status != "all":
        clause = " AND h.status=%s"
        params += (status,)
    return json_ready(fetch_all(
        "SELECT h.*,r.confirmation_code,r.start_at reservation_start_at FROM hospitality_inquiries h "
        "LEFT JOIN hospitality_reservations r ON r.id=h.reservation_id "
        f"WHERE h.estate_id=%s{clause} ORDER BY FIELD(h.status,'new','responded','converted','closed','spam'),h.received_at DESC LIMIT 300",
        params,
    ))


def inquiry(inquiry_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM hospitality_inquiries WHERE estate_id=%s AND id=%s", (estate_id(), inquiry_id))
    if not row:
        raise HTTPException(404, "Guest inquiry not found")
    return json_ready(row)


def update_inquiry(inquiry_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    inquiry(inquiry_id)
    status = str(payload.get("status") or "").strip()
    if status not in {"new", "responded", "converted", "closed", "spam"}:
        raise HTTPException(422, "Choose a valid inquiry status")
    notes = str(payload.get("internal_notes") or "")[:4000]
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE hospitality_inquiries SET status=%s,internal_notes=%s WHERE estate_id=%s AND id=%s",
            (status, notes, estate_id(), inquiry_id),
        )
        audit(cursor, "update", "hospitality_inquiry", inquiry_id, {"status": status, "internal_notes": notes}, actor)
    return inquiry(inquiry_id)


def record_inquiry_response(inquiry_id: str, subject: str, body: str, actor: str) -> dict[str, Any]:
    inquiry(inquiry_id)
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE hospitality_inquiries SET status='responded',response_subject=%s,response_body=%s,responded_at=NOW(6),responded_by=%s "
            "WHERE estate_id=%s AND id=%s",
            (subject[:300], body[:100000], actor, estate_id(), inquiry_id),
        )
        audit(cursor, "respond", "hospitality_inquiry", inquiry_id, {"subject": subject}, actor)
    return inquiry(inquiry_id)


def link_inquiry_to_reservation(inquiry_id: str, reservation_id: str, cursor: Any, actor: str) -> None:
    cursor.execute(
        "UPDATE hospitality_inquiries SET status='converted',reservation_id=%s WHERE estate_id=%s AND id=%s",
        (reservation_id, estate_id(), inquiry_id),
    )
    if cursor.rowcount != 1:
        raise HTTPException(422, "Choose a valid guest inquiry")
    audit(cursor, "convert", "hospitality_inquiry", inquiry_id, {"reservation_id": reservation_id}, actor)


def delete_inquiry(inquiry_id: str, actor: str) -> None:
    before = inquiry(inquiry_id)
    with transaction() as (_, cursor):
        audit(cursor, "delete", "hospitality_inquiry", inquiry_id, before, actor)
        cursor.execute("DELETE FROM hospitality_inquiries WHERE estate_id=%s AND id=%s", (estate_id(), inquiry_id))
