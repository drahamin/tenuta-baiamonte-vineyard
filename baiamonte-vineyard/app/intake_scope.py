"""Exact source-message families; account prefixes are never message identities."""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID


PART = re.compile(r"^(.*):(body|media|transcript|unsupported|attachment-[0-9]+)$")


def source_message_key(item: dict[str, Any]) -> str:
    external = str(item.get("external_id") or "")
    source = item.get("source")
    # System-account IDs are atomic, even when the provider message ID contains colons.
    # Codex/user-supplied IDs are also opaque; their punctuation is not a relationship.
    if source in {"gmail", "whatsapp"} and not external.startswith("system-wa:"):
        match = PART.fullmatch(external)
        if match and match[1]:
            return match[1]
    return external or str(item["id"])


def native_message_family(item: dict[str, Any]) -> tuple[str, str] | None:
    external = str(item.get("external_id") or "")
    if item.get("source") not in {"gmail", "whatsapp"} or external.startswith("system-wa:"):
        return None
    match = PART.fullmatch(external)
    return (match[1], match[2]) if match and match[1] else None


def manual_parent_id(item: dict[str, Any]) -> str | None:
    metadata = item.get("source_metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            return None
    if not isinstance(metadata, dict) or metadata.get("attachment_recovery") is not True:
        return None
    try:
        return str(UUID(str(metadata.get("manually_attached_to") or "")))
    except ValueError:
        return None


def literal_like_prefix(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
