from __future__ import annotations

from datetime import date
import json
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id, season_for_year


FIELDS = ("ph", "organic_matter_pct", "nitrogen_g_kg", "phosphorus_mg_kg", "potassium_mg_kg", "ec_ds_m")


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _interpret(row: dict[str, Any] | None) -> list[dict[str, str]]:
    if not row:
        return []
    checks: list[dict[str, str]] = []
    ph = _number(row.get("ph"))
    organic = _number(row.get("organic_matter_pct"))
    phosphorus = _number(row.get("phosphorus_mg_kg"))
    potassium = _number(row.get("potassium_mg_kg"))
    ec = _number(row.get("ec_ds_m"))
    if ph is not None:
        checks.append({"metric": "Soil pH", "value": f"{ph:g}", "status": "review" if ph < 5.8 or ph > 7.8 else "balanced", "direction": "Confirm lime/acidification and nutrient availability with the laboratory method." if ph < 5.8 or ph > 7.8 else "No pH correction signal from this result."})
    if organic is not None:
        checks.append({"metric": "Organic matter", "value": f"{organic:g}%", "status": "review" if organic < 1.5 else "balanced", "direction": "Review compost or other organic-matter strategy; calculate from the actual analysis, soil depth and material." if organic < 1.5 else "Maintain cover, residue and erosion management."})
    if phosphorus is not None:
        checks.append({"metric": "Phosphorus", "value": f"{phosphorus:g} mg/kg", "status": "review" if phosphorus < 10 else "monitor", "direction": "Potential low result; Agronomist must interpret the extraction method before selecting a product or rate." if phosphorus < 10 else "Monitor against tissue evidence and crop performance."})
    if potassium is not None:
        checks.append({"metric": "Potassium", "value": f"{potassium:g} mg/kg", "status": "review" if potassium < 120 else "monitor", "direction": "Potential low result; reconcile clay, exchange capacity, tissue data and expected crop load before a recommendation." if potassium < 120 else "Monitor with tissue analysis, berry development and crop load."})
    if ec is not None:
        checks.append({"metric": "Salinity / EC", "value": f"{ec:g} dS/m", "status": "review" if ec > 1.5 else "balanced", "direction": "Review salinity, irrigation water and drainage before fertilization." if ec > 1.5 else "No elevated EC signal from this result."})
    return checks


def _current_finding(row: dict[str, Any] | None, checks: list[dict[str, str]]) -> dict[str, Any]:
    """Summarize only the newest report without creating a prescription."""
    if not row:
        return {
            "status": "source_needed",
            "headline": "No current soil finding",
            "summary": "Upload the most recent soil report to create a source-bounded finding.",
            "review_items": [],
            "evidence_note": "No report is available for the selected year.",
            "decision_boundary": "No fertilizer product or rate is inferred without report evidence and Agronomist review.",
        }
    review_items = [check for check in checks if check["status"] == "review"]
    monitored = [check for check in checks if check["status"] in {"monitor", "balanced"}]
    if review_items:
        headline = f"{len(review_items)} current soil signal{'s' if len(review_items) != 1 else ''} need review"
        summary = "Priority review: " + "; ".join(f"{item['metric']} {item['value']}" for item in review_items) + "."
        status = "review"
    elif checks:
        headline = "No threshold review signal in the newest report"
        summary = f"{len(monitored)} recorded metric{'s' if len(monitored) != 1 else ''} remain for routine comparison with tissue, vigor, water and crop-load evidence."
        status = "monitor"
    else:
        headline = "Newest report has no structured soil values"
        summary = "Review the source file and enter only the values explicitly reported by the laboratory."
        status = "values_needed"
    source_state = "AI-extracted values remain pending review." if row.get("value_source") == "ai_extracted_pending_review" else "Analysis uses the stored values from this report."
    return {
        "status": status,
        "headline": headline,
        "summary": summary,
        "review_items": review_items,
        "report_date": str(row.get("sampled_on") or "")[:10],
        "sample_scope": row.get("sample_scope") or "Whole vineyard",
        "laboratory": row.get("laboratory"),
        "source_filename": row.get("original_filename"),
        "intake_item_id": row.get("intake_item_id"),
        "evidence_note": source_state + " Screening thresholds must be checked against the laboratory method.",
        "decision_boundary": "AI-assisted interpretation only; it does not select a fertilizer, calculate a rate, or authorize application.",
    }


def _ai_soil_values(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    if not isinstance(raw, dict):
        return {}
    for record in raw.get("suggested_database_records") or []:
        if not isinstance(record, dict):
            continue
        destination = str(record.get("destination") or record.get("section") or record.get("record_type") or "").casefold()
        if "soil" not in destination and "fertiliz" not in destination:
            continue
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
        return {name: fields.get(name) for name in FIELDS if fields.get(name) not in (None, "")}
    return {}


def dashboard(year: int) -> dict[str, Any]:
    samples = fetch_all(
        "SELECT v.*,i.original_filename,i.review_status intake_review_status,i.extracted_data FROM vineyard_soil_samples v "
        "LEFT JOIN intake_items i ON i.id=v.intake_item_id WHERE v.estate_id=%s AND v.season_id=%s ORDER BY v.sampled_on DESC,v.created_at DESC",
        (estate_id(), season_for_year(year)),
    )
    years = fetch_all(
        "SELECT s.vintage_year,COUNT(v.id) sample_count,MAX(v.sampled_on) latest_sampled_on,"
        "AVG(v.ph) ph,AVG(v.organic_matter_pct) organic_matter_pct,AVG(v.nitrogen_g_kg) nitrogen_g_kg,"
        "AVG(v.phosphorus_mg_kg) phosphorus_mg_kg,AVG(v.potassium_mg_kg) potassium_mg_kg,AVG(v.ec_ds_m) ec_ds_m "
        "FROM seasons s LEFT JOIN vineyard_soil_samples v ON v.season_id=s.id AND v.estate_id=s.estate_id "
        "WHERE s.estate_id=%s GROUP BY s.id,s.vintage_year HAVING COUNT(v.id)>0 ORDER BY s.vintage_year",
        (estate_id(),),
    )
    review = fetch_one(
        "SELECT r.* FROM vineyard_fertilization_reviews r WHERE r.estate_id=%s AND r.season_id=%s",
        (estate_id(), season_for_year(year)),
    ) or {"review_status": "draft", "agronomist_notes": ""}
    for sample in samples:
        extracted = _ai_soil_values(sample.pop("extracted_data", None))
        if extracted:
            sample["ai_extracted_values"] = extracted
            sample["value_source"] = "ai_extracted_pending_review"
            for name, value in extracted.items():
                if sample.get(name) is None:
                    sample[name] = value
    latest = samples[0] if samples else None
    interpreted = _interpret(latest)
    purchases = fetch_all(
        "SELECT pe.invoice_date,pe.invoice_number,pe.supplier,pe.description,pe.quantity_total,pe.quantity_unit,pe.net_amount_eur,pe.vat_rate_pct,p.name product_name,"
        "COALESCE((SELECT SUM(m.quantity_delta) FROM inventory_movements m WHERE m.product_id=p.id),0) stock_on_hand,p.unit stock_unit "
        "FROM treatment_purchase_evidence pe JOIN products p ON p.id=pe.product_id "
        "WHERE pe.estate_id=%s AND p.product_type='fertilizer' AND p.fertilizer_application_route='land' "
        "AND YEAR(pe.invoice_date)=%s ORDER BY pe.invoice_date DESC,pe.line_number",
        (estate_id(), year),
    )
    applications = fetch_all(
        "SELECT a.application_date,a.quantity,a.unit,a.application_scope,a.evidence_status,a.notes,p.name product_name "
        "FROM vineyard_fertilizer_applications a JOIN products p ON p.id=a.product_id "
        "WHERE a.estate_id=%s AND a.season_id=%s ORDER BY a.application_date DESC",
        (estate_id(), season_for_year(year)),
    )
    return json_ready({
        "year": year,
        "samples": samples,
        "yoy": years,
        "review": review,
        "fertilizer_purchases": purchases,
        "fertilizer_applications": applications,
        "current_finding": _current_finding(latest, interpreted),
        "prediction": {
            "status": "review_ready" if interpreted else "soil_sample_needed",
            "headline": "Agronomist review of current soil evidence" if interpreted else "Upload the annual vineyard soil analysis",
            "checks": interpreted,
            "next_step": "Compare the laboratory method with block, tissue, vigor, water and expected yield evidence before selecting fertilizer products or rates." if interpreted else "Upload the source report and enter its reported values when available.",
            "guardrail": "Screening thresholds organize review only. They are not a fertilizer prescription and never authorize an application.",
        },
    })


def save_sample(year: int, payload: dict[str, Any], actor: str) -> str:
    sampled_on = str(payload.get("sampled_on") or "")[:10]
    if not sampled_on:
        raise ValueError("Sample date is required")
    values = [_number(payload.get(name)) for name in FIELDS]
    if any(value is not None and value < 0 for value in values):
        raise ValueError("Soil values cannot be negative")
    record_id = new_id()
    has_values = any(value is not None for value in values)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO vineyard_soil_samples (id,estate_id,season_id,intake_item_id,sampled_on,laboratory,sample_scope,ph,organic_matter_pct,nitrogen_g_kg,phosphorus_mg_kg,potassium_mg_kg,ec_ds_m,source_status,notes,recorded_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (record_id, estate_id(), season_for_year(year), payload.get("intake_item_id") or None, sampled_on, str(payload.get("laboratory") or "").strip() or None, str(payload.get("sample_scope") or "Whole vineyard").strip(), *values, "values_entered" if has_values else "analysis_pending", str(payload.get("notes") or "").strip() or None, actor),
        )
        audit(cursor, "create", "vineyard_soil_sample", record_id, {"year": year, "sampled_on": sampled_on, "source_status": "values_entered" if has_values else "analysis_pending"}, actor)
    return record_id


def save_review(year: int, payload: dict[str, Any], actor: str) -> None:
    status = str(payload.get("review_status") or "draft").casefold()
    if status not in {"draft", "approved", "rejected"}:
        raise ValueError("Choose draft, approved or rejected")
    season_id = season_for_year(year)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO vineyard_fertilization_reviews (id,estate_id,season_id,review_status,agronomist_notes,reviewed_by,reviewed_at) VALUES (%s,%s,%s,%s,%s,%s,IF(%s='approved',NOW(),NULL)) "
            "ON DUPLICATE KEY UPDATE review_status=VALUES(review_status),agronomist_notes=VALUES(agronomist_notes),reviewed_by=VALUES(reviewed_by),reviewed_at=IF(VALUES(review_status)='approved',NOW(),NULL)",
            (new_id(), estate_id(), season_id, status, str(payload.get("agronomist_notes") or "").strip() or None, actor, status),
        )
        audit(cursor, "review", "vineyard_fertilization", season_id, {"year": year, "status": status}, actor)
