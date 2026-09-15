from __future__ import annotations

import math
from typing import Any

from ..wine_conversion import DEFAULT_RED_WINE_YIELD_L_PER_KG

from ..db import fetch_all


def latest_scouting_by_variety(season_id: str) -> dict[str, dict[str, Any]]:
    """Resolve block, variety and estate scouting scopes to each affected variety."""
    if not season_id:
        return {}
    rows = fetch_all(
        "SELECT routed.variety_id,MAX(routed.observed_at) observed_at,"
        "SUBSTRING_INDEX(GROUP_CONCAT(routed.issue_type ORDER BY routed.observed_at DESC SEPARATOR '||'),'||',1) issue_type,"
        "MAX(routed.action_required) action_required FROM ("
        "SELECT bv.variety_id,so.observed_at,so.issue_type,so.action_required FROM scouting_observations so "
        "LEFT JOIN scouting_damage_scopes sds ON sds.observation_id=so.id JOIN block_varieties bv ON bv.block_id=so.block_id "
        "WHERE so.season_id=%s AND COALESCE(sds.damage_scope,'block') IN ('block','zone') UNION ALL "
        "SELECT sds.variety_id,so.observed_at,so.issue_type,so.action_required FROM scouting_observations so "
        "JOIN scouting_damage_scopes sds ON sds.observation_id=so.id WHERE so.season_id=%s AND sds.damage_scope='variety' AND sds.variety_id IS NOT NULL UNION ALL "
        "SELECT gv.id,so.observed_at,so.issue_type,so.action_required FROM scouting_observations so "
        "JOIN scouting_damage_scopes sds ON sds.observation_id=so.id JOIN grape_varieties gv ON gv.estate_id=so.estate_id AND gv.active=1 "
        "WHERE so.season_id=%s AND sds.damage_scope='estate'"
        ") routed GROUP BY routed.variety_id",
        (season_id, season_id, season_id),
    )
    return {row["variety_id"]: row for row in rows}


def calculate_varietal_program(
    nerello_kg: float,
    grenache_kg: float,
    grecanico_kg: float,
    crate_weight_kg: float = 15.0,
    yield_l_per_kg: float = DEFAULT_RED_WINE_YIELD_L_PER_KG,
    tank_working_fill_pct: float = 90.0,
) -> dict[str, Any]:
    """Calculate three independent varietal production streams."""
    nerello = max(float(nerello_kg or 0), 0)
    grenache = max(float(grenache_kg or 0), 0)
    grecanico = max(float(grecanico_kg or 0), 0)
    crate = float(crate_weight_kg or 0)
    yield_factor = float(yield_l_per_kg or 0)
    fill_pct = float(tank_working_fill_pct or 0)
    if crate <= 0 or yield_factor <= 0 or not 50 <= fill_pct <= 100:
        raise ValueError("Crate weight, wine yield and tank working fill must be valid positive values")
    working_ratio = fill_pct / 100

    def wine(name: str, grape_kg: float) -> dict[str, Any]:
        liters = grape_kg * yield_factor
        return {
            "finished_wine": name,
            "composition": f"100% {name}",
            "grape_kg": round(grape_kg, 3),
            "crates": math.ceil(grape_kg / crate - 1e-9) if grape_kg else 0,
            "wine_l": round(liters, 3),
            "bottles_750ml": math.floor(liters / 0.75),
            "gross_tank_capacity_l": round(liters / working_ratio, 3),
        }

    return {
        "nerello_kg": round(nerello, 3),
        "grenache_kg": round(grenache, 3),
        "grecanico_kg": round(grecanico, 3),
        "vinification_policy": "separate_varietals",
        "wines": [
            wine("Nerello Mascalese", nerello),
            wine("Grecanico", grecanico),
            wine("Grenache", grenache),
        ],
    }
