from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..access import authorize, authorize_write, request_username
from ..db import fetch_all, fetch_one, transaction
from .laboratory import _canonical_sample_name, _sample_display_name, lab_learning_status, lab_sample_decision_support, refresh_lab_learning
from ..models import LabSampleCreate, VarietyLabStandardUpsert
from .people_roles import require_discipline_approval
from ..prediction_refresh import request_harvest_refresh
from ..service import audit, estate_id, new_id, season_for_year


router = APIRouter()


def lab_workflow_area(sample_type: str) -> dict[str, str]:
    """Route laboratory evidence by the physical stage represented by the sample."""
    if sample_type == "grape":
        return {"code": "agronomy", "label": "Agronomy · pre-harvest"}
    if sample_type in {"must", "wine"}:
        return {"code": "enology", "label": "Enology · post-harvest"}
    return {"code": "laboratory", "label": "Laboratory · supporting evidence"}


@router.get("/api/v1/labs/learning-status", dependencies=[Depends(authorize)])
def get_lab_learning_status() -> dict[str, Any]:
    return lab_learning_status()


@router.get("/api/v1/labs/variety-standards", dependencies=[Depends(authorize)])
def list_variety_lab_standards() -> list[dict[str, Any]]:
    return fetch_all(
        "SELECT s.*,v.name variety_name FROM variety_lab_standards s "
        "JOIN grape_varieties v ON v.id=s.variety_id AND v.estate_id=s.estate_id "
        "WHERE s.estate_id=%s AND s.active=1 ORDER BY v.name,s.sample_type,s.process_stage,s.analyte_name,s.unit",
        (estate_id(),),
    )


@router.put("/api/v1/labs/variety-standards", dependencies=[Depends(authorize_write)])
def save_variety_lab_standard(payload: VarietyLabStandardUpsert, request: Request) -> dict[str, Any]:
    require_discipline_approval(request, "enology")
    variety = fetch_one(
        "SELECT id,name FROM grape_varieties WHERE id=%s AND estate_id=%s AND active=1",
        (payload.variety_id, estate_id()),
    )
    if not variety:
        raise HTTPException(404, "Active grape variety not found")
    values = payload.model_dump()
    values["process_stage"] = "_".join(values["process_stage"].strip().casefold().split())
    values["analyte_code"] = values["analyte_code"].strip().casefold().replace(" ", "_")
    values["analyte_name"] = values["analyte_name"].strip()
    values["unit"] = values["unit"].strip()
    values["source_reference"] = values["source_reference"].strip()
    existing = None
    if values.get("id"):
        existing = fetch_one("SELECT id FROM variety_lab_standards WHERE id=%s AND estate_id=%s", (values["id"], estate_id()))
        if not existing:
            raise HTTPException(404, "Variety laboratory standard not found")
    if not existing:
        existing = fetch_one(
            "SELECT id FROM variety_lab_standards WHERE estate_id=%s AND variety_id=%s AND sample_type=%s AND process_stage=%s AND analyte_code=%s AND unit=%s",
            (estate_id(), values["variety_id"], values["sample_type"], values["process_stage"], values["analyte_code"], values["unit"]),
        )
    record_id, actor = (existing or {}).get("id") or new_id(), request_username(request)
    with transaction() as (_, cursor):
        if existing:
            cursor.execute(
                "UPDATE variety_lab_standards SET variety_id=%s,sample_type=%s,process_stage=%s,analyte_code=%s,analyte_name=%s,unit=%s,target_min=%s,target_max=%s,source_reference=%s,notes=%s,approved_by=%s,approved_at=NOW(6),active=1 WHERE id=%s AND estate_id=%s",
                (values["variety_id"], values["sample_type"], values["process_stage"], values["analyte_code"], values["analyte_name"], values["unit"], values["target_min"], values["target_max"], values["source_reference"], values["notes"], actor, record_id, estate_id()),
            )
        else:
            cursor.execute(
                "INSERT INTO variety_lab_standards (id,estate_id,variety_id,sample_type,process_stage,analyte_code,analyte_name,unit,target_min,target_max,source_reference,notes,approved_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (record_id, estate_id(), values["variety_id"], values["sample_type"], values["process_stage"], values["analyte_code"], values["analyte_name"], values["unit"], values["target_min"], values["target_max"], values["source_reference"], values["notes"], actor),
            )
        audit(cursor, "approve_standard", "variety_lab_standard", record_id, {**values, "variety_name": variety["name"], "approved_by": actor}, actor)
    return fetch_one(
        "SELECT s.*,v.name variety_name FROM variety_lab_standards s JOIN grape_varieties v ON v.id=s.variety_id WHERE s.id=%s AND s.estate_id=%s",
        (record_id, estate_id()),
    ) or {"id": record_id}


@router.delete("/api/v1/labs/variety-standards/{standard_id}", dependencies=[Depends(authorize_write)])
def remove_variety_lab_standard(standard_id: str, request: Request) -> dict[str, bool]:
    require_discipline_approval(request, "enology")
    actor = request_username(request)
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE variety_lab_standards SET active=0,approved_by=%s,approved_at=NOW(6) WHERE id=%s AND estate_id=%s AND active=1",
            (actor, standard_id, estate_id()),
        )
        if not changed:
            raise HTTPException(404, "Variety laboratory standard not found")
        audit(cursor, "deactivate_standard", "variety_lab_standard", standard_id, {"active": False}, actor)
    return {"ok": True}


def _result_signature(rows: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    signature: list[tuple[str, str, str, str]] = []
    for row in rows:
        numeric_value = row.get("numeric_value")
        numeric_text = "" if numeric_value is None else f"{float(numeric_value):.8g}"
        signature.append((
            str(row.get("analyte_code") or "").strip().casefold(),
            numeric_text,
            str(row.get("text_value") or "").strip().casefold(),
            str(row.get("unit") or "").strip().casefold().replace(" ", ""),
        ))
    return sorted(signature)


def _automatic_decision_support(sample_id: str) -> dict[str, Any]:
    try:
        return lab_sample_decision_support(sample_id)
    except Exception as error:
        return {
            "sample_id": sample_id,
            "status": "analysis_unavailable",
            "overall_assessment": "Measured results were saved, but the automatic decision-support summary needs review.",
            "missing_evidence": [str(error)[:220]],
            "decision_boundary": "No operational action is inferred from an unavailable summary.",
        }


@router.post("/api/v1/lab-samples", status_code=201, dependencies=[Depends(authorize_write)])
def create_lab_sample(payload: LabSampleCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    if payload.sample_type == "grape" and not payload.variety_id:
        raise HTTPException(422, "Choose the grape variety so this report updates the correct harvest prediction")
    linked_vintage = None
    if payload.wine_lot_id:
        linked_lot = fetch_one(
            "SELECT s.vintage_year FROM wine_lots w JOIN seasons s ON s.id=w.season_id WHERE w.id=%s AND w.estate_id=%s",
            (payload.wine_lot_id, estate_id()),
        )
        if not linked_lot:
            raise HTTPException(404, "Wine lot not found")
        linked_vintage = int(linked_lot["vintage_year"])
    sample_year = linked_vintage or payload.vintage_year or (payload.lab_date.year if payload.sample_type in {"grape", "must"} else year)
    if linked_vintage:
        vintage_source, vintage_confidence = "wine_lot", "confirmed"
        vintage_evidence = "Vintage inherited from the linked wine lot."
    elif payload.vintage_year:
        vintage_source, vintage_confidence = "manual", "confirmed"
        vintage_evidence = payload.vintage_assignment_evidence or "Vintage explicitly selected when the laboratory report was entered."
    elif payload.sample_type in {"grape", "must"}:
        vintage_source, vintage_confidence = "report_date", "confirmed"
        vintage_evidence = "Fruit and must report belongs to the harvest year shown by its laboratory date."
    else:
        vintage_source, vintage_confidence = "selected_vintage", "inferred"
        vintage_evidence = payload.vintage_assignment_evidence or "Wine vintage selected from the active dashboard year; verify against the report or linked wine lot."

    incoming_signature = _result_signature([result.model_dump() for result in payload.results])
    canonical_name = _canonical_sample_name(payload.sample_name, payload.sample_type)
    display_name = _sample_display_name(payload.sample_name, payload.sample_type)
    possible_duplicates = fetch_all(
        "SELECT id FROM lab_samples WHERE estate_id=%s AND sample_type=%s AND lab_date=%s "
        "AND COALESCE(canonical_sample_name,LOWER(TRIM(sample_name)))=%s AND vintage_year=%s "
        "AND (variety_id <=> %s) AND (wine_lot_id <=> %s) AND (LOWER(TRIM(laboratory)) <=> LOWER(TRIM(%s)))",
        (estate_id(), payload.sample_type, payload.lab_date, canonical_name, sample_year, payload.variety_id, payload.wine_lot_id, payload.laboratory),
    )
    for possible in possible_duplicates:
        existing_results = fetch_all(
            "SELECT analyte_code,numeric_value,text_value,unit FROM lab_results WHERE sample_id=%s",
            (possible["id"],),
        )
        if _result_signature(existing_results) == incoming_signature:
            from .lab_analyte_mapping import map_sample_analytes
            mapping = map_sample_analytes(possible["id"])
            return {"id": possible["id"], "prediction_refresh": "not_applicable", "duplicate": True, "workflow_area": lab_workflow_area(payload.sample_type), "analyte_mapping": mapping, "decision_support": _automatic_decision_support(possible["id"])}

    record_id, season_id = new_id(), season_for_year(sample_year)
    values = payload.model_dump(exclude={"results"})
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_samples (id,estate_id,season_id,block_id,variety_id,wine_lot_id,sample_name,source_sample_name,canonical_sample_name,sample_type,sampled_at,lab_date,vintage_year,vintage_assignment_source,vintage_assignment_confidence,vintage_assignment_evidence,laboratory,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["variety_id"], values["wine_lot_id"], display_name, values["sample_name"], canonical_name, values["sample_type"], values["sampled_at"], values["lab_date"], sample_year, vintage_source, vintage_confidence, vintage_evidence, values["laboratory"], values["notes"]))
        for result in payload.results:
            item = result.model_dump()
            cursor.execute("INSERT INTO lab_results (id,sample_id,analyte_code,analyte_name,numeric_value,text_value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)", (new_id(), record_id, item["analyte_code"], item["analyte_name"], item["numeric_value"], item["text_value"], item["unit"]))
        audit(cursor, "create", "lab_sample", record_id, payload.model_dump())
    if payload.sample_type == "grape":
        request_harvest_refresh("lab_sample", record_id, "New reviewed grape laboratory evidence saved")
    try:
        lab_learning = refresh_lab_learning(record_id)
    except Exception as error:
        lab_learning = {"model_status": "refresh_failed", "error": str(error)[:300]}
    from .lab_analyte_mapping import map_sample_analytes
    analyte_mapping = map_sample_analytes(record_id)
    return {"id": record_id, "prediction_refresh": "queued" if payload.sample_type == "grape" else "not_applicable", "duplicate": False, "lab_learning": lab_learning, "workflow_area": lab_workflow_area(payload.sample_type), "analyte_mapping": analyte_mapping, "decision_support": _automatic_decision_support(record_id)}
