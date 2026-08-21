from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize, authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..planning_sync import publish_task_to_google
from ..service import audit, estate_id, json_ready, new_id, season_for_year
from .treatments import (
    field_review_guidance,
    inventory_readiness,
    product_guidance,
    simulated_prediction,
)


router = APIRouter()


@router.post("/api/v1/treatments/simulate", dependencies=[Depends(authorize)])
def simulate_treatment(payload: dict[str, Any]) -> dict[str, Any]:
    """Calculate a hypothetical scenario without changing live predictions or records."""
    try:
        prediction = simulated_prediction(payload)
        water_l = min(5000.0, max(1.0, float(payload.get("planning_water_l") or 400)))
        area_ha = float(payload.get("area_ha")) if payload.get("area_ha") not in (None, "") else None
        equipment = str(payload.get("equipment") or "").strip() or None
        guidance = product_guidance(
            str(payload.get("crop_scope") or "vineyard").casefold(), prediction,
            planning_water_l=water_l, equipment_selector=equipment, planning_area_ha=area_ha,
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    return json_ready({
        "simulation": True,
        "saved": False,
        "prediction": prediction,
        "product_guidance": guidance,
        "inventory_readiness": inventory_readiness(guidance),
        "field_review_guidance": field_review_guidance(
            prediction.get("scenario_target_code") or prediction.get("target_code"),
            event_type=prediction.get("event_type"), crop_scope=str(payload.get("crop_scope") or "vineyard").casefold(),
        ),
        "guardrail": "Hypothetical decision support only. This does not alter the live model, reserve stock, create a treatment, or authorize application.",
    })


@router.post("/api/v1/treatments/field-review-requests", status_code=201, dependencies=[Depends(authorize_write)])
def request_treatment_field_review(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    crop_scope = str(payload.get("crop_scope") or "vineyard").strip().casefold()
    if crop_scope not in {"vineyard", "olives"}:
        raise HTTPException(422, "Choose vineyard or olives")
    target_code = str(payload.get("target_code") or "unclassified").strip().casefold()[:80]
    event_type = str(payload.get("event_type") or "none").strip().casefold()[:80]
    block_id = str(payload.get("block_id") or "").strip() or None
    if block_id and not fetch_one("SELECT id FROM vineyard_blocks WHERE id=%s AND estate_id=%s AND active=1", (block_id, estate_id())):
        raise HTTPException(422, "Choose an active vineyard block")
    try:
        due = date.fromisoformat(str(payload.get("due_date") or date.today() + timedelta(days=1))[:10])
    except ValueError as error:
        raise HTTPException(422, "Choose a valid field-review due date") from error
    guidance = field_review_guidance(target_code, event_type=event_type, crop_scope=crop_scope)
    actor = request.headers.get("X-Remote-User-Name") or "api"
    task_id = new_id()
    title = f"Field photo review · {target_code.replace('_', ' ')}"[:220]
    scope_text = "selected block" if block_id else "whole estate representative survey"
    notes = "\n".join([
        f"Treatment prediction confirmation request · {crop_scope} · {scope_text}.",
        *[f"PHOTO: {item}" for item in guidance["photos"]],
        *[f"MEASURE: {item}" for item in guidance["measurements"]],
        f"AI RULE: {guidance['ai_accuracy_rule']}",
        str(payload.get("notes") or "").strip(),
    ]).strip()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO tasks (id,estate_id,season_id,block_id,title,category,status,priority,due_date,notes,source) "
            "VALUES (%s,%s,%s,%s,%s,'scouting','planned',%s,%s,%s,'treatment_prediction')",
            (task_id, estate_id(), season_for_year(due.year), block_id, title, "urgent" if event_type == "hail" else "high", due, notes),
        )
        audit(cursor, "request_field_review", "treatment", task_id, {"target_code": target_code, "event_type": event_type, "crop_scope": crop_scope, "block_id": block_id, "due_date": due, "guidance": guidance}, actor)
    try:
        publish_task_to_google(task_id)
    except Exception:
        pass
    return json_ready({"created": True, "task_id": task_id, "title": title, "due_date": due, "guidance": guidance, "status": "planned"})


def treatment_actions(year: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen_record_actions: set[tuple[str, str, str]] = set()
    for row in fetch_all(
        "SELECT actor,action,entity_type,entity_id,after_data,occurred_at FROM audit_events WHERE estate_id=%s AND entity_type='treatment' AND YEAR(occurred_at)=%s ORDER BY occurred_at DESC LIMIT 40",
        (estate_id(), year),
    ):
        details = row.get("after_data")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except ValueError:
                details = {}
        status = str((details or {}).get("status") or "processed")
        action_key = (str(row.get("entity_id") or ""), str(row.get("action") or ""), status.casefold())
        if action_key in seen_record_actions:
            continue
        seen_record_actions.add(action_key)
        actions.append({"kind": "record", "title": (details or {}).get("purpose") or "Treatment record changed", "detail": row.get("action"), "status": status, "source": row.get("actor") or "system", "occurred_at": row.get("occurred_at"), "entity_id": row.get("entity_id")})
    for row in fetch_all(
        "SELECT disease_name,agronomist_status,agronomist_name,agronomist_notes,reviewed_at FROM disease_pressure_assessments WHERE estate_id=%s AND reviewed_at IS NOT NULL AND YEAR(reviewed_at)=%s ORDER BY reviewed_at DESC LIMIT 30",
        (estate_id(), year),
    ):
        actions.append({"kind": "review", "title": f"{row['disease_name']} review", "detail": row.get("agronomist_notes") or "Agronomist review recorded", "status": row.get("agronomist_status"), "source": row.get("agronomist_name") or "agronomist", "occurred_at": row.get("reviewed_at")})
    for row in fetch_all(
        "SELECT title,original_filename,classification,review_status,source,received_at FROM intake_items WHERE estate_id=%s AND classification IN ('treatment_instruction','vineyard_instruction') AND YEAR(received_at)=%s ORDER BY received_at DESC LIMIT 30",
        (estate_id(), year),
    ):
        actions.append({"kind": "intake", "title": row.get("title") or row.get("original_filename") or "Incoming treatment information", "detail": row.get("classification"), "status": row.get("review_status"), "source": row.get("source"), "occurred_at": row.get("received_at")})
    actions.sort(key=lambda row: row.get("occurred_at") or datetime.min, reverse=True)
    return actions[:50]
