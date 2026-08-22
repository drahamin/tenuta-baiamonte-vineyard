from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize, authorize_write
from .fertilization import dashboard, save_review, save_sample
from .advanced_learning import refresh_young_vine_nutrition_learning


router = APIRouter(prefix="/api/v1/fertilization", tags=["fertilization"])


@router.get("/dashboard", dependencies=[Depends(authorize)])
def fertilization_dashboard(year: int = date.today().year) -> dict[str, Any]:
    return dashboard(year)


@router.post("/soil-samples", dependencies=[Depends(authorize_write)])
def create_soil_sample(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        record_id = save_sample(int(payload.get("year") or date.today().year), payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    try:
        learning = refresh_young_vine_nutrition_learning()
    except Exception as error:
        learning = {"status": "retry_required", "reason": str(error)[:300]}
    return {"saved": True, "id": record_id, "young_vine_learning": learning}


@router.put("/review/{year}", dependencies=[Depends(authorize_write)])
def update_fertilization_review(year: int, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        save_review(year, payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True}
