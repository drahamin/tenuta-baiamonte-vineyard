from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_finance
from ..db import transaction
from ..service import audit, estate_id


router = APIRouter(prefix="/api/v1/finance/inventory", tags=["finance"])


@router.patch("/{product_id}/stock-value", dependencies=[Depends(authorize_finance)])
def update_stock_value(product_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        unit_value = round(float(payload.get("unit_value_eur")), 2)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid stock value per unit") from error
    if unit_value < 0 or unit_value > 100000:
        raise HTTPException(422, "Stock value per unit must be between EUR 0 and EUR 100,000")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT s.id,s.quantity_on_hand,p.unit FROM inventory_snapshots s JOIN products p ON p.id=s.product_id "
            "WHERE s.estate_id=%s AND s.product_id=%s ORDER BY s.snapshot_date DESC,s.id DESC LIMIT 1 FOR UPDATE",
            (estate_id(), product_id),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Add an inventory count before setting its stock value")
        inventory_value = round(float(row.get("quantity_on_hand") or 0) * unit_value, 2)
        cursor.execute(
            "UPDATE inventory_snapshots SET average_sales_price=%s,inventory_value=%s WHERE id=%s AND estate_id=%s",
            (unit_value, inventory_value, row["id"], estate_id()),
        )
        audit(cursor, "update_stock_value", "inventory_snapshot", row["id"], {"product_id": product_id, "unit_value_eur": unit_value, "inventory_value_eur": inventory_value}, actor)
    return {"saved": True, "product_id": product_id, "unit": row.get("unit"), "unit_value_eur": unit_value, "inventory_value_eur": inventory_value}
