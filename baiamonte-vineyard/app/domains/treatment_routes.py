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


@router.get("/api/v1/treatments/sprayers", dependencies=[Depends(authorize)])
def list_sprayer_profiles() -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT q.id equipment_id,q.name,q.make_model,q.serial_number,q.status,s.id profile_id,s.tank_capacity_l,s.usable_capacity_l,"
        "s.calibrated_on,s.calibration_status,s.nozzle_setup,s.flow_l_min,s.operating_pressure_bar,s.travel_speed_kph,s.carrier_rate_l_ha,"
        "s.source_reference,s.notes FROM equipment q LEFT JOIN spray_equipment_profiles s ON s.equipment_id=q.id AND s.active=1 "
        "WHERE q.estate_id=%s AND q.active=1 AND q.equipment_type='sprayer' AND q.status<>'retired' ORDER BY q.name",
        (estate_id(),),
    ))


@router.post("/api/v1/treatments/sprayers", dependencies=[Depends(authorize_write)])
def save_sprayer_profile(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    require_discipline_approval(request, "agronomy")
    equipment_id = str(payload.get("equipment_id") or "").strip()
    name = str(payload.get("name") or "").strip()[:180]
    make_model = str(payload.get("make_model") or "").strip()[:160] or None
    if not equipment_id and not name:
        raise HTTPException(422, "Enter a sprayer name")
    existing = fetch_one("SELECT id,name FROM equipment WHERE id=%s AND estate_id=%s AND active=1", (equipment_id, estate_id())) if equipment_id else None
    if equipment_id and not existing:
        raise HTTPException(404, "Sprayer not found")

    def number(name: str, *, required: bool = False) -> float | None:
        value = payload.get(name)
        if value in (None, ""):
            if required:
                raise HTTPException(422, f"Enter {name.replace('_', ' ')}")
            return None
        try:
            number_value = round(float(value), 3)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, f"{name.replace('_', ' ').title()} must be numeric") from error
        if number_value <= 0:
            raise HTTPException(422, f"{name.replace('_', ' ').title()} must be greater than zero")
        return number_value

    tank_capacity = number("tank_capacity_l", required=True)
    usable_capacity = number("usable_capacity_l")
    if usable_capacity and tank_capacity and usable_capacity > tank_capacity:
        raise HTTPException(422, "Usable fill cannot exceed nominal tank capacity")
    status = str(payload.get("calibration_status") or "needs_measurement").strip()
    if status not in {"verified", "needs_measurement", "expired"}:
        raise HTTPException(422, "Choose a valid calibration status")
    calibrated_on = str(payload.get("calibrated_on") or "").strip() or None
    nozzle_setup = str(payload.get("nozzle_setup") or "").strip()[:255] or None
    measurements = {
        "flow_l_min": number("flow_l_min"), "operating_pressure_bar": number("operating_pressure_bar"),
        "travel_speed_kph": number("travel_speed_kph"), "carrier_rate_l_ha": number("carrier_rate_l_ha"),
    }
    if status == "verified" and (not calibrated_on or not nozzle_setup or usable_capacity is None or any(value is None for value in measurements.values())):
        raise HTTPException(422, "Verified calibration requires date, usable fill, nozzle setup, flow, pressure, speed, and carrier rate")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    profile_id = new_id()
    with transaction() as (_, cursor):
        if not existing:
            equipment_id = new_id()
            cursor.execute(
                "INSERT INTO equipment (id,estate_id,name,equipment_type,make_model,status,active) VALUES (%s,%s,%s,'sprayer',%s,'available',1)",
                (equipment_id, estate_id(), name, make_model),
            )
        else:
            cursor.execute("UPDATE equipment SET name=%s,make_model=%s WHERE id=%s AND estate_id=%s", (name or existing.get("name"), make_model, equipment_id, estate_id()))
        cursor.execute(
            "INSERT INTO spray_equipment_profiles (id,estate_id,equipment_id,application_method,tank_capacity_l,usable_capacity_l,calibrated_on,"
            "calibration_status,nozzle_setup,flow_l_min,operating_pressure_bar,travel_speed_kph,carrier_rate_l_ha,source_reference,notes,active) "
            "VALUES (%s,%s,%s,'water_spray',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1) "
            "ON DUPLICATE KEY UPDATE tank_capacity_l=VALUES(tank_capacity_l),usable_capacity_l=VALUES(usable_capacity_l),calibrated_on=VALUES(calibrated_on),"
            "calibration_status=VALUES(calibration_status),nozzle_setup=VALUES(nozzle_setup),flow_l_min=VALUES(flow_l_min),"
            "operating_pressure_bar=VALUES(operating_pressure_bar),travel_speed_kph=VALUES(travel_speed_kph),carrier_rate_l_ha=VALUES(carrier_rate_l_ha),"
            "source_reference=VALUES(source_reference),notes=VALUES(notes),active=1",
            (profile_id, estate_id(), equipment_id, tank_capacity, usable_capacity, calibrated_on, status, nozzle_setup,
             measurements["flow_l_min"], measurements["operating_pressure_bar"], measurements["travel_speed_kph"], measurements["carrier_rate_l_ha"],
             str(payload.get("source_reference") or "").strip()[:255] or None, str(payload.get("notes") or "").strip() or None),
        )
        audit(cursor, "configure", "spray_equipment_profile", equipment_id, {
            "name": name or existing.get("name"), "tank_capacity_l": tank_capacity, "usable_capacity_l": usable_capacity,
            "calibration_status": status, "calibrated_on": calibrated_on, **measurements,
        }, actor)
    return json_ready({"saved": True, "equipment_id": equipment_id, "calibration_status": status})


@router.post("/api/v1/treatments/product-evidence/intake/{record_id}/approve", dependencies=[Depends(authorize_write)])
def approve_product_evidence_intake(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Turn reviewed AI extraction into source-linked product evidence, never an application."""
    require_discipline_approval(request, "agronomy")
    item = fetch_one(
        "SELECT id,classification,review_status,extracted_data,original_filename,received_at FROM intake_items WHERE id=%s AND estate_id=%s",
        (record_id, estate_id()),
    )
    if not item:
        raise HTTPException(404, "Incoming product information was not found")
    if item.get("classification") != "product_label":
        raise HTTPException(422, "Analyze this source as product information before approval")
    if item.get("review_status") not in {"ready_for_review", "approved"}:
        raise HTTPException(409, "This source is not ready for product review")
    product_id = str(payload.get("product_id") or "").strip()
    product = fetch_one("SELECT id,name FROM products WHERE id=%s AND estate_id=%s AND active=1", (product_id, estate_id()))
    if not product:
        raise HTTPException(422, "Choose the matching estate product")
    evidence_type = str(payload.get("evidence_type") or "container_label").strip()
    allowed_types = {"container_label", "manufacturer_label", "technical_product_page", "sds", "owner_document", "agronomist_review"}
    if evidence_type not in allowed_types:
        raise HTTPException(422, "Choose a valid product evidence type")

    def number(name: str) -> float | None:
        value = payload.get(name)
        if value in (None, ""):
            return None
        try:
            return round(float(value), 3)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, f"{name.replace('_', ' ').title()} must be numeric") from error

    minimum, maximum = number("rate_min"), number("rate_max")
    if minimum is not None and maximum is not None and maximum < minimum:
        raise HTTPException(422, "Maximum rate cannot be lower than minimum rate")
    observed_form = str(payload.get("formulation") or "unknown").strip()[:100]
    lot_number = str(payload.get("lot_number") or "").strip()
    if lot_number:
        observed_form = f"{observed_form} · lot {lot_number}"[:100]
    notes = str(payload.get("notes") or "").strip()
    rate_unit = str(payload.get("rate_unit") or "").strip()[:40] or None
    actor = request.headers.get("X-Remote-User-Name") or "api"
    evidence_id = new_id()
    analysis = item.get("extracted_data")
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except ValueError:
            analysis = {"raw": analysis}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO treatment_product_evidence (id,estate_id,product_id,evidence_type,source_key,source_reference,source_intake_id,"
            "observed_form,observed_rate,observed_rate_max,observed_rate_unit,evidence_date,verification_status,notes,analysis_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,DATE(%s),'verified',%s,%s) "
            "ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),evidence_type=VALUES(evidence_type),observed_form=VALUES(observed_form),"
            "observed_rate=VALUES(observed_rate),observed_rate_max=VALUES(observed_rate_max),observed_rate_unit=VALUES(observed_rate_unit),"
            "evidence_date=VALUES(evidence_date),verification_status='verified',notes=VALUES(notes),analysis_json=VALUES(analysis_json)",
            (evidence_id, estate_id(), product_id, evidence_type, f"intake:{record_id}", f"api/v1/intake/{record_id}/file", record_id,
             observed_form, minimum, maximum, rate_unit, item.get("received_at"), notes or None, json.dumps(analysis or {})),
        )
        cursor.execute(
            "UPDATE intake_items SET review_status='approved',review_reason='Approved as structured product evidence',reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s",
            (actor, record_id, estate_id()),
        )
        audit(cursor, "approve", "treatment_product_evidence", evidence_id, {
            "intake_id": record_id, "product_id": product_id, "product_name": product.get("name"), "evidence_type": evidence_type,
            "formulation": observed_form, "rate_min": minimum, "rate_max": maximum, "rate_unit": rate_unit,
            "guardrail": "Evidence stored; product profile, inventory and treatment rules are not silently rewritten",
        }, actor)
    return json_ready({"saved": True, "evidence_id": evidence_id, "product_name": product.get("name"), "review_status": "approved"})


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
        "SELECT title,original_filename,classification,review_status,source,received_at FROM intake_items WHERE estate_id=%s AND classification IN ('treatment_instruction','vineyard_instruction','product_label') AND YEAR(received_at)=%s ORDER BY received_at DESC LIMIT 30",
        (estate_id(), year),
    ):
        actions.append({"kind": "intake", "title": row.get("title") or row.get("original_filename") or "Incoming treatment information", "detail": row.get("classification"), "status": row.get("review_status"), "source": row.get("source"), "occurred_at": row.get("received_at")})
    actions.sort(key=lambda row: row.get("occurred_at") or datetime.min, reverse=True)
    return actions[:50]
