from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one, transaction


def new_id() -> str:
    return str(uuid.uuid4())


def estate_id() -> str:
    return get_settings().estate_id


def season_for_year(year: int) -> str:
    row = fetch_one(
        "SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    )
    if row:
        return row["id"]
    season_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO seasons (id, estate_id, vintage_year, status) VALUES (%s,%s,%s,'active')",
            (season_id, estate_id(), year),
        )
    return season_id


def audit(cursor: Any, action: str, entity_type: str, entity_id: str, after: dict[str, Any], actor: str = "home-assistant") -> None:
    cursor.execute(
        "INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (estate_id(), actor, action, entity_type, entity_id, json.dumps(after, default=str)),
    )


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def public_harvest_feed() -> dict[str, Any]:
    estate = fetch_one("SELECT slug,name,timezone FROM estates WHERE id=%s", (estate_id(),)) or {}
    rows = fetch_all(
        "SELECT vintage_year,variety_name,first_pick_date,last_pick_date,total_kg,total_crates,lot_count,"
        "avg_brix,avg_ph,avg_ta_g_l FROM v_harvest_summary WHERE estate_id=%s "
        "ORDER BY vintage_year DESC,variety_name",
        (estate_id(),),
    )
    vintages: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        year = str(row.pop("vintage_year"))
        vintages.setdefault(year, []).append(json_ready(row))
    return {
        "schema_version": 1,
        "estate": estate,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "vintages": vintages,
    }
