from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from statistics import median
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, new_id


OLIVE_HARVEST_STYLE_MODELS: tuple[dict[str, Any], ...] = (
    {
        "code": "green_priority",
        "name": "Green priority",
        "offset_days": -35,
        "fruit_target": "Mostly green fruit, subject to representative maturity checks.",
        "oil_style": "Earlier, vivid and grassy with stronger bitterness, pungency and polyphenol potential.",
        "tradeoff": "Usually less oil per kilogram and a greater risk of picking before adequate oil accumulation.",
    },
    {
        "code": "green_balanced",
        "name": "Green-balanced",
        "offset_days": -21,
        "fruit_target": "Green fruit with early color change across a representative grove sample.",
        "oil_style": "Aromatic and structured, balancing green character against extraction yield.",
        "tradeoff": "Less intense than green priority, but normally more forgiving on maturity and yield.",
    },
    {
        "code": "estate_calendar",
        "name": "Estate calendar baseline",
        "offset_days": 0,
        "fruit_target": "Timing follows the median of exact prior Baiamonte harvest dates.",
        "oil_style": "Later and generally softer, with greater expected extraction yield.",
        "tradeoff": "More exposure to ripening, fruit drop, pests and autumn weather.",
    },
)


def harvest_style_models() -> list[dict[str, Any]]:
    """Owner-selectable timing strategies; offsets remain inspectable and stable."""
    return [dict(model) for model in OLIVE_HARVEST_STYLE_MODELS]


def default_harvest_preference(year: int) -> dict[str, Any]:
    return {
        "record_year": year,
        "style_code": "green_priority",
        "notes": "Prefer a greener olive harvest; confirm fruit maturity, weather and same-day mill capacity before picking.",
        "saved": False,
    }


def apply_harvest_style(forecast: dict[str, Any], style_code: str) -> dict[str, Any]:
    """Shift the auditable estate calendar baseline to match the selected oil style."""
    models = {model["code"]: model for model in OLIVE_HARVEST_STYLE_MODELS}
    model = models.get(style_code) or models["green_priority"]
    result = dict(forecast)
    result["style_code"] = model["code"]
    result["style_name"] = model["name"]
    result["style_offset_days"] = model["offset_days"]
    if result.get("status") == "recorded":
        result["basis"] = "The recorded harvest date is authoritative; the selected style no longer shifts it."
        return result
    for key in ("estimated_date", "window_start", "window_end"):
        value = result.get(key)
        if value:
            result[key] = value + timedelta(days=int(model["offset_days"]))
    if result.get("estimated_date"):
        result["model_version"] = "olive-harvest-style-v1"
        result["basis"] = (
            f"{model['name']} timing is {abs(int(model['offset_days']))} days earlier than the exact-date "
            "Baiamonte calendar baseline."
            if model["offset_days"] < 0 else
            "Uses the exact-date Baiamonte calendar baseline without a style timing adjustment."
        )
        result["guardrail"] = (
            "Planning estimate only. Do not pick from the calendar alone: confirm representative fruit maturity and oil accumulation, "
            "healthy fruit, dry picking weather and same-day mill capacity."
        )
    return result


def harvest_preference_context(year: int, calendar_forecast: dict[str, Any]) -> dict[str, Any]:
    preference = fetch_one(
        "SELECT * FROM olive_harvest_preferences WHERE estate_id=%s AND record_year=%s",
        (estate_id(), year),
    )
    if preference:
        preference["saved"] = True
    else:
        preference = default_harvest_preference(year)
    styled_forecast = apply_harvest_style(calendar_forecast, str(preference.get("style_code") or "green_priority"))
    plan = fetch_one(
        "SELECT * FROM olive_harvest_plans WHERE estate_id=%s AND record_year=%s",
        (estate_id(), year),
    )
    structural_baseline = fetch_one(
        "SELECT MAX(record_year) baseline_year FROM olive_records WHERE estate_id=%s AND activity='Structural baseline'",
        (estate_id(),),
    ) or {}
    comparable_since = int(structural_baseline.get("baseline_year") or 0)
    history = fetch_all(
        "SELECT record_year,SUM(olives_harvested_kg) olives_kg,SUM(oil_liters) oil_liters "
        "FROM olive_records WHERE estate_id=%s AND record_year<%s AND record_year>=%s GROUP BY record_year ORDER BY record_year",
        (estate_id(), year, comparable_since),
    )
    return {
        "calendar_baseline_forecast": calendar_forecast,
        "harvest_forecast": apply_owner_harvest_plan(styled_forecast, plan),
        "harvest_preference": preference,
        "harvest_style_models": harvest_style_models(),
        "harvest_plan": plan,
        "harvest_capacity_plan": build_harvest_capacity_plan(history, plan),
    }


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except (TypeError, ValueError):
        return None


def apply_owner_harvest_plan(forecast: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
    """Make a current owner planning window authoritative over an older calendar estimate."""
    if not plan or forecast.get("status") == "recorded":
        return dict(forecast)
    start = _as_date(plan.get("window_start"))
    end = _as_date(plan.get("window_end"))
    if not start or not end:
        return dict(forecast)
    center = start + timedelta(days=(end - start).days // 2)
    result = dict(forecast)
    result.update({
        "status": "owner_planning_window",
        "estimated_date": center,
        "window_start": start,
        "window_end": end,
        "confidence": "owner plan",
        "model_version": "olive-owner-plan-v1",
        "basis": f"Current owner planning window for {plan.get('crew_description') or plan.get('crew_lead') or 'the harvest team'}.",
        "guardrail": "Planning window, not a picking approval. Confirm representative maturity, dry weather, crew availability and same-day mill capacity before fixing the day.",
    })
    return result


def build_harvest_capacity_plan(history: list[dict[str, Any]], plan: dict[str, Any] | None) -> dict[str, Any]:
    """Turn reconciled estate history into transparent crop, crate and oil scenarios."""
    annual = [
        {"year": int(row["record_year"]), "olives_kg": float(row.get("olives_kg") or 0), "oil_liters": float(row.get("oil_liters") or 0)}
        for row in history if float(row.get("olives_kg") or 0) > 0
    ]
    crate_kg = float((plan or {}).get("crate_capacity_kg") or 15)
    planned_crop = float((plan or {}).get("planned_crop_kg") or 0)
    historical_crop = [row["olives_kg"] for row in annual]
    expected_kg = planned_crop or (float(median(historical_crop)) if historical_crop else 0)
    low_kg = min(historical_crop) if len(historical_crop) > 1 else 0
    high_kg = max(historical_crop) if len(historical_crop) > 1 else 0
    total_kg = sum(row["olives_kg"] for row in annual if row["oil_liters"] > 0)
    total_oil = sum(row["oil_liters"] for row in annual if row["oil_liters"] > 0)
    oil_l_per_kg = total_oil / total_kg if total_kg else 0

    def crates(weight: float) -> int | None:
        return ceil(weight / crate_kg) if weight > 0 and crate_kg > 0 else None

    def oil(weight: float) -> float | None:
        return round(weight * oil_l_per_kg, 1) if weight > 0 and oil_l_per_kg > 0 else None

    return {
        "source": "owner crop target" if planned_crop else ("latest structurally comparable estate harvest" if len(annual) == 1 else "median of structurally comparable estate harvest history"),
        "historical_years": [row["year"] for row in annual],
        "expected_olive_kg": round(expected_kg, 1) if expected_kg else None,
        "low_olive_kg": round(low_kg, 1) if low_kg else None,
        "high_olive_kg": round(high_kg, 1) if high_kg else None,
        "crate_capacity_kg": round(crate_kg, 2),
        "expected_crates": crates(expected_kg),
        "low_crates": crates(low_kg),
        "high_crates": crates(high_kg),
        "expected_oil_liters": oil(expected_kg),
        "low_oil_liters": oil(low_kg),
        "high_oil_liters": oil(high_kg),
        "historical_oil_l_per_kg": round(oil_l_per_kg, 4) if oil_l_per_kg else None,
        "crew_lead": (plan or {}).get("crew_lead"),
        "crew_description": (plan or {}).get("crew_description"),
        "crew_size": (plan or {}).get("crew_size"),
        "mill_status": (plan or {}).get("mill_status") or "not_confirmed",
        "pending_inputs": [label for value, label in (
            ((plan or {}).get("crew_size"), "team headcount"),
            ((plan or {}).get("crew_capacity_crates_per_day"), "team crates per day"),
            (None if (plan or {}).get("mill_status") == "confirmed" else "pending", "mill appointment"),
        ) if not value or value == "pending"],
        "guardrail": "Crates are rounded up to whole 15 kg grape crates. Crop and oil figures are planning scenarios, not measured 2026 yield.",
    }


def save_harvest_preference(year: int, payload: dict[str, Any], actor: str) -> None:
    if year < 2000 or year > date.today().year + 5:
        raise ValueError("Choose a valid olive harvest year")
    models = {model["code"]: model for model in harvest_style_models()}
    style_code = str(payload.get("style_code") or "").strip()
    if style_code not in models:
        raise ValueError("Choose a valid olive harvest style")
    notes = str(payload.get("notes") or "").strip() or None
    if notes and len(notes) > 2000:
        raise ValueError("Harvest preference notes must be 2,000 characters or fewer")
    preference_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO olive_harvest_preferences (id,estate_id,record_year,style_code,notes,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE style_code=VALUES(style_code),notes=VALUES(notes),updated_by=VALUES(updated_by)",
            (preference_id, estate_id(), year, style_code, notes, actor),
        )
        audit(cursor, "update", "olive_harvest_preference", str(year), {"style_code": style_code, "notes": notes}, actor)


def save_harvest_plan(year: int, payload: dict[str, Any], actor: str) -> None:
    if year < 2000 or year > date.today().year + 5:
        raise ValueError("Choose a valid olive harvest year")
    start = _as_date(payload.get("window_start"))
    end = _as_date(payload.get("window_end"))
    if not start or not end or end < start or (end - start).days > 45:
        raise ValueError("Choose a valid harvest window of 45 days or fewer")

    def optional_number(name: str, minimum: float, maximum: float) -> float | None:
        raw = payload.get(name)
        if raw in (None, ""):
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Enter a valid {name.replace('_', ' ')}") from error
        if value < minimum or value > maximum:
            raise ValueError(f"{name.replace('_', ' ')} is outside the allowed range")
        return value

    crate_capacity = optional_number("crate_capacity_kg", 1, 100) or 15
    planned_crop = optional_number("planned_crop_kg", 1, 100000)
    crew_size = optional_number("crew_size", 1, 200)
    crew_capacity = optional_number("crew_capacity_crates_per_day", 1, 10000)
    crew_lead = str(payload.get("crew_lead") or "").strip() or None
    crew_description = str(payload.get("crew_description") or "").strip() or None
    mill_status = str(payload.get("mill_status") or "not_confirmed").strip()
    if mill_status not in {"not_confirmed", "requested", "confirmed"}:
        raise ValueError("Choose a valid mill status")
    notes = str(payload.get("notes") or "").strip() or None
    if any(value and len(value) > 2000 for value in (crew_lead, crew_description, notes)):
        raise ValueError("Harvest plan text is too long")
    plan_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO olive_harvest_plans (id,estate_id,record_year,window_start,window_end,crew_lead,crew_description,crew_size,crate_capacity_kg,planned_crop_kg,crew_capacity_crates_per_day,mill_status,notes,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE window_start=VALUES(window_start),window_end=VALUES(window_end),crew_lead=VALUES(crew_lead),crew_description=VALUES(crew_description),crew_size=VALUES(crew_size),crate_capacity_kg=VALUES(crate_capacity_kg),planned_crop_kg=VALUES(planned_crop_kg),crew_capacity_crates_per_day=VALUES(crew_capacity_crates_per_day),mill_status=VALUES(mill_status),notes=VALUES(notes),updated_by=VALUES(updated_by)",
            (plan_id, estate_id(), year, start, end, crew_lead, crew_description, int(crew_size) if crew_size else None, crate_capacity, planned_crop, crew_capacity, mill_status, notes, actor),
        )
        audit(cursor, "update", "olive_harvest_plan", str(year), {"window_start": start, "window_end": end, "crew_lead": crew_lead, "crew_description": crew_description, "crew_size": crew_size, "crate_capacity_kg": crate_capacity, "planned_crop_kg": planned_crop, "crew_capacity_crates_per_day": crew_capacity, "mill_status": mill_status, "notes": notes}, actor)


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

    if str(model.get("cost_model_version") or "legacy_v1") == "workflow_v2":
        return _calculate_workflow_cost_analysis(metrics, model, has_cost_model)

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


def _calculate_workflow_cost_analysis(
    metrics: dict[str, Any], model: dict[str, Any], has_cost_model: bool
) -> dict[str, Any]:
    """Calculate current olive costs without converting missing evidence to zero."""

    def optional_number(key: str, source: dict[str, Any] = model) -> float | None:
        value = source.get(key)
        return None if value in (None, "") else float(value)

    olives_kg = optional_number("olives_kg", metrics) or 0
    oil_liters = optional_number("oil_liters", metrics) or 0
    bottle_ml = max(1, int(optional_number("bottle_volume_ml") or 500))
    package_500 = optional_number("package_500ml_count")
    package_3l = optional_number("package_3l_count")

    labor_total = optional_number("harvest_labor_eur")
    labor_hours = optional_number("harvest_labor_hours")
    labor_rate = optional_number("labor_hourly_rate_eur")
    if labor_total is None and labor_hours is not None and labor_rate is not None:
        labor_total = round(labor_hours * labor_rate, 2)

    mill_total = optional_number("mill_cost_eur")
    press_rate = optional_number("press_rate_eur_per_kg")
    if mill_total is None and press_rate is not None:
        mill_total = round(olives_kg * press_rate, 2)

    packaging_500 = None
    if package_500 is not None and optional_number("package_500ml_unit_cost_eur") is not None:
        packaging_500 = round(package_500 * float(optional_number("package_500ml_unit_cost_eur") or 0), 2)
    packaging_3l = None
    if package_3l is not None and optional_number("package_3l_unit_cost_eur") is not None:
        packaging_3l = round(package_3l * float(optional_number("package_3l_unit_cost_eur") or 0), 2)

    categories = [
        ("Harvest labor", labor_total, "harvest labor hours or invoice"),
        ("Mill / pressing", mill_total, "mill invoice or rate"),
        ("Transport", optional_number("transport_cost_eur"), "transport cost"),
        ("Filtering", optional_number("filtering_cost_eur"), "filtering cost or explicit zero"),
        ("500 ml packaging", packaging_500, "500 ml package unit cost"),
        ("3 L packaging", packaging_3l, "3 L can unit cost"),
        ("Other packaging", optional_number("packaging_other_eur"), "labels, cartons or explicit zero"),
        ("Analysis / storage", optional_number("analysis_storage_eur"), "analysis and storage cost or explicit zero"),
        ("Equipment allocation", optional_number("equipment_allocation_eur"), "season equipment allocation or explicit zero"),
        ("Other", optional_number("other_cost_eur"), "other cost or explicit zero"),
    ]
    known_lines = [{"label": label, "amount_eur": round(float(amount), 2)} for label, amount, _ in categories if amount is not None]
    missing = [need for _, amount, need in categories if amount is None]
    known_subtotal = round(sum(row["amount_eur"] for row in known_lines), 2)
    complete = has_cost_model and not missing
    actual_500ml_equivalents = oil_liters * 2 if oil_liters else 0
    planned_liters = (package_500 or 0) * 0.5 + (package_3l or 0) * 3
    packaging_costs = (packaging_500, packaging_3l, optional_number("packaging_other_eur"))
    known_packaging_costs = [value for value in packaging_costs if value is not None]
    return {
        "kg_per_liter": round(olives_kg / oil_liters, 3) if oil_liters else None,
        "oil_yield_pct": round(oil_liters / olives_kg * 100, 3) if olives_kg else None,
        "actual_bottle_equivalents": round(actual_500ml_equivalents, 2),
        "planned_bottle_liters": round(planned_liters, 2),
        "bottle_volume_gap_liters": round(oil_liters - planned_liters, 2),
        "has_cost_model": has_cost_model,
        "cost_complete": complete,
        "reconciliation_status": "reconciled" if complete else ("partial" if known_lines else "draft"),
        "missing_cost_inputs": missing,
        "known_cost_eur": known_subtotal if has_cost_model else None,
        "total_cost_eur": known_subtotal if complete else None,
        "known_cost_per_liter_eur": round(known_subtotal / oil_liters, 2) if has_cost_model and oil_liters else None,
        "cost_per_liter_eur": round(known_subtotal / oil_liters, 2) if complete and oil_liters else None,
        "cost_per_actual_bottle_eur": round(known_subtotal / actual_500ml_equivalents, 2) if complete and actual_500ml_equivalents else None,
        "labor_cost_eur": labor_total,
        "press_cost_eur": mill_total,
        "bottling_cost_eur": round(sum(known_packaging_costs), 2) if known_packaging_costs else None,
        "breakdown": known_lines,
    }


def contract_cost_context(record_year: int, metrics: dict[str, Any], model: dict[str, Any]) -> dict[str, Any] | None:
    """Return traceable Consoli contract rates for the 2026 olive reconciliation."""
    if int(record_year) != 2026:
        return None

    olives_kg = float(metrics.get("olives_kg") or 0)
    bottle_count = float(model.get("package_500ml_count") or 0)
    can_count = float(model.get("package_3l_count") or 0)
    packaging_vat = 1.22
    return {
        "supplier": "Consoli Pasquale & F.lli s.n.c.",
        "document": "Contratto di servizi Campagna olearia 2026/2027",
        "source_date": "2026-09-07",
        "source_pages": "2–3",
        "status": "contract_estimate_not_invoice",
        "listed_service_estimate_eur": round(
            olives_kg * 0.18
            + 120
            + bottle_count * 2.20 * packaging_vat
            + can_count * 3.50 * packaging_vat,
            2,
        ),
        "rates": [
            {
                "category": "Mill / pressing",
                "basis": f"{olives_kg:g} kg × €0.18/kg",
                "amount_eur": round(olives_kg * 0.18, 2),
                "tax": "VAT included",
                "reconciliation": "applied",
            },
            {
                "category": "Filtering",
                "basis": "1–599 kg tier · €120.00",
                "amount_eur": 120.0,
                "tax": "VAT and 20% immediate-filter surcharge still need confirmation",
                "reconciliation": "reference_only",
            },
            {
                "category": "500 ml packaging",
                "basis": f"{bottle_count:g} units · €2.20 net each (100–199 tier)",
                "amount_eur": round(bottle_count * 2.20 * packaging_vat, 2),
                "tax": "22% VAT included in estimate; glass and label printing unconfirmed",
                "reconciliation": "reference_only",
            },
            {
                "category": "3 L can packaging",
                "basis": f"{can_count:g} units · €3.50 net each (1–59 tier)",
                "amount_eur": round(can_count * 3.50 * packaging_vat, 2),
                "unit_cost_eur": round(3.50 * packaging_vat, 4),
                "tax": "22% VAT included in model estimate",
                "reconciliation": "applied",
            },
        ],
        "conditional": [
            "Manual sheet-label application is €0.20 net per bottle; label printing is not priced.",
            "Storage is €0.28/kg, with a €50 minimum per silo below 200 kg, only if storage is used; VAT is not stated.",
            "Direct filtering at or immediately after milling adds 20% when agreed in advance.",
            "Laboratory analysis may be required, but the contract does not state a price.",
        ],
        "pending_evidence": [
            "Transport was performed by Nunzio; his invoice is pending.",
            "Giancarlo will report the harvest crew hours; Giancarlo's own time must be added separately.",
        ],
    }
