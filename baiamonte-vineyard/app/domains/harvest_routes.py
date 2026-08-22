"""Harvest intake, traceability, and two-stage weight reconciliation."""

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..access import authorize_write
from ..db import transaction
from ..models import HarvestCreate, HarvestWineryWeightUpdate
from ..prediction_refresh import request_harvest_refresh
from ..service import audit, estate_id, new_id, season_for_year


router = APIRouter(prefix="/api/v1/harvest", tags=["harvest"])


def _validate_owned_ids(cursor, table: str, record_ids: list[str], message: str) -> None:
    if not record_ids:
        return
    placeholders = ",".join(["%s"] * len(record_ids))
    cursor.execute(
        f"SELECT id FROM {table} WHERE estate_id=%s AND id IN ({placeholders})",
        (estate_id(), *record_ids),
    )
    found = {str(row["id"]) for row in cursor.fetchall()}
    if found != set(record_ids):
        raise HTTPException(422, message)


@router.post("", status_code=201, dependencies=[Depends(authorize_write)])
def create_harvest(
    payload: HarvestCreate,
    year: int = Query(default_factory=lambda: date.today().year),
) -> dict[str, Any]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    parcel_ids = values.pop("parcel_ids", [])
    block_ids = values.pop("block_ids", [])
    values.pop("net_kg_per_crate", None)
    if values.get("block_id") and values["block_id"] not in block_ids:
        block_ids.insert(0, values["block_id"])
    values["block_id"] = block_ids[0] if block_ids else None
    avg_crate = values["weight_kg"] / values["crate_count"] if values["weight_kg"] is not None and values["crate_count"] else None
    with transaction() as (_, cursor):
        _validate_owned_ids(cursor, "vineyard_blocks", block_ids, "Choose only vineyard blocks belonging to Baiamonte")
        _validate_owned_ids(cursor, "cadastral_parcels", parcel_ids, "Choose only legal parcels belonging to Baiamonte")
        cursor.execute(
            "INSERT INTO harvest_lots (id,estate_id,season_id,lot_code,block_id,variety_id,harvested_at,planned_date,planned_kg,gross_kg,tare_kg,weight_kg,field_weight_kg,crate_count,avg_crate_kg,fruit_temp_c,destination,brix,babo,ph,ta_g_l,condition_grade,status,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                record_id, estate_id(), season_id, values["lot_code"], values["block_id"], values["variety_id"],
                values["harvested_at"], values["planned_date"], values["planned_kg"], values["gross_kg"],
                values["tare_kg"], values["weight_kg"], values["weight_kg"], values["crate_count"], avg_crate,
                values["fruit_temp_c"], values["destination"], values["brix"], values["babo"], values["ph"],
                values["ta_g_l"], values["condition_grade"], values["status"], values["notes"],
            ),
        )
        for block_id in block_ids:
            cursor.execute(
                "INSERT INTO harvest_lot_blocks (id,estate_id,harvest_lot_id,block_id) VALUES (%s,%s,%s,%s)",
                (new_id(), estate_id(), record_id, block_id),
            )
        for parcel_id in parcel_ids:
            cursor.execute(
                "INSERT INTO harvest_lot_parcels (id,estate_id,harvest_lot_id,parcel_id) VALUES (%s,%s,%s,%s)",
                (new_id(), estate_id(), record_id, parcel_id),
            )
        audit(cursor, "create", "harvest_lot", record_id, {**values, "block_ids": block_ids, "parcel_ids": parcel_ids})
    request_harvest_refresh("harvest_lot", record_id, "Actual harvest evidence saved")
    return {
        "id": record_id,
        "prediction_refresh": "queued",
        "block_count": len(block_ids),
        "parcel_count": len(parcel_ids),
    }


@router.patch("/{harvest_id}/winery-weight", dependencies=[Depends(authorize_write)])
def update_winery_weight(harvest_id: str, payload: HarvestWineryWeightUpdate) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT id,weight_kg,field_weight_kg,winery_weight_kg,crate_count,status FROM harvest_lots WHERE id=%s AND estate_id=%s FOR UPDATE",
            (harvest_id, estate_id()),
        )
        before = cursor.fetchone()
        if not before:
            raise HTTPException(404, "Harvest lot not found")
        weighed_at = payload.weighed_at or datetime.now(timezone.utc)
        avg_crate = payload.winery_weight_kg / before["crate_count"] if before.get("crate_count") else None
        cursor.execute(
            "UPDATE harvest_lots SET winery_weight_kg=%s,winery_weighed_at=%s,winery_weight_notes=%s,weight_kg=%s,avg_crate_kg=%s,status='reconciled' WHERE id=%s AND estate_id=%s",
            (payload.winery_weight_kg, weighed_at, payload.notes, payload.winery_weight_kg, avg_crate, harvest_id, estate_id()),
        )
        after = {
            "winery_weight_kg": payload.winery_weight_kg,
            "winery_weighed_at": weighed_at,
            "winery_weight_notes": payload.notes,
            "field_weight_kg": (
                before.get("field_weight_kg")
                if before.get("field_weight_kg") is not None
                else before.get("weight_kg")
            ),
            "weight_kg": payload.winery_weight_kg,
            "status": "reconciled",
        }
        audit(cursor, "update", "harvest_lot_winery_weight", harvest_id, {"before": before, "after": after})
    request_harvest_refresh("harvest_lot", harvest_id, "Winery scale weight reconciled")
    return {"id": harvest_id, "authoritative_weight_kg": payload.winery_weight_kg, "prediction_refresh": "queued"}
