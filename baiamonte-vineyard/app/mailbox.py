"""Small, recoverable Gmail mailbox controls for the operations UI."""

from __future__ import annotations

import html
import imaplib
import re
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from .config import get_settings


def _clean_folder(folder: str | None) -> str:
    value = (folder or "INBOX").strip()
    if not value or len(value) > 250 or any(character in value for character in "\r\n\0"):
        raise ValueError("Invalid mailbox folder")
    return value


def _clean_uid(uid: str | int) -> str:
    value = str(uid).strip()
    if not value.isdigit():
        raise ValueError("Invalid message identifier")
    return value


def _decode(value: str | None) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return str(value or "")


def _connect() -> imaplib.IMAP4_SSL:
    settings = get_settings()
    if not settings.gmail_address or not settings.gmail_app_password:
        raise ValueError("Gmail is not configured")
    mailbox = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
    mailbox.login(settings.gmail_address, settings.gmail_app_password)
    return mailbox


def _logout(mailbox: imaplib.IMAP4_SSL) -> None:
    try:
        mailbox.logout()
    except Exception:
        pass


def _raw_message(mailbox: imaplib.IMAP4_SSL, uid: str) -> bytes:
    status, payload = mailbox.uid("FETCH", uid, "(BODY.PEEK[])")
    raw = next((part[1] for part in payload or [] if isinstance(part, tuple)), None)
    if status != "OK" or not raw:
        raise LookupError("Message not found")
    return raw


def _plain_body(message: Any) -> str:
    body = message.get_body(preferencelist=("plain",))
    if body:
        try:
            return str(body.get_content()).strip()
        except Exception:
            pass
    body = message.get_body(preferencelist=("html",))
    if not body:
        return ""
    try:
        value = str(body.get_content())
    except Exception:
        return ""
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"(?s)<[^>]+>", " ", value))).strip()


def gmail_folders() -> list[dict[str, Any]]:
    mailbox = _connect()
    try:
        status, rows = mailbox.list()
        if status != "OK":
            return [{"name": "INBOX", "label": "Inbox", "special": "inbox"}]
        folders: list[dict[str, Any]] = []
        for raw in rows or []:
            text = raw.decode(errors="replace")
            match = re.match(r'^\((?P<flags>[^)]*)\)\s+"[^"]*"\s+(?P<name>.+)$', text)
            if not match:
                continue
            name = match.group("name").strip().strip('"')
            flags = match.group("flags")
            if "\\Noselect" in flags:
                continue
            special = next((code for flag, code in (("\\All", "all"), ("\\Sent", "sent"), ("\\Drafts", "drafts"), ("\\Junk", "spam"), ("\\Trash", "trash"), ("\\Flagged", "starred")) if flag in flags), None)
            folders.append({"name": name, "label": "Inbox" if name.upper() == "INBOX" else name.rsplit("/", 1)[-1], "special": special or ("inbox" if name.upper() == "INBOX" else None)})
        folders.sort(key=lambda item: (0 if item["name"].upper() == "INBOX" else 1, item["label"].casefold()))
        return folders
    finally:
        _logout(mailbox)


def gmail_messages(folder: str = "INBOX", view: str = "all", limit: int = 50) -> dict[str, Any]:
    folder = _clean_folder(folder)
    limit = max(1, min(100, int(limit)))
    mailbox = _connect()
    try:
        status, selected = mailbox.select(folder, readonly=True)
        if status != "OK":
            raise ValueError("Mailbox folder could not be opened")
        criterion = {"unread": "UNSEEN", "starred": "FLAGGED"}.get(view, "ALL")
        status, result = mailbox.uid("SEARCH", None, criterion)
        if status != "OK":
            raise RuntimeError("Mailbox search failed")
        ids = (result[0].split() if result and result[0] else [])[-limit:]
        messages: list[dict[str, Any]] = []
        for uid_bytes in reversed(ids):
            uid = uid_bytes.decode()
            status, payload = mailbox.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID)] FLAGS RFC822.SIZE)")
            raw = next((part[1] for part in payload or [] if isinstance(part, tuple)), b"")
            meta = next((part[0].decode(errors="replace") for part in payload or [] if isinstance(part, tuple)), "")
            if status != "OK" or not raw:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw)
            sender_name, sender_address = parseaddr(_decode(message.get("From")))
            flags_match = re.search(r"FLAGS \((.*?)\)", meta)
            flags = flags_match.group(1) if flags_match else ""
            size_match = re.search(r"RFC822.SIZE (\d+)", meta)
            try:
                sent_at = parsedate_to_datetime(message.get("Date")).isoformat() if message.get("Date") else None
            except Exception:
                sent_at = message.get("Date")
            messages.append({
                "uid": uid, "folder": folder, "subject": _decode(message.get("Subject")) or "(no subject)",
                "sender_name": sender_name, "sender_address": sender_address, "to": _decode(message.get("To")),
                "sent_at": sent_at, "unread": "\\Seen" not in flags, "starred": "\\Flagged" in flags,
                "size": int(size_match.group(1)) if size_match else None,
            })
        total = int(selected[0]) if selected and selected[0] else 0
        return {"folder": folder, "view": view, "total": total, "messages": messages}
    finally:
        _logout(mailbox)


def gmail_message(uid: str, folder: str = "INBOX", mark_read: bool = True) -> dict[str, Any]:
    uid, folder = _clean_uid(uid), _clean_folder(folder)
    mailbox = _connect()
    try:
        if mailbox.select(folder, readonly=not mark_read)[0] != "OK":
            raise ValueError("Mailbox folder could not be opened")
        raw = _raw_message(mailbox, uid)
        if mark_read:
            mailbox.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        message = BytesParser(policy=policy.default).parsebytes(raw)
        sender_name, sender_address = parseaddr(_decode(message.get("From")))
        attachments = []
        for index, part in enumerate(message.iter_attachments()):
            data = part.get_payload(decode=True) or b""
            attachments.append({"index": index, "filename": _decode(part.get_filename()) or f"attachment-{index + 1}", "content_type": part.get_content_type(), "size": len(data)})
        return {
            "uid": uid, "folder": folder, "subject": _decode(message.get("Subject")) or "(no subject)",
            "sender_name": sender_name, "sender_address": sender_address, "to": _decode(message.get("To")),
            "cc": _decode(message.get("Cc")), "date": _decode(message.get("Date")), "body": _plain_body(message)[:250000],
            "attachments": attachments,
        }
    finally:
        _logout(mailbox)


def gmail_download(uid: str, folder: str = "INBOX", attachment_index: int | None = None) -> tuple[bytes, str, str]:
    uid, folder = _clean_uid(uid), _clean_folder(folder)
    mailbox = _connect()
    try:
        if mailbox.select(folder, readonly=True)[0] != "OK":
            raise ValueError("Mailbox folder could not be opened")
        raw = _raw_message(mailbox, uid)
        if attachment_index is None:
            return raw, f"message-{uid}.eml", "message/rfc822"
        message = BytesParser(policy=policy.default).parsebytes(raw)
        attachments = list(message.iter_attachments())
        if attachment_index < 0 or attachment_index >= len(attachments):
            raise LookupError("Attachment not found")
        part = attachments[attachment_index]
        return part.get_payload(decode=True) or b"", _decode(part.get_filename()) or f"attachment-{attachment_index + 1}", part.get_content_type()
    finally:
        _logout(mailbox)


def gmail_message_action(uid: str, action: str, folder: str = "INBOX") -> dict[str, Any]:
    uid, folder = _clean_uid(uid), _clean_folder(folder)
    allowed = {"read", "unread", "star", "unstar", "archive", "trash", "restore"}
    if action not in allowed:
        raise ValueError("Unsupported mailbox action")
    mailbox = _connect()
    try:
        if mailbox.select(folder, readonly=False)[0] != "OK":
            raise ValueError("Mailbox folder could not be opened")
        if action == "read":
            result = mailbox.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        elif action == "unread":
            result = mailbox.uid("STORE", uid, "-FLAGS", "(\\Seen)")
        elif action == "star":
            result = mailbox.uid("STORE", uid, "+FLAGS", "(\\Flagged)")
        elif action == "unstar":
            result = mailbox.uid("STORE", uid, "-FLAGS", "(\\Flagged)")
        elif action == "archive":
            result = mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Inbox)")
        elif action == "trash":
            result = mailbox.uid("STORE", uid, "+X-GM-LABELS", "(\\Trash)")
        else:
            mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Trash)")
            result = mailbox.uid("STORE", uid, "+X-GM-LABELS", "(\\Inbox)")
        if result[0] != "OK":
            raise RuntimeError("Gmail did not accept the mailbox action")
        return {"updated": True, "uid": uid, "action": action}
    finally:
        _logout(mailbox)
