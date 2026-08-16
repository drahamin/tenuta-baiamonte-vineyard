from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


BRIDGE_URL = "http://127.0.0.1:8110"


def _request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = os.environ.get("SYSTEM_WHATSAPP_BRIDGE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("System WhatsApp bridge token is unavailable")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        BRIDGE_URL + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error")
        except (ValueError, AttributeError):
            detail = None
        raise RuntimeError(detail or f"System WhatsApp bridge returned {error.code}") from error
    except (OSError, ValueError) as error:
        raise RuntimeError("System WhatsApp bridge is unavailable: " + str(error)) from error


def system_whatsapp_accounts() -> dict[str, Any]:
    return _request("/accounts")


def system_whatsapp_connect(slot: int, restart: bool = False) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/connect", "POST", {"restart": restart})


def system_whatsapp_disconnect(slot: int) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/disconnect", "POST", {})


def system_whatsapp_send(slot: int, chat_id: str, text: str) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/send", "POST", {"chat_id": chat_id, "text": text})


def system_whatsapp_add_contact(slot: int, name: str, number: str) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/contacts", "POST", {"name": name, "number": number})


def system_whatsapp_chat(slot: int, chat_id: str) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/chats/{urllib.parse.quote(chat_id, safe='')}/messages")


def system_whatsapp_refresh_membership(slot: int) -> dict[str, Any]:
    return _request(f"/accounts/{slot}/membership/refresh", "POST", {})


def system_whatsapp_decide_membership(slot: int, request_id: str, decision: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(request_id, safe="")
    return _request(f"/accounts/{slot}/membership/{encoded}", "POST", {"decision": decision})
