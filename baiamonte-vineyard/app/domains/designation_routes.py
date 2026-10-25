from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..access import authorize, authorize_write
from ..designation_planning import designation_planning_dashboard, save_designation_plan, simulate_designation
from ..estate_time import estate_year
from ..service import json_ready


router = APIRouter(prefix="/api/v1/vintage", tags=["vintage-designation"])


@router.get("/designation-plans", dependencies=[Depends(authorize)])
def designation_plans(year: int = Query(default_factory=estate_year)) -> dict:
    return designation_planning_dashboard(year)


@router.post("/designation-simulate", dependencies=[Depends(authorize)])
def designation_simulate(payload: dict, year: int = Query(default_factory=estate_year)) -> dict:
    try:
        return json_ready(simulate_designation(year, payload))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/designation-plans", status_code=201, dependencies=[Depends(authorize_write)])
def create_designation_plan(payload: dict, request: Request, year: int = Query(default_factory=estate_year)) -> dict:
    try:
        actor = request.headers.get("X-Remote-User-Name") or "api"
        return json_ready(save_designation_plan(year, payload, actor))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
