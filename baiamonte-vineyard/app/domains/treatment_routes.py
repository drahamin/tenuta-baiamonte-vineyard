from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize, authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..planning_sync import publish_task_to_google
from ..service import audit, estate_id, json_ready, new_id, season_for_year
from .people_roles import require_discipline_approval
from .treatments import (
    field_review_guidance,
    inventory_readiness,
    mixture_signature,
    product_guidance,
    simulated_prediction,
)


router = APIRouter()


def _checked(value: Any) -> bool:
    return value is True or str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


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


@router.post("/api/v1/treatments/{treatment_id}/mixture-approval", dependencies=[Depends(authorize_write)])
def save_treatment_mixture_approval(treatment_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Store a review against the exact current products and rates; edits invalidate it by signature."""
    require_discipline_approval(request, "agronomy")
    treatment = fetch_one(
        "SELECT id,status,purpose FROM spray_applications WHERE id=%s AND estate_id=%s",
        (treatment_id, estate_id()),
    )
    if not treatment:
        raise HTTPException(404, "Treatment not found")
    if str(treatment.get("status") or "").casefold() not in {"completed", "applied"}:
        raise HTTPException(422, "Only a completed application can receive an exact-mixture review")
    items = fetch_all(
        "SELECT i.product_id,i.dose_amount,i.dose_unit,i.total_used,p.name product_name "
        "FROM spray_application_items i JOIN products p ON p.id=i.product_id "
        "WHERE i.application_id=%s ORDER BY p.name,i.id",
        (treatment_id,),
    )
    if len(items) < 2:
        raise HTTPException(422, "This application does not contain a multi-product mixture")
    status = str(payload.get("status") or "verified").strip().casefold()
    if status not in {"verified", "rejected"}:
        raise HTTPException(422, "Choose verified or rejected")
    jar_test_status = str(payload.get("jar_test_status") or "not_recorded").strip().casefold()
    if jar_test_status not in {"passed", "not_required", "failed", "not_recorded"}:
        raise HTTPException(422, "Choose a valid jar-test result")
    current_labels = _checked(payload.get("current_labels_confirmed"))
    exact_combination = _checked(payload.get("exact_combination_confirmed"))
    compatibility_basis = str(payload.get("compatibility_basis") or "").strip()
    sequence_notes = str(payload.get("sequence_notes") or "").strip()
    notes = str(payload.get("notes") or "").strip() or None
    if status == "verified":
        if not current_labels or not exact_combination:
            raise HTTPException(422, "Confirm current labels and the exact product combination")
        if jar_test_status not in {"passed", "not_required"}:
            raise HTTPException(422, "Record a passed jar test or document why it is not required")
        if not compatibility_basis or not sequence_notes:
            raise HTTPException(422, "Record the compatibility basis and mixing sequence")
    elif not notes:
        raise HTTPException(422, "Record why the mixture was rejected")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    signature = mixture_signature(items)
    approval_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO treatment_mixture_approvals (id,estate_id,application_id,mixture_signature,product_count,status,jar_test_status,"
            "current_labels_confirmed,exact_combination_confirmed,compatibility_basis,sequence_notes,approved_by,approved_at,notes,active) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='verified' THEN CURRENT_TIMESTAMP(6) ELSE NULL END,%s,1) "
            "ON DUPLICATE KEY UPDATE mixture_signature=VALUES(mixture_signature),product_count=VALUES(product_count),status=VALUES(status),"
            "jar_test_status=VALUES(jar_test_status),current_labels_confirmed=VALUES(current_labels_confirmed),"
            "exact_combination_confirmed=VALUES(exact_combination_confirmed),compatibility_basis=VALUES(compatibility_basis),"
            "sequence_notes=VALUES(sequence_notes),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),notes=VALUES(notes),active=1",
            (approval_id, estate_id(), treatment_id, signature, len(items), status, jar_test_status, current_labels, exact_combination,
             compatibility_basis or None, sequence_notes or None, actor, status, notes),
        )
        audit(cursor, "mixture_review", "treatment", treatment_id, {
            "purpose": treatment.get("purpose"), "status": status, "mixture_signature": signature,
            "product_count": len(items), "jar_test_status": jar_test_status,
            "current_labels_confirmed": current_labels, "exact_combination_confirmed": exact_combination,
        }, actor)
    return json_ready({"saved": True, "treatment_id": treatment_id, "status": status, "mixture_signature": signature, "product_count": len(items)})


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
