"""Read boundary for private mobile-intake drafts and their evidence."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from ..access import admin_usernames, profile_access_level, request_username
from ..config import Settings
from ..db import fetch_one
from ..service import estate_id
from .people_roles import require_discipline_approval


def authorize_mobile_intake_draft_read(
    request: Request,
    report_uuid: str,
    settings: Settings,
    x_api_key: str | None = None,
) -> dict[str, Any]:
    """Allow only the immutable author, a qualified reviewer, or internal API."""
    row = fetch_one(
        "SELECT report_uuid,actor_username,entry_kind,status FROM mobile_intake_source_drafts WHERE report_uuid=%s AND estate_id=%s",
        (report_uuid, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Mobile intake report not found")
    if settings.api_key and x_api_key == settings.api_key:
        return row
    username = request_username(request)
    if username and username != "api" and username == str(row.get("actor_username") or "").strip().casefold():
        return row
    level = profile_access_level(username)
    if level == "admin" or (level is None and username in admin_usernames(settings)):
        return row
    kind = str(row.get("entry_kind") or "")
    discipline = "agronomy" if kind in {"field_observation", "damage_report", "agronomy_note"} else "enology" if kind in {"cellar_note", "enology_reading"} else None
    if discipline:
        try:
            require_discipline_approval(request, discipline)
            return row
        except HTTPException:
            pass
    raise HTTPException(403, "Mobile intake evidence is limited to its author and authorized reviewers")


def authorize_mobile_intake_attachment_read(
    request: Request,
    attachment: dict[str, Any],
    settings: Settings,
    x_api_key: str | None = None,
) -> None:
    if str(attachment.get("entity_type") or "") != "mobile_intake_draft":
        return
    authorize_mobile_intake_draft_read(request, str(attachment.get("entity_id") or ""), settings, x_api_key)
