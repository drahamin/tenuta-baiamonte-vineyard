from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one, transaction


PUBLIC_HARVEST_VARIETIES = {
    "grecanico",
    "grenache",
    "nerello mascalese",
}


def _public_harvest_variety(value: Any) -> bool:
    """Keep internal placeholders and planning categories off the public site."""
    normalized = " ".join(str(value or "").strip().casefold().split())
    return normalized in PUBLIC_HARVEST_VARIETIES


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
        if not _public_harvest_variety(row.get("variety_name")):
            continue
        year = str(row.pop("vintage_year"))
        vintages.setdefault(year, []).append(json_ready(row))
    current_year = date.today().year
    current = fetch_all(
        "SELECT v.name variety,p.planned_pick_date plan_date,p.status,p.approved_by,p.confidence plan_confidence,p.forecast_method,p.updated_at plan_updated_at,"
        "g.final_forecast_date,g.predicted_date gdd_predicted_date,g.confidence forecast_confidence,g.computed_at forecast_updated_at,"
        "h.first_pick_date,h.last_pick_date,h.total_kg,h.total_crates,h.lot_count "
        "FROM grape_varieties v LEFT JOIN seasons s ON s.estate_id=v.estate_id AND s.vintage_year=%s "
        "LEFT JOIN harvest_plans p ON p.id=(SELECT p2.id FROM harvest_plans p2 WHERE p2.season_id=s.id AND p2.variety_id=v.id "
        "ORDER BY (p2.status IN ('confirmed','in_progress','complete','hold')) DESC,(p2.approved_by IS NOT NULL) DESC,p2.updated_at DESC LIMIT 1) "
        "LEFT JOIN (SELECT gf.* FROM gdd_forecasts gf JOIN (SELECT season_id,variety_id,MAX(computed_at) latest FROM gdd_forecasts GROUP BY season_id,variety_id) x ON x.season_id=gf.season_id AND x.variety_id=gf.variety_id AND x.latest=gf.computed_at) g ON g.season_id=s.id AND g.variety_id=v.id "
        "LEFT JOIN v_harvest_summary h ON h.estate_id=v.estate_id AND h.vintage_year=%s AND h.variety_id=v.id "
        "WHERE v.estate_id=%s AND v.active=1 ORDER BY v.name",
        (current_year, current_year, estate_id()),
    )
    current = [row for row in current if _public_harvest_variety(row.get("variety"))]
    for row in current:
        protected_plan = bool(row.get("approved_by") or row.get("status") in {"confirmed", "in_progress", "complete", "hold"})
        if row.get("first_pick_date"):
            row["predicted_date"] = row["first_pick_date"]
            row["date_source"] = "recorded_harvest"
            row["confidence"] = "high"
        elif protected_plan and row.get("plan_date"):
            row["predicted_date"] = row["plan_date"]
            row["date_source"] = "approved_plan" if row.get("approved_by") else "confirmed_plan"
            row["confidence"] = row.get("plan_confidence") or "high"
        else:
            row["predicted_date"] = row.get("final_forecast_date") or row.get("gdd_predicted_date") or row.get("plan_date")
            row["date_source"] = "scheduled_forecast" if row.get("final_forecast_date") or row.get("gdd_predicted_date") else "provisional_plan"
            row["confidence"] = row.get("forecast_confidence") or row.get("plan_confidence")
        row["human_approval_required"] = not protected_plan and not bool(row.get("first_pick_date"))
        row["updated_at"] = row.get("plan_updated_at") if protected_plan else row.get("forecast_updated_at") or row.get("plan_updated_at")
        row.pop("final_forecast_date", None)
        row.pop("gdd_predicted_date", None)
        row.pop("forecast_confidence", None)
        row.pop("plan_confidence", None)
        row.pop("forecast_updated_at", None)
        row.pop("plan_updated_at", None)
    weather = fetch_one(
        "SELECT observed_at,temp_c,feels_like_c,humidity_pct,dew_point_c,vpd_kpa,pressure_hpa,rain_mm,rain_rate_mm_h,wind_kph,wind_gust_kph,gust_max_today_kph,wind_direction_deg,wind_direction_10m_deg,solar_wm2,uv_index,leaf_wetness_pct,soil_moisture_pct,soil_temp_c FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    vineyard = fetch_one("SELECT COALESCE(SUM(vine_count),0) vine_count FROM vineyard_blocks WHERE estate_id=%s AND active=1", (estate_id(),)) or {}
    # MariaDB exposes DECIMAL columns as Decimal instances. Keep the public
    # feed JSON-native at its boundary so both FastAPI and the background
    # website publisher receive the same serializable payload.
    public_estate = {
        "slug": estate.get("slug"),
        "name": estate.get("name"),
        "timezone": estate.get("timezone"),
        "vine_count": vineyard.get("vine_count"),
    }
    return json_ready({
        "schema_version": 3,
        "estate": public_estate,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "vintages": vintages,
        "year": current_year,
        "items": current,
        "weather": weather,
    })
