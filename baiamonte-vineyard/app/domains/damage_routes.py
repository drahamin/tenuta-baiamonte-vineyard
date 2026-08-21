from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready


router = APIRouter(prefix="/api/v1/agronomy/damage-assessments", tags=["agronomy"])


def damage_assessment_dashboard(year: int) -> dict[str, list[dict[str, Any]]]:
    rows = fetch_all(
        "SELECT a.*,s.vintage_year FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id "
        "WHERE a.estate_id=%s AND s.vintage_year=%s AND a.active=1 ORDER BY a.event_date,a.assessed_at",
        (estate_id(), year),
    )
    for row in rows:
        try:
            evidence = json.loads(row.pop("evidence_json", None) or "[]")
        except (TypeError, ValueError):
            evidence = []
        row["evidence"] = evidence if isinstance(evidence, list) else []
    attachments = fetch_all(
        "SELECT id,entity_id,original_filename,caption FROM entity_attachments "
        "WHERE estate_id=%s AND entity_type='damage_assessment' ORDER BY created_at",
        (estate_id(),),
    )
    attachments_by_assessment: dict[str, list[dict[str, Any]]] = {}
    for attachment in attachments:
        attachments_by_assessment.setdefault(str(attachment["entity_id"]), []).append({
            "url": f"api/v1/attachments/{attachment['id']}/file",
            "filename": attachment.get("original_filename"),
            "caption": attachment.get("caption"),
        })
    for row in rows:
        row["evidence"] = attachments_by_assessment.get(str(row["id"]), row["evidence"])
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("review_status") == "approved":
            current[str(row["event_key"])] = row
    return json_ready({"damage_assessments": rows, "current_damage_assessments": list(current.values())})


@router.patch("/{assessment_id}", dependencies=[Depends(authorize_write)])
def update_damage_assessment(assessment_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM vineyard_damage_assessments WHERE id=%s AND estate_id=%s AND active=1",
        (assessment_id, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Damage assessment not found")
    trend = str(payload.get("trend") or row["trend"]).strip().casefold()
    confidence = str(payload.get("confidence") or row["confidence"]).strip().casefold()
    review_status = str(payload.get("review_status") or row["review_status"]).strip().casefold()
    if trend not in {"initial", "worsening", "stable", "improving", "resolved"}:
        raise HTTPException(422, "Choose a valid damage trend")
    if confidence not in {"low", "medium", "high"}:
        raise HTTPException(422, "Choose low, medium or high confidence")
    if review_status not in {"draft", "approved", "rejected"}:
        raise HTTPException(422, "Choose draft, approved or rejected")
    loss_value = payload.get("estate_yield_loss_pct", row.get("estate_yield_loss_pct"))
    if loss_value in (None, ""):
        loss_pct = None
    else:
        try:
            loss_pct = round(float(loss_value), 2)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Estate yield loss must be a percentage") from exc
        if loss_pct < 0 or loss_pct > 80:
            raise HTTPException(422, "Estate yield loss must be between 0 and 80 percent")
    assessed_value = str(payload.get("assessed_at") or row["assessed_at"]).strip()
    if len(assessed_value) == 10:
        assessed_value += " 12:00:00"
    actor = request.headers.get("X-Remote-User-Name") or "api"
    approved_by = str(payload.get("approved_by") or row.get("approved_by") or actor).strip() if review_status == "approved" else None
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE vineyard_damage_assessments SET assessed_at=%s,observer_name=%s,trend=%s,estate_yield_loss_pct=%s,"
            "confidence=%s,review_status=%s,approved_by=%s,approved_at=CASE WHEN %s='approved' THEN COALESCE(approved_at,CURRENT_TIMESTAMP(6)) ELSE NULL END,notes=%s "
            "WHERE id=%s AND estate_id=%s AND active=1",
            (assessed_value, str(payload.get("observer_name") or row["observer_name"]).strip(), trend, loss_pct,
             confidence, review_status, approved_by, review_status, str(payload.get("notes") or "").strip() or None,
             assessment_id, estate_id()),
        )
        audit(cursor, "update", "damage_assessment", assessment_id, {"trend": trend, "estate_yield_loss_pct": loss_pct, "review_status": review_status}, actor)
    return {"saved": True, "assessment_id": assessment_id}


@router.delete("/{assessment_id}", dependencies=[Depends(authorize_write)])
def delete_damage_assessment(assessment_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE vineyard_damage_assessments SET active=0,review_status='archived' WHERE id=%s AND estate_id=%s AND active=1",
            (assessment_id, estate_id()),
        )
        if not cursor.rowcount:
            raise HTTPException(404, "Damage assessment not found")
        audit(cursor, "archive", "damage_assessment", assessment_id, {"reason": "Removed from Agronomy; audit history preserved"}, actor)
    return {"deleted": True, "audit_preserved": True}
