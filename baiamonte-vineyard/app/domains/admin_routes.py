"""Thin administrative routes backed by bounded Admin Control services."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..access import authorize_admin
from ..service import estate_id, estate_year
from .admin_control import admin_runtime_payload
from .payroll import payroll_summary
from .official_documents import router as official_documents_router


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
router.include_router(official_documents_router)
_ROUTER_STARTED_MONOTONIC = time.monotonic()


@router.get("/payroll", dependencies=[Depends(authorize_admin)])
def admin_payroll(request: Request) -> dict[str, Any]:
    """Load the ledger without runtime, camera catalog or live HA dependencies."""
    from ..main import _admin_control_payload

    return _admin_control_payload(request, payroll_only=True)


@router.get("/control/runtime", dependencies=[Depends(authorize_admin)])
def admin_control_runtime() -> dict[str, Any]:
    """Load process, connection, recovery, and runtime status independently."""
    payload = admin_runtime_payload(_ROUTER_STARTED_MONOTONIC)
    payload.update({"scope": "runtime", "payroll": payroll_summary(estate_id(), estate_year())})
    return payload
