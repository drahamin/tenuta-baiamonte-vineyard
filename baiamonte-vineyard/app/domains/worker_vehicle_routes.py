"""Administrative review endpoints for advisory worker vehicle/location learning."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..access import authorize_admin, request_username
from ..db import fetch_all, transaction
from ..service import audit, estate_id
from .worker_evidence_archive import evidence_metadata, extend_evidence_review, read_camera_evidence
from .worker_vehicle_presence import refresh_worker_vehicle_presence


router = APIRouter(prefix="/api/v1/admin/vehicle-learning", tags=["vehicle learning"])


@router.post("/scan", dependencies=[Depends(authorize_admin)])
def scan_worker_vehicles(request: Request) -> dict[str, Any]:
    """Analyze a fresh configured parking frame now, including outside the normal schedule."""
    result = refresh_worker_vehicle_presence(force=True)
    with transaction() as (_, cursor):
        audit(
            cursor,
            "run",
            "worker_vehicle_learning",
            str(result.get("camera") or "configured-camera"),
            {
                "updated": bool(result.get("updated")),
                "observations": int(result.get("observations") or 0),
                "reason": str(result.get("reason") or "")[:300],
            },
            request_username(request),
        )
    return result


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
    evidence_id = None
    promoted_to_present = False
    with transaction() as (_, cursor):
        if kind == "vehicle":
            cursor.execute(
                "SELECT evidence,presence_status FROM worker_vehicle_observations WHERE id=%s AND estate_id=%s",
                (observation_id, estate_id()),
            )
            row = cursor.fetchone() or {}
            try:
                evidence_id = str((json.loads(row.get("evidence") or "{}") or {}).get("evidence_id") or "") or None
            except (TypeError, ValueError):
                evidence_id = None
            promoted_to_present = status == "confirmed" and row.get("presence_status") == "uncertain"
        changed = cursor.execute(
            f"UPDATE {table} SET review_status=%s WHERE id=%s AND estate_id=%s",
            (status, observation_id, estate_id()),
        )
        if not changed:
            raise HTTPException(404, "Observation not found")
        if promoted_to_present:
            cursor.execute(
                "UPDATE worker_vehicle_observations SET presence_status='present',confidence_pct=GREATEST(confidence_pct,90) "
                "WHERE id=%s AND estate_id=%s",
                (observation_id, estate_id()),
            )
        audit(
            cursor, "review", kind + "_presence_observation", str(observation_id),
            {"status": status, "promoted_to_present": promoted_to_present}, actor,
        )
    if evidence_id:
        extend_evidence_review(evidence_id, status)
    return {
        "saved": True, "kind": kind, "observation_id": observation_id, "status": status,
        "promoted_to_present": promoted_to_present,
    }


@router.get("/evidence/{evidence_id}", dependencies=[Depends(authorize_admin)])
def view_camera_evidence(evidence_id: str, request: Request) -> Response:
    """Decrypt one retained frame for an administrator; every access is audited."""
    result = read_camera_evidence(evidence_id)
    if not result:
        raise HTTPException(404, "Camera evidence is unavailable or has expired")
    row, content = result
    with transaction() as (_, cursor):
        audit(
            cursor, "view", "worker_camera_evidence", evidence_id,
            {"camera": row.get("camera_entity_id"), "captured_at": row.get("captured_at")},
            request_username(request),
        )
    return Response(
        content,
        media_type=str(row.get("content_type") or "image/jpeg"),
        headers={"Cache-Control": "private, no-store", "Content-Disposition": f'inline; filename="evidence-{evidence_id[:12]}.jpg"'},
    )


@router.patch("/evidence/{evidence_id}", dependencies=[Depends(authorize_admin)])
def update_camera_evidence(evidence_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Allow an administrator to place or remove a deliberate evidence hold."""
    if evidence_metadata(evidence_id) is None:
        raise HTTPException(404, "Camera evidence not found")
    legal_hold = bool(payload.get("legal_hold"))
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE worker_camera_evidence SET legal_hold=%s WHERE estate_id=%s AND id=%s",
            (legal_hold, estate_id(), evidence_id),
        )
        audit(cursor, "legal_hold" if legal_hold else "release_hold", "worker_camera_evidence", evidence_id, {}, request_username(request))
    return {"saved": True, "evidence_id": evidence_id, "legal_hold": legal_hold}
