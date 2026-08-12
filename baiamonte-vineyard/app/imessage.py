"""Optional bridge to a Mac signed into Apple Messages.

The bridge is deliberately vendor-neutral.  A small Mac relay exposes the
documented Baiamonte endpoints and keeps the Apple account off Home Assistant.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings


def _normalized_handle(value: str) -> str:
    value = value.strip().casefold()
    return value if "@" in value else "".join(character for character in value if character.isdigit())


def _allowed_handles() -> set[str]:
    return {_normalized_handle(value) for value in get_settings().imessage_allowed_handles.split(",") if _normalized_handle(value)}


def _conversation_handles(conversation: dict[str, Any]) -> set[str]:
    values = conversation.get("participants") or conversation.get("handles") or []
    if isinstance(values, str):
        values = [values]
    handles = set()
    for value in values:
        raw = value.get("handle") or value.get("address") or value.get("id") if isinstance(value, dict) else value
        if raw and _normalized_handle(str(raw)):
            handles.add(_normalized_handle(str(raw)))
    return handles


def _request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    base = settings.imessage_bridge_url.strip().rstrip("/")
    if not base or not settings.imessage_bridge_token:
        raise ValueError("iMessage Mac bridge is not configured")
    if not base.startswith(("http://", "https://")):
        raise ValueError("iMessage bridge URL must start with http:// or https://")
    request = urllib.request.Request(
        base + "/" + path.lstrip("/"),
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {settings.imessage_bridge_token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read() or b"{}").get("detail")
        except Exception:
            detail = None
        raise RuntimeError(str(detail or error)[:400]) from error


def imessage_status() -> dict[str, Any]:
    settings = get_settings()
    configured = bool(settings.imessage_bridge_url and settings.imessage_bridge_token)
    if not configured:
        return {"configured": False, "connected": False, "error": "Add the Mac bridge URL and token in Home Assistant app configuration."}
    try:
        result = _request("api/v1/status")
        return {"configured": True, "connected": bool(result.get("connected", True)), "mac": result.get("mac"), "account": result.get("account"), "version": result.get("version")}
    except Exception as error:
        return {"configured": True, "connected": False, "error": str(error)[:300]}


def imessage_conversations(limit: int = 50) -> list[dict[str, Any]]:
    result = _request("api/v1/conversations?limit=" + str(max(1, min(100, int(limit)))))
    rows = list(result.get("conversations") or [])
    allowed = _allowed_handles()
    return [row for row in rows if not allowed or bool(_conversation_handles(row) & allowed)]


def send_imessage(recipient: str, body: str, conversation_id: str = "", attachment: tuple[str, str, bytes] | None = None) -> dict[str, Any]:
    clean_body = body.strip()
    if not clean_body and not attachment:
        raise ValueError("Message or attachment is required")
    if not recipient.strip() and not conversation_id.strip():
        raise ValueError("Choose a conversation or enter a phone number / Apple address")
    allowed = _allowed_handles()
    if allowed:
        if recipient.strip() and _normalized_handle(recipient) not in allowed:
            raise ValueError("This recipient is not in the vineyard iMessage allowlist")
        if conversation_id.strip():
            conversation = next((row for row in imessage_conversations(100) if str(row.get("id") or row.get("guid")) == conversation_id.strip()), None)
            if not conversation or not (_conversation_handles(conversation) & allowed):
                raise ValueError("This conversation is not in the vineyard iMessage allowlist")
    payload: dict[str, Any] = {"recipient": recipient.strip()[:250], "conversation_id": conversation_id.strip()[:250], "body": clean_body[:10000]}
    if attachment:
        filename, content_type, data = attachment
        if not data or len(data) > 20 * 1024 * 1024:
            raise ValueError("Attachment must be 20 MB or smaller")
        payload["attachment"] = {
            "filename": filename[:180], "content_type": content_type[:120], "data_base64": base64.b64encode(data).decode(),
        }
    return _request("api/v1/messages", "POST", payload)
