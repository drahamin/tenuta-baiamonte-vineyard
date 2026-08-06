from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import IntegrityError

from .config import Settings, get_settings
from .db import fetch_all, fetch_one, run_migrations, transaction
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
    task = asyncio.create_task(publishing_loop()) if get_settings().public_publish_url else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Baiamonte Vineyard API", version="1.0.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"


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
    try:
        return save_quick_entry(record_type, payload)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


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


@app.get("/api/v1/home-assistant/summary", dependencies=[Depends(authorize)])
def home_assistant_summary(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    vineyard = dashboard(year)
    bottle_row = fetch_one(
        "SELECT COALESCE(SUM(quantity_on_hand),0) n FROM v_inventory_current WHERE estate_id=%s AND unit='bt.'",
        (estate_id(),),
    ) or {"n": 0}
    return {
        "status": "online",
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "year": year,
        "open_tasks": vineyard["counts"]["open_tasks"],
        "alerts": vineyard["counts"]["open_alerts"],
        "harvest_kg": vineyard["counts"]["harvest_kg"],
        "work_hours": vineyard["counts"]["work_hours"],
        "bottles_on_hand": bottle_row["n"],
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


@app.get("/api/v1/labs/decision-board", dependencies=[Depends(authorize)])
def lab_decision_board(limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 250))
    return json_ready({
        "queue": fetch_all("SELECT * FROM v_lab_decision_queue WHERE estate_id=%s ORDER BY (review_status='decision_needed') DESC,flagged_results DESC,lab_date DESC LIMIT %s", (estate_id(), safe_limit)),
        "latest": fetch_all("SELECT * FROM v_lab_comparison WHERE estate_id=%s ORDER BY lab_date DESC,sample_name,analyte_name LIMIT %s", (estate_id(), safe_limit)),
        "reference_ranges": fetch_all("SELECT * FROM lab_reference_ranges WHERE estate_id=%s AND active=1 ORDER BY analyte_name,sample_type,stage", (estate_id(),)),
    })


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
    if not any((vineyard, finance, funding)):
        raise HTTPException(422, "Select at least one workbook")
    if commit and confirmation != "BACKUP VERIFIED":
        raise HTTPException(409, "Confirm that the Home Assistant backup completed before importing")

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    reports: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="baiamonte-import-") as temp_name:
        temp_dir = Path(temp_name)
        uploaded: dict[str, Path] = {}
        for label, upload in (("vineyard", vineyard), ("finance", finance), ("funding", funding)):
            if upload:
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


app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
