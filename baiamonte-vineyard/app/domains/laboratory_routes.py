from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..access import authorize, authorize_write
from ..db import fetch_all, fetch_one, transaction
from .laboratory import _canonical_sample_name, _sample_display_name, lab_learning_status, refresh_lab_learning
from ..models import LabSampleCreate
from ..prediction_refresh import request_harvest_refresh
from ..service import audit, estate_id, new_id, season_for_year


router = APIRouter()


@router.get("/api/v1/labs/learning-status", dependencies=[Depends(authorize)])
def get_lab_learning_status() -> dict[str, Any]:
    return lab_learning_status()


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
    canonical_name = _canonical_sample_name(payload.sample_name)
    display_name = _sample_display_name(payload.sample_name)
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
            return {"id": possible["id"], "prediction_refresh": "not_applicable", "duplicate": True}

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
    return {"id": record_id, "prediction_refresh": "queued" if payload.sample_type == "grape" else "not_applicable", "duplicate": False, "lab_learning": lab_learning}
