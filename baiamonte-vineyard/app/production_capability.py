"""Evidence-backed production capacity for harvest and cellar screens."""

from __future__ import annotations

import math
from typing import Any

from .db import fetch_all, fetch_one
from .historical_dashboard import all_vintage_rows
from .service import estate_id
from .varietal_yield import build_varietal_yield_profiles, variety_key
from .wine_conversion import DEFAULT_RED_WINE_YIELD_L_PER_KG


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def summarize_production_capability(
    fruit_rows: list[dict[str, Any]],
    lot_rows: list[dict[str, Any]],
    tank_rows: list[dict[str, Any]],
    legal_scenarios: list[dict[str, Any]],
    *,
    bottle_ml: int = 750,
    working_fill_pct: float = 90.0,
    yield_profiles: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Keep physical actuals, vessel capacity and conditional legal ceilings separate."""
    fruit_by_variety = {
        str(row.get("variety_name") or "Unassigned"): row for row in fruit_rows
    }
    lots_by_variety = {
        str(row.get("variety_name") or "Unassigned"): row for row in lot_rows
    }
    names = sorted(set(fruit_by_variety) | set(lots_by_variety), key=str.casefold)
    bottle_l = bottle_ml / 1000
    streams = []
    yield_profiles = yield_profiles or {}
    for name in names:
        fruit = fruit_by_variety.get(name, {})
        lots = lots_by_variety.get(name, {})
        measured_l = _number(lots.get("measured_wine_l"))
        fruit_kg = _number(fruit.get("fruit_kg"))
        profile = yield_profiles.get(variety_key(name), {})
        streams.append({
            "variety_name": name,
            "estate_fruit_kg": round(_number(fruit.get("estate_fruit_kg")), 3),
            "purchased_fruit_kg": round(_number(fruit.get("purchased_fruit_kg")), 3),
            "fruit_received_kg": round(fruit_kg, 3),
            "measured_wine_l": round(measured_l, 3),
            "full_bottle_equivalents": math.floor(measured_l / bottle_l) if bottle_l else 0,
            "observed_l_per_kg": round(measured_l / fruit_kg, 3) if fruit_kg and measured_l else None,
            "predictive_l_per_kg": profile.get("predictive_l_per_kg"),
            "predicted_l_from_received_grapes": profile.get("predicted_l_from_received_grapes"),
            "prediction_source": profile.get("prediction_source"),
            "historical_vintage_count": profile.get("historical_vintage_count", 0),
            "historical_vintages": profile.get("historical_vintages", []),
            "prediction_confidence": profile.get("confidence"),
            "unmeasured_lot_count": int(lots.get("unmeasured_lot_count") or 0),
            "lot_count": int(lots.get("lot_count") or 0),
        })

    nominal_l = sum(_number(row.get("capacity_l")) for row in tank_rows)
    occupied_l = sum(_number(row.get("occupied_l")) for row in tank_rows)
    working_l = nominal_l * working_fill_pct / 100
    measured_l = sum(_number(row.get("measured_wine_l")) for row in lot_rows)
    fruit_kg = sum(_number(row.get("fruit_kg")) for row in fruit_rows)
    unmeasured = sum(int(row.get("unmeasured_lot_count") or 0) for row in lot_rows)
    warnings = []
    if unmeasured:
        warnings.append(f"{unmeasured} lot{'s' if unmeasured != 1 else ''} still need a measured liquid volume before final yield or bottle output can be stated.")
    if occupied_l > working_l + 0.001:
        warnings.append("Recorded vessel occupancy exceeds the configured 90% fermentation working capacity; confirm safe headspace for active ferments.")
    if legal_scenarios:
        warnings.append("Legal scenarios are documentary ceilings, not additive production or a live SIAN entitlement; current eligibility still requires written confirmation.")
    return {
        "fruit_received_kg": round(fruit_kg, 3),
        "measured_wine_l": round(measured_l, 3),
        "full_bottle_equivalents": math.floor(measured_l / bottle_l) if bottle_l else 0,
        "bottle_size_ml": bottle_ml,
        "observed_l_per_kg": round(measured_l / fruit_kg, 3) if fruit_kg and measured_l else None,
        "vessels": {
            "active_count": len(tank_rows),
            "nominal_capacity_l": round(nominal_l, 3),
            "working_capacity_l": round(working_l, 3),
            "recorded_occupancy_l": round(occupied_l, 3),
            "available_working_capacity_l": round(max(working_l - occupied_l, 0), 3),
            "working_fill_pct": working_fill_pct,
        },
        "streams": streams,
        "unmeasured_lot_count": unmeasured,
        "legal_scenarios": legal_scenarios,
        "warnings": warnings,
        "yield_profiles": yield_profiles,
        "basis": "Actual fruit receipts and measured current lot volumes are reconciled separately from per-variety predictions. Predictions use reconciled prior vintages or an explicit enologist override; current transfers never train the model.",
    }


def production_capability(year: int) -> dict[str, Any]:
    season = fetch_one(
        "SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    season_id = season.get("id", "")
    fruit_rows = fetch_all(
        "SELECT v.name variety_name,SUM(h.weight_kg) fruit_kg,"
        "SUM(CASE WHEN h.source_type='estate_harvest' THEN h.weight_kg ELSE 0 END) estate_fruit_kg,"
        "SUM(CASE WHEN h.source_type='purchased' THEN h.weight_kg ELSE 0 END) purchased_fruit_kg "
        "FROM harvest_lots h JOIN grape_varieties v ON v.id=h.variety_id "
        "WHERE h.estate_id=%s AND h.season_id=%s GROUP BY v.id,v.name",
        (estate_id(), season_id),
    ) if season_id else []
    lot_rows = fetch_all(
        "SELECT COALESCE(NULLIF(TRIM(w.variety_summary),''),'Unassigned') variety_name,"
        "SUM(COALESCE(w.volume_l,w.initial_l,0)) measured_wine_l,SUM(COALESCE(w.initial_l,0)) initial_liquid_l,COUNT(*) lot_count,"
        "SUM(CASE WHEN w.volume_l IS NULL AND w.initial_l IS NULL THEN 1 ELSE 0 END) unmeasured_lot_count "
        "FROM wine_lots w WHERE w.estate_id=%s AND w.season_id=%s "
        "GROUP BY COALESCE(NULLIF(TRIM(w.variety_summary),''),'Unassigned')",
        (estate_id(), season_id),
    ) if season_id else []
    tank_rows = fetch_all(
        "SELECT c.id,c.capacity_l,COALESCE((SELECT SUM(COALESCE(w.volume_l,w.initial_l)) FROM wine_lots w "
        "WHERE w.current_container_id=c.id AND w.season_id=%s),cp.manual_volume_l,0) occupied_l "
        "FROM cellar_containers c LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id "
        "WHERE c.estate_id=%s AND c.active=1",
        (season_id, estate_id()),
    ) if season_id else []
    legal_scenarios = fetch_all(
        "SELECT scenario_code,scenario_label,denomination,eligibility_status,grapes_kg,wine_l,full_bottles_750ml,source_name,caveat "
        "FROM production_capacity_references WHERE estate_id=%s AND vintage_year=%s ORDER BY display_order,scenario_code",
        (estate_id(), year),
    )
    settings = fetch_one(
        "SELECT expected_yield_l_per_kg FROM varietal_program_settings WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    saved_yields = fetch_all(
        "SELECT v.name variety_name,y.expected_finished_wine_l_per_kg FROM varietal_yield_settings y "
        "JOIN grape_varieties v ON v.id=y.variety_id WHERE y.estate_id=%s",
        (estate_id(),),
    )
    yield_profiles = build_varietal_yield_profiles(
        year,
        all_vintage_rows(),
        fruit_rows,
        lot_rows,
        fallback_l_per_kg=float(settings.get("expected_yield_l_per_kg") or DEFAULT_RED_WINE_YIELD_L_PER_KG),
        overrides={str(row["variety_name"]): float(row["expected_finished_wine_l_per_kg"]) for row in saved_yields},
    )
    return summarize_production_capability(fruit_rows, lot_rows, tank_rows, legal_scenarios, yield_profiles=yield_profiles)
