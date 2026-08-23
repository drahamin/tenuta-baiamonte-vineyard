"""Thin administrative routes backed by bounded Admin Control services."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends

from ..access import authorize_admin
from .admin_control import admin_runtime_payload


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
_ROUTER_STARTED_MONOTONIC = time.monotonic()


@router.get("/control/runtime", dependencies=[Depends(authorize_admin)])
def admin_control_runtime() -> dict[str, Any]:
    """Load process, connection, recovery, and runtime status independently."""
    return admin_runtime_payload(_ROUTER_STARTED_MONOTONIC)
