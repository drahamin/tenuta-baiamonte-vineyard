from contextlib import contextmanager
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import intelligence


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        gmail_address="estate@example.com",
        gmail_app_password="secret",
        gmail_folder="INBOX",
        gmail_allowed_senders="",
        openai_api_key="",
    )


def _header(uid: str) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = f"<{uid}@example.com>"
    message["From"] = "Cellar <cellar@example.com>"
    message["To"] = "estate@example.com"
    message["Subject"] = f"Cellar update {uid}"
    return message.as_bytes()


def _full_message(uid: str) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = f"<{uid}@example.com>"
    message["From"] = "Cellar <cellar@example.com>"
    message["To"] = "estate@example.com"
    message["Subject"] = f"Cellar update {uid}"
    message.set_content("Routine cellar update")
    return message.as_bytes()


@contextmanager
def _transaction():
    yield None, MagicMock()


def _mailbox() -> tuple[MagicMock, list[str]]:
    mailbox = MagicMock()
    full_fetches: list[str] = []

    def uid(command: str, uid: str | None, query: str):
        if command == "SEARCH":
            return "OK", [b" ".join(str(index).encode() for index in range(1, 51))]
        metadata = f'{uid} (X-GM-LABELS () FLAGS (\\Seen) RFC822.SIZE 250)'.encode()
        if "BODY.PEEK[]" in query:
            full_fetches.append(str(uid))
            return "OK", [(metadata, _full_message(str(uid)))]
        return "OK", [(metadata, _header(str(uid)))]

    mailbox.uid.side_effect = uid
    return mailbox, full_fetches


def test_existing_gmail_records_use_headers_without_redownloading_mime() -> None:
    mailbox, full_fetches = _mailbox()
    with (
        patch.object(intelligence, "get_settings", return_value=_settings()),
        patch.object(intelligence, "_trusted_gmail_senders", return_value=set()),
        patch.object(intelligence.imaplib, "IMAP4_SSL", return_value=mailbox) as connector,
        patch.object(intelligence, "fetch_one", return_value={"id": "saved", "message_text": "Routine"}),
        patch.object(intelligence, "transaction", side_effect=_transaction),
        patch.object(intelligence, "hospitality_message_matches", return_value=False),
        patch.object(intelligence, "estate_id", return_value="estate"),
    ):
        assert intelligence.poll_gmail_once() == 0

    connector.assert_called_once_with("imap.gmail.com", timeout=intelligence.GMAIL_SOCKET_TIMEOUT_SECONDS)
    assert full_fetches == []


def test_new_gmail_downloads_are_bounded_per_poll() -> None:
    mailbox, full_fetches = _mailbox()
    with (
        patch.object(intelligence, "get_settings", return_value=_settings()),
        patch.object(intelligence, "_trusted_gmail_senders", return_value=set()),
        patch.object(intelligence.imaplib, "IMAP4_SSL", return_value=mailbox),
        patch.object(intelligence, "fetch_one", return_value=None),
        patch.object(intelligence, "fetch_all", return_value=[]),
        patch.object(intelligence, "transaction", side_effect=_transaction),
        patch.object(intelligence, "hospitality_message_matches", return_value=False),
        patch.object(intelligence, "gmail_attachment_parts", return_value=[]),
        patch.object(intelligence, "save_intake_file", side_effect=lambda *args, **kwargs: "saved"),
        patch.object(intelligence, "create_alert_once"),
        patch.object(intelligence, "estate_id", return_value="estate"),
    ):
        assert intelligence.poll_gmail_once() == intelligence.GMAIL_NEW_MESSAGE_BUDGET

    assert len(full_fetches) == intelligence.GMAIL_NEW_MESSAGE_BUDGET
