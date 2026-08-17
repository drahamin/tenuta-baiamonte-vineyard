from __future__ import annotations

import json
from typing import Any


def event_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def whatsapp_delivery_status(row: dict[str, Any]) -> str:
    details = event_payload(row.get("payload"))
    value = str(details.get("delivery_status") or "").lower()
    if value in {"accepted", "sent", "delivered", "read", "failed"}:
        return value
    return "failed" if row.get("status") == "failed" else "accepted"
