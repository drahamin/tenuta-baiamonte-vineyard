from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..db import fetch_all
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


def _risk_rate(candidate: dict[str, Any], prediction: dict[str, Any]) -> float | None:
    minimum, maximum = _number(candidate.get("min_dose")), _number(candidate.get("max_dose"))
    if minimum is None or candidate.get("dose_unit") != "kg/ha":
        return None
    score = _number(prediction.get("current_risk_score")) or 0
    if score >= 75:
        return min(maximum or minimum, max(minimum, 8.0))
    if score >= 50:
        return min(maximum or minimum, max(minimum, 4.0))
    return minimum


def product_guidance(crop_scope: str, prediction: dict[str, Any], *, forecast: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a fully calculated proposal while retaining legal and human approval gates."""
    if forecast is None:
        from ..display_data import weather_context_payload
        forecast = weather_context_payload().get("forecast") or []
    target_code = str(prediction.get("target_code") or "").strip()
    all_purchases = fetch_all("SELECT pe.*,p.name product_name FROM treatment_purchase_evidence pe LEFT JOIN products p ON p.id=pe.product_id WHERE pe.estate_id=%s AND YEAR(pe.invoice_date)=YEAR(CURDATE()) ORDER BY pe.invoice_date,pe.invoice_number,pe.line_number", (estate_id(),))
    stock_review_list = [row for row in all_purchases if "[STOCK REVIEW]" in str(row.get("notes") or "") or "Unclassified Agriplanet line" in str(row.get("notes") or "")]
    purchases = [row for row in all_purchases if row not in stock_review_list]
    purchase_by_product: dict[str, list[dict[str, Any]]] = {}
    for row in purchases:
        if row.get("product_name"):
            purchase_by_product.setdefault(str(row["product_name"]), []).append(row)
    stock_rows = fetch_all("SELECT p.name product_name,p.unit,SUM(i.quantity_delta) stock_on_hand FROM products p JOIN inventory_movements i ON i.product_id=p.id WHERE p.estate_id=%s GROUP BY p.id,p.name,p.unit", (estate_id(),))
    stock_by_product = {str(row["product_name"]): row for row in stock_rows}
    purchase_summary = [{"product_name": name, "quantity": round(sum(_number(row.get("quantity_total")) or 0 for row in lines), 3), "unit": lines[0].get("quantity_unit"), "stock_on_hand": round(_number((stock_by_product.get(name) or {}).get("stock_on_hand")) or 0, 3), "stock_unit": (stock_by_product.get(name) or {}).get("unit") or lines[0].get("quantity_unit"), "invoice_numbers": list(dict.fromkeys(str(row.get("invoice_number")) for row in lines)), "treatment_relevance": lines[0].get("treatment_relevance")} for name, lines in purchase_by_product.items()]
    non_treatment = [row for row in purchases if row.get("treatment_relevance") == "not_treatment"]
    if not target_code:
        return {"status": "waiting_for_target", "target_code": None, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "purchase_summary": purchase_summary, "non_treatment_purchases": non_treatment, "message": "No current target is supported. Purchased products are inventory evidence, not a reason to spray."}

    uses = fetch_all("SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit FROM product_authorized_uses u JOIN products p ON p.id=u.product_id WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 ORDER BY (u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE())) DESC,u.label_verified_on DESC,p.name", (estate_id(), crop_scope, target_code))
    candidates = [row for row in uses if row.get("authorization_status") == "authorized" and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= date.today())]
    blocked_products = [{"product_name": row.get("product_name"), "reason": f"Authorization status: {row.get('authorization_status')}; expiry {row.get('authorization_expires_on') or 'not recorded'}."} for row in uses if row not in candidates]
    if not candidates:
        return {"status": "no_verified_candidate", "target_code": target_code, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "non_treatment_purchases": non_treatment, "message": "No currently authorized crop-and-target product is verified. The engine may recommend a new purchase only after a current Italian label is added and checked."}

    area_rows = fetch_all("SELECT code,name,area_ha FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),))
    known_area = round(sum(_number(row.get("area_ha")) or 0 for row in area_rows), 3)
    missing_area_blocks = [row.get("code") for row in area_rows if _number(row.get("area_ha")) is None]
    harvest_rows = fetch_all("SELECT g.final_forecast_date,g.predicted_date FROM gdd_forecasts g JOIN seasons s ON s.id=g.season_id WHERE g.estate_id=%s AND s.vintage_year=YEAR(CURDATE()) ORDER BY COALESCE(g.final_forecast_date,g.predicted_date)", (estate_id(),))
    harvest_dates = [_day(row.get("final_forecast_date") or row.get("predicted_date")) for row in harvest_rows]
    earliest_harvest = min((value for value in harvest_dates if value), default=None)
    candidate = candidates[0]
    rate = _risk_rate(candidate, prediction)
    planning_water_l = 500.0
    calculation = calculate_area_mix(area_ha=known_area, water_l=planning_water_l, rate_kg_ha=rate) if known_area and rate else None
    stock_balance = _number((stock_by_product.get(str(candidate.get("product_name"))) or {}).get("stock_on_hand")) or 0
    required_quantity = _number(calculation.get("total_kg")) if calculation else None
    purchase_state = "in_stock" if stock_balance > 0 and (required_quantity is None or stock_balance >= required_quantity) else "insufficient_stock" if stock_balance > 0 else "suggested_purchase"
    spray_window = select_application_window(forecast, prediction.get("window_start"), prediction.get("window_end"), sulfur=str(candidate.get("active_ingredient") or "").casefold().startswith("sulfur"))
    phi_days = int(candidate.get("phi_days") or 0)
    recommended_day = _day(spray_window.get("recommended_date"))
    phi_ok = not (recommended_day and earliest_harvest and (earliest_harvest - recommended_day).days < phi_days)
    hard_blocks = ["Record a current block scouting observation and confirm the target before approval.", "Select the exact treated blocks; the calculated estate area is only a planning basis.", "Confirm the actual tank water volume; 500 L is a planning assumption, not an application record.", "Agronomist must approve the product, rate, compatibility, sequence, PHI, REI, weather and PPE."]
    if missing_area_blocks:
        hard_blocks.append("Add area for blocks: " + ", ".join(str(value) for value in missing_area_blocks) + ".")
    if spray_window["status"] != "provisional_window":
        hard_blocks.append(spray_window["message"])
    if not phi_ok:
        hard_blocks.append(f"The {phi_days}-day PHI would overlap the earliest current harvest forecast ({earliest_harvest}).")
    if purchase_state == "suggested_purchase":
        hard_blocks.append(f"Purchase/on-hand quantity for {candidate.get('product_name')} is not verified; acquire or count stock before approval.")
    if purchase_state == "insufficient_stock":
        hard_blocks.append(f"Only {stock_balance:g} {candidate.get('unit') or ''} is recorded in stock; the proposal requires {required_quantity:g} kg.")
    needed_list = [] if required_quantity is None or stock_balance >= required_quantity else [{"product_name": candidate.get("product_name"), "required": required_quantity, "on_hand": round(stock_balance, 3), "needed": calculate_stock_shortage(required_quantity, stock_balance), "unit": "kg", "target": candidate.get("target_name"), "reason": "Predicted mixture requirement exceeds current recorded stock.", "purchase_state": purchase_state}]
    component = {"product_name": candidate.get("product_name"), "active_ingredient": candidate.get("active_ingredient"), "registration_number": candidate.get("registration_number"), "purpose": candidate.get("target_name"), "rate": rate, "rate_unit": candidate.get("dose_unit"), "total": calculation.get("total_kg") if calculation else None, "total_unit": "kg" if calculation else None, "per_100_l": calculation.get("per_100_l_g") if calculation else None, "per_100_l_unit": "g/100 L" if calculation else None, "purchase_state": purchase_state, "stock_on_hand": stock_balance, "stock_unit": candidate.get("unit"), "phi_days": phi_days, "rei_hours": candidate.get("rei_hours"), "resistance_group": candidate.get("resistance_group"), "mixing_sequence": "Add only according to the current container label while agitation is running; do not add unverified adjuncts.", "label_url": candidate.get("label_url")}
    support_review = [{"product_name": "GEL DI SILICE", "purchase_state": "in_stock", "stock_on_hand": _number((stock_by_product.get("GEL DI SILICE") or {}).get("stock_on_hand")) or 0, "stock_unit": (stock_by_product.get("GEL DI SILICE") or {}).get("unit"), "decision": "blocked_pending_container_check", "reason": "Invoice is kg while the historical recipe is ml/100 L; exact formulation, rate, compatibility and sequence must be reconciled."}, {"product_name": "RESOLVE", "purchase_state": "in_stock", "stock_on_hand": _number((stock_by_product.get("RESOLVE") or {}).get("stock_on_hand")) or 0, "stock_unit": (stock_by_product.get("RESOLVE") or {}).get("unit"), "decision": "blocked_pending_container_check", "reason": "Invoice is liquid 5 L packages while the historical recipe is g/100 L; do not infer a conversion."}, {"product_name": "IMPULSIVE PREMIUM", "purchase_state": "in_stock", "stock_on_hand": _number((stock_by_product.get("IMPULSIVE PREMIUM") or {}).get("stock_on_hand")) or 0, "stock_unit": (stock_by_product.get("IMPULSIVE PREMIUM") or {}).get("unit"), "decision": "not_selected", "reason": "Nutritional/biostimulant support is not justified by the current powdery-mildew signal alone."}] if target_code == "powdery_mildew" else []
    return {"status": "calculated_proposal_blocked" if hard_blocks else "ready_for_agronomist_review", "target_code": target_code, "target_name": candidate.get("target_name"), "preferred_candidate": candidate, "candidates": candidates, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "needed_list": needed_list, "stock_review_list": stock_review_list, "non_treatment_purchases": non_treatment, "application_window": spray_window, "mixture": {"planning_basis": {"area_ha": known_area, "water_l": planning_water_l, "area_note": "All active blocks with known area; confirm exact treated blocks.", "water_note": "Planning assumption; confirm tank volume."}, "components": [component], "support_product_review": support_review, "mixing_order": [component["product_name"]], "hard_blocks": hard_blocks, "earliest_harvest_forecast": earliest_harvest, "phi_passes_current_forecast": phi_ok}, "message": "Calculated decision support, not an application order. Products outside the purchase ledger are allowed and are clearly marked as suggested purchases."}
