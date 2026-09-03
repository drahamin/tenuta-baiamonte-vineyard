from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from unittest.mock import patch

from app import intelligence
from app.mailbox import gmail_attachment_parts


FORWARDED_LAB = b"""MIME-Version: 1.0\r
From: David Rahamin <david@rahamins.com>\r
To: estate@example.com\r
Subject: Fwd: 03/09/2026\r
Content-Type: multipart/alternative; boundary=outer\r
\r
--outer\r
Content-Type: text/plain; charset=utf-8\r
\r
Forwarded laboratory report\r
--outer\r
Content-Type: multipart/mixed; boundary=inner\r
\r
--inner\r
Content-Type: text/html; charset=utf-8\r
\r
<p>Forwarded laboratory report</p>\r
--inner\r
Content-Type: application/pdf\r
Content-Disposition: inline; filename="Baiamonte 03-09-2026.pdf"\r
Content-Transfer-Encoding: base64\r
\r
JVBERi0xLjQK\r
--inner--\r
--outer--\r
"""


def test_nested_inline_forwarded_pdf_is_an_attachment() -> None:
    message = BytesParser(policy=policy.default).parsebytes(FORWARDED_LAB)
    attachments = gmail_attachment_parts(message)
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "Baiamonte 03-09-2026.pdf"
    assert attachments[0].get_content_type() == "application/pdf"


def test_owner_estate_mailbox_and_active_staff_are_trusted() -> None:
    settings = SimpleNamespace(
        gmail_allowed_senders="laboratorio@cimalab.it",
        gmail_address="estate@example.com",
    )
    with patch.object(intelligence, "fetch_all", return_value=[{"email": "Staff Member <staff@example.com>"}]):
        trusted = intelligence._trusted_gmail_senders(settings)
    assert trusted == {
        "laboratorio@cimalab.it",
        "david@rahamins.com",
        "estate@example.com",
        "staff@example.com",
    }
