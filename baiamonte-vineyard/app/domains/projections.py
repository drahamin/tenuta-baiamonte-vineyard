from __future__ import annotations

import math
from typing import Any

from ..production_impact import adjust_production_forecasts
from ..wine_conversion import yield_disclosure


def build_operational_projections(
    year: int,
    grapes: dict[str, Any],
    varietal_program: dict[str, Any],
    conversion: float,
    forecast_evidence: dict[str, Any],
    production_forecasts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build planning scenarios from database records without implying a learned model."""
    varietal_working = varietal_program.get("operational") or varietal_program["planning"]
    has_harvest_evidence = bool(varietal_program.get("operational") and varietal_working.get("harvest_started"))
    planning_conversion = float(varietal_program["settings"].get("expected_yield_l_per_kg") or conversion)
    configured_conversion = bool(varietal_program["settings"].get("expected_yield_is_configured"))
    conversion_source = str(varietal_program["settings"].get("expected_yield_source") or ("Current vintage configured planning yield" if configured_conversion else forecast_evidence.get("conversion_source") or "Weighted reconciled prior-vintage yield"))
    conversion_disclosure = yield_disclosure(planning_conversion, conversion_source)
    vintages = grapes["vintages"]
    scenario_range = float(forecast_evidence.get("recommended_scenario_range_pct") or 15) / 100
    planned_kg = grapes["metrics"].get("planned_kg")
    harvested_kg = grapes["metrics"].get("harvested_kg")
    has_adjusted_forecast = any(int(row.get("vintage_year") or 0) == year for row in production_forecasts)
    adjusted_basis_kg = sum(float(varietal_working.get(field) or 0) for field in ("nerello_kg", "grenache_kg", "grecanico_kg"))
    basis_kg = adjusted_basis_kg if has_adjusted_forecast or has_harvest_evidence else planned_kg if planned_kg is not None else harvested_kg
    adjusted_wine_l = sum(float(row.get("wine_l") or 0) for row in varietal_working.get("wines") or [])
    recorded_kg = float(varietal_working.get("recorded_grape_kg") or 0) if has_harvest_evidence else 0
    projected_remaining_kg = float(varietal_working.get("projected_remaining_kg") or adjusted_basis_kg) if has_harvest_evidence else float(basis_kg or 0)
    recorded_crates = int(varietal_working.get("recorded_crates") or 0) if has_harvest_evidence else 0
    crate_weight_kg = float(varietal_program["settings"]["crate_weight_kg"])
    scenarios = []
    for name, factor in (("Downside", 1 - scenario_range), ("Working", 1.0), ("Upside", 1 + scenario_range)):
        kg = recorded_kg + projected_remaining_kg * factor if basis_kg is not None else None
        if not has_harvest_evidence:
            kg = float(basis_kg) * factor if basis_kg is not None else None
        kg = round(kg, 3) if kg is not None else None
        wine_l = round(kg * planning_conversion, 3) if kg is not None else None
        projected_crates = math.ceil(projected_remaining_kg * factor / crate_weight_kg - 1e-9) if kg is not None and projected_remaining_kg else 0 if kg is not None else None
        crate_count = recorded_crates + projected_crates if projected_crates is not None else None
        scenarios.append({
            "name": name, "grapes_kg": kg, "wine_l": wine_l,
            "bottle_equivalents": wine_l / 0.75 if wine_l is not None else None,
            "crate_count": crate_count, "crates_15kg": crate_count,
            "recorded_grapes_kg": recorded_kg, "recorded_crates": recorded_crates,
            "projected_grapes_kg": round(projected_remaining_kg * factor, 3) if kg is not None else None,
            "projected_crates": projected_crates, "crate_weight_kg": crate_weight_kg,
        })
    production_forecasts = adjust_production_forecasts(production_forecasts, year)
    if has_harvest_evidence:
        operational_by_name = {
            str(row.get("finished_wine") or "").casefold(): row
            for row in varietal_working.get("wines") or []
        }
        for row in production_forecasts:
            if int(row.get("vintage_year") or 0) != year:
                continue
            wine = operational_by_name.get(str(row.get("variety_name") or "").casefold())
            if wine:
                row["adjusted_grape_kg"] = float(wine.get("grape_kg") or 0)
                row["recorded_grape_kg"] = float(wine.get("recorded_grape_kg") or 0)
                row["projected_remaining_kg"] = float(wine.get("projected_remaining_kg") or 0)
    forecast_totals = []
    for forecast_year in sorted({int(row["vintage_year"]) for row in production_forecasts}):
        rows = [row for row in production_forecasts if int(row["vintage_year"]) == forecast_year]
        total_kg = round(sum(float(row.get("adjusted_grape_kg", row.get("grape_kg")) or 0) for row in rows), 3)
        baseline_kg = sum(float(row.get("baseline_grape_kg", row.get("grape_kg")) or 0) for row in rows)
        if has_harvest_evidence and forecast_year == year:
            crate_count = recorded_crates + int(varietal_working.get("projected_crates") or 0)
        else:
            crate_count = round(total_kg / crate_weight_kg)
        forecast_totals.append({"vintage_year": forecast_year, "grape_kg": total_kg, "baseline_grape_kg": baseline_kg, "crate_count": crate_count, "crates_15kg": crate_count, "crate_weight_kg": crate_weight_kg, "wine_l": round(total_kg * planning_conversion), "bottles_750ml": int(total_kg * planning_conversion / 0.75), "sources": sorted({str(row.get("source") or "unlabelled") for row in rows})})
    return {
        "year": year,
        "basis": "recorded harvest plus remaining damage-adjusted forecast" if has_harvest_evidence and has_adjusted_forecast else "recorded harvest plus remaining forecast" if has_harvest_evidence else "damage-adjusted production forecast" if has_adjusted_forecast else "harvest plan" if planned_kg is not None else "harvested weight" if harvested_kg is not None else "missing",
        "historical_conversion_l_per_kg": conversion,
        "planning_conversion_l_per_kg": planning_conversion,
        "wine_yield_conversion": conversion_disclosure,
        "forecast_evidence": forecast_evidence,
        "scenarios": scenarios,
        "varieties": grapes["varieties"],
        "actual_history": vintages,
        "production_plan": {
            "policy": "separate_varietals",
            "target_grapes_kg": basis_kg,
            "estimated_volume_l": adjusted_wine_l if has_adjusted_forecast or has_harvest_evidence else (float(basis_kg) * planning_conversion if basis_kg is not None else None),
            "estimated_crates": recorded_crates + int(varietal_working.get("projected_crates") or 0) if has_harvest_evidence else basis_kg / crate_weight_kg if basis_kg is not None else None,
            "crate_weight_kg": crate_weight_kg,
            "recorded_grapes_kg": recorded_kg,
            "recorded_crates": recorded_crates,
            "projected_remaining_kg": projected_remaining_kg,
            "projected_crates": int(varietal_working.get("projected_crates") or 0) if has_harvest_evidence else None,
            "crate_basis": "Actual crate counts for harvested fruit; configured crate weight only for unpicked fruit" if has_harvest_evidence else "Configured planning crate weight",
        },
        "varietal_program": varietal_program,
        "production_forecasts": production_forecasts,
        "production_forecast_totals": forecast_totals,
        "production_forecast_method": "Database planning records with vintage-isolated damage assessments. Approved Agronomist estimates are authoritative; structured AI event estimates are used provisionally and visibly require confirmation.",
        "grape_allocations": [{
            "grape_name": row["finished_wine"], "total_kg": row["grape_kg"],
            "total_crates": row.get("crates"), "total_crates_15kg": row.get("crates"),
            "recorded_kg": row.get("recorded_grape_kg", 0), "recorded_crates": row.get("recorded_crates", 0),
            "projected_kg": row.get("projected_remaining_kg", row["grape_kg"]), "projected_crates": row.get("projected_crates", row.get("crates")),
            "crate_weight_kg": crate_weight_kg,
            "wine_destination": f"{row['finished_wine']} · 100% varietal",
        } for row in varietal_working.get("wines") or []],
        "wine_outputs": varietal_working["wines"],
        "guardrail": "Planning estimate only. Final picking and production decisions require current maturity, weather, logistics and enologist approval.",
    }
