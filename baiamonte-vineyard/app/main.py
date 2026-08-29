from __future__ import annotations
import asyncio
import hashlib
import html
import json
import logging
import math
import os
import re
import time
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import IntegrityError
from .access import (
    authorize,
    authorize_admin,
    authorize_crew,
    authorize_finance,
    authorize_write,
    has_finance_access,
    match_home_assistant_person as _match_home_assistant_person,
    people_profiles,
)
from .ai_usage import ai_cost_summary, ai_request_profile, ai_service_summary
from .config import RUNTIME_OPTIONS_PATH, Settings, addon_version, get_settings, runtime_option
from .cache_headers import ReleaseAssetCacheMiddleware
from .cellar_demo import live_sensor_tank_keys
from .db import fetch_all, fetch_one, run_migrations, transaction
from .data_quality import operational_data_quality
from .domains.alerts_intake_routes import router as alerts_intake_router
from .domains.admin_control import LEGACY_PROCESS_INTEGRATIONS, PROCESS_INTEGRATIONS, admin_control_foundation
from .domains.admin_routes import router as admin_router
from .domains.communications_gmail_routes import router as communications_gmail_router
from .domains.communications_meta_routes import router as communications_meta_router
from .domains.communications_meta_webhook_routes import router as communications_meta_webhook_router
from .domains.communications_system_whatsapp_routes import router as communications_system_whatsapp_router
from .domains.cellar_routes import (
    _ensure_current_manual_tanks,
    _live_cellar_dashboard,
    router as cellar_router,
)
from .domains.camera_routes import router as camera_router, snapshot_router as camera_snapshot_router
from .domains.damage_routes import damage_assessment_dashboard, router as damage_router
from .domains.dashboard_routes import grape_dashboard, router as dashboard_router
from .domains.disease_routes import router as disease_router
from .domains.finance import dashboard_payload as _finance_dashboard_payload, home_assistant_summary as _home_assistant_finance_summary
from .domains.finance_inventory_routes import router as finance_inventory_router
from .domains.fertilization_routes import router as fertilization_router
from .domains.harvest import calculate_blend_program
from .domains.hospitality_routes import router as hospitality_router
from .domains.intelligence_routes import router as intelligence_router
from .domains.bottling_routes import router as bottling_router
from .domains.system_docs import hospitality_documentation
from .domains.laboratory import decision_board as _lab_decision_board, history as _lab_history, records as _lab_records, refresh_lab_learning, trends as _lab_trends, vintage_outlook as _lab_vintage_outlook
from .domains.cistern_learning import refresh_cistern_learning
from .domains.laboratory_routes import router as laboratory_router
from .domains.olives import calculate_cost_analysis as _olive_cost_analysis, harvest_preference_context as _olive_pref_context, prediction_context as _olive_prediction_context
from .domains.olive_routes import router as olive_router
from .domains.observation_routes import router as observation_router
from .domains.register_routes import router as register_router
from .domains.harvest_routes import router as harvest_router
from .domains.payroll_presence import labor_identity_links as _labor_identity_links
from .domains.payroll_admin_routes import router as payroll_admin_router
from .domains.payroll import (
    attach_labor_invoice_payments as _attach_labor_invoice_payments,
    consolidate_labor_people as _consolidate_labor_people,
    labor_payment_integrity as _labor_payment_integrity,
    payroll_summary as _payroll_summary,
    labor_card_payment_totals as _labor_card_payment_totals,
    worker_payment_batch_key as _worker_payment_batch_key,
)
from .domains.projections import build_operational_projections
from .domains.public_routes import router as public_router
from .domains.treatment_routes import router as treatment_router, treatment_actions as _treatment_actions
from .domains.treatment_scouting import treatment_scouting_workflows
from .domains.treatments import attach_treatment_costs as _attach_treatment_costs, existing_treatment_safety_audits as _existing_treatment_safety_audits, field_review_guidance as _treatment_field_review_guidance, inventory_readiness as _treatment_inventory_readiness, latest_hail_followup as _latest_treatment_hail_followup, product_guidance as _treatment_product_guidance, treatment_record_evidence_gaps as _treatment_record_evidence_gaps, treatment_scenario_options as _treatment_scenario_options
from .domains.people_roles import ESTATE_ROLES, require_discipline_approval, session_payload
from .domains.whatsapp_people import person_ivr as _person_whatsapp_ivr, save_person_ivr as _save_person_whatsapp_ivr
from .domains.worker_portal_routes import router as worker_portal_router
from .domains.reference_chains import observation_chain_options
from .display_data import system_status_payload, weather_context_payload
from .display_provisioning import cellar_label_origin, router as display_provisioning_router
from .fattureincloud import pull_fattureincloud
from .historical_dashboard import FIRST_ESTATE_VINTAGE, historical_forecast_evidence, historical_note_facts
from .inventory import sync_treatment_inventory_use
from .planning_sync import publish_task_to_google
from .observation_catalog import reference_catalog
from .etna import etna_status
from .intelligence import ProcessAlreadyRunningError, analyze_intake, current_home_assistant_presence, fit_disease_pressure_model, home_assistant_local_only_user_ids, home_assistant_manager_camera_catalog, home_assistant_people, home_assistant_state_map, integration_loop, mark_power_monitor_stopped, power_continuity_heartbeat, power_continuity_loop, predict_next_treatment, pressure_codes_for_crop, refresh_treatment_weather_learning, resolve_condition_alert, run_full_refresh, run_named_process, visual_rtsp_source_health
from .process_control import save_process_controls
from .prediction_refresh import request_harvest_refresh
from .prediction_sources import prediction_source_context
from .production_impact import adjust_production_forecasts
from .whatsapp_registration import router as whatsapp_router
from .whatsapp_blend import parse_crate_count as _parse_crate_count
from .whatsapp_notices import (
    reconcile_answered_notices as _reconcile_answered_whatsapp_notices,
)
from .models import (
    ActivityCreate,
    BlockCreate,
    CashTransactionCreate,
    FinancialDocumentCreate,
    ParcelMapUpdate,
    TaskCreate,
    TaskStatusUpdate,
    VarietyCreate,
    WeatherObservationCreate,
)
from .quick_entry import save_quick_entry
from .service import audit, estate_id, json_ready, new_id, season_for_year
from .social import publish_facebook, publish_instagram, publish_social_photo, social_dashboard
from .tank_labels import (
    CELLAR_STAGES,
    DENOMINATION_CLASSES,
    LEGAL_PROFILE_DEFAULTS,
    PROCESSING_PHASES,
    WINE_COLORS,
    WINE_TYPES,
    enrollment_rows,
    kiosk_rows,
    provisioned_device_rows,
    tank_label_rows,
)
APP_STARTED_MONOTONIC = time.monotonic()
TV_CONFIG_FIELDS: dict[str, tuple[str, Any, Any]] = {
    "tv_time_zone": ("str", None, None), "tv_cycle_seconds": ("int", 10, 300),
    "tv_refresh_seconds": ("int", 30, 1800), "tv_camera_entities": ("str", None, None),
    "tv_vineyard_camera_page_enabled": ("bool", None, None), "tv_adsb_url": ("str", None, None),
    "tv_ais_url": ("str", None, None), "tv_map_brightness_percent": ("int", 60, 180),
    "tv_weather_zoom_level": ("int", 0, 6), "tv_adsb_zoom_level": ("int", -6, 20),
    "tv_ais_zoom_level": ("int", -6, 20), "tv_adsb_target_size_percent": ("int", 30, 180),
    "tv_ais_target_size_percent": ("int", 30, 180), "tv_theme": ("choice", ("auto", "dark", "light"), None),
    "tv_controls_enabled": ("bool", None, None), "tv_home_airport_enabled": ("bool", None, None),
    "tv_home_airport_icao": ("icao", None, None), "etna_enabled": ("bool", None, None),
    "etna_refresh_minutes": ("int", 2, 60), "etna_webcam_codes": ("str", None, None),
}

def _read_addon_options() -> dict[str, Any]:
    values: dict[str, Any] = {}
    try:
        values.update(json.loads(Path("/data/options.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        pass
    try:
        values.update(json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        pass
    return values


def _write_runtime_options(values: dict[str, Any]) -> None:
    RUNTIME_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    try:
        loaded = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            current.update(loaded)
    except (OSError, ValueError, TypeError):
        pass
    current.update(values)
    temporary = RUNTIME_OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(RUNTIME_OPTIONS_PATH)


def _clean_tv_options(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = set(payload) - set(TV_CONFIG_FIELDS)
    if unknown:
        raise ValueError("Unsupported TV settings: " + ", ".join(sorted(unknown)))
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        kind, minimum, maximum = TV_CONFIG_FIELDS[key]
        if kind == "bool":
            cleaned[key] = bool(value)
        elif kind == "int":
            number = int(value)
            if number < minimum or number > maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
            cleaned[key] = number
        elif kind == "choice":
            choice = str(value).strip().casefold()
            if choice not in minimum:
                raise ValueError(f"Choose one of: {', '.join(minimum)}")
            cleaned[key] = choice
        elif kind == "icao":
            code = str(value).strip().upper()
            if not re.fullmatch(r"[A-Z0-9]{4}", code):
                raise ValueError("Enter a four-character airport ICAO code")
            cleaned[key] = code
        else:
            cleaned[key] = str(value).strip()
    return cleaned


logger = logging.getLogger("baiamonte")
@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    try:
        refresh_lab_learning()
    except Exception:
        logger.exception("Could not initialize durable laboratory learning")
    try:
        refresh_treatment_weather_learning()
    except Exception:
        logger.exception("Could not initialize durable treatment learning")
    try:
        fit_disease_pressure_model()
    except Exception:
        logger.exception("Disease learn failed")
    try: refresh_cistern_learning()
    except Exception: logger.exception("Cistern learn failed")
    try:
        _ensure_current_manual_tanks(get_settings())
    except Exception:
        logger.exception("Could not initialize configured cellar tanks")
    try:
        power_continuity_heartbeat(startup=True)
    except Exception:
        logger.exception("Could not initialize power-continuity monitoring")
    try:
        _reconcile_answered_whatsapp_notices()
    except Exception:
        logger.exception("Could not reconcile answered WhatsApp notices during startup")
    tasks = [asyncio.create_task(integration_loop()), asyncio.create_task(power_continuity_loop())]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    try:
        mark_power_monitor_stopped()
    except Exception:
        logger.exception("Could not record the planned power-monitor shutdown")


app = FastAPI(title="Baiamonte Vineyard API", version="1.7.4", lifespan=lifespan)
app.add_middleware(ReleaseAssetCacheMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.include_router(admin_router)
app.include_router(alerts_intake_router)
app.include_router(communications_gmail_router)
app.include_router(communications_meta_router)
app.include_router(communications_meta_webhook_router)
app.include_router(communications_system_whatsapp_router)
app.include_router(display_provisioning_router)
app.include_router(bottling_router)
app.include_router(camera_router)
app.include_router(camera_snapshot_router)
app.include_router(cellar_router)
app.include_router(damage_router)
app.include_router(dashboard_router)
app.include_router(disease_router)
app.include_router(fertilization_router)
app.include_router(finance_inventory_router)
app.include_router(hospitality_router)
app.include_router(intelligence_router)
app.include_router(harvest_router)
app.include_router(laboratory_router)
app.include_router(olive_router)
app.include_router(observation_router)
app.include_router(payroll_admin_router)
app.include_router(public_router)
app.include_router(register_router)
app.include_router(treatment_router)
app.include_router(whatsapp_router)
app.include_router(worker_portal_router)
static_dir = Path(__file__).resolve().parent / "static"
docs_dir = Path(__file__).resolve().parent.parent / "docs"


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, error: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with existing data", "code": error.args[0]})


@app.get("/health")
def health() -> dict[str, Any]:
    row = fetch_one("SELECT 1 AS database_ok")
    return {"ok": True, "database": bool(row and row["database_ok"] == 1)}


@app.post("/api/v1/system/refresh", dependencies=[Depends(authorize_write)])
async def refresh_entire_system() -> dict[str, Any]:
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
        "parcels": fetch_all(
            "SELECT id,municipality,cadastral_sheet,parcel_number,tenure,contract_protocol,cadastral_area_ha,conducted_area_ha,official_vineyard_area_ha "
            "FROM cadastral_parcels WHERE estate_id=%s ORDER BY municipality,cadastral_sheet,parcel_number",
            (estate_id(),),
        ),
        "varieties": fetch_all("SELECT * FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),)),
        "wine_lots": fetch_all("SELECT id,code,name,stage,volume_l,current_container_id FROM wine_lots WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "containers": fetch_all("SELECT id,code,name,container_type,capacity_l,status FROM cellar_containers WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),)),
        "products": fetch_all("SELECT p.id,p.sku,p.name,p.product_type,p.category_name,p.active_ingredient,p.registration_number,p.unit,p.track_inventory,"
                              "EXISTS(SELECT 1 FROM treatment_product_profiles t WHERE t.product_id=p.id AND t.active=1) treatment_reference "
                              "FROM products p WHERE p.estate_id=%s AND p.active=1 ORDER BY p.name", (estate_id(),)),
        "categories": ["canopy", "cultivation", "fertilizer", "irrigation", "maintenance", "mowing", "pruning", "scouting", "treatment", "harvest", "cellar", "general"],
        "observation_chains": observation_chain_options(year),
        "treatment_scouting_workflows": treatment_scouting_workflows(year, None),
        **reference_catalog(),
    })


@app.get("/api/v1/session", dependencies=[Depends(authorize)])
def session_access(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    # Owns sync_ingress_identity(request), "approval_permissions": role_approval_permissions, "finance": normalized in finance_usernames(settings), "dedicated_worker": dedicated_worker, "hourly_worker": hourly_worker, and not dedicated_worker.
    return session_payload(request, settings)


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


@app.get("/api/v1/admin/system-documentation", dependencies=[Depends(authorize_admin)])
def system_documentation() -> dict[str, Any]:
    settings = get_settings()
    hospitality_docs = hospitality_documentation(people_profiles())
    vineyard_url = "http://192.168.0.10:8101"
    mcp_url = "http://192.168.0.10:8100/mcp"
    services = [
        {"name": "Home Assistant", "port": 8123, "url": "http://192.168.0.10:8123", "health_url": "http://192.168.0.10:8123/api/", "access": "Home Assistant account", "purpose": "Estate devices, dashboards, users and Supervisor"},
        {"name": "Vineyard Operations", "port": 8101, "url": vineyard_url, "health_url": f"{vineyard_url}/health", "access": "Home Assistant ingress", "purpose": "Authoritative vineyard operations interface"},
        hospitality_docs["service"],
        {"name": "Vineyard TV", "port": 8101, "url": f"{vineyard_url}/tv", "health_url": f"{vineyard_url}/api/display-data", "access": "Read-only display", "purpose": "Samsung TV and kiosk rotation"},
        {"name": "Baiamonte MCP", "port": 8100, "url": mcp_url, "health_url": None, "access": "Bearer token", "purpose": "Codex and approved automation bridge"},
        {"name": "ADS-B", "port": urllib.parse.urlparse(settings.tv_adsb_url).port or 8998, "url": settings.tv_adsb_url, "health_url": f"{settings.tv_adsb_url.rstrip('/')}/api/status", "access": "Local network", "purpose": "Aircraft map and target feed"},
        {"name": "AIS", "port": urllib.parse.urlparse(settings.tv_ais_url).port or 8999, "url": settings.tv_ais_url, "health_url": f"{settings.tv_ais_url.rstrip('/')}/api/status", "access": "Local network", "purpose": "Sicily vessel map and target feed"},
        {"name": "MariaDB", "port": settings.db_port, "url": None, "health_url": None, "access": "Add-on network only", "purpose": f"Authoritative database · {settings.db_host}/{settings.db_name}"},
    ]
    api_groups = [
        {"name": "Status & display", "routes": [
            {"method": "GET", "path": "/health", "access": "Public health check", "purpose": "Application readiness"},
            {"method": "GET", "path": "/api/v1/session", "access": "Signed in", "purpose": "Current user and permissions"},
            {"method": "GET", "path": "/api/v1/system/status", "access": "Signed in", "purpose": "Estate service and device health"},
            {"method": "GET", "path": "/api/display-data", "access": "Display", "purpose": "TV dashboard data"},
        ]},
        {"name": "Administration", "routes": [
            {"method": "GET", "path": "/api/v1/admin/control", "access": "Administrator", "purpose": "Processes, errors, storage, users and labor"},
            {"method": "GET", "path": "/api/v1/admin/system-documentation", "access": "Administrator", "purpose": "This safe system registry"},
            {"method": "GET", "path": "/api/v1/admin/system-manual.pdf", "access": "Administrator", "purpose": "View or download the system manual"},
            {"method": "GET/PUT", "path": "/api/v1/admin/tv-config", "access": "Administrator", "purpose": "TV and camera configuration"},
            {"method": "POST", "path": "/api/v1/admin/run/{process}", "access": "Administrator", "purpose": "Run one scheduled process"},
        ]},
        hospitality_docs["api_group"],
        {"name": "Intake & integrations", "routes": [
            {"method": "POST", "path": "/api/v1/intake/mac", "access": "API key", "purpose": "Authenticated Mac/Codex review intake"},
            {"method": "POST", "path": "/api/v1/intake/upload", "access": "Operations", "purpose": "Document and photo review intake"},
            {"method": "GET/POST", "path": "/webhooks/whatsapp", "access": "Meta signature/verify token", "purpose": "Official WhatsApp inbound events"},
            {"method": "POST", "path": "/mcp", "access": "MCP bearer token", "purpose": "Model Context Protocol endpoint"},
        ]},
        {"name": "Public website", "routes": [
            {"method": "GET", "path": "/public/v1/harvest.json", "access": "Public feed token when enabled", "purpose": "Approved harvest dates and vintage summary"},
            {"method": "GET", "path": "/public/v1/harvest.ics", "access": "Public feed token when enabled", "purpose": "Harvest calendar feed"},
        ]},
    ]
    credentials = [
        {"name": "MariaDB login", "configured": _configured(settings.db_password), "location": "Home Assistant add-on configuration"},
        {
            "name": "Mac / Codex intake",
            "configured": _configured(settings.api_key) or _configured(settings.mcp_server_token),
            "location": "Authenticated by api_key or mcp_server_token" if (_configured(settings.api_key) or _configured(settings.mcp_server_token)) else "Set api_key or mcp_server_token in the Home Assistant add-on configuration",
        },
        {"name": "MCP bearer token", "configured": _configured(settings.mcp_server_token), "location": "Home Assistant add-on configuration"},
        {"name": "OpenAI API", "configured": _configured(settings.openai_api_key), "location": "Home Assistant add-on configuration"},
        {"name": "Gmail intake", "configured": _configured(settings.gmail_address) and _configured(settings.gmail_app_password), "location": "Home Assistant add-on configuration"},
        {"name": "Meta WhatsApp", "configured": _configured(settings.whatsapp_access_token) and _configured(settings.whatsapp_phone_number_id), "location": "Home Assistant add-on configuration"},
        {"name": "Fatture in Cloud", "configured": _configured(settings.fattureincloud_token) and _configured(settings.fattureincloud_company_id), "location": "Home Assistant add-on configuration"},
        {"name": "Website publisher", "configured": _configured(settings.public_publish_url) and _configured(settings.public_publish_token), "location": "Home Assistant add-on configuration"},
        {"name": "Treatment planning defaults", "configured": settings.treatment_planning_water_l > 0 and _configured(settings.treatment_default_sprayer), "location": f"Home Assistant add-on configuration · {settings.treatment_planning_water_l:g} L · {settings.treatment_default_sprayer or 'sprayer not selected'}"},
        {
            "name": "Facebook",
            "configured": _configured(settings.meta_page_access_token or settings.whatsapp_access_token) and _configured(settings.facebook_page_id),
            "location": "Protected Meta connection configured" if (_configured(settings.meta_page_access_token or settings.whatsapp_access_token) and _configured(settings.facebook_page_id)) else "Set a Meta/WhatsApp access token and facebook_page_id in the Home Assistant add-on configuration",
        },
        {
            "name": "Instagram",
            "configured": _configured(settings.meta_page_access_token or settings.whatsapp_access_token) and _configured(settings.instagram_business_account_id),
            "location": "Protected Meta connection configured" if (_configured(settings.meta_page_access_token or settings.whatsapp_access_token) and _configured(settings.instagram_business_account_id)) else "Set a Meta/WhatsApp access token and instagram_business_account_id in the Home Assistant add-on configuration",
        },
    ]
    access_profiles = [
        {"name": "Administrators", "users": _csv_values(settings.admin_usernames), "scope": "System configuration, people, payroll, messaging and process control"},
        {"name": "Operations", "users": _csv_values(settings.operations_usernames), "scope": "Vineyard records, work, harvest, cellar and review"},
        {"name": "Finance", "users": _csv_values(settings.finance_usernames), "scope": "Read-only Fatture in Cloud mirror and financial review"},
        {"name": "Workers", "users": [item.split(":", 1)[0] for item in _csv_values(settings.worker_usernames)], "scope": "Personal clock, services, receipts and approved history"},
        hospitality_docs["access_profile"],
        {"name": "Viewers", "users": _csv_values(settings.viewer_usernames), "scope": "Read-only wall panels, iPad and TV displays"},
    ]
    links = [
        {"name": "Vineyard add-on configuration", "url": "/hassio/addon/0c04eef6_baiamonte_vineyard/config", "purpose": "Protected credentials and service settings"},
        {"name": "Installed add-on", "url": "/hassio/addon/0c04eef6_baiamonte_vineyard/info", "purpose": "Version, logs, restart and update"},
        {"name": "Home Assistant people", "url": "/config/person", "purpose": "Authoritative names, pictures and presence"},
        {"name": "Home Assistant dashboards", "url": "/config/lovelace/dashboards", "purpose": "Managed dashboard registry"},
        {"name": "GitHub source", "url": "https://github.com/drahamin/tenuta-baiamonte-vineyard", "purpose": "Versioned source and releases"},
    ]
    notes = ["MariaDB is the sole operational authority; workbooks are not consulted or accepted for updates.", *hospitality_docs["notes"], "Secrets are intentionally never returned by this page.", f"MCP writes are {'enabled' if settings.mcp_allow_writes else 'disabled'}; allowed hosts are configured separately."]
    return json_ready({"generated_at": datetime.now(timezone.utc), "version": addon_version(), "services": services, "api_groups": api_groups, "credentials": credentials, "access_profiles": access_profiles, "links": links, "notes": notes})


@app.get("/api/v1/admin/system-manual.pdf", dependencies=[Depends(authorize_admin)])
def system_manual_pdf(download: bool = Query(False)):
    path = docs_dir / "Tenuta_Baiamonte_System_Manual.pdf"
    if not path.is_file(): raise HTTPException(404, "The system manual has not been installed")
    disposition = "attachment" if download else "inline"
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": f'{disposition}; filename="Tenuta_Baiamonte_System_Manual.pdf"', "Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@app.get("/api/v1/admin/control", dependencies=[Depends(authorize_admin)])
def admin_control(request: Request) -> dict[str, Any]:
    foundation = admin_control_foundation(APP_STARTED_MONOTONIC)
    controls = foundation["controls"]
    now = foundation["checked_at"]
    processes = foundation["processes"]
    review = foundation["review_queue"]
    recovery_errors = foundation["recovery_errors"]
    failed_intake = foundation["failed_intake"]
    labor_people = [
        {"key": "giancarlo", "name": "Giancarlo Pafumi", "person_entity": "person.giancarlo", "gps_entity": "device_tracker.iphone_che", "name_aliases": ("giancarlo", "giancarlo pafumi"), "camera_aliases": ("giancarlo", "giancarlo pafumi"), "pay_model": "monthly", "payment_schedule": "Paid on the 15th for the prior month", "payroll_scope": "part_time", "role": "Estate manager"},
        {"key": "luca", "name": "Luca Schiliro Cognato", "person_entity": "person.luca_schiliro_cognato", "gps_entity": "device_tracker.luca_iphone", "name_aliases": ("luca", "schiliro", "cognato"), "camera_aliases": ("luca", "schiliro", "cognato"), "pay_model": "year_round_hourly", "payment_schedule": "Invoice received on an undetermined schedule", "payroll_scope": "contractor", "role": "Year-round contractor"},
        {"key": "carmella", "name": "Carmela Pafumi", "person_entity": "person.carmela", "name_aliases": ("carmela", "carmella", "carmela pafumi"), "camera_aliases": ("carmela", "carmella", "carmela pafumi"), "pay_model": "seasonal_hourly", "payment_schedule": "Seasonal hourly reconciliation", "payroll_scope": "contractor", "role": "Seasonal labor"},
        {"key": "mattia", "name": "Mattia", "person_entity": "person.mattia", "name_aliases": ("mattia",), "camera_aliases": ("mattia",), "pay_model": "seasonal_hourly", "payment_schedule": "Seasonal hourly reconciliation", "payroll_scope": "contractor", "role": "Seasonal labor"},
        {"key": "nunzio", "name": "Nunzio", "name_aliases": ("nunzio",), "camera_aliases": (), "pay_model": "seasonal_hourly", "payment_schedule": "Seasonal hourly reconciliation", "payroll_scope": "contractor", "role": "Seasonal labor"},
        {"key": "seasonal-worker-1", "name": "Unidentified part-time worker 1", "name_aliases": ("unidentified part-time worker 1",), "camera_aliases": (), "pay_model": "seasonal_hourly", "payment_schedule": "Seasonal hourly reconciliation", "payroll_scope": "contractor", "role": "Seasonal labor"},
        {"key": "seasonal-worker-2", "name": "Unidentified part-time worker 2", "name_aliases": ("unidentified part-time worker 2",), "camera_aliases": (), "pay_model": "seasonal_hourly", "payment_schedule": "Seasonal hourly reconciliation", "payroll_scope": "contractor", "role": "Seasonal labor"},
    ]
    canonical_labor_keys = {person["key"] for person in labor_people}
    people_specs = [
        {"key": "david", "name": "David Rahamin", "username": "rahamin", "role": "Administrator", "person_entity": "person.david_rahamin"},
        {"key": "wendy", "name": "Wendy Creque", "username": "creque", "role": "Administrator", "person_entity": "person.wendy_creque"},
        {"key": "giancarlo", "name": "Giancarlo Pafumi", "username": "giancarlo", "role": "Estate manager", "person_entity": "person.giancarlo", "gps_entity": "device_tracker.iphone_che", "camera_aliases": ("giancarlo", "giancarlo pafumi")},
        {"key": "giuseppe", "name": "Giuseppe Regalia", "username": "giuseppe", "role": "Accountant", "person_entity": "person.giuseppe_regalia"},
        {"key": "luca", "name": "Luca Schiliro Cognato", "username": "cognato", "role": "Contractor", "person_entity": "person.luca_schiliro_cognato", "gps_entity": "device_tracker.luca_iphone", "camera_aliases": ("luca", "schiliro", "cognato")},
        {"key": "sebastian", "name": "Sebastiano Vinci", "username": "sebastian", "role": "Agronomist & Enologist", "person_entity": "person.sebastian_vinvi", "name_aliases": ("sebastian", "sebastiano", "sebastiano vinci", "sebastian vinvi")},
        {"key": "fede", "name": "Fede Camuto", "role": "Estate contact", "person_entity": "person.fede_camuto"},
        {"key": "mattia", "name": "Mattia", "username": "mattia", "role": "Seasonal labor", "person_entity": "person.mattia", "camera_aliases": ("mattia",)},
        {"key": "carmella", "name": "Carmela Pafumi", "username": "carmela", "role": "Seasonal labor", "person_entity": "person.carmela", "name_aliases": ("carmela", "carmella", "carmela pafumi"), "camera_aliases": ("carmela", "carmella", "carmela pafumi")},
    ]
    local_only_user_ids = home_assistant_local_only_user_ids()
    ha_people = [
        item for item in home_assistant_people()
        if str((item.get("attributes") or {}).get("user_id") or "") not in local_only_user_ids
    ]
    saved_people_profiles = people_profiles()
    labor_identity_links = _labor_identity_links()
    linked_labor_key_by_entity = {entity_id: worker_key for worker_key, entity_id in labor_identity_links.items()}
    saved_profiles_by_username = {
        str(profile.get("username") or "").strip().casefold(): (entity_id, profile)
        for entity_id, profile in saved_people_profiles.items()
        if isinstance(profile, dict) and profile.get("username")
    }
    claimed_people: set[str] = set()
    for spec in people_specs:
        original_entity = spec["person_entity"]
        profile = saved_people_profiles.get(original_entity, {})
        if not profile and spec.get("username"):
            _, profile = saved_profiles_by_username.get(str(spec["username"]).casefold(), ("", {}))
        ha_person = _match_home_assistant_person(spec, ha_people, profile, claimed_people)
        if ha_person:
            actual_entity = str(ha_person.get("entity_id") or original_entity)
            claimed_people.add(actual_entity)
            spec["legacy_person_entity"] = original_entity if actual_entity != original_entity else None
            spec["person_entity"] = actual_entity
            if linked_labor_key_by_entity.get(actual_entity):
                spec["key"] = linked_labor_key_by_entity[actual_entity]
        attributes = ha_person.get("attributes") or {}
        friendly_name = str(attributes.get("friendly_name") or "").strip()
        if friendly_name:
            spec["name"] = friendly_name
        spec["ha_user_id"] = attributes.get("user_id")
        spec["ha_picture"] = attributes.get("entity_picture")
        spec["ha_person_synced"] = bool(ha_person)

    # An existing saved profile can retain the linked HA user id even when its
    # Person entity is no longer returned. Local-only service accounts remain
    # valid in Home Assistant but do not belong in the estate People directory.
    people_specs = [
        spec for spec in people_specs
        if str(spec.get("ha_user_id") or "") not in local_only_user_ids
    ]

    known_people = {spec["person_entity"] for spec in people_specs}
    for item in ha_people:
        entity_id = str(item.get("entity_id") or "")
        if entity_id in known_people:
            continue
        attributes = item.get("attributes") or {}
        key = linked_labor_key_by_entity.get(entity_id) or entity_id.removeprefix("person.")
        people_specs.append({
            "key": key,
            "name": str(attributes.get("friendly_name") or key.replace("_", " ").title()),
            "role": "Home Assistant person",
            "person_entity": entity_id,
            "ha_user_id": attributes.get("user_id"),
            "ha_picture": attributes.get("entity_picture"),
            "ha_person_synced": True,
        })
        known_people.add(entity_id)
    configured_levels = {
        "rahamin": "admin", "creque": "admin", "giancarlo": "operations",
        "giuseppe": "operations", "cognato": "operations", "sebastian": "operations",
        "mattia": "worker", "carmela": "worker",
    }
    for spec in people_specs:
        profile = saved_people_profiles.get(spec["person_entity"], {})
        if not profile and spec.get("legacy_person_entity"):
            profile = saved_people_profiles.get(spec["legacy_person_entity"], {})
        if not profile and spec.get("username"):
            _, profile = saved_profiles_by_username.get(str(spec["username"]).casefold(), ("", {}))
        if profile:
            spec.update({key: profile[key] for key in ("username", "role") if profile.get(key)})
        spec["access_level"] = profile.get("access_level") or configured_levels.get(str(spec.get("username") or "").casefold(), "viewer")
        default_hourly = any(person["key"] == spec["key"] and "hourly" in person["pay_model"] for person in labor_people)
        spec["track_hourly_labor"] = bool(profile.get("track_hourly_labor", default_hourly))
    non_hourly_labor_keys = {person["key"] for person in labor_people if "hourly" not in person["pay_model"]}
    explicitly_disabled = {spec["key"] for spec in people_specs if not spec["track_hourly_labor"]}
    labor_people = [person for person in labor_people if "hourly" not in person["pay_model"] or person["key"] not in explicitly_disabled]
    for spec in people_specs:
        if not spec["track_hourly_labor"] and spec["key"] not in non_hourly_labor_keys:
            continue
        normalized_name = re.sub(r"\s+", " ", str(spec["name"]).casefold()).strip()
        aliases = tuple(dict.fromkeys((
            normalized_name,
            *(part for part in re.split(r"\W+", normalized_name) if len(part) > 1),
            spec["key"],
        )))
        labor_people.append({
            "key": spec["key"], "name": spec["name"], "person_entity": spec["person_entity"],
            "gps_entity": spec.get("gps_entity"), "name_aliases": aliases,
            "camera_aliases": spec.get("camera_aliases") or aliases,
            "ha_user_id": spec.get("ha_user_id"), "ha_person_synced": bool(spec.get("ha_person_synced")),
            "pay_model": "seasonal_hourly", "payment_schedule": "Hourly reconciliation",
            "payroll_scope": "contractor", "role": spec.get("role") or "Hourly labor",
        })
    labor_people = _consolidate_labor_people(labor_people, canonical_labor_keys)
    camera_identity_entities = {
        "sensor.gate_doorbell_person_name", "sensor.front_gate_person_name",
        "sensor.vineyard_north_person_name", "sensor.mid_vineyard_north_person_name",
        "sensor.rear_gate_person_name",
    }
    labor_ha_states = {item["entity_id"]: item for item in ha_people if item.get("entity_id")}
    labor_ha_states.update(home_assistant_state_map(
        {item[key] for item in people_specs for key in ("person_entity", "gps_entity") if item.get(key)} | camera_identity_entities
    ))
    discovered_trackers: set[str] = set()
    for spec in people_specs:
        attributes = (labor_ha_states.get(spec["person_entity"]) or {}).get("attributes") or {}
        source_entity = attributes.get("source")
        if isinstance(source_entity, str) and source_entity.startswith("device_tracker."):
            discovered_trackers.add(source_entity)
        for entity_id in attributes.get("device_trackers") or []:
            if isinstance(entity_id, str) and entity_id.startswith("device_tracker."):
                discovered_trackers.add(entity_id)
    labor_ha_states.update(home_assistant_state_map(discovered_trackers))

    def recent_ha_state(item: dict[str, Any], minutes: int) -> bool:
        try:
            observed = datetime.fromisoformat(str(item.get("last_updated") or item.get("last_changed") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - observed.astimezone(timezone.utc) <= timedelta(minutes=minutes)
        except (TypeError, ValueError):
            return False

    def recent_camera_match(aliases: tuple[str, ...]) -> bool:
        for entity_id in camera_identity_entities:
            item = labor_ha_states.get(entity_id) or {}
            value = str(item.get("state") or "").casefold()
            if any(alias in value for alias in aliases) and recent_ha_state(item, 30):
                return True
        return False

    labor_reconciliation = []
    for person in labor_people:
        patterns = tuple(alias.casefold() for alias in person["name_aliases"])
        person_match = "(" + " OR ".join("LOWER(TRIM(person_or_crew)) = %s" for _ in patterns) + ")"
        person_params = (estate_id(), *patterns)
        totals = fetch_one(
            "SELECT "
            "COALESCE(SUM(CASE WHEN work_date=CURDATE() THEN COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) ELSE 0 END),0) today_hours,"
            "COALESCE(SUM(CASE WHEN work_date>=CURDATE()-INTERVAL 6 DAY THEN COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) ELSE 0 END),0) seven_day_hours,"
            "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND MONTH(work_date)=MONTH(CURDATE()) THEN COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) ELSE 0 END),0) month_hours,"
            "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) ELSE 0 END),0) year_hours,"
            "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND MONTH(work_date)=MONTH(CURDATE()) THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) month_cost_eur "
            f"FROM labor_entries WHERE estate_id=%s AND {person_match}",
            person_params,
        ) or {}
        totals.update(_labor_card_payment_totals(estate_id(), patterns))
        daily = fetch_all(
            "SELECT id record_id,work_date,COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) hours,"
            "COALESCE(NULLIF(work_performed,''),NULLIF(notes,'')) details,"
            "location_text locations,entry_source sources,payment_status "
            f"FROM labor_entries WHERE estate_id=%s AND {person_match} "
            "ORDER BY work_date DESC,id DESC",
            person_params,
        )
        years = fetch_all(
            "SELECT YEAR(work_date) work_year,COUNT(*) entry_count,"
            "COALESCE(SUM(COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)),0) hours,"
            "COALESCE(SUM(COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0)),0) cost_eur "
            f"FROM labor_entries WHERE estate_id=%s AND {person_match} AND work_date IS NOT NULL "
            "GROUP BY YEAR(work_date) ORDER BY work_year DESC",
            person_params,
        )
        entries = fetch_all(
            "SELECT id,source_labor_id,work_date,shift_label,person_or_crew,role,work_category,work_performed,location_text,"
            "start_time,end_time,regular_hours,overtime_hours,hourly_rate_eur,labor_cost_eur,other_cost_eur,kg_handled,"
            "incident_near_miss,approved_by,payment_status,payroll_scope,entry_source,notes "
            f"FROM labor_entries WHERE estate_id=%s AND {person_match} ORDER BY work_date DESC,id DESC LIMIT 1000",
            person_params,
        )
        person_item = labor_ha_states.get(person.get("person_entity", "")) or {}
        gps_item = labor_ha_states.get(person.get("gps_entity", "")) or {}
        person_attributes = person_item.get("attributes") or {}
        source_entity = str(person_attributes.get("source") or "")
        source_state = labor_ha_states.get(source_entity) if source_entity.startswith("device_tracker.") else None
        source_is_stale = bool(source_entity) and not recent_ha_state(source_state or {}, 120)
        gps_is_fresh = bool(gps_item) and recent_ha_state(gps_item, 120)
        person_presence = None if source_is_stale else current_home_assistant_presence(person_item)
        gps_presence = current_home_assistant_presence(gps_item) if gps_is_fresh else None
        live_presence = person_presence or gps_presence
        if live_presence == "on_site" or recent_camera_match(person["camera_aliases"]):
            onsite_status = "on_site"
        elif live_presence == "away":
            onsite_status = "away"
        else:
            onsite_status = "uncertain"
        labor_reconciliation.append({
            **{key: value for key, value in person.items() if key not in {"gps_entity", "camera_aliases", "name_aliases"}},
            "identified": not str(person.get("key") or "").startswith("seasonal-worker-")
            and not str(person.get("name") or "").casefold().startswith("unidentified part-time worker"),
            "home_assistant_linked": bool(person.get("ha_person_synced")),
            "totals": totals,
            "daily": daily,
            "years": years,
            "entries": entries,
            "current_status": onsite_status,
        })

    all_labor_entries = fetch_all(
        "SELECT id,source_labor_id,work_date,shift_label,person_or_crew,role,work_category,work_performed,location_text,"
        "start_time,end_time,regular_hours,overtime_hours,hourly_rate_eur,labor_cost_eur,other_cost_eur,kg_handled,"
        "incident_near_miss,approved_by,payment_status,payroll_scope,entry_source,notes "
        "FROM labor_entries WHERE estate_id=%s ORDER BY work_date DESC,id DESC LIMIT 1000",
        (estate_id(),),
    )
    named_aliases = tuple(dict.fromkeys(alias.casefold() for person in labor_people for alias in person["name_aliases"]))
    named_match = "(" + " OR ".join("LOWER(TRIM(person_or_crew)) = %s" for _ in named_aliases) + ")"
    unassigned_labor = fetch_all(
        "SELECT person_or_crew,COUNT(*) entry_count,MIN(work_date) first_date,MAX(work_date) last_date,"
        "COALESCE(SUM(COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)),0) hours,"
        "COALESCE(SUM(COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0)),0) cost_eur "
        f"FROM labor_entries WHERE estate_id=%s AND NOT {named_match} GROUP BY person_or_crew ORDER BY last_date DESC,person_or_crew",
        (estate_id(), *named_aliases),
    )

    timesheet_rows = fetch_all(
        "SELECT id,source,external_id,sender_name,sender_address,received_at,title,message_text,original_filename,"
        "media_type,classification,ai_summary,extracted_data,review_status,review_reason "
        "FROM intake_items WHERE estate_id=%s AND review_status IN ('new','ready_for_review') AND ("
        "classification IN ('labor','labor_hours','timesheet') OR LOWER(COALESCE(title,'')) REGEXP 'timesheet|labor|hours|ore' "
        "OR LOWER(COALESCE(ai_summary,'')) REGEXP 'timesheet|labor hours|ore di') "
        "ORDER BY received_at DESC LIMIT 30",
        (estate_id(),),
    )
    timesheet_reviews = []
    for item in timesheet_rows:
        extracted = item.get("extracted_data")
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except (TypeError, json.JSONDecodeError):
                extracted = {}
        extracted = extracted if isinstance(extracted, dict) else {}
        proposed = extracted.get("timesheet_entries") or extracted.get("labor_entries") or extracted.get("daily_entries") or extracted.get("rows") or []
        if not isinstance(proposed, list):
            proposed = []
        normalized = []
        for row in proposed:
            if not isinstance(row, dict):
                continue
            work_date = row.get("work_date") or row.get("date")
            hours = row.get("regular_hours") if row.get("regular_hours") is not None else row.get("hours")
            if work_date and hours is not None:
                normalized.append({"work_date": str(work_date)[:10], "hours": hours, "notes": row.get("notes") or row.get("work_performed")})
        worker = extracted.get("person_or_crew") or extracted.get("worker") or extracted.get("person")
        rate = extracted.get("hourly_rate_eur") if extracted.get("hourly_rate_eur") is not None else extracted.get("hourly_rate")
        reimbursement_rows = extracted.get("reimbursable_expenses") or []
        if not isinstance(reimbursement_rows, list):
            reimbursement_rows = []
        source_text = str(item.get("ai_summary") or item.get("message_text") or "").strip()
        expense_notes = extracted.get("expense_notes") or extracted.get("expenses") or extracted.get("cost_notes")
        if isinstance(expense_notes, (dict, list)):
            expense_notes = json.dumps(expense_notes, ensure_ascii=False, default=str)
        if not expense_notes and source_text:
            cost_lines = [
                line.strip()
                for line in source_text.splitlines()
                if any(term in line.casefold() for term in ("expense", "benzina", "gasolio", "riparazione", "€", " eur"))
            ]
            expense_notes = " ".join(cost_lines)
        dates = sorted(row["work_date"] for row in normalized)
        timesheet_reviews.append({
            **item,
            "extracted_data": extracted,
            "reporter": item.get("sender_name") or item.get("sender_address"),
            "worker": worker,
            "hourly_rate_eur": rate,
            "entries": normalized,
            "expenses": reimbursement_rows,
            "period_start": dates[0] if dates else None,
            "period_end": dates[-1] if dates else None,
            "reported_total_hours": round(sum(float(row.get("hours") or 0) for row in normalized), 2),
            "expense_notes": str(expense_notes).strip() if expense_notes else None,
            "source_notes": source_text,
        })

    worker_submissions = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND "
        "((l.worker_username IS NOT NULL AND l.approval_status IN ('submitted','rejected')) OR "
        "(l.approval_status='approved' AND l.payment_status IN ('unpaid','unknown','part_paid'))) "
        "ORDER BY COALESCE(l.pay_due_date,l.work_date,DATE(l.submitted_at),DATE(l.clock_out_at),DATE(l.clock_in_at)) DESC,l.id DESC LIMIT 500",
        (estate_id(),),
    )
    _attach_labor_invoice_payments(worker_submissions, estate_id())
    for submission in worker_submissions:
        submission["payment_batch_key"] = _worker_payment_batch_key(submission)

    worker_payment_holds = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND l.approval_status='approved' AND l.payment_status='verification_needed' "
        "ORDER BY l.work_date IS NULL,l.work_date DESC,l.id DESC LIMIT 100",
        (estate_id(),),
    )
    _attach_labor_invoice_payments(worker_payment_holds, estate_id())

    payment_integrity = _labor_payment_integrity(estate_id())

    def state_timestamp(item: dict[str, Any]) -> str | None:
        return item.get("last_updated") or item.get("last_changed")

    people_directory = []
    for spec in people_specs:
        person_item = labor_ha_states.get(spec["person_entity"]) or {}
        person_attributes = person_item.get("attributes") or {}
        tracker_entities = [
            entity_id for entity_id in dict.fromkeys([
                spec.get("gps_entity"), person_attributes.get("source"), *(person_attributes.get("device_trackers") or [])
            ]) if isinstance(entity_id, str) and entity_id.startswith("device_tracker.")
        ]
        phone_states = [labor_ha_states[entity_id] for entity_id in tracker_entities if labor_ha_states.get(entity_id)]
        phone_states.sort(key=lambda item: str(state_timestamp(item) or ""), reverse=True)
        gps_item = phone_states[0] if phone_states else {}
        candidates = [item for item in (person_item, *phone_states) if item]
        candidates.sort(key=lambda item: str(state_timestamp(item) or ""), reverse=True)
        freshest = candidates[0] if candidates else {}
        camera_rows = []
        for entity_id in sorted(camera_identity_entities):
            camera_item = labor_ha_states.get(entity_id) or {}
            value = str(camera_item.get("state") or "")
            aliases = spec.get("camera_aliases") or ()
            if aliases and any(alias in value.casefold() for alias in aliases):
                camera_rows.append({"entity_id": entity_id, **camera_item})
        source_entity = str(person_attributes.get("source") or "")
        source_state = labor_ha_states.get(source_entity) if source_entity.startswith("device_tracker.") else None
        source_is_stale = bool(source_entity) and not recent_ha_state(source_state or {}, 120)
        gps_is_fresh = bool(gps_item) and recent_ha_state(gps_item, 120)
        person_presence = None if source_is_stale else current_home_assistant_presence(person_item)
        gps_presence = current_home_assistant_presence(gps_item) if gps_is_fresh else None
        live_presence = person_presence or gps_presence
        camera_fresh = any(recent_ha_state(item, 30) for item in camera_rows)
        if live_presence == "on_site" or camera_fresh:
            presence = "on_site"
        elif live_presence == "away":
            presence = "away"
        else:
            presence = "uncertain"
        freshest_attributes = freshest.get("attributes") or {}
        latitude = freshest_attributes.get("latitude")
        longitude = freshest_attributes.get("longitude")
        valid_coordinates = (
            isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))
            and -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180
            and not (float(latitude) == 0 and float(longitude) == 0)
        )
        location_fresh = bool(freshest) and recent_ha_state(freshest, 120) and valid_coordinates
        people_directory.append({
            **{key: value for key, value in spec.items() if key != "camera_aliases"},
            "whatsapp_ivr": _person_whatsapp_ivr(str(spec.get("person_entity") or ""), str(spec.get("name") or "")),
            "presence": presence,
            "location": freshest.get("state") or "unknown",
            "last_updated": state_timestamp(freshest),
            "latitude": latitude if location_fresh else None,
            "longitude": longitude if location_fresh else None,
            "gps_accuracy": freshest_attributes.get("gps_accuracy") if location_fresh else None,
            "location_fresh": location_fresh,
            "presence_note": "Location update is stale; presence is not asserted." if source_is_stale or (gps_item and not gps_is_fresh) else None,
            "person_state": person_item,
            "gps_entity": tracker_entities[0] if tracker_entities else None,
            "gps_state": gps_item or None,
            "phone_states": phone_states,
            "camera_evidence": camera_rows,
        })
    return json_ready({
        "paused": controls["paused"], "updated_at": controls.get("updated_at"), "updated_by": controls.get("updated_by"),
        "checked_at": now, "processes": processes, "review_queue": review,
        "connections": foundation["connections"],
        "runtime": foundation["runtime"],
        "mac_setup": foundation["mac_setup"],
        "ai_cost": ai_cost_summary(),
        "ai_profile": ai_request_profile(),
        "ai_service": ai_service_summary(),
        "estate_roles": list(ESTATE_ROLES),
        "people_directory": people_directory,
        "labor_reconciliation": labor_reconciliation,
        "labor_identity_links": labor_identity_links,
        "labor_history": all_labor_entries,
        "unassigned_labor": unassigned_labor,
        "timesheet_reviews": timesheet_reviews,
        "worker_submissions": worker_submissions,
        "worker_payment_holds": worker_payment_holds,
        "payroll": _payroll_summary(estate_id(), date.today().year),
        "payment_integrity": payment_integrity,
        "data_quality": operational_data_quality(estate_id()),
        "recovery_errors": [
            {**row, "kind": "integration", "recoverable": row["integration_name"] in (set(PROCESS_INTEGRATIONS.values()) | set(LEGACY_PROCESS_INTEGRATIONS))} for row in recovery_errors
        ] + [{**row, "kind": "intake", "recoverable": True} for row in failed_intake],
    })


@app.put("/api/v1/admin/people/{person_entity:path}/profile", dependencies=[Depends(authorize_admin)])
def update_person_profile(person_entity: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    person_entity = person_entity.strip()
    if not person_entity.startswith("person."):
        raise HTTPException(422, "Choose a Home Assistant Person")
    current = people_profiles()
    existing = current.get(person_entity, {}) if isinstance(current.get(person_entity), dict) else {}
    ha_person = next((item for item in home_assistant_people() if item.get("entity_id") == person_entity), {})
    ha_attributes = ha_person.get("attributes") or {}
    access_level = str(payload.get("access_level") or "viewer").strip().casefold()
    if access_level not in {"admin", "operations", "hospitality", "register", "worker", "viewer", "none"}:
        raise HTTPException(422, "Choose a valid Vineyard Operations access level")
    username = str(payload.get("username") or "").strip().casefold()
    if (ha_attributes.get("user_id") or existing.get("ha_user_id")) and existing.get("username"):
        username = str(existing["username"]).strip().casefold()
    if access_level not in {"viewer", "none"} and not username:
        raise HTTPException(422, "Enter the Home Assistant username for this access level")
    role = str(payload.get("role") or existing.get("role") or "Team member").strip()
    if role not in ESTATE_ROLES and role != str(existing.get("role") or "").strip():
        raise HTTPException(422, "Choose a standard estate role")
    if username:
        duplicate = next(
            (
                entity
                for entity, saved_profile in current.items()
                if entity != person_entity
                and isinstance(saved_profile, dict)
                and str(saved_profile.get("username") or "").strip().casefold() == username
            ),
            None,
        )
        if duplicate:
            raise HTTPException(409, "That Home Assistant username is already linked to another person")
    profile = {
        **existing,
        "name": str(ha_attributes.get("friendly_name") or payload.get("name") or existing.get("name") or "").strip(),
        "ha_user_id": ha_attributes.get("user_id") or existing.get("ha_user_id"),
        "role": role,
        "username": username,
        "access_level": access_level,
        "track_hourly_labor": bool(payload.get("track_hourly_labor")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": request.headers.get("X-Remote-User-Name") or "api",
    }
    current[person_entity] = profile
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'people_profiles',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(current, ensure_ascii=False, default=str)),
        )
        audit(cursor, "update", "person_profile", person_entity, profile, profile["updated_by"])
    return {"saved": True, "person_entity": person_entity, "profile": profile}


@app.put("/api/v1/admin/people/{person_entity:path}/whatsapp-ivr", dependencies=[Depends(authorize_admin)])
def update_person_whatsapp_ivr(person_entity: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Link and configure one person's field IVR without exposing message content."""
    return _save_person_whatsapp_ivr(person_entity, payload, request.headers.get("X-Remote-User-Name") or "api")


@app.put("/api/v1/admin/control", dependencies=[Depends(authorize_admin)])
def update_admin_control(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return json_ready(save_process_controls(payload, request.headers.get("X-Remote-User-Name") or "api"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(503, f"Schedule could not be saved: {str(error)[:300]}") from error


@app.get("/api/v1/admin/tv-config", dependencies=[Depends(authorize_admin)])
def get_tv_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    saved = _read_addon_options()
    values = {key: saved.get(key, getattr(settings, key)) for key in TV_CONFIG_FIELDS}
    return json_ready({
        "values": values,
        "available_cameras": home_assistant_manager_camera_catalog(),
        "display_url": "http://192.168.0.10:8101/",
        "saved_live": True,
    })


@app.put("/api/v1/admin/tv-config", dependencies=[Depends(authorize_admin)])
def update_tv_config(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        cleaned = _clean_tv_options(payload)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    merged = {**_read_addon_options(), **cleaned}
    _write_runtime_options({key: merged[key] for key in TV_CONFIG_FIELDS if key in merged})
    token = os.environ.get("SUPERVISOR_TOKEN")
    supervisor_synced = False
    if token:
        supervisor_request = urllib.request.Request(
            "http://supervisor/addons/self/options",
            data=json.dumps({"options": merged}).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(supervisor_request, timeout=20) as response:
                response.read()
            supervisor_synced = True
        except Exception:
            pass
    with transaction() as (_, cursor):
        audit(cursor, "update", "tv_display", "configuration", {"fields": sorted(cleaned)})
    return {
        "saved": True,
        "supervisor_synced": supervisor_synced,
        "values": {key: merged.get(key, getattr(get_settings(), key)) for key in TV_CONFIG_FIELDS},
    }


@app.post("/api/v1/admin/run/{code}", dependencies=[Depends(authorize_admin)])
async def run_admin_process(code: str) -> dict[str, Any]:
    try:
        return await run_named_process(code)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    except ProcessAlreadyRunningError as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(502, f"Process failed: {str(error)[:300]}") from error


@app.get("/api/v1/admin/camera-source-health", dependencies=[Depends(authorize_admin)])
def camera_source_health() -> dict[str, Any]:
    return json_ready(visual_rtsp_source_health())


@app.post("/api/v1/admin/recover/{kind}/{record_id}", dependencies=[Depends(authorize_admin)])
async def recover_admin_error(kind: str, record_id: str) -> dict[str, Any]:
    if kind == "intake":
        row = fetch_one("SELECT id FROM intake_items WHERE id=%s AND estate_id=%s AND review_status='failed'", (record_id, estate_id()))
        if not row:
            raise HTTPException(404, "Failed inbox item not found")
        try:
            return analyze_intake(record_id)
        except Exception as error:
            raise HTTPException(502, f"Inbox recovery failed: {str(error)[:300]}") from error
    if kind == "integration":
        row = fetch_one("SELECT integration_name FROM integration_events WHERE id=%s AND estate_id=%s AND status='failed'", (record_id, estate_id()))
        if not row:
            raise HTTPException(404, "Processing error not found")
        reverse = {name: code for code, name in PROCESS_INTEGRATIONS.items()}
        reverse.update(LEGACY_PROCESS_INTEGRATIONS)
        code = reverse.get(row["integration_name"])
        if not code:
            raise HTTPException(422, "This historical error has no safe automatic retry; use the complete recovery sweep")
        try:
            return await run_named_process(code)
        except Exception as error:
            raise HTTPException(502, f"Recovery failed: {str(error)[:300]}") from error
    raise HTTPException(404, "Unknown recovery item")


@app.post("/api/v1/admin/errors/{kind}/{record_id}/clear", dependencies=[Depends(authorize_admin)])
def clear_admin_error(kind: str, record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    if kind not in {"integration", "intake"}:
        raise HTTPException(404, "Unknown error item")
    if kind == "integration":
        row = fetch_one(
            "SELECT id,integration_name FROM integration_events WHERE id=%s AND estate_id=%s AND status='failed'",
            (record_id, estate_id()),
        )
    else:
        row = fetch_one(
            "SELECT id,title FROM intake_items WHERE id=%s AND estate_id=%s AND review_status='failed'",
            (record_id, estate_id()),
        )
    if not row:
        raise HTTPException(404, "Failed item not found")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    note = str(payload.get("note") or "Acknowledged in Operations Control").strip()[:500]
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO error_acknowledgements (estate_id,error_kind,record_id,acknowledged_by,note) VALUES (%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE acknowledged_at=CURRENT_TIMESTAMP(6),acknowledged_by=VALUES(acknowledged_by),note=VALUES(note)",
            (estate_id(), kind, record_id, actor, note),
        )
        if kind == "integration" and row.get("integration_name"):
            cursor.execute(
                "UPDATE sync_checkpoints SET last_error=NULL WHERE estate_id=%s AND integration_name=%s",
                (estate_id(), row["integration_name"]),
            )
        audit(cursor, "acknowledge", "processing_error", f"{kind}:{record_id}", {"note": note, "source": row.get("integration_name") or row.get("title")})
    return {"cleared": True, "kind": kind, "record_id": record_id, "audit_preserved": True}


@app.post("/api/v1/admin/errors/clear-shown", dependencies=[Depends(authorize_admin)])
def clear_shown_admin_errors(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    note = str(payload.get("note") or "Bulk acknowledged in Operations Control").strip()[:500]
    collation = "utf8mb4_unicode_ci"
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO error_acknowledgements (estate_id,error_kind,record_id,acknowledged_by,note) "
            "SELECT current_event.estate_id,'integration',CAST(current_event.id AS CHAR),%s,%s "
            "FROM integration_events current_event WHERE current_event.estate_id=%s AND current_event.status='failed' "
            "AND current_event.integration_name<>'whatsapp-channel' "
            "AND NOT EXISTS (SELECT 1 FROM integration_events newer_event WHERE newer_event.estate_id=current_event.estate_id "
            "AND newer_event.integration_name=current_event.integration_name AND newer_event.event_type=current_event.event_type "
            "AND (newer_event.occurred_at>current_event.occurred_at OR (newer_event.occurred_at=current_event.occurred_at AND newer_event.id>current_event.id))) "
            f"AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a WHERE a.estate_id COLLATE {collation}=current_event.estate_id COLLATE {collation} "
            f"AND a.error_kind='integration' AND a.record_id COLLATE {collation}=CAST(current_event.id AS CHAR) COLLATE {collation}) "
            "ON DUPLICATE KEY UPDATE acknowledged_at=CURRENT_TIMESTAMP(6),acknowledged_by=VALUES(acknowledged_by),note=VALUES(note)",
            (actor, note, estate_id()),
        )
        integration_count = int(cursor.rowcount or 0)
        cursor.execute(
            "INSERT INTO error_acknowledgements (estate_id,error_kind,record_id,acknowledged_by,note) "
            "SELECT i.estate_id,'intake',CAST(i.id AS CHAR),%s,%s FROM intake_items i "
            f"WHERE i.estate_id=%s AND i.review_status='failed' AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a "
            f"WHERE a.estate_id COLLATE {collation}=i.estate_id COLLATE {collation} AND a.error_kind='intake' "
            f"AND a.record_id COLLATE {collation}=CAST(i.id AS CHAR) COLLATE {collation}) "
            "ON DUPLICATE KEY UPDATE acknowledged_at=CURRENT_TIMESTAMP(6),acknowledged_by=VALUES(acknowledged_by),note=VALUES(note)",
            (actor, note, estate_id()),
        )
        intake_count = int(cursor.rowcount or 0)
        cursor.execute("UPDATE sync_checkpoints SET last_error=NULL WHERE estate_id=%s", (estate_id(),))
        audit(cursor, "acknowledge", "processing_error", "shown", {"integration_count": integration_count, "intake_count": intake_count, "note": note}, actor)
    resolve_condition_alert("system", "system:integration-failures")
    return {"cleared": integration_count + intake_count, "integration_errors": integration_count, "intake_errors": intake_count, "audit_preserved": True}


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
        saved = save_quick_entry(record_type, payload)
        if record_type in {"maturity_sample", "harvest_plan", "treatment"}:
            request_harvest_refresh(record_type, saved["id"], "New harvest-readiness evidence saved")
        return saved
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



def blend_program_payload(year: int, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    saved = fetch_one(
        "SELECT * FROM blend_program_settings WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    settings = {
        "blend_name": saved.get("blend_name") or "Nerello blend",
        "nerello_variety_name": saved.get("nerello_variety_name") or "Nerello Mascalese",
        "grenache_variety_name": saved.get("grenache_variety_name") or "Grenache",
        "grecanico_variety_name": saved.get("grecanico_variety_name") or "Grecanico",
        "grenache_pct": float(saved.get("grenache_pct") or 6.5),
        "crate_weight_kg": float(saved.get("crate_weight_kg") or 15),
        "expected_yield_l_per_kg": float(saved.get("expected_yield_l_per_kg") or 0.70),
        "tank_working_fill_pct": float(saved.get("tank_working_fill_pct") or 90),
        "updated_at": saved.get("updated_at"),
        "updated_by": saved.get("updated_by"),
    }
    if overrides:
        for key in ("grenache_pct", "crate_weight_kg", "expected_yield_l_per_kg", "tank_working_fill_pct"):
            if overrides.get(key) not in (None, ""):
                settings[key] = float(overrides[key])
    forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg FROM production_forecasts WHERE estate_id=%s AND vintage_year=%s AND scenario='base'",
        (estate_id(), year),
    )
    forecasts = adjust_production_forecasts(forecasts, year)
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    harvested = fetch_all(
        "SELECT v.name variety_name,COALESCE(SUM(h.weight_kg),0) grape_kg,COALESCE(SUM(h.crate_count),0) crates "
        "FROM harvest_lots h JOIN grape_varieties v ON v.id=h.variety_id WHERE h.estate_id=%s AND h.season_id=%s GROUP BY v.id,v.name",
        (estate_id(), season.get("id")),
    ) if season.get("id") else []

    def amount(rows: list[dict[str, Any]], intended: str, fallback: str = "") -> float:
        wanted = intended.casefold()
        match = next((row for row in rows if str(row.get("variety_name") or "").casefold() == wanted), None)
        if not match and fallback:
            match = next((row for row in rows if fallback in str(row.get("variety_name") or "").casefold()), None)
        return float((match or {}).get("adjusted_grape_kg", (match or {}).get("grape_kg")) or 0)

    forecast_inputs = {
        "nerello_kg": amount(forecasts, settings["nerello_variety_name"], "nerello"),
        "grenache_available_kg": amount(forecasts, settings["grenache_variety_name"], "grenache"),
        "grecanico_kg": amount(forecasts, settings["grecanico_variety_name"], "grecanico"),
    }
    if overrides:
        for key in forecast_inputs:
            if overrides.get(key) not in (None, ""):
                forecast_inputs[key] = float(overrides[key])
    live_inputs = {
        "nerello_kg": amount(harvested, settings["nerello_variety_name"], "nerello"),
        "grenache_available_kg": amount(harvested, settings["grenache_variety_name"], "grenache"),
        "grecanico_kg": amount(harvested, settings["grecanico_variety_name"], "grecanico"),
    }
    calculator_args = {
        "grenache_pct": settings["grenache_pct"],
        "crate_weight_kg": settings["crate_weight_kg"],
        "yield_l_per_kg": settings["expected_yield_l_per_kg"],
        "tank_working_fill_pct": settings["tank_working_fill_pct"],
    }
    planning = calculate_blend_program(**forecast_inputs, **calculator_args)
    live = calculate_blend_program(**live_inputs, **calculator_args)
    # The live picking target begins with Nerello, not merely because another
    # variety (for example the earlier Grecanico pick) has been recorded.
    live["harvest_started"] = live_inputs["nerello_kg"] > 0
    live["any_harvest_started"] = any(value > 0 for value in live_inputs.values())
    live["additional_grenache_crates_to_target"] = max(
        0,
        math.ceil((float(live["required_grenache_kg"]) - live_inputs["grenache_available_kg"]) / settings["crate_weight_kg"] - 1e-9),
    )
    tanks = fetch_all(
        "SELECT c.id,c.code,c.name,c.container_type,c.capacity_l,c.status,"
        "COALESCE((SELECT SUM(w.volume_l) FROM wine_lots w WHERE w.current_container_id=c.id),cp.manual_volume_l,0) current_volume_l "
        "FROM cellar_containers c LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.capacity_l DESC,c.code",
        (estate_id(),),
    )
    for result in (planning, live):
        for wine in result["wines"]:
            required_capacity = float(wine["gross_tank_capacity_l"])
            candidates = []
            for tank in tanks:
                available = max(float(tank.get("capacity_l") or 0) - float(tank.get("current_volume_l") or 0), 0)
                if available + 0.001 >= required_capacity:
                    candidates.append({"id": tank["id"], "code": tank["code"], "name": tank["name"], "container_type": tank.get("container_type"), "available_l": round(available, 1)})
            wine["candidate_tanks"] = candidates[:5]
    return {
        "year": year,
        "settings": settings,
        "planning": planning,
        "live": live,
        "forecast_source": "production_forecasts base scenario",
        "live_source": "recorded harvest lots",
        "guardrail": "Capacity planning only. The enologist confirms picking, blend composition, yield and final vessel assignments.",
    }


@app.put("/api/v1/agronomy/blend-program", dependencies=[Depends(authorize_write)])
def save_blend_program(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    year = int(payload.get("year") or date.today().year)
    try:
        grenache_pct = float(payload.get("grenache_pct") or 0)
        crate_weight_kg = float(payload.get("crate_weight_kg") or 0)
        expected_yield_l_per_kg = float(payload.get("expected_yield_l_per_kg") or 0)
        tank_working_fill_pct = float(payload.get("tank_working_fill_pct") or 0)
        validated = calculate_blend_program(
            0, 0, 0,
            grenache_pct,
            crate_weight_kg,
            expected_yield_l_per_kg,
            tank_working_fill_pct,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    actor = request.headers.get("X-Remote-User-Name") or "api"
    values = (validated["grenache_pct"], crate_weight_kg, expected_yield_l_per_kg, tank_working_fill_pct)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO blend_program_settings (id,estate_id,vintage_year,grenache_pct,crate_weight_kg,expected_yield_l_per_kg,tank_working_fill_pct,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE grenache_pct=VALUES(grenache_pct),crate_weight_kg=VALUES(crate_weight_kg),expected_yield_l_per_kg=VALUES(expected_yield_l_per_kg),tank_working_fill_pct=VALUES(tank_working_fill_pct),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), year, *values, actor),
        )
        audit(cursor, "update", "blend_program", str(year), {"grenache_pct": values[0], "crate_weight_kg": values[1], "yield_l_per_kg": values[2], "tank_working_fill_pct": values[3]}, actor)
    return {"saved": True, "blend_program": blend_program_payload(year)}


@app.post("/api/v1/agronomy/blend-calculator", dependencies=[Depends(authorize)])
def calculate_blend_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    year = int(payload.get("year") or date.today().year)
    try:
        return json_ready(blend_program_payload(year, payload))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/agronomy/dashboard", dependencies=[Depends(authorize)])
def agronomy_dashboard(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    settings = get_settings()
    season = season_for_year(year)
    maintenance = fetch_all(
        "SELECT m.*,c.code tank_code,c.name tank_name FROM cellar_maintenance_records m JOIN cellar_containers c ON c.id=m.container_id "
        "WHERE m.estate_id=%s ORDER BY m.maintenance_at DESC LIMIT 40", (estate_id(),),
    )
    reviews = fetch_all(
        "SELECT * FROM treatment_program_reviews WHERE estate_id=%s AND season_id=%s ORDER BY reviewed_at DESC LIMIT 20",
        (estate_id(), season),
    )
    configured = sorted(live_sensor_tank_keys(settings))
    wine_lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,w.volume_l,w.current_container_id FROM wine_lots w "
        "WHERE w.estate_id=%s AND w.season_id=%s ORDER BY w.code",
        (estate_id(), season),
    )
    harvest_lots = fetch_all(
        "SELECT h.id,h.harvested_at,h.weight_kg,h.field_weight_kg,h.winery_weight_kg,h.winery_weighed_at,h.winery_weight_notes,h.crate_count,h.destination,v.name variety_name,b.code block_code,"
        "(SELECT GROUP_CONCAT(DISTINCT vb.code ORDER BY vb.code SEPARATOR ', ') FROM harvest_lot_blocks hlb JOIN vineyard_blocks vb ON vb.id=hlb.block_id WHERE hlb.harvest_lot_id=h.id) block_summary,"
        "(SELECT GROUP_CONCAT(CONCAT(p.municipality,' · sheet ',p.cadastral_sheet,' · parcel ',p.parcel_number) ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number SEPARATOR '; ') "
        "FROM harvest_lot_parcels hp JOIN cadastral_parcels p ON p.id=hp.parcel_id WHERE hp.harvest_lot_id=h.id) parcel_summary "
        "FROM harvest_lots h JOIN grape_varieties v ON v.id=h.variety_id LEFT JOIN vineyard_blocks b ON b.id=h.block_id "
        "WHERE h.estate_id=%s AND h.season_id=%s ORDER BY h.harvested_at DESC",
        (estate_id(), season),
    )
    lot_trace = fetch_all(
        "SELECT tr.*,h.harvested_at,v.name variety_name,b.code block_code,w.code wine_lot_code,w.name wine_lot_name,c.code tank_code,c.name tank_name,"
        "(SELECT GROUP_CONCAT(CONCAT(p.municipality,' · sheet ',p.cadastral_sheet,' · parcel ',p.parcel_number) ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number SEPARATOR '; ') "
        "FROM harvest_lot_parcels hp JOIN cadastral_parcels p ON p.id=hp.parcel_id WHERE hp.harvest_lot_id=h.id) parcel_summary "
        "FROM cellar_lot_trace_records tr JOIN harvest_lots h ON h.id=tr.harvest_lot_id JOIN grape_varieties v ON v.id=h.variety_id "
        "LEFT JOIN vineyard_blocks b ON b.id=h.block_id JOIN wine_lots w ON w.id=tr.wine_lot_id JOIN cellar_containers c ON c.id=tr.container_id "
        "WHERE tr.estate_id=%s AND tr.season_id=%s ORDER BY tr.transferred_at DESC",
        (estate_id(), season),
    )
    content_values = sorted({
        str(row.get("value") or "").strip()
        for row in fetch_all(
            "SELECT name value FROM grape_varieties WHERE estate_id=%s "
            "UNION SELECT variety_summary value FROM wine_lots WHERE estate_id=%s AND season_id=%s",
            (estate_id(), estate_id(), season),
        )
        if str(row.get("value") or "").strip()
    }, key=str.casefold)
    damage = damage_assessment_dashboard(year)
    return json_ready({
        "year": year,
        "cellar": _live_cellar_dashboard(year, settings),
        "treatments": treatment_dashboard(year, "vineyard", 400.0),
        **damage,
        "maintenance": maintenance,
        "treatment_reviews": reviews,
        "wine_lots": wine_lots,
        "harvest_lots": harvest_lots,
        "lot_trace": lot_trace,
        "blend_program": blend_program_payload(year),
        "tank_labels": tank_label_rows(year),
        "retired_tank_labels": tank_label_rows(year, active=False),
        "label_kiosks": kiosk_rows(),
        "label_enrollments": enrollment_rows(),
        "provisioned_label_devices": provisioned_device_rows(),
        "retired_label_kiosks": kiosk_rows(active=False),
        "legal_label_options": {
            "wine_types": WINE_TYPES,
            "wine_colors": WINE_COLORS,
            "denomination_classes": DENOMINATION_CLASSES,
            "processing_phases": PROCESSING_PHASES,
            "legal_defaults": LEGAL_PROFILE_DEFAULTS,
            "port": 8102,
            "origin": cellar_label_origin(settings, required=False),
            "enrollment_enabled": bool(settings.cellar_label_enrollment_key.strip()),
            "ipad_dashboard_url": settings.cellar_ipad_dashboard_url,
        },
        "cellar_options": {"contents": content_values, "stages": CELLAR_STAGES, "wine_colors": WINE_COLORS},
        "sensor_configuration": {
            "location": "Home Assistant App Configuration",
            "option": "cellar_live_sensors / Tank Sensor mappings",
            "configured_tanks": configured,
            "note": "Home Assistant entities and protected Tank Sensor credentials/mappings are configured in App Configuration. Manual readings remain available as a fallback.",
        },
    })


@app.post("/api/v1/agronomy/treatment-program/review", dependencies=[Depends(authorize_write)])
def save_treatment_program_review(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("review_status") or "reviewed").casefold()
    if status not in {"reviewed", "changes_required", "approved"}:
        raise HTTPException(422, "Choose reviewed, changes required or approved")
    if status == "approved":
        require_discipline_approval(request, "agronomy")
    year = int(payload.get("year") or date.today().year)
    season = season_for_year(year)
    actor = request.headers.get("X-Remote-User-Name") or "api"
    review_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO treatment_program_reviews (id,estate_id,season_id,reviewed_at,review_status,reviewer,scope_text,notes,next_review_at) VALUES (%s,%s,%s,NOW(6),%s,%s,%s,%s,%s)",
            (review_id, estate_id(), season, status, actor, str(payload.get("scope_text") or "").strip() or None, str(payload.get("notes") or "").strip() or None, payload.get("next_review_at") or None),
        )
        audit(cursor, "review", "treatment_program", review_id, {"year": year, "status": status}, actor)
    return {"saved": True, "id": review_id}


@app.get("/api/v1/olives/dashboard", dependencies=[Depends(authorize)])
def olive_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=FIRST_ESTATE_VINTAGE)) -> dict[str, Any]:
    metrics = fetch_one(
        "SELECT SUM(olives_harvested_kg) olives_kg,SUM(oil_liters) oil_liters,SUM(labor_hours) labor_hours,"
        "AVG(yield_pct) avg_yield_pct,COUNT(*) record_count FROM olive_records WHERE estate_id=%s AND record_year=%s",
        (estate_id(), year),
    ) or {}
    def default_cost_model(model_year: int) -> dict[str, Any]:
        supplied_2024 = model_year == 2024
        return {
            "record_year": model_year,
            "press_rate_eur_per_kg": 0.20,
            "bottle_volume_ml": 500,
            "bottle_count": 220 if supplied_2024 else 0,
            "bottle_unit_cost_eur": 2.30,
            "supplier_net_eur": 751 if supplied_2024 else 0,
            "vat_rate_pct": 22,
            "supplier_includes_press_bottling": 1,
            "annual_labor_eur": 1000 if supplied_2024 else 0,
            "harvest_labor_eur": 540 if supplied_2024 else 0,
            "harvest_included_in_annual": 1,
            "harvest_rate_eur_per_tree": 7,
            "notes": "Owner-supplied 2024 cost assumptions; save to retain edits." if supplied_2024 else None,
        }
    default_model = default_cost_model(year)
    stored_model = fetch_one("SELECT * FROM olive_cost_models WHERE estate_id=%s AND record_year=%s", (estate_id(), year))
    effective_model = stored_model or (default_model if year == 2024 else None)
    model = stored_model or default_model
    analysis = _olive_cost_analysis(metrics, effective_model)
    history = fetch_all(
        "SELECT record_year,SUM(olives_harvested_kg) olives_kg,SUM(oil_liters) oil_liters,AVG(yield_pct) avg_yield_pct,SUM(labor_hours) labor_hours,COUNT(*) record_count "
        "FROM olive_records WHERE estate_id=%s AND record_year>=%s GROUP BY record_year ORDER BY record_year",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
    cost_models = {int(row["record_year"]): row for row in fetch_all("SELECT * FROM olive_cost_models WHERE estate_id=%s AND record_year>=%s ORDER BY record_year", (estate_id(), FIRST_ESTATE_VINTAGE))}
    history_enriched = []
    for row in history:
        row_year = int(row["record_year"])
        year_model = cost_models.get(row_year) or (default_cost_model(row_year) if row_year == 2024 else None)
        year_analysis = _olive_cost_analysis(row, year_model)
        history_enriched.append({**row, "year": row_year, "kg_per_liter": year_analysis.get("kg_per_liter"), "total_cost_eur": year_analysis.get("total_cost_eur"), "cost_per_liter_eur": year_analysis.get("cost_per_liter_eur"), "has_cost_model": year_model is not None})
    prediction_context = _olive_prediction_context(year)
    prediction_context.update(_olive_pref_context(year, prediction_context.get("harvest_forecast") or {}))
    return json_ready({
        "year": year,
        "metrics": metrics,
        "cost_model": model,
        "cost_analysis": analysis,
        "has_cost_model": effective_model is not None,
        "records": fetch_all("SELECT * FROM olive_records WHERE estate_id=%s AND record_year=%s ORDER BY COALESCE(record_date,mill_date) DESC,id DESC", (estate_id(), year)),
        "source_facts": historical_note_facts(year, "olives"),
        "history": history_enriched,
        **prediction_context,
    })


@app.put("/api/v1/olives/cost-model/{year}", dependencies=[Depends(authorize_write)])
def save_olive_cost_model(year: int, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    if year < 2000 or year > date.today().year + 5:
        raise HTTPException(422, "Choose a valid olive production year")
    numeric_fields = {
        "press_rate_eur_per_kg": 1000,
        "bottle_volume_ml": 10000,
        "bottle_count": 1000000,
        "bottle_unit_cost_eur": 1000,
        "supplier_net_eur": 1000000,
        "vat_rate_pct": 100,
        "annual_labor_eur": 1000000,
        "harvest_labor_eur": 1000000,
        "harvest_rate_eur_per_tree": 10000,
    }
    values: dict[str, float] = {}
    for field, maximum in numeric_fields.items():
        try:
            value = float(payload.get(field) or 0)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, f"Enter a valid value for {field.replace('_', ' ')}") from error
        if value < 0 or value > maximum:
            raise HTTPException(422, f"{field.replace('_', ' ')} is outside the allowed range")
        values[field] = value
    if values["bottle_volume_ml"] <= 0:
        raise HTTPException(422, "Bottle volume must be greater than zero")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    model_id = new_id()
    notes = str(payload.get("notes") or "").strip() or None
    included = 1 if payload.get("harvest_included_in_annual") else 0
    supplier_includes = 1 if payload.get("supplier_includes_press_bottling") else 0
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO olive_cost_models (id,estate_id,record_year,press_rate_eur_per_kg,bottle_volume_ml,bottle_count,bottle_unit_cost_eur,supplier_net_eur,vat_rate_pct,supplier_includes_press_bottling,annual_labor_eur,harvest_labor_eur,harvest_included_in_annual,harvest_rate_eur_per_tree,notes,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE press_rate_eur_per_kg=VALUES(press_rate_eur_per_kg),bottle_volume_ml=VALUES(bottle_volume_ml),bottle_count=VALUES(bottle_count),bottle_unit_cost_eur=VALUES(bottle_unit_cost_eur),supplier_net_eur=VALUES(supplier_net_eur),vat_rate_pct=VALUES(vat_rate_pct),supplier_includes_press_bottling=VALUES(supplier_includes_press_bottling),annual_labor_eur=VALUES(annual_labor_eur),harvest_labor_eur=VALUES(harvest_labor_eur),harvest_included_in_annual=VALUES(harvest_included_in_annual),harvest_rate_eur_per_tree=VALUES(harvest_rate_eur_per_tree),notes=VALUES(notes),updated_by=VALUES(updated_by)",
            (model_id, estate_id(), year, values["press_rate_eur_per_kg"], int(values["bottle_volume_ml"]), values["bottle_count"], values["bottle_unit_cost_eur"], values["supplier_net_eur"], values["vat_rate_pct"], supplier_includes, values["annual_labor_eur"], values["harvest_labor_eur"], included, values["harvest_rate_eur_per_tree"], notes, actor),
        )
        audit(cursor, "update", "olive_cost_model", str(year), {**values, "supplier_includes_press_bottling": bool(supplier_includes), "harvest_included_in_annual": bool(included), "notes": notes}, actor)
    return olive_dashboard(year)


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
        "(SELECT SUM(h.weight_kg/NULLIF((SELECT COUNT(*) FROM harvest_lot_blocks hlbc WHERE hlbc.harvest_lot_id=h.id),0)) FROM harvest_lot_blocks hlb JOIN harvest_lots h ON h.id=hlb.harvest_lot_id WHERE hlb.block_id=b.id AND h.season_id=%s) harvested_kg "
        "FROM vineyard_blocks b LEFT JOIN block_varieties bv ON bv.block_id=b.id LEFT JOIN grape_varieties v ON v.id=bv.variety_id "
        "WHERE b.estate_id=%s AND b.active=1 GROUP BY b.id,b.code,b.name,b.area_ha,b.vine_count,b.planted_year,b.training_system,b.soil_type,b.elevation_m,b.aspect,b.irrigation_available ORDER BY b.code",
        (season_id, season_id, season_id, estate_id()),
    ))


@app.get("/api/v1/predictions/sources", dependencies=[Depends(authorize)])
def prediction_sources_status() -> dict[str, Any]:
    return json_ready({
        "credential_policy": "free_without_credentials_only",
        "authoritative_store": "MariaDB",
        "sources": prediction_source_context(),
        "guardrails": {
            "open_meteo_ensemble": "Near-term uncertainty only; maximum automatic movement is one day.",
            "sias_validation": "Independent validation only; never replaces the on-site station.",
            "sentinel_2_vegetation": "Block trend evidence only; exact polygons require explicit public-processing opt-in.",
            "ecmwf_seasonal": "Early planning only; never selects an exact harvest date.",
        },
    })


@app.get("/api/v1/vineyard/atlas", dependencies=[Depends(authorize)])
def vineyard_atlas() -> dict[str, Any]:
    return json_ready({
        "estate": fetch_one("SELECT name,latitude,longitude,total_area_ha FROM estates WHERE id=%s", (estate_id(),)) or {},
        "parcels": fetch_all(
            "SELECT id,municipality,cadastral_sheet,parcel_number,tenure,tenure_start,tenure_end,cadastral_area_ha,conducted_area_ha,buildings_m2,official_vineyard_area_ha,center_latitude,center_longitude,geometry_geojson,map_url,notes "
            "FROM cadastral_parcels WHERE estate_id=%s ORDER BY municipality,cadastral_sheet,parcel_number",
            (estate_id(),),
        ),
        "blocks": fetch_all(
            "SELECT id,code,name,area_ha,geometry_geojson FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code",
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


@app.put("/api/v1/vineyard/atlas/parcels/{parcel_id}/map", dependencies=[Depends(authorize_write)])
def update_parcel_map(parcel_id: str, payload: ParcelMapUpdate) -> dict[str, Any]:
    map_url = (payload.map_url or "").strip() or None
    if map_url and not map_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="Map link must start with http:// or https://")
    geometry = payload.geometry_geojson
    if geometry and geometry.get("type") not in {"Point", "Polygon", "MultiPolygon"}:
        raise HTTPException(status_code=422, detail="Boundary must be Point, Polygon or MultiPolygon GeoJSON")
    with transaction() as (_, cursor):
        cursor.execute("SELECT id FROM cadastral_parcels WHERE id=%s AND estate_id=%s", (parcel_id, estate_id()))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Parcel not found")
        cursor.execute(
            "UPDATE cadastral_parcels SET center_latitude=%s,center_longitude=%s,geometry_geojson=%s,map_url=%s WHERE id=%s AND estate_id=%s",
            (payload.center_latitude, payload.center_longitude, json.dumps(geometry) if geometry else None, map_url, parcel_id, estate_id()),
        )
        audit(cursor, "update", "cadastral_parcel_map", parcel_id, {"mapped": bool(geometry or (payload.center_latitude is not None and payload.center_longitude is not None)), "map_url": bool(map_url)})
    return {"updated": True}


@app.get("/api/v1/issues", dependencies=[Depends(authorize)])
def issues_and_decisions(year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    year_start, year_end = date(year, 1, 1), date(year, 12, 31)
    return json_ready(fetch_all(
        "SELECT * FROM issues_decisions WHERE estate_id=%s AND ((status IN ('open','monitoring') AND opened_date<=%s) "
        "OR (status IN ('resolved','deferred') AND (closed_date BETWEEN %s AND %s OR (closed_date IS NULL AND opened_date BETWEEN %s AND %s)))) "
        "ORDER BY FIELD(status,'open','monitoring','deferred','resolved'),FIELD(priority,'critical','high','medium','low'),due_date IS NULL,due_date",
        (estate_id(), year_end, year_start, year_end, year_start, year_end),
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
    if values.get("status") in {"resolved", "deferred"} and not values.get("closed_date"):
        values["closed_date"] = date.today()
    elif values.get("status") in {"open", "monitoring"}:
        values["closed_date"] = None
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
    # Database planning records; not a learned forecast model.
    grapes = grape_dashboard(year)
    blend_program = blend_program_payload(year)
    conversion, forecast_evidence = historical_forecast_evidence(year, grapes["vintages"])
    production_forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg,crates_15kg,source,notes,updated_at FROM production_forecasts WHERE estate_id=%s AND scenario='base' AND vintage_year BETWEEN %s AND %s ORDER BY vintage_year,variety_name",
        (estate_id(), year, year + 5),
    )
    return json_ready(build_operational_projections(
        year, grapes, blend_program, conversion, forecast_evidence, production_forecasts,
    ))


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


@app.post("/api/v1/finance/cash", status_code=201, dependencies=[Depends(authorize_finance)])
def create_cash_transaction(payload: CashTransactionCreate) -> dict[str, str]:
    raise HTTPException(405, "Finance is read-only here; pull authoritative records from Fatture in Cloud")


def finance_dashboard_payload(year: int) -> dict[str, Any]:
    return _finance_dashboard_payload(year, lambda selected_year: _payroll_summary(estate_id(), selected_year))


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
    return _home_assistant_finance_summary(finance_dashboard_payload(year), year)


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
def create_task(payload: TaskCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO tasks (id,estate_id,season_id,block_id,title,category,status,priority,due_date,estimated_hours,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["block_id"], values["title"], values["category"], values["status"], values["priority"], values["due_date"], values["estimated_hours"], values["notes"]))
        audit(cursor, "create", "task", record_id, values)
    try:
        google_sync = publish_task_to_google(record_id)
    except Exception as error:
        google_sync = {"published": False, "reason": str(error)[:300]}
    return {"id": record_id, "google_sync": google_sync}


@app.patch("/api/v1/tasks/{task_id}/status", dependencies=[Depends(authorize_write)])
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> dict[str, Any]:
    completed_at = datetime.now() if payload.status == "done" else None
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE tasks SET status=%s,completed_at=%s WHERE id=%s AND estate_id=%s", (payload.status, completed_at, task_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Task not found")
        audit(cursor, "status", "task", task_id, payload.model_dump())
    try:
        google_sync = publish_task_to_google(task_id)
    except Exception as error:
        google_sync = {"published": False, "reason": str(error)[:300]}
    return {"ok": True, "google_sync": google_sync}


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


@app.get("/api/v1/labs/analytes", dependencies=[Depends(authorize)])
def lab_analytes() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT analyte_code,MAX(analyte_name) analyte_name,MAX(unit) unit,COUNT(*) result_count,MIN(numeric_value) minimum,MAX(numeric_value) maximum FROM lab_results GROUP BY analyte_code ORDER BY analyte_name"))


@app.get("/api/v1/labs/comparison", dependencies=[Depends(authorize)])
def lab_comparison(analyte_code: str, from_year: int = 2023, to_year: int = Query(default_factory=lambda: date.today().year)) -> list[dict[str, Any]]:
    from_year = max(FIRST_ESTATE_VINTAGE, from_year)
    return json_ready(fetch_all(
        "SELECT * FROM v_lab_comparison WHERE estate_id=%s AND analyte_code=%s AND vintage_year BETWEEN %s AND %s ORDER BY lab_date,sample_name",
        (estate_id(), analyte_code, from_year, to_year),
    ))


@app.get("/api/v1/labs/trends", dependencies=[Depends(authorize)])
def lab_trends(from_year: int = FIRST_ESTATE_VINTAGE, to_year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return _lab_trends(max(FIRST_ESTATE_VINTAGE, from_year), to_year)


@app.get("/api/v1/labs/decision-board", dependencies=[Depends(authorize)])
def lab_decision_board(year: int = Query(default_factory=lambda: date.today().year), limit: int = 100) -> dict[str, Any]:
    return _lab_decision_board(year, limit)


@app.get("/api/v1/labs/vintage-outlook", dependencies=[Depends(authorize)])
def lab_vintage_outlook(year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    return _lab_vintage_outlook(year)


@app.get("/api/v1/labs/history", dependencies=[Depends(authorize)])
def lab_history(from_year: int = FIRST_ESTATE_VINTAGE, to_year: int = Query(default_factory=lambda: date.today().year), search: str = "") -> list[dict[str, Any]]:
    return _lab_history(max(FIRST_ESTATE_VINTAGE, from_year), to_year, search)


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
    sample = fetch_one("SELECT sample_type FROM lab_samples WHERE id=%s", (before["sample_id"],)) or {}
    if sample.get("sample_type") == "grape":
        request_harvest_refresh("lab_result", result_id, "Grape laboratory result corrected")
    try:
        lab_learning = refresh_lab_learning(before["sample_id"])
    except Exception as error:
        lab_learning = {"model_status": "refresh_failed", "error": str(error)[:300]}
    return {"saved": True, "result_id": result_id, "prediction_refresh": "queued" if sample.get("sample_type") == "grape" else "not_applicable", "lab_learning": lab_learning}


@app.post("/api/v1/labs/{sample_id}/review", dependencies=[Depends(authorize_write)])
def save_lab_review(sample_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed = {"review_status","interpretation","decision_action","decision_type","owner_text","next_check_at","enologist_approval_required","approved_by","approved_at","evidence_reference_id","notes"}
    unknown = set(payload)-allowed
    if unknown:
        raise HTTPException(422,"Unsupported review fields: "+", ".join(sorted(unknown)))
    is_approval = bool(payload.get("approved_at") or payload.get("approved_by")) or (
        payload.get("review_status") == "closed" and not payload.get("enologist_approval_required", True)
    )
    if is_approval:
        require_discipline_approval(request, "enology")
    sample = fetch_one("SELECT id FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise HTTPException(404,"Lab sample not found")
    review_id = new_id()
    values = {key: payload.get(key) for key in allowed}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_reviews (id,estate_id,sample_id,review_status,interpretation,decision_action,decision_type,owner_text,next_check_at,enologist_approval_required,approved_by,approved_at,evidence_reference_id,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE review_status=VALUES(review_status),interpretation=VALUES(interpretation),decision_action=VALUES(decision_action),decision_type=VALUES(decision_type),owner_text=VALUES(owner_text),next_check_at=VALUES(next_check_at),enologist_approval_required=VALUES(enologist_approval_required),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),evidence_reference_id=VALUES(evidence_reference_id),notes=VALUES(notes)", (review_id,estate_id(),sample_id,values.get("review_status") or "reviewing",values.get("interpretation"),values.get("decision_action"),values.get("decision_type"),values.get("owner_text"),values.get("next_check_at"),1 if values.get("enologist_approval_required",True) else 0,values.get("approved_by"),values.get("approved_at"),values.get("evidence_reference_id"),values.get("notes")))
        if is_approval:
            cursor.execute(
                "UPDATE lab_samples SET needs_review=0,review_notes=CONCAT('Enologist approved by ',%s,' on ',%s) WHERE id=%s AND estate_id=%s",
                (values.get("approved_by") or "Enologist", values.get("approved_at"), sample_id, estate_id()),
            )
        audit(cursor,"review","lab_sample",sample_id,payload)
    sample_type = (fetch_one("SELECT sample_type FROM lab_samples WHERE id=%s", (sample_id,)) or {}).get("sample_type")
    if sample_type == "grape":
        request_harvest_refresh("lab_review", sample_id, "Grape laboratory review updated")
    try:
        lab_learning = refresh_lab_learning(sample_id)
    except Exception as error:
        lab_learning = {"model_status": "refresh_failed", "error": str(error)[:300]}
    return {"saved":True,"sample_id":sample_id,"prediction_refresh":"queued" if sample_type == "grape" else "not_applicable","lab_learning":lab_learning}


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


@app.get("/api/v1/treatments", dependencies=[Depends(authorize)])
def treatment_history(year: int | None = None) -> list[dict[str, Any]]:
    if year:
        return json_ready(fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s AND YEAR(application_date)=%s ORDER BY application_date DESC", (estate_id(), year)))
    return json_ready(fetch_all("SELECT * FROM v_treatment_history WHERE estate_id=%s ORDER BY application_date DESC LIMIT 500", (estate_id(),)))


@app.patch("/api/v1/treatments/{treatment_id}/complete", dependencies=[Depends(authorize_write)])
def complete_treatment(treatment_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    unknown = set(payload) - {"application_date", "notes"}
    if unknown:
        raise HTTPException(422, "Unsupported fields: " + ", ".join(sorted(unknown)))
    raw_date = str(payload.get("application_date") or "").strip()
    try:
        completed_on = date.fromisoformat(raw_date[:10])
    except ValueError as exc:
        raise HTTPException(422, "Enter the actual treatment completion date") from exc
    if completed_on > date.today():
        raise HTTPException(422, "A completed treatment cannot have a future date")
    completion_note = str(payload.get("notes") or "").strip()
    if len(completion_note) > 4000:
        raise HTTPException(422, "Completion notes must be 4,000 characters or fewer")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    completed_task_ids: list[str] = []
    inventory_sync: dict[str, Any] = {"posted": [], "unresolved": [], "complete": True}
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT id,application_date,planned_application_date,purpose,status,notes FROM spray_applications "
            "WHERE id=%s AND estate_id=%s FOR UPDATE",
            (treatment_id, estate_id()),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Treatment not found")
        status = str(row.get("status") or "").casefold()
        if status in {"completed", "applied"}:
            raise HTTPException(409, "This treatment is already complete")
        if status in {"cancelled", "canceled", "rejected", "void"}:
            raise HTTPException(409, "A cancelled treatment cannot be marked complete")
        notes = str(row.get("notes") or "").strip()
        if completion_note:
            completion_text = f"Completion note ({completed_on.isoformat()}): {completion_note}"
            notes = f"{notes}\n\n{completion_text}" if notes else completion_text
        cursor.execute(
            "UPDATE spray_applications SET planned_application_date=COALESCE(planned_application_date,DATE(application_date)),"
            "application_date=%s,status='completed',notes=%s WHERE id=%s AND estate_id=%s",
            (completed_on, notes or None, treatment_id, estate_id()),
        )
        if cursor.rowcount != 1:
            raise HTTPException(500, "Treatment completion was not persisted")
        inventory_sync = sync_treatment_inventory_use(cursor, treatment_id)
        planned_on = row.get("planned_application_date") or row.get("application_date")
        if isinstance(planned_on, datetime):
            planned_on = planned_on.date()
        elif planned_on and not isinstance(planned_on, date):
            planned_on = date.fromisoformat(str(planned_on)[:10])
        treatment_task_title = f"Treatment plan · {row.get('purpose') or ''}".strip()
        cursor.execute(
            "SELECT id,title FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
            "AND category IN ('treatment','treatments','treatment_review','spray','spray_application') "
            "AND LOWER(TRIM(title))=LOWER(TRIM(%s)) AND (due_date=%s OR due_date IS NULL) FOR UPDATE",
            (estate_id(), treatment_task_title, planned_on),
        )
        linked_tasks = list(cursor.fetchall())
        for task in linked_tasks:
            cursor.execute(
                "UPDATE tasks SET status='done',completed_at=COALESCE(completed_at,NOW(6)) WHERE id=%s AND estate_id=%s",
                (task["id"], estate_id()),
            )
            audit(
                cursor,
                "reconcile_completed_treatment",
                "task",
                task["id"],
                {"title": task.get("title"), "status": "done", "treatment_id": treatment_id},
                actor,
            )
            completed_task_ids.append(str(task["id"]))
        audit(
            cursor,
            "complete",
            "treatment",
            treatment_id,
            {
                "purpose": row.get("purpose"),
                "status": "completed",
                "application_date": completed_on,
                "completion_notes": completion_note or None,
                "previous_status": row.get("status"),
                "planned_application_date": row.get("planned_application_date") or row.get("application_date"),
                "inventory_sync": inventory_sync,
            },
            actor,
        )
    saved = fetch_one("SELECT * FROM v_treatment_history WHERE id=%s AND estate_id=%s", (treatment_id, estate_id()))
    if not saved or str(saved.get("status") or "").casefold() != "completed":
        raise HTTPException(500, "Treatment completion could not be verified after saving")
    google_sync = []
    for task_id in completed_task_ids:
        try:
            google_sync.append(publish_task_to_google(task_id))
        except Exception as error:
            google_sync.append({"published": False, "task_id": task_id, "reason": str(error)[:300]})
    try:
        model_learning = refresh_treatment_weather_learning(treatment_id)
    except Exception as error:
        model_learning = {"updated": 0, "status": "retry_required", "reason": str(error)[:300]}
    return json_ready({"saved": True, "treatment": saved, "inventory_sync": inventory_sync, "completed_task_ids": completed_task_ids, "google_sync": google_sync, "model_learning": model_learning})


@app.get("/api/v1/treatments/dashboard", dependencies=[Depends(authorize)])
def treatment_dashboard(
    year: int = Query(default_factory=lambda: date.today().year),
    crop_scope: str = Query("vineyard"),
    planning_water_l: float | None = Query(None, ge=1, le=5000),
    equipment: str | None = Query(None, max_length=190),
) -> dict[str, Any]:
    crop_scope = str(crop_scope or "vineyard").casefold()
    if crop_scope not in {"vineyard", "olives"}:
        raise HTTPException(422, "Choose vineyard or olives")
    settings = get_settings()
    try:
        configured_water = float(runtime_option("treatment_planning_water_l", settings.treatment_planning_water_l))
    except (TypeError, ValueError):
        configured_water = settings.treatment_planning_water_l
    planning_water_l = min(5000.0, max(1.0, planning_water_l if planning_water_l is not None else configured_water))
    equipment = str(equipment or runtime_option("treatment_default_sprayer", settings.treatment_default_sprayer) or "").strip() or None
    rows = fetch_all(
        "SELECT * FROM v_treatment_history WHERE estate_id=%s AND crop_scope=%s AND YEAR(application_date)=%s ORDER BY application_date DESC",
        (estate_id(), crop_scope, year),
    )
    current_plans = fetch_all(
        "SELECT * FROM v_treatment_history WHERE estate_id=%s AND crop_scope=%s AND status='planned' ORDER BY COALESCE(planned_application_date,DATE(application_date)),application_date",
        (estate_id(), crop_scope),
    )
    crop_pressure_codes = set(pressure_codes_for_crop(crop_scope))
    pressure = [row for row in fetch_all(
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2') ORDER BY risk_score DESC",
        (estate_id(), estate_id()),
    ) if row.get("disease_code") in crop_pressure_codes]
    pressure_months = [row for row in fetch_all(
        "SELECT disease_code,MAX(disease_name) disease_name,YEAR(assessment_date) assessment_year,MONTH(assessment_date) month_number,"
        "AVG(risk_score) average_score,MAX(risk_score) peak_score,COUNT(*) assessment_count "
        "FROM disease_pressure_assessments WHERE estate_id=%s AND YEAR(assessment_date)>=%s AND model_version<>'evidence-screen-v2' GROUP BY disease_code,YEAR(assessment_date),MONTH(assessment_date) "
        "ORDER BY disease_code,assessment_year,month_number",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    ) if row.get("disease_code") in crop_pressure_codes]
    pressure_yoy: list[dict[str, Any]] = []
    for disease_code in dict.fromkeys(row.get("disease_code") for row in pressure_months):
        disease_rows = [row for row in pressure_months if row.get("disease_code") == disease_code]
        latest = next((row for row in pressure if row.get("disease_code") == disease_code), {})
        yearly = []
        for assessment_year in dict.fromkeys(int(row["assessment_year"]) for row in disease_rows):
            year_rows = [row for row in disease_rows if int(row["assessment_year"]) == assessment_year]
            yearly.append({
                "year": assessment_year,
                "average": [next((row.get("average_score") for row in year_rows if int(row["month_number"]) == month), None) for month in range(1, 13)],
                "peak": [next((row.get("peak_score") for row in year_rows if int(row["month_number"]) == month), None) for month in range(1, 13)],
                "checks": sum(int(row.get("assessment_count") or 0) for row in year_rows),
            })
        pressure_yoy.append({
            "disease_code": disease_code,
            "disease_name": disease_rows[0].get("disease_name") if disease_rows else disease_code,
            "years": yearly,
            "current_score": latest.get("risk_score"),
            "current_level": latest.get("risk_level"),
            "evidence_summary": latest.get("evidence_summary"),
            "suggested_action": latest.get("suggested_action"),
            "model_version": latest.get("model_version"),
            "prediction_method": "Monthly average and peak of the evidence-based disease/stress screening scores recorded by Vineyard Operations. Missing months remain blank; no values are invented.",
        })
    monthly = []
    for month in range(1, 13):
        matching = [row for row in rows if _treatment_date(row).month == month]
        active_matching = [row for row in matching if str(row.get("status") or "").casefold() not in {"cancelled", "canceled", "rejected", "void"}]
        monthly.append({
            "month": month,
            "total": len(active_matching),
            "completed": sum(row.get("status") == "completed" for row in active_matching),
            "planned": sum(row.get("status") == "planned" for row in active_matching),
        })
    actions = _treatment_actions(year)
    prediction = predict_next_treatment(current_plans, pressure, crop_scope=crop_scope)
    product_guidance = _treatment_product_guidance(crop_scope, prediction, planning_water_l=planning_water_l, equipment_selector=equipment)
    olive_harvest = None
    if crop_scope == "olives":
        olive_harvest = (_olive_prediction_context(year).get("harvest_forecast") or {}).get("estimated_date")
    safety_audit = _existing_treatment_safety_audits(rows, year, crop_scope=crop_scope, harvest_date=olive_harvest)
    for row in rows:
        row["safety_audit"] = (safety_audit.get("rows") or {}).get(str(row.get("id") or ""))
    _attach_treatment_costs(rows)
    latest_hail = _latest_treatment_hail_followup(year, crop_scope)
    hail_needs_followup = bool(latest_hail) and str(latest_hail.get("trend") or "").casefold() != "resolved"
    review_target = "hail_wound_followup" if hail_needs_followup else prediction.get("target_code")
    review_guidance = _treatment_field_review_guidance(review_target, event_type="hail" if hail_needs_followup else None, crop_scope=crop_scope)
    inactive_statuses = {"cancelled", "canceled", "rejected", "void"}
    active_rows = [row for row in rows if str(row.get("status") or "").casefold() not in inactive_statuses]
    completed_rows = [row for row in active_rows if str(row.get("status") or "").casefold() in {"completed", "applied"}]
    return json_ready({
        "year": year,
        "crop_scope": crop_scope,
        "summary": {
            "total": len(rows),
            "active": len(active_rows),
            "inactive": len(rows) - len(active_rows),
            "planned": sum(row.get("status") == "planned" for row in active_rows),
            "completed": len(completed_rows),
            "completion_needs_verification": sum(not bool(row.get("actual_details_confirmed")) for row in completed_rows),
            "approved": sum(bool(row.get("agronomist_approved")) for row in active_rows),
            "missing_actual_details": sum(not bool(row.get("actual_details_confirmed")) for row in completed_rows),
            "safety_verified": (safety_audit.get("summary") or {}).get("verified", 0),
            "safety_attention": (safety_audit.get("summary") or {}).get("attention", 0),
            "safety_blocked": (safety_audit.get("summary") or {}).get("blocked", 0),
        },
        "prediction": prediction,
        "product_guidance": product_guidance,
        "inventory_readiness": _treatment_inventory_readiness(product_guidance),
        "field_review_guidance": review_guidance,
        "latest_hail_followup": latest_hail,
        "scenario_options": _treatment_scenario_options(),
        "pressure": pressure,
        "pressure_yoy": pressure_yoy,
        "monthly": monthly,
        "treatments": rows,
        "record_evidence_gaps": _treatment_record_evidence_gaps(rows, crop_scope),
        "existing_treatment_safety_audit": safety_audit,
        "actions": actions,
        "scouting_followups": treatment_scouting_workflows(year, crop_scope),
        "prediction_as_of": date.today(),
        "guardrail": "Decision support only. Agronomist approval and safety checks remain required.",
    })


def _treatment_date(row: dict[str, Any]) -> date:
    value = row.get("application_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@app.get("/api/v1/system/status", dependencies=[Depends(authorize)])
def system_status() -> dict[str, Any]:
    return json_ready(system_status_payload())



@app.get("/api/v1/etna", dependencies=[Depends(authorize)])
def mount_etna_status(refresh: bool = False) -> dict[str, Any]:
    return etna_status(refresh=refresh)



@app.get("/api/v1/social", dependencies=[Depends(authorize_admin)])
def social_center(refresh: bool = Query(False)) -> dict[str, Any]:
    return social_dashboard(refresh=refresh)


@app.post("/api/v1/social/facebook", dependencies=[Depends(authorize_admin)])
def social_publish_facebook(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_facebook(str(payload.get("message") or ""), str(payload.get("link") or "") or None, str(payload.get("image_url") or "") or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Facebook publish failed: " + str(error)[:300]) from error


@app.post("/api/v1/social/instagram", dependencies=[Depends(authorize_admin)])
def social_publish_instagram(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_instagram(str(payload.get("image_url") or ""), str(payload.get("caption") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Instagram publish failed: " + str(error)[:300]) from error


@app.post("/api/v1/social/photo", dependencies=[Depends(authorize_admin)])
async def social_publish_photo(channel: str = Form(...), caption: str = Form(...), link: str = Form(""), file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Choose a photo smaller than 12 MB")
    try:
        return publish_social_photo(channel, data, file.filename or "social-photo.jpg", file.content_type or "application/octet-stream", caption, link or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Social photo publish failed: " + str(error)[:300]) from error



@app.get("/api/v1/records/{record_type}", dependencies=[Depends(authorize)])
def vineyard_records(
    record_type: str,
    request: Request,
    year: int | None = None,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    if record_type == "labs":
        return _lab_records(year)
    if record_type == "historical_costs" and not has_finance_access(request, x_api_key, settings):
        raise HTTPException(403, "Finance access is limited to the private finance group")
    queries = {
        "blocks": ("SELECT code,name,area_ha,planted_year,vine_count,training_system,soil_type FROM vineyard_blocks WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "varieties": ("SELECT name,color_hex,target_gdd,notes FROM grape_varieties WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "stock": ("SELECT name,sku,product_type,category_name,unit,track_inventory FROM products WHERE estate_id=%s AND active=1 ORDER BY category_name,name", (estate_id(),)),
        "cellar": ("SELECT code,name,stage,volume_l,current_container_id FROM wine_lots WHERE estate_id=%s ORDER BY code", (estate_id(),)),
        "reports": ("SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,first_pick_date,last_pick_date,harvest_date_precision,evidence_status,reconciliation_note,source_note_name FROM vintage_summaries WHERE estate_id=%s AND vintage_year>=%s ORDER BY vintage_year DESC,variety_name", (estate_id(), FIRST_ESTATE_VINTAGE)),
        "note_facts": ("SELECT fact_date,fact_year,date_precision,domain,subject,quantity_value,quantity_unit,details,evidence_status,source_note_name,conflict_note FROM historical_note_facts WHERE estate_id=%s AND fact_year>=%s ORDER BY COALESCE(fact_date,MAKEDATE(fact_year,1)) DESC,domain,subject", (estate_id(), FIRST_ESTATE_VINTAGE)),
        "attachments": ("SELECT id,entity_type,entity_id,original_filename,media_type,caption,uploaded_by,created_at FROM entity_attachments WHERE estate_id=%s ORDER BY created_at DESC LIMIT 250", (estate_id(),)),
        "labor": ("SELECT id,source_labor_id,work_date,shift_label,person_or_crew,role,work_category,work_performed,location_text,start_time,end_time,regular_hours,overtime_hours,hourly_rate_eur,labor_cost_eur,other_cost_eur,kg_handled,incident_near_miss,approved_by,payment_status,payroll_scope,entry_source,notes FROM labor_entries WHERE estate_id=%s ORDER BY work_date DESC,id DESC LIMIT 1000", (estate_id(),)),
        "historical_costs": ("SELECT record_date,record_year,period_start_year,period_end_year,date_precision,record_kind,classification,actor_name,description,amount_eur,labor_hours,payment_method,payment_status,included_in_totals,exclusion_reason,source_file_name,source_sheet,source_row_number FROM historical_cost_records WHERE estate_id=%s ORDER BY COALESCE(record_date,MAKEDATE(COALESCE(record_year,period_end_year),1)) DESC,source_file_name,source_sheet,source_row_number LIMIT 1000", (estate_id(),)),
    }
    if record_type not in queries:
        raise HTTPException(404, "Record type not found")
    sql, params = queries[record_type]
    return json_ready(fetch_all(sql, params))



app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
