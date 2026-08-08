from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import IntegrityError

from .config import Settings, get_settings, runtime_option
from .cellar_demo import cellar_guardrails, demo_cellar, demo_enabled, evaluate_cellar_tanks
from .db import fetch_all, fetch_one, run_migrations, transaction
from .display_data import display_payload, system_status_payload, weather_context_payload
from .fattureincloud import pull_fattureincloud
from .ha_auth import home_assistant_token
from .etna import etna_status
from .intelligence import analyze_intake, ask_assistant, integration_loop, poll_gmail_once, predict_next_treatment, refresh_disease_pressure, run_full_refresh, save_intake_file
from .models import (
    ActivityCreate,
    BlockCreate,
    CashTransactionCreate,
    FinancialDocumentCreate,
    HarvestCreate,
    LabSampleCreate,
    TaskCreate,
    TaskStatusUpdate,
    VarietyCreate,
    WeatherObservationCreate,
)
from .publisher import publishing_loop
from .quick_entry import save_quick_entry
from .service import audit, estate_id, json_ready, new_id, public_harvest_feed, season_for_year
from .weather_history import import_baiamonte_weather_csv


def authorize(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if (
        settings.trust_home_assistant_ingress
        and request.headers.get("X-Ingress-Path")
        and request.headers.get("X-Remote-User-Name")
    ):
        return
    if settings.api_key and x_api_key == settings.api_key:
        return
    raise HTTPException(status_code=401, detail="Valid API key required")


def finance_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.finance_usernames.split(",") if name.strip()}


def operations_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.operations_usernames.split(",") if name.strip()}


def viewer_usernames(settings: Settings) -> set[str]:
    return {name.strip().casefold() for name in settings.viewer_usernames.split(",") if name.strip()}


def authorize_write(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    if username in operations_usernames(settings):
        return
    raise HTTPException(status_code=403, detail="This Home Assistant account has view-only vineyard access")


def authorize_finance(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    if username and username in finance_usernames(settings):
        return
    raise HTTPException(status_code=403, detail="Finance access is limited to the private finance group")


def authorize_crew(x_crew_token: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.crew_entry_token or x_crew_token != settings.crew_entry_token:
        raise HTTPException(status_code=401, detail="Valid crew entry code required")


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    tasks = [asyncio.create_task(integration_loop())]
    if get_settings().public_publish_url:
        tasks.append(asyncio.create_task(publishing_loop()))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Baiamonte Vineyard API", version="1.0.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
attachment_root = Path(os.getenv("ATTACHMENT_ROOT", "/data/baiamonte-attachments"))

WEATHER_MAP_STYLE = """
<style id="baiamonte-weather-map-mode">
html,body,.shell,main,#overview,.overview-grid,.map-panel{width:100%!important;height:100%!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important}
body{background:#071014!important}
aside,main>header,.hero,.summary-strip,.status-column,.lower-grid,.section-head,.map-panel>.panel-head,.map-panel>.map-footer{display:none!important}
main,.page#overview,.overview-grid,.map-panel{display:block!important;margin:0!important}
.map-panel{border:0!important;border-radius:0!important;box-shadow:none!important;background:#071014!important}
.radar-map{width:100%!important;height:100vh!important;min-height:100vh!important;border:0!important;border-radius:0!important}
.map-controls,.weather-status,.weather-attribution,.altitude-legend,.map-attribution{z-index:40!important}
@media(prefers-reduced-motion:reduce){.sweep,.range-ring{animation:none!important}}
</style>
"""


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, error: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with existing data", "code": error.args[0]})


@app.get("/health")
def health() -> dict[str, Any]:
    row = fetch_one("SELECT 1 AS database_ok")
    return {"ok": True, "database": bool(row and row["database_ok"] == 1)}


@app.post("/api/v1/system/refresh", dependencies=[Depends(authorize_write)])
async def refresh_entire_system() -> dict[str, Any]:
    """Run the same complete refresh used by the configured master schedule."""
    return await run_full_refresh()


@app.get("/api/v1/weather/current", dependencies=[Depends(authorize)])
def current_weather() -> dict[str, Any]:
    return weather_context_payload()


@app.get("/api/v1/reference", dependencies=[Depends(authorize)])
def reference(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return json_ready({
        "estate": fetch_one("SELECT * FROM estates WHERE id=%s", (estate_id(),)),
        "season": fetch_one("SELECT * FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)),
        "blocks": fetch_all("SELECT * FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),)),
        "varieties": fetch_all("SELECT * FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),)),
        "wine_lots": fetch_all("SELECT id,code,name,stage,volume_l,current_container_id FROM wine_lots WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "containers": fetch_all("SELECT id,code,name,container_type,capacity_l,status FROM cellar_containers WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),)),
        "products": fetch_all("SELECT id,sku,name,product_type,category_name,unit,track_inventory FROM products WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),)),
        "categories": ["canopy", "cultivation", "fertilizer", "irrigation", "maintenance", "mowing", "pruning", "scouting", "treatment", "harvest", "cellar", "general"],
    })


@app.get("/api/v1/session", dependencies=[Depends(authorize)])
def session_access(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username = (request.headers.get("X-Remote-User-Name") or "api").strip()
    normalized = username.casefold()
    return {
        "username": username,
        "display_name": request.headers.get("X-Remote-User-Display-Name") or username,
        "permissions": {
            "view": normalized in operations_usernames(settings) | viewer_usernames(settings),
            "write": normalized in operations_usernames(settings),
            "finance": normalized in finance_usernames(settings),
        },
    }


@app.post("/api/v1/quick-entry/{record_type}", status_code=201, dependencies=[Depends(authorize_write)])
def quick_entry(
    record_type: str,
    payload: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if record_type == "financial_document":
        authorize_finance(request, x_api_key, settings)
        raise HTTPException(405, "Finance is read-only here; pull authoritative records from Fatture in Cloud")
    try:
        return save_quick_entry(record_type, payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


ATTACHMENT_ENTITIES = {
    "activity": "work_activities",
    "harvest": "harvest_lots",
    "cellar_operation": "cellar_operations",
    "cellar_lot": "wine_lots",
    "fermentation": "fermentation_observations",
    "equipment_event": "equipment_service_events",
    "maturity_sample": "maturity_samples",
    "scouting": "scouting_observations",
    "phenology": "phenology_observations",
    "treatment": "spray_applications",
    "labor": "labor_entries",
    "olive": "olive_records",
    "issue": "issues_decisions",
    "lab_sample": "lab_samples",
}


@app.post("/api/v1/attachments/{entity_type}/{entity_id}", status_code=201, dependencies=[Depends(authorize_write)])
async def add_entity_attachment(entity_type: str, entity_id: str, request: Request, file: UploadFile = File(...), caption: str = Form("")) -> dict[str, Any]:
    table = ATTACHMENT_ENTITIES.get(entity_type)
    if not table:
        raise HTTPException(422, "This record type does not accept attachments")
    if not fetch_one(f"SELECT id FROM {table} WHERE id=%s AND estate_id=%s", (entity_id, estate_id())):
        raise HTTPException(404, "Record not found")
    data = await file.read(15 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Each photo or file must be 15 MB or smaller")
    media_type = file.content_type or "application/octet-stream"
    if not (media_type.startswith("image/") or media_type == "application/pdf"):
        raise HTTPException(422, "Choose a photo, screenshot, or PDF")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "attachment").name)[:180]
    attachment_id = new_id()
    attachment_root.mkdir(parents=True, exist_ok=True)
    stored = attachment_root / f"{attachment_id}-{safe_name}"
    stored.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (attachment_id, estate_id(), entity_type, entity_id, safe_name, str(stored), media_type, digest, caption or None, request.headers.get("X-Remote-User-Name") or "api"),
        )
        audit(cursor, "attach", entity_type, entity_id, {"attachment_id": attachment_id, "filename": safe_name})
    return {"id": attachment_id, "entity_id": entity_id}


@app.get("/api/v1/attachments/{attachment_id}/file", dependencies=[Depends(authorize)])
def entity_attachment_file(attachment_id: str) -> FileResponse:
    row = fetch_one("SELECT * FROM entity_attachments WHERE id=%s AND estate_id=%s", (attachment_id, estate_id()))
    if not row or not Path(row["stored_path"]).is_file():
        raise HTTPException(404, "Attachment not found")
    return FileResponse(row["stored_path"], media_type=row.get("media_type"), filename=row.get("original_filename"))


@app.post("/api/v1/crew/hours", status_code=201, dependencies=[Depends(authorize_crew)])
def crew_hours(payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    values = {
        **payload,
        "person_or_crew": settings.crew_default_name,
        "role": "Contractor",
        "payroll_scope": "contractor",
        "payment_status": "verification_needed",
        "entry_source": "crew_portal",
    }
    try:
        return save_quick_entry("labor", values)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/dashboard", dependencies=[Depends(authorize)])
def dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year))
    season_id = season["id"] if season else ""
    return json_ready({
        "year": year,
        "counts": {
            "open_tasks": (fetch_one("SELECT COUNT(*) n FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress')", (estate_id(),)) or {"n": 0})["n"],
            "open_alerts": (fetch_one("SELECT COUNT(*) n FROM alerts WHERE estate_id=%s AND status='open'", (estate_id(),)) or {"n": 0})["n"],
            "harvest_kg": (fetch_one("SELECT COALESCE(SUM(weight_kg),0) n FROM harvest_lots WHERE season_id=%s", (season_id,)) or {"n": 0})["n"],
            "work_hours": (fetch_one("SELECT COALESCE(SUM(labor_hours),0) n FROM work_activities WHERE season_id=%s", (season_id,)) or {"n": 0})["n"],
        },
        "tasks": fetch_all("SELECT id,title,category,priority,status,due_date,block_code,block_name,days_until_due FROM v_open_work WHERE estate_id=%s ORDER BY due_date IS NULL,due_date LIMIT 12", (estate_id(),)),
        "activities": fetch_all("SELECT a.id,a.activity_date,a.title,a.category,a.status,a.labor_hours,b.code block_code FROM work_activities a LEFT JOIN vineyard_blocks b ON b.id=a.block_id WHERE a.estate_id=%s ORDER BY a.activity_date DESC LIMIT 12", (estate_id(),)),
        "harvest": fetch_all("SELECT * FROM v_harvest_summary WHERE estate_id=%s AND vintage_year=%s ORDER BY variety_name", (estate_id(), year)),
        "weather": fetch_all("SELECT observed_at,temp_c,humidity_pct,rain_mm,wind_kph,soil_moisture_pct FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 48", (estate_id(),))[::-1],
        "alerts": fetch_all("SELECT id,severity,title,message,triggered_at FROM alerts WHERE estate_id=%s AND status='open' ORDER BY triggered_at DESC LIMIT 8", (estate_id(),)),
    })


@app.get("/api/display-data", dependencies=[Depends(authorize)])
def ingress_display_data() -> dict[str, Any]:
    return display_payload()


@app.get("/api/v1/grapes/dashboard", dependencies=[Depends(authorize)])
def grape_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
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
        "WHERE v.estate_id=%s AND v.active=1 ORDER BY v.name",
        (season_id, season_id, estate_id()),
    )
    forecasts = fetch_all(
        "SELECT g.variety_id,g.observed_through,g.observed_gdd,g.target_gdd,g.predicted_date,g.final_forecast_date,g.confidence,g.calibration_evidence "
        "FROM gdd_forecasts g JOIN (SELECT variety_id,MAX(computed_at) computed_at FROM gdd_forecasts WHERE season_id=%s GROUP BY variety_id) latest "
        "ON latest.variety_id=g.variety_id AND latest.computed_at=g.computed_at WHERE g.season_id=%s",
        (season_id, season_id),
    ) if season_id else []
    forecast_by_variety = {row["variety_id"]: row for row in forecasts}
    maturity_rows = fetch_all(
        "SELECT m.* FROM maturity_samples m JOIN (SELECT variety_id,MAX(sampled_at) sampled_at FROM maturity_samples WHERE season_id=%s AND variety_id IS NOT NULL GROUP BY variety_id) latest "
        "ON latest.variety_id=m.variety_id AND latest.sampled_at=m.sampled_at WHERE m.season_id=%s",
        (season_id, season_id),
    ) if season_id else []
    maturity_by_variety = {row["variety_id"]: row for row in maturity_rows}
    recent_weather = fetch_one(
        "SELECT MAX(weather_date) observed_through,SUM(rain_mm) rain_7d_mm,AVG(temp_avg_c) temp_avg_7d_c,MAX(temp_max_c) temp_max_7d_c,SUM(gdd_base10) gdd_7d "
        "FROM weather_daily WHERE estate_id=%s AND weather_date>=CURDATE()-INTERVAL 7 DAY",
        (estate_id(),),
    ) or {}
    scouting_rows = fetch_all(
        "SELECT bv.variety_id,MAX(so.observed_at) observed_at,SUBSTRING_INDEX(GROUP_CONCAT(so.issue_type ORDER BY so.observed_at DESC SEPARATOR '||'),'||',1) issue_type,"
        "MAX(so.action_required) action_required FROM scouting_observations so JOIN block_varieties bv ON bv.block_id=so.block_id "
        "WHERE so.season_id=%s GROUP BY bv.variety_id",
        (season_id,),
    ) if season_id else []
    scouting_by_variety = {row["variety_id"]: row for row in scouting_rows}
    chemistry_rows = fetch_all(
        "SELECT s.variety_id,s.lab_date,r.analyte_code,r.analyte_name,r.numeric_value,r.unit "
        "FROM lab_samples s JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND s.season_id=%s AND s.sample_type='grape' AND r.numeric_value IS NOT NULL "
        "ORDER BY s.lab_date DESC,s.created_at DESC",
        (estate_id(), season_id),
    ) if season_id else []
    chemistry: dict[str, dict[str, Any]] = {}
    for row in chemistry_rows:
        item = chemistry.setdefault(row["variety_id"] or "unassigned", {"lab_date": row["lab_date"], "results": {}})
        code = (row["analyte_code"] or row["analyte_name"]).casefold()
        if code not in item["results"]:
            item["results"][code] = {"value": row["numeric_value"], "unit": row["unit"], "name": row["analyte_name"]}
    for row in varieties:
        planned = float(row.get("planned_kg") or 0)
        harvested = float(row.get("harvested_kg") or 0)
        row["remaining_kg"] = max(planned - harvested, 0) if row.get("planned_kg") is not None else None
        row["completion_pct"] = round(harvested / planned * 100, 1) if planned else None
        row["forecast"] = forecast_by_variety.get(row["id"])
        row["latest_grape_lab"] = chemistry.get(row["id"])
        maturity = maturity_by_variety.get(row["id"]) or {}
        scouting = scouting_by_variety.get(row["id"]) or {}
        forecast = row["forecast"] or {}
        candidates = [maturity.get("provisional_pick_date"), forecast.get("final_forecast_date"), forecast.get("predicted_date"), row.get("planned_pick_date")]
        recommended = next((value for value in candidates if value), None)
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
        weather_notes = []
        if recent_weather.get("rain_7d_mm") is not None:
            weather_notes.append(f"{float(recent_weather['rain_7d_mm']):.1f} mm rain / 7d")
        if recent_weather.get("temp_max_7d_c") is not None:
            weather_notes.append(f"{float(recent_weather['temp_max_7d_c']):.1f}°C max / 7d")
        row["harvest_recommendation"] = {
            "recommended_pick_date": recommended,
            "approval_status": "recorded" if row.get("first_pick_date") else "ready_for_approval" if maturity.get("decision") == "ready" else "hold" if maturity.get("decision") == "hold" else "review",
            "confidence": "high" if len(evidence) >= 3 else "medium" if len(evidence) >= 2 else "low",
            "evidence": evidence,
            "weather_summary": " · ".join(weather_notes),
            "note": "Decision-support date only; confirm current fruit, forecast, crew and cellar readiness before picking.",
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
    planned_total = float(metrics.get("planned_kg") or 0)
    harvested_total = float(metrics.get("harvested_kg") or 0)
    metrics["completion_pct"] = round(harvested_total / planned_total * 100, 1) if planned_total else None
    vintages = fetch_all(
        "SELECT vintage_year,SUM(grapes_kg) grapes_kg,SUM(wine_l) wine_l,SUM(cassette_count) cassette_count,"
        "GROUP_CONCAT(DISTINCT evidence_status ORDER BY evidence_status SEPARATOR ', ') evidence_status,"
        "GROUP_CONCAT(DISTINCT reconciliation_note SEPARATOR '; ') reconciliation_note "
        "FROM vintage_summaries WHERE estate_id=%s GROUP BY vintage_year ORDER BY vintage_year",
        (estate_id(),),
    )
    blocks = fetch_all(
        "SELECT b.id,b.code,b.name,b.area_ha,GROUP_CONCAT(DISTINCT v.name ORDER BY v.name SEPARATOR ', ') varieties,"
        "SUM(h.weight_kg) harvested_kg,COUNT(DISTINCT h.id) lot_count "
        "FROM vineyard_blocks b LEFT JOIN block_varieties bv ON bv.block_id=b.id LEFT JOIN grape_varieties v ON v.id=bv.variety_id "
        "LEFT JOIN harvest_lots h ON h.block_id=b.id AND h.season_id=%s WHERE b.estate_id=%s AND b.active=1 "
        "GROUP BY b.id,b.code,b.name,b.area_ha ORDER BY b.code",
        (season_id, estate_id()),
    )
    harvest_lots = fetch_all(
        "SELECT h.id,h.harvested_at,h.weight_kg,h.crate_count,h.avg_crate_kg,h.destination,h.brix,h.babo,h.ph,h.ta_g_l,h.condition_grade,h.notes,v.name variety_name,b.code block_code "
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
    blend_history = fetch_all(
        "SELECT s.vintage_year,b.code,b.name,b.target_grapes_kg,b.target_volume_l,b.planned_bottles,b.crate_weight_kg,b.expected_yield_l_per_kg,b.components_text,b.decision_status,"
        "(SELECT SUM(w.fruit_kg) FROM wine_lots w WHERE w.season_id=s.id AND (w.code=b.code OR w.name=b.name)) actual_grapes_kg,"
        "(SELECT SUM(COALESCE(w.volume_l,w.initial_l)) FROM wine_lots w WHERE w.season_id=s.id AND (w.code=b.code OR w.name=b.name)) actual_volume_l "
        "FROM blend_plans b JOIN seasons s ON s.id=b.season_id WHERE b.estate_id=%s ORDER BY s.vintage_year DESC,b.code",
        (estate_id(),),
    )
    return json_ready({"year": year, "metrics": metrics, "varieties": varieties, "vintages": vintages, "blocks": blocks, "harvest_lots": harvest_lots, "cellar_lots": cellar_lots, "blend_plans": blend_plans, "blend_history": blend_history})


@app.get("/api/v1/cellar/dashboard", dependencies=[Depends(authorize)])
def cellar_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    settings = get_settings()
    if demo_enabled(settings):
        return json_ready(demo_cellar(settings, year))
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    season_id = season.get("id", "")
    tanks = fetch_all(
        "SELECT c.id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.sensor_entity_id,c.status,"
        "w.id wine_lot_id,w.code lot_code,w.name lot_name,w.stage,w.volume_l,w.variety_summary,w.started_at,"
        "(SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) temp_c,"
        "(SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) density_sg,"
        "(SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) brix,"
        "(SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) ph,"
        "(SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) reading_at,"
        "(SELECT f.next_check_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) next_check_at "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.season_id=%s "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (season_id, estate_id()),
    )
    for tank in tanks:
        capacity = float(tank.get("capacity_l") or 0)
        volume = float(tank.get("volume_l") or 0)
        tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
        tank["source"] = "Tank monitor" if tank.get("sensor_entity_id") else "Recorded reading"
    guard_alerts = evaluate_cellar_tanks(tanks, settings)
    processes = fetch_all(
        "SELECT f.id,f.observed_at,f.vessel_name,f.stage,f.temp_c,f.density_sg,f.brix,f.ph,f.cap_management,f.addition_action,f.sensory_observation,f.owner_text,f.next_check_at,f.status,w.code lot_code,w.name lot_name "
        "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id WHERE f.estate_id=%s "
        "AND (w.season_id=%s OR w.season_id IS NULL) ORDER BY COALESCE(f.next_check_at,f.observed_at) DESC LIMIT 30",
        (estate_id(), season_id),
    )
    return json_ready({"year": year, "demo": False, "tanks": tanks, "processes": processes, "guardrails": cellar_guardrails(settings), "guard_alerts": guard_alerts})


@app.get("/api/v1/olives/dashboard", dependencies=[Depends(authorize)])
def olive_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return json_ready({
        "year": year,
        "metrics": fetch_one(
            "SELECT SUM(olives_harvested_kg) olives_kg,SUM(oil_liters) oil_liters,SUM(labor_hours) labor_hours,"
            "AVG(yield_pct) avg_yield_pct,COUNT(*) record_count FROM olive_records WHERE estate_id=%s AND record_year=%s",
            (estate_id(), year),
        ) or {},
        "records": fetch_all("SELECT * FROM olive_records WHERE estate_id=%s AND record_year=%s ORDER BY COALESCE(record_date,mill_date) DESC,id DESC", (estate_id(), year)),
        "history": fetch_all(
            "SELECT record_year,SUM(olives_harvested_kg) olives_kg,SUM(oil_liters) oil_liters,AVG(yield_pct) avg_yield_pct,SUM(labor_hours) labor_hours,COUNT(*) record_count "
            "FROM olive_records WHERE estate_id=%s GROUP BY record_year ORDER BY record_year",
            (estate_id(),),
        ),
    })


@app.get("/api/v1/blocks/plan", dependencies=[Depends(authorize)])
def block_plan(year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year))
    season_id = season["id"] if season else ""
    return json_ready(fetch_all(
        "SELECT b.id,b.code,b.name,b.area_ha,b.vine_count,b.planted_year,b.training_system,b.soil_type,b.elevation_m,b.aspect,b.irrigation_available,"
        "GROUP_CONCAT(DISTINCT v.name ORDER BY v.name SEPARATOR ', ') varieties,"
        "(SELECT CONCAT(p.stage_name,'|',p.stage_code,'|',COALESCE(p.percent_complete,''),'|',p.observed_date) FROM phenology_observations p WHERE p.block_id=b.id AND p.season_id=%s ORDER BY p.observed_date DESC LIMIT 1) latest_phenology,"
        "(SELECT COUNT(*) FROM tasks t WHERE t.block_id=b.id AND t.status IN ('planned','in_progress')) open_tasks,"
        "(SELECT COUNT(*) FROM scouting_observations so WHERE so.block_id=b.id AND so.season_id=%s AND so.action_required=1) action_items,"
        "(SELECT SUM(h.weight_kg) FROM harvest_lots h WHERE h.block_id=b.id AND h.season_id=%s) harvested_kg "
        "FROM vineyard_blocks b LEFT JOIN block_varieties bv ON bv.block_id=b.id LEFT JOIN grape_varieties v ON v.id=bv.variety_id "
        "WHERE b.estate_id=%s AND b.active=1 GROUP BY b.id,b.code,b.name,b.area_ha,b.vine_count,b.planted_year,b.training_system,b.soil_type,b.elevation_m,b.aspect,b.irrigation_available ORDER BY b.code",
        (season_id, season_id, season_id, estate_id()),
    ))


@app.get("/api/v1/vineyard/atlas", dependencies=[Depends(authorize)])
def vineyard_atlas() -> dict[str, Any]:
    return json_ready({
        "estate": fetch_one("SELECT name,latitude,longitude,total_area_ha FROM estates WHERE id=%s", (estate_id(),)) or {},
        "parcels": fetch_all(
            "SELECT municipality,cadastral_sheet,parcel_number,tenure,tenure_start,tenure_end,cadastral_area_ha,conducted_area_ha,buildings_m2,official_vineyard_area_ha,notes "
            "FROM cadastral_parcels WHERE estate_id=%s ORDER BY municipality,cadastral_sheet,parcel_number",
            (estate_id(),),
        ),
        "terraces": fetch_all(
            "SELECT terrace_code,cohort,training_system,allocated_vines,spacing_m,reconciliation_basis,confidence,field_census_status,live_vines,dead_missing_vines,replacement_new_vines,notes "
            "FROM vineyard_terraces WHERE estate_id=%s ORDER BY terrace_code",
            (estate_id(),),
        ),
        "nursery": fetch_all(
            "SELECT n.invoice_date,n.invoice_number,n.supplied_variety_name,n.quantity,n.cohort_use,n.mapping_status,n.notes,v.name canonical_variety "
            "FROM nursery_deliveries n LEFT JOIN grape_varieties v ON v.id=n.variety_id WHERE n.estate_id=%s ORDER BY n.invoice_date DESC,n.supplied_variety_name",
            (estate_id(),),
        ),
    })


@app.get("/api/v1/issues", dependencies=[Depends(authorize)])
def issues_and_decisions(year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT * FROM issues_decisions WHERE estate_id=%s AND (YEAR(opened_date)=%s OR status IN ('open','monitoring')) "
        "ORDER BY FIELD(status,'open','monitoring','deferred','resolved'),FIELD(priority,'critical','high','medium','low'),due_date IS NULL,due_date DESC",
        (estate_id(), year),
    ))


@app.patch("/api/v1/issues/{issue_id}", dependencies=[Depends(authorize_write)])
def update_issue_or_decision(issue_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed = {"priority", "decision_action", "owner_text", "due_date", "status", "closed_date", "notes"}
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(422, "Unsupported fields: " + ", ".join(sorted(unknown)))
    if payload.get("status") not in {None, "open", "monitoring", "resolved", "deferred"}:
        raise HTTPException(422, "Choose open, monitoring, resolved or deferred")
    if payload.get("priority") not in {None, "low", "medium", "high", "critical"}:
        raise HTTPException(422, "Choose a valid priority")
    values = dict(payload)
    if values.get("status") == "resolved" and not values.get("closed_date"):
        values["closed_date"] = date.today()
    assignments = ",".join(f"{key}=%s" for key in values)
    if not assignments:
        raise HTTPException(422, "No changes supplied")
    with transaction() as (_, cursor):
        changed = cursor.execute(f"UPDATE issues_decisions SET {assignments} WHERE id=%s AND estate_id=%s", (*values.values(), issue_id, estate_id()))
        if not changed and not fetch_one("SELECT id FROM issues_decisions WHERE id=%s AND estate_id=%s", (issue_id, estate_id())):
            raise HTTPException(404, "Issue not found")
        audit(cursor, "update", "issue", issue_id, values, request.headers.get("X-Remote-User-Name") or "api")
    return {"saved": True, "id": issue_id}


@app.get("/api/v1/projections", dependencies=[Depends(authorize)])
def operational_projections(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    grapes = grape_dashboard(year)
    vintages = grapes["vintages"]
    conversion_rows = [row for row in vintages if row.get("grapes_kg") and row.get("wine_l") and int(row["vintage_year"]) < year]
    conversion = sum(float(row["wine_l"]) / float(row["grapes_kg"]) for row in conversion_rows) / len(conversion_rows) if conversion_rows else 0.70
    blend_plans = grapes.get("blend_plans") or []
    blend_kg = sum(float(row.get("target_grapes_kg") or 0) for row in blend_plans) or None
    blend_volume = sum(float(row.get("estimated_volume_l") or row.get("target_volume_l") or 0) for row in blend_plans) or None
    blend_crates = sum(float(row.get("estimated_crates") or 0) for row in blend_plans) or None
    planned_kg = grapes["metrics"].get("planned_kg")
    harvested_kg = grapes["metrics"].get("harvested_kg")
    basis_kg = blend_kg if blend_kg is not None else planned_kg if planned_kg is not None else harvested_kg
    scenarios = []
    for name, factor in (("Downside", 0.85), ("Working", 1.0), ("Upside", 1.15)):
        kg = float(basis_kg) * factor if basis_kg is not None else None
        base_wine = blend_volume if blend_volume is not None else (float(basis_kg) * conversion if basis_kg is not None else None)
        wine_l = base_wine * factor if base_wine is not None else None
        scenarios.append({"name": name, "grapes_kg": kg, "wine_l": wine_l, "bottle_equivalents": wine_l / 0.75 if wine_l is not None else None, "crates_15kg": kg / 15 if kg is not None else None})
    production_forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg,crates_15kg FROM production_forecasts WHERE estate_id=%s AND scenario='base' AND vintage_year BETWEEN %s AND %s ORDER BY vintage_year,variety_name",
        (estate_id(), year, year + 5),
    )
    forecast_totals = []
    for forecast_year in sorted({int(row["vintage_year"]) for row in production_forecasts}):
        rows = [row for row in production_forecasts if int(row["vintage_year"]) == forecast_year]
        total_kg = sum(float(row.get("grape_kg") or 0) for row in rows)
        forecast_totals.append({"vintage_year": forecast_year, "grape_kg": total_kg, "crates_15kg": sum(int(row.get("crates_15kg") or 0) for row in rows), "wine_l": round(total_kg * 0.70), "bottles_750ml": int(total_kg * 0.70 / 0.75)})
    return json_ready({
        "year": year,
        "basis": "current blend plan" if blend_kg is not None else "harvest plan" if planned_kg is not None else "harvested weight" if harvested_kg is not None else "missing",
        "historical_conversion_l_per_kg": conversion,
        "scenarios": scenarios,
        "varieties": grapes["varieties"],
        "actual_history": vintages,
        "blend_plan": {"count": len(blend_plans), "target_grapes_kg": blend_kg, "estimated_volume_l": blend_volume, "estimated_crates": blend_crates, "crate_weight_kg": 15},
        "production_forecasts": production_forecasts,
        "production_forecast_totals": forecast_totals,
        "grape_allocations": fetch_all("SELECT grape_name,total_kg,total_crates_15kg,wine_destination,blend_kg,blend_crates_15kg,varietal_kg,varietal_crates_15kg,field_instruction FROM grape_allocation_plans WHERE estate_id=%s AND vintage_year=%s ORDER BY grape_name", (estate_id(), year)),
        "wine_outputs": fetch_all("SELECT finished_wine,composition,grape_kg,wine_l,bottles_750ml FROM wine_output_plans WHERE estate_id=%s AND vintage_year=%s ORDER BY finished_wine", (estate_id(), year)),
        "guardrail": "Planning estimate only. Final picking and production decisions require current maturity, weather, logistics and enologist approval.",
    })


def ensure_finance_party(cursor: Any, name: str | None, party_type: str) -> str | None:
    if not name:
        return None
    row = fetch_one("SELECT id FROM finance_parties WHERE estate_id=%s AND name=%s", (estate_id(), name))
    if row:
        return row["id"]
    party_id = new_id()
    cursor.execute("INSERT INTO finance_parties (id,estate_id,party_type,name,source) VALUES (%s,%s,%s,%s,'home-assistant')", (party_id, estate_id(), party_type, name))
    return party_id


@app.post("/api/v1/finance/documents", status_code=201, dependencies=[Depends(authorize_finance)])
def create_financial_document(payload: FinancialDocumentCreate) -> dict[str, str]:
    raise HTTPException(405, "Finance is read-only here; pull authoritative records from Fatture in Cloud")
    # Retained below for backwards-compatible schema documentation only.
    record_id = new_id()
    values = payload.model_dump()
    with transaction() as (_, cursor):
        party_type = "customer" if values["document_type"] == "sales_invoice" else "supplier"
        party_id = ensure_finance_party(cursor, values.pop("party_name"), party_type)
        gross = values["taxable_amount"] + values["vat_amount"] - values["withholding_tax"]
        status = "issued" if values["document_type"] == "sales_invoice" else "received"
        cursor.execute("INSERT INTO financial_documents (id,estate_id,document_type,document_number,document_date,due_date,party_id,taxable_amount,vat_amount,withholding_tax,gross_total,status,payment_status,source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'home-assistant',%s)", (record_id, estate_id(), values["document_type"], values["document_number"], values["document_date"], values["due_date"], party_id, values["taxable_amount"], values["vat_amount"], values["withholding_tax"], gross, status, values["payment_status"], values["notes"]))
        audit(cursor, "create", "financial_document", record_id, payload.model_dump())
    return {"id": record_id}


@app.post("/api/v1/finance/cash", status_code=201, dependencies=[Depends(authorize_finance)])
def create_cash_transaction(payload: CashTransactionCreate) -> dict[str, str]:
    raise HTTPException(405, "Finance is read-only here; pull authoritative records from Fatture in Cloud")
    # Retained below for backwards-compatible schema documentation only.
    record_id = new_id()
    values = payload.model_dump()
    with transaction() as (_, cursor):
        account = fetch_one("SELECT id FROM cash_accounts WHERE estate_id=%s AND name=%s", (estate_id(), values["account_name"]))
        account_id = account["id"] if account else new_id()
        if not account:
            cursor.execute("INSERT INTO cash_accounts (id,estate_id,name,account_type) VALUES (%s,%s,%s,%s)", (account_id, estate_id(), values["account_name"], values["account_type"]))
        party_id = ensure_finance_party(cursor, values["party_name"], "other")
        cursor.execute("INSERT INTO cash_transactions (id,estate_id,cash_account_id,transaction_date,description,party_id,transaction_type,amount_in,amount_out,source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'home-assistant',%s)", (record_id, estate_id(), account_id, values["transaction_date"], values["description"], party_id, values["transaction_type"], values["amount_in"], values["amount_out"], values["notes"]))
        audit(cursor, "create", "cash_transaction", record_id, payload.model_dump())
    return {"id": record_id}


def finance_dashboard_payload(year: int) -> dict[str, Any]:
    actual = fetch_one("SELECT COALESCE(SUM(revenue_net),0) revenue,COALESCE(SUM(cost_net),0) cost,COALESCE(SUM(output_vat),0) output_vat,COALESCE(SUM(input_vat),0) input_vat FROM v_monthly_actual_finance WHERE estate_id=%s AND fiscal_year=%s", (estate_id(), year)) or {}
    plan = fetch_one("SELECT COALESCE(SUM(budget_revenue),0) budget_revenue,COALESCE(SUM(budget_cost),0) budget_cost,COALESCE(SUM(latest_forecast_revenue),0) forecast_revenue,COALESCE(SUM(latest_forecast_cost),0) forecast_cost FROM monthly_financial_summary WHERE estate_id=%s AND fiscal_year=%s", (estate_id(), year)) or {}
    annual = fetch_one(
        "SELECT a.*,s.name scenario_name,s.scenario_type FROM annual_financial_summary a "
        "JOIN financial_scenarios s ON s.id=a.scenario_id WHERE a.estate_id=%s AND a.fiscal_year=%s "
        "ORDER BY (s.scenario_type='actual') DESC,s.selected DESC LIMIT 1",
        (estate_id(), year),
    ) or {}
    monthly = fetch_all("SELECT * FROM v_budget_vs_actual WHERE estate_id=%s AND fiscal_year=%s ORDER BY fiscal_month", (estate_id(), year))
    open_documents = fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND payment_status IN ('unpaid','part_paid','unknown') ORDER BY due_date IS NULL,due_date,document_date DESC LIMIT 25", (estate_id(),))
    requirements = fetch_all("SELECT id,category,requirement_name,owner_text,status,due_date,evidence_url,notes FROM funding_requirements WHERE estate_id=%s AND status NOT IN ('complete','not_applicable') ORDER BY due_date IS NULL,due_date LIMIT 25", (estate_id(),))
    annual_history = fetch_all(
        "SELECT YEAR(document_date) finance_year,"
        "SUM(CASE WHEN document_type='sales_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) revenue,"
        "SUM(CASE WHEN document_type='purchase_invoice' AND status<>'void' THEN taxable_amount ELSE 0 END) cost,"
        "SUM(CASE WHEN document_type='delivery_note' AND status<>'void' THEN 1 ELSE 0 END) delivery_notes,"
        "SUM(CASE WHEN document_type IN ('sales_invoice','purchase_invoice','credit_note') THEN 1 ELSE 0 END) invoices "
        "FROM financial_documents WHERE estate_id=%s GROUP BY YEAR(document_date) ORDER BY finance_year",
        (estate_id(),),
    )
    checkpoint = fetch_one("SELECT last_success_at,last_attempt_at,last_error,metadata FROM sync_checkpoints WHERE estate_id=%s AND integration_name='fattureincloud'", (estate_id(),)) or {}
    document_counts = fetch_one(
        "SELECT SUM(document_type='sales_invoice') sales_invoices,SUM(document_type='purchase_invoice') purchase_invoices,SUM(document_type='delivery_note') delivery_notes,SUM(document_type='credit_note') credit_notes FROM financial_documents WHERE estate_id=%s AND YEAR(document_date)=%s",
        (estate_id(), year),
    ) or {}
    elapsed_months = max(1, date.today().month if year == date.today().year else 12)
    projection_factor = 12 / elapsed_months if year == date.today().year else 1
    return json_ready({
        "year": year,
        "actual": {**actual, "result": (actual.get("revenue") or 0) - (actual.get("cost") or 0)},
        "plan": plan,
        "annual": annual,
        "monthly": monthly,
        "cash": fetch_all("SELECT * FROM v_cash_balances WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "receivables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND document_type='sales_invoice' AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(),)),
        "payables": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND document_type='purchase_invoice' AND open_amount>0 ORDER BY due_date,document_date LIMIT 25", (estate_id(),)),
        "recent_documents": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s ORDER BY document_date DESC,id DESC LIMIT 30", (estate_id(),)),
        "document_counts": document_counts,
        "fatture_sync": checkpoint,
        "annual_history": annual_history,
        "projection": {"basis_months": elapsed_months, "revenue": float(actual.get("revenue") or 0) * projection_factor, "cost": float(actual.get("cost") or 0) * projection_factor, "result": (float(actual.get("revenue") or 0) - float(actual.get("cost") or 0)) * projection_factor, "method": "Current year-to-date annualized" if projection_factor != 1 else "Actual full-year total"},
        "open_documents": open_documents,
        "inventory": fetch_all("SELECT * FROM v_inventory_current WHERE estate_id=%s ORDER BY category_name,name", (estate_id(),)),
        "vat": fetch_one("SELECT * FROM vat_returns WHERE estate_id=%s AND fiscal_year=%s ORDER BY FIELD(filing_status,'filed','amended','forecast','draft') LIMIT 1", (estate_id(), year)),
        "funding": fetch_all("SELECT * FROM v_funding_control WHERE estate_id=%s ORDER BY FIELD(priority,'critical','high','medium','low'),deadline LIMIT 30", (estate_id(),)),
        "requirements": requirements,
        "funding_requirements": requirements,
        "capital_projects": fetch_all("SELECT code,name,site,status,budget_low,budget_high,actual_cost,decision_gate FROM capital_projects WHERE estate_id=%s ORDER BY status,name", (estate_id(),)),
        "unit_economics": fetch_one("SELECT * FROM v_vineyard_unit_economics WHERE vintage_year=%s", (year,)),
    })


@app.get("/api/v1/finance/dashboard", dependencies=[Depends(authorize_finance)])
def finance_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return finance_dashboard_payload(year)


@app.get("/api/v1/finance/documents/{document_id}/print", dependencies=[Depends(authorize_finance)], response_class=HTMLResponse)
def print_finance_document(document_id: str) -> HTMLResponse:
    row = fetch_one("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND id=%s", (estate_id(), document_id))
    if not row:
        raise HTTPException(404, "Finance document not found")
    label = "DDT" if row.get("document_type") == "delivery_note" else "Fattura"
    original = row.get("source_document")
    original_link = f'<p><a href="{html.escape(str(original), quote=True)}" target="_blank" rel="noopener">Open authoritative original in Fatture in Cloud</a></p>' if original else "<p>Authoritative original URL will be added by the next Fatture in Cloud pull.</p>"
    page = f"""<!doctype html><html><head><meta charset='utf-8'><title>{label} {html.escape(str(row.get('document_number') or ''))}</title><style>body{{font:16px system-ui;color:#222;max-width:820px;margin:40px auto;padding:20px}}header{{border-bottom:3px solid #d4af37;padding-bottom:18px}}h1{{font-family:Georgia,serif}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin:28px 0}}.total{{font-size:28px}}.note{{color:#666}}button{{padding:10px 16px}}@media print{{button{{display:none}}}}</style></head><body><header><p>TENUTA BAIAMONTE · READ-ONLY ACCOUNTING MIRROR</p><h1>{label} {html.escape(str(row.get('document_number') or ''))}</h1></header><div class='grid'><div><b>Date</b><p>{html.escape(str(row.get('document_date') or ''))}</p></div><div><b>Party</b><p>{html.escape(str(row.get('party_name') or 'Not recorded'))}</p></div><div><b>Status</b><p>{html.escape(str(row.get('payment_status') or row.get('status') or ''))}</p></div><div><b>Net / VAT</b><p>€{float(row.get('taxable_amount') or 0):,.2f} / €{float(row.get('vat_amount') or 0):,.2f}</p></div></div><p class='total'><b>Total €{float(row.get('gross_total') or 0):,.2f}</b></p>{original_link}<p class='note'>This is a reporting copy. Fatture in Cloud remains authoritative.</p><button onclick='window.print()'>Print</button></body></html>"""
    return HTMLResponse(page)


@app.post("/api/v1/finance/fattureincloud/pull", dependencies=[Depends(authorize_finance)])
async def pull_fattureincloud_now() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(pull_fattureincloud)
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO sync_checkpoints (estate_id,integration_name,last_attempt_at,last_error) VALUES (%s,'fattureincloud',NOW(),%s) ON DUPLICATE KEY UPDATE last_attempt_at=NOW(),last_error=VALUES(last_error)", (estate_id(), str(error)[:1000]))
        raise HTTPException(502, "Fatture in Cloud pull failed: " + str(error)[:350]) from error


@app.get("/api/v1/home-assistant/summary", dependencies=[Depends(authorize)])
def home_assistant_summary(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    vineyard = dashboard(year)
    bottle_row = fetch_one(
        "SELECT COALESCE(SUM(quantity_on_hand),0) n FROM v_inventory_current WHERE estate_id=%s AND unit='bt.'",
        (estate_id(),),
    ) or {"n": 0}
    pressure = fetch_one("SELECT disease_name,risk_level,risk_score FROM disease_pressure_assessments WHERE estate_id=%s AND assessment_date=CURDATE() ORDER BY risk_score DESC LIMIT 1", (estate_id(),)) or {}
    sync = fetch_one("SELECT last_success_at,last_error FROM sync_checkpoints WHERE estate_id=%s AND integration_name='home_assistant_gw2000_history'", (estate_id(),)) or {}
    return {
        "status": "online",
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "year": year,
        "open_tasks": vineyard["counts"]["open_tasks"],
        "alerts": vineyard["counts"]["open_alerts"],
        "harvest_kg": vineyard["counts"]["harvest_kg"],
        "work_hours": vineyard["counts"]["work_hours"],
        "bottles_on_hand": bottle_row["n"],
        "disease_pressure_name": pressure.get("disease_name"),
        "disease_pressure_level": pressure.get("risk_level", "unknown"),
        "disease_pressure_score": pressure.get("risk_score"),
        "lab_review_count": (fetch_one("SELECT COUNT(*) n FROM v_lab_decision_queue WHERE estate_id=%s AND (review_status='decision_needed' OR flagged_results>0)", (estate_id(),)) or {"n": 0})["n"],
        "inbox_review_count": (fetch_one("SELECT COUNT(*) n FROM intake_items WHERE estate_id=%s AND review_status IN ('new','ready_for_review','failed')", (estate_id(),)) or {"n": 0})["n"],
        "planned_treatments": (fetch_one("SELECT COUNT(*) n FROM spray_applications WHERE estate_id=%s AND status='planned'", (estate_id(),)) or {"n": 0})["n"],
        "weather_sync_at": sync.get("last_success_at"),
        "weather_sync_error": sync.get("last_error"),
    }


@app.get("/api/v1/home-assistant/finance-summary", dependencies=[Depends(authorize_finance)])
def home_assistant_finance_summary(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    finance = finance_dashboard_payload(year)
    annual = finance["annual"] or {}
    actual = finance["actual"] or {}
    cash_total = sum(float(row.get("current_balance") or 0) for row in finance["cash"])
    inventory_units = sum(float(row.get("quantity_on_hand") or 0) for row in finance["inventory"])
    bottles = sum(float(row.get("quantity_on_hand") or 0) for row in finance["inventory"] if row.get("unit") == "bt.")
    open_funding = sum(1 for row in finance["funding"] if str(row.get("status", "")).lower() not in {"closed", "rejected"})
    return {
        "status": "online",
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "year": year,
        "revenue": actual.get("revenue", annual.get("revenue")),
        "cost": actual.get("cost", annual.get("total_operating_costs")),
        "result": actual.get("result", annual.get("operating_result")),
        "operating_costs": actual.get("cost", annual.get("total_operating_costs")),
        "operating_result": actual.get("result", annual.get("operating_result")),
        "scenario": annual.get("scenario_name"),
        "cash_balance": cash_total,
        "inventory_units": inventory_units,
        "bottles_on_hand": bottles,
        "open_receivables": sum(float(row.get("open_amount") or 0) for row in finance["receivables"]),
        "open_payables": sum(float(row.get("open_amount") or 0) for row in finance["payables"]),
        "open_funding_opportunities": open_funding,
        "funding_actions_due": len(finance["funding_requirements"]),
        "funding_actions": len(finance["funding_requirements"]),
        "cost_per_kg": (finance["unit_economics"] or {}).get("cost_per_kg"),
        "monthly": finance["monthly"],
        "funding": finance["funding"][:12],
    }


@app.post("/api/v1/blocks", status_code=201, dependencies=[Depends(authorize_write)])
def create_block(payload: BlockCreate) -> dict[str, str]:
    record_id = new_id()
    values = payload.model_dump()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO vineyard_blocks (id,estate_id,code,name,area_ha,planted_year,vine_count,training_system,soil_type,irrigation_available,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (record_id, estate_id(), values["code"], values["name"], values["area_ha"], values["planted_year"], values["vine_count"], values["training_system"], values["soil_type"], values["irrigation_available"], values["notes"]),
        )
        audit(cursor, "create", "vineyard_block", record_id, values)
    return {"id": record_id}


@app.post("/api/v1/varieties", status_code=201, dependencies=[Depends(authorize_write)])
def create_variety(payload: VarietyCreate) -> dict[str, str]:
    record_id = new_id()
    values = payload.model_dump()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO grape_varieties (id,estate_id,name,color_hex,target_gdd,notes) VALUES (%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), values["name"], values["color_hex"], values["target_gdd"], values["notes"]))
        audit(cursor, "create", "grape_variety", record_id, values)
    return {"id": record_id}


@app.get("/api/v1/tasks", dependencies=[Depends(authorize)])
def list_tasks(status: str | None = None) -> list[dict[str, Any]]:
    if status:
        return json_ready(fetch_all("SELECT * FROM tasks WHERE estate_id=%s AND status=%s ORDER BY due_date", (estate_id(), status)))
    return json_ready(fetch_all("SELECT * FROM tasks WHERE estate_id=%s ORDER BY created_at DESC LIMIT 250", (estate_id(),)))


@app.post("/api/v1/tasks", status_code=201, dependencies=[Depends(authorize_write)])
def create_task(payload: TaskCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, str]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO tasks (id,estate_id,season_id,block_id,title,category,status,priority,due_date,estimated_hours,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["title"], values["category"], values["status"], values["priority"], values["due_date"], values["estimated_hours"], values["notes"]))
        audit(cursor, "create", "task", record_id, values)
    return {"id": record_id}


@app.patch("/api/v1/tasks/{task_id}/status", dependencies=[Depends(authorize_write)])
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> dict[str, bool]:
    completed_at = datetime.now() if payload.status == "done" else None
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE tasks SET status=%s,completed_at=%s WHERE id=%s AND estate_id=%s", (payload.status, completed_at, task_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Task not found")
        audit(cursor, "status", "task", task_id, payload.model_dump())
    return {"ok": True}


@app.get("/api/v1/activities", dependencies=[Depends(authorize)])
def list_activities(year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT a.*,b.code block_code,b.name block_name FROM work_activities a LEFT JOIN vineyard_blocks b ON b.id=a.block_id LEFT JOIN seasons s ON s.id=a.season_id WHERE a.estate_id=%s AND s.vintage_year=%s ORDER BY activity_date DESC LIMIT 500", (estate_id(), year)))


@app.post("/api/v1/activities", status_code=201, dependencies=[Depends(authorize_write)])
def create_activity(payload: ActivityCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, str]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO work_activities (id,estate_id,season_id,block_id,activity_date,end_date,category,title,status,labor_hours,worker_count,cost_eur,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["activity_date"], values["end_date"], values["category"], values["title"], values["status"], values["labor_hours"], values["worker_count"], values["cost_eur"], values["notes"]))
        audit(cursor, "create", "work_activity", record_id, values)
    return {"id": record_id}


@app.post("/api/v1/harvest", status_code=201, dependencies=[Depends(authorize_write)])
def create_harvest(payload: HarvestCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, str]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    avg_crate = values["weight_kg"] / values["crate_count"] if values["weight_kg"] is not None and values["crate_count"] else None
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO harvest_lots (id,estate_id,season_id,lot_code,block_id,variety_id,harvested_at,planned_date,planned_kg,gross_kg,tare_kg,weight_kg,crate_count,avg_crate_kg,fruit_temp_c,destination,brix,babo,ph,ta_g_l,condition_grade,status,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["lot_code"], values["block_id"], values["variety_id"], values["harvested_at"], values["planned_date"], values["planned_kg"], values["gross_kg"], values["tare_kg"], values["weight_kg"], values["crate_count"], avg_crate, values["fruit_temp_c"], values["destination"], values["brix"], values["babo"], values["ph"], values["ta_g_l"], values["condition_grade"], values["status"], values["notes"]))
        audit(cursor, "create", "harvest_lot", record_id, values)
    return {"id": record_id}


@app.post("/api/v1/lab-samples", status_code=201, dependencies=[Depends(authorize_write)])
def create_lab_sample(payload: LabSampleCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, str]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump(exclude={"results"})
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_samples (id,estate_id,season_id,block_id,variety_id,wine_lot_id,sample_name,sample_type,sampled_at,lab_date,laboratory,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["variety_id"], values["wine_lot_id"], values["sample_name"], values["sample_type"], values["sampled_at"], values["lab_date"], values["laboratory"], values["notes"]))
        for result in payload.results:
            item = result.model_dump()
            cursor.execute("INSERT INTO lab_results (id,sample_id,analyte_code,analyte_name,numeric_value,text_value,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)", (new_id(), record_id, item["analyte_code"], item["analyte_name"], item["numeric_value"], item["text_value"], item["unit"]))
        audit(cursor, "create", "lab_sample", record_id, payload.model_dump())
    return {"id": record_id}


@app.get("/api/v1/labs/analytes", dependencies=[Depends(authorize)])
def lab_analytes() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT analyte_code,MAX(analyte_name) analyte_name,MAX(unit) unit,COUNT(*) result_count,MIN(numeric_value) minimum,MAX(numeric_value) maximum FROM lab_results GROUP BY analyte_code ORDER BY analyte_name"))


@app.get("/api/v1/labs/comparison", dependencies=[Depends(authorize)])
def lab_comparison(analyte_code: str, from_year: int = 2023, to_year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT * FROM v_lab_comparison WHERE estate_id=%s AND analyte_code=%s AND vintage_year BETWEEN %s AND %s ORDER BY lab_date,sample_name",
        (estate_id(), analyte_code, from_year, to_year),
    ))


@app.get("/api/v1/labs/trends", dependencies=[Depends(authorize)])
def lab_trends(from_year: int = 2020, to_year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return json_ready({
        "annual": fetch_all(
            "SELECT YEAR(s.lab_date) result_year,s.sample_type,r.analyte_code,MAX(r.analyte_name) analyte_name,MAX(r.unit) unit,"
            "COUNT(*) result_count,AVG(r.numeric_value) average_value,MIN(r.numeric_value) minimum_value,MAX(r.numeric_value) maximum_value,"
            "SUM(CASE WHEN COALESCE(r.flag,'normal') IN ('low','high','review') THEN 1 ELSE 0 END) flagged_count "
            "FROM lab_samples s JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s AND YEAR(s.lab_date) BETWEEN %s AND %s AND r.numeric_value IS NOT NULL "
            "GROUP BY YEAR(s.lab_date),s.sample_type,r.analyte_code ORDER BY r.analyte_code,result_year,s.sample_type",
            (estate_id(), from_year, to_year),
        ),
        "coverage": fetch_all(
            "SELECT YEAR(lab_date) result_year,sample_type,COUNT(*) sample_count,COUNT(DISTINCT laboratory) laboratory_count,"
            "SUM(needs_review) review_count FROM lab_samples WHERE estate_id=%s AND YEAR(lab_date) BETWEEN %s AND %s "
            "GROUP BY YEAR(lab_date),sample_type ORDER BY result_year,sample_type",
            (estate_id(), from_year, to_year),
        ),
    })


@app.get("/api/v1/labs/decision-board", dependencies=[Depends(authorize)])
def lab_decision_board(limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 250))
    return json_ready({
        "queue": fetch_all("SELECT * FROM v_lab_decision_queue WHERE estate_id=%s ORDER BY (review_status='decision_needed') DESC,flagged_results DESC,lab_date DESC LIMIT %s", (estate_id(), safe_limit)),
        "latest": fetch_all("SELECT * FROM v_lab_comparison WHERE estate_id=%s ORDER BY lab_date DESC,sample_name,analyte_name LIMIT %s", (estate_id(), safe_limit)),
        "reference_ranges": fetch_all("SELECT * FROM lab_reference_ranges WHERE estate_id=%s AND active=1 ORDER BY analyte_name,sample_type,stage", (estate_id(),)),
    })


@app.get("/api/v1/labs/history", dependencies=[Depends(authorize)])
def lab_history(from_year: int = 2020, to_year: int = Query(default_factory=lambda: date.today().year), search: str = "") -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%"
    return json_ready(fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,"
        "se.vintage_year,b.code block_code,v.name variety_name,w.code wine_lot_code,"
        "COUNT(r.id) result_count,GROUP_CONCAT(CONCAT(r.analyte_name,': ',COALESCE(CAST(r.numeric_value AS CHAR),r.text_value,''),' ',COALESCE(r.unit,'')) ORDER BY r.analyte_name SEPARATOR ' | ') results_summary "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN vineyard_blocks b ON b.id=s.block_id "
        "LEFT JOIN grape_varieties v ON v.id=s.variety_id LEFT JOIN wine_lots w ON w.id=s.wine_lot_id LEFT JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND YEAR(s.lab_date) BETWEEN %s AND %s AND (%s='' OR s.sample_name LIKE %s OR s.laboratory LIKE %s OR r.analyte_name LIKE %s) "
        "GROUP BY s.id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,se.vintage_year,b.code,v.name,w.code "
        "ORDER BY s.lab_date DESC,s.sample_name LIMIT 500",
        (estate_id(), from_year, to_year, search.strip(), pattern, pattern, pattern),
    ))


@app.get("/api/v1/labs/samples/{sample_id}", dependencies=[Depends(authorize)])
def lab_sample_detail(sample_id: str) -> dict[str, Any]:
    sample = fetch_one("SELECT * FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise HTTPException(404, "Lab sample not found")
    return json_ready({
        "sample": sample,
        "results": fetch_all("SELECT * FROM lab_results WHERE sample_id=%s ORDER BY analyte_name", (sample_id,)),
        "comparison": fetch_all("SELECT result_id,analyte_code,analyte_name,numeric_value,text_value,unit,target_min,target_max,review_below,review_above,source_reference,comparison_flag FROM v_lab_comparison WHERE sample_id=%s ORDER BY analyte_name", (sample_id,)),
        "review": fetch_one("SELECT * FROM lab_reviews WHERE sample_id=%s", (sample_id,)),
        "revisions": fetch_all("SELECT * FROM lab_result_revisions WHERE estate_id=%s AND result_id IN (SELECT id FROM lab_results WHERE sample_id=%s) ORDER BY changed_at DESC", (estate_id(), sample_id)),
    })


@app.patch("/api/v1/labs/results/{result_id}", dependencies=[Depends(authorize_write)])
def correct_lab_result(result_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed = {"analyte_code", "analyte_name", "numeric_value", "text_value", "unit", "method", "flag"}
    reason = str(payload.pop("reason", "")).strip()
    unknown = set(payload) - allowed
    if unknown:
        raise HTTPException(422, "Unsupported fields: " + ", ".join(sorted(unknown)))
    if not reason:
        raise HTTPException(422, "A correction reason is required")
    before = fetch_one("SELECT r.* FROM lab_results r JOIN lab_samples s ON s.id=r.sample_id WHERE r.id=%s AND s.estate_id=%s", (result_id, estate_id()))
    if not before:
        raise HTTPException(404, "Lab result not found")
    after = {**before, **payload}
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        assignments = ",".join(f"{key}=%s" for key in payload)
        if assignments:
            cursor.execute(f"UPDATE lab_results SET {assignments} WHERE id=%s", (*payload.values(), result_id))
        cursor.execute("INSERT INTO lab_result_revisions (estate_id,result_id,changed_by,reason,before_data,after_data) VALUES (%s,%s,%s,%s,%s,%s)", (estate_id(), result_id, actor, reason, json.dumps(json_ready(before)), json.dumps(json_ready(after))))
        audit(cursor, "correct", "lab_result", result_id, {"reason": reason, **after}, actor)
    return {"saved": True, "result_id": result_id}


@app.post("/api/v1/labs/{sample_id}/review", dependencies=[Depends(authorize_write)])
def save_lab_review(sample_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"review_status","interpretation","decision_action","decision_type","owner_text","next_check_at","enologist_approval_required","approved_by","approved_at","evidence_reference_id","notes"}
    unknown = set(payload)-allowed
    if unknown:
        raise HTTPException(422,"Unsupported review fields: "+", ".join(sorted(unknown)))
    sample = fetch_one("SELECT id FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise HTTPException(404,"Lab sample not found")
    review_id = new_id()
    values = {key: payload.get(key) for key in allowed}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_reviews (id,estate_id,sample_id,review_status,interpretation,decision_action,decision_type,owner_text,next_check_at,enologist_approval_required,approved_by,approved_at,evidence_reference_id,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE review_status=VALUES(review_status),interpretation=VALUES(interpretation),decision_action=VALUES(decision_action),decision_type=VALUES(decision_type),owner_text=VALUES(owner_text),next_check_at=VALUES(next_check_at),enologist_approval_required=VALUES(enologist_approval_required),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),evidence_reference_id=VALUES(evidence_reference_id),notes=VALUES(notes)", (review_id,estate_id(),sample_id,values.get("review_status") or "reviewing",values.get("interpretation"),values.get("decision_action"),values.get("decision_type"),values.get("owner_text"),values.get("next_check_at"),1 if values.get("enologist_approval_required",True) else 0,values.get("approved_by"),values.get("approved_at"),values.get("evidence_reference_id"),values.get("notes")))
        audit(cursor,"review","lab_sample",sample_id,payload)
    return {"saved":True,"sample_id":sample_id}


@app.post("/api/v1/weather/observations", status_code=202, dependencies=[Depends(authorize_write)])
def ingest_weather(payload: WeatherObservationCreate) -> dict[str, Any]:
    values = payload.model_dump()
    station_id = values.pop("station_id")
    external_id = values.pop("station_external_id")
    if not station_id and external_id:
        row = fetch_one("SELECT id FROM weather_stations WHERE estate_id=%s AND external_id=%s", (estate_id(), external_id))
        station_id = row["id"] if row else None
    columns = ["temp_c", "humidity_pct", "pressure_hpa", "wind_kph", "wind_gust_kph", "rain_mm", "solar_wm2", "uv_index", "leaf_wetness_pct", "soil_moisture_pct", "soil_temp_c"]
    source_hash = hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO weather_observations (estate_id,station_id,observed_at," + ",".join(columns) + ",source_hash,raw_payload) VALUES (%s,%s,%s," + ",".join(["%s"] * len(columns)) + ",%s,%s) ON DUPLICATE KEY UPDATE " + ",".join(f"{column}=VALUES({column})" for column in columns), (estate_id(), station_id, values["observed_at"], *(values[column] for column in columns), source_hash, json.dumps(values, default=str)))
    return {"accepted": True, "source_hash": source_hash}


@app.get("/api/v1/weather/comparison", dependencies=[Depends(authorize)])
def weather_comparison(from_year: int = 2023, to_year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT YEAR(weather_date) weather_year,MONTH(weather_date) weather_month,"
        "AVG(temp_min_c) temp_min_c,AVG(temp_avg_c) temp_avg_c,AVG(temp_max_c) temp_max_c,"
        "AVG(humidity_avg_pct) humidity_avg_pct,SUM(rain_mm) rain_mm,MAX(wind_max_kph) wind_max_kph,"
        "SUM(gdd_base10) gdd_base10,AVG(soil_moisture_avg_pct) soil_moisture_avg_pct,"
        "AVG(solar_mj_m2) solar_mj_m2,SUM(et0_mm) et0_mm "
        "FROM weather_daily WHERE estate_id=%s AND YEAR(weather_date) BETWEEN %s AND %s "
        "GROUP BY YEAR(weather_date),MONTH(weather_date) ORDER BY weather_year,weather_month",
        (estate_id(), from_year, to_year),
    ))


@app.post("/api/v1/weather/import-history", dependencies=[Depends(authorize_write)])
async def import_weather_history(file: UploadFile = File(...)) -> dict[str, Any]:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "Choose the Baiamonte Weather CSV file")
    data = await file.read(10 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Weather CSV must be 10 MB or smaller")
    return import_baiamonte_weather_csv(data)


@app.get("/api/v1/treatments", dependencies=[Depends(authorize)])
def treatment_history(year: int | None = None) -> list[dict[str, Any]]:
    if year:
        return json_ready(fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s AND YEAR(application_date)=%s ORDER BY application_date DESC", (estate_id(), year)))
    return json_ready(fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s ORDER BY application_date DESC LIMIT 500", (estate_id(),)))


@app.get("/api/v1/treatments/dashboard", dependencies=[Depends(authorize)])
def treatment_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    refresh_disease_pressure()
    rows = fetch_all(
        "SELECT * FROM v_treatment_history WHERE estate_id=%s AND YEAR(application_date)=%s ORDER BY application_date DESC",
        (estate_id(), year),
    )
    current_plans = fetch_all(
        "SELECT * FROM v_treatment_history WHERE estate_id=%s AND status='planned' ORDER BY COALESCE(planned_application_date,DATE(application_date)),application_date",
        (estate_id(),),
    )
    pressure = fetch_all(
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s) ORDER BY risk_score DESC",
        (estate_id(), estate_id()),
    )
    monthly = []
    for month in range(1, 13):
        matching = [row for row in rows if _treatment_date(row).month == month]
        monthly.append({
            "month": month,
            "total": len(matching),
            "completed": sum(row.get("status") == "completed" for row in matching),
            "planned": sum(row.get("status") == "planned" for row in matching),
        })
    actions = _treatment_actions(year)
    return json_ready({
        "year": year,
        "summary": {
            "total": len(rows),
            "planned": sum(row.get("status") == "planned" for row in rows),
            "completed": sum(row.get("status") == "completed" for row in rows),
            "approved": sum(bool(row.get("agronomist_approved")) for row in rows),
            "missing_actual_details": sum(not bool(row.get("actual_details_confirmed")) for row in rows),
        },
        "prediction": predict_next_treatment(current_plans, pressure),
        "pressure": pressure,
        "monthly": monthly,
        "treatments": rows,
        "actions": actions,
        "prediction_as_of": date.today(),
        "guardrail": "Decision support only. Sebastian/agronomist approval and all legal and safety checks remain required.",
    })


def _treatment_date(row: dict[str, Any]) -> date:
    value = row.get("application_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _treatment_actions(year: int) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in fetch_all(
        "SELECT actor,action,entity_type,entity_id,after_data,occurred_at FROM audit_events WHERE estate_id=%s AND entity_type='treatment' AND YEAR(occurred_at)=%s ORDER BY occurred_at DESC LIMIT 40",
        (estate_id(), year),
    ):
        details = row.get("after_data")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except ValueError:
                details = {}
        actions.append({"kind": "record", "title": (details or {}).get("purpose") or "Treatment record changed", "detail": row.get("action"), "status": (details or {}).get("status") or "processed", "source": row.get("actor") or "system", "occurred_at": row.get("occurred_at"), "entity_id": row.get("entity_id")})
    for row in fetch_all(
        "SELECT disease_name,agronomist_status,agronomist_name,agronomist_notes,reviewed_at FROM disease_pressure_assessments WHERE estate_id=%s AND reviewed_at IS NOT NULL AND YEAR(reviewed_at)=%s ORDER BY reviewed_at DESC LIMIT 30",
        (estate_id(), year),
    ):
        actions.append({"kind": "review", "title": f"{row['disease_name']} review", "detail": row.get("agronomist_notes") or "Agronomist review recorded", "status": row.get("agronomist_status"), "source": row.get("agronomist_name") or "agronomist", "occurred_at": row.get("reviewed_at")})
    for row in fetch_all(
        "SELECT title,original_filename,classification,review_status,source,received_at FROM intake_items WHERE estate_id=%s AND classification IN ('treatment_instruction','vineyard_instruction') AND YEAR(received_at)=%s ORDER BY received_at DESC LIMIT 30",
        (estate_id(), year),
    ):
        actions.append({"kind": "intake", "title": row.get("title") or row.get("original_filename") or "Incoming treatment information", "detail": row.get("classification"), "status": row.get("review_status"), "source": row.get("source"), "occurred_at": row.get("received_at")})
    actions.sort(key=lambda row: row.get("occurred_at") or datetime.min, reverse=True)
    return actions[:50]


@app.get("/api/v1/system/status", dependencies=[Depends(authorize)])
def system_status() -> dict[str, Any]:
    return json_ready(system_status_payload())


@app.get("/api/v1/disease-pressure", dependencies=[Depends(authorize)])
def disease_pressure() -> list[dict[str, Any]]:
    refresh_disease_pressure()
    return json_ready(fetch_all("SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date DESC,risk_score DESC", (estate_id(),)))


@app.patch("/api/v1/disease-pressure/{assessment_id}/review", dependencies=[Depends(authorize_write)])
def review_disease_pressure(assessment_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = payload.get("agronomist_status")
    if status not in {"approved", "modified", "rejected", "not_required"}:
        raise HTTPException(422, "Choose an agronomist review status")
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE disease_pressure_assessments SET agronomist_status=%s,agronomist_name=%s,agronomist_notes=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, request.headers.get("X-Remote-User-Name") or "api", payload.get("agronomist_notes"), assessment_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Assessment not found")
    return {"saved": True}


@app.get("/api/v1/alerts", dependencies=[Depends(authorize)])
def list_alerts(status: str = "open") -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT * FROM alerts WHERE estate_id=%s AND (%s='all' OR status=%s) ORDER BY triggered_at DESC LIMIT 250", (estate_id(), status, status)))


@app.patch("/api/v1/alerts/{alert_id}", dependencies=[Depends(authorize_write)])
def update_alert(alert_id: str, payload: dict[str, Any]) -> dict[str, bool]:
    status = payload.get("status")
    if status not in {"acknowledged", "resolved", "dismissed"}:
        raise HTTPException(422, "Unsupported alert status")
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE alerts SET status=%s,acknowledged_at=IF(%s='acknowledged',NOW(),acknowledged_at),resolved_at=IF(%s='resolved',NOW(),resolved_at) WHERE id=%s AND estate_id=%s", (status, status, status, alert_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Alert not found")
    return {"saved": True}


ALERT_TYPES = {
    "disease_pressure": "Disease & stress",
    "weather": "Weather extremes",
    "laboratory": "Laboratory review",
    "tasks": "Overdue priority work",
    "system": "System & integrations",
    "cellar": "Cellar tank guardrails",
    "etna": "Mount Etna activity",
}


@app.get("/api/v1/etna", dependencies=[Depends(authorize)])
def mount_etna_status(refresh: bool = False) -> dict[str, Any]:
    return etna_status(refresh=refresh)


@app.get("/api/v1/alert-settings", dependencies=[Depends(authorize)])
def alert_settings(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username = (request.headers.get("X-Remote-User-Name") or "").strip().casefold()
    if username and username not in operations_usernames(settings):
        return {"preferences": [], "channels": {}}
    saved = {row["alert_type"]: row for row in fetch_all("SELECT * FROM alert_preferences WHERE estate_id=%s", (estate_id(),))}
    preferences = []
    for alert_type, label in ALERT_TYPES.items():
        row = saved.get(alert_type) or {
            "alert_type": alert_type, "enabled": 1, "min_severity": "warning",
            "notify_home_assistant": 1, "notify_email": 0, "notify_whatsapp": 0,
            "email_recipients": "", "whatsapp_recipients": "",
        }
        preferences.append({**row, "label": label})
    return json_ready({
        "preferences": preferences,
        "channels": {
            "home_assistant": {"configured": bool(settings.ha_notifications_enabled and home_assistant_token()), "detail": settings.ha_notify_service if settings.ha_notifications_enabled else "Disabled in add-on options"},
            "email": {"configured": bool(settings.gmail_address and settings.gmail_app_password), "detail": settings.gmail_address or "Add the Gmail address and app password in add-on options"},
            "whatsapp": {"configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id), "detail": "Meta WhatsApp Business connected" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "Add the Meta token and phone number ID in add-on options"},
        },
    })


@app.put("/api/v1/alert-settings/{alert_type}", dependencies=[Depends(authorize_write)])
def update_alert_settings(alert_type: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    if alert_type not in ALERT_TYPES:
        raise HTTPException(404, "Unknown alert type")
    severity = str(payload.get("min_severity") or "warning")
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(422, "Choose info, warning or critical")
    emails = ",".join(value.strip() for value in str(payload.get("email_recipients") or "").split(",") if value.strip())[:2000]
    numbers = ",".join(value.strip() for value in str(payload.get("whatsapp_recipients") or "").split(",") if value.strip())[:2000]
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO alert_preferences (estate_id,alert_type,enabled,min_severity,notify_home_assistant,notify_email,notify_whatsapp,email_recipients,whatsapp_recipients,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE enabled=VALUES(enabled),min_severity=VALUES(min_severity),notify_home_assistant=VALUES(notify_home_assistant),notify_email=VALUES(notify_email),notify_whatsapp=VALUES(notify_whatsapp),email_recipients=VALUES(email_recipients),whatsapp_recipients=VALUES(whatsapp_recipients),updated_by=VALUES(updated_by)",
            (estate_id(), alert_type, bool(payload.get("enabled", True)), severity, bool(payload.get("notify_home_assistant", True)), bool(payload.get("notify_email")), bool(payload.get("notify_whatsapp")), emails, numbers, request.headers.get("X-Remote-User-Name") or "api"),
        )
    return {"saved": True}


@app.get("/api/v1/intake", dependencies=[Depends(authorize)])
def list_intake() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT id,source,sender_name,sender_address,received_at,title,original_filename,media_type,classification,ai_summary,extracted_data,review_status,processing_error FROM intake_items WHERE estate_id=%s ORDER BY received_at DESC LIMIT 250", (estate_id(),)))


@app.get("/api/v1/processing-log", dependencies=[Depends(authorize)])
def processing_log(limit: int = Query(100, ge=10, le=500)) -> list[dict[str, Any]]:
    """A safe, user-facing activity/error trail for automated processing."""
    rows: list[dict[str, Any]] = []
    for row in fetch_all(
        "SELECT id,integration_name,direction,event_type,status,error_message,occurred_at "
        "FROM integration_events WHERE estate_id=%s ORDER BY occurred_at DESC LIMIT %s",
        (estate_id(), limit),
    ):
        rows.append({
            "id": f"integration-{row['id']}", "kind": "integration", "source": row["integration_name"],
            "action": row["event_type"], "direction": row["direction"], "status": row["status"],
            "message": row.get("error_message"), "occurred_at": row["occurred_at"],
        })
    for row in fetch_all(
        "SELECT id,source,title,original_filename,classification,review_status,processing_error,received_at "
        "FROM intake_items WHERE estate_id=%s ORDER BY received_at DESC LIMIT %s",
        (estate_id(), limit),
    ):
        rows.append({
            "id": f"intake-{row['id']}", "kind": "intake", "source": row["source"],
            "action": row.get("classification") or row.get("title") or row.get("original_filename") or "incoming item",
            "direction": "inbound", "status": row["review_status"], "message": row.get("processing_error"),
            "occurred_at": row["received_at"],
        })
    rows.sort(key=lambda row: row.get("occurred_at") or datetime.min, reverse=True)
    return json_ready(rows[:limit])


@app.post("/api/v1/intake/gmail/check", dependencies=[Depends(authorize_write)])
def check_gmail_now() -> dict[str, Any]:
    settings = get_settings()
    if not settings.gmail_address or not settings.gmail_app_password:
        return {"configured": False, "message": "Add the Gmail address and app password in Vineyard Operations configuration."}
    try:
        saved = poll_gmail_once()
        return {"configured": True, "saved": saved, "message": f"Gmail checked; {saved} new item(s) added for review."}
    except Exception as error:
        raise HTTPException(502, "Gmail check failed: " + str(error)[:300]) from error


@app.get("/api/v1/intake/{record_id}", dependencies=[Depends(authorize)])
def intake_detail(record_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT id,source,sender_name,sender_address,received_at,title,original_filename,media_type,classification,ai_summary,extracted_data,review_status,processing_error FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Inbox item not found")
    if isinstance(row.get("extracted_data"), str):
        try:
            row["extracted_data"] = json.loads(row["extracted_data"])
        except json.JSONDecodeError:
            row["extracted_data"] = None
    return json_ready(row)


@app.post("/api/v1/intake/{record_id}/link", dependencies=[Depends(authorize_write)])
def link_intake_to_record(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    entity_type = str(payload.get("entity_type") or "")
    entity_id = str(payload.get("entity_id") or "")
    table = ATTACHMENT_ENTITIES.get(entity_type)
    if not table or not entity_id:
        raise HTTPException(422, "Choose a supported vineyard record")
    item = fetch_one("SELECT * FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not item:
        raise HTTPException(404, "Inbox item not found")
    if not fetch_one(f"SELECT id FROM {table} WHERE id=%s AND estate_id=%s", (entity_id, estate_id())):
        raise HTTPException(404, "Saved vineyard record not found")
    attachment_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (attachment_id, estate_id(), entity_type, entity_id, item.get("original_filename") or "incoming-item", item.get("stored_path"), item.get("media_type"), item.get("file_sha256"), item.get("ai_summary") or item.get("title"), request.headers.get("X-Remote-User-Name") or "api"),
        )
        cursor.execute("UPDATE intake_items SET review_status='approved',reviewed_by=%s,reviewed_at=NOW() WHERE id=%s", (request.headers.get("X-Remote-User-Name") or "api", record_id))
        audit(cursor, "approve", "intake", record_id, {"entity_type": entity_type, "entity_id": entity_id, "attachment_id": attachment_id})
    return {"saved": True, "attachment_id": attachment_id, "entity_id": entity_id}


@app.post("/api/v1/intake/upload", status_code=201, dependencies=[Depends(authorize_write)])
async def upload_intake(background_tasks: BackgroundTasks, file: UploadFile = File(...), title: str = Form(""), notes: str = Form("")) -> dict[str, Any]:
    data = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    try:
        record_id = save_intake_file(data, file.filename or "upload", file.content_type, "upload", title or file.filename, notes)
    except ValueError as error:
        raise HTTPException(413, str(error)) from error
    if get_settings().openai_api_key:
        background_tasks.add_task(analyze_intake, record_id)
        return {"id": record_id, "status": "processing"}
    return {"id": record_id, "status": "new"}


@app.post("/api/v1/intake/{record_id}/analyze", dependencies=[Depends(authorize_write)])
async def analyze_intake_item(record_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(analyze_intake, record_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.patch("/api/v1/intake/{record_id}/review", dependencies=[Depends(authorize_write)])
def review_intake(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = payload.get("review_status")
    if status not in {"approved", "rejected", "ready_for_review"}:
        raise HTTPException(422, "Unsupported review status")
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE intake_items SET review_status=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, request.headers.get("X-Remote-User-Name") or "api", record_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Intake item not found")
    return {"saved": True}


@app.post("/api/v1/assistant/ask", dependencies=[Depends(authorize_write)])
async def assistant_question(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    language = "it" if str(payload.get("language") or "en").lower().startswith("it") else "en"
    focus = str(payload.get("focus") or "vineyard").strip().casefold()
    if focus not in {"vineyard", "laboratory", "treatments", "cellar"}:
        focus = "vineyard"
    if not question:
        raise HTTPException(422, "Enter a vineyard question")
    try:
        return await asyncio.to_thread(ask_assistant, question, language, focus)
    except Exception as error:
        raise HTTPException(502, "Assistant request failed: " + str(error)[:350]) from error


@app.post("/api/v1/assistant/suggestion", dependencies=[Depends(authorize_write)])
def save_assistant_suggestion(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Place an AI suggestion in the human review inbox; never apply it directly."""
    question = str(payload.get("question") or "").strip()[:4000]
    answer = str(payload.get("answer") or "").strip()[:12000]
    focus = str(payload.get("focus") or "vineyard").strip().casefold()
    if focus not in {"vineyard", "laboratory", "treatments", "cellar"}:
        focus = "vineyard"
    if not question or not answer:
        raise HTTPException(422, "A question and AI suggestion are required")
    combined = f"Question:\n{question}\n\nAI suggestion:\n{answer}\n"
    external_id = hashlib.sha256(combined.encode()).hexdigest()
    record_id = save_intake_file(
        combined.encode(), f"{focus}-ai-suggestion.txt", "text/plain", "assistant",
        f"AI {focus} suggestion", combined, external_id,
        request.headers.get("X-Remote-User-Name") or "Vineyard Operations", None,
    )
    extracted = {
        "classification": "cellar_instruction" if focus == "cellar" else "issue_or_decision",
        "summary": answer[:500], "facts": [], "uncertainties": ["AI-generated suggestion; verify source readings and assumptions"],
        "suggested_database_records": [{
            "destination_section": "issue",
            "fields": {
                "issue_text": f"AI {focus} suggestion: {answer[:3000]}",
                "priority": "medium",
                "decision_action": "Verify the source records and obtain the required human approval before applying this suggestion.",
            },
        }],
        "required_human_review": "enologist_review_required" if focus == "cellar" else "human_review_required",
        "question": question, "answer": answer, "focus": focus,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE intake_items SET classification=%s,ai_summary=%s,extracted_data=%s,review_status='ready_for_review' WHERE id=%s AND estate_id=%s",
            (extracted["classification"], extracted["summary"], json.dumps(extracted), record_id, estate_id()),
        )
    return {"saved": True, "id": record_id, "review_status": "ready_for_review"}


@app.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    if hub_mode == "subscribe" and settings.whatsapp_verify_token and hmac.compare_digest(hub_verify_token or "", settings.whatsapp_verify_token):
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(403, "Webhook verification failed")


@app.post("/webhooks/whatsapp")
async def receive_whatsapp_webhook(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.whatsapp_app_secret:
        expected = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(403, "Invalid webhook signature")
    payload = json.loads(raw or b"{}")
    allowed = {number.strip().replace("+", "") for number in settings.whatsapp_allowed_numbers.split(",") if number.strip()}
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            contacts = {contact.get("wa_id"): (contact.get("profile") or {}).get("name") for contact in value.get("contacts", [])}
            for message in value.get("messages", []):
                sender = str(message.get("from") or "").replace("+", "")
                if allowed and sender not in allowed:
                    continue
                message_type = message.get("type") or "unknown"
                body = (message.get("text") or {}).get("body") or (message.get(message_type) or {}).get("caption") or json.dumps(message.get(message_type) or {})
                filename = f"whatsapp-{message.get('id','message')}.txt"
                try:
                    record_id = save_intake_file(body.encode(), filename, "text/plain", "whatsapp", f"WhatsApp {message_type}", body, message.get("id"), contacts.get(sender), sender)
                    if settings.openai_api_key:
                        asyncio.create_task(asyncio.to_thread(analyze_intake, record_id))
                except IntegrityError:
                    pass
    return {"received": True}


@app.get("/api/v1/records/{record_type}", dependencies=[Depends(authorize)])
def vineyard_records(record_type: str) -> list[dict[str, Any]]:
    queries = {
        "blocks": ("SELECT code,name,area_ha,planted_year,vine_count,training_system,soil_type FROM vineyard_blocks WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "varieties": ("SELECT name,color_hex,target_gdd,notes FROM grape_varieties WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "labs": ("SELECT lab_date,sample_name,sample_type,laboratory,source_document FROM lab_samples WHERE estate_id=%s ORDER BY lab_date DESC LIMIT 250", (estate_id(),)),
        "stock": ("SELECT name,sku,product_type,category_name,unit,track_inventory FROM products WHERE estate_id=%s AND active=1 ORDER BY category_name,name", (estate_id(),)),
        "cellar": ("SELECT code,name,stage,volume_l,current_container_id FROM wine_lots WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "reports": ("SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,evidence_status,reconciliation_note FROM vintage_summaries WHERE estate_id=%s ORDER BY vintage_year DESC,variety_name", (estate_id(),)),
        "attachments": ("SELECT id,entity_type,entity_id,original_filename,media_type,caption,uploaded_by,created_at FROM entity_attachments WHERE estate_id=%s ORDER BY created_at DESC LIMIT 250", (estate_id(),)),
    }
    if record_type not in queries:
        raise HTTPException(404, "Record type not found")
    sql, params = queries[record_type]
    return json_ready(fetch_all(sql, params))


@app.get("/api/v1/history/overview", dependencies=[Depends(authorize)])
def multi_year_overview(from_year: int = 2020, to_year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    """Compact year-by-year operating history for comparisons without workbook pivots."""
    years: dict[int, dict[str, Any]] = {
        year: {"year": year, "harvest_kg": None, "harvest_lots": 0, "cellar_l": None, "labor_hours": None, "treatments": 0, "treatments_completed": 0, "lab_samples": 0, "olives_kg": None, "oil_l": None, "history_source": None}
        for year in range(from_year, to_year + 1)
    }
    queries = {
        "harvest": "SELECT s.vintage_year year,COALESCE(SUM(h.weight_kg),0) harvest_kg,COUNT(h.id) harvest_lots FROM seasons s LEFT JOIN harvest_lots h ON h.season_id=s.id WHERE s.estate_id=%s AND s.vintage_year BETWEEN %s AND %s GROUP BY s.vintage_year",
        "cellar": "SELECT s.vintage_year year,COALESCE(SUM(w.volume_l),0) cellar_l FROM seasons s LEFT JOIN wine_lots w ON w.season_id=s.id WHERE s.estate_id=%s AND s.vintage_year BETWEEN %s AND %s GROUP BY s.vintage_year",
        "labor": "SELECT YEAR(work_date) year,COALESCE(SUM(COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)),0) labor_hours FROM labor_entries WHERE estate_id=%s AND YEAR(work_date) BETWEEN %s AND %s GROUP BY YEAR(work_date)",
        "treatments": "SELECT YEAR(application_date) year,COUNT(*) treatments,SUM(status='completed') treatments_completed FROM spray_applications WHERE estate_id=%s AND YEAR(application_date) BETWEEN %s AND %s GROUP BY YEAR(application_date)",
        "labs": "SELECT YEAR(lab_date) year,COUNT(*) lab_samples FROM lab_samples WHERE estate_id=%s AND YEAR(lab_date) BETWEEN %s AND %s GROUP BY YEAR(lab_date)",
        "olives": "SELECT record_year year,COALESCE(SUM(olives_harvested_kg),0) olives_kg,COALESCE(SUM(oil_liters),0) oil_l FROM olive_records WHERE estate_id=%s AND record_year BETWEEN %s AND %s GROUP BY record_year",
    }
    for sql in queries.values():
        for row in fetch_all(sql, (estate_id(), from_year, to_year)):
            year = int(row.pop("year"))
            years.setdefault(year, {"year": year}).update(row)
    # The workbook's reconciled vintage register is authoritative for historical
    # years where lot-level harvest/cellar rows were never available.
    for row in fetch_all(
        "SELECT vintage_year year,SUM(grapes_kg) summary_harvest_kg,SUM(wine_l) summary_cellar_l "
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
    return json_ready([years[year] for year in sorted(years, reverse=True)])


def validate_feed_token(token: str | None, settings: Settings) -> None:
    if not settings.public_feed_token or token != settings.public_feed_token:
        raise HTTPException(404, "Not found")


@app.get("/public/v1/harvest.json")
def harvest_feed(response: Response, token: str | None = None, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    validate_feed_token(token, settings)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "public, max-age=300"
    return json_ready(public_harvest_feed())


@app.get("/public/v1/harvest.ics", response_class=PlainTextResponse)
def harvest_calendar(token: str | None = None, settings: Settings = Depends(get_settings)) -> str:
    validate_feed_token(token, settings)
    rows = fetch_all("SELECT vintage_year,variety_name,first_pick_date,last_pick_date FROM v_harvest_summary WHERE estate_id=%s ORDER BY vintage_year DESC,variety_name", (estate_id(),))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Tenuta Baiamonte//Harvest//EN", "CALSCALE:GREGORIAN"]
    for row in rows:
        if not row["first_pick_date"]:
            continue
        start = row["first_pick_date"].strftime("%Y%m%d")
        end_date = row["last_pick_date"] or row["first_pick_date"]
        end = end_date.fromordinal(end_date.toordinal() + 1).strftime("%Y%m%d")
        lines.extend(["BEGIN:VEVENT", f"UID:{row['vintage_year']}-{row['variety_name']}@baiamonte", f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}", f"SUMMARY:Harvest — {row['variety_name']}", "END:VEVENT"])
    lines.extend(["END:VCALENDAR", ""])
    return "\r\n".join(lines)


async def save_workbook_upload(upload: UploadFile, destination: Path) -> None:
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(422, "Only Excel .xlsx or .xlsm workbooks are accepted")
    size = 0
    with destination.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > 25 * 1024 * 1024:
                raise HTTPException(413, "Each workbook must be 25 MB or smaller")
            handle.write(chunk)
    await upload.close()


def supplied_workbook(upload: UploadFile | None) -> bool:
    """Ignore the empty UploadFile objects browsers send for unselected fields."""
    return upload is not None and bool((upload.filename or "").strip())


def run_workbook_import(command: list[str], working_directory: Path) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=working_directory,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(504, "Workbook validation exceeded five minutes") from error
    if result.returncode:
        message = (result.stderr or result.stdout or "Workbook import failed").strip().splitlines()[-1]
        raise HTTPException(422, message[:500])


@app.post("/api/v1/admin/import-workbooks", dependencies=[Depends(authorize_finance)])
async def import_workbooks(
    commit: bool = Form(False),
    confirmation: str = Form(""),
    vineyard: UploadFile | None = File(default=None),
    finance: UploadFile | None = File(default=None),
    funding: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    if not any(supplied_workbook(upload) for upload in (vineyard, finance, funding)):
        raise HTTPException(422, "Select at least one workbook")
    if commit and confirmation != "BACKUP VERIFIED":
        raise HTTPException(409, "Confirm that the Home Assistant backup completed before importing")

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    reports: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="baiamonte-import-") as temp_name:
        temp_dir = Path(temp_name)
        uploaded: dict[str, Path] = {}
        for label, upload in (("vineyard", vineyard), ("finance", finance), ("funding", funding)):
            if supplied_workbook(upload):
                path = temp_dir / f"{label}.xlsx"
                await save_workbook_upload(upload, path)
                uploaded[label] = path

        if "vineyard" in uploaded:
            report_path = temp_dir / "vineyard-report.json"
            command = [sys.executable, str(scripts_dir / "import_workbook.py"), str(uploaded["vineyard"]), "--report", str(report_path)]
            if commit:
                command.append("--commit")
            await asyncio.to_thread(run_workbook_import, command, scripts_dir)
            reports["vineyard"] = json.loads(report_path.read_text(encoding="utf-8"))

        finance_paths = [uploaded[label] for label in ("finance", "funding") if label in uploaded]
        if finance_paths:
            report_path = temp_dir / "finance-report.json"
            command = [sys.executable, str(scripts_dir / "import_finance_workbooks.py"), *(str(path) for path in finance_paths), "--report", str(report_path)]
            if commit:
                command.append("--commit")
            await asyncio.to_thread(run_workbook_import, command, scripts_dir)
            reports["finance_funding"] = json.loads(report_path.read_text(encoding="utf-8"))

    return {"mode": "commit" if commit else "dry-run", "reports": reports}


@app.get("/weather-map/{path:path}")
def weather_map_proxy(path: str, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    """Show the existing ADS-B precipitation layer inside Vineyard Operations."""
    base_url = str(runtime_option("tv_adsb_url", settings.tv_adsb_url)).rstrip("/")
    safe_path = urllib.parse.quote(path or "", safe="/@:._~!$&'()*+,;=-")
    upstream_url = f"{base_url}/{safe_path}"
    if request.url.query:
        upstream_url += "?" + request.url.query
    upstream_request = urllib.request.Request(
        upstream_url,
        headers={"Accept": request.headers.get("accept", "*/*"), "Accept-Encoding": "identity", "User-Agent": "Baiamonte-Vineyard-Weather/1.0"},
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=15) as upstream:
            content = upstream.read(12 * 1024 * 1024)
            media_type = upstream.headers.get_content_type() or "application/octet-stream"
    except Exception as error:
        raise HTTPException(502, "The precipitation map service is temporarily unavailable") from error
    if media_type == "text/html":
        document = content.decode("utf-8", errors="replace")
        document = document.replace("</head>", WEATHER_MAP_STYLE + "</head>", 1)
        content = document.encode("utf-8")
    cache_control = "no-store" if media_type in {"text/html", "application/json"} else "public, max-age=300"
    return Response(content, media_type=media_type, headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/crew")
def crew_entry_page() -> FileResponse:
    return FileResponse(static_dir / "crew.html")


@app.get("/display")
def vineyard_display_page() -> FileResponse:
    return FileResponse(static_dir / "display.html", headers={"Cache-Control": "no-cache"})


app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
