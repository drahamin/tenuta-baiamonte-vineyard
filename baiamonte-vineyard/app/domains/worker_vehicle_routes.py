"""Administrative review endpoints for advisory worker vehicle/location learning."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_admin, request_username
from ..db import fetch_all, transaction
from ..service import audit, estate_id


router = APIRouter(prefix="/api/v1/admin/vehicle-learning", tags=["vehicle learning"])


@router.get("/dashboard", dependencies=[Depends(authorize_admin)])
def vehicle_learning_dashboard() -> dict[str, Any]:
    """Return aggregate accuracy and camera coverage without exposing images or plates."""
    cameras = fetch_all(
        "SELECT camera_entity_id,COUNT(*) observations,"
        "SUM(review_status IN ('confirmed','rejected')) reviewed,"
        "SUM(review_status='confirmed') confirmed,MAX(observed_at) last_observed_at "
        "FROM worker_vehicle_observations WHERE estate_id=%s GROUP BY camera_entity_id ORDER BY last_observed_at DESC",
        (estate_id(),),
    )
    for row in cameras:
        reviewed = int(row.get("reviewed") or 0)
        row["review_accuracy_percent"] = round(int(row.get("confirmed") or 0) / reviewed * 100) if reviewed else None
    people = fetch_all(
        "SELECT source_kind,COUNT(*) observations,SUM(person_entity IS NOT NULL) linked,MAX(observed_at) last_observed_at "
        "FROM worker_person_observations WHERE estate_id=%s GROUP BY source_kind ORDER BY source_kind",
        (estate_id(),),
    )
    unknown_labels = fetch_all(
        "SELECT observed_label,COUNT(*) observations,MAX(observed_at) last_observed_at "
        "FROM worker_person_observations WHERE estate_id=%s AND person_entity IS NULL "
        "GROUP BY observed_label ORDER BY last_observed_at DESC LIMIT 20",
        (estate_id(),),
    )
    return {
        "vehicle_cameras": cameras,
        "secondary_person_sources": people,
        "unlinked_eufy_labels": unknown_labels,
        "policy": "Vehicle evidence is primary. Named Eufy person evidence is secondary; unlabeled detections never create an identity.",
    }


@router.patch("/observations/{kind}/{observation_id}", dependencies=[Depends(authorize_admin)])
def review_vehicle_observation(kind: str, observation_id: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Confirm or reject one retained observation so source accuracy can learn."""
    status = str(payload.get("status") or "").strip().casefold()
    if status not in {"unreviewed", "confirmed", "rejected"}:
        raise HTTPException(422, "Status must be unreviewed, confirmed, or rejected")
    table = {"vehicle": "worker_vehicle_observations", "person": "worker_person_observations"}.get(kind)
    if not table:
        raise HTTPException(422, "Observation kind must be vehicle or person")
    actor = request_username(request)
    with transaction() as (_, cursor):
        changed = cursor.execute(
            f"UPDATE {table} SET review_status=%s WHERE id=%s AND estate_id=%s",
            (status, observation_id, estate_id()),
        )
        if not changed:
            raise HTTPException(404, "Observation not found")
        audit(cursor, "review", kind + "_presence_observation", str(observation_id), {"status": status}, actor)
    return {"saved": True, "kind": kind, "observation_id": observation_id, "status": status}
