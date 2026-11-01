"""Read boundary for private mobile-intake drafts and their evidence."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from ..config import Settings
from ..db import fetch_one
from ..service import estate_id
from .mobile_intake_policy import MobileIntakeAuthorPolicy


def authorize_mobile_intake_draft_read(
    request: Request,
    report_uuid: str,
    settings: Settings,
    x_api_key: str | None = None,
) -> dict[str, Any]:
    """Allow only the exact immutable pilot author; review access is disabled."""
    if isinstance(x_api_key, str):
        raise HTTPException(403, "API key authentication cannot access private mobile intake evidence")
    row = fetch_one(
        "SELECT report_uuid,actor_username,entry_kind,status FROM mobile_intake_source_drafts WHERE report_uuid=%s AND estate_id=%s",
        (report_uuid, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Mobile intake report not found")
    policy = MobileIntakeAuthorPolicy.current()
    if str(row.get("actor_username") or "").strip().casefold() != policy.website_username or str(row.get("entry_kind") or "") not in policy.allowed_kinds:
        raise HTTPException(403, "Mobile intake report is outside the approved pilot")
    policy.require_author_request(request)
    return row


def authorize_mobile_intake_attachment_read(
    request: Request,
    attachment: dict[str, Any],
    settings: Settings,
    x_api_key: str | None = None,
) -> None:
    if str(attachment.get("entity_type") or "") != "mobile_intake_draft":
        return
    authorize_mobile_intake_draft_read(request, str(attachment.get("entity_id") or ""), settings, x_api_key)
