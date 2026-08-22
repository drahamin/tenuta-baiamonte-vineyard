from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any

from ..db import fetch_all, fetch_one
from ..inventory import treatment_inventory_reconciliation
from ..service import estate_id


SCENARIO_TARGETS = (
    {"code": "downy_mildew", "label": "Downy mildew / peronospora", "crop_scope": "vineyard"},
    {"code": "powdery_mildew", "label": "Powdery mildew / oidium", "crop_scope": "vineyard"},
    {"code": "botrytis", "label": "Botrytis / grey mold", "crop_scope": "vineyard"},
    {"code": "hail_wound_followup", "label": "Hail wound follow-up / mold risk", "crop_scope": "vineyard", "guidance_target": "botrytis"},
    {"code": "olive_fly", "label": "Olive fruit fly", "crop_scope": "olives"},
    {"code": "olive_peacock_spot", "label": "Olive peacock spot", "crop_scope": "olives"},
)


_TREATMENT_SEASONALITY = {
    "downy_mildew": {
        "active_months": {4, 5, 6, 7}, "shoulder_months": {3, 8},
        "stages": {"budbreak", "shoot_growth", "flowering", "fruit_set", "bunch_closure"},
    },
    "powdery_mildew": {
        "active_months": {4, 5, 6, 7, 8}, "shoulder_months": {3, 9},
        "stages": {"shoot_growth", "flowering", "fruit_set", "bunch_closure", "veraison"},
    },
    "botrytis": {
        "active_months": {5, 6, 7, 8, 9, 10}, "shoulder_months": {4, 11},
        "stages": {"flowering", "fruit_set", "bunch_closure", "veraison", "ripening", "harvest_ready"},
    },
    "olive_fly": {
        "active_months": {7, 8, 9, 10, 11}, "shoulder_months": {6, 12},
        "stages": {"fruit_set", "veraison", "ripening", "harvest_ready"},
    },
    "olive_peacock_spot": {
        "active_months": {2, 3, 4, 5, 9, 10, 11, 12}, "shoulder_months": {1, 6, 8},
        "stages": set(),
    },
}


def treatment_seasonality(
    payload: dict[str, Any], *, pressure_history: dict[str, Any] | None = None,
    treatment_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain seasonal fit without using a calendar heuristic as field proof."""
    requested = str(payload.get("target_code") or "").strip().casefold()
    option = next((row for row in SCENARIO_TARGETS if row["code"] == requested), None) or {}
    target = str(option.get("guidance_target") or requested)
    scenario_day = _day(payload.get("scenario_date")) or date.today()
    stage = str(payload.get("growth_stage") or "").strip().casefold()
    event = str(payload.get("event_type") or "none").strip().casefold()
    rules = _TREATMENT_SEASONALITY.get(target) or {}
    active_months = set(rules.get("active_months") or ())
    shoulder_months = set(rules.get("shoulder_months") or ())
    expected_stages = set(rules.get("stages") or ())
    event_driven = requested == "hail_wound_followup" or event in {"hail", "visible_symptoms"}
    if event_driven:
        calendar_fit = "event driven"
    elif scenario_day.month in active_months:
        calendar_fit = "active window"
    elif scenario_day.month in shoulder_months:
        calendar_fit = "shoulder window"
    else:
        calendar_fit = "outside typical window"
    if not stage:
        stage_fit = "not supplied"
    elif not expected_stages:
        stage_fit = "stage-neutral rule"
    elif stage in expected_stages:
        stage_fit = "stage aligned"
    else:
        stage_fit = "stage outside typical window"
    pressure = dict(pressure_history or {})
    treatments = dict(treatment_history or {})
    pressure_samples = int(pressure.get("samples") or 0)
    pressure_average = _number(pressure.get("average_risk_score"))
    treatment_count = int(treatments.get("treatments") or 0)
    supports_review = event_driven or calendar_fit in {"active window", "shoulder window"} or (
        pressure_samples > 0 and pressure_average is not None and pressure_average >= 45
    )
    evidence = [f"{scenario_day.strftime('%B')} is {calendar_fit} for {target.replace('_', ' ')}"]
    if stage:
        evidence.append(f"{stage.replace('_', ' ')} is {stage_fit}")
    if pressure_samples:
        evidence.append(f"Baiamonte has {pressure_samples} same-month pressure assessment(s), average score {pressure_average:.1f}")
    if treatment_count:
        evidence.append(f"Baiamonte has {treatment_count} completed {str(payload.get('crop_scope') or 'vineyard')} treatment(s) in this calendar month across prior/current seasons")
    return {
        "target_code": target, "scenario_month": scenario_day.month,
        "calendar_fit": calendar_fit, "stage_fit": stage_fit,
        "event_driven": event_driven, "supports_program_review": supports_review,
        "pressure_samples": pressure_samples, "historical_average_risk_score": pressure_average,
        "same_month_treatment_count": treatment_count,
        "evidence": evidence,
        "message": "; ".join(evidence) + ". Seasonal fit changes review priority, but never proves disease or authorizes application.",
    }


def treatment_record_evidence_gaps(rows: list[dict[str, Any]], crop_scope: str) -> list[dict[str, Any]]:
    """Expose missing numbered records without inventing applications or completion facts."""
    numbers: set[int] = set()
    for row in rows:
        match = re.search(r"\btreatment\s+(\d+)\b", str(row.get("purpose") or ""), re.IGNORECASE)
        if match:
            numbers.add(int(match.group(1)))
    if not numbers:
        return []
    return [{
        "code": f"missing_{crop_scope}_treatment_{number}",
        "treatment_number": number,
        "title": f"Treatment {number} record needed",
        "status": "source_required",
        "detail": "Do not mark this treatment completed until an authoritative field record supplies the date, products, rates, water, scope and actual quantities used.",
    } for number in range(1, max(numbers) + 1) if number not in numbers]


def latest_hail_followup(year: int, crop_scope: str) -> dict[str, Any] | None:
    """Prefer the authoritative damage chain, retaining legacy scouting fallback."""
    if crop_scope != "vineyard":
        return None
    assessment = fetch_one(
        "SELECT a.id,a.assessed_at observed_at,a.event_date,a.damage_type issue_type,a.event_key damage_event_key,a.review_status damage_proposal_status,"
        "COALESCE(a.estate_yield_loss_pct,a.affected_area_pct*a.estimated_yield_loss_pct/100) proposed_estate_loss_pct,"
        "a.scope_type,a.trend,a.confidence,'damage_assessment' source "
        "FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id WHERE a.estate_id=%s AND s.vintage_year=%s "
        "AND a.damage_type='hail' AND a.active=1 AND a.review_status NOT IN ('rejected','archived') ORDER BY a.assessed_at DESC LIMIT 1",
        (estate_id(), year),
    )
    return assessment or fetch_one(
        "SELECT so.id,so.observed_at,so.issue_type,so.damage_event_key,so.damage_proposal_status,so.proposed_estate_loss_pct,"
        "'scouting_observation' source FROM scouting_observations so JOIN seasons s ON s.id=so.season_id "
        "WHERE so.estate_id=%s AND s.vintage_year=%s AND so.damage_type='hail' ORDER BY so.observed_at DESC LIMIT 1",
        (estate_id(), year),
    )


def treatment_scenario_options() -> dict[str, Any]:
    return {
        "targets": list(SCENARIO_TARGETS),
        "severities": ["trace", "low", "moderate", "high", "critical"],
        "events": ["none", "hail", "heavy_rain", "high_humidity", "heat", "visible_symptoms"],
    }


def field_review_guidance(target_code: Any, *, event_type: Any = None, crop_scope: str = "vineyard") -> dict[str, Any]:
    """Describe the evidence needed for a defensible treatment or damage decision."""
    target = str(target_code or "unclassified").strip().casefold()
    event = str(event_type or "none").strip().casefold()
    hail = event == "hail" or target == "hail_wound_followup"
    photos = [
        "One wide canopy photo from each representative zone, with row direction and block visible.",
        "Close photos of symptoms on both upper and lower leaf surfaces and on bunches/fruit.",
        "An undamaged comparison from the same block, distance and lighting.",
        "Sharp, original-resolution images without filters; avoid repeated views of the same plant.",
    ]
    measurements = [
        "Record block or whole-estate scope, growth stage, date/time and the exact sampled rows or parcel.",
        "Count total and affected leaves, bunches or fruit in at least five representative points; do not report a percentage without counts.",
        "Record severity, affected-area estimate, recent rain/leaf wetness, irrigation and whether symptoms are spreading.",
    ]
    if hail:
        photos.extend([
            "Photograph shoot wounds, split berries, damaged bunches and defoliation separately.",
            "Repeat the same marked locations after 24–72 hours to show wound drying or emerging mold/rot.",
        ])
        measurements.append("For hail, count damaged and total bunches/shoots separately; note berry splitting and fresh mold/rot symptoms.")
    if crop_scope == "olives":
        measurements.append("Include trap count/date where available and photograph both sides of affected leaves or fruit entry/exit marks.")
    return {
        "target_code": target,
        "event_type": event,
        "minimum_photo_set": 0,
        "recommended_photo_set": 6 if hail else 4,
        "photos_optional": True,
        "photos": photos,
        "measurements": measurements,
        "ai_accuracy_rule": "Photos are optional supporting evidence. The review can proceed from structured observations and counts; AI can estimate visible incidence only within the declared sampled scope, and no evidence source by itself authorizes a treatment.",
        "completion_rule": "The review is complete only after the Agronomist confirms target, current label, rate, compatibility, PHI, REI, weather and PPE.",
    }


def simulated_prediction(
    payload: dict[str, Any], *, as_of_assessment: dict[str, Any] | None = None,
    seasonal_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a bounded hypothetical treatment-review prediction without saving field facts."""
    crop_scope = str(payload.get("crop_scope") or "vineyard").strip().casefold()
    if crop_scope not in {"vineyard", "olives"}:
        raise ValueError("Choose vineyard or olives")
    requested_target = str(payload.get("target_code") or "").strip().casefold()
    option = next((row for row in SCENARIO_TARGETS if row["code"] == requested_target and row["crop_scope"] == crop_scope), None)
    if not option:
        raise ValueError("Choose a configured scenario target for this crop")
    severity = str(payload.get("severity") or "moderate").strip().casefold()
    scores = {"trace": 18, "low": 32, "moderate": 55, "high": 76, "critical": 92}
    if severity not in scores:
        raise ValueError("Choose trace, low, moderate, high or critical")
    try:
        scenario_date = _day(payload.get("scenario_date")) or date.today()
    except (TypeError, ValueError):
        scenario_date = date.today()
    reported_risk_score = scores[severity]
    risk_score = reported_risk_score
    event = str(payload.get("event_type") or "none").strip().casefold()
    replayed = bool(as_of_assessment)
    weather_risk_score = _number((as_of_assessment or {}).get("risk_score")) if replayed else None
    if weather_risk_score is not None:
        # A replay combines the user's field scenario with historical weather.
        # Weather is evidence, not a reason to erase reported symptoms or
        # severity.  The stronger defensible signal controls product review.
        weather_risk_score = min(100, max(0, weather_risk_score))
        risk_score = max(reported_risk_score, weather_risk_score)
    elif event in {"hail", "heavy_rain", "high_humidity", "visible_symptoms"}:
        risk_score = min(100, risk_score + 8)
    level = "critical" if risk_score >= 85 else "high" if risk_score >= 70 else "moderate" if risk_score >= 45 else "low"
    windows = {"critical": (0, 1), "high": (1, 3), "moderate": (3, 7), "low": (7, 10)}
    start_days, end_days = windows[level]
    # A historical replay answers "what would the engine have shown on this
    # date?".  Keep its application check anchored to that exact day so the
    # result can be compared with the recorded treatment instead of searching
    # a later, hypothetical risk window.
    window_start = scenario_date if replayed else scenario_date + timedelta(days=start_days)
    window_end = scenario_date if replayed else scenario_date + timedelta(days=end_days)
    guidance_target = str(option.get("guidance_target") or requested_target)
    seasonality = dict(seasonal_evidence or treatment_seasonality(payload))
    return {
        "type": "scenario_simulation",
        "headline": f"Simulated {option['label']} review",
        "timing_label": (
            f"Historical replay · {scenario_date.strftime('%d %b')}"
            if replayed else
            f"Field review {window_start.strftime('%d %b')}–{window_end.strftime('%d %b')}"
        ),
        "window_start": window_start,
        "window_end": window_end,
        "confidence": "Historical weather-model replay" if replayed else "Hypothetical scenario only",
        "risk_level": level,
        "current_risk_level": level,
        "current_risk_score": risk_score,
        "reported_severity_score": reported_risk_score,
        "weather_risk_score": weather_risk_score,
        "why": (
            f"As-of replay combines the selected {severity} field severity ({reported_risk_score:.0f}) "
            f"with the stored {as_of_assessment.get('model_version') or 'disease'} weather score "
            f"({weather_risk_score:.1f}): {as_of_assessment.get('evidence_summary') or 'weather evidence recorded for that date'}. "
            f"The stronger signal ({risk_score:.1f}) controls the product-review program."
            if replayed else
            f"Scenario inputs: {severity} severity; event {event.replace('_', ' ')}; growth stage {str(payload.get('growth_stage') or 'not supplied').replace('_', ' ')}."
        ),
        "suggested_action": "Request the structured field review and confirm live weather before considering any product. This simulation does not change the live prediction or create an application.",
        "agronomist_status": "pending",
        "requires_agronomist_approval": True,
        "target_code": guidance_target,
        "scenario_target_code": requested_target,
        "event_type": event,
        "scenario_date": scenario_date,
        "historical_replay": replayed,
        "source_assessment_id": (as_of_assessment or {}).get("id"),
        "weather_assessment": dict(as_of_assessment or {}),
        "seasonality": seasonality,
    }


def inventory_readiness(guidance: dict[str, Any]) -> dict[str, Any]:
    reconciliation = guidance.get("inventory_reconciliation") or {}
    needed = guidance.get("needed_list") or []
    reviews = guidance.get("stock_review_list") or []
    mixture = guidance.get("mixture") or {}
    components = mixture.get("components") or []
    if not reconciliation.get("complete", False) or reviews:
        status = "blocked"
        message = "Inventory is not prediction-ready: reconcile completed use and classify invoice stock lines first."
    elif needed:
        status = "shortage"
        message = "The mixture can be calculated, but recorded stock is insufficient. Use the needed list before approval."
    elif components and all(item.get("purchase_state") == "in_stock" for item in components):
        status = "ready"
        message = "Every calculated primary component is reconciled and currently recorded in stock."
    elif guidance.get("status") in {"waiting_for_target", "no_verified_candidate"}:
        status = "not_applicable"
        message = "Inventory cannot be judged until a verified crop-and-target product exists."
    else:
        status = "review"
        message = "Inventory evidence exists, but final quantities remain conditional on scope, rate and approval."
    return {"status": status, "message": message, "reconciliation": reconciliation, "needed_count": len(needed), "unclassified_stock_lines": len(reviews)}


def mixture_signature(items: list[dict[str, Any]]) -> str:
    """Fingerprint the exact structured products and rates in one application."""
    normalized = sorted((
        {
            "product_id": str(item.get("product_id") or ""),
            "dose_amount": str(item.get("dose_amount") or ""),
            "dose_unit": str(item.get("dose_unit") or "").strip(),
            "total_used": str(item.get("total_used") or ""),
        }
        for item in items
    ), key=lambda item: (item["product_id"], item["dose_unit"], item["dose_amount"], item["total_used"]))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def existing_treatment_safety_audits(
    rows: list[dict[str, Any]], year: int, *, crop_scope: str = "vineyard", harvest_date: Any = None,
) -> dict[str, Any]:
    """Audit historical and current applications without upgrading unknown evidence."""
    application_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
    if not application_ids:
        return {"rows": {}, "summary": {"records": 0, "active_records": 0, "inactive": 0, "verified": 0, "restricted": 0, "attention": 0, "blocked": 0}}
    placeholders = ",".join(["%s"] * len(application_ids))
    item_rows = fetch_all(
        "SELECT i.application_id,i.id item_id,i.product_id,i.dose_amount,i.total_used,i.dose_unit,i.phi_days,p.name product_name,"
        "r.verification_status,r.label_verified_on,r.estate_authorization_status "
        "FROM spray_application_items i JOIN products p ON p.id=i.product_id "
        "LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 "
        f"WHERE i.application_id IN ({placeholders}) ORDER BY i.application_id,p.name",
        tuple(application_ids),
    )
    product_ids = sorted({str(item.get("product_id") or "") for item in item_rows if item.get("product_id")})
    use_rows = fetch_all(
        "SELECT product_id,dose_unit,min_dose,max_dose,water_rate_unit,water_rate_min,water_rate_max "
        "FROM product_authorized_uses WHERE estate_id=%s AND crop_scope=%s AND active=1 "
        f"AND product_id IN ({','.join(['%s'] * len(product_ids))})",
        (estate_id(), crop_scope, *product_ids),
    ) if product_ids else []
    uses_by_product: dict[str, list[dict[str, Any]]] = {}
    for use in use_rows:
        uses_by_product.setdefault(str(use.get("product_id") or ""), []).append(use)
    equipment_rows = fetch_all(
        "SELECT a.id application_id,a.equipment_name,a.equipment_id,q.name configured_name,s.calibration_status,s.calibrated_on,"
        "s.nozzle_setup,s.flow_l_min,s.operating_pressure_bar,s.travel_speed_kph,s.carrier_rate_l_ha "
        "FROM spray_applications a LEFT JOIN equipment q ON q.id=a.equipment_id "
        "LEFT JOIN spray_equipment_profiles s ON s.equipment_id=a.equipment_id AND s.active=1 "
        f"WHERE a.id IN ({placeholders})",
        tuple(application_ids),
    )
    approval_rows = fetch_all(
        "SELECT application_id,mixture_signature,status,jar_test_status,current_labels_confirmed,exact_combination_confirmed,"
        "compatibility_basis,sequence_notes,approved_by,approved_at FROM treatment_mixture_approvals "
        f"WHERE estate_id=%s AND active=1 AND application_id IN ({placeholders})",
        (estate_id(), *application_ids),
    )
    approvals_by_application = {str(item.get("application_id") or ""): item for item in approval_rows}
    if crop_scope == "vineyard":
        harvest = fetch_all(
            "SELECT first_pick_date FROM vintage_summaries WHERE estate_id=%s AND vintage_year=%s "
            "AND first_pick_date IS NOT NULL AND harvest_date_precision='day' "
            "UNION ALL SELECT COALESCE(g.final_forecast_date,g.predicted_date) first_pick_date FROM gdd_forecasts g "
            "JOIN seasons s ON s.id=g.season_id WHERE g.estate_id=%s AND s.vintage_year=%s "
            "AND COALESCE(g.final_forecast_date,g.predicted_date) IS NOT NULL",
            (estate_id(), year, estate_id(), year),
        )
        earliest_harvest = min((_day(item.get("first_pick_date")) for item in harvest if _day(item.get("first_pick_date"))), default=None)
    else:
        earliest_harvest = _day(harvest_date)
    reconciliation = treatment_inventory_reconciliation(year)
    unresolved_by_application: dict[str, list[dict[str, Any]]] = {}
    for issue in reconciliation.get("issues") or []:
        unresolved_by_application.setdefault(str(issue.get("application_id") or ""), []).append(issue)
    items_by_application: dict[str, list[dict[str, Any]]] = {}
    for item in item_rows:
        items_by_application.setdefault(str(item.get("application_id") or ""), []).append(item)
    equipment_by_application = {str(item.get("application_id") or ""): item for item in equipment_rows}

    audited: dict[str, dict[str, Any]] = {}
    counts = {"records": len(rows), "active_records": 0, "inactive": 0, "verified": 0, "restricted": 0, "attention": 0, "blocked": 0}
    for row in rows:
        application_id = str(row.get("id") or "")
        row_status = str(row.get("status") or "").casefold()
        if row_status in {"cancelled", "canceled", "rejected", "void"}:
            counts["inactive"] += 1
            audited[application_id] = {
                "status": "inactive",
                "checks": [],
                "blocker_count": 0,
                "safe_for_prediction_reuse": False,
                "rule": "Inactive evidence remains in the audit trail but is excluded from active treatment-readiness counts.",
            }
            continue
        counts["active_records"] += 1
        items = items_by_application.get(application_id, [])
        equipment = equipment_by_application.get(application_id) or {}
        completed = str(row.get("status") or "").casefold() in {"completed", "applied"}
        checks: list[dict[str, Any]] = []

        labels_ready = bool(items) and bool(row.get("label_legal_confirmed")) and all(
            item.get("verification_status") == "verified"
            and item.get("estate_authorization_status") == "confirmed"
            and bool(item.get("label_verified_on"))
            for item in items
        )
        label_products = [str(item.get("product_name") or "product") for item in items if not (
            item.get("verification_status") == "verified"
            and item.get("estate_authorization_status") == "confirmed"
            and item.get("label_verified_on")
        )]
        checks.append({
            "code": "label",
            "label": "Current product label",
            "status": "verified" if labels_ready else "unverified",
            "detail": "Application and current product-label evidence agree." if labels_ready else (
                "Unverified label evidence: " + ", ".join(label_products) if label_products else "The application label check or structured product label is not verified."
            ),
        })

        unresolved = unresolved_by_application.get(application_id, [])
        # Exact product use can be authoritative even while other completion
        # facts (operator, scope, weather or PPE) remain unconfirmed.
        quantities_ready = (not completed) or (bool(items) and not unresolved and all(item.get("total_used") is not None for item in items))
        checks.append({
            "code": "completed_use",
            "label": "Completed-use quantities",
            "status": "not_applicable" if not completed else "verified" if quantities_ready else "unknown",
            "detail": "Not applicable until the treatment is completed." if not completed else "Every product total is recorded and reconciled to inventory." if quantities_ready else (
                "; ".join(str(item.get("reason") or "Exact total used is unknown") for item in unresolved) or "One or more exact product totals used are unknown."
            ),
        })

        rate_conflicts: list[str] = []
        rate_unknown: list[str] = []
        for item in items:
            item_unit = str(item.get("dose_unit") or "").strip().casefold()
            item_rate = _number(item.get("dose_amount"))
            comparable: list[tuple[float, float]] = []
            for use in uses_by_product.get(str(item.get("product_id") or ""), []):
                if item_unit == str(use.get("water_rate_unit") or "").strip().casefold() and use.get("water_rate_min") is not None:
                    low = float(use["water_rate_min"])
                    comparable.append((low, float(use.get("water_rate_max") if use.get("water_rate_max") is not None else low)))
                if item_unit == str(use.get("dose_unit") or "").strip().casefold() and use.get("min_dose") is not None:
                    low = float(use["min_dose"])
                    comparable.append((low, float(use.get("max_dose") if use.get("max_dose") is not None else low)))
            if item_rate is None or not comparable:
                rate_unknown.append(str(item.get("product_name") or "product"))
            elif not any(low <= item_rate <= high for low, high in comparable):
                ranges = ", ".join(f"{low:g}–{high:g} {item.get('dose_unit')}" for low, high in comparable)
                rate_conflicts.append(f"{item.get('product_name')}: {item_rate:g} {item.get('dose_unit')} recorded; verified range {ranges}")
        checks.append({
            "code": "rate",
            "label": "Recorded rate vs current directions",
            "status": "conflict" if rate_conflicts else "unknown" if rate_unknown else "verified",
            "detail": "; ".join(rate_conflicts) if rate_conflicts else (
                "No comparable rate basis for: " + ", ".join(rate_unknown) if rate_unknown else "Every recorded rate is within a comparable current database range."
            ),
        })

        calibration_fields = ("nozzle_setup", "flow_l_min", "operating_pressure_bar", "travel_speed_kph", "carrier_rate_l_ha")
        calibration_ready = equipment.get("calibration_status") == "verified" and all(equipment.get(field) is not None for field in calibration_fields)
        checks.append({
            "code": "sprayer_calibration",
            "label": "Sprayer calibration",
            "status": "verified" if calibration_ready else "missing",
            "detail": f"Verified calibration for {equipment.get('configured_name') or equipment.get('equipment_name')}." if calibration_ready else "Missing a verified sprayer profile with nozzle, flow, pressure, speed and carrier-rate measurements.",
        })

        application_day = _day(row.get("application_date"))
        phi_values = [int(item["phi_days"]) for item in items if item.get("phi_days") is not None]
        phi_end = application_day + timedelta(days=max(phi_values)) if application_day and phi_values else None
        phi_conflict = bool(phi_end and earliest_harvest and phi_end > earliest_harvest)
        phi_ready = bool(row.get("phi_checked")) and bool(items) and len(phi_values) == len(items) and not phi_conflict
        checks.append({
            "code": "phi",
            "label": "Pre-harvest interval",
            "status": "conflict" if phi_conflict else "verified" if phi_ready else "unknown",
            "detail": f"PHI ends {phi_end.isoformat()}, after the earliest harvest evidence {earliest_harvest.isoformat()}." if phi_conflict else (
                f"Checked against earliest harvest evidence {earliest_harvest.isoformat()}." if phi_ready and earliest_harvest else "PHI is recorded, but no exact harvest date is available for comparison." if phi_ready else "PHI days or the completed application PHI check are missing."
            ),
            "phi_end": phi_end,
            "earliest_harvest": earliest_harvest,
        })

        approval = approvals_by_application.get(application_id) or {}
        signature_matches = bool(items) and approval.get("mixture_signature") == mixture_signature(items)
        approval_ready = (
            len(items) > 1
            and approval.get("status") == "verified"
            and signature_matches
            and bool(approval.get("current_labels_confirmed"))
            and bool(approval.get("exact_combination_confirmed"))
            and approval.get("jar_test_status") in {"passed", "not_required"}
            and bool(str(approval.get("compatibility_basis") or "").strip())
            and bool(str(approval.get("sequence_notes") or "").strip())
            and bool(approval.get("approved_by"))
            and bool(approval.get("approved_at"))
        )
        mixture_ready = len(items) == 1 or approval_ready
        checks.append({
            "code": "mixture",
            "label": "Tank mixture",
            "status": "single_product" if len(items) == 1 else "verified" if approval_ready else "stale" if approval and not signature_matches else "unverified",
            "detail": "Single structured product; no multi-product compatibility claim is required." if len(items) == 1 else (
                f"Exact mixture approved by {approval.get('approved_by')}." if approval_ready else
                "The stored approval no longer matches the current products or rates." if approval and not signature_matches else
                "No complete exact-mixture compatibility approval is stored for this completed mixture."
            ) if len(items) > 1 else "The mixture is unstructured or no product items are recorded.",
        })

        unsafe_statuses = {"unverified", "unknown", "missing", "conflict", "stale"}
        blockers = [check for check in checks if check["status"] in unsafe_statuses]
        disposition = str(row.get("safety_review_disposition") or "").casefold()
        restricted = disposition == "restricted_historical"
        status = "restricted" if restricted else "verified" if not blockers else "blocked" if any(check["status"] == "conflict" for check in blockers) else "attention"
        counts[status] += 1
        audited[application_id] = {
            "status": status,
            "checks": checks,
            "blocker_count": 0 if restricted else len(blockers),
            "retained_limitation_count": len(blockers) if restricted else 0,
            "safe_for_prediction_reuse": status == "verified",
            "reviewed_by": row.get("safety_reviewed_by"),
            "reviewed_at": row.get("safety_reviewed_at"),
            "review_basis": row.get("safety_review_basis"),
            "rule": (
                "Safety review closed as a restricted historical record. Unknown contemporaneous checks remain visible, and this application cannot be reused as a prescription."
                if restricted else
                "Historical products, quantities or mixtures are not reused as prescriptions while any safety evidence remains unknown or unverified."
            ),
        }
    return {"rows": audited, "summary": counts, "crop_scope": crop_scope, "earliest_harvest": earliest_harvest}


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


def select_application_window(forecast: list[dict[str, Any]], window_start: Any, window_end: Any, *, sulfur: bool = False, evidence_kind: str = "forecast") -> dict[str, Any]:
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
        source_text = "recorded daily weather replay" if evidence_kind == "historical_observation" else "daily forecast"
        return {"status": "provisional_window", "recommended_date": selected["date"], "evidence_kind": evidence_kind, "message": f"Candidate day from the {source_text}. Confirm the recorded or hourly wind, rain, temperature, leaf condition and label restrictions before mixing.", "evaluated_days": evaluated}
    if evidence_kind == "historical_observation" and evaluated:
        # The selected historical date is still the replay reference even when
        # daily aggregates cannot prove a safe application window.  Returning
        # it separately from a provisional window prevents the UI from looking
        # broken while preserving the weather/label approval block.
        replay = evaluated[0]
        return {
            "status": "historical_replay_not_cleared",
            "recommended_date": replay["date"],
            "evidence_kind": evidence_kind,
            "message": (
                "Historical replay date calculated, but the recorded daily weather does not establish a safe application window"
                + (f": {', '.join(replay['reasons'])}." if replay["reasons"] else ".")
                + " Review hourly conditions and the completed field record; this date is not an application authorization."
            ),
            "evaluated_days": evaluated,
        }
    source_text = "recorded weather window" if evidence_kind == "historical_observation" else "current forecast window"
    return {"status": "no_suitable_window", "recommended_date": None, "evidence_kind": evidence_kind, "message": f"No defensible application day is available in the {source_text}. Review the evaluated weather evidence; do not force the planned date.", "evaluated_days": evaluated}


def calculate_area_mix(*, area_ha: float, water_l: float, rate_kg_ha: float) -> dict[str, float]:
    total_kg = area_ha * rate_kg_ha
    return {"area_ha": round(area_ha, 3), "water_l": round(water_l, 1), "rate_kg_ha": round(rate_kg_ha, 3), "total_kg": round(total_kg, 3), "per_100_l_g": round(total_kg * 100000 / water_l, 1)}


def reconcile_area_and_water_rate(
    *, area_ha: float, water_l: float, selected_rate: float, minimum_rate: float,
    maximum_rate: float, rate_unit: str, water_rate_min: float | None = None,
    water_rate_max: float | None = None, water_rate_unit: str | None = None,
) -> dict[str, Any]:
    """Intersect label area and carrier-water limits without changing units."""
    total_unit = "kg" if rate_unit == "kg/ha" else "L" if rate_unit == "L/ha" else None
    if not total_unit:
        return {"valid": False, "reason": f"Unsupported area-rate unit {rate_unit or 'not recorded'}."}
    area_low, area_high = area_ha * minimum_rate, area_ha * maximum_rate
    water_quantity = calculate_water_rate_quantity(
        water_l=water_l, rate_min=water_rate_min, rate_max=water_rate_max, rate_unit=water_rate_unit,
    ) if water_rate_min is not None and water_rate_unit else None
    low, high = area_low, area_high
    if water_quantity:
        if water_quantity.get("unit") != total_unit:
            return {"valid": False, "reason": "Area and water concentration limits use incompatible physical units."}
        low = max(low, float(water_quantity["minimum"]))
        high = min(high, float(water_quantity["maximum"]))
    if low > high + 1e-9:
        return {
            "valid": False,
            "reason": "The selected carrier volume cannot satisfy both the per-hectare and per-100-L label ranges.",
            "area_total_range": [round(area_low, 3), round(area_high, 3)],
            "water_total_range": [water_quantity.get("minimum"), water_quantity.get("maximum")] if water_quantity else None,
        }
    desired = area_ha * selected_rate
    total = min(high, max(low, desired))
    per_100_l = total * (100000 if total_unit == "kg" else 100000) / water_l
    return {
        "valid": True, "total": round(total, 3), "total_unit": total_unit,
        "effective_rate_per_ha": round(total / area_ha, 3),
        "per_100_l": round(per_100_l, 1),
        "per_100_l_unit": "g/100 L" if total_unit == "kg" else "ml/100 L",
        "area_total_range": [round(area_low, 3), round(area_high, 3)],
        "water_total_range": [water_quantity.get("minimum"), water_quantity.get("maximum")] if water_quantity else None,
        "limited_by_water_concentration": bool(water_quantity and desired > high),
    }


def compare_treatment_programs(
    predicted_components: list[dict[str, Any]], actual_applications: list[dict[str, Any]], *, target_code: str,
) -> dict[str, Any]:
    """Explain an independent replay beside the actual record without copying it."""
    predicted = {str(row.get("product_name") or "").strip().casefold(): row for row in predicted_components if row.get("product_name")}
    actual_items = [item for application in actual_applications for item in (application.get("products") or [])]
    actual = {str(row.get("product_name") or "").strip().casefold(): row for row in actual_items if row.get("product_name")}
    rows: list[dict[str, Any]] = []
    for key in sorted(predicted.keys() | actual.keys()):
        proposed, applied = predicted.get(key), actual.get(key)
        source = applied or proposed or {}
        if proposed and applied:
            status = "agreement"
            explanation = "The independent replay and the completed field record include this product; compare rate, water and compatibility separately."
        elif proposed:
            status = "system_only"
            explanation = "The independent replay selected this current evidence-backed candidate, but the Agronomist used a different program on the recorded date."
        else:
            status = "actual_only"
            product_type = str(source.get("product_type") or "").casefold()
            targets = {value for value in str(source.get("authorized_targets") or "").split(",") if value}
            roles = {value for value in str(source.get("mixture_roles") or "").split(",") if value}
            if product_type == "fertilizer" or "nutrition" in roles or "support" in roles:
                explanation = "Agronomist-applied nutritional/support component; a disease-only scenario cannot infer its field need from weather alone."
            elif targets and target_code not in targets:
                explanation = "Agronomist-applied control for a different target (" + ", ".join(sorted(value.replace("_", " ") for value in targets)) + ")."
            elif target_code in targets:
                explanation = "Agronomist-selected alternative for the same target; the replay ranked another currently verified candidate and must show this divergence."
            else:
                explanation = "Present in the completed field record, but its current target/role evidence is incomplete."
        rows.append({
            "product_name": source.get("product_name"), "status": status,
            "system_role": (proposed or {}).get("program_role"),
            "actual_dose": (applied or {}).get("dose_amount"), "actual_dose_unit": (applied or {}).get("dose_unit"),
            "explanation": explanation,
        })
    return {
        "actual_record_found": bool(actual_applications),
        "agreement_count": sum(row["status"] == "agreement" for row in rows),
        "system_only_count": sum(row["status"] == "system_only" for row in rows),
        "actual_only_count": sum(row["status"] == "actual_only" for row in rows),
        "rows": rows,
        "message": (
            "Independent counterfactual compared with the completed Agronomist record. Differences are retained and explained; the actual mixture is never copied into the prediction."
            if actual_applications else
            "No completed treatment record overlaps this replay date."
        ),
    }


def calculate_stock_shortage(required: float, on_hand: float) -> float:
    return round(max(0.0, required - on_hand), 3)


def treatment_inventory_plan(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare every calculated program quantity with the running stock ledger.

    Negative stock is preserved: it represents completed use whose supplier
    receipt may arrive later.  Only documented mass-to-mass or volume-to-volume
    unit conversions are performed.
    """
    units = {
        "l": ("volume", 1.0, "L"), "liter": ("volume", 1.0, "L"), "litre": ("volume", 1.0, "L"),
        "ml": ("volume", .001, "ml"),
        "kg": ("mass", 1.0, "kg"), "kilogram": ("mass", 1.0, "kg"),
        "g": ("mass", .001, "g"), "gram": ("mass", .001, "g"),
    }
    plan: list[dict[str, Any]] = []
    for component in components:
        required = _number(component.get("total"))
        on_hand = _number(component.get("stock_on_hand")) or 0.0
        required_unit = str(component.get("total_unit") or "").strip()
        stock_unit = str(component.get("stock_unit") or "").strip()
        req = units.get(required_unit.casefold())
        stock = units.get(stock_unit.casefold())
        comparable = bool(required is not None and req and stock and req[0] == stock[0])
        on_hand_required = round(on_hand * stock[1] / req[1], 3) if comparable else None
        remaining = calculate_stock_shortage(required, on_hand_required) if comparable and required is not None else None
        after = round(on_hand_required - required, 3) if comparable and required is not None else None
        status = (
            "calculation_pending" if required is None else
            "unit_review" if not comparable else
            "receipt_pending" if on_hand < 0 else
            "shortage" if remaining and remaining > 0 else
            "ready"
        )
        plan.append({
            "product_name": component.get("product_name"),
            "program_role": component.get("program_role") or component.get("purpose"),
            "required": round(required, 3) if required is not None else None,
            "required_unit": required_unit or None,
            "on_hand": round(on_hand, 3),
            "stock_unit": stock_unit or None,
            "on_hand_in_required_unit": on_hand_required,
            "remaining_needed": remaining,
            "balance_after_treatment": after,
            "status": status,
            "receipt_pending": on_hand < 0,
        })
    return plan


def annual_nutrition_baseline(year: int, crop_scope: str = "vineyard") -> dict[str, Any]:
    """Return the database-owned annual nutrition review plan and current phase.

    The baseline defines what evidence to collect. It never turns a calendar
    phase into a fertilizer order and never treats a support product as disease
    control.
    """
    crop_scope = str(crop_scope or "vineyard").casefold()
    if crop_scope not in {"vineyard", "olives"}:
        raise ValueError("crop_scope must be vineyard or olives")
    rows = fetch_all(
        "SELECT n.* FROM crop_nutrition_baselines n JOIN seasons s ON s.id=n.season_id "
        "WHERE n.estate_id=%s AND s.vintage_year=%s AND n.crop_scope=%s AND n.active=1 ORDER BY n.phase_order",
        (estate_id(), year, crop_scope),
    )
    latest_stage = fetch_one(
        "SELECT p.stage_code,p.stage_name,p.observed_date,p.percent_complete,COUNT(DISTINCT p.block_id) block_count "
        "FROM phenology_observations p JOIN seasons s ON s.id=p.season_id "
        "WHERE p.estate_id=%s AND s.vintage_year=%s GROUP BY p.stage_code,p.stage_name,p.observed_date,p.percent_complete "
        "ORDER BY p.observed_date DESC,p.created_at DESC LIMIT 1",
        (estate_id(), year),
    ) or {} if crop_scope == "vineyard" else {}
    calendars = {
        "vineyard": {1: "dormant", 2: "dormant", 3: "budbreak", 4: "shoot_growth", 5: "flowering", 6: "fruit_set", 7: "bunch_closure", 8: "veraison", 9: "ripening", 10: "post_harvest", 11: "post_harvest", 12: "dormant"},
        "olives": {1: "olive_dormant", 2: "olive_dormant", 3: "olive_budbreak", 4: "olive_flowering", 5: "olive_flowering", 6: "olive_fruit_set", 7: "olive_pit_hardening", 8: "olive_pit_hardening", 9: "olive_ripening", 10: "olive_ripening", 11: "olive_post_harvest", 12: "olive_dormant"},
    }
    historical = year < date.today().year
    calendar_stage = calendars[crop_scope].get(date.today().month)
    stage_code = str(latest_stage.get("stage_code") or calendar_stage)
    stage_source = "historical_complete" if historical else "recorded_phenology" if latest_stage.get("stage_code") else "calendar_fallback"
    product_names = sorted({
        str(name) for row in rows
        for name in (json.loads(row.get("product_review_json") or "[]") if isinstance(row.get("product_review_json"), str) else row.get("product_review_json") or [])
    })
    products: dict[str, dict[str, Any]] = {}
    if product_names:
        placeholders = ",".join(["%s"] * len(product_names))
        product_rows = fetch_all(
            "SELECT p.name,p.product_type,p.unit,COALESCE(m.stock_on_hand,0) stock_on_hand,"
            "u.mixture_roles,u.selection_conditions,"
            "MAX(r.verification_status) verification_status,MAX(r.estate_authorization_status) estate_authorization_status "
            "FROM products p LEFT JOIN (SELECT product_id,SUM(quantity_delta) stock_on_hand FROM inventory_movements GROUP BY product_id) m ON m.product_id=p.id "
            "LEFT JOIN (SELECT product_id,GROUP_CONCAT(DISTINCT mixture_role ORDER BY mixture_role) mixture_roles,"
            "GROUP_CONCAT(DISTINCT NULLIF(selection_conditions,'') SEPARATOR ' | ') selection_conditions "
            "FROM treatment_product_options WHERE estate_id=%s AND crop_scope=%s AND active=1 GROUP BY product_id) u ON u.product_id=p.id "
            "LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 "
            f"WHERE p.estate_id=%s AND p.name IN ({placeholders}) GROUP BY p.id,p.name,p.product_type,p.unit,m.stock_on_hand,u.mixture_roles,u.selection_conditions",
            (estate_id(), crop_scope, estate_id(), *product_names),
        )
        products = {str(row["name"]): row for row in product_rows}
    phases: list[dict[str, Any]] = []
    for row in rows:
        names = json.loads(row.get("product_review_json") or "[]") if isinstance(row.get("product_review_json"), str) else row.get("product_review_json") or []
        reviews = []
        for name in names:
            product = products.get(str(name))
            reviews.append({
                "product_name": name,
                "catalog_status": "reviewable" if product else "missing_from_catalog",
                "stock_on_hand": _number((product or {}).get("stock_on_hand")) or 0,
                "stock_unit": (product or {}).get("unit"),
                "roles": str((product or {}).get("mixture_roles") or "").split(",") if product else [],
                "verification_status": (product or {}).get("verification_status"),
                "estate_authorization_status": (product or {}).get("estate_authorization_status"),
                "selection_conditions": (product or {}).get("selection_conditions"),
            })
        phases.append({
            **row,
            "current": not historical and str(row.get("stage_code")) == stage_code,
            "product_reviews": reviews,
            "product_review_json": None,
        })
    return {
        "year": year,
        "crop_scope": crop_scope,
        "historical_complete": historical,
        "current_stage": stage_code,
        "stage_source": stage_source,
        "latest_phenology": latest_stage or None,
        "phases": phases,
        "missing_catalog_products": [name for name in product_names if name not in products],
        "rule": "This is an annual evidence-and-review baseline, not a standing fertilizer prescription. A product is proposed only after a documented need, current crop directions, stock review and Agronomist approval. Any application is calculated, weather-cleared, approved and completed in Treatments.",
    }


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


def build_one_pass_treatment_plan(
    *, water_l: float, batches: list[dict[str, float]], components: list[dict[str, Any]]
) -> dict[str, Any]:
    """Present the estate workflow as one carrier pass split across identical fills.

    Product eligibility is decided before this function is called.  This helper
    does not add optional products and does not assert tank compatibility; it
    makes the calculated, evidence-supported program operationally readable.
    """
    ordered = sorted(
        components,
        key=lambda item: (
            _number(item.get("mixing_position")) is None,
            _number(item.get("mixing_position")) or 999,
            str(item.get("product_name") or ""),
        ),
    )
    recipe = calculate_batch_recipe(batches, ordered)
    unresolved = [
        str(item.get("product_name") or "")
        for item in ordered
        if item.get("application_relationship") not in {"primary_pass", "same_tank_verified"}
    ]
    capacity = max((_number(row.get("water_l")) or 0 for row in batches), default=0)
    return {
        "application_passes": 1,
        "whole_vineyard_pass": True,
        "total_carrier_l": round(water_l, 1),
        "batch_count": len(batches),
        "batch_capacity_l": round(capacity, 1) if capacity else None,
        "same_recipe_each_batch": bool(batches) and len({row.get("water_l") for row in batches}) == 1,
        "products": ordered,
        "batch_recipe": recipe,
        "mix_status": "exact_mix_review_required" if unresolved else "ready_for_final_agronomist_review",
        "compatibility_review_products": unresolved,
        "process_summary": (
            f"One pass over the whole vineyard using {water_l:g} L total carrier, "
            f"prepared as {len(batches)} × {capacity:g} L batches."
            if batches and capacity else
            f"One pass over the whole vineyard using {water_l:g} L total carrier; configure the sprayer fill size."
        ),
        "necessity_rule": "Only products supported by the selected issue or independently moderate-or-higher current pressure are included. Inventory or prior use alone never creates a recommendation.",
    }


def treatment_program_similarity(actual: list[str], predicted: list[str]) -> dict[str, Any]:
    """Score a complete-program comparison without rewarding duplicate names."""
    actual_set = {str(name).strip().casefold() for name in actual if str(name).strip()}
    predicted_set = {str(name).strip().casefold() for name in predicted if str(name).strip()}
    overlap = actual_set & predicted_set
    union = actual_set | predicted_set
    return {
        "agreement_count": len(overlap),
        "actual_count": len(actual_set),
        "predicted_count": len(predicted_set),
        "recall_pct": round(100 * len(overlap) / len(actual_set), 1) if actual_set else 0.0,
        "precision_pct": round(100 * len(overlap) / len(predicted_set), 1) if predicted_set else 0.0,
        "similarity_pct": round(100 * len(overlap) / len(union), 1) if union else 100.0,
    }


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def treatment_weather_similarity(current: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    """Compare weather regimes on agronomically meaningful, bounded scales."""
    scales = {
        "temp_avg_c": 10.0,
        "temp_max_c": 12.0,
        "humidity_avg_pct": 30.0,
        "rain_72h_mm": 25.0,
        "rain_7d_mm": 50.0,
        "soil_moisture_avg_pct": 35.0,
    }
    comparisons = []
    for key, scale in scales.items():
        left, right = _number(current.get(key)), _number(historical.get(key))
        if left is None or right is None:
            continue
        similarity = max(0.0, 1 - min(abs(left - right) / scale, 1.0))
        comparisons.append({"metric": key, "current": left, "historical": right, "similarity": similarity})
    score = round(100 * sum(row["similarity"] for row in comparisons) / len(comparisons), 1) if comparisons else None
    return {"similarity_pct": score, "comparable_metrics": len(comparisons), "metrics": comparisons}


def select_agronomist_program_analog(
    programs: list[dict[str, Any]], *, scenario_day: date, event_type: str = "none",
    exclude_id: str | None = None, weather_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Choose the closest complete Agronomist program, led by weather fit."""
    candidates = [row for row in programs if str(row.get("id") or "") != str(exclude_id or "")]
    if not candidates:
        return None
    event = str(event_type or "none").casefold()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in candidates:
        applied = _day(row.get("application_date"))
        if not applied:
            continue
        day_gap = abs((scenario_day - applied).days)
        month_gap = abs(scenario_day.month - applied.month)
        score = 100 - min(day_gap, 100) - month_gap * 18
        if scenario_day.month == applied.month:
            score += 55
        weather_match = treatment_weather_similarity(
            weather_context or {}, _json_mapping(row.get("learning_weather_snapshot"))
        )
        if weather_match.get("similarity_pct") is not None and weather_match.get("comparable_metrics", 0) >= 3:
            # Weather is the primary rationale. Calendar position preserves
            # phenological context when weather regimes are similarly close.
            score += float(weather_match["similarity_pct"]) * 1.5
        if event in {"hail", "visible_symptoms"}:
            # For a new event, the immediately preceding full program is the
            # relevant re-protection basis. Treatment 5 confirms this behavior
            # by repeating Treatment 4 after the June 26 hailstorm.
            score += 45 if applied <= scenario_day else 0
        scored.append((score, {**row, "weather_match": weather_match}))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], abs((scenario_day - _day(item[1]["application_date"])).days)))
    return {**scored[0][1], "analog_score": round(scored[0][0], 1)}


def _historical_rate_total(dose: Any, dose_unit: Any, water_l: float) -> tuple[float | None, str | None]:
    value = _number(dose)
    unit = str(dose_unit or "").strip()
    if value is None:
        return None, None
    factor = water_l / 100
    if unit == "g/100 L":
        return round(value * factor / 1000, 3), "kg"
    if unit == "ml/100 L":
        return round(value * factor / 1000, 3), "L"
    if unit == "kg/100 L":
        return round(value * factor, 3), "kg"
    if unit == "L/100 L":
        return round(value * factor, 3), "L"
    return None, None


def _agronomist_programs() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT a.id,a.purpose,a.application_date,a.water_volume_l,a.source_reference,a.source_instructions,a.notes,"
        "l.weather_snapshot learning_weather_snapshot,l.pressure_snapshot learning_pressure_snapshot,l.rationale_summary learning_rationale,l.model_version learning_model_version,l.learning_status,"
        "d.disposition safety_disposition,d.safe_for_prediction_reuse,"
        "i.dose_amount,i.dose_unit,p.name product_name,p.product_type,p.active_ingredient,p.unit stock_unit,"
        "r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.eligible_for_projection,r.mixing_position,r.mixing_instructions,r.compatibility_notes,"
        "(SELECT GROUP_CONCAT(DISTINCT u.target_code ORDER BY u.target_code) FROM product_authorized_uses u WHERE u.product_id=p.id AND u.crop_scope='vineyard' AND u.active=1) authorized_targets,"
        "(SELECT GROUP_CONCAT(DISTINCT o.mixture_role ORDER BY o.mixture_role) FROM treatment_product_options o WHERE o.product_id=p.id AND o.crop_scope='vineyard' AND o.active=1) mixture_roles "
        "FROM spray_applications a JOIN spray_application_items i ON i.application_id=a.id JOIN products p ON p.id=i.product_id "
        "LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 "
        "LEFT JOIN treatment_weather_learning_cases l ON l.application_id=a.id "
        "LEFT JOIN treatment_safety_dispositions d ON d.application_id=a.id AND d.estate_id=a.estate_id "
        "WHERE a.estate_id=%s AND a.crop_scope='vineyard' AND a.status IN ('completed','applied') "
        "AND a.actual_details_confirmed=1 "
        "ORDER BY a.application_date,a.id,COALESCE(r.mixing_position,999),p.name",
        (estate_id(),),
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        program = grouped.setdefault(str(row["id"]), {
            "id": row["id"], "purpose": row.get("purpose"), "application_date": row.get("application_date"),
            "water_volume_l": row.get("water_volume_l"), "source_reference": row.get("source_reference"),
            "source_instructions": row.get("source_instructions"), "notes": row.get("notes"),
            "learning_weather_snapshot": row.get("learning_weather_snapshot"),
            "learning_pressure_snapshot": row.get("learning_pressure_snapshot"),
            "learning_rationale": row.get("learning_rationale"),
            "learning_model_version": row.get("learning_model_version"),
            "learning_status": row.get("learning_status"),
            "safety_disposition": row.get("safety_disposition"),
            "safe_for_prediction_reuse": bool(row.get("safe_for_prediction_reuse")), "items": [],
        })
        program["items"].append({key: value for key, value in row.items() if key not in {"id", "purpose", "application_date", "water_volume_l", "source_reference", "source_instructions", "notes", "learning_weather_snapshot", "learning_pressure_snapshot", "learning_rationale", "learning_model_version", "learning_status", "safety_disposition", "safe_for_prediction_reuse"}})
    return list(grouped.values())


def agronomist_program_backtest(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Leave one treatment out and test whether the remaining history predicts it."""
    rows: list[dict[str, Any]] = []
    for actual in programs:
        actual_day = _day(actual.get("application_date"))
        if not actual_day:
            continue
        analog = select_agronomist_program_analog(
            programs, scenario_day=actual_day, exclude_id=str(actual.get("id") or ""),
            weather_context=_json_mapping(actual.get("learning_weather_snapshot")),
        )
        if not analog:
            continue
        score = treatment_program_similarity(
            [item.get("product_name") for item in actual.get("items") or []],
            [item.get("product_name") for item in analog.get("items") or []],
        )
        rows.append({
            "actual_treatment": actual.get("purpose"),
            "predicted_from": analog.get("purpose"),
            **score,
        })
    return {
        "replays": rows,
        "replay_count": len(rows),
        "exact_program_count": sum(
            1 for row in rows if row["recall_pct"] == 100 and row["precision_pct"] == 100
        ),
        "average_recall_pct": round(
            sum(row["recall_pct"] for row in rows) / len(rows), 1
        ) if rows else 0.0,
        "method": "Leave-one-treatment-out comparison; the treatment being scored is never used as its own prediction.",
    }


def agronomist_pattern_program(
    *, prediction: dict[str, Any], water_l: float, stock_by_product: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Build a current, review-gated program from complete Agronomist analogs."""
    scenario_day = _day(prediction.get("scenario_date")) or date.today()
    target = str(prediction.get("scenario_target_code") or prediction.get("target_code") or "").casefold()
    event = str(prediction.get("event_type") or "none").casefold()
    seasonality = prediction.get("seasonality") or {}
    risk_rank = _RISK_RANK.get(str(prediction.get("current_risk_level") or "unknown").casefold(), 0)
    if target not in {"downy_mildew", "powdery_mildew", "hail_wound_followup"}:
        return None
    if not (
        event in {"hail", "visible_symptoms"}
        or risk_rank >= _RISK_RANK["moderate"]
        or prediction.get("historical_replay")
    ):
        return None
    if not seasonality.get("supports_program_review", False) or seasonality.get("stage_fit") == "stage outside typical window":
        return None
    programs = _agronomist_programs()
    actual = next((row for row in programs if _day(row.get("application_date")) == scenario_day), None) if prediction.get("historical_replay") else None
    assessment = prediction.get("weather_assessment") if isinstance(prediction.get("weather_assessment"), dict) else {}
    current_weather = _json_mapping(assessment.get("input_snapshot"))
    if not current_weather and actual:
        current_weather = _json_mapping(actual.get("learning_weather_snapshot"))
    analog = select_agronomist_program_analog(
        programs, scenario_day=scenario_day, event_type=event,
        exclude_id=(actual or {}).get("id"), weather_context=current_weather,
    )
    if not analog:
        return None
    analog_day = _day(analog.get("application_date"))
    month_gap = abs(scenario_day.month - analog_day.month) if analog_day else 99
    if month_gap > 2 and event not in {"hail", "visible_symptoms"}:
        return None
    signatures: dict[tuple[str, ...], int] = {}
    product_frequency: dict[str, int] = {}
    for program in programs:
        signature = tuple(sorted(str(item.get("product_name") or "") for item in program.get("items") or []))
        signatures[signature] = signatures.get(signature, 0) + 1
        for name in set(signature):
            product_frequency[name] = product_frequency.get(name, 0) + 1
    analog_signature = tuple(sorted(str(item.get("product_name") or "") for item in analog.get("items") or []))
    components: list[dict[str, Any]] = []
    program_objectives: set[str] = set()
    for item in analog.get("items") or []:
        name = str(item.get("product_name") or "")
        total, total_unit = _historical_rate_total(item.get("dose_amount"), item.get("dose_unit"), water_l)
        stock = stock_by_product.get(name) or {}
        roles = {value for value in str(item.get("mixture_roles") or "").split(",") if value}
        authorized_targets = {
            value.replace("_", " ") for value in str(item.get("authorized_targets") or "").split(",") if value
        }
        if item.get("product_type") == "plant_protection":
            role = "disease control" + (f" ({', '.join(sorted(authorized_targets))})" if authorized_targets else "")
        elif "nutrition" in roles:
            role = "foliar nutrition"
        elif "stress_support" in roles or "plant_defense_support" in roles:
            role = "stress / plant-defense support"
        else:
            role = "support"
        program_objectives.add(role)
        current_ready = _profile_ready(item)
        trigger = (
            "the documented hail/stress event and the Agronomist's Treatment 4→5 re-protection pattern"
            if event in {"hail", "visible_symptoms"} else
            f"the selected {target.replace('_', ' ')} scenario, {seasonality.get('calendar_fit') or 'seasonal window'}, and the closest complete Agronomist program"
        )
        repeated = product_frequency.get(name, 0)
        recorded_rate = _number(item.get("dose_amount"))
        rate_text = f"{recorded_rate:g}" if recorded_rate is not None else "unrecorded"
        components.append({
            "product_name": name, "active_ingredient": item.get("active_ingredient"),
            "purpose": role, "program_role": f"Agronomist pattern · {role}",
            "rate": _number(item.get("dose_amount")), "rate_unit": item.get("dose_unit"),
            "total": total, "total_unit": total_unit,
            "purchase_state": "in_stock" if (_number(stock.get("stock_on_hand")) or 0) >= (total or 0) else "insufficient_stock",
            "stock_on_hand": _number(stock.get("stock_on_hand")) or 0, "stock_unit": stock.get("unit") or item.get("stock_unit"),
            "mixing_position": item.get("mixing_position"), "mixing_sequence": item.get("mixing_instructions"),
            "compatibility_notes": item.get("compatibility_notes"),
            "application_relationship": "agronomist_pattern_exact_mix_review",
            "current_profile_ready": current_ready,
            "selection_reason": f"Included because of {trigger}. {name} appears in {repeated} of {len(programs)} completed weather-learning cases; this recipe uses the Agronomist's recorded {rate_text} {item.get('dose_unit') or 'rate unit missing'} rate, recalculated for {water_l:g} L.",
        })
    validation = treatment_program_similarity(
        [item.get("product_name") for item in (actual or {}).get("items") or []],
        [item.get("product_name") for item in analog.get("items") or []],
    ) if actual else None
    return {
        "basis_treatment_id": analog.get("id"), "basis_treatment": analog.get("purpose"),
        "basis_date": analog_day, "basis_source": analog.get("source_reference"),
        "basis_water_l": _number(analog.get("water_volume_l")), "current_water_l": water_l,
        "program_repeat_count": signatures.get(analog_signature, 1),
        "confidence": "high" if signatures.get(analog_signature, 1) >= 2 and (_number((analog.get("weather_match") or {}).get("similarity_pct")) or 0) >= 70 else "medium",
        "program_objectives": sorted(program_objectives),
        "learning_case_count": len(programs),
        "weather_match": analog.get("weather_match"),
        "weather_rationale": analog.get("learning_rationale"),
        "learning_model_version": analog.get("learning_model_version") or "weather-treatment-learning-v1",
        "learning_status": analog.get("learning_status") or "awaiting_weather_backfill",
        "historical_safety_disposition": analog.get("safety_disposition"),
        "safe_for_prescription_reuse": bool(analog.get("safe_for_prediction_reuse")),
        "components": components, "historical_validation": validation,
        "model_validation": agronomist_program_backtest(programs),
        "actual_treatment": (actual or {}).get("purpose"),
        "reason_status": "documented_event_plus_pattern" if event == "hail" else "inferred_from_timing_products_and_repetition",
        "reason_note": (
            "The June 26 hail trigger is documented; the complete Treatment 4 recipe was explicitly repeated as Treatment 5."
            if event == "hail" else
            "The exact Agronomist rationale was not recorded for Treatments 2–4. Product roles, timing and repetition support this inference; the Agronomist must confirm it before application."
        ),
        "explanation": "The complete Agronomist program with the closest pre-treatment weather regime is selected first; event, seasonal phase and date resolve similar weather matches. Historical rates are scaled to the current 400 L process; every product still requires a current-need and safety review.",
    }


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
        "target_code": row.get("target_code"),
        "mixture_role": row.get("mixture_role"),
        "active_ingredient": row.get("active_ingredient"),
        "concentrate_form": row.get("concentrate_form"),
        "final_application_medium": row.get("final_application_medium"),
        "verification_status": row.get("verification_status"),
        "purchase_state": "stock_unreconciled" if stock.get("stock_reconciled") is False else "in_stock" if (_number(stock.get("stock_on_hand")) or 0) > 0 else "not_in_stock",
        # A delayed supplier invoice can legitimately leave the running ledger
        # negative.  Preserve that evidence instead of presenting a false zero;
        # the later receipt will net against completed use automatically.
        "stock_on_hand": _number(stock.get("stock_on_hand")) or 0,
        "stock_unit": stock.get("unit") or row.get("measure_unit"),
        "decision": decision,
        "reason": reason,
        "selection_conditions": row.get("selection_conditions"),
        "compatibility_status": compatibility,
        "compatibility_conditions": row.get("compatibility_conditions"),
        "mixing_position": row.get("mixing_position"),
        "mixing_instructions": row.get("mixing_instructions"),
        "projected_quantity": quantity,
    }


_RISK_RANK = {"unknown": 0, "trace": 1, "low": 2, "moderate": 3, "high": 4, "critical": 5}


def _support_program_selection(
    reviews: list[dict[str, Any]], prediction: dict[str, Any]
) -> list[dict[str, Any]]:
    """Select defensible support reviews without inventing a nutritional need.

    A disease model may justify reviewing a support product, but it cannot turn
    a fertilizer or biostimulant into disease control and it cannot establish
    tank compatibility.  Target-specific, verified, conditionally compatible
    support products rank ahead of estate-wide options.  Nutrition products are
    retained for review unless the scenario explicitly describes hail, heat or
    visible stress.
    """
    risk_level = str(prediction.get("current_risk_level") or prediction.get("risk_level") or "unknown").casefold()
    risk_rank = _RISK_RANK.get(risk_level, 0)
    target = str(prediction.get("target_code") or "").casefold()
    scenario_target = str(prediction.get("scenario_target_code") or target).casefold()
    event = str(prediction.get("event_type") or "none").casefold()
    stress_event = event in {"hail", "heat", "visible_symptoms"} or scenario_target == "hail_wound_followup"
    if risk_rank < _RISK_RANK["moderate"] and not stress_event:
        return []
    seasonality = prediction.get("seasonality") or {}
    if seasonality and not seasonality.get("supports_program_review", True) and not stress_event:
        return []

    growth_stage = str(
        ((prediction.get("historical_context") or {}).get("effective_growth_stage"))
        or prediction.get("growth_stage") or ""
    ).strip().casefold()
    nutrition_signal = stress_event
    eligible: list[tuple[int, dict[str, Any]]] = []
    for row in reviews:
        if str(row.get("decision") or "").startswith("blocked") or row.get("decision") == "not_selected" and row.get("mixture_role") == "nutrition" and not nutrition_signal:
            continue
        role = str(row.get("mixture_role") or "support")
        if role == "nutrition" and not nutrition_signal:
            continue
        if role not in {"support", "adjuvant", "nutrition"}:
            continue
        quantity = row.get("projected_quantity") or {}
        if quantity.get("minimum") is None:
            continue
        compatibility = str(row.get("compatibility_status") or "not_verified")
        # Prefer an exact target row and a conditional/verified compatibility
        # basis.  An unverified product remains visible in the review list but
        # is not promoted into the calculated program.
        if compatibility not in {"verified_compatible", "conditional"} and role != "nutrition":
            continue
        score = (3 if str(row.get("target_code") or target).casefold() == target else 1)
        score += 2 if compatibility == "verified_compatible" else 1
        score += 1 if role in {"support", "adjuvant"} else 0
        product_name = str(row.get("product_name") or "")
        # Weather-derived disease pressure alone cannot establish a need for a
        # silica gel, inducer, biostimulant or adjuvant. Keep these visible in
        # the review list, but promote them only for documented stress or
        # visible symptoms. Prior use and inventory are never a reason to spray.
        if role in {"support", "adjuvant"} and not stress_event:
            continue
        score += {"GEL DI SILICE": 4, "REPENTE": 3, "RESOLVE": 2}.get(product_name.upper(), 0)
        eligible.append((score, row))
    if not eligible:
        return []
    eligible.sort(key=lambda item: (-item[0], str(item[1].get("product_name") or "")))
    chosen = eligible[:1]
    result: list[dict[str, Any]] = []
    for _, source in chosen:
        selected = dict(source)
        quantity = selected.get("projected_quantity") or {}
        minimum = _number(quantity.get("minimum"))
        maximum = _number(quantity.get("maximum"))
        if minimum is not None:
            maximum = maximum if maximum is not None else minimum
            fraction = 1.0 if risk_rank >= _RISK_RANK["critical"] else .5 if risk_rank >= _RISK_RANK["high"] else 0.0
            selected_total = minimum + (maximum - minimum) * fraction
            selected["selected_total"] = round(selected_total, 3)
            selected["selected_unit"] = quantity.get("unit")
        same_tank = selected.get("compatibility_status") == "verified_compatible"
        selected["application_relationship"] = "same_tank_verified" if same_tank else "separate_pass_or_agronomist_mix_review"
        if selected.get("mixture_role") == "nutrition":
            selected["selection_reason"] = (
                f"Nutrition review is supported by the {growth_stage.replace('_', ' ') or 'recorded'} growth stage "
                + "and a documented stress event."
                + " It is a separate nutritional/biostimulant decision, not disease control; confirm the current field need and exact compatibility."
            )
        else:
            selected["selection_reason"] = (
                f"{risk_level.title()} {target.replace('_', ' ')} pressure supports a field review of this "
                f"{selected.get('mixture_role') or 'support'} product; seasonal screening is "
                f"{str(seasonality.get('calendar_fit') or 'not available')}"
                + "."
                + " It is not a substitute for the primary disease-control product."
            )
        result.append(selected)
    return result


def _additional_disease_controls(
    *, crop_scope: str, prediction: dict[str, Any], primary_target: str,
    area_ha: float, water_l: float, stock_by_product: dict[str, dict[str, Any]],
    authorization_reference_day: date,
) -> list[dict[str, Any]]:
    """Calculate one separate-pass control for each independently supported target.

    The selected scenario remains the primary target. Other diseases enter the
    program only when their stored same-date pressure is moderate or worse and
    the date/growth stage is within that disease's seasonal window. This keeps
    weather, disease pressure, phenology and treatment selection connected
    without turning a historical recipe into a recommendation.
    """
    context = prediction.get("historical_context") or {}
    stage = str(context.get("effective_growth_stage") or "").strip().casefold()
    scenario_day = _day(prediction.get("scenario_date")) or date.today()
    controls: list[dict[str, Any]] = []
    seen_products: set[str] = set()
    for pressure in context.get("pressure_screen") or []:
        target = str(pressure.get("disease_code") or "").strip().casefold()
        score = _number(pressure.get("risk_score")) or 0
        level = str(pressure.get("risk_level") or "low").strip().casefold()
        if target == primary_target or target not in _TREATMENT_SEASONALITY:
            continue
        if score < 45 and level not in {"moderate", "high", "critical"}:
            continue
        rules = _TREATMENT_SEASONALITY.get(target) or {}
        stage_ok = not stage or not rules.get("stages") or stage in set(rules.get("stages") or ())
        date_ok = scenario_day.month in set(rules.get("active_months") or ()) | set(rules.get("shoulder_months") or ())
        if not (stage_ok and date_ok):
            continue
        uses = fetch_all(
            "SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit,"
            "r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,"
            "r.eligible_for_projection,r.compatibility_notes,r.mixing_position,r.mixing_instructions "
            "FROM product_authorized_uses u JOIN products p ON p.id=u.product_id "
            "LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 "
            "WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 "
            "ORDER BY (u.authorization_status='authorized') DESC,u.label_verified_on DESC,p.name",
            (estate_id(), crop_scope, target),
        )
        candidates = [
            row for row in uses
            if row.get("authorization_status") in {"authorized", "expired"}
            and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= authorization_reference_day)
            and _profile_ready(row)
            and str(row.get("product_name") or "").casefold() not in seen_products
        ]
        if not candidates:
            continue
        candidate = candidates[0]
        rate = _risk_rate(candidate, {"current_risk_level": level, "risk_level": level})
        if not rate or str(candidate.get("dose_unit") or "") not in {"kg/ha", "L/ha"}:
            continue
        calculated = reconcile_area_and_water_rate(
            area_ha=area_ha, water_l=water_l, selected_rate=rate,
            minimum_rate=_number(candidate.get("min_dose")) or rate,
            maximum_rate=_number(candidate.get("max_dose")) or rate,
            rate_unit=str(candidate.get("dose_unit") or ""),
            water_rate_min=_number(candidate.get("water_rate_min")),
            water_rate_max=_number(candidate.get("water_rate_max")),
            water_rate_unit=candidate.get("water_rate_unit"),
        )
        if not calculated.get("valid"):
            continue
        name = str(candidate.get("product_name") or "")
        stock = stock_by_product.get(name) or {}
        total_unit = str(calculated.get("total_unit") or "")
        controls.append({
            "product_name": name,
            "active_ingredient": candidate.get("active_ingredient"),
            "purpose": candidate.get("target_name") or target.replace("_", " "),
            "program_role": f"secondary disease control · {target.replace('_', ' ')}",
            "total": calculated.get("total"), "total_unit": total_unit,
            "per_100_l": calculated.get("per_100_l"),
            "per_100_l_unit": calculated.get("per_100_l_unit"),
            "rate": calculated.get("effective_rate_per_ha"), "rate_unit": candidate.get("dose_unit"),
            "stock_on_hand": _number(stock.get("stock_on_hand")) or 0,
            "stock_unit": stock.get("unit") or candidate.get("unit"),
            "purchase_state": "receipt_pending" if (_number(stock.get("ledger_balance")) or 0) < 0 else "in_stock" if (_number(stock.get("stock_on_hand")) or 0) >= (_number(calculated.get("total")) or 0) else "insufficient_stock",
            "phi_days": int(candidate.get("phi_days") or 0),
            "application_relationship": "separate_pass_pending_exact_mix_review",
            "selection_reason": (
                f"Same-date {target.replace('_', ' ')} pressure is {score:.1f} ({level}); "
                f"{scenario_day.strftime('%B')} and {stage.replace('_', ' ') or 'the recorded stage'} are within its review window. "
                "Keep as a separate homogeneous pass unless exact tank compatibility is approved."
            ),
            "compatibility_notes": candidate.get("compatibility_notes"),
            "mixing_position": candidate.get("mixing_position"),
            "mixing_sequence": candidate.get("mixing_instructions"),
        })
        seen_products.add(name.casefold())
    return controls


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


def product_guidance(crop_scope: str, prediction: dict[str, Any], *, forecast: list[dict[str, Any]] | None = None, planning_water_l: float = 400.0, equipment_selector: str | None = None, planning_area_ha: float | None = None) -> dict[str, Any]:
    """Build a fully calculated proposal while retaining legal and human approval gates."""
    if forecast is None:
        from ..display_data import weather_context_payload
        forecast = weather_context_payload().get("forecast") or []
    target_code = str(prediction.get("target_code") or "").strip()
    scenario_day = _day(prediction.get("scenario_date"))
    authorization_reference_day = scenario_day if prediction.get("historical_replay") and scenario_day else date.today()
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
        "SUM(i.quantity_delta) stock_on_hand "
        "FROM products p JOIN inventory_movements i ON i.product_id=p.id "
        "WHERE p.estate_id=%s GROUP BY p.id,p.name,p.unit",
        (estate_id(),),
    )
    stock_by_product = {str(row["product_name"]): row for row in stock_rows}
    inventory_reconciliation = treatment_inventory_reconciliation(date.today().year)
    unresolved_products = {str(row.get("product_name") or "") for row in inventory_reconciliation["issues"]}
    for product_name, stock in stock_by_product.items():
        stock["stock_reconciled"] = product_name not in unresolved_products
    reference_catalog = fetch_all("SELECT p.name product_name,p.product_type,p.active_ingredient,p.registration_number,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.density_kg_l,r.density_min_kg_l,r.density_max_kg_l,r.density_source,r.label_verified_on,r.label_url,r.eligible_for_projection,(SELECT COUNT(*) FROM treatment_product_evidence ev WHERE ev.product_id=p.id) evidence_count FROM treatment_product_profiles r JOIN products p ON p.id=r.product_id WHERE r.estate_id=%s AND r.active=1 AND p.active=1 ORDER BY p.name", (estate_id(),))
    purchase_summary = [{"product_name": name, "quantity": round(sum(_number(row.get("quantity_total")) or 0 for row in lines), 3), "unit": lines[0].get("quantity_unit"), "stock_on_hand": round(_number((stock_by_product.get(name) or {}).get("stock_on_hand")) or 0, 3), "stock_unit": (stock_by_product.get(name) or {}).get("unit") or lines[0].get("quantity_unit"), "stock_reconciled": name not in unresolved_products and not any("[STOCK REVIEW]" in str(row.get("notes") or "") for row in lines), "invoice_numbers": list(dict.fromkeys(str(row.get("invoice_number")) for row in lines)), "treatment_relevance": lines[0].get("treatment_relevance")} for name, lines in purchase_by_product.items()]
    non_treatment = [row for row in purchases if row.get("treatment_relevance") == "not_treatment"]
    if not target_code:
        return {"status": "waiting_for_target", "target_code": None, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "message": "No current target is supported. Purchased products are inventory evidence, not a reason to spray."}

    uses_sql = "SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.density_kg_l,r.density_min_kg_l,r.density_max_kg_l,r.density_source,r.mixing_position,r.mixing_instructions,r.compatibility_notes,r.water_quality_notes,r.eligible_for_projection FROM product_authorized_uses u JOIN products p ON p.id=u.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 ORDER BY (u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE())) DESC,u.label_verified_on DESC,p.name"
    requested_target_code = target_code
    uses = fetch_all(uses_sql, (estate_id(), crop_scope, target_code))
    candidates = [
        row for row in uses
        if (
            row.get("authorization_status") == "authorized"
            or (
                prediction.get("historical_replay")
                and row.get("authorization_status") == "expired"
                and _day(row.get("authorization_expires_on"))
                and _day(row.get("authorization_expires_on")) >= authorization_reference_day
            )
        )
        and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= authorization_reference_day)
        and _profile_ready(row)
    ]
    blocked_products = [{"product_name": row.get("product_name"), "reason": _profile_block_reason(row) if row.get("authorization_status") == "authorized" else f"Authorization status: {row.get('authorization_status')}; expiry {row.get('authorization_expires_on') or 'not recorded'}."} for row in uses if row not in candidates]
    fallback_target_code = None
    if not candidates:
        context = prediction.get("historical_context") or {}
        stage = str(context.get("effective_growth_stage") or "").strip().casefold()
        scenario_day_for_fit = scenario_day or date.today()
        pressure_rows = sorted(context.get("pressure_screen") or [], key=lambda row: -(_number(row.get("risk_score")) or 0))
        for pressure in pressure_rows:
            alternate = str(pressure.get("disease_code") or "").strip().casefold()
            level = str(pressure.get("risk_level") or "low").strip().casefold()
            score = _number(pressure.get("risk_score")) or 0
            rules = _TREATMENT_SEASONALITY.get(alternate) or {}
            stage_ok = not stage or not rules.get("stages") or stage in set(rules.get("stages") or ())
            date_ok = scenario_day_for_fit.month in set(rules.get("active_months") or ()) | set(rules.get("shoulder_months") or ())
            if alternate == requested_target_code or alternate not in _TREATMENT_SEASONALITY:
                continue
            if score < 45 and level not in {"moderate", "high", "critical"}:
                continue
            if not (stage_ok and date_ok):
                continue
            alternate_uses = fetch_all(uses_sql, (estate_id(), crop_scope, alternate))
            alternate_candidates = [
                row for row in alternate_uses
                if (
                    row.get("authorization_status") == "authorized"
                    or (
                        prediction.get("historical_replay")
                        and row.get("authorization_status") == "expired"
                        and _day(row.get("authorization_expires_on"))
                        and _day(row.get("authorization_expires_on")) >= authorization_reference_day
                    )
                )
                and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= authorization_reference_day)
                and _profile_ready(row)
            ]
            if alternate_candidates:
                fallback_target_code = alternate
                target_code = alternate
                uses = alternate_uses
                candidates = alternate_candidates
                blocked_products.extend({
                    "product_name": row.get("product_name"),
                    "reason": _profile_block_reason(row) if row.get("authorization_status") == "authorized" else f"Authorization status: {row.get('authorization_status')}; expiry {row.get('authorization_expires_on') or 'not recorded'}.",
                } for row in alternate_uses if row not in alternate_candidates)
                break
    if not candidates:
        return {"status": "no_verified_candidate", "target_code": target_code, "candidates": [], "mixture": None, "needed_list": [], "stock_review_list": stock_review_list, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "message": "No currently authorized crop-and-target product has a complete water-spray formulation reference. A current Italian label and formulation profile must be checked before calculation."}

    area_rows = fetch_all("SELECT code,name,area_ha FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),))
    estate_known_area = round(sum(_number(row.get("area_ha")) or 0 for row in area_rows), 3)
    supplied_area = _number(planning_area_ha)
    if supplied_area is not None and not 0 < supplied_area <= 1000:
        raise ValueError("Scenario treatment area must be greater than zero and no more than 1000 hectares")
    known_area = round(supplied_area, 3) if supplied_area is not None else estate_known_area
    missing_area_blocks = [] if supplied_area is not None else [row.get("code") for row in area_rows if _number(row.get("area_ha")) is None]
    area_note = "Hypothetical scenario area; confirm exact treated blocks." if supplied_area is not None else "All active blocks with known area; confirm exact treated blocks."
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
    rate_conflict = None
    if known_area and rate and dose_unit in {"kg/ha", "L/ha"}:
        reconciled_rate = reconcile_area_and_water_rate(
            area_ha=known_area, water_l=planning_water_l, selected_rate=rate,
            minimum_rate=_number(candidate.get("min_dose")) or rate,
            maximum_rate=_number(candidate.get("max_dose")) or rate,
            rate_unit=dose_unit,
            water_rate_min=_number(candidate.get("water_rate_min")),
            water_rate_max=_number(candidate.get("water_rate_max")),
            water_rate_unit=candidate.get("water_rate_unit"),
        )
        if reconciled_rate.get("valid"):
            calculation = {
                "area_ha": known_area, "water_l": planning_water_l,
                "total": reconciled_rate["total"], "total_unit": reconciled_rate["total_unit"],
                "rate_kg_ha" if dose_unit == "kg/ha" else "rate_l_ha": reconciled_rate["effective_rate_per_ha"],
                "per_100_l_g" if dose_unit == "kg/ha" else "per_100_l_ml": reconciled_rate["per_100_l"],
                "dual_rate_screen": reconciled_rate,
            }
        else:
            calculation = None
            rate_conflict = reconciled_rate.get("reason")
    else:
        calculation = None
    candidate_stock = stock_by_product.get(str(candidate.get("product_name"))) or {}
    ledger_balance = _number(candidate_stock.get("ledger_balance")) or 0
    stock_balance = _number(candidate_stock.get("stock_on_hand")) or 0
    required_quantity = _number(calculation.get("total")) if calculation else None
    candidate_name = str(candidate.get("product_name") or "")
    purchase_state = "stock_unreconciled" if candidate_name in unresolved_products else "receipt_pending" if ledger_balance < 0 else "in_stock" if stock_balance > 0 and (required_quantity is None or stock_balance >= required_quantity) else "insufficient_stock" if stock_balance > 0 else "suggested_purchase"
    window_weather = list(forecast or [])
    weather_evidence_kind = "forecast"
    if scenario_day and scenario_day < date.today():
        historical_days = fetch_all(
            "SELECT weather_date,temp_max_c,rain_mm,wind_max_kph FROM weather_daily "
            "WHERE estate_id=%s AND weather_date BETWEEN %s AND %s ORDER BY weather_date",
            (estate_id(), _day(prediction.get("window_start")) or scenario_day, _day(prediction.get("window_end")) or scenario_day),
        )
        window_weather = [{
            "date": row.get("weather_date"), "temperature_high": row.get("temp_max_c"),
            "precipitation": row.get("rain_mm"), "wind_speed_kph": row.get("wind_max_kph"),
        } for row in historical_days]
        weather_evidence_kind = "historical_observation"
    spray_window = select_application_window(
        window_weather, prediction.get("window_start"), prediction.get("window_end"),
        sulfur=str(candidate.get("active_ingredient") or "").casefold().startswith("sulfur"),
        evidence_kind=weather_evidence_kind,
    )
    phi_days = int(candidate.get("phi_days") or 0)
    recommended_day = _day(spray_window.get("recommended_date"))
    phi_ok = not (recommended_day and earliest_harvest and (earliest_harvest - recommended_day).days < phi_days)
    hard_blocks = ["Record a current block scouting observation and confirm the target before approval.", "Select the exact treated blocks; the scenario/estate area is only a planning basis.", f"Confirm the actual tank water volume; {planning_water_l:g} L is an adjustable planning value, not an application record.", "Agronomist must approve the product, rate, compatibility, sequence, PHI, REI, weather and PPE.", "Do not combine sulfur, copper, or any support product with another concentrate unless the database records verified compatibility for that exact mixture. Otherwise keep applications separate; where the current label permits it, complete an agronomist-approved jar test first."]
    if fallback_target_code:
        hard_blocks.insert(0, f"No verified product is available for {requested_target_code.replace('_', ' ')}; the calculated {fallback_target_code.replace('_', ' ')} pass addresses only that independently supported concurrent disease.")
    if rate_conflict:
        hard_blocks.append(rate_conflict + " Increase carrier water or select another label-compliant rate before review.")
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
    if purchase_state == "receipt_pending":
        hard_blocks.append(f"Recorded stock is {ledger_balance:g} {candidate.get('unit') or ''}; completed use has posted and a delayed purchase invoice or receipt is still pending. The ledger will net automatically when it arrives.")
    if purchase_state == "stock_unreconciled":
        hard_blocks.append(f"Completed use of {candidate.get('product_name')} has an unknown total or unresolved unit; its displayed balance and purchase quantity are provisional.")
    if not inventory_reconciliation["complete"]:
        hard_blocks.append(f"{inventory_reconciliation['unresolved_items']} completed-treatment product quantities still need inventory reconciliation; purchase advice is provisional until those exact totals are confirmed.")
    if not sprayer:
        hard_blocks.append("Select the water-spray equipment and record its tank capacity and calibration before approval." if not requested_equipment else f"Configured sprayer '{requested_equipment}' was not found among active spray-equipment profiles.")
    elif sprayer.get("calibration_status") != "verified":
        hard_blocks.append(f"{sprayer.get('name') or 'The sprayer'} has a documented nominal {sprayer_capacity:g} L tank but its usable fill, pump/nozzle setup and field calibration are not verified.")
    required_unit = calculation.get("total_unit") if calculation else candidate.get("unit")
    needed_list = ([{"product_name": candidate.get("product_name"), "required": required_quantity, "on_hand": round(stock_balance, 3), "needed": None, "unit": required_unit, "target": candidate.get("target_name"), "reason": "Exact purchase quantity is withheld until completed use with unknown totals or units is reconciled.", "purchase_state": purchase_state}] if purchase_state == "stock_unreconciled" else [] if required_quantity is None or stock_balance >= required_quantity else [{"product_name": candidate.get("product_name"), "required": required_quantity, "on_hand": round(stock_balance, 3), "needed": calculate_stock_shortage(required_quantity, stock_balance), "unit": required_unit, "target": candidate.get("target_name"), "reason": "Predicted requirement exceeds the current ledger balance; a negative balance means a delayed purchase receipt has not posted yet.", "purchase_state": purchase_state}])
    per_100_l = calculation.get("per_100_l_g") if calculation and calculation.get("per_100_l_g") is not None else calculation.get("per_100_l_ml") if calculation else None
    per_100_l_unit = "g/100 L" if calculation and calculation.get("per_100_l_g") is not None else "ml/100 L" if calculation and calculation.get("per_100_l_ml") is not None else None
    effective_rate = (
        calculation.get("rate_kg_ha") if calculation and dose_unit == "kg/ha" else
        calculation.get("rate_l_ha") if calculation and dose_unit == "L/ha" else rate
    )
    component = {"product_name": candidate.get("product_name"), "active_ingredient": candidate.get("active_ingredient"), "registration_number": candidate.get("registration_number"), "purpose": candidate.get("target_name"), "concentrate_form": candidate.get("concentrate_form"), "final_application_medium": candidate.get("final_application_medium"), "rate": effective_rate, "rate_unit": candidate.get("dose_unit"), "total": calculation.get("total") if calculation else None, "total_unit": calculation.get("total_unit") if calculation else None, "per_100_l": per_100_l, "per_100_l_unit": per_100_l_unit, "purchase_state": purchase_state, "stock_on_hand": stock_balance, "stock_unit": candidate.get("unit"), "phi_days": phi_days, "rei_hours": candidate.get("rei_hours"), "resistance_group": candidate.get("resistance_group"), "mixing_position": candidate.get("mixing_position"), "mixing_sequence": candidate.get("mixing_instructions"), "compatibility_notes": candidate.get("compatibility_notes"), "label_url": candidate.get("label_url")}
    batch_recipe = calculate_batch_recipe(batches, [component])
    option_rows = fetch_all("SELECT o.*,p.name product_name,p.active_ingredient,p.unit,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.mixing_position,r.mixing_instructions,r.compatibility_notes,r.eligible_for_projection FROM treatment_product_options o JOIN products p ON p.id=o.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE o.estate_id=%s AND o.crop_scope=%s AND o.target_code IN (%s,'any') AND o.mixture_role<>'primary' AND o.active=1 AND p.active=1 ORDER BY FIELD(o.default_decision,'candidate','blocked','not_selected'),p.name", (estate_id(), crop_scope, target_code))
    support_review = [_review_possible_product(row, stock_by_product, planning_water_l=planning_water_l, planning_area_ha=known_area) for row in option_rows]
    support_prediction = prediction
    if fallback_target_code:
        fallback_pressure = next((
            row for row in ((prediction.get("historical_context") or {}).get("pressure_screen") or [])
            if str(row.get("disease_code") or "").casefold() == fallback_target_code
        ), {})
        support_prediction = {
            **prediction,
            "target_code": fallback_target_code,
            "scenario_target_code": fallback_target_code,
            "current_risk_level": fallback_pressure.get("risk_level") or prediction.get("current_risk_level"),
            "current_risk_score": fallback_pressure.get("risk_score") or prediction.get("current_risk_score"),
            "seasonality": {
                **(prediction.get("seasonality") or {}),
                "calendar_fit": "active concurrent-disease window",
            },
        }
    selected_support = _support_program_selection(support_review, support_prediction)
    program_components = [{
        **component,
        "program_role": (f"concurrent disease control · {target_code.replace('_', ' ')}" if fallback_target_code else "primary disease control"),
        "application_relationship": "primary_pass",
        "selection_reason": (
            f"No verified product is available for {requested_target_code.replace('_', ' ')}. "
            f"The independently screened {target_code.replace('_', ' ')} signal is moderate or higher and has a verified candidate; this product does not treat the unsupported target."
            if fallback_target_code else
            f"Needed for the selected {candidate.get('target_name') or target_code} issue: "
            f"current modeled pressure is {(_number(prediction.get('current_risk_score')) or 0):g} "
            f"({str(prediction.get('current_risk_level') or prediction.get('risk_level') or 'unknown')})."
        ),
    }]
    same_tank_components = [component]
    program_passes = [{"pass": 1, "relationship": "primary", "components": [component], "batch_recipe": batch_recipe}]
    additional_controls = _additional_disease_controls(
        crop_scope=crop_scope, prediction=prediction, primary_target=target_code,
        area_ha=known_area, water_l=planning_water_l, stock_by_product=stock_by_product,
        authorization_reference_day=authorization_reference_day,
    )
    primary_name = str(component.get("product_name") or "").casefold()
    for additional in additional_controls:
        if str(additional.get("product_name") or "").casefold() == primary_name:
            continue
        program_components.append(additional)
        program_passes.append({
            "pass": len(program_passes) + 1,
            "relationship": "secondary_disease_control_separate_pass",
            "components": [additional],
            "batch_recipe": calculate_batch_recipe(batches, [additional]),
        })
        additional_total = _number(additional.get("total"))
        additional_balance = _number(additional.get("stock_on_hand")) or 0
        if additional_total is not None and additional_balance < additional_total:
            needed_list.append({
                "product_name": additional.get("product_name"), "required": additional_total,
                "on_hand": round(additional_balance, 3),
                "needed": calculate_stock_shortage(additional_total, additional_balance),
                "unit": additional.get("total_unit"), "target": additional.get("purpose"),
                "reason": "Independent same-date disease pressure supports this additional separate-pass control review.",
                "purchase_state": additional.get("purchase_state"),
            })
    for selected in selected_support:
        selected_total = _number(selected.get("selected_total"))
        selected_unit = selected.get("selected_unit")
        support_component = {
            "product_name": selected.get("product_name"),
            "active_ingredient": selected.get("active_ingredient"),
            "purpose": selected.get("mixture_role") or "support",
            "program_role": f"conditional {selected.get('mixture_role') or 'support'}",
            "total": selected_total,
            "total_unit": selected_unit,
            "purchase_state": selected.get("purchase_state"),
            "stock_on_hand": selected.get("stock_on_hand"),
            "stock_unit": selected.get("stock_unit"),
            "application_relationship": selected.get("application_relationship"),
            "selection_reason": selected.get("selection_reason"),
            "compatibility_notes": selected.get("compatibility_conditions"),
            "mixing_position": selected.get("mixing_position"),
            "mixing_sequence": selected.get("mixing_instructions"),
        }
        program_components.append(support_component)
        if selected.get("application_relationship") == "same_tank_verified":
            same_tank_components.append(support_component)
        else:
            program_passes.append({
                "pass": len(program_passes) + 1,
                "relationship": "separate_or_pending_exact_mix_approval",
                "components": [support_component],
                "batch_recipe": calculate_batch_recipe(batches, [support_component]),
            })
        support_balance = _number(selected.get("stock_on_hand")) or 0
        if selected_total is not None and support_balance < selected_total:
            needed_list.append({
                "product_name": selected.get("product_name"), "required": selected_total,
                "on_hand": round(support_balance, 3),
                "needed": calculate_stock_shortage(selected_total, support_balance),
                "unit": selected_unit, "target": candidate.get("target_name"),
                "reason": "Conditional support selected for the calculated program; confirm need and receipt before approval.",
                "purchase_state": selected.get("purchase_state"),
            })
    agronomist_pattern = agronomist_pattern_program(
        prediction={
            **prediction,
            "scenario_target_code": requested_target_code,
        },
        water_l=planning_water_l,
        stock_by_product=stock_by_product,
    ) if crop_scope == "vineyard" else None
    if agronomist_pattern:
        # A complete recorded program replaces the independent-product draft.
        # It is deliberately review-gated: history is evidence of the
        # Agronomist's practice, never a substitute for a current legal label.
        program_components = agronomist_pattern["components"]
        same_tank_components = []
        batch_recipe = calculate_batch_recipe(batches, program_components)
        program_passes = [{
            "pass": 1,
            "relationship": "agronomist_pattern_one_pass_pending_exact_mix_review",
            "components": program_components,
            "batch_recipe": batch_recipe,
        }]
        needed_list = []
        hard_blocks.append(
            "Confirm that every Agronomist-pattern component is necessary for this current field condition; prior use alone is not a reason to apply it."
        )
        hard_blocks.append(
            "Agronomist must approve the exact combined recipe and mixing order before either 200 L batch is prepared."
        )
        if not agronomist_pattern.get("safe_for_prescription_reuse"):
            hard_blocks.append(
                "The matched historical treatment is restricted learning evidence, not a reusable prescription. Re-authorize the current products, rates, safety checks and exact mixture from current evidence."
            )
        if agronomist_pattern.get("reason_status") != "documented_event_plus_pattern":
            hard_blocks.append(
                "Confirm the inferred treatment rationale. Treatments 2–4 record what was applied, but not the Agronomist's exact decision reason."
            )
        for pattern_component in program_components:
            if not pattern_component.get("current_profile_ready"):
                hard_blocks.append(
                    f"Verify the current Italian label, estate authorization and formulation profile for {pattern_component.get('product_name')} before approval; historical use is not current authorization."
                )
    if len(same_tank_components) > 1:
        batch_recipe = calculate_batch_recipe(batches, same_tank_components)
    inventory_plan = treatment_inventory_plan(program_components)
    if agronomist_pattern:
        needed_list = [{
            "product_name": row.get("product_name"),
            "required": row.get("required"),
            "on_hand": row.get("on_hand"),
            "needed": row.get("remaining_needed"),
            "unit": row.get("required_unit"),
            "target": candidate.get("target_name"),
            "reason": "Complete Agronomist-pattern program requirement exceeds recorded available stock.",
            "purchase_state": row.get("status"),
        } for row in inventory_plan if row.get("remaining_needed") is None or (_number(row.get("remaining_needed")) or 0) > 0]
    operating_plan = build_one_pass_treatment_plan(
        water_l=planning_water_l, batches=batches, components=program_components
    )

    weather_assessment = fetch_one(
        "SELECT assessed_at,assessment_date,model_version,disease_code,disease_name,risk_score,risk_level,evidence_summary,input_snapshot "
        "FROM disease_pressure_assessments WHERE estate_id=%s AND disease_code=%s "
        + ("AND assessment_date=%s " if scenario_day and scenario_day < date.today() else "") +
        "ORDER BY assessed_at DESC LIMIT 1",
        (estate_id(), target_code, scenario_day) if scenario_day and scenario_day < date.today() else (estate_id(), target_code),
    ) or (prediction.get("weather_assessment") if isinstance(prediction.get("weather_assessment"), dict) else {})
    snapshot = weather_assessment.get("input_snapshot") or {}
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except (TypeError, ValueError):
            snapshot = {}
    assessed_day = _day(weather_assessment.get("assessment_date"))
    weather_watch = {
        "connected": bool(weather_assessment),
        "assessment_date": weather_assessment.get("assessment_date"),
        "assessed_at": weather_assessment.get("assessed_at"),
        "model_version": weather_assessment.get("model_version"),
        "target_code": target_code,
        "risk_score": weather_assessment.get("risk_score"),
        "risk_level": weather_assessment.get("risk_level"),
        "evidence_summary": weather_assessment.get("evidence_summary"),
        "weather_latest_at": snapshot.get("weather_latest_at") if isinstance(snapshot, dict) else None,
        "weather_observation_count": snapshot.get("weather_observation_count") if isinstance(snapshot, dict) else None,
        "rain_72h_mm": snapshot.get("rain_72h_mm") if isinstance(snapshot, dict) else None,
        "rain_7d_mm": snapshot.get("rain_7d_mm") if isinstance(snapshot, dict) else None,
        "humidity_avg_pct": snapshot.get("humidity_avg_pct") if isinstance(snapshot, dict) else None,
        "leaf_wetness_avg_pct": snapshot.get("leaf_wetness_avg_pct") if isinstance(snapshot, dict) else None,
        "current": bool(assessed_day and (date.today() - assessed_day).days <= 1),
        "weather_evidence_kind": weather_evidence_kind,
        "weather_days_checked": len(window_weather),
        "watch_cadence_minutes": 5,
        "pipeline": "on-site weather + daily rain + forecast → disease pressure → field review → products + timing → Agronomist approval",
    }
    compatibility_policy = {"automatic_combination_allowed": False, "rule": "Only an exact product combination recorded as verified_compatible may be combined. Sulfur and copper default to separate applications. Conditional combinations require agronomist approval and a jar test only where the current label permits it.", "primary_product": component["product_name"]}
    equipment_choices = [{"id": row.get("equipment_id"), "name": row.get("name"), "make_model": row.get("make_model"), "capacity_l": _number(row.get("usable_capacity_l")) or _number(row.get("tank_capacity_l")), "calibration_status": row.get("calibration_status")} for row in equipment_rows]
    configuration_needed = []
    if not equipment_rows:
        configuration_needed.append("Add an active spray-equipment profile.")
    elif not any(row.get("calibration_status") == "verified" for row in equipment_rows):
        configuration_needed.append("Measure usable tank fill and complete sprayer calibration.")
    if missing_area_blocks:
        configuration_needed.append("Record the area of every active block used for whole-estate projections.")
    return {"status": "calculated_proposal_blocked" if hard_blocks else "ready_for_agronomist_review", "requested_target_code": requested_target_code, "fallback_target_code": fallback_target_code, "target_code": target_code, "target_name": candidate.get("target_name"), "preferred_candidate": candidate, "candidates": candidates, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "inventory_plan": inventory_plan, "needed_list": needed_list, "stock_review_list": stock_review_list, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "application_window": spray_window, "weather_watch": weather_watch, "configuration": {"requested_sprayer": requested_equipment or None, "selected_sprayer_id": (sprayer or {}).get("equipment_id"), "equipment_choices": equipment_choices, "needs_configuration": configuration_needed}, "mixture": {"homogeneous": True, "homogeneity_rule": "The Baiamonte operating plan is one vineyard pass using two prepared fills. Every included product must have a documented need; the exact combined mixture still requires current compatibility approval.", "planning_basis": {"area_ha": known_area, "water_l": planning_water_l, "application_medium": "water_spray", "equipment": sprayer, "equipment_choices": equipment_choices, "sprayer_batches": batches, "area_note": area_note, "water_note": "Baiamonte standard: 400 L total carrier as two 200 L fills for one complete vineyard pass."}, "components": same_tank_components, "program_components": program_components, "program_passes": program_passes, "batch_recipe": batch_recipe, "operating_plan": operating_plan, "agronomist_pattern": agronomist_pattern, "support_product_review": support_review, "selected_support_products": selected_support, "compatibility_policy": compatibility_policy, "mixing_order": [item["product_name"] for item in operating_plan["products"]], "hard_blocks": hard_blocks, "earliest_harvest_forecast": earliest_harvest, "phi_passes_current_forecast": phi_ok}, "message": (f"Complete Agronomist-pattern program calculated from {agronomist_pattern.get('basis_treatment')} and scaled to the current two-by-200-L process. Current need, labels, exact-mixture compatibility, weather and Agronomist approval remain mandatory." if agronomist_pattern else f"No verified {requested_target_code.replace('_', ' ')} product is currently available. The simulator still calculated the independently supported concurrent {fallback_target_code.replace('_', ' ')} program; it does not treat the unsupported target." if fallback_target_code else "Calculated one-pass vineyard treatment using only evidence-supported products. Quantities are split into two 200 L recipes; current labels, exact-mixture compatibility, weather and Agronomist approval remain mandatory.")}
def treatment_cost_estimate(components: list[dict[str, Any]], application_date: Any = None) -> dict[str, Any]:
    """Price a proposed or completed program from the newest posted purchase evidence."""
    as_of = str(application_date or date.today())[:10]
    rows = []
    total_cost = 0.0
    missing = []
    for component in components:
        name = str(component.get("product_name") or "").strip()
        if not name:
            continue
        product = fetch_one("SELECT id,unit FROM products WHERE estate_id=%s AND name=%s", (estate_id(), name)) or {}
        price = fetch_one(
            "SELECT unit_cost_eur,movement_date FROM inventory_movements WHERE estate_id=%s AND product_id=%s "
            "AND movement_date<=%s AND unit_cost_eur>0 ORDER BY movement_date DESC,created_at DESC LIMIT 1",
            (estate_id(), product.get("id"), as_of),
        ) if product.get("id") else None
        quantity = component.get("total") if component.get("total") is not None else component.get("total_used")
        quantity_unit = component.get("total_unit") or component.get("dose_unit") or product.get("unit")
        unit_cost = float((price or {}).get("unit_cost_eur") or 0)
        compatible = quantity is not None and str(quantity_unit or "").casefold() == str(product.get("unit") or "").casefold()
        cost = float(quantity) * unit_cost if compatible and unit_cost else None
        if cost is None:
            missing.append(name)
        else:
            total_cost += cost
        rows.append({"product_name": name, "quantity": quantity, "unit": quantity_unit, "unit_cost_eur": unit_cost or None, "cost_eur": cost, "price_date": (price or {}).get("movement_date"), "status": "priced" if cost is not None else "price_or_unit_review"})
    return {"total_eur": round(total_cost, 2), "products": rows, "missing_prices": missing, "complete": not missing, "basis": "Newest posted supplier purchase at or before the treatment date; excludes labor and equipment unless entered separately."}


def attach_treatment_costs(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        items = fetch_all("SELECT p.name product_name,i.total_used,i.dose_unit FROM spray_application_items i JOIN products p ON p.id=i.product_id WHERE i.application_id=%s", (row.get("id"),))
        row["cost_estimate"] = treatment_cost_estimate(items, row.get("application_date"))
