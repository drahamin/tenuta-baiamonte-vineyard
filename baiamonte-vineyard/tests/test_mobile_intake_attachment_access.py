from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import Settings
from app.domains import alerts_intake_routes, mobile_intake_access, mobile_intake_policy, mobile_intake_routes


REPORT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ATTACHMENT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ESTATE = "00000000-0000-4000-8000-000000000001"
AUTHOR_USER = "22456456-cc5e-11f1-b520-0200fd82860d"
AUTHOR_HA = "50302bdc5bed42ac92dbfc2b4b4e5181"


def request(username, user_id="", *, client="172.30.32.2", extra=()):
    return Request({"type": "http", "method": "GET", "path": "/", "client": (client, 1234), "headers": [(b"x-ingress-path", b"/api/hassio_ingress/mobile"), (b"x-remote-user-name", username.encode()), (b"x-remote-user-id", user_id.encode()), *extra]})


def draft():
    return {"report_uuid": REPORT, "actor_username": "david", "entry_kind": "enology_reading", "status": "pending_review"}


def attachment(path):
    return {"id": ATTACHMENT, "estate_id": ESTATE, "entity_type": "mobile_intake_draft", "entity_id": REPORT, "stored_path": str(path), "media_type": "image/png", "original_filename": "proof.png"}


def configure(monkeypatch):
    monkeypatch.setattr(mobile_intake_access, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_access, "fetch_one", lambda *_: draft())
    monkeypatch.setattr(mobile_intake_policy, "runtime_option", lambda *_: {"enabled": True, "website_user_id": AUTHOR_USER, "website_username": "david", "ha_user_id": AUTHOR_HA, "ha_username": "rahamin", "allowed_kinds": ["enology_reading"]})


def test_same_estate_viewer_and_different_author_cannot_read_mobile_evidence(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    configure(monkeypatch)
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    settings = Settings(api_key="")
    with pytest.raises(HTTPException) as denied:
        alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("other-user"), settings=settings)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as preview_denied:
        alerts_intake_routes.entity_attachment_preview(ATTACHMENT, request("other-user"), settings=settings)
    assert preview_denied.value.status_code == 403


def test_mobile_evidence_exact_mapped_author_can_read(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    configure(monkeypatch)
    assert alerts_intake_routes.entity_attachment_file(ATTACHMENT, request("rahamin", AUTHOR_HA), settings=Settings(api_key="")).path == str(path)
    assert str(alerts_intake_routes.entity_attachment_preview(ATTACHMENT, request("rahamin", AUTHOR_HA), settings=Settings(api_key="")).path) == str(path)


def test_mobile_evidence_admin_reviewer_and_internal_api_are_denied(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    configure(monkeypatch)
    for username, user_id, api_key in [("admin", "a" * 32, None), ("sebastian", "f402bf2ae76842088ac296979a9f4a8e", None), ("service", "", "secret")]:
        with pytest.raises(HTTPException) as denied:
            alerts_intake_routes.entity_attachment_file(ATTACHMENT, request(username, user_id), x_api_key=api_key, settings=Settings(api_key="secret"))
        assert denied.value.status_code == 403


def test_valid_api_key_cannot_forge_author_headers(monkeypatch, tmp_path):
    path = tmp_path / "proof.png"; path.write_bytes(b"\x89PNG\r\n\x1a\nproof")
    monkeypatch.setattr(alerts_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(alerts_intake_routes, "fetch_one", lambda *_: attachment(path))
    configure(monkeypatch)
    forged = request("rahamin", AUTHOR_HA, client="203.0.113.10")
    with pytest.raises(HTTPException) as denied:
        alerts_intake_routes.entity_attachment_file(ATTACHMENT, forged, x_api_key="secret", settings=Settings(api_key="secret"))
    assert denied.value.status_code == 403


def test_specialized_attachment_listing_is_author_or_reviewer_scoped(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(mobile_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_routes, "fetch_all", lambda *_: [{"id": ATTACHMENT, "original_filename": "proof.png", "media_type": "image/png", "caption": None, "created_at": None}])
    result = mobile_intake_routes.mobile_intake_attachments(REPORT, request("rahamin", AUTHOR_HA), settings=Settings(api_key=""))
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
