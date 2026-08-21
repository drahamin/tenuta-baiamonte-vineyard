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
        "SELECT a.id,a.assessed_at observed_at,a.damage_type issue_type,a.event_key damage_event_key,a.review_status damage_proposal_status,"
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
        return {"rows": {}, "summary": {"records": 0, "active_records": 0, "inactive": 0, "verified": 0, "attention": 0, "blocked": 0}}
    placeholders = ",".join(["%s"] * len(application_ids))
    item_rows = fetch_all(
        "SELECT i.application_id,i.id item_id,i.product_id,i.dose_amount,i.total_used,i.dose_unit,i.phi_days,p.name product_name,"
        "r.verification_status,r.label_verified_on,r.estate_authorization_status "
        "FROM spray_application_items i JOIN products p ON p.id=i.product_id "
        "LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 "
        f"WHERE i.application_id IN ({placeholders}) ORDER BY i.application_id,p.name",
        tuple(application_ids),
    )
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
    counts = {"records": len(rows), "active_records": 0, "inactive": 0, "verified": 0, "attention": 0, "blocked": 0}
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
        quantities_ready = (not completed) or (bool(items) and bool(row.get("actual_details_confirmed")) and not unresolved and all(item.get("total_used") is not None for item in items))
        checks.append({
            "code": "completed_use",
            "label": "Completed-use quantities",
            "status": "not_applicable" if not completed else "verified" if quantities_ready else "unknown",
            "detail": "Not applicable until the treatment is completed." if not completed else "Every product total is recorded and reconciled to inventory." if quantities_ready else (
                "; ".join(str(item.get("reason") or "Exact total used is unknown") for item in unresolved) or "One or more exact product totals used are unknown."
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
        status = "verified" if not blockers else "blocked" if any(check["status"] == "conflict" for check in blockers) else "attention"
        counts[status] += 1
        audited[application_id] = {
            "status": status,
            "checks": checks,
            "blocker_count": len(blockers),
            "safe_for_prediction_reuse": status == "verified",
            "rule": "Historical products, quantities or mixtures are not reused as prescriptions while any safety evidence remains unknown or unverified.",
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
        "projected_quantity": quantity,
    }


_RISK_RANK = {"unknown": 0, "trace": 1, "low": 2, "moderate": 3, "high": 4, "critical": 5}


def _support_program_selection(
    reviews: list[dict[str, Any]], prediction: dict[str, Any]
) -> list[dict[str, Any]]:
    """Select at most one defensible support product for the proposed program.

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

    eligible: list[tuple[int, dict[str, Any]]] = []
    for row in reviews:
        if str(row.get("decision") or "").startswith("blocked") or row.get("decision") == "not_selected" and row.get("mixture_role") == "nutrition" and not stress_event:
            continue
        role = str(row.get("mixture_role") or "support")
        if role == "nutrition" and not stress_event:
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
        if compatibility not in {"verified_compatible", "conditional"}:
            continue
        score = (3 if str(row.get("target_code") or target).casefold() == target else 1)
        score += 2 if compatibility == "verified_compatible" else 1
        score += 1 if role in {"support", "adjuvant"} else 0
        score += {"GEL DI SILICE": 4, "REPENTE": 3, "RESOLVE": 2}.get(str(row.get("product_name") or "").upper(), 0)
        eligible.append((score, row))
    if not eligible:
        return []
    eligible.sort(key=lambda item: (-item[0], str(item[1].get("product_name") or "")))
    selected = dict(eligible[0][1])
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
    selected["selection_reason"] = (
        f"{risk_level.title()} {target.replace('_', ' ')} pressure supports a field review of this "
        f"{selected.get('mixture_role') or 'support'} product; seasonal screening is "
        f"{str(seasonality.get('calendar_fit') or 'not available')}. It is not a substitute for the primary disease-control product."
    )
    return [selected]


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

    uses = fetch_all("SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.density_kg_l,r.density_min_kg_l,r.density_max_kg_l,r.density_source,r.mixing_position,r.mixing_instructions,r.compatibility_notes,r.water_quality_notes,r.eligible_for_projection FROM product_authorized_uses u JOIN products p ON p.id=u.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 ORDER BY (u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE())) DESC,u.label_verified_on DESC,p.name", (estate_id(), crop_scope, target_code))
    candidates = [row for row in uses if row.get("authorization_status") == "authorized" and (not _day(row.get("authorization_expires_on")) or _day(row.get("authorization_expires_on")) >= date.today()) and _profile_ready(row)]
    blocked_products = [{"product_name": row.get("product_name"), "reason": _profile_block_reason(row) if row.get("authorization_status") == "authorized" else f"Authorization status: {row.get('authorization_status')}; expiry {row.get('authorization_expires_on') or 'not recorded'}."} for row in uses if row not in candidates]
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
    if known_area and rate and dose_unit == "kg/ha":
        calculation = {**calculate_area_mix(area_ha=known_area, water_l=planning_water_l, rate_kg_ha=rate), "total": round(known_area * rate, 3), "total_unit": "kg"}
    elif known_area and rate and dose_unit == "L/ha":
        total_l = round(known_area * rate, 3)
        calculation = {"area_ha": known_area, "water_l": planning_water_l, "rate_l_ha": rate, "total": total_l, "total_unit": "L", "per_100_l_ml": round(total_l * 100000 / planning_water_l, 1)}
    else:
        calculation = None
    candidate_stock = stock_by_product.get(str(candidate.get("product_name"))) or {}
    ledger_balance = _number(candidate_stock.get("ledger_balance")) or 0
    stock_balance = _number(candidate_stock.get("stock_on_hand")) or 0
    required_quantity = _number(calculation.get("total")) if calculation else None
    candidate_name = str(candidate.get("product_name") or "")
    purchase_state = "stock_unreconciled" if candidate_name in unresolved_products else "receipt_pending" if ledger_balance < 0 else "in_stock" if stock_balance > 0 and (required_quantity is None or stock_balance >= required_quantity) else "insufficient_stock" if stock_balance > 0 else "suggested_purchase"
    scenario_day = _day(prediction.get("scenario_date"))
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
    component = {"product_name": candidate.get("product_name"), "active_ingredient": candidate.get("active_ingredient"), "registration_number": candidate.get("registration_number"), "purpose": candidate.get("target_name"), "concentrate_form": candidate.get("concentrate_form"), "final_application_medium": candidate.get("final_application_medium"), "rate": rate, "rate_unit": candidate.get("dose_unit"), "total": calculation.get("total") if calculation else None, "total_unit": calculation.get("total_unit") if calculation else None, "per_100_l": per_100_l, "per_100_l_unit": per_100_l_unit, "purchase_state": purchase_state, "stock_on_hand": stock_balance, "stock_unit": candidate.get("unit"), "phi_days": phi_days, "rei_hours": candidate.get("rei_hours"), "resistance_group": candidate.get("resistance_group"), "mixing_sequence": candidate.get("mixing_instructions"), "compatibility_notes": candidate.get("compatibility_notes"), "label_url": candidate.get("label_url")}
    batch_recipe = calculate_batch_recipe(batches, [component])
    option_rows = fetch_all("SELECT o.*,p.name product_name,p.active_ingredient,p.unit,r.id profile_id,r.concentrate_form,r.final_application_medium,r.verification_status,r.estate_authorization_status,r.estate_authorization_confirmed_on,r.authorization_notes,r.measure_unit,r.mixing_position,r.mixing_instructions,r.compatibility_notes,r.eligible_for_projection FROM treatment_product_options o JOIN products p ON p.id=o.product_id LEFT JOIN treatment_product_profiles r ON r.product_id=p.id AND r.active=1 WHERE o.estate_id=%s AND o.crop_scope=%s AND o.target_code IN (%s,'any') AND o.mixture_role<>'primary' AND o.active=1 AND p.active=1 ORDER BY FIELD(o.default_decision,'candidate','blocked','not_selected'),p.name", (estate_id(), crop_scope, target_code))
    support_review = [_review_possible_product(row, stock_by_product, planning_water_l=planning_water_l, planning_area_ha=known_area) for row in option_rows]
    selected_support = _support_program_selection(support_review, prediction)
    program_components = [{**component, "program_role": "primary disease control", "application_relationship": "primary_pass", "selection_reason": f"Authorized primary candidate for {candidate.get('target_name') or target_code}."}]
    same_tank_components = [component]
    program_passes = [{"pass": 1, "relationship": "primary", "components": [component], "batch_recipe": batch_recipe}]
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
    if len(same_tank_components) > 1:
        batch_recipe = calculate_batch_recipe(batches, same_tank_components)
    inventory_plan = treatment_inventory_plan(program_components)

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
    return {"status": "calculated_proposal_blocked" if hard_blocks else "ready_for_agronomist_review", "target_code": target_code, "target_name": candidate.get("target_name"), "preferred_candidate": candidate, "candidates": candidates, "blocked_products": blocked_products, "purchase_summary": purchase_summary, "inventory_reconciliation": inventory_reconciliation, "inventory_plan": inventory_plan, "needed_list": needed_list, "stock_review_list": stock_review_list, "non_treatment_purchases": non_treatment, "product_reference_catalog": reference_catalog, "application_window": spray_window, "weather_watch": weather_watch, "configuration": {"requested_sprayer": requested_equipment or None, "selected_sprayer_id": (sprayer or {}).get("equipment_id"), "equipment_choices": equipment_choices, "needs_configuration": configuration_needed}, "mixture": {"homogeneous": True, "homogeneity_rule": "Every prepared tank is treated as a homogeneous water mixture under label-required agitation; products assigned to separate passes are prepared as separate homogeneous tanks.", "planning_basis": {"area_ha": known_area, "water_l": planning_water_l, "application_medium": "water_spray", "equipment": sprayer, "equipment_choices": equipment_choices, "sprayer_batches": batches, "area_note": area_note, "water_note": "Adjustable planning carrier volume; confirm calibrated L/ha and actual batch fills."}, "components": same_tank_components, "program_components": program_components, "program_passes": program_passes, "batch_recipe": batch_recipe, "support_product_review": support_review, "selected_support_products": selected_support, "compatibility_policy": compatibility_policy, "mixing_order": [item["product_name"] for item in same_tank_components], "hard_blocks": hard_blocks, "earliest_harvest_forecast": earliest_harvest, "phi_passes_current_forecast": phi_ok}, "message": "Calculated multi-product treatment program, not an application order. Primary control and justified support products are separated unless exact compatibility is verified; current labels, weather, field evidence and Agronomist approval remain mandatory."}
