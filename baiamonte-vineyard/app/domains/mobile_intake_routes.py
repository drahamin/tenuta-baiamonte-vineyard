"""Human review endpoints for immutable mobile intake drafts."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..access import authorize, authorize_admin, request_username
from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready
from .people_roles import require_discipline_approval


router = APIRouter(prefix="/api/v1/mobile-intake", tags=["mobile-intake"])


@router.get("", dependencies=[Depends(authorize_admin)])
def mobile_intake_queue(status: str = "pending_review") -> dict[str, Any]:
    if status not in {"pending_review", "approved", "rejected", "correction_required", "superseded"}:
        raise HTTPException(422, "Unsupported mobile intake status")
    rows = fetch_all(
        "SELECT report_uuid,actor_username,actor_role,entry_kind,occurred_at,received_at,source_timezone,status,revision,payload_json,reviewed_by,reviewed_at,review_note "
        "FROM mobile_intake_source_drafts WHERE estate_id=%s AND status=%s ORDER BY received_at DESC LIMIT 200",
        (estate_id(), status),
    )
    for row in rows:
        row["payload"] = json.loads(row.pop("payload_json") or "{}")
    return {"reports": json_ready(rows)}


@router.get("/mine", dependencies=[Depends(authorize)])
def my_mobile_intake(request: Request, status: str | None = None) -> dict[str, Any]:
    if status is not None and status not in {"pending_review", "approved", "rejected", "correction_required", "superseded"}:
        raise HTTPException(422, "Unsupported mobile intake status")
    sql = "SELECT report_uuid,entry_kind,occurred_at,received_at,status,revision,reviewed_at,review_note FROM mobile_intake_source_drafts WHERE estate_id=%s AND actor_username=%s"
    params: list[Any] = [estate_id(), request_username(request)]
    if status is not None: sql += " AND status=%s"; params.append(status)
    rows = fetch_all(sql + " ORDER BY received_at DESC LIMIT 200", tuple(params))
    return {"reports": json_ready(rows)}


@router.patch("/{report_uuid}/review", dependencies=[Depends(authorize_admin)])
def review_mobile_intake(
    report_uuid: str,
    payload: dict[str, Any],
    request: Request,
    x_baiamonte_expected_revision: str | None = Header(default=None),
) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM mobile_intake_source_drafts WHERE report_uuid=%s AND estate_id=%s", (report_uuid, estate_id()))
    if not row:
        raise HTTPException(404, "Mobile intake report not found")
    try:
        expected = int(str(x_baiamonte_expected_revision or ""))
    except ValueError as error:
        raise HTTPException(422, "Expected revision is required") from error
    if expected != int(row["revision"]):
        raise HTTPException(409, "Mobile intake revision conflict")
    status = str(payload.get("status") or "")
    if status not in {"approved", "rejected", "correction_required"}:
        raise HTTPException(422, "Choose approved, rejected or correction required")
    note = str(payload.get("review_note") or "").strip()[:2000] or None
    if status != "approved" and not note:
        raise HTTPException(422, "A review note is required")
    if row["entry_kind"] in {"field_observation", "damage_report", "agronomy_note"}:
        require_discipline_approval(request, "agronomy")
    if row["entry_kind"] in {"cellar_note", "enology_reading"}:
        require_discipline_approval(request, "enology")
    actor = request_username(request)
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE mobile_intake_source_drafts SET status=%s,revision=revision+1,reviewed_by=%s,reviewed_at=NOW(6),review_note=%s "
            "WHERE report_uuid=%s AND estate_id=%s AND revision=%s AND status='pending_review'",
            (status, actor, note, report_uuid, estate_id(), expected),
        )
        if changed != 1:
            raise HTTPException(409, "Mobile intake changed while it was being reviewed")
        audit(cursor, "review", "mobile_intake_draft", report_uuid, {"status": status, "expected_revision": expected, "review_note": note}, actor)
    return {"saved": True, "report_uuid": report_uuid, "status": status, "revision": str(expected + 1), "domain_side_effects": []}
