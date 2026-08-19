from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from ..db import fetch_all
from ..service import estate_id


def prediction_context(year: int) -> dict[str, Any]:
    estate = estate_id()
    training = fetch_all(
        "SELECT record_year,record_date,activity,details,status,olives_harvested_kg,notes FROM olive_records WHERE estate_id=%s AND record_date IS NOT NULL "
        "UNION ALL SELECT fact_year,fact_date,subject,details,evidence_status,quantity_value,conflict_note FROM historical_note_facts "
        "WHERE estate_id=%s AND domain='olives' AND date_precision='day' AND fact_date IS NOT NULL ORDER BY record_date",
        (estate, estate),
    )
    treatments = fetch_all(
        "SELECT * FROM v_treatment_history WHERE estate_id=%s AND crop_scope='olives' AND YEAR(application_date)=%s ORDER BY application_date DESC",
        (estate, year),
    )
    return {"harvest_forecast": estimate_harvest_date(training, year), "treatments": treatments}


def estimate_harvest_date(records: list[dict[str, Any]], target_year: int, as_of: date | None = None) -> dict[str, Any]:
    """Estimate olive harvest timing from exact estate harvest records only.

    This is deliberately a calendar baseline, not a claim of fruit readiness.
    Field maturity, crop load and weather evidence can refine it later.
    """
    today = as_of or date.today()
    exact: list[tuple[int, date]] = []
    seen_exact: set[tuple[int, int, int]] = set()
    current_actual: date | None = None
    for row in records:
        raw = row.get("record_date")
        try:
            observed = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            continue
        text = " ".join(str(row.get(key) or "") for key in ("activity", "details", "status", "notes")).casefold()
        if "harvest" not in text and "raccolt" not in text:
            continue
        if float(row.get("olives_harvested_kg") or 0) <= 0:
            continue
        if observed.year == target_year:
            current_actual = min(current_actual, observed) if current_actual else observed
        elif observed.year < target_year and (observed.year, observed.month, observed.day) not in seen_exact:
            anchor = date(2000, observed.month, observed.day)
            exact.append((observed.year, anchor))
            seen_exact.add((observed.year, observed.month, observed.day))

    if current_actual:
        return {
            "status": "recorded", "estimated_date": current_actual,
            "window_start": current_actual, "window_end": current_actual,
            "confidence": "recorded actual", "model_version": "olive-harvest-calendar-v1",
            "training_samples": len(exact), "training_years": sorted({year for year, _ in exact}),
            "basis": "The first exact olive harvest record for this year.",
            "guardrail": "Recorded harvest date; no prediction is being substituted for the actual record.",
        }
    if not exact:
        return {
            "status": "insufficient_data", "estimated_date": None, "window_start": None, "window_end": None,
            "confidence": "insufficient data", "model_version": "olive-harvest-calendar-v1",
            "training_samples": 0, "training_years": [],
            "basis": "No exact prior olive harvest date is available.",
            "guardrail": "Add an exact harvest date; the system will not invent one from a year-only note.",
        }

    ordinals = [anchor.toordinal() for _, anchor in exact]
    center = int(round(median(ordinals)))
    deviations = [abs(value - center) for value in ordinals]
    spread = median(deviations) * 1.4826 if len(deviations) > 1 else 21
    window_days = max(7, min(28, int(round(spread)))) if len(exact) >= 3 else (14 if len(exact) == 2 else 21)
    anchor = date.fromordinal(center)
    estimate = date(target_year, anchor.month, anchor.day)
    confidence = "medium" if len(exact) >= 3 and window_days <= 14 else "low"
    return {
        "status": "estimated", "estimated_date": estimate,
        "window_start": estimate - timedelta(days=window_days),
        "window_end": estimate + timedelta(days=window_days),
        "confidence": confidence, "model_version": "olive-harvest-calendar-v1",
        "training_samples": len(exact), "training_years": sorted({year for year, _ in exact}),
        "basis": f"Median calendar timing from {len(exact)} exact estate olive harvest record{'s' if len(exact) != 1 else ''}.",
        "guardrail": "Planning estimate only. Confirm fruit maturity, oil accumulation, crop condition, mill availability and weather before harvesting.",
    }


def calculate_cost_analysis(metrics: dict[str, Any], model: dict[str, Any] | None) -> dict[str, Any]:
    has_cost_model = model is not None
    model = model or {"bottle_volume_ml": 500}

    def number(key: str, source: dict[str, Any] = model) -> float:
        return float(source.get(key) or 0)

    olives_kg = number("olives_kg", metrics)
    oil_liters = number("oil_liters", metrics)
    bottle_ml = max(1, int(number("bottle_volume_ml")))
    bottles = number("bottle_count")
    press_cost = round(olives_kg * number("press_rate_eur_per_kg"), 2)
    bottling_cost = round(bottles * number("bottle_unit_cost_eur"), 2)
    supplier_vat = round(number("supplier_net_eur") * number("vat_rate_pct") / 100, 2)
    supplier_gross = round(number("supplier_net_eur") + supplier_vat, 2)
    supplier_includes_variable = bool(model.get("supplier_includes_press_bottling"))
    supplier_remainder = round(number("supplier_net_eur") - press_cost - bottling_cost, 2) if supplier_includes_variable else number("supplier_net_eur")
    harvest_additional = 0 if bool(model.get("harvest_included_in_annual")) else number("harvest_labor_eur")
    labor_cost = round(number("annual_labor_eur") + harvest_additional, 2)
    total_cost = round(supplier_gross + labor_cost if supplier_includes_variable else press_cost + bottling_cost + supplier_gross + labor_cost, 2)
    actual_bottle_equivalents = oil_liters * 1000 / bottle_ml if oil_liters else 0
    return {
        "kg_per_liter": round(olives_kg / oil_liters, 3) if oil_liters else None,
        "oil_yield_pct": round(oil_liters / olives_kg * 100, 3) if olives_kg else None,
        "actual_bottle_equivalents": round(actual_bottle_equivalents, 2),
        "planned_bottle_liters": round(bottles * bottle_ml / 1000, 2),
        "bottle_volume_gap_liters": round(oil_liters - bottles * bottle_ml / 1000, 2),
        "estimated_harvest_trees": round(number("harvest_labor_eur") / number("harvest_rate_eur_per_tree"), 2) if number("harvest_rate_eur_per_tree") else None,
        "has_cost_model": has_cost_model,
        "press_cost_eur": press_cost if has_cost_model else None,
        "bottling_cost_eur": bottling_cost if has_cost_model else None,
        "supplier_vat_eur": supplier_vat if has_cost_model else None,
        "supplier_gross_eur": supplier_gross if has_cost_model else None,
        "supplier_remainder_eur": supplier_remainder if has_cost_model else None,
        "supplier_includes_press_bottling": supplier_includes_variable,
        "labor_cost_eur": labor_cost if has_cost_model else None,
        "harvest_cost_added_eur": round(harvest_additional, 2) if has_cost_model else None,
        "total_cost_eur": total_cost if has_cost_model else None,
        "cost_per_liter_eur": round(total_cost / oil_liters, 2) if has_cost_model and oil_liters else None,
        "cost_per_actual_bottle_eur": round(total_cost / actual_bottle_equivalents, 2) if has_cost_model and actual_bottle_equivalents else None,
        "cost_per_planned_bottle_eur": round(total_cost / bottles, 2) if has_cost_model and bottles else None,
        "breakdown": ([
            {"label": "Pressing", "amount_eur": press_cost},
            {"label": "Bottling", "amount_eur": bottling_cost},
            {"label": "Other supplier net", "amount_eur": supplier_remainder},
            {"label": "VAT", "amount_eur": supplier_vat},
            {"label": "Labor", "amount_eur": labor_cost},
        ] if supplier_includes_variable else [
            {"label": "Pressing", "amount_eur": press_cost},
            {"label": "Bottling", "amount_eur": bottling_cost},
            {"label": "Separate supplier + VAT", "amount_eur": supplier_gross},
            {"label": "Labor", "amount_eur": labor_cost},
        ]) if has_cost_model else [],
    }
