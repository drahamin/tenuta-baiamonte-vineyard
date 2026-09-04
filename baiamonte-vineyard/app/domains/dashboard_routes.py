"""Operational dashboard, vintage dashboard, and multi-year aggregation routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request

from ..access import authorize, has_finance_access
from ..config import Settings, get_settings
from ..db import fetch_all, fetch_one
from ..display_data import display_payload
from ..historical_dashboard import (
    FIRST_ESTATE_VINTAGE,
    all_vintage_rows,
    historical_note_facts,
    merge_historical_fact_overview,
    merge_historical_work_overview,
    merge_variety_history,
    merge_variety_summaries,
    reconciled_vintage_values,
    selected_dashboard_activities,
    selected_dashboard_history,
    selected_vintage_rows,
)
from ..prediction_evidence import maturity_evidence_sql
from ..prediction_sources import prediction_source_context
from ..service import estate_id, json_ready
from ..official_facts import official_pipeline_context
from ..wine_conversion import yield_disclosure
from .harvest import latest_scouting_by_variety
from .messaging import event_payload


router = APIRouter(tags=["dashboard"])


@router.get("/api/v1/dashboard", dependencies=[Depends(authorize)])
def dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=FIRST_ESTATE_VINTAGE)) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year))
    season_id = season["id"] if season else ""
    historical = selected_dashboard_history(year, season_id)
    activity = selected_dashboard_activities(year, season_id)
    current_year = datetime.now(ZoneInfo("Europe/Rome")).year
    today_rome = datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()
    recent_activities = [
        row for row in activity["activities"]
        if year != current_year or str(row.get("activity_date") or row.get("record_date") or "")[:10] <= today_rome
    ][:6]
    return json_ready({
        "year": year,
        "counts": {
            "open_tasks": (fetch_one("SELECT COUNT(*) n FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress')", (estate_id(),)) or {"n": 0})["n"] if year == current_year else 0,
            "open_alerts": (fetch_one("SELECT COUNT(*) n FROM alerts WHERE estate_id=%s AND status='open'", (estate_id(),)) or {"n": 0})["n"] if year == current_year else 0,
            "harvest_kg": historical["recorded_kg"] or historical["totals"].get("grapes_kg") or 0,
            "work_hours": activity["work_hours"],
            "historical_work_records": activity["historical_records"],
            "labor_records": activity["labor_records"],
            "work_records": activity["work_records"],
            "historical_work_audit": activity["historical_audit"],
        },
        "tasks": fetch_all("SELECT id,title,category,priority,status,due_date,block_code,block_name,days_until_due FROM v_open_work WHERE estate_id=%s ORDER BY due_date IS NULL,due_date LIMIT 6", (estate_id(),)) if year == current_year else [],
        "activities": recent_activities,
        "historical_facts": historical_note_facts(year),
        "official_facts": official_pipeline_context(year),
        "harvest": historical["harvest"],
        "weather": historical["weather"],
        "historical_summary": historical["totals"] if historical["has_summary"] else None,
        "alerts": fetch_all("SELECT id,alert_type,severity,title,message,source_id,status,triggered_at FROM alerts WHERE estate_id=%s AND status='open' ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC", (estate_id(),)) if year == current_year else [],
    })


@router.get("/api/display-data", dependencies=[Depends(authorize)])
def ingress_display_data() -> dict[str, Any]:
    return display_payload()


@router.get("/api/v1/grapes/dashboard", dependencies=[Depends(authorize)])
def grape_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=FIRST_ESTATE_VINTAGE)) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year))
    season_id = season["id"] if season else ""
    varieties = fetch_all(
        "SELECT v.id,v.name,v.color_hex,v.target_gdd,"
        "p.planned_kg,p.planned_pick_date,p.plan_status,p.confidence,p.weather_risk,p.dependencies,"
        "h.harvested_kg,h.crates,h.first_pick_date,h.last_pick_date,h.avg_babo,h.avg_brix,h.avg_ph,h.avg_ta "
        "FROM grape_varieties v "
        "LEFT JOIN (SELECT variety_id,SUM(planned_kg) planned_kg,MIN(planned_pick_date) planned_pick_date,"
        "GROUP_CONCAT(DISTINCT status ORDER BY status SEPARATOR ', ') plan_status,MAX(confidence) confidence,"
        "GROUP_CONCAT(DISTINCT weather_risk SEPARATOR '; ') weather_risk,GROUP_CONCAT(DISTINCT dependencies SEPARATOR '; ') dependencies "
        "FROM harvest_plans WHERE season_id=%s GROUP BY variety_id) p ON p.variety_id=v.id "
        "LEFT JOIN (SELECT variety_id,SUM(weight_kg) harvested_kg,SUM(crate_count) crates,MIN(DATE(harvested_at)) first_pick_date,"
        "MAX(DATE(harvested_at)) last_pick_date,AVG(babo) avg_babo,AVG(brix) avg_brix,AVG(ph) avg_ph,AVG(ta_g_l) avg_ta "
        "FROM harvest_lots WHERE season_id=%s GROUP BY variety_id) h ON h.variety_id=v.id "
        "WHERE v.estate_id=%s AND v.active=1 AND LOWER(v.name) NOT IN ('blend','other') ORDER BY v.name",
        (season_id, season_id, estate_id()),
    )
    selected_vintage_summaries = selected_vintage_rows(year)
    varieties = merge_variety_summaries(varieties, selected_vintage_summaries)
    forecasts = fetch_all(
        "SELECT g.variety_id,g.observed_through,g.observed_gdd,g.target_gdd,g.predicted_date,g.final_forecast_date,g.confidence,g.calibration_evidence "
        "FROM gdd_forecasts g JOIN (SELECT variety_id,MAX(computed_at) computed_at FROM gdd_forecasts WHERE season_id=%s GROUP BY variety_id) latest "
        "ON latest.variety_id=g.variety_id AND latest.computed_at=g.computed_at WHERE g.season_id=%s",
        (season_id, season_id),
    ) if season_id else []
    for forecast in forecasts:
        calibration = event_payload(forecast.get("calibration_evidence"))
        learned_model = calibration.get("learned_model") if isinstance(calibration.get("learned_model"), dict) else {}
        forecast["target_gdd_source"] = calibration.get("target_gdd_source") or "unknown"
        forecast["gdd_forecast_ready"] = bool(calibration.get("gdd_forecast_ready"))
        forecast["learned_model"] = learned_model
        forecast["forecast_basis"] = (
            "Learned and backtested harvest model" if forecast["target_gdd_source"] == "learned_model" and learned_model.get("ready")
            else "Configured expert GDD target" if forecast["target_gdd_source"] == "configured"
            else "Provisional seasonal date while the model gathers exact harvest evidence"
        )
    forecast_by_variety = {row["variety_id"]: row for row in forecasts}
    maturity_rows = fetch_all(
        "SELECT m.* FROM maturity_samples m JOIN (SELECT candidate.variety_id,MAX(candidate.sampled_at) sampled_at FROM maturity_samples candidate WHERE candidate.season_id=%s AND candidate.variety_id IS NOT NULL AND " + maturity_evidence_sql("candidate") + " GROUP BY candidate.variety_id) latest "
        "ON latest.variety_id=m.variety_id AND latest.sampled_at=m.sampled_at WHERE m.season_id=%s",
        (season_id, season_id),
    ) if season_id else []
    maturity_by_variety = {row["variety_id"]: row for row in maturity_rows}
    recent_weather = fetch_one(
        "SELECT MAX(weather_date) observed_through,SUM(rain_mm) rain_7d_mm,AVG(temp_avg_c) temp_avg_7d_c,MAX(temp_max_c) temp_max_7d_c,SUM(gdd_base10) gdd_7d "
        "FROM weather_daily WHERE estate_id=%s AND weather_date>=CURDATE()-INTERVAL 7 DAY",
        (estate_id(),),
    ) or {}
    scouting_by_variety = latest_scouting_by_variety(season_id)
    chemistry_rows = fetch_all(
        "SELECT s.variety_id,s.lab_date,r.analyte_code,r.analyte_name,r.numeric_value,r.unit "
        "FROM lab_samples s JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND s.season_id=%s AND s.sample_type='grape' AND s.needs_review=0 AND r.numeric_value IS NOT NULL "
        "ORDER BY s.lab_date DESC,s.created_at DESC",
        (estate_id(), season_id),
    ) if season_id else []
    chemistry: dict[str, dict[str, Any]] = {}
    for row in chemistry_rows:
        item = chemistry.setdefault(row["variety_id"] or "unassigned", {"lab_date": row["lab_date"], "results": {}})
        code = (row["analyte_code"] or row["analyte_name"]).casefold()
        if code not in item["results"]:
            item["results"][code] = {"value": row["numeric_value"], "unit": row["unit"], "name": row["analyte_name"]}
    preferred_plans = fetch_all(
        "SELECT p.* FROM harvest_plans p WHERE p.season_id=%s AND p.id=(SELECT p2.id FROM harvest_plans p2 "
        "WHERE p2.season_id=p.season_id AND p2.variety_id=p.variety_id "
        "ORDER BY (p2.status IN ('confirmed','in_progress','complete','hold')) DESC,(p2.approved_by IS NOT NULL) DESC,p2.updated_at DESC LIMIT 1)",
        (season_id,),
    ) if season_id else []
    preferred_plan_by_variety = {row["variety_id"]: row for row in preferred_plans}
    for row in varieties:
        planned = float(row.get("planned_kg") or 0)
        harvested = float(row.get("harvested_kg") or 0)
        row["remaining_kg"] = max(planned - harvested, 0) if row.get("planned_kg") is not None else None
        row["completion_pct"] = round(harvested / planned * 100, 1) if planned else None
        past_pick = year < date.today().year and row.get("first_pick_date")
        if past_pick:
            row.update(plan_status="picked / complete", remaining_kg=0, completion_pct=100.0)
        row["forecast"] = forecast_by_variety.get(row["id"])
        row["latest_grape_lab"] = chemistry.get(row["id"])
        maturity = maturity_by_variety.get(row["id"]) or {}
        scouting = scouting_by_variety.get(row["id"]) or {}
        forecast = row["forecast"] or {}
        preferred_plan = preferred_plan_by_variety.get(row["id"]) or {}
        protected_plan = bool(preferred_plan.get("approved_by") or preferred_plan.get("status") in {"confirmed", "in_progress", "complete", "hold"})
        candidates = [maturity.get("provisional_pick_date"), forecast.get("final_forecast_date"), forecast.get("predicted_date"), preferred_plan.get("planned_pick_date"), row.get("planned_pick_date")]
        recommended = preferred_plan.get("planned_pick_date") if protected_plan else next((value for value in candidates if value), None)
        if row.get("first_pick_date"):
            recommended = row["first_pick_date"]
        elif maturity.get("decision") == "ready":
            soon = date.today() + timedelta(days=3)
            recommended = min(recommended, soon) if recommended else soon
        elif maturity.get("decision") == "hold":
            hold_until = date.today() + timedelta(days=7)
            recommended = max(recommended, hold_until) if recommended else hold_until
        evidence = []
        if forecast.get("observed_through"):
            evidence.append(f"Weather/GDD through {forecast['observed_through']}")
        elif recent_weather.get("observed_through"):
            evidence.append(f"Weather through {recent_weather['observed_through']}")
        lab = row.get("latest_grape_lab") or {}
        if lab.get("lab_date"):
            evidence.append(f"Grape lab {lab['lab_date']}")
        if maturity.get("sampled_at"):
            evidence.append(f"Field maturity {str(maturity['sampled_at'])[:10]}: {maturity.get('decision') or 'monitor'}")
        if scouting.get("observed_at"):
            evidence.append(f"Reported field check {str(scouting['observed_at'])[:10]}: {scouting.get('issue_type') or 'observation'}")
        if protected_plan:
            evidence.append(f"Human plan: {preferred_plan.get('status') or 'approved'}" + (f" by {preferred_plan['approved_by']}" if preferred_plan.get("approved_by") else ""))
        weather_notes = []
        if recent_weather.get("rain_7d_mm") is not None:
            weather_notes.append(f"{float(recent_weather['rain_7d_mm']):.1f} mm rain / 7d")
        if recent_weather.get("temp_max_7d_c") is not None:
            weather_notes.append(f"{float(recent_weather['temp_max_7d_c']):.1f}°C max / 7d")
        row["harvest_recommendation"] = {
            "recommended_pick_date": recommended,
            "approval_status": "picked_complete" if past_pick else "recorded" if row.get("first_pick_date") else preferred_plan.get("status") if protected_plan else "ready_for_approval" if maturity.get("decision") == "ready" else "hold" if maturity.get("decision") == "hold" else "review",
            "confidence": "high" if len(evidence) >= 3 else "medium" if len(evidence) >= 2 else "low",
            "evidence": evidence,
            "weather_summary": " · ".join(weather_notes),
            "note": "Human-confirmed harvest plan." if protected_plan else ((forecast.get("forecast_basis") or "Decision-support date") + "; confirm current fruit, forecast, crew and cellar readiness before picking."),
        }
    metrics = fetch_one(
        "SELECT (SELECT SUM(planned_kg) FROM harvest_plans WHERE season_id=%s) planned_kg,"
        "(SELECT SUM(weight_kg) FROM harvest_lots WHERE season_id=%s) harvested_kg,"
        "(SELECT COUNT(*) FROM harvest_lots WHERE season_id=%s) harvest_lots,"
        "(SELECT SUM(volume_l) FROM wine_lots WHERE season_id=%s) cellar_volume_l,"
        "(SELECT SUM(regular_hours+COALESCE(overtime_hours,0)) FROM labor_entries WHERE season_id=%s) labor_hours,"
        "(SELECT SUM(labor_cost_eur) FROM labor_entries WHERE season_id=%s) labor_cost_eur",
        (season_id, season_id, season_id, season_id, season_id, season_id),
    ) or {}
    selected_historical_totals = reconciled_vintage_values(selected_vintage_summaries)
    if not float(metrics.get("harvested_kg") or 0):
        metrics["harvested_kg"] = selected_historical_totals.get("grapes_kg")
    if not float(metrics.get("cellar_volume_l") or 0):
        metrics["cellar_volume_l"] = selected_historical_totals.get("wine_l")
    metrics["historical_summary"] = bool(selected_vintage_summaries)
    planned_total = float(metrics.get("planned_kg") or 0)
    harvested_total = float(metrics.get("harvested_kg") or 0)
    metrics["completion_pct"] = round(harvested_total / planned_total * 100, 1) if planned_total else None
    vintages = fetch_all(
        "SELECT vintage_year,COALESCE(MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN grapes_kg END),SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN grapes_kg END)) grapes_kg,"
        "COALESCE(MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN wine_l END),SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN wine_l END)) wine_l,"
        "COALESCE(MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN cassette_count END),SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN cassette_count END)) cassette_count,"
        "GROUP_CONCAT(DISTINCT evidence_status ORDER BY evidence_status SEPARATOR ', ') evidence_status,"
        "GROUP_CONCAT(DISTINCT reconciliation_note SEPARATOR '; ') reconciliation_note "
        "FROM vintage_summaries WHERE estate_id=%s AND vintage_year>=%s GROUP BY vintage_year ORDER BY vintage_year",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
    blocks = fetch_all(
        "SELECT b.id,b.code,b.name,b.area_ha,GROUP_CONCAT(DISTINCT v.name ORDER BY v.name SEPARATOR ', ') varieties,"
        "SUM(h.weight_kg/NULLIF((SELECT COUNT(*) FROM harvest_lot_blocks hlbc WHERE hlbc.harvest_lot_id=h.id),0)) harvested_kg,COUNT(DISTINCT h.id) lot_count "
        "FROM vineyard_blocks b LEFT JOIN block_varieties bv ON bv.block_id=b.id LEFT JOIN grape_varieties v ON v.id=bv.variety_id "
        "LEFT JOIN harvest_lot_blocks hlb ON hlb.block_id=b.id LEFT JOIN harvest_lots h ON h.id=hlb.harvest_lot_id AND h.season_id=%s WHERE b.estate_id=%s AND b.active=1 "
        "GROUP BY b.id,b.code,b.name,b.area_ha ORDER BY b.code",
        (season_id, estate_id()),
    )
    harvest_lots = fetch_all(
        "SELECT h.id,h.harvested_at,h.weight_kg,h.field_weight_kg,h.winery_weight_kg,h.winery_weighed_at,h.winery_weight_notes,h.crate_count,h.avg_crate_kg,h.destination,h.brix,h.babo,h.ph,h.ta_g_l,h.condition_grade,h.notes,v.name variety_name,b.code block_code,"
        "(SELECT GROUP_CONCAT(DISTINCT vb.code ORDER BY vb.code SEPARATOR ', ') FROM harvest_lot_blocks hlb JOIN vineyard_blocks vb ON vb.id=hlb.block_id WHERE hlb.harvest_lot_id=h.id) block_summary,"
        "(SELECT GROUP_CONCAT(CONCAT(p.municipality,' · sheet ',p.cadastral_sheet,' · parcel ',p.parcel_number) ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number SEPARATOR '; ') "
        "FROM harvest_lot_parcels hp JOIN cadastral_parcels p ON p.id=hp.parcel_id WHERE hp.harvest_lot_id=h.id) parcel_summary "
        "FROM harvest_lots h JOIN grape_varieties v ON v.id=h.variety_id LEFT JOIN vineyard_blocks b ON b.id=h.block_id WHERE h.season_id=%s ORDER BY h.harvested_at DESC",
        (season_id,),
    ) if season_id else []
    cellar_lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,w.lot_status,w.volume_l,w.fruit_kg,w.initial_l,w.free_run_l,w.press_l,w.loss_l,w.variety_summary,w.harvest_lot_reference,w.started_at,w.responsible,w.notes,c.code container_code,c.name container_name "
        "FROM wine_lots w LEFT JOIN cellar_containers c ON c.id=w.current_container_id WHERE w.season_id=%s ORDER BY w.started_at,w.code",
        (season_id,),
    ) if season_id else []
    blend_plans = fetch_all(
        "SELECT id,code,name,planned_blend_date,target_grapes_kg,target_volume_l,planned_bottles,crate_weight_kg,expected_yield_l_per_kg,components_text,target_style,decision_status,approved_by,notes "
        "FROM blend_plans WHERE season_id=%s ORDER BY planned_blend_date IS NULL,planned_blend_date,code",
        (season_id,),
    ) if season_id else []
    for plan in blend_plans:
        grapes = float(plan.get("target_grapes_kg") or 0)
        crate = float(plan.get("crate_weight_kg") or 15)
        yield_factor = float(plan.get("expected_yield_l_per_kg") or 0)
        plan["estimated_crates"] = round(grapes / crate, 1) if grapes and crate else None
        plan["estimated_volume_l"] = round(grapes * yield_factor, 1) if grapes and yield_factor else plan.get("target_volume_l")
        plan["wine_yield_conversion"] = (
            yield_disclosure(yield_factor, "Blend plan expected finished-wine yield")
            if grapes and yield_factor
            else None
        )
    blend_history = fetch_all(
        "SELECT s.vintage_year,b.code,b.name,b.target_grapes_kg,b.target_volume_l,b.planned_bottles,b.crate_weight_kg,b.expected_yield_l_per_kg,b.components_text,b.decision_status,"
        "(SELECT SUM(w.fruit_kg) FROM wine_lots w WHERE w.season_id=s.id AND (w.code=b.code OR w.name=b.name)) actual_grapes_kg,"
        "(SELECT SUM(COALESCE(w.volume_l,w.initial_l)) FROM wine_lots w WHERE w.season_id=s.id AND (w.code=b.code OR w.name=b.name)) actual_volume_l "
        "FROM blend_plans b JOIN seasons s ON s.id=b.season_id WHERE b.estate_id=%s ORDER BY s.vintage_year DESC,b.code",
        (estate_id(),),
    )
    variety_history = fetch_all(
        "SELECT s.vintage_year,v.name variety_name,p.planned_kg,h.harvested_kg,h.crates,h.first_pick_date,h.last_pick_date,"
        "m.latest_sample_at,m.max_brix,m.avg_ph "
        "FROM seasons s JOIN grape_varieties v ON v.estate_id=s.estate_id "
        "LEFT JOIN (SELECT season_id,variety_id,SUM(planned_kg) planned_kg FROM harvest_plans GROUP BY season_id,variety_id) p ON p.season_id=s.id AND p.variety_id=v.id "
        "LEFT JOIN (SELECT season_id,variety_id,SUM(weight_kg) harvested_kg,SUM(crate_count) crates,MIN(DATE(harvested_at)) first_pick_date,MAX(DATE(harvested_at)) last_pick_date FROM harvest_lots GROUP BY season_id,variety_id) h ON h.season_id=s.id AND h.variety_id=v.id "
        "LEFT JOIN (SELECT season_id,variety_id,MAX(sampled_at) latest_sample_at,MAX(brix) max_brix,AVG(ph) avg_ph FROM maturity_samples GROUP BY season_id,variety_id) m ON m.season_id=s.id AND m.variety_id=v.id "
        "WHERE s.estate_id=%s AND s.vintage_year>=%s AND v.active=1 "
        "AND (p.planned_kg IS NOT NULL OR h.harvested_kg IS NOT NULL OR m.latest_sample_at IS NOT NULL) ORDER BY s.vintage_year,v.name",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
    all_variety_summaries = all_vintage_rows()
    variety_history = merge_variety_history(variety_history, all_variety_summaries)
    return json_ready({"year": year, "metrics": metrics, "varieties": varieties, "vintages": vintages, "blocks": blocks, "harvest_lots": harvest_lots, "cellar_lots": cellar_lots, "blend_plans": blend_plans, "blend_history": blend_history, "variety_history": variety_history, "prediction_sources": prediction_source_context() if year == date.today().year else {}})



@router.get("/api/v1/history/overview", dependencies=[Depends(authorize)])
def multi_year_overview(
    request: Request,
    from_year: int = FIRST_ESTATE_VINTAGE,
    to_year: int = Query(default_factory=lambda: date.today().year),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    from_year = max(FIRST_ESTATE_VINTAGE, from_year)
    include_finance = has_finance_access(request, x_api_key, settings)
    years: dict[int, dict[str, Any]] = {
        year: {"year": year, "harvest_kg": None, "harvest_lots": 0, "cellar_l": None, "labor_hours": None, "labor_entries": 0, "historical_work_records": 0, "historical_known_hour_records": 0, "historical_exact_date_records": 0, "historical_month_date_records": 0, "historical_broad_date_records": 0, "labor_hours_status": "not_available", "expenses_eur": None, "payments_eur": None, "treatments": 0, "treatments_completed": 0, "treatment_records": 0, "lab_samples": 0, "olives_kg": None, "oil_l": None, "history_source": None}
        for year in range(from_year, to_year + 1)
    }
    queries = {
        "harvest": "SELECT s.vintage_year year,COALESCE(SUM(h.weight_kg),0) harvest_kg,COUNT(h.id) harvest_lots FROM seasons s LEFT JOIN harvest_lots h ON h.season_id=s.id WHERE s.estate_id=%s AND s.vintage_year BETWEEN %s AND %s GROUP BY s.vintage_year",
        "cellar": "SELECT s.vintage_year year,COALESCE(SUM(w.volume_l),0) cellar_l FROM seasons s LEFT JOIN wine_lots w ON w.season_id=s.id WHERE s.estate_id=%s AND s.vintage_year BETWEEN %s AND %s GROUP BY s.vintage_year",
        "labor": "SELECT YEAR(work_date) year,COUNT(*) labor_entries,COALESCE(SUM(COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)),0) recorded_labor_hours FROM labor_entries WHERE estate_id=%s AND YEAR(work_date) BETWEEN %s AND %s GROUP BY YEAR(work_date)",
        "treatments": "SELECT YEAR(application_date) year,SUM(status='completed') treatments,SUM(status='completed') treatments_completed,COUNT(*) treatment_records FROM spray_applications WHERE estate_id=%s AND YEAR(application_date) BETWEEN %s AND %s GROUP BY YEAR(application_date)",
        "labs": "SELECT COALESCE(vintage_year,YEAR(lab_date)) year,COUNT(*) lab_samples FROM lab_samples WHERE estate_id=%s AND COALESCE(vintage_year,YEAR(lab_date)) BETWEEN %s AND %s GROUP BY COALESCE(vintage_year,YEAR(lab_date))",
        "olives": "SELECT record_year year,COALESCE(SUM(olives_harvested_kg),0) olives_kg,COALESCE(SUM(oil_liters),0) oil_l FROM olive_records WHERE estate_id=%s AND record_year BETWEEN %s AND %s GROUP BY record_year",
    }
    if include_finance:
        queries["historical_costs"] = "SELECT record_year year,SUM(CASE WHEN included_in_totals=1 THEN amount_eur ELSE 0 END) expenses_eur,SUM(CASE WHEN record_kind='payment' THEN amount_eur ELSE 0 END) payments_eur FROM historical_cost_records WHERE estate_id=%s AND record_year BETWEEN %s AND %s GROUP BY record_year"
    for sql in queries.values():
        for row in fetch_all(sql, (estate_id(), from_year, to_year)):
            year = int(row.pop("year"))
            years.setdefault(year, {"year": year}).update(row)
    merge_historical_work_overview(years, from_year, to_year)
    merge_historical_fact_overview(years, from_year, to_year)
    for row in fetch_all(
        "SELECT vintage_year year,"
        "COALESCE(MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN grapes_kg END),SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN grapes_kg END)) summary_harvest_kg,"
        "COALESCE(MAX(CASE WHEN LOWER(TRIM(variety_name))='vintage total' THEN wine_l END),SUM(CASE WHEN LOWER(TRIM(variety_name))<>'vintage total' THEN wine_l END)) summary_cellar_l "
        "FROM vintage_summaries WHERE estate_id=%s AND vintage_year BETWEEN %s AND %s GROUP BY vintage_year",
        (estate_id(), from_year, to_year),
    ):
        year = int(row["year"])
        item = years.setdefault(year, {"year": year})
        if not item.get("harvest_kg"):
            item["harvest_kg"] = row.get("summary_harvest_kg")
        if not item.get("cellar_l"):
            item["cellar_l"] = row.get("summary_cellar_l")
        item["history_source"] = "reconciled vintage summary"
    for item in years.values():
        recorded = item.pop("recorded_labor_hours", None)
        historical = item.pop("historical_labor_hours", None)
        if recorded is not None or historical is not None:
            item["labor_hours"] = float(recorded or 0) + float(historical or 0)
        historical_records = int(item.get("historical_work_records") or 0)
        known_records = int(item.get("historical_known_hour_records") or 0)
        if historical_records and known_records == historical_records:
            item["labor_hours_status"] = "complete"
        elif historical_records and (known_records or int(item.get("labor_entries") or 0)):
            item["labor_hours_status"] = "partial"
        elif historical_records:
            item["labor_hours_status"] = "not_recorded"
        elif int(item.get("labor_entries") or 0):
            item["labor_hours_status"] = "recorded"
    return json_ready([years[year] for year in sorted(years, reverse=True)])
