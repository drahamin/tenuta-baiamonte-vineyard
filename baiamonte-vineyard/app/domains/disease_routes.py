from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize, authorize_write
from ..db import fetch_all, transaction
from ..intelligence import disease_pressure_learning_status, fit_disease_pressure_model, risk_level
from ..service import audit, estate_id, json_ready
from .people_roles import require_discipline_approval


router = APIRouter()


@router.get("/api/v1/disease-pressure", dependencies=[Depends(authorize)])
def disease_pressure() -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' "
        "AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date DESC,risk_score DESC",
        (estate_id(),),
    ))


@router.patch("/api/v1/disease-pressure/{assessment_id}/review", dependencies=[Depends(authorize_write)])
def review_disease_pressure(assessment_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = payload.get("agronomist_status")
    if status not in {"approved", "modified", "rejected", "not_required"}:
        raise HTTPException(422, "Choose an agronomist review status")
    require_discipline_approval(request, "agronomy")
    corrected_score = payload.get("agronomist_risk_score")
    if status in {"modified", "rejected"} and corrected_score in {None, ""}:
        raise HTTPException(422, "Enter the Agronomist's corrected risk score")
    try:
        corrected_score = None if corrected_score in {None, ""} else max(0.0, min(100.0, float(corrected_score)))
    except (TypeError, ValueError):
        raise HTTPException(422, "Corrected risk score must be between 0 and 100")
    corrected_level = risk_level(corrected_score) if corrected_score is not None else None
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE disease_pressure_assessments SET agronomist_status=%s,agronomist_risk_score=%s,agronomist_risk_level=%s,"
            "agronomist_name=%s,agronomist_notes=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s",
            (status, corrected_score, corrected_level, actor, payload.get("agronomist_notes"), assessment_id, estate_id()),
        )
        if not changed:
            raise HTTPException(404, "Assessment not found")
        audit(cursor, "agronomist_review", "disease_pressure_assessment", assessment_id, {
            "agronomist_status": status, "agronomist_risk_score": corrected_score,
            "agronomist_risk_level": corrected_level, "agronomist_notes": payload.get("agronomist_notes"),
        }, actor)
    fit_disease_pressure_model()
    return {"saved": True}


@router.get("/api/v1/disease-pressure/learning-status", dependencies=[Depends(authorize)])
def disease_pressure_model_status() -> dict[str, Any]:
    return json_ready(disease_pressure_learning_status())
