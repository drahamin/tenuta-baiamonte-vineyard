from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import IntegrityError

from .config import Settings, get_settings
from .db import fetch_all, fetch_one, run_migrations, transaction
from .display_data import display_payload
from .fattureincloud import pull_fattureincloud
from .intelligence import analyze_intake, ask_assistant, integration_loop, refresh_disease_pressure, save_intake_file
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


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, error: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with existing data", "code": error.args[0]})


@app.get("/health")
def health() -> dict[str, Any]:
    row = fetch_one("SELECT 1 AS database_ok")
    return {"ok": True, "database": bool(row and row["database_ok"] == 1)}


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
    return json_ready({"year": year, "metrics": metrics, "varieties": varieties, "vintages": vintages, "blocks": blocks})


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


@app.get("/api/v1/projections", dependencies=[Depends(authorize)])
def operational_projections(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    grapes = grape_dashboard(year)
    vintages = grapes["vintages"]
    conversion_rows = [row for row in vintages if row.get("grapes_kg") and row.get("wine_l") and int(row["vintage_year"]) < year]
    conversion = sum(float(row["wine_l"]) / float(row["grapes_kg"]) for row in conversion_rows) / len(conversion_rows) if conversion_rows else 0.70
    planned_kg = grapes["metrics"].get("planned_kg")
    harvested_kg = grapes["metrics"].get("harvested_kg")
    basis_kg = planned_kg if planned_kg is not None else harvested_kg
    scenarios = []
    for name, factor in (("Downside", 0.85), ("Working", 1.0), ("Upside", 1.15)):
        kg = float(basis_kg) * factor if basis_kg is not None else None
        wine_l = kg * conversion if kg is not None else None
        scenarios.append({"name": name, "grapes_kg": kg, "wine_l": wine_l, "bottle_equivalents": wine_l / 0.75 if wine_l is not None else None})
    return json_ready({
        "year": year,
        "basis": "harvest plan" if planned_kg is not None else "harvested weight" if harvested_kg is not None else "missing",
        "historical_conversion_l_per_kg": conversion,
        "scenarios": scenarios,
        "varieties": grapes["varieties"],
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


@app.post("/api/v1/finance/fattureincloud/pull", dependencies=[Depends(authorize_finance)])
async def pull_fattureincloud_now() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(pull_fattureincloud)
    except Exception as error:
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
        cursor.execute("INSERT INTO harvest_lots (id,estate_id,season_id,block_id,variety_id,harvested_at,weight_kg,crate_count,avg_crate_kg,destination,brix,babo,ph,ta_g_l,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["variety_id"], values["harvested_at"], values["weight_kg"], values["crate_count"], avg_crate, values["destination"], values["brix"], values["babo"], values["ph"], values["ta_g_l"], values["notes"]))
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
        "SUM(gdd_base10) gdd_base10,AVG(soil_moisture_avg_pct) soil_moisture_avg_pct "
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


@app.get("/api/v1/intake", dependencies=[Depends(authorize)])
def list_intake() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT id,source,sender_name,sender_address,received_at,title,original_filename,media_type,classification,ai_summary,review_status,processing_error FROM intake_items WHERE estate_id=%s ORDER BY received_at DESC LIMIT 250", (estate_id(),)))


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


@app.post("/api/v1/assistant/ask", dependencies=[Depends(authorize)])
async def assistant_question(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(422, "Enter a vineyard question")
    try:
        return await asyncio.to_thread(ask_assistant, question)
    except Exception as error:
        raise HTTPException(502, "Assistant request failed: " + str(error)[:350]) from error


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/crew")
def crew_entry_page() -> FileResponse:
    return FileResponse(static_dir / "crew.html")


@app.get("/display")
def vineyard_display_page() -> FileResponse:
    return FileResponse(static_dir / "display.html")


app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
