from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.access import authorize, authorize_write
from app.domains import communications_gmail_routes as gmail_routes
from app.main import app


ROOT = Path(__file__).resolve().parents[1]


def test_gmail_routes_keep_methods_paths_and_access_boundaries() -> None:
    expected = {
        ("/api/v1/communications/gmail/folders", ("GET",)): authorize,
        ("/api/v1/communications/gmail/messages", ("GET",)): authorize,
        ("/api/v1/communications/gmail/messages/{uid}", ("GET",)): authorize,
        ("/api/v1/communications/gmail/messages/{uid}/download", ("GET",)): authorize,
        ("/api/v1/communications/gmail/messages/{uid}/attachments/{attachment_index}", ("GET",)): authorize,
        ("/api/v1/communications/gmail/messages/{uid}", ("PATCH",)): authorize_write,
        ("/api/v1/communications/gmail/send", ("POST",)): authorize_write,
        ("/api/v1/communications/gmail/send-files", ("POST",)): authorize_write,
    }
    actual = {}
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/v1/communications/gmail"):
            key = (route.path, tuple(sorted(route.methods or ())))
            assert key not in actual
            actual[key] = route.dependencies[0].dependency
    assert actual == expected


def test_main_delegates_gmail_routes_and_keeps_cached_aggregate() -> None:
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    aggregate = (ROOT / "app" / "domains" / "communications_meta_routes.py").read_text(encoding="utf-8")
    assert "app.include_router(communications_gmail_router)" in source
    assert '@app.get("/api/v1/communications/gmail/' not in source
    assert "gmail_cached_status()" in aggregate


def test_message_errors_and_download_headers_remain_compatible() -> None:
    with patch.object(gmail_routes, "gmail_message", side_effect=LookupError("Message not found")):
        with pytest.raises(HTTPException) as missing:
            gmail_routes.communication_gmail_message("42")
    assert missing.value.status_code == 404

    with patch.object(gmail_routes, "gmail_download", return_value=(b"mail", "caffè report.eml", "message/rfc822")):
        response = gmail_routes.communication_gmail_download("42")
    assert response.body == b"mail"
    assert response.media_type == "message/rfc822"
    assert response.headers["content-disposition"] == "attachment; filename*=UTF-8''caff%C3%A8%20report.eml"


def test_send_normalizes_string_recipients_and_preserves_validation_errors() -> None:
    sent = {"sent": True}
    with patch.object(gmail_routes, "send_gmail_message", return_value=sent) as sender:
        result = gmail_routes.communication_send_gmail({
            "recipients": "one@example.com, two@example.com",
            "subject": "Harvest",
            "body": "Ready",
        })
    assert result == sent
    sender.assert_called_once_with(["one@example.com", "two@example.com"], "Harvest", "Ready")

    with patch.object(gmail_routes, "send_gmail_message", side_effect=ValueError("recipient required")):
        with pytest.raises(HTTPException) as invalid:
            gmail_routes.communication_send_gmail({"recipients": []})
    assert invalid.value.status_code == 422
    assert invalid.value.detail == "recipient required"
