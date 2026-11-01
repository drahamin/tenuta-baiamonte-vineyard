from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import Settings
from app.domains import alerts_intake_routes, mobile_intake_access, mobile_intake_routes


REPORT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ATTACHMENT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ESTATE = "00000000-0000-4000-8000-000000000001"


def request(username):
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"x-remote-user-name", username.encode())]})


def draft():
    return {"report_uuid": REPORT, "actor_username": "author", "entry_kind": "enology_reading", "status": "pending_review"}


def attachment(path):
    return {"id": ATTACHMENT, "estate_id": ESTATE, "entity_type": "mobile_intake_draft", "entity_id": REPORT, "stored_path": str(path), "media_type": "image/png", "original_filename": "proof.png"}


def configure(monkeypatch, level=None, reviewer=False):
    monkeypatch.setattr(mobile_intake_access, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_access, "fetch_one", lambda *_: draft())
    monkeypatch.setattr(mobile_intake_access, "profile_access_level", lambda _username: level)
    monkeypatch.setattr(mobile_intake_access, "admin_usernames", lambda _settings: set())
    def discipline(_request, _discipline):
        if not reviewer:
            raise HTTPException(403, "not reviewer")
    monkeypatch.setattr(mobile_intake_access, "require_discipline_approval", discipline)


def test_same_estate_viewer_and_different_author_cannot_read_mobile_evidence(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    configure(monkeypatch, level="viewer")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    settings = Settings(api_key="")
    with pytest.raises(HTTPException) as denied:
        alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("other-user"), settings=settings)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as preview_denied:
        alerts_intake_routes.entity_attachment_preview(ATTACHMENT, request("other-user"), settings=settings)
    assert preview_denied.value.status_code == 403


def test_mobile_evidence_author_and_authorized_reviewer_can_read(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    configure(monkeypatch, level="viewer")
    assert alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("author"), settings=Settings(api_key="")).path == str(path)
    configure(monkeypatch, level="operations", reviewer=True)
    assert str(alerts_intake_routes.entity_attachment_preview(ATTACHMENT, request("enologist"), settings=Settings(api_key="")).path) == str(path)


def test_mobile_evidence_admin_and_internal_api_can_read(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    configure(monkeypatch, level="admin")
    assert alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("admin"), settings=Settings(api_key="secret")).path == str(path)
    configure(monkeypatch, level="viewer")
    assert alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("service"), x_api_key="secret", settings=Settings(api_key="secret")).path == str(path)


def test_specialized_attachment_listing_is_author_or_reviewer_scoped(monkeypatch):
    configure(monkeypatch, level="viewer")
    monkeypatch.setattr(mobile_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_routes, "fetch_all", lambda *_: [{"id": ATTACHMENT, "original_filename": "proof.png", "media_type": "image/png", "caption": None, "created_at": None}])
    result = mobile_intake_routes.mobile_intake_attachments(REPORT, request("author"), settings=Settings(api_key=""))
    assert result["attachments"][0]["file_url"].endswith(f"/{ATTACHMENT}/file")
    with pytest.raises(HTTPException) as denied:
        mobile_intake_routes.mobile_intake_attachments(REPORT, request("other-user"), settings=Settings(api_key=""))
    assert denied.value.status_code == 403


def test_generic_records_listing_excludes_every_mobile_intake_draft():
    root = Path(__file__).resolve().parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    marker = '"attachments": ("SELECT id,entity_type,entity_id,original_filename,media_type,caption,uploaded_by,created_at'
    query = main.split(marker, 1)[1].split('\", (estate_id(),))', 1)[0]
    assert "entity_type<>'mobile_intake_draft'" in query
