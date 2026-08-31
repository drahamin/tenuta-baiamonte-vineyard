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
from .db import fetch_all, fetch_one, transaction
from .service import estate_id


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


def _gmail_folders_live() -> list[dict[str, Any]]:
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
        with transaction() as (_, cursor):
            for folder in folders:
                cursor.execute(
                    "INSERT INTO gmail_folder_cache (estate_id,folder_name,folder_label,special_code,synced_at) VALUES (%s,%s,%s,%s,NOW(6)) "
                    "ON DUPLICATE KEY UPDATE folder_label=VALUES(folder_label),special_code=VALUES(special_code),synced_at=NOW(6)",
                    (estate_id(), folder["name"], folder["label"], folder.get("special")),
                )
        return folders
    finally:
        _logout(mailbox)


def _gmail_messages_live(folder: str = "INBOX", view: str = "all", limit: int = 50) -> dict[str, Any]:
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
        matching_ids = result[0].split() if result and result[0] else []
        ids = matching_ids[-limit:]
        if view == "unread":
            unread_total = len(matching_ids)
        else:
            unread_status, unread_result = mailbox.uid("SEARCH", None, "UNSEEN")
            unread_total = len(unread_result[0].split()) if unread_status == "OK" and unread_result and unread_result[0] else 0
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
        with transaction() as (_, cursor):
            if view == "all":
                cursor.execute("DELETE FROM gmail_message_cache WHERE estate_id=%s AND folder_name=%s", (estate_id(), folder))
            for item in messages:
                cursor.execute(
                    "INSERT INTO gmail_message_cache (estate_id,folder_name,message_uid,subject,sender_name,sender_address,recipient_text,sent_at,unread,starred,message_size,synced_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6)) "
                    "ON DUPLICATE KEY UPDATE subject=VALUES(subject),sender_name=VALUES(sender_name),sender_address=VALUES(sender_address),"
                    "recipient_text=VALUES(recipient_text),sent_at=VALUES(sent_at),unread=VALUES(unread),starred=VALUES(starred),message_size=VALUES(message_size),synced_at=NOW(6)",
                    (estate_id(), folder, item["uid"], item["subject"], item.get("sender_name"), item.get("sender_address"),
                     item.get("to"), item.get("sent_at"), int(bool(item.get("unread"))), int(bool(item.get("starred"))), item.get("size")),
                )
        return {"folder": folder, "view": view, "total": total, "unread_total": unread_total, "messages": messages, "cached": False, "synced_at": None}
    finally:
        _logout(mailbox)


def gmail_folders(refresh: bool = False) -> list[dict[str, Any]]:
    cached = fetch_all(
        "SELECT folder_name name,folder_label label,special_code special FROM gmail_folder_cache WHERE estate_id=%s ORDER BY (folder_name='INBOX') DESC,folder_label",
        (estate_id(),),
    )
    if cached and not refresh:
        return cached
    return _gmail_folders_live()


def gmail_messages(folder: str = "INBOX", view: str = "all", limit: int = 50, refresh: bool = False) -> dict[str, Any]:
    folder, limit = _clean_folder(folder), max(1, min(100, int(limit)))
    if refresh:
        return _gmail_messages_live(folder, view, limit)
    where = {"unread": "AND unread=1", "starred": "AND starred=1"}.get(view, "")
    rows = fetch_all(
        "SELECT message_uid uid,folder_name folder,subject,sender_name,sender_address,recipient_text `to`,sent_at,unread,starred,message_size size,synced_at "
        f"FROM gmail_message_cache WHERE estate_id=%s AND folder_name=%s {where} ORDER BY CAST(message_uid AS UNSIGNED) DESC LIMIT %s",
        (estate_id(), folder, limit),
    )
    if not rows:
        return _gmail_messages_live(folder, view, limit)
    newest = rows[0].get("synced_at")
    total = fetch_one("SELECT COUNT(*) total,SUM(unread) unread FROM gmail_message_cache WHERE estate_id=%s AND folder_name=%s", (estate_id(), folder)) or {}
    for row in rows:
        row.pop("synced_at", None)
    return {"folder": folder, "view": view, "total": int(total.get("total") or 0), "unread_total": int(total.get("unread") or 0), "messages": rows, "cached": True, "synced_at": newest}


def gmail_cached_status() -> dict[str, Any]:
    settings = get_settings()
    row = fetch_one(
        "SELECT COUNT(*) total,SUM(unread) unread,MAX(synced_at) synced_at FROM gmail_message_cache WHERE estate_id=%s AND folder_name=%s",
        (estate_id(), settings.gmail_folder or "INBOX"),
    ) or {}
    return {"configured": bool(settings.gmail_address and settings.gmail_app_password), "address": settings.gmail_address or None,
            "folder": settings.gmail_folder or "INBOX", "total": int(row.get("total") or 0),
            "unread": int(row.get("unread") or 0), "cached": True, "synced_at": row.get("synced_at")}


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
    allowed = {"read", "unread", "star", "unstar", "archive", "trash", "junk", "restore", "delete"}
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
            mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Inbox)")
            result = mailbox.uid("STORE", uid, "+X-GM-LABELS", "(\\Trash)")
        elif action == "junk":
            mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Inbox)")
            result = mailbox.uid("STORE", uid, "+X-GM-LABELS", "(\\Spam)")
        elif action == "delete":
            if not re.search(r"trash|cestino", folder, re.IGNORECASE):
                raise ValueError("Permanent deletion is only allowed from Trash")
            result = mailbox.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
            if result[0] == "OK" and mailbox.expunge()[0] != "OK":
                raise RuntimeError("Gmail could not permanently remove the message")
        else:
            mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Trash)")
            mailbox.uid("STORE", uid, "-X-GM-LABELS", "(\\Spam)")
            result = mailbox.uid("STORE", uid, "+X-GM-LABELS", "(\\Inbox)")
        if result[0] != "OK":
            raise RuntimeError("Gmail did not accept the mailbox action")
        return {"updated": True, "uid": uid, "action": action}
    finally:
        _logout(mailbox)
