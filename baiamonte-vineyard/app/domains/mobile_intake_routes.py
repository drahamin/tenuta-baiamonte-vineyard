"""Human review endpoints for immutable mobile intake drafts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..access import authorize
from ..config import Settings, get_settings
from ..db import fetch_all
from ..service import estate_id, json_ready
from .mobile_intake_access import authorize_mobile_intake_draft_read
from .mobile_intake_policy import MobileIntakeAuthorPolicy, review_unavailable


router = APIRouter(prefix="/api/v1/mobile-intake", tags=["mobile-intake"])


@router.get("", dependencies=[Depends(authorize)])
def mobile_intake_queue(status: str = "pending_review") -> dict[str, Any]:
    review_unavailable()
    return {"reports": []}


@router.get("/mine", dependencies=[Depends(authorize)])
def my_mobile_intake(request: Request, status: str | None = None) -> dict[str, Any]:
    if status is not None and status not in {"pending_review", "approved", "rejected", "correction_required", "superseded"}:
        raise HTTPException(422, "Unsupported mobile intake status")
    sql = "SELECT report_uuid,entry_kind,occurred_at,received_at,status,revision,reviewed_at,review_note FROM mobile_intake_source_drafts WHERE estate_id=%s AND actor_username=%s"
    author_username = MobileIntakeAuthorPolicy.current().require_author_request(request)
    params: list[Any] = [estate_id(), author_username]
    if status is not None: sql += " AND status=%s"; params.append(status)
    rows = fetch_all(sql + " ORDER BY received_at DESC LIMIT 200", tuple(params))
    return {"reports": json_ready(rows)}


@router.get("/{report_uuid}/attachments", dependencies=[Depends(authorize)])
def mobile_intake_attachments(
    report_uuid: str,
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    authorize_mobile_intake_draft_read(request, report_uuid, settings, x_api_key)
    rows = fetch_all(
        "SELECT id,original_filename,media_type,caption,created_at FROM entity_attachments "
        "WHERE estate_id=%s AND entity_type='mobile_intake_draft' AND entity_id=%s ORDER BY created_at,id",
        (estate_id(), report_uuid),
    )
    return {"attachments": json_ready([
        {**row, "file_url": f"/api/v1/attachments/{row['id']}/file", "preview_url": f"/api/v1/attachments/{row['id']}/preview"}
        for row in rows
    ])}


@router.patch("/{report_uuid}/review", dependencies=[Depends(authorize)])
def review_mobile_intake(
    report_uuid: str,
    payload: dict[str, Any],
    request: Request,
    x_baiamonte_expected_revision: str | None = Header(default=None),
) -> dict[str, Any]:
    review_unavailable()
    return {"saved": False}
