from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .db import fetch_all
from .service import estate_id, new_id


def _unit(value: Any) -> str:
    raw = str(value or "").strip().replace("ℓ", "L")
    aliases = {
        "l": "L", "liter": "L", "liters": "L", "litre": "L", "litres": "L",
        "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
        "kg": "kg", "kilogram": "kg", "kilograms": "kg",
        "g": "g", "gram": "g", "grams": "g",
    }
    return aliases.get(raw.casefold(), raw)


def total_used_unit(dose_unit: Any) -> str | None:
    """Return the physical unit represented by total_used; never infer density."""
    raw = str(dose_unit or "").strip().replace("ℓ", "L")
    token = raw.split("/", 1)[0].strip()
    normalized = _unit(token)
    return normalized if normalized in {"g", "kg", "ml", "L"} else None


def convert_inventory_quantity(value: Any, source_unit: Any, target_unit: Any, density_kg_l: Any = None) -> Decimal | None:
    """Convert inventory units, allowing mass/volume conversion only with verified density."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    source, target = _unit(source_unit), _unit(target_unit)
    if amount < 0 or source not in {"g", "kg", "ml", "L"} or target not in {"g", "kg", "ml", "L"}:
        return None
    if source == target:
        return amount
    factors = {("g", "kg"): Decimal("0.001"), ("kg", "g"): Decimal("1000"), ("ml", "L"): Decimal("0.001"), ("L", "ml"): Decimal("1000")}
    factor = factors.get((source, target))
    if factor is not None:
        return amount * factor
    try:
        density = Decimal(str(density_kg_l))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if density <= 0:
        return None
    mass_kg = amount * (Decimal("0.001") if source == "g" else Decimal("1")) if source in {"g", "kg"} else None
    volume_l = amount * (Decimal("0.001") if source == "ml" else Decimal("1")) if source in {"ml", "L"} else None
    if mass_kg is not None and target in {"ml", "L"}:
        result_l = mass_kg / density
        return result_l * (Decimal("1000") if target == "ml" else Decimal("1"))
    if volume_l is not None and target in {"g", "kg"}:
        result_kg = volume_l * density
        return result_kg * (Decimal("1000") if target == "g" else Decimal("1"))
    return None


def sync_treatment_inventory_use(cursor: Any, treatment_id: str) -> dict[str, Any]:
    """Post one idempotent negative inventory movement per confirmed treatment item."""
    cursor.execute(
        "SELECT a.id application_id,a.application_date,a.status,i.id item_id,i.total_used,i.dose_unit,"
        "p.id product_id,p.name product_name,p.unit product_unit,"
        "(SELECT r.density_kg_l FROM treatment_product_profiles r WHERE r.estate_id=a.estate_id AND r.product_id=p.id AND r.active=1 LIMIT 1) density_kg_l,"
        "(SELECT r.density_source FROM treatment_product_profiles r WHERE r.estate_id=a.estate_id AND r.product_id=p.id AND r.active=1 LIMIT 1) density_source "
        "FROM spray_applications a JOIN spray_application_items i ON i.application_id=a.id "
        "JOIN products p ON p.id=i.product_id WHERE a.id=%s AND a.estate_id=%s ORDER BY p.name,i.id FOR UPDATE",
        (treatment_id, estate_id()),
    )
    rows = list(cursor.fetchall())
    posted: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status") or "").casefold() not in {"completed", "applied"}:
            continue
        if row.get("total_used") is None:
            unresolved.append({"item_id": row["item_id"], "product_name": row["product_name"], "reason": "missing_total_used"})
            continue
        source_unit = total_used_unit(row.get("dose_unit"))
        converted = convert_inventory_quantity(row.get("total_used"), source_unit, row.get("product_unit"), row.get("density_kg_l"))
        if source_unit is None or converted is None:
            unresolved.append({"item_id": row["item_id"], "product_name": row["product_name"], "reason": "unit_conversion_requires_review", "recorded_unit": source_unit, "stock_unit": row.get("product_unit")})
            continue
        cursor.execute(
            "SELECT id FROM inventory_movements WHERE estate_id=%s AND reference_type='spray_application_item' AND reference_id=%s FOR UPDATE",
            (estate_id(), row["item_id"]),
        )
        movement = cursor.fetchone()
        quantity_delta = -converted.quantize(Decimal("0.001"))
        density_note = f" · density {row['density_kg_l']} kg/L ({row.get('density_source') or 'verified profile'})" if source_unit in {"g", "kg"} and row.get("product_unit") in {"ml", "L"} else ""
        notes = f"Confirmed treatment use: {row['product_name']} · application {treatment_id} · source total {row['total_used']} {source_unit}{density_note}."
        if movement:
            cursor.execute(
                "UPDATE inventory_movements SET product_id=%s,movement_date=%s,movement_type='use',quantity_delta=%s,notes=%s "
                "WHERE id=%s AND estate_id=%s",
                (row["product_id"], row["application_date"], quantity_delta, notes, movement["id"], estate_id()),
            )
            movement_id = movement["id"]
        else:
            movement_id = new_id()
            cursor.execute(
                "INSERT INTO inventory_movements (id,estate_id,product_id,movement_date,movement_type,quantity_delta,reference_type,reference_id,notes) "
                "VALUES (%s,%s,%s,%s,'use',%s,'spray_application_item',%s,%s)",
                (movement_id, estate_id(), row["product_id"], row["application_date"], quantity_delta, row["item_id"], notes),
            )
        posted.append({"movement_id": movement_id, "item_id": row["item_id"], "product_name": row["product_name"], "quantity": float(-quantity_delta), "unit": row.get("product_unit")})
    return {"posted": posted, "unresolved": unresolved, "complete": not unresolved}


def treatment_inventory_reconciliation(year: int | None = None) -> dict[str, Any]:
    params: list[Any] = [estate_id()]
    year_filter = ""
    if year is not None:
        year_filter = " AND YEAR(a.application_date)=%s"
        params.append(year)
    rows = fetch_all(
        "SELECT a.id application_id,a.purpose,a.application_date,i.id item_id,i.total_used,i.dose_unit,"
        "p.name product_name,p.unit product_unit,r.density_kg_l,r.density_source,m.id movement_id,m.quantity_delta "
        "FROM spray_applications a JOIN spray_application_items i ON i.application_id=a.id "
        "JOIN products p ON p.id=i.product_id LEFT JOIN treatment_product_profiles r "
        "ON r.estate_id=a.estate_id AND r.product_id=p.id AND r.active=1 LEFT JOIN inventory_movements m "
        "ON m.estate_id=a.estate_id AND m.reference_type='spray_application_item' AND m.reference_id=i.id "
        "WHERE a.estate_id=%s AND a.status IN ('completed','applied')" + year_filter + " ORDER BY a.application_date,p.name",
        tuple(params),
    )
    issues: list[dict[str, Any]] = []
    reconciled = 0
    for row in rows:
        source_unit = total_used_unit(row.get("dose_unit"))
        expected = convert_inventory_quantity(row.get("total_used"), source_unit, row.get("product_unit"), row.get("density_kg_l")) if row.get("total_used") is not None else None
        reason = None
        if row.get("total_used") is None:
            reason = "Exact total used is not recorded"
        elif expected is None:
            reason = f"Recorded {source_unit or 'unknown'} cannot be converted safely to stock unit {row.get('product_unit') or 'unknown'}"
        elif not row.get("movement_id"):
            reason = "Inventory use movement is missing"
        elif abs(Decimal(str(row.get("quantity_delta") or 0)) + expected) > Decimal("0.001"):
            reason = "Inventory movement does not match the confirmed treatment total"
        if reason:
            issues.append({**row, "reason": reason})
        else:
            reconciled += 1
    return {"complete": not issues, "reconciled_items": reconciled, "unresolved_items": len(issues), "issues": issues}
