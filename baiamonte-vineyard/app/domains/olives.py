from __future__ import annotations

from typing import Any


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
