from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_write
from .olives import save_harvest_preference


router = APIRouter(prefix="/api/v1/olives", tags=["olives"])


@router.put("/harvest-preference/{year}", dependencies=[Depends(authorize_write)])
def save_harvest_preference_route(year: int, request: Request, payload: dict[str, Any]) -> dict[str, bool]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        save_harvest_preference(year, payload, actor)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"saved": True}
