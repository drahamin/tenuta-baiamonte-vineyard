"""Fail-closed candidate identity preparation; never authenticates an account."""

import hashlib
import re

PHONE_JID = "393409695752@s.whatsapp.net"
PHONE_CUS = "393409695752@c.us"


def source_key(message_id: str) -> str:
    return "whatsapp-personal:" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()


def prepare_identity(message_id: str, chat_id: str, sender_id: str, verified_lid: str | None = None) -> dict:
    """Prepare possible keys, without claiming aliases or ID forms are equivalent.

    A caller-provided LID is mapping evidence, not authentication. Composite
    provider IDs are review-only until a trusted adapter and historical ID
    equivalence are independently established.
    """
    if not isinstance(message_id, str) or not message_id or message_id != message_id.strip():
        raise ValueError("Exact platform_message_id is required")
    aliases = {PHONE_JID, PHONE_CUS}
    if verified_lid is not None:
        if not re.fullmatch(r"[0-9]+@lid", verified_lid):
            raise ValueError("Invalid LID mapping evidence")
        aliases.add(verified_lid)
    if chat_id not in aliases or sender_id not in aliases:
        raise ValueError("Only Sebastiano's exact one-to-one personal WhatsApp chat and sender are authorized")
    match = re.fullmatch(r"(true|false)_([^_]+)_([A-Za-z0-9-]{1,128})", message_id)
    if match:
        direction, remote, bare = match.groups()
        if direction != "false" or remote not in aliases:
            raise ValueError("Message direction or chat conflicts with supplied mapping")
    elif re.fullmatch(r"[A-Za-z0-9-]{1,128}", message_id):
        bare = message_id
    else:
        raise ValueError("Unsupported platform message ID format")
    candidate_ids = {message_id, bare} | {f"false_{alias}_{bare}" for alias in aliases}
    return {
        "raw_platform_message_id": message_id,
        "candidate_bare_id": bare,
        "raw_chat_id": chat_id,
        "raw_sender_id": sender_id,
        "verified_lid": verified_lid,
        "candidate_keys": sorted(source_key(value) for value in candidate_ids),
        "exact_key": source_key(message_id),
        "composite": bool(match),
    }
