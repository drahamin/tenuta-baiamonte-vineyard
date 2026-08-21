from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize, authorize_write
from .bottling import complete_run, dashboard, save_cost, save_winemaking_plan


router = APIRouter(prefix="/api/v1/bottling", tags=["bottling"])


@router.get("/dashboard", dependencies=[Depends(authorize)])
def bottling_dashboard(year: int = date.today().year) -> dict[str, Any]:
    return dashboard(year)


@router.post("/runs", dependencies=[Depends(authorize_write)])
def complete_bottling_run(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        run_id = complete_run(int(payload.get("year") or date.today().year), payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True, "run_id": run_id}


@router.put("/costs/{year}/{category}", dependencies=[Depends(authorize_write)])
def save_bottling_cost(year: int, category: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        save_cost(year, category, payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True}


@router.put("/winemaking/{year}", dependencies=[Depends(authorize_write)])
def save_annual_winemaking_cost(year: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        record_id = save_winemaking_plan(year, payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True, "id": record_id}
