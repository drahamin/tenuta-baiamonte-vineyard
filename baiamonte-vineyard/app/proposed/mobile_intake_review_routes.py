"""Unwired routes for the minimum independent enology review flow."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..access import authorize, request_username
from ..db import fetch_all
from ..service import estate_id, json_ready
from ..domains.people_roles import require_discipline_approval
from .mobile_intake_review import ReviewConflict, ReviewPolicy, ReviewRejected, decide_initial_enology_report


router = APIRouter(prefix="/api/v1/mobile-intake", tags=["proposed-mobile-intake-review"])


def _configured_policy() -> ReviewPolicy:
    try:
        return ReviewPolicy.current()
    except ReviewRejected as error:
        raise HTTPException(503, "Mobile intake review policy is not configured") from error


@router.get("/initial-enology-review", dependencies=[Depends(authorize)])
def initial_enology_review_queue(request: Request) -> dict[str, Any]:
    policy = _configured_policy()
    require_discipline_approval(request, "enology")
    reviewer = request_username(request)
    if reviewer not in policy.reviewer_roles:
        raise HTTPException(403, "This account is not in the approved review policy")
    rows = fetch_all(
        "SELECT report_uuid,actor_username,entry_kind,occurred_at,received_at,status,revision,payload_json "
        "FROM mobile_intake_source_drafts WHERE estate_id=%s AND actor_username=%s "
        "AND entry_kind=%s AND actor_username<>%s AND status='pending_review' ORDER BY received_at LIMIT 100",
        (estate_id(), policy.author_username, policy.entry_kind, reviewer),
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
    policy = _configured_policy()
    try:
        reviewer = request_username(request)
        expected = int(str(x_baiamonte_expected_revision or ""))
        result = decide_initial_enology_report(
            report_uuid,
            expected,
            str(payload.get("review_status") or ""),
            str(payload.get("review_note") or ""),
            reviewer,
            str(policy.reviewer_roles.get(reviewer) or ""),
            policy,
        )
    except ReviewRejected as error:
        raise HTTPException(403, str(error)) from error
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True, **result}
