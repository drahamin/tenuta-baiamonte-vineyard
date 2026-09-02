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


def calculate_blend_program(
    nerello_kg: float,
    grenache_available_kg: float,
    grecanico_kg: float,
    grenache_pct: float = 6.5,
    crate_weight_kg: float = 15.0,
    yield_l_per_kg: float = DEFAULT_RED_WINE_YIELD_L_PER_KG,
    tank_working_fill_pct: float = 90.0,
) -> dict[str, Any]:
    """Calculate the three-wine program with Grenache as final-blend percent."""
    nerello = max(float(nerello_kg or 0), 0)
    grenache = max(float(grenache_available_kg or 0), 0)
    grecanico = max(float(grecanico_kg or 0), 0)
    pct = float(grenache_pct or 0)
    crate = float(crate_weight_kg or 0)
    yield_factor = float(yield_l_per_kg or 0)
    fill_pct = float(tank_working_fill_pct or 0)
    if not 0 < pct < 50:
        raise ValueError("Grenache must be between 0 and 50 percent of the final blend")
    if crate <= 0 or yield_factor <= 0 or not 50 <= fill_pct <= 100:
        raise ValueError("Crate weight, wine yield and tank working fill must be valid positive values")
    required = nerello * pct / (100 - pct)
    exact_crates = required / crate
    whole_crates = math.ceil(exact_crates - 1e-9) if required else 0
    picked_kg = whole_crates * crate
    remaining = max(grenache - required, 0)
    shortage = max(required - grenache, 0)
    working_ratio = fill_pct / 100

    def wine(name: str, composition: str, grape_kg: float) -> dict[str, Any]:
        liters = grape_kg * yield_factor
        return {
            "finished_wine": name,
            "composition": composition,
            "grape_kg": round(grape_kg, 3),
            "wine_l": round(liters, 3),
            "bottles_750ml": math.floor(liters / 0.75),
            "gross_tank_capacity_l": round(liters / working_ratio, 3),
        }

    return {
        "nerello_kg": round(nerello, 3),
        "grenache_available_kg": round(grenache, 3),
        "grecanico_kg": round(grecanico, 3),
        "grenache_pct": round(pct, 3),
        "nerello_pct": round(100 - pct, 3),
        "required_grenache_kg": round(required, 3),
        "exact_grenache_crates": round(exact_crates, 3),
        "whole_grenache_crates": whole_crates,
        "whole_crate_pick_kg": round(picked_kg, 3),
        "whole_crate_rounding_surplus_kg": round(max(picked_kg - required, 0), 3),
        "remaining_grenache_kg": round(remaining, 3),
        "grenache_shortage_kg": round(shortage, 3),
        "wines": [
            wine("Nerello blend", f"{100 - pct:g}% Nerello / {pct:g}% Grenache", nerello + required),
            wine("Grecanico", "100% Grecanico", grecanico),
            wine("Grenache", "100% Grenache from balance", remaining),
        ],
    }


def calculate_grenache_crate_target(
    nerello_crates: float,
    grenache_pct: float = 6.5,
) -> dict[str, Any]:
    """Return the whole Grenache crates needed for a Nerello-led final blend."""
    nerello = float(nerello_crates or 0)
    pct = float(grenache_pct or 0)
    if not 0 < nerello <= 100000:
        raise ValueError("Nerello crates must be greater than zero")
    if not 0 < pct < 50:
        raise ValueError("Grenache must be between 0 and 50 percent of the final blend")
    exact = nerello * pct / (100 - pct)
    whole = math.ceil(exact - 1e-9)
    return {
        "nerello_crates": round(nerello, 3),
        "grenache_pct": round(pct, 3),
        "exact_grenache_crates": round(exact, 3),
        "whole_grenache_crates": whole,
        "total_planned_crates": round(nerello + whole, 3),
    }
