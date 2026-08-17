from __future__ import annotations

import math
from typing import Any


def calculate_blend_program(
    nerello_kg: float,
    grenache_available_kg: float,
    grecanico_kg: float,
    grenache_pct: float = 6.5,
    crate_weight_kg: float = 15.0,
    yield_l_per_kg: float = 0.70,
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
