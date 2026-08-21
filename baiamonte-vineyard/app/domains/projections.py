from __future__ import annotations

import math
from typing import Any

from ..production_impact import adjust_production_forecasts


def build_operational_projections(
    year: int,
    grapes: dict[str, Any],
    blend_program: dict[str, Any],
    conversion: float,
    forecast_evidence: dict[str, Any],
    production_forecasts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build planning scenarios from database records without implying a learned model."""
    blend_working = blend_program["planning"]
    planning_conversion = float(blend_program["settings"].get("expected_yield_l_per_kg") or conversion)
    vintages = grapes["vintages"]
    scenario_range = float(forecast_evidence.get("recommended_scenario_range_pct") or 15) / 100
    blend_plans = grapes.get("blend_plans") or []
    blend_kg = sum(float(row.get("target_grapes_kg") or 0) for row in blend_plans) or None
    blend_volume = sum(float(row.get("estimated_volume_l") or row.get("target_volume_l") or 0) for row in blend_plans) or None
    blend_crates = sum(float(row.get("estimated_crates") or 0) for row in blend_plans) or None
    planned_kg = grapes["metrics"].get("planned_kg")
    harvested_kg = grapes["metrics"].get("harvested_kg")
    has_adjusted_forecast = any(int(row.get("vintage_year") or 0) == year for row in production_forecasts)
    adjusted_basis_kg = sum(float(blend_working.get(field) or 0) for field in ("nerello_kg", "grenache_available_kg", "grecanico_kg"))
    basis_kg = adjusted_basis_kg if has_adjusted_forecast else blend_kg if blend_kg is not None else planned_kg if planned_kg is not None else harvested_kg
    adjusted_wine_l = sum(float(row.get("wine_l") or 0) for row in blend_working.get("wines") or [])
    scenarios = []
    for name, factor in (("Downside", 1 - scenario_range), ("Working", 1.0), ("Upside", 1 + scenario_range)):
        kg = float(basis_kg) * factor if basis_kg is not None else None
        base_wine = adjusted_wine_l if has_adjusted_forecast else (float(basis_kg) * planning_conversion if basis_kg is not None else None)
        wine_l = base_wine * factor if base_wine is not None else None
        scenarios.append({"name": name, "grapes_kg": kg, "wine_l": wine_l, "bottle_equivalents": wine_l / 0.75 if wine_l is not None else None, "crates_15kg": kg / 15 if kg is not None else None})
    production_forecasts = adjust_production_forecasts(production_forecasts, year)
    forecast_totals = []
    for forecast_year in sorted({int(row["vintage_year"]) for row in production_forecasts}):
        rows = [row for row in production_forecasts if int(row["vintage_year"]) == forecast_year]
        total_kg = sum(float(row.get("adjusted_grape_kg", row.get("grape_kg")) or 0) for row in rows)
        baseline_kg = sum(float(row.get("baseline_grape_kg", row.get("grape_kg")) or 0) for row in rows)
        forecast_totals.append({"vintage_year": forecast_year, "grape_kg": total_kg, "baseline_grape_kg": baseline_kg, "crates_15kg": round(total_kg / 15), "wine_l": round(total_kg * planning_conversion), "bottles_750ml": int(total_kg * planning_conversion / 0.75), "sources": sorted({str(row.get("source") or "unlabelled") for row in rows})})
    return {
        "year": year,
        "basis": "damage-adjusted production forecast" if has_adjusted_forecast else "current blend plan" if blend_kg is not None else "harvest plan" if planned_kg is not None else "harvested weight" if harvested_kg is not None else "missing",
        "historical_conversion_l_per_kg": conversion,
        "planning_conversion_l_per_kg": planning_conversion,
        "forecast_evidence": forecast_evidence,
        "scenarios": scenarios,
        "varieties": grapes["varieties"],
        "actual_history": vintages,
        "blend_plan": {
            "count": len(blend_plans),
            "target_grapes_kg": basis_kg,
            "estimated_volume_l": adjusted_wine_l if has_adjusted_forecast else blend_volume,
            "estimated_crates": basis_kg / blend_program["settings"]["crate_weight_kg"] if basis_kg is not None else blend_crates,
            "crate_weight_kg": blend_program["settings"]["crate_weight_kg"],
        },
        "blend_program": blend_program,
        "production_forecasts": production_forecasts,
        "production_forecast_totals": forecast_totals,
        "production_forecast_method": "Database planning records with vintage-isolated, approved damage assessments. Scouting and photo heuristics never change production kilograms.",
        "grape_allocations": [
            {
                "grape_name": blend_program["settings"]["grecanico_variety_name"],
                "total_kg": blend_working["grecanico_kg"],
                "total_crates_15kg": math.ceil(blend_working["grecanico_kg"] / blend_program["settings"]["crate_weight_kg"] - 1e-9) if blend_working["grecanico_kg"] else 0,
                "wine_destination": "Grecanico · 100% varietal",
            },
            {
                "grape_name": blend_program["settings"]["nerello_variety_name"],
                "total_kg": blend_working["nerello_kg"],
                "total_crates_15kg": math.ceil(blend_working["nerello_kg"] / blend_program["settings"]["crate_weight_kg"] - 1e-9) if blend_working["nerello_kg"] else 0,
                "wine_destination": f"Nerello blend · {blend_working['nerello_pct']:g}%",
            },
            {
                "grape_name": blend_program["settings"]["grenache_variety_name"],
                "total_kg": blend_working["grenache_available_kg"],
                "total_crates_15kg": math.ceil(blend_working["grenache_available_kg"] / blend_program["settings"]["crate_weight_kg"] - 1e-9) if blend_working["grenache_available_kg"] else 0,
                "wine_destination": f"{blend_working['required_grenache_kg']:g} kg to Nerello blend · {blend_working['remaining_grenache_kg']:g} kg to 100% Grenache",
            },
        ],
        "wine_outputs": blend_working["wines"],
        "guardrail": "Planning estimate only. Final picking and production decisions require current maturity, weather, logistics and enologist approval.",
    }
