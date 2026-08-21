from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..access import authorize
from ..db import fetch_all, fetch_one
from ..service import estate_id, json_ready
from .messaging import event_payload


router = APIRouter(prefix="/api/v1/observation-analysis", tags=["observations"])


@router.get("/{entity_type}/{entity_id}", dependencies=[Depends(authorize)])
def observation_analysis_status(entity_type: str, entity_id: str) -> dict[str, Any]:
    if entity_type not in {"scouting", "phenology", "maturity_sample"}:
        raise HTTPException(422, "This record type does not use observation photo analysis")
    rows = fetch_all(
        "SELECT opa.attachment_id,opa.status,opa.confidence,opa.applied_fields,opa.review_reason,opa.error_message,opa.analyzed_at "
        "FROM observation_photo_analyses opa WHERE opa.estate_id=%s AND opa.entity_type=%s AND opa.entity_id=%s "
        "ORDER BY opa.created_at,opa.id",
        (estate_id(), entity_type, entity_id),
    )
    route_event = fetch_one(
        "SELECT after_data,occurred_at FROM audit_events WHERE estate_id=%s AND entity_type=%s AND entity_id=%s "
        "AND action='photo_route' ORDER BY occurred_at DESC,id DESC LIMIT 1",
        (estate_id(), entity_type, entity_id),
    ) or {}
    terminal = {"applied", "review_required", "failed"}
    statuses = [str(row.get("status") or "queued") for row in rows]
    overall = "not_queued" if not rows else "complete" if all(status in terminal for status in statuses) else "processing"
    payload = event_payload(route_event.get("after_data"))
    return json_ready({
        "entity_type": entity_type,
        "entity_id": entity_id,
        "status": overall,
        "analyses": rows,
        "pipelines": payload.get("pipelines") if isinstance(payload, dict) else {},
        "routed_at": route_event.get("occurred_at"),
    })
