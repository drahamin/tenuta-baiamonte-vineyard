"""Unwired routes for the minimum independent enology review flow."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..access import authorize, request_username
from ..db import fetch_all
from ..service import estate_id, json_ready
from ..domains.people_roles import require_discipline_approval
from .mobile_intake_review import ReviewConflict, ReviewRejected, decide_initial_enology_report


router = APIRouter(prefix="/api/v1/mobile-intake", tags=["proposed-mobile-intake-review"])


@router.get("/initial-enology-review", dependencies=[Depends(authorize)])
def initial_enology_review_queue(request: Request) -> dict[str, Any]:
    require_discipline_approval(request, "enology")
    if request_username(request) != "sebastian":
        raise HTTPException(403, "The initial review queue is assigned to Sebastian")
    rows = fetch_all(
        "SELECT report_uuid,actor_username,entry_kind,occurred_at,received_at,status,revision,payload_json "
        "FROM mobile_intake_source_drafts WHERE estate_id=%s AND actor_username='david' "
        "AND entry_kind='enology_reading' AND status='pending_review' ORDER BY received_at LIMIT 100",
        (estate_id(),),
    )
    return {"reports": json_ready(rows), "business_application_status": "not_applied"}


@router.patch("/{report_uuid}/decision", dependencies=[Depends(authorize)])
def initial_enology_review_decision(
    report_uuid: str,
    payload: dict[str, Any],
    request: Request,
    x_baiamonte_expected_revision: str | None = Header(default=None),
) -> dict[str, Any]:
    require_discipline_approval(request, "enology")
    try:
        expected = int(str(x_baiamonte_expected_revision or ""))
        result = decide_initial_enology_report(
            report_uuid,
            expected,
            str(payload.get("review_status") or ""),
            str(payload.get("review_note") or ""),
            request_username(request),
            "Agronomist & Enologist",
        )
    except ReviewRejected as error:
        raise HTTPException(403, str(error)) from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True, **result}
