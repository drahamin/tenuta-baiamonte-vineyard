from __future__ import annotations

from datetime import date, datetime
from math import ceil
from typing import Any

from ..db import fetch_all
from ..inventory import treatment_inventory_reconciliation
from ..service import estate_id


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def select_application_window(forecast: list[dict[str, Any]], window_start: Any, window_end: Any, *, sulfur: bool = False) -> dict[str, Any]:
    """Choose a conservative daily window; hourly field conditions still require confirmation."""
    start, end = _day(window_start), _day(window_end)
    evaluated: list[dict[str, Any]] = []
    for row in forecast:
        forecast_day = _day(row.get("datetime") or row.get("date") or row.get("time"))
        if not forecast_day or (start and forecast_day < start) or (end and forecast_day > end):
            continue
        high = _number(row.get("temperature") or row.get("temperature_high") or row.get("temp_max"))
        rain = _number(row.get("precipitation") or row.get("precipitation_amount") or row.get("rain")) or 0.0
        wind = _number(row.get("wind_speed") or row.get("wind_speed_kph") or row.get("wind"))
        reasons: list[str] = []
        if rain >= 1:
            reasons.append(f"{rain:g} mm forecast rain")
        if wind is None:
            reasons.append("wind forecast missing")
        elif wind > 15:
            reasons.append(f"wind {wind:g} km/h")
        if high is None:
            reasons.append("maximum temperature missing")
        elif sulfur and high > 28:
            reasons.append(f"maximum {high:g}°C exceeds the conservative sulfur screen")
        elif high > 32:
            reasons.append(f"maximum {high:g}°C exceeds the conservative spray screen")
        evaluated.append({"date": forecast_day, "suitable": not reasons, "reasons": reasons, "high_c": high, "rain_mm": rain, "wind_kph": wind})
    selected = next((row for row in evaluated if row["suitable"]), None)
    if selected:
        return {"status": "provisional_window", "recommended_date": selected["date"], "message": "Provisional day from the daily forecast. Confirm hourly wind, rain, temperature, leaf condition and label restrictions before mixing.", "evaluated_days": evaluated}
    return {"status": "no_suitable_window", "recommended_date": None, "message": "No defensible application day is available in the current forecast window. Recalculate when the forecast refreshes; do not force the stale planned date.", "evaluated_days": evaluated}


def calculate_area_mix(*, area_ha: float, water_l: float, rate_kg_ha: float) -> dict[str, float]:
    total_kg = area_ha * rate_kg_ha
    return {"area_ha": round(area_ha, 3), "water_l": round(water_l, 1), "rate_kg_ha": round(rate_kg_ha, 3), "total_kg": round(total_kg, 3), "per_100_l_g": round(total_kg * 100000 / water_l, 1)}


def calculate_stock_shortage(required: float, on_hand: float) -> float:
    return round(max(0.0, required - on_hand), 3)


def calculate_sprayer_batches(total_water_l: float, tank_capacity_l: float | None) -> list[dict[str, float]]:
    """Split a water-based application into nominal sprayer fills without guessing usable capacity."""
    if total_water_l <= 0 or not tank_capacity_l or tank_capacity_l <= 0:
        return []
    count = int(ceil(total_water_l / tank_capacity_l))
    remaining = total_water_l
    batches: list[dict[str, float]] = []
    for index in range(count):
        water_l = min(tank_capacity_l, remaining)
        batches.append({"batch": float(index + 1), "water_l": round(water_l, 1), "share": round(water_l / total_water_l, 6)})
        remaining -= water_l
    return batches


def _practical_batch_quantity(quantity: float, unit: str) -> tuple[float, str]:
    """Use readable batch units without changing mass into volume or vice versa."""
    if unit == "kg" and abs(quantity) < 1:
        return round(quantity * 1000, 1), "g"
    if unit == "L" and abs(quantity) < 1:
        return round(quantity * 1000, 1), "ml"
    return round(quantity, 3), unit


def calculate_batch_recipe(
    batches: list[dict[str, float]], components: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Allocate every calculated ingredient across sprayer fills, preserving totals exactly."""
    if not batches:
        return []
    recipe = [{**batch, "components": []} for batch in batches]
    for component in components:
        total = _number(component.get("total"))
        unit = str(component.get("total_unit") or "")
        if total is None or not unit:
            continue
        allocated = 0.0
        for index, batch in enumerate(recipe):
            raw = total - allocated if index == len(recipe) - 1 else total * float(batch["share"])
            raw = round(raw, 6)
            allocated = round(allocated + raw, 6)
            display_quantity, display_unit = _practical_batch_quantity(raw, unit)
            batch["components"].append(
                {
                    "product_name": component.get("product_name"),
                    "quantity": raw,
                    "unit": unit,
                    "display_quantity": display_quantity,
                    "display_unit": display_unit,
                }
            )
    return recipe


def calculate_water_rate_quantity(*, water_l: float, rate_min: float | None, rate_max: float | None, rate_unit: str | None) -> dict[str, Any] | None:
    """Calculate a label water-rate without inventing mass/volume conversions."""
    if water_l <= 0 or rate_min is None or not rate_unit:
        return None
    maximum = rate_max if rate_max is not None else rate_min
    if rate_unit == "g/L":
        low_g, high_g = water_l * rate_min, water_l * maximum
        if low_g >= 1000 and high_g >= 1000:
            return {"water_l": round(water_l, 1), "minimum": round(low_g / 1000, 3), "maximum": round(high_g / 1000, 3), "unit": "kg", "rate_min": rate_min, "rate_max": maximum, "rate_unit": rate_unit}
        return {"water_l": round(water_l, 1), "minimum": round(low_g, 1), "maximum": round(high_g, 1), "unit": "g", "rate_min": rate_min, "rate_max": maximum, "rate_unit": rate_unit}
    if rate_unit == "g/100 L":
        factor = water_l / 100
        low_g, high_g = rate_min * factor, maximum * factor
        if low_g >= 1000 and high_g >= 1000:
            return {"water_l": round(water_l, 1), "minimum": round(low_g / 1000, 3), "maximum": round(high_g / 1000, 3), "unit": "kg", "rate_min": rate_min, "rate_max": maximum, "rate_unit": rate_unit}
        return {"water_l": round(water_l, 1), "minimum": round(low_g, 1), "maximum": round(high_g, 1), "unit": "g", "rate_min": rate_min, "rate_max": maximum, "rate_unit": rate_unit}
    if rate_unit == "ml/100 L":
        factor = water_l / 100
        return {"water_l": round(water_l, 1), "minimum": round(rate_min * factor / 1000, 3), "maximum": round(maximum * factor / 1000, 3), "unit": "L", "rate_min": rate_min, "rate_max": maximum, "rate_unit": rate_unit}
    return None


def calculate_area_rate_quantity(*, area_ha: float, rate_min: float | None, rate_max: float | None, rate_unit: str | None) -> dict[str, Any] | None:
    """Calculate a documented per-hectare range without converting between mass and volume."""
    if area_ha <= 0 or rate_min is None or rate_unit not in {"kg/ha", "L/ha"}:
        return None
    maximum = rate_max if rate_max is not None else rate_min
    return {
        "area_ha": round(area_ha, 3),
        "minimum": round(area_ha * rate_min, 3),
        "maximum": round(area_ha * maximum, 3),
        "unit": "kg" if rate_unit == "kg/ha" else "L",
        "rate_min": rate_min,
        "rate_max": maximum,
        "rate_unit": rate_unit,
    }


def _profile_ready(row: dict[str, Any]) -> bool:
    return (
        row.get("final_application_medium") == "water_spray"
        and row.get("verification_status") == "verified"
        and row.get("estate_authorization_status") == "confirmed"
        and bool(row.get("eligible_for_projection"))
    )


def _profile_block_reason(row: dict[str, Any]) -> str:
    if not row.get("profile_id"):
        return "No formulation profile is recorded."
    if row.get("final_application_medium") != "water_spray":
        return "The product is not verified for the estate's water-spray application method."
    if row.get("verification_status") != "verified":
        return f"Formulation verification status: {row.get('verification_status') or 'not recorded'}."
    if row.get("estate_authorization_status") != "confirmed":
        return "Estate authorization has not been confirmed."
    if not row.get("eligible_for_projection"):
        return "The product is retained as reference evidence but is not eligible for a projected mixture."
    return "Current crop-and-target authorization is not verified."


def _review_possible_product(row: dict[str, Any], stock_by_product: dict[str, dict[str, Any]], *, planning_water_l: float = 400.0, planning_area_ha: float = 0.0) -> dict[str, Any]:
    name = str(row.get("product_name") or "")
    stock = stock_by_product.get(name) or {}
    default = str(row.get("default_decision") or "blocked")
    compatibility = str(row.get("compatibility_status") or "not_verified")
    quantity = calculate_water_rate_quantity(
        water_l=planning_water_l,
        rate_min=_number(row.get("water_rate_min")),
        rate_max=_number(row.get("water_rate_max")),
        rate_unit=row.get("water_rate_unit"),
    )
    if quantity is None:
        quantity = calculate_area_rate_quantity(
            area_ha=planning_area_ha,
            rate_min=_number(row.get("minimum_rate_per_ha")),
            rate_max=_number(row.get("maximum_rate_per_ha")),
            rate_unit=row.get("minimum_rate_per_ha_unit"),
        )
    if not _profile_ready(row):
        decision = "blocked_pending_container_check"
        reason = row.get("exclusion_reason") or _profile_block_reason(row)
    elif default == "not_selected":
        decision = "not_selected"
        reason = row.get("exclusion_reason") or row.get("selection_conditions") or "The current condition does not justify this product."
    elif compatibility != "verified_compatible":
        decision = "separate_or_agronomist_compatibility_review"
        reason = row.get("compatibility_conditions") or "Compatibility with the exact proposed mixture is not verified; keep this product separate unless the agronomist approves the current label directions and any required jar test."
    else:
        decision = "eligible_for_agronomist_review"
        reason = row.get("selection_conditions") or "Current label, compatibility, sequence and agronomist approval must be confirmed."
    return {
        "product_name": name,
        "mixture_role": row.get("mixture_role"),
        "concentrate_form": row.get("concentrate_form"),
        "final_application_medium": row.get("final_application_medium"),
        "verification_status": row.get("verification_status"),
        "purchase_state": "stock_unreconciled" if stock.get("stock_reconciled") is False else "in_stock" if (_number(stock.get("stock_on_hand")) or 0) > 0 else "not_in_stock",
        "stock_on_hand": max(0.0, _number(stock.get("stock_on_hand")) or 0),
        "stock_unit": stock.get("unit") or row.get("measure_unit"),
        "decision": decision,
        "reason": reason,
        "selection_conditions": row.get("selection_conditions"),
        "compatibility_status": compatibility,
        "compatibility_conditions": row.get("compatibility_conditions"),
        "projected_quantity": quantity,
    }


def _risk_rate(candidate: dict[str, Any], prediction: dict[str, Any]) -> float | None:
    minimum, maximum = _number(candidate.get("min_dose")), _number(candidate.get("max_dose"))
    if minimum is None or candidate.get("dose_unit") not in {"kg/ha", "L/ha"}:
        return None
    score = _number(prediction.get("current_risk_score")) or 0
    if score >= 75:
        return min(maximum or minimum, max(minimum, 8.0))
    if score >= 50:
        return min(maximum or minimum, max(minimum, 4.0))
    return minimum


def product_guidance(crop_scope: str, prediction: dict[str, Any], *, forecast: list[dict[str, Any]] | None = None, planning_water_l: float = 400.0, equipment_selector: str | None = None) -> dict[str, Any]:
    """Build a fully calculated proposal while retaining legal and human approval gates."""
    if forecast is None:
        from ..display_data import weather_context_payload
        forecast = weather_context_payload().get("forecast") or []
    target_code = str(prediction.get("target_code") or "").strip()
    planning_water_l = _number(planning_water_l) or 400.0
    planning_water_l = min(5000.0, max(1.0, planning_water_l))
    all_purchases = fetch_all("SELECT pe.*,p.name product_name FROM treatment_purchase_evidence pe LEFT JOIN products p ON p.id=pe.product_id WHERE pe.estate_id=%s AND YEAR(pe.invoice_date)=YEAR(CURDATE()) ORDER BY pe.invoice_date,pe.invoice_number,pe.line_number", (estate_id(),))
    stock_review_list = [row for row in all_purchases if "[STOCK REVIEW]" in str(row.get("notes") or "") or "Unclassified Agriplanet line" in str(row.get("notes") or "")]
    purchases = [row for row in all_purchases if row not in stock_review_list]
    purchase_by_product: dict[str, list[dict[str, Any]]] = {}
    for row in purchases:
        if row.get("product_name"):
            purchase_by_product.setdefault(str(row["product_name"]), []).append(row)
    stock_rows = fetch_all(
        "SELECT p.name product_name,p.unit,SUM(i.quantity_delta) ledger_balance,"
        "GREATEST(0,SUM(i.quantity_delta)) stock_on_hand "
        "FROM products p JOIN inventory_movements i ON i.product_id=p.id "
        "WHERE p.estate_id=%s GROUP BY p.id,p.name,p.unit",
        (estate_id(),),
    )
    stock_by_product = {str(row["product_name"]): row for row in stock_rows}
    inventory_reconciliation = treatment_inventory_reconciliation(date.today().year)
    unresolved_products = {str(row.get("product_name") or "") for row in inventory_reconciliation["issues"]}
    for product_name, stock in stock_by_product.items():
        stock["stock_reconciled"] = product_name not in unresolved_products and (_number(stock.get("ledger_balance")) or 0) >= 0
    reference_catalog = fetch_all("SELECT p.name product_name,p.product_type,p.active_ingredient,p.registration_number,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.density_kg_l,r.label_verified_on,r.label_url,r.eligible_for_projection,(SELECT COUNT(*) FROM treatment_product_evidence ev WHERE ev.product_id=p.id) evidence_count FROM treatment_product_profiles r JOIN products p ON p.id=r.product_id WHERE r.estate_id=%s AND r.active=1 AND p.active=1 ORDER BY p.name", (estate_id(),))
    purchase_summary = [{"product_name": name, "quantity": round(sum(_number(row.get("quantity_total")) or 0 for row in lines), 3), "unit": lines[0].get("quantity_unit"), "stock_on_hand": round(max(0.0, _number((stock_by_product.get(name) or {}).get("stock_on_hand")) or 0), 3), "stock_unit": (stock_by_product.get(name) or {}).get("unit") or lines[0].get("quantity_unit"), "stock_reconciled": name not in unresolved_products and (_number((stock_by_product.get(name) or {}).get("ledger_balance")) or 0) >= 0 and not any("[STOCK REVIEW]" in str(row.get("notes") or "") for row in lines), "invoice_numbers": list(dict.fromkeys(str(row.get("invoice_number")) for row in lines)), "treatment_relevance": lines[0].get("treatment_relevance")} for name, lines in purchase_by_product.items()]
    non_treatment = [row for row in purchases if row.get("treatment_relevance") == "not_treatment"]
    if not target_code:
        return {"status": "waiting_for_target", "target_code": None, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "message": "No current target is supported. Purchased products are inventory evidence, not a reason to spray."}

    uses = fetch_all("SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.density_kg_l,r.mixing_position,r.mixing_instructions,r.compatibility_notes,r.water_quality_notes,r.eligible_for_projection FROM product_authorized_uses u JOIN products p ON p.id=u.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 ORDER BY (u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE())) DESC,u.label_verified_on DESC,p.name", (estate_id(), crop_scope, target_code))
    candidates = [row for row in uses if row.get("authorization_status") == "authorized" and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= date.today()) and _profile_ready(row)]
    blocked_products = [{"product_name": row.get("product_name"), "reason": _profile_block_reason(row) if row.get("authorization_status") == "authorized" else f"Authorization status: {row.get('authorization_status')}; expiry {row.get('authorization_expires_on') or 'not recorded'}."} for row in uses if row not in candidates]
    if not candidates:
        return {"status": "no_verified_candidate", "target_code": target_code, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "message": "No currently authorized crop-and-target product has a complete water-spray formulation reference. A current Italian label and formulation profile must be checked before calculation."}

    area_rows = fetch_all("SELECT code,name,area_ha FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),))
    known_area = round(sum(_number(row.get("area_ha")) or 0 for row in area_rows), 3)
    missing_area_blocks = [row.get("code") for row in area_rows if _number(row.get("area_ha")) is None]
    harvest_rows = fetch_all("SELECT g.final_forecast_date,g.predicted_date FROM gdd_forecasts g JOIN seasons s ON s.id=g.season_id WHERE g.estate_id=%s AND s.vintage_year=YEAR(CURDATE()) ORDER BY COALESCE(g.final_forecast_date,g.predicted_date)", (estate_id(),))
    harvest_dates = [_day(row.get("final_forecast_date") or row.get("predicted_date")) for row in harvest_rows]
    earliest_harvest = min((value for value in harvest_dates if value), default=None)
    candidate = candidates[0]
    rate = _risk_rate(candidate, prediction)
    equipment_rows = fetch_all("SELECT q.id equipment_id,q.name,q.make_model,s.tank_capacity_l,s.usable_capacity_l,s.calibrated_on,s.calibration_status,s.nozzle_setup,s.flow_l_min,s.operating_pressure_bar,s.travel_speed_kph,s.carrier_rate_l_ha,s.source_reference FROM spray_equipment_profiles s JOIN equipment q ON q.id=s.equipment_id WHERE s.estate_id=%s AND s.active=1 AND q.active=1 AND q.status<>'retired' ORDER BY (s.calibration_status='verified') DESC,q.name", (estate_id(),))
    requested_equipment = str(equipment_selector or "").strip()
    sprayer = next((row for row in equipment_rows if requested_equipment and requested_equipment in {str(row.get("equipment_id") or ""), str(row.get("name") or ""), str(row.get("make_model") or "")}), None)
    if not sprayer and not requested_equipment:
        sprayer = equipment_rows[0] if equipment_rows else None
    sprayer_capacity = _number((sprayer or {}).get("usable_capacity_l")) or _number((sprayer or {}).get("tank_capacity_l"))
    batches = calculate_sprayer_batches(planning_water_l, sprayer_capacity)
    dose_unit = str(candidate.get("dose_unit") or "")
    if known_area and rate and dose_unit == "kg/ha":
        calculation = {**calculate_area_mix(area_ha=known_area, water_l=planning_water_l, rate_kg_ha=rate), "total": round(known_area * rate, 3), "total_unit": "kg"}
    elif known_area and rate and dose_unit == "L/ha":
        total_l = round(known_area * rate, 3)
        calculation = {"area_ha": known_area, "water_l": planning_water_l, "rate_l_ha": rate, "total": total_l, "total_unit": "L", "per_100_l_ml": round(total_l * 100000 / planning_water_l, 1)}
    else:
        calculation = None
    candidate_stock = stock_by_product.get(str(candidate.get("product_name"))) or {}
    ledger_balance = _number(candidate_stock.get("ledger_balance")) or 0
    stock_balance = max(0.0, _number(candidate_stock.get("stock_on_hand")) or 0)
    required_quantity = _number(calculation.get("total")) if calculation else None
    candidate_name = str(candidate.get("product_name") or "")
    purchase_state = "stock_unreconciled" if candidate_name in unresolved_products else "stock_deficit" if ledger_balance < 0 else "in_stock" if stock_balance > 0 and (required_quantity is None or stock_balance >= required_quantity) else "insufficient_stock" if stock_balance > 0 else "suggested_purchase"
    spray_window = select_application_window(forecast, prediction.get("window_start"), prediction.get("window_end"), sulfur=str(candidate.get("active_ingredient") or "").casefold().startswith("sulfur"))
    phi_days = int(candidate.get("phi_days") or 0)
    recommended_day = _day(spray_window.get("recommended_date"))
    phi_ok = not (recommended_day and earliest_harvest and (earliest_harvest - recommended_day).days < phi_days)
    hard_blocks = ["Record a current block scouting observation and confirm the target before approval.", "Select the exact treated blocks; the calculated estate area is only a planning basis.", f"Confirm the actual tank water volume; {planning_water_l:g} L is an adjustable planning value, not an application record.", "Agronomist must approve the product, rate, compatibility, sequence, PHI, REI, weather and PPE.", "Do not combine sulfur, copper, or any support product with another concentrate unless the database records verified compatibility for that exact mixture. Otherwise keep applications separate; where the current label permits it, complete an agronomist-approved jar test first."]
    if missing_area_blocks:
        hard_blocks.append("Add area for blocks: " + ", ".join(str(value) for value in missing_area_blocks) + ".")
    if spray_window["status"] != "provisional_window":
        hard_blocks.append(spray_window["message"])
    if not phi_ok:
        hard_blocks.append(f"The {phi_days}-day PHI would overlap the earliest current harvest forecast ({earliest_harvest}).")
    if purchase_state == "suggested_purchase":
        hard_blocks.append(f"Purchase/on-hand quantity for {candidate.get('product_name')} is not verified; acquire or count stock before approval.")
    if purchase_state == "insufficient_stock":
        hard_blocks.append(f"Only {stock_balance:g} {candidate.get('unit') or ''} is recorded in stock; the proposal requires {required_quantity:g} {calculation.get('total_unit') if calculation else candidate.get('unit') or ''}.")
    if purchase_state == "stock_deficit":
        hard_blocks.append(f"Recorded use exceeds received stock for {candidate.get('product_name')} by {abs(ledger_balance):g} {candidate.get('unit') or ''}; displayed on-hand stock is held at zero until a missing receipt or physical count is reconciled.")
    if purchase_state == "stock_unreconciled":
        hard_blocks.append(f"Completed use of {candidate.get('product_name')} has an unknown total or unresolved unit; its displayed balance and purchase quantity are provisional.")
    if not inventory_reconciliation["complete"]:
        hard_blocks.append(f"{inventory_reconciliation['unresolved_items']} completed-treatment product quantities still need inventory reconciliation; purchase advice is provisional until those exact totals are confirmed.")
    if not sprayer:
        hard_blocks.append("Select the water-spray equipment and record its tank capacity and calibration before approval." if not requested_equipment else f"Configured sprayer '{requested_equipment}' was not found among active spray-equipment profiles.")
    elif sprayer.get("calibration_status") != "verified":
        hard_blocks.append(f"{sprayer.get('name') or 'The sprayer'} has a documented nominal {sprayer_capacity:g} L tank but its usable fill, pump/nozzle setup and field calibration are not verified.")
    required_unit = calculation.get("total_unit") if calculation else candidate.get("unit")
    needed_list = ([{"product_name": candidate.get("product_name"), "required": required_quantity, "on_hand": round(stock_balance, 3), "needed": None, "unit": required_unit, "target": candidate.get("target_name"), "reason": "Exact purchase quantity is withheld until completed use and any missing opening receipt or physical stock count are reconciled.", "purchase_state": purchase_state}] if purchase_state in {"stock_unreconciled", "stock_deficit"} else [] if required_quantity is None or stock_balance >= required_quantity else [{"product_name": candidate.get("product_name"), "required": required_quantity, "on_hand": round(stock_balance, 3), "needed": calculate_stock_shortage(required_quantity, stock_balance), "unit": required_unit, "target": candidate.get("target_name"), "reason": "Predicted mixture requirement exceeds current recorded stock.", "purchase_state": purchase_state}])
    per_100_l = calculation.get("per_100_l_g") if calculation and calculation.get("per_100_l_g") is not None else calculation.get("per_100_l_ml") if calculation else None
    per_100_l_unit = "g/100 L" if calculation and calculation.get("per_100_l_g") is not None else "ml/100 L" if calculation and calculation.get("per_100_l_ml") is not None else None
    component = {"product_name": candidate.get("product_name"), "active_ingredient": candidate.get("active_ingredient"), "registration_number": candidate.get("registration_number"), "purpose": candidate.get("target_name"), "concentrate_form": candidate.get("concentrate_form"), "final_application_medium": candidate.get("final_application_medium"), "rate": rate, "rate_unit": candidate.get("dose_unit"), "total": calculation.get("total") if calculation else None, "total_unit": calculation.get("total_unit") if calculation else None, "per_100_l": per_100_l, "per_100_l_unit": per_100_l_unit, "purchase_state": purchase_state, "stock_on_hand": stock_balance, "stock_unit": candidate.get("unit"), "phi_days": phi_days, "rei_hours": candidate.get("rei_hours"), "resistance_group": candidate.get("resistance_group"), "mixing_sequence": candidate.get("mixing_instructions"), "compatibility_notes": candidate.get("compatibility_notes"), "label_url": candidate.get("label_url")}
    batch_recipe = calculate_batch_recipe(batches, [component])
    option_rows = fetch_all("SELECT o.*,p.name product_name,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.eligible_for_projection FROM treatment_product_options o JOIN products p ON p.id=o.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE o.estate_id=%s AND o.crop_scope=%s AND o.target_code IN (%s,'any') AND o.mixture_role<>'primary' AND o.active=1 AND p.active=1 ORDER BY FIELD(o.default_decision,'candidate','blocked','not_selected'),p.name", (estate_id(), crop_scope, target_code))
    support_review = [_review_possible_product(row, stock_by_product, planning_water_l=planning_water_l, planning_area_ha=known_area) for row in option_rows]
    compatibility_policy = {"automatic_combination_allowed": False, "rule": "Only an exact product combination recorded as verified_compatible may be combined. Sulfur and copper default to separate applications. Conditional combinations require agronomist approval and a jar test only where the current label permits it.", "primary_product": component["product_name"]}
    equipment_choices = [{"id": row.get("equipment_id"), "name": row.get("name"), "make_model": row.get("make_model"), "capacity_l": _number(row.get("usable_capacity_l")) or _number(row.get("tank_capacity_l")), "calibration_status": row.get("calibration_status")} for row in equipment_rows]
    configuration_needed = []
    if not equipment_rows:
        configuration_needed.append("Add an active spray-equipment profile.")
    elif not any(row.get("calibration_status") == "verified" for row in equipment_rows):
        configuration_needed.append("Measure usable tank fill and complete sprayer calibration.")
    if missing_area_blocks:
        configuration_needed.append("Record the area of every active block used for whole-estate projections.")
    return {"status": "calculated_proposal_blocked" if hard_blocks else "ready_for_agronomist_review", "target_code": target_code, "target_name": candidate.get("target_name"), "preferred_candidate": candidate, "candidates": candidates, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "needed_list": needed_list, "stock_review_list": stock_review_list, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "application_window": spray_window, "configuration": {"requested_sprayer": requested_equipment or None, "selected_sprayer_id": (sprayer or {}).get("equipment_id"), "equipment_choices": equipment_choices, "needs_configuration": configuration_needed}, "mixture": {"planning_basis": {"area_ha": known_area, "water_l": planning_water_l, "application_medium": "water_spray", "equipment": sprayer, "equipment_choices": equipment_choices, "sprayer_batches": batches, "area_note": "All active blocks with known area; confirm exact treated blocks.", "water_note": "Adjustable planning carrier volume; confirm calibrated L/ha and actual batch fills."}, "components": [component], "batch_recipe": batch_recipe, "support_product_review": support_review, "compatibility_policy": compatibility_policy, "mixing_order": [component["product_name"]], "hard_blocks": hard_blocks, "earliest_harvest_forecast": earliest_harvest, "phi_passes_current_forecast": phi_ok}, "message": "Calculated water-spray decision support, not an application order. Every concentrate form, source, compatibility gate and exclusion remains in the database; unverified conversions and combinations are blocked."}
