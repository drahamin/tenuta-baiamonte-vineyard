from datetime import datetime
from unittest.mock import patch

from app.mailbox import gmail_messages


def test_cached_mailbox_avoids_live_gmail_connection():
    cached = [{"uid": "42", "folder": "INBOX", "subject": "Cached", "sender_name": "Sender", "sender_address": "sender@example.com",
               "to": "estate@example.com", "sent_at": "2026-08-22T12:00:00", "unread": 1, "starred": 0, "size": 1200,
               "synced_at": datetime(2026, 8, 22, 12, 1)}]
    with patch("app.mailbox.estate_id", return_value="estate-1"), patch("app.mailbox.fetch_all", return_value=cached), patch("app.mailbox.fetch_one", return_value={"total": 1}), patch(
        "app.mailbox._gmail_messages_live", side_effect=AssertionError("live Gmail must not be opened")
    ):
        result = gmail_messages("INBOX", "all", 60)
    assert result["cached"] is True
    assert result["messages"][0]["subject"] == "Cached"
    assert result["unread_total"] == 0


def test_explicit_refresh_bypasses_mail_cache():
    live = {"folder": "INBOX", "view": "all", "total": 1, "messages": [], "cached": False}
    with patch("app.mailbox._gmail_messages_live", return_value=live) as refresh:
        result = gmail_messages("INBOX", "all", 60, refresh=True)
    refresh.assert_called_once_with("INBOX", "all", 60)
    assert result["cached"] is False
