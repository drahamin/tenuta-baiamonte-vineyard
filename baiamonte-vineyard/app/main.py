from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
import html
import json
import logging
import math
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pymysql.err import IntegrityError
from .access import (
    admin_usernames,
    authorize,
    authorize_admin,
    authorize_crew,
    authorize_finance,
    authorize_worker,
    authorize_write,
    dedicated_worker_usernames,
    finance_usernames,
    has_finance_access,
    match_home_assistant_person as _match_home_assistant_person,
    operations_usernames,
    people_profiles,
    profile_access_level,
    request_username,
    viewer_usernames,
    worker_accounts,
)
from .ai_usage import ai_cost_summary, ai_request_profile, ai_service_summary, save_ai_cost_settings, save_ai_request_profile
from .config import RUNTIME_OPTIONS_PATH, Settings, addon_version, get_settings, runtime_option
from .cache_headers import ReleaseAssetCacheMiddleware
from .cellar_demo import apply_live_sensor_readings, cellar_guardrails, demo_cellar, demo_enabled, evaluate_cellar_tanks, live_sensor_entity_ids, live_sensor_tank_keys
from .db import fetch_all, fetch_one, run_migrations, transaction
from .data_quality import operational_data_quality
from .domains.alerts import valid_alert_transition
from .domains.cellar import manual_tank_definitions
from .domains.damage_routes import damage_assessment_dashboard, router as damage_router
from .domains.finance import dashboard_payload as _finance_dashboard_payload, home_assistant_summary as _home_assistant_finance_summary
from .domains.fertilization_routes import router as fertilization_router
from .domains.harvest import calculate_blend_program, calculate_grenache_crate_target, latest_scouting_by_variety
from .domains.hospitality_routes import router as hospitality_router
from .domains.bottling_routes import router as bottling_router
from .domains.system_docs import hospitality_documentation
from .domains.laboratory import decision_board as _lab_decision_board, history as _lab_history, records as _lab_records, trends as _lab_trends
from .domains.laboratory_routes import router as laboratory_router
from .domains.messaging import (
    event_payload as _event_payload,
    whatsapp_delivery_status as _whatsapp_delivery_status,
)
from .domains.olives import calculate_cost_analysis as _olive_cost_analysis, harvest_preference_context as _olive_pref_context, prediction_context as _olive_prediction_context
from .domains.olive_routes import router as olive_router
from .domains.observation_routes import router as observation_router
from .domains.people_presence import resolve_timesheet_presence_entities
from .domains.payroll import (
    attach_labor_invoice_payments as _attach_labor_invoice_payments,
    consolidate_labor_people as _consolidate_labor_people,
    labor_payment_integrity as _labor_payment_integrity,
    labor_payment_summary as _labor_payment_summary,
    normalize_contractor_job_lines as _normalize_contractor_job_lines,
    record_labor_invoice_payment as _record_labor_invoice_payment,
    record_labor_payment_batch as _record_labor_payment_batch,
    worker_pay_due as _worker_pay_due,
    worker_payment_totals as _worker_payment_totals,
    worker_payment_batch_key as _worker_payment_batch_key,
)
from .domains.projections import build_operational_projections
from .domains.treatment_routes import router as treatment_router, treatment_actions as _treatment_actions
from .domains.treatments import attach_treatment_costs as _attach_treatment_costs, existing_treatment_safety_audits as _existing_treatment_safety_audits, field_review_guidance as _treatment_field_review_guidance, inventory_readiness as _treatment_inventory_readiness, latest_hail_followup as _latest_treatment_hail_followup, product_guidance as _treatment_product_guidance, treatment_record_evidence_gaps as _treatment_record_evidence_gaps, treatment_scenario_options as _treatment_scenario_options
from .domains.people_roles import ESTATE_ROLES, require_discipline_approval, session_payload, worker_profile as _worker_profile
from .domains.whatsapp_live import live_assisted_snapshot as _whatsapp_live_assisted_snapshot
from .domains.reference_chains import observation_chain_options
from .display_data import display_payload, system_status_payload, weather_context_payload
from .display_provisioning import cellar_label_origin, router as display_provisioning_router, url_qr
from .fattureincloud import pull_fattureincloud
from .ha_auth import home_assistant_token
from .historical_dashboard import FIRST_ESTATE_VINTAGE, all_vintage_rows, historical_cellar_summary, historical_forecast_evidence, historical_note_facts, merge_cellar_history, merge_historical_fact_overview, merge_historical_work_overview, merge_variety_history, merge_variety_summaries, reconciled_vintage_values, selected_dashboard_activities, selected_dashboard_history, selected_vintage_rows
from .inventory import sync_treatment_inventory_use, treatment_inventory_reconciliation
from .planning_sync import publish_task_to_google
from .observation_catalog import reference_catalog
from .etna import etna_status
from .intelligence import CISTERN_SNAPSHOT_PATH, ProcessAlreadyRunningError, alert_preference, analyze_intake, analyze_observation_attachment, ask_assistant, check_openai_service, clear_whatsapp_cache, control_home_assistant_manager_device, create_whatsapp_group, current_home_assistant_presence, download_whatsapp_media, gmail_mailbox_status, home_assistant_camera_snapshot, home_assistant_local_only_user_ids, home_assistant_manager_camera_catalog, home_assistant_manager_cameras, home_assistant_manager_devices, home_assistant_people, home_assistant_state_map, integration_loop, mark_power_monitor_stopped, poll_gmail_once, power_continuity_heartbeat, predict_next_treatment, quarantine_intake, refresh_disease_pressure, resolve_condition_alert, resolve_home_assistant_camera_request, resolve_home_assistant_control_request, run_full_refresh, run_named_process, save_intake_file, send_gmail_message, send_whatsapp_media, send_whatsapp_message, synthesize_whatsapp_voice, transcribe_whatsapp_voice, whatsapp_chatbot_reply, whatsapp_diagnostics, whatsapp_group_invite_link, whatsapp_native_groups, whatsapp_phone_number_id, whatsapp_phone_numbers, whatsapp_templates
from .mailbox import gmail_download, gmail_folders, gmail_message, gmail_message_action, gmail_messages
from .process_control import PROCESS_ORDER, process_controls, save_process_controls
from .process_runtime import processing_runtime_snapshot
from .prediction_evidence import maturity_evidence_sql
from .prediction_refresh import request_harvest_refresh
from .prediction_sources import prediction_source_context
from .production_impact import adjust_production_forecasts
from .whatsapp_registration import router as whatsapp_router
from .whatsapp_policy import approved_whatsapp_template
from .whatsapp_blend import (
    begin_calculator as _begin_whatsapp_blend_calculator,
    continue_calculator as _continue_whatsapp_blend_calculator_flow,
    parse_crate_count as _parse_crate_count,
    pending_action as _pending_whatsapp_action,
)
from .whatsapp_notices import (
    inbound_context as _whatsapp_inbound_context,
    mark_intervention_notice as _mark_whatsapp_intervention_notice,
    reconcile_answered_notices as _reconcile_answered_whatsapp_notices,
    resolve_answered_notice as _resolve_answered_whatsapp_notice,
)
from .whatsapp_intent import (
    capabilities as _whatsapp_capabilities,
    handoff_requested as _whatsapp_handoff_requested,
    is_submission as whatsapp_is_submission,
    language_preference as _whatsapp_language_preference,
    menu_route as _whatsapp_menu_route,
    prefers_italian as _whatsapp_is_italian,
)
from .whatsapp_observations import (
    begin_submission as _begin_whatsapp_submission,
    continue_submission as _continue_whatsapp_submission_flow,
    new_state as _whatsapp_observation_new,
    submission_menu as _whatsapp_submission_menu,
)
from .models import (
    ActivityCreate,
    BlockCreate,
    CashTransactionCreate,
    FinancialDocumentCreate,
    HarvestCreate,
    ParcelMapUpdate,
    TaskCreate,
    TaskStatusUpdate,
    VarietyCreate,
    WeatherObservationCreate,
)
from .quick_entry import save_quick_entry
from .service import audit, estate_id, json_ready, new_id, public_harvest_feed, season_for_year
from .social import publish_facebook, publish_instagram, publish_social_photo, social_dashboard
from .system_whatsapp import (
    system_whatsapp_accounts,
    system_whatsapp_add_contact,
    system_whatsapp_chat,
    system_whatsapp_backup,
    system_whatsapp_connect,
    system_whatsapp_decide_membership,
    system_whatsapp_disconnect,
    system_whatsapp_import_contacts,
    system_whatsapp_refresh_catalog,
    system_whatsapp_refresh_membership,
    system_whatsapp_rename_contact,
    system_whatsapp_relink,
    system_whatsapp_send,
    system_whatsapp_sync_history,
)
from .tank_labels import (
    CELLAR_STAGES,
    DENOMINATION_CLASSES,
    LEGAL_PROFILE_DEFAULTS,
    PROCESSING_PHASES,
    WINE_LOT_STAGES,
    WINE_COLORS,
    WINE_TYPES,
    approve_device_enrollment,
    create_kiosk,
    enrollment_rows,
    ensure_tank_label,
    kiosk_rows,
    provisioned_device_rows,
    reject_kiosk_enrollment,
    reprovision_device,
    retire_kiosk,
    save_legal_profile,
    tank_label_rows,
    update_kiosk,
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
_background_tasks: set[asyncio.Task[Any]] = set()


def _background_task_done(task: asyncio.Task[Any]) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        logger.exception("Background task failed")


def _start_background_task(awaitable: Any) -> asyncio.Task[Any]:
    task = asyncio.create_task(awaitable)
    _background_tasks.add(task)
    task.add_done_callback(_background_task_done)
    return task


async def _analyze_intake_background(record_id: str) -> None:
    await asyncio.to_thread(analyze_intake, record_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    try:
        _ensure_current_manual_tanks(get_settings())
    except Exception:
        logger.exception("Could not initialize configured cellar tanks")
    try:
        power_continuity_heartbeat()
    except Exception:
        logger.exception("Could not initialize power-continuity monitoring")
    try:
        _reconcile_answered_whatsapp_notices()
    except Exception:
        logger.exception("Could not reconcile answered WhatsApp notices during startup")
    tasks = [asyncio.create_task(integration_loop())]
    yield
    for task in tasks:
        task.cancel()
    for task in list(_background_tasks):
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.gather(*list(_background_tasks), return_exceptions=True)
    try:
        mark_power_monitor_stopped()
    except Exception:
        logger.exception("Could not record the planned power-monitor shutdown")


app = FastAPI(title="Baiamonte Vineyard API", version="1.5.17", lifespan=lifespan)
app.add_middleware(ReleaseAssetCacheMiddleware)
app.include_router(display_provisioning_router)
app.include_router(bottling_router)
app.include_router(damage_router)
app.include_router(fertilization_router)
app.include_router(hospitality_router)
app.include_router(laboratory_router)
app.include_router(olive_router)
app.include_router(observation_router)
app.include_router(treatment_router)
app.include_router(whatsapp_router)
static_dir = Path(__file__).resolve().parent / "static"
docs_dir = Path(__file__).resolve().parent.parent / "docs"
attachment_root = Path(os.getenv("ATTACHMENT_ROOT", "/data/baiamonte-attachments"))

WEATHER_MAP_STYLE = """
<style id="baiamonte-weather-map-mode">
html,body,.shell,main,#overview,.overview-grid,.map-panel,#tv-shell,#map,.map,.map-canvas,.map-container,.leaflet-container{width:100%!important;height:100%!important;min-width:100%!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important}
.shell,#tv-shell{display:block!important;grid-template-columns:none!important;grid-template-rows:none!important}
body{background:#071014!important}
aside,main>header,.hero,.summary-strip,.status-column,.lower-grid,.section-head,.map-panel>.panel-head,.map-panel>.map-footer{display:none!important}
main,.page#overview,.overview-grid,.map-panel,#map,.map,.map-canvas,.map-container,.leaflet-container{display:block!important;margin:0!important;grid-column:auto!important;grid-row:auto!important}
.map-panel{border:0!important;border-radius:0!important;box-shadow:none!important;background:#071014!important}
.radar-map,#map,.map,.map-canvas,.map-container,.leaflet-container{position:relative!important;width:100%!important;height:100vh!important;min-width:100%!important;min-height:100vh!important;border:0!important;border-radius:0!important}
.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,.plane,.plane-icon,.target-aircraft,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]{display:none!important;visibility:hidden!important}
.estate-map-marker,[class*="estate-marker"],[class*="home-marker"]{display:block!important;visibility:visible!important}
.map-controls,.weather-status,.weather-attribution,.altitude-legend,.map-attribution{z-index:40!important}
@media(prefers-reduced-motion:reduce){.sweep,.range-ring{animation:none!important}}
</style>
<script id="baiamonte-weather-map-cleanup">
(()=>{const hideAircraft=()=>document.querySelectorAll('.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,.plane,.plane-icon,.target-aircraft,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]').forEach(node=>{node.style.setProperty('display','none','important');node.setAttribute('aria-hidden','true')});document.addEventListener('DOMContentLoaded',()=>{hideAircraft();new MutationObserver(hideAircraft).observe(document.body,{childList:true,subtree:true})})})();
</script>
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
        **reference_catalog(),
    })


@app.get("/api/v1/session", dependencies=[Depends(authorize)])
def session_access(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    # Owns sync_ingress_identity(request), "approval_permissions": role_approval_permissions, "finance": normalized in finance_usernames(settings), "dedicated_worker": dedicated_worker, "hourly_worker": hourly_worker, and not dedicated_worker.
    return session_payload(request, settings)


def _worker_identity(request: Request, settings: Settings) -> tuple[str, str]:
    username = request_username(request)
    workers = worker_accounts(settings)
    name = workers.get(username)
    if not name and profile_access_level(username) == "worker":
        name = (request.headers.get("X-Remote-User-Display-Name") or username).strip()
    if not name:
        raise HTTPException(403, "Worker account is not assigned")
    return username, name


def _worker_labor_row(record_id: str, username: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s AND worker_username=%s",
        (record_id, estate_id(), username),
    )
    if not row:
        raise HTTPException(404, "Work record not found")
    return row


@app.get("/api/v1/worker-portal", dependencies=[Depends(authorize_worker)])
def worker_portal(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    active = fetch_one(
        "SELECT * FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_in_at IS NOT NULL AND clock_out_at IS NULL "
        "AND approval_status='draft' ORDER BY clock_in_at DESC LIMIT 1",
        (estate_id(), username),
    )
    pending = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND l.worker_username=%s AND l.approval_status IN ('draft','submitted','rejected') "
        "ORDER BY COALESCE(l.clock_in_at,CAST(l.work_date AS DATETIME)) DESC LIMIT 40",
        (estate_id(), username),
    )
    history = fetch_all(
        "SELECT l.*,(SELECT COUNT(*) FROM entity_attachments a WHERE a.estate_id=l.estate_id AND a.entity_type='labor' AND a.entity_id=l.id) photo_count "
        "FROM labor_entries l WHERE l.estate_id=%s AND (l.worker_username=%s OR (l.worker_username IS NULL AND LOWER(l.person_or_crew)=LOWER(%s))) "
        "AND l.approval_status='approved' ORDER BY l.work_date DESC,l.id DESC LIMIT 120",
        (estate_id(), username, worker_name),
    )
    totals = fetch_one(
        "SELECT COALESCE(SUM(regular_hours+overtime_hours),0) total_hours,COALESCE(SUM(COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0)),0) total_pay,"
        "COALESCE(SUM(CASE WHEN work_date=CURDATE() THEN regular_hours+overtime_hours ELSE 0 END),0) today_approved_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND MONTH(work_date)=MONTH(CURDATE()) THEN regular_hours+overtime_hours ELSE 0 END),0) month_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN regular_hours+overtime_hours ELSE 0 END),0) year_hours,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_pay,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND payment_status='paid' THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_paid_pay,"
        "COALESCE(SUM(CASE WHEN YEAR(work_date)=YEAR(CURDATE()) AND payment_status='unpaid' THEN COALESCE(labor_cost_eur,0)+COALESCE(other_cost_eur,0) ELSE 0 END),0) year_due_pay,"
        "COUNT(DISTINCT CASE WHEN YEAR(work_date)=YEAR(CURDATE()) THEN work_date END) year_days "
        "FROM labor_entries WHERE estate_id=%s AND (worker_username=%s OR (worker_username IS NULL AND LOWER(person_or_crew)=LOWER(%s))) AND approval_status='approved'",
        (estate_id(), username, worker_name),
    ) or {}
    queue_totals = fetch_one(
        "SELECT COALESCE(SUM(CASE WHEN work_date=CURDATE() AND clock_out_at IS NOT NULL THEN regular_hours+overtime_hours ELSE 0 END),0) today_submitted_hours,"
        "COALESCE(SUM(CASE WHEN approval_status IN ('submitted','rejected') THEN regular_hours+overtime_hours ELSE 0 END),0) pending_hours,"
        "COALESCE(SUM(CASE WHEN approval_status IN ('submitted','rejected') THEN expense_amount_eur ELSE 0 END),0) pending_charges_eur,"
        "SUM(approval_status IN ('submitted','rejected')) pending_entries "
        "FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND approval_status IN ('draft','submitted','rejected')",
        (estate_id(), username),
    ) or {}
    totals.update(queue_totals)
    totals.update(_worker_payment_totals(estate_id(), username, worker_name))
    weather = weather_context_payload()
    work = fetch_all(
        "SELECT title,due_date,priority,status FROM tasks WHERE estate_id=%s AND status IN ('open','in_progress') "
        "ORDER BY FIELD(priority,'urgent','high','medium','low'),due_date IS NULL,due_date LIMIT 5",
        (estate_id(),),
    )
    return json_ready({
        "username": username, "worker_name": worker_name, "active": active, "pending": pending, "history": history,
        "totals": totals, "weather": weather, "work": work, "server_time": datetime.now(ZoneInfo("Europe/Rome")),
    })


@app.post("/api/v1/worker-portal/clock-in", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_clock_in(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    profile = _worker_profile(worker_name)
    existing = fetch_one(
        "SELECT id,clock_in_at FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft' LIMIT 1",
        (estate_id(), username),
    )
    if existing:
        raise HTTPException(409, "You are already clocked in / Sei già registrato")
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    record_id = new_id()
    values = {
        "work_category": str(payload.get("work_category") or "general")[:100],
        "work_performed": str(payload.get("work_performed") or "").strip()[:500] or None,
        "location_text": str(payload.get("location_text") or "Tenuta Baiamonte")[:180],
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO labor_entries (id,estate_id,season_id,work_date,person_or_crew,role,start_time,regular_hours,overtime_hours,payroll_scope,payment_status,entry_source,worker_username,clock_in_at,approval_status,work_category,work_performed,location_text,pay_due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,0,0,%s,'verification_needed','worker_portal',%s,%s,'draft',%s,%s,%s,%s)",
            (record_id, estate_id(), season_for_year(now.year), now.date(), worker_name, profile["role"], now.time(), profile["payroll_scope"], username, now, values["work_category"], values["work_performed"], values["location_text"], _worker_pay_due(worker_name, now.date())),
        )
        audit(cursor, "clock_in", "labor", record_id, {"worker": worker_name, "clock_in_at": now, **values}, username)
    return {"saved": True, "id": record_id, "clock_in_at": now.isoformat()}


@app.post("/api/v1/worker-portal/clock-out", dependencies=[Depends(authorize_worker)])
def worker_clock_out(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = fetch_one(
        "SELECT * FROM labor_entries WHERE estate_id=%s AND worker_username=%s AND clock_out_at IS NULL AND approval_status='draft' ORDER BY clock_in_at DESC LIMIT 1",
        (estate_id(), username),
    )
    if not row:
        raise HTTPException(409, "No open shift / Nessun turno aperto")
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    started = row.get("clock_in_at")
    hours = round(max(0.0, min(24.0, (now - started).total_seconds() / 3600)), 2) if started else 0
    if hours <= 0:
        raise HTTPException(422, "The shift is too short to submit")
    expense = payload.get("expense_amount_eur")
    expense = None if expense in (None, "") else round(float(expense), 2)
    if expense is not None and (expense < 0 or expense > 10000):
        raise HTTPException(422, "Enter a valid expense amount")
    changes = {
        "clock_out_at": now, "end_time": now.time(), "regular_hours": hours, "approval_status": "submitted", "submitted_at": now,
        "work_performed": str(payload.get("work_performed") or row.get("work_performed") or "").strip()[:500] or None,
        "notes": str(payload.get("notes") or "").strip() or None,
        "expense_amount_eur": expense,
        "expense_category": str(payload.get("expense_category") or "").strip()[:100] or None,
        "expense_notes": str(payload.get("expense_notes") or "").strip() or None,
        "review_note": None,
    }
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE labor_entries SET clock_out_at=%s,end_time=%s,regular_hours=%s,approval_status=%s,submitted_at=%s,work_performed=%s,notes=%s,expense_amount_eur=%s,expense_category=%s,expense_notes=%s,review_note=%s WHERE id=%s AND estate_id=%s",
            (*changes.values(), row["id"], estate_id()),
        )
        audit(cursor, "clock_out_submit", "labor", row["id"], changes, username)
    return {"saved": True, "id": row["id"], "hours": hours, "approval_status": "submitted"}


@app.post("/api/v1/worker-portal/charge", status_code=201, dependencies=[Depends(authorize_worker)])
def worker_one_off_charge(request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, worker_name = _worker_identity(request, settings)
    profile = _worker_profile(worker_name)
    description = str(payload.get("description") or "").strip()[:500]
    if not description:
        raise HTTPException(422, "Enter what was delivered or provided")
    try:
        amount = round(float(payload.get("amount_eur")), 2)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid charge amount") from error
    if not 0 < amount <= 10000:
        raise HTTPException(422, "Enter a charge between €0.01 and €10,000")
    try:
        service_date = date.fromisoformat(str(payload.get("service_date") or ""))
    except ValueError as error:
        raise HTTPException(422, "Enter a valid service date") from error
    rome_today = datetime.now(ZoneInfo("Europe/Rome")).date()
    if service_date > rome_today:
        raise HTTPException(422, "The service date cannot be in the future")
    category = str(payload.get("category") or "Other service").strip()[:100] or "Other service"
    notes = str(payload.get("notes") or "").strip()[:2000] or None
    now = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO labor_entries (id,estate_id,season_id,work_date,person_or_crew,role,regular_hours,overtime_hours,payroll_scope,payment_status,entry_source,worker_username,approval_status,submitted_at,work_category,work_performed,notes,expense_amount_eur,expense_category,expense_notes,location_text,pay_due_date) "
            "VALUES (%s,%s,%s,%s,%s,%s,0,0,%s,'verification_needed','worker_portal_charge',%s,'submitted',%s,'one_off_charge',%s,%s,%s,%s,%s,'Tenuta Baiamonte',%s)",
            (record_id, estate_id(), season_for_year(service_date.year), service_date, worker_name, profile["role"], profile["payroll_scope"], username, now, description, notes, amount, category, notes, _worker_pay_due(worker_name, service_date)),
        )
        audit(cursor, "worker_charge_submit", "labor", record_id, {"worker": worker_name, "service_date": service_date, "amount_eur": amount, "category": category, "description": description}, username)
    return {"saved": True, "id": record_id, "approval_status": "submitted", "queue": "services", "amount_eur": amount}


@app.patch("/api/v1/worker-portal/entries/{record_id}", dependencies=[Depends(authorize_worker)])
def worker_edit_entry(record_id: str, request: Request, payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = _worker_labor_row(record_id, username)
    if row.get("approval_status") == "approved" or row.get("locked_at"):
        raise HTTPException(409, "Approved records are locked / I record approvati sono bloccati")
    allowed = {"work_performed", "notes", "expense_amount_eur", "expense_category", "expense_notes"}
    values = {key: payload.get(key) for key in allowed if key in payload}
    adjusted_times = False
    if "clock_in_at" in payload or "clock_out_at" in payload:
        try:
            started = datetime.fromisoformat(str(payload.get("clock_in_at") or row.get("clock_in_at")))
            ended = datetime.fromisoformat(str(payload.get("clock_out_at") or row.get("clock_out_at")))
        except (TypeError, ValueError) as error:
            raise HTTPException(422, "Enter valid clock-in and clock-out times") from error
        if ended <= started or (ended - started).total_seconds() > 24 * 3600:
            raise HTTPException(422, "Clock-out must be after clock-in and within 24 hours")
        values.update({"clock_in_at": started, "clock_out_at": ended, "work_date": started.date(), "start_time": started.time(), "end_time": ended.time(), "regular_hours": round((ended - started).total_seconds() / 3600, 2), "time_adjusted_by_worker": 1})
        adjusted_times = True
    if "expense_amount_eur" in values:
        values["expense_amount_eur"] = None if values["expense_amount_eur"] in (None, "") else round(float(values["expense_amount_eur"]), 2)
        if values["expense_amount_eur"] is not None and not 0 <= values["expense_amount_eur"] <= 10000:
            raise HTTPException(422, "Enter a valid expense amount")
    if not values:
        raise HTTPException(422, "Enter a change")
    if row.get("approval_status") == "rejected":
        values.update({"approval_status": "submitted", "submitted_at": datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)})
    with transaction() as (_, cursor):
        cursor.execute(f"UPDATE labor_entries SET {','.join(f'{key}=%s' for key in values)},review_note=NULL WHERE id=%s AND estate_id=%s", (*values.values(), record_id, estate_id()))
        audit(cursor, "worker_time_edit" if adjusted_times else "worker_edit", "labor", record_id, {"before": json_ready(row), "changes": values}, username)
    return {"saved": True, "id": record_id, "time_adjusted": adjusted_times}


@app.post("/api/v1/worker-portal/entries/{record_id}/photo", status_code=201, dependencies=[Depends(authorize_worker)])
async def worker_add_photo(record_id: str, request: Request, file: UploadFile = File(...), caption: str = Form(""), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    username, _ = _worker_identity(request, settings)
    row = _worker_labor_row(record_id, username)
    if row.get("approval_status") == "approved" or row.get("locked_at"):
        raise HTTPException(409, "Approved records are locked")
    data = await file.read(15 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Photo must be 15 MB or smaller")
    media_type = file.content_type or "application/octet-stream"
    if not media_type.startswith("image/"):
        raise HTTPException(422, "Choose a photo")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "work-photo").name)[:180]
    attachment_id = new_id()
    attachment_root.mkdir(parents=True, exist_ok=True)
    stored = attachment_root / f"{attachment_id}-{safe_name}"
    stored.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,'labor',%s,%s,%s,%s,%s,%s,%s)", (attachment_id, estate_id(), record_id, safe_name, str(stored), media_type, digest, caption or None, username))
        audit(cursor, "worker_photo", "labor", record_id, {"attachment_id": attachment_id, "filename": safe_name}, username)
    return {"saved": True, "id": attachment_id, "entity_id": record_id}


@app.post("/api/v1/admin/worker-labor/{record_id}/review", dependencies=[Depends(authorize_admin)])
def review_worker_labor(record_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    decision = str(payload.get("decision") or "").casefold()
    if decision not in {"approve", "reject"}:
        raise HTTPException(422, "Choose approve or reject")
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s AND worker_username IS NOT NULL", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Worker submission not found")
    if row.get("approval_status") == "approved":
        raise HTTPException(409, "This record is already approved and locked")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    note = str(payload.get("review_note") or "").strip() or None
    status = "approved" if decision == "approve" else "rejected"
    rate = payload.get("hourly_rate_eur")
    rate = row.get("hourly_rate_eur") if rate in (None, "") else round(float(rate), 2)
    if rate is not None and not 0 <= float(rate) <= 1000:
        raise HTTPException(422, "Enter a valid hourly rate")
    hours = float(row.get("regular_hours") or 0) + float(row.get("overtime_hours") or 0)
    labor_cost = round(hours * float(rate), 2) if rate is not None else row.get("labor_cost_eur")
    approval_time = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None) if status == "approved" else None
    pay_due_date = row.get("pay_due_date") or (approval_time.date() if approval_time else None)
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE labor_entries SET approval_status=%s,approved_by=%s,locked_at=IF(%s='approved',NOW(6),NULL),review_note=%s,"
            "hourly_rate_eur=IF(%s='approved',%s,hourly_rate_eur),labor_cost_eur=IF(%s='approved',%s,labor_cost_eur),"
            "other_cost_eur=IF(%s='approved',expense_amount_eur,other_cost_eur),pay_due_date=IF(%s='approved',%s,pay_due_date),"
            "paid_at=NULL,payment_status=IF(%s='approved','unpaid',payment_status) WHERE id=%s AND estate_id=%s",
            (status, actor if status == "approved" else None, status, note, status, rate, status, labor_cost, status, status, pay_due_date, status, record_id, estate_id()),
        )
        audit(cursor, f"worker_{status}", "labor", record_id, {"status": status, "review_note": note, "hourly_rate_eur": rate, "labor_cost_eur": labor_cost, "pay_due_date": pay_due_date, "payment_status": "unpaid" if status == "approved" else row.get("payment_status")}, actor)
    return {"saved": True, "id": record_id, "approval_status": status, "labor_cost_eur": labor_cost, "pay_due_date": pay_due_date, "payment_status": "unpaid" if status == "approved" else row.get("payment_status")}


@app.post("/api/v1/admin/worker-labor/{record_id}/pay", dependencies=[Depends(authorize_admin)])
def pay_worker_labor(record_id: str, request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Worker payment record not found")
    if row.get("approval_status") != "approved":
        raise HTTPException(409, "Approve and lock the labor record before payment")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return _record_labor_invoice_payment(row, payload or {}, actor, estate_id())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/admin/labor-payment-batches/pay", dependencies=[Depends(authorize_admin)])
def pay_worker_labor_batch(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    record_ids = list(dict.fromkeys(str(value).strip() for value in (payload.get("record_ids") or []) if str(value).strip()))
    if not record_ids or len(record_ids) > 200:
        raise HTTPException(422, "Choose between 1 and 200 payment records")
    placeholders = ",".join(["%s"] * len(record_ids))
    rows = fetch_all(
        f"SELECT * FROM labor_entries WHERE estate_id=%s AND id IN ({placeholders})",
        (estate_id(), *record_ids),
    )
    if len(rows) != len(record_ids):
        raise HTTPException(404, "One or more payment records were not found")
    if any(row.get("approval_status") != "approved" for row in rows):
        raise HTTPException(409, "Every record in the timesheet must be approved before payment")
    if any(row.get("payment_status") == "part_paid" for row in rows):
        raise HTTPException(409, "Finish partially paid invoices individually so each deposit remains allocated correctly")
    if any(row.get("payment_status") == "verification_needed" for row in rows):
        raise HTTPException(409, "Resolve every verification hold before paying the timesheet")
    batch_keys = {_worker_payment_batch_key(row) for row in rows}
    workers = {str(row.get("person_or_crew") or "").strip().casefold() for row in rows}
    if len(batch_keys) != 1 or len(workers) != 1:
        raise HTTPException(409, "The selected records do not belong to one employee timesheet")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return _record_labor_payment_batch(rows, record_ids, next(iter(batch_keys)), actor, estate_id())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/admin/worker-labor/{record_id}/presence", dependencies=[Depends(authorize_admin)])
def worker_labor_presence(record_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s AND worker_username IS NOT NULL", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Worker submission not found")
    return json_ready(_timesheet_presence(str(row.get("person_or_crew") or ""), [{"work_date": row.get("work_date"), "hours": row.get("regular_hours")}]))


PROCESS_INTEGRATIONS = {
    "full_refresh": "full-system-refresh", "planning": "google-planning", "weather": "home-assistant-weather", "forecast_sources": "external-prediction-sources", "harvest": "harvest-projection", "cistern": "cistern-camera-level", "gmail": "gmail-intake",
    "finance": "fattureincloud", "whatsapp": "whatsapp-system", "cameras": "camera-snapshot-cache", "etna": "etna-monitor", "public_feed": "public-harvest-publisher",
    "traffic": "home-assistant-traffic", "disease": "disease-pressure", "alerts": "operational-alerts",
}


def _configured(value: Any) -> bool:
    return bool(str(value or "").strip())


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def payroll_summary(year: int) -> dict[str, Any]:
    row = _labor_payment_summary(estate_id(), year)
    review = fetch_one(
        "SELECT COALESCE(SUM(approval_status IN ('draft','submitted')),0) awaiting_review FROM labor_entries WHERE estate_id=%s",
        (estate_id(),),
    ) or {}
    return json_ready({"year": year, **row, **review})


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


def _labor_identity_links() -> dict[str, str]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='labor_identity_links'",
        (estate_id(),),
    ) or {}
    try:
        payload = json.loads(row.get("setting_value") or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(worker_key).strip(): str(person_entity).strip()
        for worker_key, person_entity in payload.items()
        if str(worker_key).strip() and str(person_entity).strip().startswith("person.")
    }


@app.get("/api/v1/admin/control", dependencies=[Depends(authorize_admin)])
def admin_control(request: Request) -> dict[str, Any]:
    controls = process_controls()
    settings = get_settings()
    collation = "utf8mb4_unicode_ci"
    latest = {row["integration_name"]: row for row in fetch_all(
        "SELECT e.integration_name,e.status,e.occurred_at,e.error_message,e.payload FROM integration_events e "
        "JOIN (SELECT candidate.integration_name,MAX(candidate.id) id FROM integration_events candidate WHERE candidate.estate_id=%s "
        f"AND NOT (candidate.status='failed' AND EXISTS (SELECT 1 FROM error_acknowledgements a "
        f"WHERE a.estate_id COLLATE {collation}=candidate.estate_id COLLATE {collation} AND a.error_kind='integration' "
        f"AND a.record_id COLLATE {collation}=CAST(candidate.id AS CHAR) COLLATE {collation})) "
        "GROUP BY candidate.integration_name) x ON x.id=e.id",
        (estate_id(),),
    )}
    now = datetime.now()
    processing_runtime = processing_runtime_snapshot()
    active_by_code = {str(item.get("code")): item for item in processing_runtime.get("jobs") or []}
    processes = []
    for code in PROCESS_ORDER:
        item = controls["processes"][code]
        event = latest.get(PROCESS_INTEGRATIONS.get(code, code)) or {}
        occurred = event.get("occurred_at")
        next_run = occurred + timedelta(minutes=item["interval_minutes"]) if occurred and item["enabled"] and not controls["paused"] else None
        age_minutes = max(0, int((now - occurred).total_seconds() / 60)) if occurred else None
        active = active_by_code.get(code)
        if active and active.get("state") == "timed_out":
            health = "timed_out"
        elif active:
            health = "running"
        elif controls["paused"] or not item["enabled"]:
            health = "paused"
        elif event.get("status") == "failed":
            health = "error"
        elif age_minutes is None:
            health = "waiting"
        elif age_minutes > item["interval_minutes"] * 2 + 2:
            health = "stale"
        else:
            health = "healthy"
        processes.append({**item, "code": code, "health": health, "last_status": event.get("status"), "last_run": occurred, "next_run": next_run, "last_error": active.get("error") if active and active.get("error") else event.get("error_message"), "active_run": active})
    process_by_code = {item["code"]: item for item in processes}
    website_process = process_by_code.get("public_feed") or {}
    website_state = "off" if not settings.public_publish_url else {
        "healthy": "green", "error": "red", "stale": "red", "waiting": "amber", "paused": "off",
    }.get(str(website_process.get("health")), "amber")
    website_detail = (
        "Not configured" if not settings.public_publish_url else
        str(website_process.get("last_error") or "Publish is overdue") if website_state == "red" else
        f"Last publish {website_process.get('last_run')}" if website_state == "green" else
        "Publishing paused" if website_state == "off" else "Waiting for a successful publish"
    )
    review = fetch_one("SELECT COUNT(*) total,SUM(review_status='ready_for_review') ready,SUM(review_status='failed') failed FROM intake_items WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed')", (estate_id(),)) or {}
    review_age = fetch_one("SELECT MIN(received_at) oldest_pending_at FROM intake_items WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed')", (estate_id(),)) or {}
    recovery_errors = fetch_all(
        "SELECT current_event.id,current_event.integration_name,current_event.event_type,current_event.error_message,current_event.occurred_at "
        "FROM integration_events current_event WHERE current_event.estate_id=%s AND current_event.status='failed' "
        "AND current_event.integration_name<>'whatsapp-channel' "
        "AND NOT EXISTS (SELECT 1 FROM integration_events newer_event WHERE newer_event.estate_id=current_event.estate_id "
        "AND newer_event.integration_name=current_event.integration_name AND newer_event.event_type=current_event.event_type "
        "AND (newer_event.occurred_at>current_event.occurred_at OR (newer_event.occurred_at=current_event.occurred_at AND newer_event.id>current_event.id))) "
        f"AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a WHERE a.estate_id COLLATE {collation}=current_event.estate_id COLLATE {collation} "
        f"AND a.error_kind='integration' AND a.record_id COLLATE {collation}=CAST(current_event.id AS CHAR) COLLATE {collation}) "
        "ORDER BY current_event.occurred_at DESC LIMIT 30",
        (estate_id(),),
    )
    failed_intake = fetch_all(
        "SELECT i.id,i.source,i.title,i.original_filename,i.processing_error,i.received_at occurred_at FROM intake_items i "
        f"WHERE i.estate_id=%s AND i.review_status='failed' AND NOT EXISTS (SELECT 1 FROM error_acknowledgements a "
        f"WHERE a.estate_id COLLATE {collation}=i.estate_id COLLATE {collation} AND a.error_kind='intake' "
        f"AND a.record_id COLLATE {collation}=CAST(i.id AS CHAR) COLLATE {collation}) "
        "ORDER BY i.received_at DESC LIMIT 20",
        (estate_id(),),
    )
    attachment_count = fetch_one("SELECT COUNT(*) total FROM entity_attachments WHERE estate_id=%s", (estate_id(),)) or {}
    try:
        storage = shutil.disk_usage("/data")
        storage_summary = {"total_bytes": storage.total, "used_bytes": storage.used, "free_bytes": storage.free, "used_percent": round(storage.used / storage.total * 100, 1) if storage.total else None}
    except OSError:
        storage_summary = {"total_bytes": None, "used_bytes": None, "free_bytes": None, "used_percent": None}
    mcp_hosts = {item.strip() for item in settings.mcp_allowed_hosts.split(",") if item.strip()}
    setup_warnings = []
    if not settings.mcp_server_token:
        setup_warnings.append("Create an MCP server token to connect Codex on the Mac.")
    if not any(item.startswith("192.168.0.10:") for item in mcp_hosts):
        setup_warnings.append("Allow 192.168.0.10:* in MCP allowed hosts.")
    if not settings.openai_api_key:
        setup_warnings.append("Add an OpenAI API key to enable document, photo and question analysis.")
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
        "connections": {
            "mac_api": {"state": "green" if settings.mcp_server_token or settings.api_key else "amber", "detail": "Authenticated" if settings.mcp_server_token or settings.api_key else "Needs setup"},
            "gmail": {"state": "green" if settings.gmail_address and settings.gmail_app_password else "amber", "detail": "Configured" if settings.gmail_address and settings.gmail_app_password else "Needs setup"},
            "whatsapp": {"state": "green" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "amber", "detail": "Configured" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "Needs setup"},
            "website": {"state": website_state, "detail": website_detail},
        },
        "runtime": {
            "version": addon_version(), "uptime_seconds": int(time.monotonic() - APP_STARTED_MONOTONIC),
            "database": "connected", "storage": storage_summary, "attachment_count": int(attachment_count.get("total") or 0),
            "processing_errors_24h": len(recovery_errors) + len(failed_intake), "oldest_review_at": review_age.get("oldest_pending_at"),
            "processing": processing_runtime,
        },
        "mac_setup": {
            "endpoint": "http://192.168.0.10:8100/mcp", "token_configured": bool(settings.mcp_server_token),
            "writes_enabled": bool(settings.mcp_allow_writes), "allowed_host_ready": any(item.startswith("192.168.0.10:") for item in mcp_hosts),
            "setup_warnings": setup_warnings,
        },
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
        "payroll": payroll_summary(date.today().year),
        "payment_integrity": payment_integrity,
        "data_quality": operational_data_quality(estate_id()),
        "recovery_errors": [
            {**row, "kind": "integration", "recoverable": row["integration_name"] in set(PROCESS_INTEGRATIONS.values())} for row in recovery_errors
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
    if access_level not in {"admin", "operations", "hospitality", "worker", "viewer", "none"}:
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


@app.patch("/api/v1/admin/labor/{record_id}", dependencies=[Depends(authorize_admin)])
def update_labor_record(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed = {
        "work_date", "person_or_crew", "regular_hours", "overtime_hours",
        "hourly_rate_eur", "work_performed", "notes",
        "role", "work_category", "payroll_scope", "entry_source",
        "expense_amount_eur", "other_cost_eur", "expense_category",
        "expense_notes",
    }
    resolve_verification = payload.get("resolve_verification") is True
    values = {key: payload.get(key) for key in allowed if key in payload}
    job_lines = payload.get("job_lines") if "job_lines" in payload else None
    if job_lines is not None:
        try:
            values.update(_normalize_contractor_job_lines(payload))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
    if not values and not resolve_verification:
        raise HTTPException(422, "Enter a labor correction")
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Labor entry not found")
    if "work_date" in values:
        try:
            values["work_date"] = date.fromisoformat(str(values["work_date"])).isoformat()
        except ValueError as error:
            raise HTTPException(422, "Use a valid work date") from error
    if "person_or_crew" in values and not str(values["person_or_crew"] or "").strip():
        raise HTTPException(422, "Worker name is required")
    for key in ("regular_hours", "overtime_hours"):
        if key in values:
            values[key] = float(values[key] or 0)
            if values[key] < 0 or (job_lines is None and values[key] > 24):
                raise HTTPException(422, "Hours must be between 0 and 24")
    if "hourly_rate_eur" in values:
        values["hourly_rate_eur"] = None if values["hourly_rate_eur"] in (None, "") else float(values["hourly_rate_eur"])
        if values["hourly_rate_eur"] is not None and values["hourly_rate_eur"] < 0:
            raise HTTPException(422, "Hourly rate cannot be negative")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s FOR UPDATE", (record_id, estate_id()))
        locked = cursor.fetchone()
        if not locked:
            raise HTTPException(404, "Labor entry not found")
        cursor.execute(
            "SELECT COALESCE(SUM(amount_eur),0) amount_paid FROM labor_invoice_payments WHERE estate_id=%s AND labor_entry_id=%s AND voided_at IS NULL",
            (estate_id(), record_id),
        )
        amount_paid = float((cursor.fetchone() or {}).get("amount_paid") or 0)
        protected_fields = {
            "work_date", "person_or_crew", "regular_hours", "overtime_hours", "hourly_rate_eur",
            "labor_cost_eur", "other_cost_eur", "expense_amount_eur", "expense_category",
            "expense_notes", "work_category", "payroll_scope", "entry_source",
        }
        if (amount_paid > 0 or locked.get("payment_status") in {"part_paid", "paid"}) and protected_fields.intersection(values):
            raise HTTPException(409, "This invoice already has a payment. Financial and ownership fields are locked; only notes and description may be corrected.")
        merged = {**locked, **values}
        if job_lines is None and merged.get("hourly_rate_eur") is not None:
            values["labor_cost_eur"] = round((float(merged.get("regular_hours") or 0) + float(merged.get("overtime_hours") or 0)) * float(merged["hourly_rate_eur"]), 2)
        if resolve_verification:
            if locked.get("approval_status") != "approved" or locked.get("payment_status") != "verification_needed":
                raise HTTPException(409, "Only an approved verification hold can be released")
            if amount_paid > 0:
                raise HTTPException(409, "This held invoice already has payment history and needs ledger reconciliation before release")
            invoice_total = float(values.get("labor_cost_eur", merged.get("labor_cost_eur")) or 0) + float(values.get("other_cost_eur", merged.get("other_cost_eur")) or 0)
            if invoice_total <= 0:
                raise HTTPException(422, "Enter and verify a positive invoice amount before releasing payment")
            values["payment_status"] = "unpaid"
            values["paid_at"] = None
        assignments = ",".join(f"{key}=%s" for key in values)
        if resolve_verification:
            assignments += ",approved_by=COALESCE(NULLIF(approved_by,''),%s),locked_at=COALESCE(locked_at,NOW(6))"
            params = (*values.values(), actor, record_id, estate_id())
        else:
            params = (*values.values(), record_id, estate_id())
        cursor.execute(
            f"UPDATE labor_entries SET {assignments} WHERE id=%s AND estate_id=%s",
            params,
        )
        audit(cursor, "resolve_verification" if resolve_verification else "correct", "labor", record_id, {"before": json_ready(locked), "changes": values, "amount_paid_eur": amount_paid}, actor)
    return {"saved": True, "id": record_id, "labor_cost_eur": values.get("labor_cost_eur"), "payment_status": values.get("payment_status", row.get("payment_status"))}


@app.delete("/api/v1/admin/labor/{record_id}", dependencies=[Depends(authorize_admin)])
def delete_labor_record(record_id: str, request: Request) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Labor entry not found")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT COUNT(*) payment_count FROM labor_invoice_payments WHERE estate_id=%s AND labor_entry_id=%s",
            (estate_id(), record_id),
        )
        if int((cursor.fetchone() or {}).get("payment_count") or 0) or row.get("payment_status") in {"part_paid", "paid"}:
            raise HTTPException(409, "This labor record has payment history and cannot be deleted. Retain it for audit and correct its notes instead.")
        audit(cursor, "delete", "labor", record_id, {"before": json_ready(row)}, actor)
        cursor.execute("DELETE FROM labor_entries WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    return {"deleted": True, "id": record_id}


@app.post("/api/v1/admin/labor/reassign-worker", dependencies=[Depends(authorize_admin)])
def reassign_unidentified_worker(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    current_name = str(payload.get("current_name") or "").strip()
    new_name = str(payload.get("new_name") or "").strip()
    if not current_name.casefold().startswith("unidentified part-time worker"):
        raise HTTPException(422, "Only unidentified worker records can be reassigned here")
    if not new_name or new_name.casefold().startswith("unidentified part-time worker"):
        raise HTTPException(422, "Enter the worker's real name")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE labor_entries SET person_or_crew=%s,approved_by=%s WHERE estate_id=%s AND LOWER(person_or_crew)=LOWER(%s)",
            (new_name[:200], actor, estate_id(), current_name),
        )
        changed = cursor.rowcount
        audit(cursor, "reassign_worker", "labor_worker", current_name, {"from": current_name, "to": new_name[:200], "records_updated": changed}, actor)
    if not changed:
        raise HTTPException(404, "No labor records were found for that unidentified worker")
    return {"saved": True, "from": current_name, "to": new_name[:200], "records_updated": changed}


@app.put("/api/v1/admin/labor-identities/{worker_key}/home-assistant-person", dependencies=[Depends(authorize_admin)])
def link_labor_identity(worker_key: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker_key = worker_key.strip()
    person_entity = str(payload.get("person_entity") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", worker_key):
        raise HTTPException(422, "Choose a valid payroll worker")
    if worker_key.startswith("seasonal-worker-"):
        raise HTTPException(422, "Identify the historical worker before linking a Home Assistant Person")
    ha_person = next((item for item in home_assistant_people() if item.get("entity_id") == person_entity), None)
    if not ha_person:
        raise HTTPException(422, "Choose an existing Home Assistant Person")
    links = _labor_identity_links()
    conflict = next((key for key, entity in links.items() if key != worker_key and entity == person_entity), None)
    if conflict:
        raise HTTPException(409, "That Home Assistant Person is already linked to another payroll worker")
    links[worker_key] = person_entity
    actor = request.headers.get("X-Remote-User-Name") or "api"
    attributes = ha_person.get("attributes") or {}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'labor_identity_links',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(links, ensure_ascii=False)),
        )
        audit(cursor, "link", "labor_identity", worker_key, {
            "worker_key": worker_key,
            "person_entity": person_entity,
            "home_assistant_name": attributes.get("friendly_name"),
        }, actor)
    return {
        "saved": True,
        "worker_key": worker_key,
        "person_entity": person_entity,
        "name": attributes.get("friendly_name") or person_entity.removeprefix("person.").replace("_", " ").title(),
    }


@app.post("/api/v1/admin/labor/monthly", dependencies=[Depends(authorize_admin)])
def save_monthly_labor_total(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker = str(payload.get("worker") or "").strip()
    month_text = str(payload.get("month") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    if not worker:
        raise HTTPException(422, "Worker name is required")
    try:
        month_start = date.fromisoformat(f"{month_text}-01")
        hours = float(payload.get("hours"))
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid month and total hours") from error
    if hours <= 0 or hours > 744:
        raise HTTPException(422, "Monthly hours must be greater than 0 and no more than 744")
    rate_value = payload.get("hourly_rate_eur")
    rate = None if rate_value in (None, "") else float(rate_value)
    if rate is None and "giancarlo" in worker.casefold():
        rate = 10.0
    if rate is not None and rate < 0:
        raise HTTPException(422, "Hourly rate cannot be negative")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    source_id = f"MONTHLY-{worker.casefold().replace(' ', '-')}-{month_text}"
    cost = round(hours * rate, 2) if rate is not None else None
    existing = fetch_one(
        "SELECT * FROM labor_entries WHERE estate_id=%s AND source_labor_id=%s LIMIT 1",
        (estate_id(), source_id),
    )
    record_id = existing.get("id") if existing else new_id()
    values = {
        "work_date": month_start,
        "shift_label": f"Monthly total {month_text}",
        "person_or_crew": worker,
        "regular_hours": hours,
        "hourly_rate_eur": rate,
        "labor_cost_eur": cost,
        "approved_by": actor,
        "notes": notes or f"Monthly attendance total for {month_text}; daily dates were not reported.",
    }
    with transaction() as (_, cursor):
        if existing:
            cursor.execute(
                "UPDATE labor_entries SET work_date=%s,shift_label=%s,person_or_crew=%s,regular_hours=%s,"
                "overtime_hours=0,hourly_rate_eur=%s,labor_cost_eur=%s,approved_by=%s,notes=%s WHERE id=%s AND estate_id=%s",
                (*values.values(), record_id, estate_id()),
            )
            audit(cursor, "correct", "monthly_labor", record_id, {"before": json_ready(existing), "changes": values}, actor)
        else:
            cursor.execute(
                "INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,regular_hours,overtime_hours,hourly_rate_eur,labor_cost_eur,approved_by,payment_status,payroll_scope,entry_source,notes) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'Estate manager',%s,0,%s,%s,%s,'unknown','part_time','monthly_total',%s)",
                (record_id, estate_id(), season_for_year(month_start.year), source_id, *values.values()),
            )
            audit(cursor, "create", "monthly_labor", record_id, values, actor)
    return {"saved": True, "id": record_id, "worker": worker, "month": month_text, "hours": hours, "updated": bool(existing)}


@app.patch("/api/v1/admin/timesheets/{record_id}", dependencies=[Depends(authorize_admin)])
def save_timesheet_draft(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    worker, entries = str(payload.get("worker") or "").strip(), payload.get("entries") or []
    if not worker or not isinstance(entries, list):
        raise HTTPException(422, "Enter a worker and day or month lines")
    for row in entries:
        if not isinstance(row, dict):
            raise HTTPException(422, "Every timesheet line must be a day or monthly total")
        period_type = str(row.get("period_type") or "day").strip().casefold()
        if period_type not in {"day", "month"}:
            raise HTTPException(422, "Choose Day or Month total for every timesheet line")
        period_value = row.get("work_month") if period_type == "month" else row.get("work_date") or row.get("date")
        if not str(period_value or "").strip():
            raise HTTPException(422, f"Every {period_type} line needs a valid {period_type}")
        row_worker = str(row.get("person_or_crew") or row.get("worker") or worker).strip()
        if row_worker.casefold() != worker.casefold():
            raise HTTPException(422, "Save and approve one employee at a time; split mixed-worker hours into separate reviews")
    expenses = _normalize_timesheet_expenses(payload.get("expenses") or [])
    draft = {
        "person_or_crew": worker,
        "hourly_rate_eur": payload.get("hourly_rate_eur"),
        "timesheet_entries": entries,
        "reimbursable_expenses": expenses,
    }
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE intake_items SET extracted_data=%s,review_status='ready_for_review',review_reason=%s WHERE id=%s AND estate_id=%s AND review_status IN ('new','ready_for_review')",
            (json.dumps(draft, default=str), "Timesheet edited in Operations Control; awaiting approval", record_id, estate_id()),
        )
        if not changed:
            raise HTTPException(404, "Pending timesheet not found")
        audit(cursor, "edit", "timesheet_review", record_id, draft, request.headers.get("X-Remote-User-Name") or "api")
    return {"saved": True, "id": record_id}


def _normalize_timesheet_expenses(raw_expenses: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_expenses, list):
        raise HTTPException(422, "Reimbursable expenses must be entered as separate rows")
    normalized = []
    allowed_categories = {
        "contractor_job", "water_delivery", "equipment", "transport",
        "materials", "fuel", "tools", "delivery", "service", "other",
    }
    for raw in raw_expenses:
        if not isinstance(raw, dict):
            raise HTTPException(422, "Every reimbursable expense must be a separate row")
        amount_value = raw.get("amount_eur")
        if amount_value in (None, ""):
            continue
        try:
            amount = round(float(amount_value), 2)
            expense_date = date.fromisoformat(str(raw.get("expense_date") or raw.get("date") or "")[:10])
        except (TypeError, ValueError) as error:
            raise HTTPException(422, "Every reimbursable expense needs a valid date and amount") from error
        if expense_date > datetime.now(ZoneInfo("Europe/Rome")).date():
            raise HTTPException(422, "A reimbursable expense cannot be dated in the future")
        if amount <= 0 or amount > 10000:
            raise HTTPException(422, "Each reimbursable expense must be greater than €0 and no more than €10,000")
        category = str(raw.get("category") or "other").strip().casefold()
        if category not in allowed_categories:
            raise HTTPException(422, "Choose a valid reimbursement category")
        description = str(raw.get("description") or raw.get("notes") or "").strip()
        if not description:
            raise HTTPException(422, "Describe each reimbursable expense")
        normalized.append({
            "expense_date": expense_date.isoformat(),
            "category": category,
            "description": description[:500],
            "amount_eur": amount,
        })
    return normalized


def _timesheet_presence(worker: str, raw_entries: list[dict[str, Any]]) -> dict[str, Any]:
    dates = []
    for row in raw_entries:
        if not isinstance(row, dict):
            raise HTTPException(422, "Every timesheet row must be a dated labor entry")
        row_worker = str(row.get("person_or_crew") or row.get("worker") or worker).strip()
        if row_worker.casefold() != worker.casefold():
            raise HTTPException(422, "Approve one employee at a time; split mixed-worker hours into separate reviews")
        try:
            dates.append(date.fromisoformat(str(row.get("work_date") or row.get("date"))[:10]))
        except (AttributeError, TypeError, ValueError):
            continue
    dates = sorted(set(dates))
    if not dates:
        return {"available": False, "reason": "No dated rows", "days": [], "confidence_percent": 0}
    resolved_identity = resolve_timesheet_presence_entities(
        worker,
        _labor_identity_links(),
        home_assistant_people(),
        people_profiles(),
        _match_home_assistant_person,
    )
    if not resolved_identity:
        return {"available": False, "reason": "No Home Assistant person or phone entity is assigned to this worker", "days": [{"work_date": day.isoformat(), "status": "unknown", "sources": [], "confidence_percent": 0} for day in dates], "confidence_percent": 0}
    aliases, entities = resolved_identity
    camera_entities = (
        "sensor.gate_doorbell_person_name", "sensor.front_gate_person_name", "sensor.vineyard_north_person_name",
        "sensor.mid_vineyard_north_person_name", "sensor.rear_gate_person_name",
    )
    token = home_assistant_token()
    if not token:
        return {"available": False, "reason": "Home Assistant history authentication unavailable", "days": [{"work_date": day.isoformat(), "status": "unknown", "sources": [], "confidence_percent": 0} for day in dates], "confidence_percent": 0}
    rome = ZoneInfo("Europe/Rome")
    start = datetime.combine(dates[0], datetime.min.time()).replace(tzinfo=rome)
    end = datetime.combine(dates[-1] + timedelta(days=1), datetime.min.time()).replace(tzinfo=rome)
    query = urllib.parse.urlencode({"end_time": end.isoformat(), "filter_entity_id": ",".join((*entities, *camera_entities)), "minimal_response": ""})
    url = "http://supervisor/core/api/history/period/" + urllib.parse.quote(start.isoformat(), safe="-:T+") + "?" + query
    try:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            history = json.loads(response.read())
    except Exception as error:
        return {"available": False, "reason": f"Home Assistant history could not be read: {type(error).__name__}", "days": [{"work_date": day.isoformat(), "status": "unknown", "sources": [], "confidence_percent": 0} for day in dates], "confidence_percent": 0}
    evidence = {day: {"confirmed": set(), "away": set()} for day in dates}
    for series in history if isinstance(history, list) else []:
        if not series:
            continue
        entity_id = str(series[0].get("entity_id") or "")
        for point in series:
            try:
                observed = datetime.fromisoformat(str(point.get("last_changed") or point.get("last_updated") or "").replace("Z", "+00:00")).astimezone(rome).date()
            except ValueError:
                continue
            if observed not in evidence:
                continue
            value = str(point.get("state") or "").casefold()
            if entity_id in entities and value == "home":
                evidence[observed]["confirmed"].add(entity_id)
            elif entity_id in entities and value == "not_home":
                evidence[observed]["away"].add(entity_id)
            elif entity_id in camera_entities and any(alias in value for alias in aliases):
                evidence[observed]["confirmed"].add(entity_id)
    days = []
    for day in dates:
        confirmed, away = evidence[day]["confirmed"], evidence[day]["away"]
        status = "confirmed" if confirmed else "away" if away else "unknown"
        sources = sorted(confirmed or away)
        has_location_source = any(source.startswith(("person.", "device_tracker.")) for source in confirmed)
        has_camera_source = any(source.startswith("sensor.") for source in confirmed)
        confidence = 92 if has_location_source else 78 if has_camera_source else 58 if away else 0
        basis = "GPS/person presence" if has_location_source else "camera recognition" if has_camera_source else "away-state evidence" if away else "no retained evidence"
        days.append({"work_date": day.isoformat(), "status": status, "sources": sources, "confidence_percent": confidence, "confidence_basis": basis})
    confidence = round(sum(day["confidence_percent"] for day in days) / len(days)) if days else 0
    return {"available": True, "reason": None, "days": days, "confidence_percent": confidence, "note": "Presence confidence measures supporting evidence only; it does not approve hours. Missing or away states do not disprove reported work."}


@app.post("/api/v1/admin/timesheets/{record_id}/presence", dependencies=[Depends(authorize_admin)])
def check_timesheet_presence(record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not fetch_one("SELECT id FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id())):
        raise HTTPException(404, "Timesheet not found")
    return json_ready(_timesheet_presence(str(payload.get("worker") or ""), payload.get("entries") or []))


@app.post("/api/v1/admin/timesheets/{record_id}/approve", dependencies=[Depends(authorize_admin)])
def approve_timesheet(record_id: str, payload: dict[str, Any], request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    item = fetch_one("SELECT * FROM intake_items WHERE id=%s AND estate_id=%s AND review_status IN ('new','ready_for_review')", (record_id, estate_id()))
    if not item:
        raise HTTPException(404, "Pending timesheet not found")
    worker, raw_entries = str(payload.get("worker") or "").strip(), payload.get("entries") or []
    if not worker or not isinstance(raw_entries, list) or not raw_entries:
        raise HTTPException(422, "Enter the worker and at least one day or month line")
    expenses = _normalize_timesheet_expenses(payload.get("expenses") or [])
    rate = None if payload.get("hourly_rate_eur") in (None, "") else float(payload["hourly_rate_eur"])
    if rate is not None and rate < 0:
        raise HTTPException(422, "Hourly rate cannot be negative")
    entries = []
    for row in raw_entries:
        period_type = str(row.get("period_type") or "day").strip().casefold()
        if period_type not in {"day", "month"}:
            raise HTTPException(422, "Choose Day or Month total for every timesheet line")
        try:
            if period_type == "month":
                month_text = str(row.get("work_month") or row.get("month") or "")[:7]
                work_date = date.fromisoformat(f"{month_text}-01")
            else:
                month_text = None
                work_date = date.fromisoformat(str(row.get("work_date") or row.get("date")))
            hours = float(row.get("hours") if row.get("hours") is not None else row.get("regular_hours"))
        except (AttributeError, TypeError, ValueError) as error:
            raise HTTPException(422, "Every timesheet line needs a valid day or month and hours") from error
        maximum = 744 if period_type == "month" else 24
        if hours <= 0 or hours > maximum:
            raise HTTPException(422, f"{'Monthly' if period_type == 'month' else 'Daily'} hours must be greater than 0 and no more than {maximum}")
        entries.append({"period_type": period_type, "work_date": work_date, "work_month": month_text, "hours": hours, "notes": str(row.get("notes") or "").strip() or None})
    entry_keys = [(row["period_type"], row["work_month"] or row["work_date"].isoformat()) for row in entries]
    if len(set(entry_keys)) != len(entry_keys):
        raise HTTPException(422, "Combine duplicate day or month lines before approval")
    seasons = {year: season_for_year(year) for year in {row["work_date"].year for row in entries}}
    presence_rows = [{**row, "work_date": row["work_date"].isoformat()} for row in entries if row["period_type"] == "day"]
    presence = _timesheet_presence(worker, presence_rows)
    if any(row["period_type"] == "month" for row in entries):
        presence["monthly_note"] = "Monthly totals are retained as aggregate attendance; no unsupported daily presence is inferred."
    actor = request.headers.get("X-Remote-User-Name") or "api"
    worker_username = next(
        (username for username, display_name in worker_accounts(settings).items() if display_name.casefold() == worker.casefold()),
        None,
    )
    inserted, duplicates, expenses_inserted, expense_duplicates = [], [], [], []
    with transaction() as (_, cursor):
        for row in entries:
            if row["period_type"] == "month":
                cursor.execute(
                    "SELECT id,COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) hours FROM labor_entries "
                    "WHERE estate_id=%s AND YEAR(work_date)=%s AND MONTH(work_date)=%s AND LOWER(person_or_crew)=LOWER(%s) "
                    "AND work_category='monthly_total' ORDER BY id",
                    (estate_id(), row["work_date"].year, row["work_date"].month, worker),
                )
            else:
                cursor.execute(
                    "SELECT id,COALESCE(regular_hours,0)+COALESCE(overtime_hours,0) hours FROM labor_entries "
                    "WHERE estate_id=%s AND work_date=%s AND LOWER(person_or_crew)=LOWER(%s) AND COALESCE(work_category,'')<>'monthly_total' ORDER BY id",
                    (estate_id(), row["work_date"], worker),
                )
            matches = cursor.fetchall() or []
            exact = next((match for match in matches if abs(float(match.get("hours") or 0) - row["hours"]) < .001), None)
            if exact:
                duplicates.append({"period_type": row["period_type"], "work_date": row["work_date"].isoformat(), "work_month": row["work_month"], "hours": row["hours"], "existing_id": exact["id"]})
                continue
            period_key = row["work_month"] if row["period_type"] == "month" else row["work_date"].isoformat()
            labor_id, source_id = new_id(), f"TIMESHEET-{record_id[:8]}-{row['period_type'].upper()}-{period_key}"
            cost = round(row["hours"] * rate, 2) if rate is not None else None
            work_category = "monthly_total" if row["period_type"] == "month" else None
            shift_label = f"Monthly total {row['work_month']}" if row["period_type"] == "month" else None
            default_note = f"Monthly attendance total for {row['work_month']}; daily dates were not reported." if row["period_type"] == "month" else f"Approved from {item.get('source') or 'incoming'} timesheet {record_id}"
            cursor.execute(
                "INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,shift_label,person_or_crew,role,work_category,regular_hours,hourly_rate_eur,labor_cost_eur,approved_by,payment_status,payroll_scope,entry_source,notes,worker_username) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'Contractor',%s,%s,%s,%s,%s,'unpaid','contractor',%s,%s,%s)",
                (labor_id, estate_id(), seasons[row["work_date"].year], source_id, row["work_date"], shift_label, worker, work_category, row["hours"], rate, cost, actor, item.get("source") or "timesheet", row["notes"] or default_note, worker_username),
            )
            inserted.append({"id": labor_id, "period_type": row["period_type"], "work_date": row["work_date"].isoformat(), "work_month": row["work_month"], "hours": row["hours"]})
        for index, expense in enumerate(expenses, start=1):
            source_id = f"{record_id}:expense:{index}"
            cursor.execute("SELECT id FROM labor_entries WHERE estate_id=%s AND source_labor_id=%s LIMIT 1", (estate_id(), source_id))
            existing_expense = cursor.fetchone()
            if existing_expense:
                expense_duplicates.append({"id": existing_expense["id"], **expense})
                continue
            expense_id = new_id()
            expense_date = date.fromisoformat(expense["expense_date"])
            cursor.execute(
                "INSERT INTO labor_entries (id,estate_id,season_id,source_labor_id,work_date,person_or_crew,role,work_category,work_performed,regular_hours,overtime_hours,labor_cost_eur,other_cost_eur,expense_amount_eur,expense_category,expense_notes,approved_by,approval_status,payment_status,payroll_scope,entry_source,notes,worker_username) "
                "VALUES (%s,%s,%s,%s,%s,%s,'Contractor','reimbursable_expense',%s,0,0,0,%s,%s,%s,%s,%s,'approved','unpaid','contractor',%s,%s,%s)",
                (
                    expense_id, estate_id(), season_for_year(expense_date.year), source_id, expense_date, worker,
                    expense["description"], expense["amount_eur"], expense["amount_eur"], expense["category"],
                    expense["description"], actor, item.get("source") or "timesheet",
                    f"Approved reimbursement from timesheet {record_id}", worker_username,
                ),
            )
            expenses_inserted.append({"id": expense_id, **expense})
        review = {
            "person_or_crew": worker,
            "hourly_rate_eur": rate,
            "timesheet_entries": [{**row, "work_date": row["work_date"].isoformat()} for row in entries],
            "reimbursable_expenses": expenses,
        }
        cursor.execute(
            "UPDATE intake_items SET extracted_data=%s,review_status='approved',review_reason=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s",
            (json.dumps(review, default=str), f"Timesheet approved: {len(inserted)} work rows and {len(expenses_inserted)} reimbursements added", actor, record_id, estate_id()),
        )
        audit(cursor, "approve", "timesheet_review", record_id, {
            "worker": worker, "inserted": inserted, "duplicates": duplicates,
            "expenses_inserted": expenses_inserted, "expense_duplicates": expense_duplicates,
            "presence_evidence": presence,
        }, actor)
    labor_total = None if rate is None else round(sum(row["hours"] for row in entries) * rate, 2)
    reimbursement_total = round(sum(row["amount_eur"] for row in expenses_inserted), 2)
    return {
        "approved": True, "inserted": inserted, "duplicates": duplicates,
        "expenses_inserted": expenses_inserted, "expense_duplicates": expense_duplicates,
        "labor_total_eur": labor_total,
        "reimbursement_total_eur": reimbursement_total,
        "total_payable_eur": None if labor_total is None else round(labor_total + reimbursement_total, 2),
        "presence_evidence": presence, "total_hours": sum(row["hours"] for row in entries),
    }


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


@app.put("/api/v1/admin/ai-cost", dependencies=[Depends(authorize_admin)])
def update_ai_cost(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        return save_ai_cost_settings(
            float(payload.get("monthly_budget_usd", 25)), float(payload.get("warning_percent", 80)),
            request.headers.get("X-Remote-User-Name") or "api",
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Enter a valid monthly budget and warning percentage") from error


@app.put("/api/v1/admin/ai-profile", dependencies=[Depends(authorize_admin)])
def update_ai_profile(payload: dict[str, Any], request: Request) -> dict[str, str]:
    try:
        return save_ai_request_profile(
            str(payload.get("effort") or ""), str(payload.get("speed") or ""),
            request.headers.get("X-Remote-User-Name") or "api",
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/admin/ai-credit-check", dependencies=[Depends(authorize_admin)])
def recheck_ai_credit() -> dict[str, Any]:
    return check_openai_service()


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


ATTACHMENT_ENTITIES = {
    "activity": "work_activities",
    "harvest": "harvest_lots",
    "cellar_operation": "cellar_operations",
    "cellar_lot": "wine_lots",
    "fermentation": "fermentation_observations",
    "equipment_event": "equipment_service_events",
    "maturity_sample": "maturity_samples",
    "scouting": "scouting_observations",
    "damage_assessment": "vineyard_damage_assessments",
    "phenology": "phenology_observations",
    "treatment": "spray_applications",
    "labor": "labor_entries",
    "olive": "olive_records",
    "issue": "issues_decisions",
    "lab_sample": "lab_samples",
    "winemaking_plan": "winemaking_cost_plans",
}


@app.post("/api/v1/attachments/{entity_type}/{entity_id}", status_code=201, dependencies=[Depends(authorize_write)])
async def add_entity_attachment(
    entity_type: str,
    entity_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    caption: str = Form(""),
) -> dict[str, Any]:
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
    analysis_queued = entity_type in {"scouting", "phenology", "maturity_sample"} and media_type.startswith("image/")
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (attachment_id, estate_id(), entity_type, entity_id, safe_name, str(stored), media_type, digest, caption or None, request.headers.get("X-Remote-User-Name") or "api"),
        )
        if analysis_queued:
            cursor.execute(
                "INSERT INTO observation_photo_analyses "
                "(id,estate_id,attachment_id,entity_type,entity_id,status) VALUES (%s,%s,%s,%s,%s,'queued')",
                (new_id(), estate_id(), attachment_id, entity_type, entity_id),
            )
        audit(cursor, "attach", entity_type, entity_id, {"attachment_id": attachment_id, "filename": safe_name})
    if analysis_queued:
        background_tasks.add_task(analyze_observation_attachment, attachment_id)
    return {
        "id": attachment_id,
        "entity_id": entity_id,
        "analysis_status": "queued" if analysis_queued else None,
    }


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
        "harvest": historical["harvest"],
        "weather": historical["weather"],
        "historical_summary": historical["totals"] if historical["has_summary"] else None,
        "alerts": fetch_all("SELECT id,alert_type,severity,title,message,source_id,status,triggered_at FROM alerts WHERE estate_id=%s AND status='open' ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC", (estate_id(),)) if year == current_year else [],
    })


@app.get("/api/display-data", dependencies=[Depends(authorize)])
def ingress_display_data() -> dict[str, Any]:
    return display_payload()


@app.get("/api/v1/grapes/dashboard", dependencies=[Depends(authorize)])
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
        calibration = _event_payload(forecast.get("calibration_evidence"))
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
        "SUM(h.weight_kg) harvested_kg,COUNT(DISTINCT h.id) lot_count "
        "FROM vineyard_blocks b LEFT JOIN block_varieties bv ON bv.block_id=b.id LEFT JOIN grape_varieties v ON v.id=bv.variety_id "
        "LEFT JOIN harvest_lots h ON h.block_id=b.id AND h.season_id=%s WHERE b.estate_id=%s AND b.active=1 "
        "GROUP BY b.id,b.code,b.name,b.area_ha ORDER BY b.code",
        (season_id, estate_id()),
    )
    harvest_lots = fetch_all(
        "SELECT h.id,h.harvested_at,h.weight_kg,h.crate_count,h.avg_crate_kg,h.destination,h.brix,h.babo,h.ph,h.ta_g_l,h.condition_grade,h.notes,v.name variety_name,b.code block_code,"
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


@app.get("/api/v1/cellar/dashboard", dependencies=[Depends(authorize)])
def cellar_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=FIRST_ESTATE_VINTAGE)) -> dict[str, Any]:
    settings = get_settings()
    if demo_enabled(settings):
        result = demo_cellar(settings, year)
        result["history"] = fetch_all(
            "SELECT s.vintage_year,w.lot_count,w.volume_l,w.fruit_kg,co.operation_count,co.latest_operation_at "
            "FROM seasons s LEFT JOIN (SELECT season_id,COUNT(*) lot_count,SUM(COALESCE(volume_l,initial_l)) volume_l,SUM(fruit_kg) fruit_kg FROM wine_lots GROUP BY season_id) w ON w.season_id=s.id "
            "LEFT JOIN (SELECT season_id,COUNT(*) operation_count,MAX(operation_at) latest_operation_at FROM cellar_operations GROUP BY season_id) co ON co.season_id=s.id "
            "WHERE s.estate_id=%s AND s.vintage_year>=%s ORDER BY s.vintage_year",
            (estate_id(), FIRST_ESTATE_VINTAGE),
        )
        return json_ready(result)
    return _live_cellar_dashboard(year, settings)


def _live_cellar_dashboard(year: int, settings: Settings) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    season_id = season.get("id", "")
    tanks = fetch_all(
        "SELECT c.id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.sensor_entity_id,c.status,"
        "w.id wine_lot_id,w.code lot_code,w.name lot_name,COALESCE(w.stage,cp.manual_stage) stage,COALESCE(w.volume_l,cp.manual_volume_l) volume_l,COALESCE(w.variety_summary,cp.manual_contents) variety_summary,cp.wine_color,w.started_at,"
        "COALESCE((SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_temp_c) temp_c,"
        "COALESCE((SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_density_sg) density_sg,"
        "COALESCE((SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_brix) brix,"
        "COALESCE((SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_ph) ph,"
        "COALESCE((SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_reading_at) reading_at,"
        "(SELECT f.next_check_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) next_check_at,"
        "COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status,"
        "cp.last_maintenance_at,cp.next_maintenance_at,cp.maintenance_notes "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.id=("
        "SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.season_id=%s "
        "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1) "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (season_id, estate_id()),
    )
    for tank in tanks:
        capacity = float(tank.get("capacity_l") or 0)
        volume = float(tank.get("volume_l") or 0)
        tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
        tank["source"] = "Manual record"
    configured_keys = live_sensor_tank_keys(settings)
    for tank in tanks:
        tank["sensor_configured"] = bool(
            tank.get("sensor_entity_id")
            or str(tank.get("code") or "").casefold() in configured_keys
            or str(tank.get("name") or "").casefold() in configured_keys
        )
        if tank.get("reading_mode") == "sensor":
            tank["sensor_status"] = "configured" if tank["sensor_configured"] else "not_configured"
    try:
        sensor_tanks = [tank for tank in tanks if tank.get("reading_mode") == "sensor" and tank.get("sensor_configured")]
        apply_live_sensor_readings(sensor_tanks, settings, home_assistant_state_map(live_sensor_entity_ids(settings)))
        for tank in sensor_tanks:
            tank["sensor_status"] = "fault" if tank.get("sensor_issues") else "live"
    except Exception:
        for tank in tanks:
            if tank.get("reading_mode") == "sensor" and tank.get("sensor_configured"):
                tank["sensor_status"] = "fault"
    guard_alerts = evaluate_cellar_tanks(tanks, settings)
    processes = fetch_all(
        "SELECT f.id,f.observed_at,f.vessel_name,f.stage,f.temp_c,f.density_sg,f.brix,f.ph,f.cap_management,f.addition_action,f.sensory_observation,f.owner_text,f.next_check_at,f.status,w.code lot_code,w.name lot_name "
        "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id WHERE f.estate_id=%s "
        "AND (w.season_id=%s OR w.season_id IS NULL) ORDER BY COALESCE(f.next_check_at,f.observed_at) DESC LIMIT 30",
        (estate_id(), season_id),
    )
    if year != date.today().year:
        tanks = [tank for tank in tanks if tank.get("wine_lot_id")]
        processes = [process for process in processes if process.get("lot_code")]
        guard_alerts = evaluate_cellar_tanks(tanks, settings)
    history = fetch_all(
        "SELECT s.vintage_year,w.lot_count,w.volume_l,w.fruit_kg,co.operation_count,co.latest_operation_at "
        "FROM seasons s LEFT JOIN (SELECT season_id,COUNT(*) lot_count,SUM(COALESCE(volume_l,initial_l)) volume_l,SUM(fruit_kg) fruit_kg FROM wine_lots GROUP BY season_id) w ON w.season_id=s.id "
        "LEFT JOIN (SELECT season_id,COUNT(*) operation_count,MAX(operation_at) latest_operation_at FROM cellar_operations GROUP BY season_id) co ON co.season_id=s.id "
        "WHERE s.estate_id=%s AND s.vintage_year>=%s ORDER BY s.vintage_year",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
    all_vintage_summaries = all_vintage_rows()
    history = merge_cellar_history(history, all_vintage_summaries)
    selected_rows = [row for row in all_vintage_summaries if int(row["vintage_year"]) == year]
    return json_ready({"year": year, "demo": False, "tanks": tanks, "processes": processes, "guardrails": cellar_guardrails(settings), "guard_alerts": guard_alerts, "history": history, "historical_summary": historical_cellar_summary(year, selected_rows)})


def _cellar_container(container_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT c.*,COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status "
        "FROM cellar_containers c LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.id=%s AND c.estate_id=%s AND c.active=1",
        (container_id, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Cellar tank not found")
    return row


def _ensure_current_manual_tanks(settings: Settings) -> None:
    raw = str(runtime_option("cellar_demo_tanks", settings.cellar_demo_tanks) or settings.cellar_demo_tanks)
    definitions = manual_tank_definitions(raw)
    with transaction() as (_, cursor):
        for index, parts in enumerate(definitions, start=1):
            name = parts[0] if parts and parts[0] else f"Tank {index}"
            try:
                capacity = max(1.0, float(parts[1]))
            except (IndexError, TypeError, ValueError):
                capacity = 750.0
            try:
                level = min(100.0, max(0.0, float(parts[4])))
            except (IndexError, TypeError, ValueError):
                level = 0.0
            stage = parts[3] if len(parts) > 3 and parts[3] else None
            contents = parts[2] if len(parts) > 2 and parts[2] else None
            def configured_number(position: int) -> float | None:
                try:
                    return float(parts[position]) if parts[position] else None
                except (IndexError, TypeError, ValueError):
                    return None
            temp = configured_number(5)
            density = configured_number(6)
            brix = configured_number(7)
            ph = configured_number(8)
            container_type = "barrel" if str(stage or "").casefold() == "aging" else "tank"
            cursor.execute("SELECT id FROM cellar_containers WHERE estate_id=%s AND (name=%s OR code=%s) LIMIT 1", (estate_id(), name, f"T-{index:02d}"))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "INSERT IGNORE INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) "
                    "VALUES (%s,%s,%s,'manual','not_configured',%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6),'startup-import')",
                    (new_id(), estate_id(), existing["id"], contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph),
                )
                cursor.execute(
                    "UPDATE cellar_control_profiles SET manual_contents=COALESCE(manual_contents,%s),manual_volume_l=COALESCE(manual_volume_l,%s),manual_stage=COALESCE(manual_stage,%s),"
                    "manual_temp_c=COALESCE(manual_temp_c,%s),manual_density_sg=COALESCE(manual_density_sg,%s),manual_brix=COALESCE(manual_brix,%s),manual_ph=COALESCE(manual_ph,%s),"
                    "manual_reading_at=COALESCE(manual_reading_at,NOW(6)),manual_updated_at=COALESCE(manual_updated_at,NOW(6)) WHERE estate_id=%s AND container_id=%s",
                    (contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph, estate_id(), existing["id"]),
                )
                continue
            container_id = new_id()
            cursor.execute(
                "INSERT INTO cellar_containers (id,estate_id,code,name,container_type,capacity_l,status,notes,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (container_id, estate_id(), f"T-{index:02d}", name, container_type, capacity, "in_use" if level else "empty", "Imported from the prior configured tank list"),
            )
            cursor.execute(
                "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) VALUES (%s,%s,%s,'manual','not_configured',%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6),'startup-import')",
                (new_id(), estate_id(), container_id, contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph),
            )
            audit(cursor, "import", "cellar_container", container_id, {"source": "configured tank list", "reading_mode": "manual"}, "startup")

        cursor.execute(
            "SELECT id FROM cellar_containers WHERE estate_id=%s AND active=1",
            (estate_id(),),
        )
        for tank in cursor.fetchall():
            ensure_tank_label(cursor, tank["id"])


@app.post("/api/v1/agronomy/tanks", dependencies=[Depends(authorize_write)])
def create_manual_tank(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload.get("code") or "").strip()
    name = str(payload.get("name") or "").strip()
    container_type = str(payload.get("container_type") or "tank").strip().casefold()
    if not code or not name:
        raise HTTPException(422, "Enter a tank code and name")
    if container_type not in {"tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other"}:
        raise HTTPException(422, "Choose a supported container type")
    capacity = float(payload.get("capacity_l") or 0)
    if not 0 < capacity <= 1000000:
        raise HTTPException(422, "Enter a valid capacity in liters")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    container_id = new_id()
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO cellar_containers (id,estate_id,code,name,container_type,material,capacity_l,location,status,notes,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'empty',%s,1)",
                (container_id, estate_id(), code, name, container_type, str(payload.get("material") or "").strip() or None, capacity, str(payload.get("location") or "").strip() or None, str(payload.get("notes") or "").strip() or None),
            )
            cursor.execute("INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,updated_by) VALUES (%s,%s,%s,'manual','not_configured',%s)", (new_id(), estate_id(), container_id, actor))
            ensure_tank_label(cursor, container_id)
            audit(cursor, "create", "cellar_container", container_id, {"code": code, "name": name, "capacity_l": capacity, "reading_mode": "manual"}, actor)
    except IntegrityError as exc:
        raise HTTPException(409, "A tank with that code already exists") from exc
    return {"saved": True, "id": container_id, "reading_mode": "manual"}


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
        "SELECT h.id,h.harvested_at,h.weight_kg,h.crate_count,h.destination,v.name variety_name,b.code block_code,"
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
            "option": "cellar_live_sensors",
            "configured_tanks": configured,
            "note": "Sensor entity IDs are configured only in the protected app configuration. Manual readings are managed here.",
        },
    })


@app.put("/api/v1/agronomy/tanks/{container_id}/legal-label", dependencies=[Depends(authorize_write)])
def update_tank_legal_label(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    require_discipline_approval(request, "enology")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = save_legal_profile(container_id, payload, actor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "update", "tank_legal_label", container_id, {"wine_lot_id": result["wine_lot_id"]}, actor)
    return result


@app.post("/api/v1/agronomy/label-kiosks", dependencies=[Depends(authorize_write)])
def add_tank_label_kiosk(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = create_kiosk(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "create", "cellar_label_kiosk", result["id"], {"name": payload.get("name"), "container_id": payload.get("container_id")}, actor)
    return result


@app.put("/api/v1/agronomy/label-kiosks/{kiosk_id}", dependencies=[Depends(authorize_write)])
def edit_tank_label_kiosk(kiosk_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = update_kiosk(kiosk_id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "update", "cellar_label_kiosk", kiosk_id, {"name": payload.get("name"), "container_id": payload.get("container_id")}, actor)
    return result


@app.get("/api/v1/agronomy/label-kiosks/{kiosk_id}/qr", dependencies=[Depends(authorize_write)])
def tank_label_kiosk_qr(kiosk_id: str) -> Response:
    kiosk = fetch_one(
        "SELECT public_token FROM cellar_label_kiosks WHERE id=%s AND estate_id=%s AND active=1",
        (kiosk_id, estate_id()),
    )
    if not kiosk:
        raise HTTPException(404, "Tablet not found")
    origin = cellar_label_origin(get_settings())
    return url_qr(f"{origin}/kiosk/{kiosk['public_token']}")


@app.delete("/api/v1/agronomy/label-kiosks/{kiosk_id}", dependencies=[Depends(authorize_write)])
def delete_tank_label_kiosk(kiosk_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = retire_kiosk(kiosk_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "retire", "cellar_label_kiosk", kiosk_id, {}, actor)
    return result


@app.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/approve", dependencies=[Depends(authorize_write)])
def approve_tank_label_enrollment(enrollment_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = approve_device_enrollment(
            enrollment_id,
            payload,
            actor,
            get_settings().cellar_ipad_dashboard_url,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "approve", "cellar_label_enrollment", enrollment_id, {
            "device_role": result.get("device_role"),
            "kiosk_id": result.get("id"),
            "container_id": payload.get("container_id"),
        }, actor)
    return result


@app.delete("/api/v1/agronomy/label-enrollments/{enrollment_id}", dependencies=[Depends(authorize_write)])
def reject_tank_label_enrollment(enrollment_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = reject_kiosk_enrollment(enrollment_id, actor)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "reject", "cellar_label_enrollment", enrollment_id, {}, actor)
    return result


@app.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/reprovision", dependencies=[Depends(authorize_write)])
def reprovision_tank_label_device(enrollment_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = reprovision_device(enrollment_id, actor)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "reprovision", "cellar_label_enrollment", enrollment_id, {
            "expires_in_seconds": result["expires_in_seconds"],
        }, actor)
    return result


@app.post("/api/v1/agronomy/tanks/{container_id}/lot-transfer", dependencies=[Depends(authorize_write)])
def save_harvest_lot_transfer(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    year = int(payload.get("year") or date.today().year)
    season = season_for_year(year)
    harvest_lot_id = str(payload.get("harvest_lot_id") or "").strip()
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip()
    harvest_lot = fetch_one("SELECT * FROM harvest_lots WHERE id=%s AND estate_id=%s AND season_id=%s", (harvest_lot_id, estate_id(), season))
    wine_lot = fetch_one("SELECT * FROM wine_lots WHERE id=%s AND estate_id=%s AND season_id=%s", (wine_lot_id, estate_id(), season))
    if not harvest_lot or not wine_lot:
        raise HTTPException(422, "Choose a harvest lot and cellar lot from this vintage")
    parcel_rows = fetch_all(
        "SELECT p.id,p.municipality,p.cadastral_sheet,p.parcel_number FROM harvest_lot_parcels hp "
        "JOIN cadastral_parcels p ON p.id=hp.parcel_id AND p.estate_id=hp.estate_id "
        "WHERE hp.estate_id=%s AND hp.harvest_lot_id=%s ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number",
        (estate_id(), harvest_lot_id),
    )

    def optional_number(key: str) -> float | None:
        raw = payload.get(key)
        if raw in (None, ""):
            return None
        value = float(raw)
        if value < 0:
            raise HTTPException(422, f"{key} cannot be negative")
        return value
    fruit_kg = optional_number("fruit_kg")
    must_l = optional_number("must_l")
    transferred_at = payload.get("transferred_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    actor = request.headers.get("X-Remote-User-Name") or "api"
    trace_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cellar_lot_trace_records (id,estate_id,season_id,harvest_lot_id,wine_lot_id,container_id,transferred_at,fruit_kg,must_l,notes,recorded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (trace_id, estate_id(), season, harvest_lot_id, wine_lot_id, container_id, transferred_at, fruit_kg, must_l, str(payload.get("notes") or "").strip() or None, actor),
        )
        cursor.execute(
            "UPDATE wine_lots SET current_container_id=%s,harvest_lot_reference=%s,"
            "fruit_kg=CASE WHEN %s IS NULL THEN fruit_kg ELSE COALESCE(fruit_kg,0)+%s END,"
            "initial_l=CASE WHEN %s IS NULL THEN initial_l ELSE COALESCE(initial_l,0)+%s END,"
            "volume_l=CASE WHEN %s IS NULL THEN volume_l ELSE COALESCE(volume_l,0)+%s END "
            "WHERE id=%s AND estate_id=%s",
            (container_id, harvest_lot_id, fruit_kg, fruit_kg, must_l, must_l, must_l, must_l, wine_lot_id, estate_id()),
        )
        cursor.execute("UPDATE cellar_containers SET status='in_use' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "transfer", "harvest_lot_to_tank", trace_id, {"harvest_lot_id": harvest_lot_id, "wine_lot_id": wine_lot_id, "container_id": container_id, "fruit_kg": fruit_kg, "must_l": must_l, "tank": tank.get("code"), "parcel_ids": [row["id"] for row in parcel_rows]}, actor)
    return {"saved": True, "id": trace_id, "legal_parcels_carried_to_tank": len(parcel_rows)}


@app.put("/api/v1/agronomy/tanks/{container_id}/mode", dependencies=[Depends(authorize_write)])
def set_agronomy_tank_mode(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    mode = str(payload.get("reading_mode") or "").strip().casefold()
    if mode not in {"manual", "sensor"}:
        raise HTTPException(422, "Choose manual or sensor mode")
    container_type = str(payload.get("container_type") or tank.get("container_type") or "tank").strip().casefold()
    if container_type not in {"tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other"}:
        raise HTTPException(422, "Choose a supported vessel type")
    name = str(payload.get("name") or tank.get("name") or tank.get("code") or "").strip()
    if not name or len(name) > 190:
        raise HTTPException(422, "Tank name is required and must be 190 characters or fewer")
    settings = get_settings()
    keys = live_sensor_tank_keys(settings)
    configured = bool(tank.get("sensor_entity_id") or str(tank.get("code") or "").casefold() in keys or str(tank.get("name") or "").casefold() in keys)
    if mode == "sensor" and not configured:
        raise HTTPException(422, "Configure this tank under cellar_live_sensors in Home Assistant App Configuration before enabling sensor mode")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    status = "configured" if mode == "sensor" else ("configured" if configured else "not_configured")
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_containers SET name=%s,container_type=%s WHERE id=%s AND estate_id=%s",
            (name, container_type, container_id, estate_id()),
        )
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,updated_by) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE reading_mode=VALUES(reading_mode),sensor_status=VALUES(sensor_status),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), container_id, mode, status, actor),
        )
        audit(cursor, "set_reading_mode", "cellar_container", container_id, {"reading_mode": mode, "container_type": container_type, "name": name, "sensor_configured": configured}, actor)
    return {"saved": True, "container_id": container_id, "name": name, "reading_mode": mode, "container_type": container_type, "sensor_status": status}


@app.post("/api/v1/agronomy/tanks/{container_id}/reading", dependencies=[Depends(authorize_write)])
def save_manual_tank_reading(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    if tank.get("reading_mode") == "sensor":
        raise HTTPException(409, "This tank is in sensor mode. Switch it to manual mode before entering a manual reading")
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip() or None
    lot = None
    if wine_lot_id:
        lot = fetch_one("SELECT w.* FROM wine_lots w JOIN seasons s ON s.id=w.season_id WHERE w.id=%s AND w.estate_id=%s AND s.vintage_year=%s", (wine_lot_id, estate_id(), int(payload.get("year") or date.today().year)))
        if not lot:
            raise HTTPException(422, "Choose a wine lot from this vintage")
    def number(key: str, minimum: float, maximum: float) -> float | None:
        raw = payload.get(key)
        if raw in (None, ""):
            return None
        value = float(raw)
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{key} must be between {minimum:g} and {maximum:g}")
        return value
    volume = number("volume_l", 0, max(float(tank.get("capacity_l") or 100000) * 1.05, 1))
    temp = number("temp_c", -20, 60)
    density = number("density_sg", 0.8, 1.5)
    brix = number("brix", -5, 50)
    ph = number("ph", 0, 14)
    stage = str(payload.get("stage") or (lot or {}).get("stage") or "").strip().casefold() or None
    stage = {"fermenting": "fermentation"}.get(stage, stage)
    if stage and stage not in CELLAR_STAGES:
        raise HTTPException(422, "Choose a supported cellar stage")
    contents = str(payload.get("contents") or (lot or {}).get("variety_summary") or "").strip() or None
    wine_color = str(payload.get("wine_color") or "").strip().casefold() or None
    if wine_color and wine_color not in WINE_COLORS:
        raise HTTPException(422, "Choose red, white or rosé")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    observed = payload.get("observed_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    next_check = str(payload.get("next_check_at") or "").strip() or None
    if next_check and len(next_check) == 10:
        next_check = f"{next_check} 09:00:00"
    reading_id = new_id()
    with transaction() as (_, cursor):
        if lot:
            lot_stage = stage if stage in WINE_LOT_STAGES else None
            cursor.execute("UPDATE wine_lots SET current_container_id=%s,volume_l=COALESCE(%s,volume_l),stage=COALESCE(%s,stage) WHERE id=%s AND estate_id=%s", (container_id, volume, lot_stage, wine_lot_id, estate_id()))
            cursor.execute("UPDATE cellar_containers SET status='in_use' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,wine_color,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) "
            "VALUES (%s,%s,%s,'manual',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),%s) ON DUPLICATE KEY UPDATE manual_contents=VALUES(manual_contents),wine_color=VALUES(wine_color),manual_volume_l=VALUES(manual_volume_l),manual_stage=VALUES(manual_stage),manual_temp_c=VALUES(manual_temp_c),manual_density_sg=VALUES(manual_density_sg),manual_brix=VALUES(manual_brix),manual_ph=VALUES(manual_ph),manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), container_id, tank.get("sensor_status") or "not_configured", contents, wine_color, volume, stage, temp, density, brix, ph, observed, actor),
        )
        cursor.execute(
            "INSERT INTO fermentation_observations (id,estate_id,wine_lot_id,observed_at,vessel_name,stage,temp_c,density_sg,brix,ph,sensory_observation,owner_text,next_check_at,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual')",
            (reading_id, estate_id(), wine_lot_id, observed, tank.get("name") or tank.get("code"), stage, temp, density, brix, ph, str(payload.get("notes") or "").strip() or None, actor, next_check),
        )
        audit(cursor, "manual_reading", "cellar_container", container_id, {"reading_id": reading_id, "wine_lot_id": wine_lot_id, "volume_l": volume, "stage": stage, "wine_color": wine_color}, actor)
    return {"saved": True, "id": reading_id, "container_id": container_id, "reading_mode": "manual"}


@app.delete("/api/v1/agronomy/tanks/{container_id}", dependencies=[Depends(authorize_write)])
def delete_manual_tank(container_id: str, request: Request) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    if tank.get("reading_mode") != "manual":
        raise HTTPException(409, "Switch this tank to manual mode before removing it")
    assigned = fetch_one(
        "SELECT id,code,name FROM wine_lots WHERE estate_id=%s AND current_container_id=%s LIMIT 1",
        (estate_id(), container_id),
    )
    if assigned:
        raise HTTPException(409, f"Move wine lot {assigned.get('code') or assigned.get('name')} out of this tank before removing it")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("UPDATE cellar_containers SET active=0,status='retired' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        cursor.execute("UPDATE cellar_tank_labels SET active=0,retired_at=NOW(6) WHERE container_id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "retire", "cellar_container", container_id, {"code": tank.get("code"), "reading_mode": "manual"}, actor)
    return {"saved": True, "container_id": container_id, "active": False, "status": "retired"}


@app.post("/api/v1/agronomy/tanks/{container_id}/maintenance", dependencies=[Depends(authorize_write)])
def save_tank_maintenance(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    status = str(payload.get("status") or "completed").casefold()
    if status not in {"planned", "in_progress", "completed"}:
        raise HTTPException(422, "Choose planned, in progress or completed")
    maintenance_type = str(payload.get("maintenance_type") or "").strip()
    if not maintenance_type:
        raise HTTPException(422, "Enter the maintenance type")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    record_id = new_id()
    occurred = payload.get("maintenance_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cellar_maintenance_records (id,estate_id,container_id,maintenance_at,maintenance_type,status,performed_by,next_due_at,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (record_id, estate_id(), container_id, occurred, maintenance_type, status, actor, payload.get("next_due_at") or None, str(payload.get("notes") or "").strip() or None),
        )
        sensor_status = "maintenance" if status == "in_progress" else tank.get("sensor_status")
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,last_maintenance_at,next_maintenance_at,maintenance_notes,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE sensor_status=VALUES(sensor_status),last_maintenance_at=VALUES(last_maintenance_at),next_maintenance_at=VALUES(next_maintenance_at),maintenance_notes=VALUES(maintenance_notes),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), container_id, tank.get("reading_mode") or "manual", sensor_status, occurred, payload.get("next_due_at") or None, str(payload.get("notes") or "").strip() or None, actor),
        )
        if status == "in_progress":
            cursor.execute("UPDATE cellar_containers SET status='maintenance' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "maintenance", "cellar_container", container_id, {"record_id": record_id, "type": maintenance_type, "status": status}, actor)
    return {"saved": True, "id": record_id}


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
        "(SELECT SUM(h.weight_kg) FROM harvest_lots h WHERE h.block_id=b.id AND h.season_id=%s) harvested_kg "
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


@app.get("/api/v1/cistern/snapshot", dependencies=[Depends(authorize)])
def cistern_snapshot() -> Response:
    if not CISTERN_SNAPSHOT_PATH.is_file():
        raise HTTPException(status_code=404, detail="No cistern camera finding has been captured yet")
    media_type = "image/jpeg"
    try:
        media_type = str(json.loads(CISTERN_SNAPSHOT_PATH.with_suffix(".json").read_text(encoding="utf-8")).get("media_type") or media_type)
    except (OSError, ValueError, TypeError):
        pass
    return FileResponse(CISTERN_SNAPSHOT_PATH, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


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
    return _finance_dashboard_payload(year, payroll_summary)


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


@app.post("/api/v1/harvest", status_code=201, dependencies=[Depends(authorize_write)])
def create_harvest(payload: HarvestCreate, year: int = Query(default_factory=lambda: date.today().year)) -> dict[str, Any]:
    record_id, season_id = new_id(), season_for_year(year)
    values = payload.model_dump()
    parcel_ids = values.pop("parcel_ids", [])
    avg_crate = values["weight_kg"] / values["crate_count"] if values["weight_kg"] is not None and values["crate_count"] else None
    with transaction() as (_, cursor):
        if parcel_ids:
            placeholders = ",".join(["%s"] * len(parcel_ids))
            cursor.execute(
                f"SELECT id FROM cadastral_parcels WHERE estate_id=%s AND id IN ({placeholders})",
                (estate_id(), *parcel_ids),
            )
            found = {str(row["id"]) for row in cursor.fetchall()}
            if found != set(parcel_ids):
                raise HTTPException(422, "Choose only legal parcels belonging to Baiamonte")
        cursor.execute("INSERT INTO harvest_lots (id,estate_id,season_id,lot_code,block_id,variety_id,harvested_at,planned_date,planned_kg,gross_kg,tare_kg,weight_kg,crate_count,avg_crate_kg,fruit_temp_c,destination,brix,babo,ph,ta_g_l,condition_grade,status,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id, estate_id(), season_id, values["lot_code"], values["block_id"], values["variety_id"], values["harvested_at"], values["planned_date"], values["planned_kg"], values["gross_kg"], values["tare_kg"], values["weight_kg"], values["crate_count"], avg_crate, values["fruit_temp_c"], values["destination"], values["brix"], values["babo"], values["ph"], values["ta_g_l"], values["condition_grade"], values["status"], values["notes"]))
        for parcel_id in parcel_ids:
            cursor.execute(
                "INSERT INTO harvest_lot_parcels (id,estate_id,harvest_lot_id,parcel_id) VALUES (%s,%s,%s,%s)",
                (new_id(), estate_id(), record_id, parcel_id),
            )
        audit(cursor, "create", "harvest_lot", record_id, {**values, "parcel_ids": parcel_ids})
    request_harvest_refresh("harvest_lot", record_id, "Actual harvest evidence saved")
    return {"id": record_id, "prediction_refresh": "queued", "parcel_count": len(parcel_ids)}


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
    return {"saved": True, "result_id": result_id, "prediction_refresh": "queued" if sample.get("sample_type") == "grape" else "not_applicable"}


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
        audit(cursor,"review","lab_sample",sample_id,payload)
    sample_type = (fetch_one("SELECT sample_type FROM lab_samples WHERE id=%s", (sample_id,)) or {}).get("sample_type")
    if sample_type == "grape":
        request_harvest_refresh("lab_review", sample_id, "Grape laboratory review updated")
    return {"saved":True,"sample_id":sample_id,"prediction_refresh":"queued" if sample_type == "grape" else "not_applicable"}


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
    return json_ready({"saved": True, "treatment": saved, "inventory_sync": inventory_sync, "completed_task_ids": completed_task_ids, "google_sync": google_sync})


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
    pressure = [] if crop_scope == "olives" else fetch_all(
        "SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2') ORDER BY risk_score DESC",
        (estate_id(), estate_id()),
    )
    pressure_months = [] if crop_scope == "olives" else fetch_all(
        "SELECT disease_code,MAX(disease_name) disease_name,YEAR(assessment_date) assessment_year,MONTH(assessment_date) month_number,"
        "AVG(risk_score) average_score,MAX(risk_score) peak_score,COUNT(*) assessment_count "
        "FROM disease_pressure_assessments WHERE estate_id=%s AND YEAR(assessment_date)>=%s AND model_version<>'evidence-screen-v2' GROUP BY disease_code,YEAR(assessment_date),MONTH(assessment_date) "
        "ORDER BY disease_code,assessment_year,month_number",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
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


@app.get("/api/v1/disease-pressure", dependencies=[Depends(authorize)])
def disease_pressure() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT * FROM disease_pressure_assessments WHERE estate_id=%s AND model_version<>'evidence-screen-v2' AND assessment_date>=CURDATE()-INTERVAL 14 DAY ORDER BY assessment_date DESC,risk_score DESC", (estate_id(),)))


@app.patch("/api/v1/disease-pressure/{assessment_id}/review", dependencies=[Depends(authorize_write)])
def review_disease_pressure(assessment_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = payload.get("agronomist_status")
    if status not in {"approved", "modified", "rejected", "not_required"}:
        raise HTTPException(422, "Choose an agronomist review status")
    require_discipline_approval(request, "agronomy")
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE disease_pressure_assessments SET agronomist_status=%s,agronomist_name=%s,agronomist_notes=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, request.headers.get("X-Remote-User-Name") or "api", payload.get("agronomist_notes"), assessment_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Assessment not found")
    return {"saved": True}


@app.get("/api/v1/alerts", dependencies=[Depends(authorize)])
def list_alerts(status: str = "open") -> list[dict[str, Any]]:
    if status in {"open", "all"}:
        try:
            _reconcile_answered_whatsapp_notices()
        except Exception:
            logger.exception("Alert inbox reconciliation failed; returning stored alerts")
    return json_ready(fetch_all("SELECT * FROM alerts WHERE estate_id=%s AND (%s='all' OR status=%s) ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC LIMIT 250", (estate_id(), status, status)))


@app.patch("/api/v1/alerts/{alert_id}", dependencies=[Depends(authorize_write)])
def update_alert(alert_id: str, payload: dict[str, Any]) -> dict[str, bool]:
    status = payload.get("status")
    if not valid_alert_transition(status):
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
    "ai_service": "AI service & API quota",
    "power_recovery": "Power restored",
    "cistern": "Cistern water level",
    "cellar_temperature": "Cellar temperature",
    "cellar_level": "Tank fill level",
    "cellar_chemistry": "Cellar density & pH",
    "cellar_sensor": "Tank monitor connection",
    "cellar_checks": "Overdue cellar checks",
    "etna": "Mount Etna activity",
    "mail": "Incoming email",
    "inbox": "Important messages",
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
        row = saved.get(alert_type) or alert_preference(alert_type)
        preferences.append({**row, "label": label})
    template_catalog = whatsapp_templates()
    operational_templates = []
    for template in template_catalog.get("templates") or []:
        if str(template.get("status") or "").upper() != "APPROVED":
            continue
        body = next((component for component in template.get("components") or [] if str(component.get("type") or "").upper() == "BODY"), {})
        variable_count = len(set(re.findall(r"\{\{(\d+)\}\}", str(body.get("text") or ""))))
        # Operational alerts supply exactly two fields: title and details. Do not
        # offer fixed invitations or templates with a different parameter shape.
        if variable_count == 2:
            operational_templates.append({"name": template.get("name"), "language": template.get("language"), "variable_count": variable_count})
    return json_ready({
        "preferences": preferences,
        "whatsapp_templates": operational_templates,
        "cellar_thresholds": cellar_guardrails(settings),
        "channels": {
            "home_assistant": {"configured": bool(settings.ha_notifications_enabled and home_assistant_token()), "detail": settings.ha_notify_service if settings.ha_notifications_enabled else "Disabled in add-on options"},
            "email": {"configured": bool(settings.gmail_address and settings.gmail_app_password), "detail": settings.gmail_address or "Add the Gmail address and app password in add-on options"},
            "whatsapp": {"configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id), "detail": "Meta WhatsApp Business connected" if settings.whatsapp_access_token and settings.whatsapp_phone_number_id else "Add the Meta token and phone number ID in add-on options"},
        },
    })


@app.put("/api/v1/alert-settings/cellar-thresholds", dependencies=[Depends(authorize_write)])
def update_cellar_thresholds(payload: dict[str, Any], request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    ranges = {
        "cellar_temp_min_c": (0.0, 50.0), "cellar_temp_max_c": (0.0, 50.0),
        "cellar_level_min_pct": (0.0, 100.0), "cellar_level_max_pct": (0.0, 100.0),
        "cellar_ph_min": (0.0, 14.0), "cellar_ph_max": (0.0, 14.0),
        "cellar_density_min_sg": (0.8, 1.5), "cellar_density_max_sg": (0.8, 1.5),
    }
    values: dict[str, float] = {}
    for key, (minimum, maximum) in ranges.items():
        try:
            value = float(payload[key])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, f"Enter a numeric value for {key}")
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{key} must be between {minimum:g} and {maximum:g}")
        values[key] = value
    for low, high in (("cellar_temp_min_c", "cellar_temp_max_c"), ("cellar_level_min_pct", "cellar_level_max_pct"), ("cellar_ph_min", "cellar_ph_max"), ("cellar_density_min_sg", "cellar_density_max_sg")):
        if values[low] >= values[high]:
            raise HTTPException(422, f"{low} must be lower than {high}")
    username = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'cellar_guardrails',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps({**values, "updated_by": username})),
        )
    return {"saved": True, "cellar_thresholds": cellar_guardrails(settings)}


@app.put("/api/v1/alert-settings/{alert_type}", dependencies=[Depends(authorize_write)])
def update_alert_settings(alert_type: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    if alert_type not in ALERT_TYPES:
        raise HTTPException(404, "Unknown alert type")
    severity = str(payload.get("min_severity") or "warning")
    if severity not in {"info", "warning", "critical"}:
        raise HTTPException(422, "Choose info, warning or critical")
    emails = ",".join(value.strip() for value in str(payload.get("email_recipients") or "").split(",") if value.strip())[:2000]
    numbers = ",".join(dict.fromkeys(re.sub(r"\D", "", value) for value in re.split(r"[,;\n]+", str(payload.get("whatsapp_recipients") or "")) if re.sub(r"\D", "", value)))[:2000]
    template_name = re.sub(r"[^a-zA-Z0-9_]", "", str(payload.get("whatsapp_template_name") or ""))[:180]
    template_language = re.sub(r"[^a-zA-Z0-9_-]", "", str(payload.get("whatsapp_template_language") or ""))[:20]
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO alert_preferences (estate_id,alert_type,enabled,min_severity,notify_home_assistant,notify_email,notify_whatsapp,email_recipients,whatsapp_recipients,whatsapp_template_name,whatsapp_template_language,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE enabled=VALUES(enabled),min_severity=VALUES(min_severity),notify_home_assistant=VALUES(notify_home_assistant),notify_email=VALUES(notify_email),notify_whatsapp=VALUES(notify_whatsapp),email_recipients=VALUES(email_recipients),whatsapp_recipients=VALUES(whatsapp_recipients),whatsapp_template_name=VALUES(whatsapp_template_name),whatsapp_template_language=VALUES(whatsapp_template_language),updated_by=VALUES(updated_by)",
            (estate_id(), alert_type, bool(payload.get("enabled", True)), severity, bool(payload.get("notify_home_assistant", True)), bool(payload.get("notify_email")), bool(payload.get("notify_whatsapp")), emails, numbers, template_name or None, template_language or None, request.headers.get("X-Remote-User-Name") or "api"),
        )
    return {"saved": True}


@app.get("/api/v1/intake", dependencies=[Depends(authorize)])
def list_intake() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT id,source,sender_name,sender_address,received_at,title,original_filename,media_type,classification,ai_summary,extracted_data,review_status,processing_error FROM intake_items WHERE estate_id=%s ORDER BY received_at DESC LIMIT 250", (estate_id(),)))


@app.get("/api/v1/processing-log", dependencies=[Depends(authorize)])
def processing_log(limit: int = Query(100, ge=10, le=500)) -> list[dict[str, Any]]:
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


def _whatsapp_contact_book() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts'", (estate_id(),)) or {}
    book = _event_payload(row.get("setting_value"))
    return {"contacts": list(book.get("contacts") or []), "groups": list(book.get("groups") or [])}


def _system_whatsapp_settings() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='system_whatsapp_accounts'", (estate_id(),)) or {}
    saved = _event_payload(row.get("setting_value"))
    stored = {int(item.get("slot") or 0): item for item in saved.get("accounts", []) if isinstance(item, dict)}
    accounts = []
    for slot in (1, 2):
        item = stored.get(slot, {})
        accounts.append({
            "slot": slot,
            "label": str(item.get("label") or f"System account {slot}")[:80],
            "enabled": bool(item.get("enabled", True)),
            "ingest_direct": bool(item.get("ingest_direct", True)),
            "ingest_groups": bool(item.get("ingest_groups", True)),
            "contact_scope": "selected" if str(item.get("contact_scope") or "all") == "selected" else "all",
            "selected_contact_ids": [str(value)[:190] for value in item.get("selected_contact_ids", []) if str(value).strip()][:250],
            "monitor_all": bool(item.get("monitor_all", False)),
            "selected_chat_ids": [str(value)[:190] for value in item.get("selected_chat_ids", []) if str(value).strip()][:250],
            "send_enabled": bool(item.get("send_enabled", False)),
        })
    return {"accounts": accounts}


def _save_system_whatsapp_settings(payload: dict[str, Any]) -> dict[str, Any]:
    raw = {int(item.get("slot") or 0): item for item in payload.get("accounts", []) if isinstance(item, dict)}
    accounts = []
    for slot in (1, 2):
        item = raw.get(slot, {})
        accounts.append({
            "slot": slot,
            "label": str(item.get("label") or f"System account {slot}").strip()[:80],
            "enabled": bool(item.get("enabled", True)),
            "ingest_direct": bool(item.get("ingest_direct", True)),
            "ingest_groups": bool(item.get("ingest_groups", True)),
            "contact_scope": "selected" if str(item.get("contact_scope") or "all") == "selected" else "all",
            "selected_contact_ids": list(dict.fromkeys(str(value).strip()[:190] for value in item.get("selected_contact_ids", []) if str(value).strip()))[:250],
            "monitor_all": bool(item.get("monitor_all", False)),
            "selected_chat_ids": list(dict.fromkeys(str(value).strip()[:190] for value in item.get("selected_chat_ids", []) if str(value).strip()))[:250],
            "send_enabled": bool(item.get("send_enabled", False)),
        })
    stored = {"accounts": accounts, "updated_at": datetime.now(timezone.utc).isoformat()}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'system_whatsapp_accounts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
    return stored


def _system_whatsapp_chat_allowed(account: dict[str, Any], chat_id: str, is_group: bool | None = None) -> bool:
    group = chat_id.endswith("@g.us") if is_group is None else is_group
    if group:
        return bool(account["monitor_all"]) or chat_id in account["selected_chat_ids"]
    return account["contact_scope"] == "all" or chat_id in account["selected_contact_ids"]


def _system_whatsapp_center(settings: Settings) -> dict[str, Any]:
    configured = _system_whatsapp_settings()
    if not settings.system_whatsapp_enabled:
        return {"available": False, "error": "System WhatsApp accounts are disabled in Home Assistant configuration", **configured}
    try:
        live = system_whatsapp_accounts()
        by_slot = {int(item.get("slot") or 0): item for item in live.get("accounts", [])}
        saved_names = {
            re.sub(r"\D", "", str(contact.get("number") or "")): str(contact.get("name") or "").strip()
            for contact in _whatsapp_contact_book()["contacts"]
            if re.sub(r"\D", "", str(contact.get("number") or "")) and str(contact.get("name") or "").strip()
        }
        accounts = []
        for item in configured["accounts"]:
            account = {**item, **by_slot.get(item["slot"], {})}
            account["contacts"] = [
                {
                    **contact,
                    "name": saved_names.get(re.sub(r"\D", "", str(contact.get("number") or ""))) or contact.get("name"),
                }
                for contact in account.get("contacts", [])
            ]
            accounts.append(account)
        return {"available": True, "accounts": accounts}
    except Exception as error:
        return {"available": False, "error": str(error)[:300], **configured}


def _whatsapp_assistant_settings() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_assistants'", (estate_id(),)) or {}
    saved = _event_payload(row.get("setting_value"))
    controls = [code for code in saved.get("manager_controls", []) if code in {"full_refresh", "weather", "cistern", "disease", "public_feed"}]
    ha_entities = [str(value) for value in saved.get("home_assistant_entities", []) if re.fullmatch(r"(?:light|switch|input_boolean|fan|media_player)\.[a-z0-9_]+", str(value))]
    camera_entities = [str(value) for value in saved.get("home_assistant_camera_entities", []) if re.fullmatch(r"camera\.[a-z0-9_]+", str(value))]
    return {
        "reception_enabled": bool(saved.get("reception_enabled", False)),
        "manager_enabled": bool(saved.get("manager_enabled", False)),
        "unknown_reception": bool(saved.get("unknown_reception", False)),
        "trusted_ingestion": bool(saved.get("trusted_ingestion", True)),
        "manager_controls": controls or ["weather", "cistern", "disease", "public_feed"],
        "reply_limit_unknown": min(20, max(1, int(saved.get("reply_limit_unknown", 6)))),
        "reply_limit_manager": min(100, max(1, int(saved.get("reply_limit_manager", 30)))),
        "voice": str(saved.get("voice") or "marin") if str(saved.get("voice") or "marin") in {"marin", "coral", "shimmer", "nova"} else "marin",
        "home_assistant_entities": ha_entities[:100],
        "home_assistant_camera_entities": camera_entities[:100],
    }


def _whatsapp_sender_profile(number: str) -> dict[str, Any]:
    clean = re.sub(r"\D", "", number or "")
    contact = next((item for item in _whatsapp_contact_book()["contacts"] if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
    assistants = _whatsapp_assistant_settings()
    assigned = str((contact or {}).get("assistant") or "").lower()
    if (contact or {}).get("auto_unknown"):
        profile = "reception" if assistants["unknown_reception"] else "off"
    else:
        profile = assigned if assigned in {"reception", "manager", "reporter", "off"} else ("reception" if not contact and assistants["unknown_reception"] else "off")
    language = str((contact or {}).get("language") or "auto").lower()
    role = str((contact or {}).get("role") or "").strip().casefold()
    administrator = bool((contact or {}).get("administrator")) or role in {"admin", "administrator", "amministratore"}
    return {"profile": profile, "language": language if language in {"auto", "en", "it"} else "auto", "contact": contact, "administrator": administrator, "settings": assistants}


def _whatsapp_reply_preference(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    help_commands = {
        "reply settings", "reply options", "response settings",
        "impostazioni risposta", "opzioni risposta", "preferenze risposta",
    }
    if normalized in help_commands:
        return "help"
    english = re.fullmatch(r"(?:set )?(?:my )?(?:reply|replies|response)(?: mode)?(?: to)? (text|voice|audio|both|match|same)", normalized)
    italian = re.fullmatch(r"(?:imposta )?(?:la |le )?(?:risposta|risposte)(?: in| su| a)? (testo|voce|audio|entrambe|entrambi|stesso|come ricevuto)", normalized)
    selected = (english or italian).group(1) if english or italian else ""
    return {
        "text": "text", "testo": "text",
        "voice": "voice", "audio": "voice", "voce": "voice",
        "both": "both", "entrambe": "both", "entrambi": "both",
        "match": "match", "same": "match", "stesso": "match", "come ricevuto": "match",
    }.get(selected)


def _whatsapp_capabilities_requested(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return normalized in {"?", "menu", "help", "capabilities", "what can you do", "aiuto", "funzioni", "cosa puoi fare", "cosa sai fare"}


def _set_whatsapp_reply_preference(number: str, reply_mode: str) -> bool:
    clean = re.sub(r"\D", "", number or "")
    if reply_mode not in {"text", "voice", "both", "match"}:
        return False
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE",
            (estate_id(),),
        )
        row = cursor.fetchone() or {}
        book = _event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        contact = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
        if not contact:
            return False
        contact["reply_mode"] = reply_mode
        stored = {**book, "contacts": contacts[:100], "groups": list(book.get("groups") or [])[:30], "updated_by": f"WhatsApp {clean}"}
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
        audit(cursor, "update", "whatsapp_reply_preference", clean, {"reply_mode": reply_mode, "source": "self_service"}, f"WhatsApp {clean}")
    return True


def _set_whatsapp_language_preference(number: str, language: str) -> bool:
    clean = re.sub(r"\D", "", number or "")
    if language not in {"auto", "en", "it"}:
        return False
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE",
            (estate_id(),),
        )
        row = cursor.fetchone() or {}
        book = _event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        contact = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
        if not contact:
            return False
        contact["language"] = language
        stored = {**book, "contacts": contacts[:100], "groups": list(book.get("groups") or [])[:30], "updated_by": f"WhatsApp {clean}"}
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
        audit(cursor, "update", "whatsapp_language_preference", clean, {"language": language, "source": "self_service"}, f"WhatsApp {clean}")
    return True


async def _send_whatsapp_assistant_reply(sender: str, text: str, assignment: dict[str, Any], *, resolve_notice: bool = True) -> None:
    if not resolve_notice:
        await asyncio.to_thread(_mark_whatsapp_intervention_notice)
    contact = assignment.get("contact") or {}
    # Unless a contact explicitly selected text, voice, or both, answer in the
    # same medium that arrived. This avoids surprise audio for normal texts.
    reply_mode = str(contact.get("reply_mode") or "match").lower()
    if reply_mode == "match":
        reply_mode = "voice" if assignment.get("incoming_mode") == "voice" else "text"
    if reply_mode == "both":
        await asyncio.to_thread(send_whatsapp_message, sender, text)
    if reply_mode in {"voice", "both"} and assignment.get("profile") in {"manager", "reporter", "reception"}:
        try:
            audio = await asyncio.to_thread(synthesize_whatsapp_voice, text, assignment.get("language") or "auto", assignment.get("settings", {}).get("voice") or "marin")
            disclosure = "Baiamonte AI voice"
            await asyncio.to_thread(send_whatsapp_media, sender, audio, "baiamonte-reply.mp3", "audio/mpeg", disclosure)
            if resolve_notice:
                await asyncio.to_thread(_resolve_answered_whatsapp_notice)
            return
        except Exception:
            if reply_mode == "both":
                return
    if reply_mode == "both":
        if resolve_notice:
            await asyncio.to_thread(_resolve_answered_whatsapp_notice)
        return
    await asyncio.to_thread(send_whatsapp_message, sender, text)
    if resolve_notice:
        await asyncio.to_thread(_resolve_answered_whatsapp_notice)


async def _handle_whatsapp_assistant(sender: str, body: str, message_id: str, record_id: str | None = None, group_id: str = "", incoming_mode: str = "text") -> None:
    if group_id or not body:
        return
    _whatsapp_inbound_context.set((message_id, record_id))
    assignment = _whatsapp_sender_profile(sender)
    assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
    profile, language, options = assignment["profile"], assignment["language"], assignment["settings"]
    italian = _whatsapp_is_italian(body, language, sender)
    if _whatsapp_capabilities_requested(body):
        await _send_whatsapp_assistant_reply(sender, _whatsapp_capabilities(profile, italian, assignment.get("administrator", False)), assignment)
        return
    language_preference = _whatsapp_language_preference(body)
    if language_preference and assignment.get("contact"):
        if language_preference == "help":
            reply = "Language / Lingua: reply ENGLISH, ITALIANO, or LANGUAGE AUTO."
        elif _set_whatsapp_language_preference(sender, language_preference):
            assignment = _whatsapp_sender_profile(sender)
            assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
            language = assignment["language"]
            italian = language_preference == "it"
            labels = {"en": "English", "it": "Italiano", "auto": "automatic / automatica"}
            reply = f"Lingua salvata: {labels[language_preference]}." if italian else f"Language saved: {labels[language_preference]}."
        else:
            reply = "Non è stato possibile salvare la lingua." if italian else "The language preference could not be saved."
        await _send_whatsapp_assistant_reply(sender, reply, assignment)
        return
    preference = _whatsapp_reply_preference(body)
    if preference and assignment.get("contact"):
        if preference == "help":
            reply = (
                "Preferenze risposta: RISPONDI TESTO, RISPONDI VOCE, RISPONDI ENTRAMBI oppure RISPONDI COME RICEVUTO."
                if italian else
                "Reply preferences: REPLY TEXT, REPLY VOICE, REPLY BOTH, or REPLY MATCH."
            )
        elif _set_whatsapp_reply_preference(sender, preference):
            assignment = _whatsapp_sender_profile(sender)
            assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
            names = {
                "text": ("testo", "text"), "voice": ("voce", "voice"),
                "both": ("testo e voce", "text and voice"),
                "match": ("lo stesso formato del messaggio ricevuto", "the same format as the incoming message"),
            }
            reply = f"Preferenza salvata: {names[preference][0]}." if italian else f"Preference saved: {names[preference][1]}."
        else:
            reply = "Non è stato possibile salvare la preferenza." if italian else "The reply preference could not be saved."
        await _send_whatsapp_assistant_reply(sender, reply, assignment)
        return
    if profile == "off" or profile == "reception" and not options["reception_enabled"] or profile in {"manager", "reporter"} and not options["manager_enabled"]:
        reason = "assistant_disabled" if profile != "off" else "review_only"
        reply = (
            "Messaggio ricevuto e conservato per la revisione dell'amministratore. Nessun dato operativo è stato modificato."
            if italian else
            "Message received and saved for administrator review. No operational data was changed."
        )
        try:
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            with transaction() as (_, cursor):
                cursor.execute(
                    "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','inbound_routing',%s,'processed',%s)",
                    (estate_id(), message_id[:190], json.dumps({"sender": sender, "profile": profile, "route": reason, "record_id": record_id})),
                )
        except Exception as error:
            with transaction() as (_, cursor):
                cursor.execute(
                    "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','inbound_routing',%s,'failed',%s,%s)",
                    (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "profile": profile, "route": reason, "record_id": record_id})),
                )
        return
    if await _continue_whatsapp_blend_calculator_flow(sender, body, assignment, italian, _send_whatsapp_assistant_reply):
        return
    if await _continue_whatsapp_submission_flow(sender, body, assignment, italian, _send_whatsapp_assistant_reply):
        return
    menu_route = _whatsapp_menu_route(profile, body, italian, assignment.get("administrator", False))
    if menu_route:
        route, routed_text = menu_route
        if route == "reply":
            await _send_whatsapp_assistant_reply(sender, routed_text, assignment)
            return
        if route == "handoff":
            reply = (
                "Messaggio conservato per il team. Aggiungi ora il motivo, il tuo nome e il modo migliore per contattarti. Una persona lo esaminerà; non è ancora una conferma."
                if italian else
                "Your message is retained for the team. Now add the reason, your name, and the best way to contact you. A person will review it; this is not yet a confirmation."
            )
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            return
        if route == "observation_menu":
            state = {"kind": "select", "step": 0, "values": {}}
            await asyncio.to_thread(_begin_whatsapp_submission, sender, state, f"WhatsApp {sender}")
            await _send_whatsapp_assistant_reply(sender, _whatsapp_submission_menu(italian), assignment, resolve_notice=False)
            return
        if route == "blend_crate_calculator":
            await asyncio.to_thread(_begin_whatsapp_blend_calculator, sender, date.today().year)
            reply = (
                "Quante cassette di Nerello prevedi di raccogliere? Rispondi solo con il numero, per esempio 100."
                if italian else
                "How many Nerello crates do you plan to pick? Reply with only the number, for example 100."
            )
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            return
        if route.startswith("snapshot_"):
            try:
                reply = await _whatsapp_live_assisted_snapshot(
                    route,
                    routed_text,
                    italian,
                    options["home_assistant_entities"],
                    assignment.get("administrator", False),
                )
                await _send_whatsapp_assistant_reply(sender, reply, assignment)
            except Exception as error:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','live_menu_snapshot',%s,'failed',%s,%s)",
                        (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "route": route})),
                    )
                reply = "I dati operativi dal vivo non sono temporaneamente disponibili. Il messaggio è stato conservato." if italian else "Live operational data is temporarily unavailable. Your message was retained."
                await _send_whatsapp_assistant_reply(sender, reply, assignment)
            return
        body = routed_text
    if _whatsapp_handoff_requested(body):
        reply = (
            "Richiesta inoltrata per la revisione umana. Scrivi in un solo messaggio cosa ti serve, l'urgenza e il modo migliore per contattarti."
            if italian else
            "Your request has been flagged for human review. In one message, send what you need, the urgency, and the best way to contact you."
        )
        await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
        return
    analysis: dict[str, Any] = {}
    if record_id and profile in {"manager", "reporter"} and options["trusted_ingestion"] and get_settings().openai_api_key:
        try:
            analyzed = await asyncio.to_thread(analyze_intake, record_id)
            analysis = analyzed.get("analysis") or {}
        except Exception:
            pass
    approval = re.fullmatch(r"\s*(?:APPROVE|APPROVA)\s+(\d{4,8})\s*", body, re.I)
    rejection = re.fullmatch(r"\s*(?:REJECT|RIFIUTA)\s+(\d{4,8})(?:\s+(.{1,500}))?\s*", body, re.I)
    if profile == "manager" and (approval or rejection):
        code = (approval or rejection).group(1)
        pending = _pending_whatsapp_action(sender, code, "intake_approval_pending")
        if pending:
            status = "approved" if approval else "rejected"
            review_reason = None if approval else (rejection.group(2) or "Rejected through WhatsApp; no additional reason supplied").strip()
            with transaction() as (_, cursor):
                cursor.execute("UPDATE intake_items SET review_status=%s,review_reason=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, review_reason, f"WhatsApp {sender}", pending.get("record_id"), estate_id()))
                cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (pending.get("_event_id"),))
            await _send_whatsapp_assistant_reply(sender, ("Informazione approvata e conservata nel registro di revisione." if italian else "Information approved and retained in the review record.") if approval else ("Informazione rifiutata." if italian else "Information rejected."), assignment)
            return
    confirmation = re.fullmatch(r"\s*(?:CONFIRM|CONFERMA)\s+(\d{4,8})\s*", body, re.I)
    if profile == "manager" and confirmation:
        code = confirmation.group(1)
        pending = _pending_whatsapp_action(sender, code, "manager_control_pending")
        if pending and pending.get("process") in options["manager_controls"]:
            with transaction() as (_, cursor):
                claimed = cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (pending.get("_event_id"),))
            if not claimed:
                return
            try:
                await run_named_process(str(pending["process"]))
                await _send_whatsapp_assistant_reply(sender, "Aggiornamento completato." if italian else "System update completed.", assignment)
            except Exception:
                await _send_whatsapp_assistant_reply(sender, "Aggiornamento non riuscito. Controlla Operations Control." if italian else "System update failed. Check Operations Control.", assignment, resolve_notice=False)
            return
        device_pending = _pending_whatsapp_action(sender, code, "manager_device_control_pending")
        if device_pending:
            with transaction() as (_, cursor):
                claimed = cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (device_pending.get("_event_id"),))
            if not claimed:
                return
            try:
                result = await asyncio.to_thread(control_home_assistant_manager_device, str(device_pending.get("entity_id") or ""), str(device_pending.get("action") or ""), options["home_assistant_entities"])
                with transaction() as (_, cursor):
                    audit(cursor, "control", "home_assistant_entity", result["entity_id"], {"action": result["action"], "source": "whatsapp_manager"}, f"WhatsApp {sender}")
                action_text = "acceso" if result["action"] == "turn_on" else "spento"
                await _send_whatsapp_assistant_reply(sender, (f"{result['name']} {action_text}." if italian else f"{result['name']} turned {'on' if result['action']=='turn_on' else 'off'}.") , assignment)
            except Exception:
                await _send_whatsapp_assistant_reply(sender, "Controllo non riuscito. Verifica Home Assistant." if italian else "Device control failed. Check Home Assistant.", assignment, resolve_notice=False)
            return
    commands = {
        "full_refresh": ("refresh system", "aggiorna sistema", "aggiornamento completo"),
        "weather": ("refresh weather", "aggiorna meteo"),
        "cistern": ("check cistern", "controlla cisterna"),
        "disease": ("update disease", "aggiorna malattie", "pressione malattie"),
        "public_feed": ("publish website", "aggiorna sito", "pubblica sito"),
    }
    lowered = body.casefold()
    if profile == "manager":
        camera_request = await asyncio.to_thread(resolve_home_assistant_camera_request, body)
        if camera_request:
            cameras = camera_request.get("cameras") or []
            if camera_request.get("action") in {"list", "unavailable"}:
                if cameras:
                    names = "\n".join(f"• {item['name']}" for item in cameras[:20])
                    text = ("Telecamere disponibili:\n" if italian else "Available cameras:\n") + names
                else:
                    text = "Nessuna telecamera è disponibile per WhatsApp." if italian else "No cameras are available to WhatsApp."
                await _send_whatsapp_assistant_reply(sender, text, assignment)
                return
            recent = fetch_one(
                "SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='manager_camera_snapshot' AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender'))=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 1 MINUTE)",
                (estate_id(), sender),
            ) or {}
            if int(recent.get("total") or 0) >= 3:
                await _send_whatsapp_assistant_reply(sender, "Attendi un momento prima di richiedere un'altra immagine." if italian else "Please wait a moment before requesting another camera image.", assignment)
                return
            camera = camera_request["camera"]
            try:
                captured = await asyncio.to_thread(home_assistant_camera_snapshot, camera["entity_id"])
                stale = bool(captured.get("stale"))
                age_minutes = max(1, int(captured.get("age_seconds") or 0) // 60) if stale else 0
                caption = (
                    f"{camera['name']} · ultima immagine disponibile ({age_minutes} min fa)" if italian and stale else
                    f"{camera['name']} · immagine attuale" if italian else
                    f"{camera['name']} · last available image ({age_minutes} min old)" if stale else
                    f"{camera['name']} · current image"
                )
                await asyncio.to_thread(send_whatsapp_media, sender, captured["data"], f"{camera['entity_id'].split('.',1)[-1]}.jpg", captured["content_type"], caption)
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','manager_camera_snapshot',%s,'processed',%s)",
                        (estate_id(), message_id[:190], json.dumps({"sender": sender, "entity_id": camera["entity_id"], "stale": stale})),
                    )
                    audit(cursor, "view", "home_assistant_camera", camera["entity_id"], {"source": "whatsapp_manager", "stale": stale}, f"WhatsApp {sender}")
            except Exception as error:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','manager_camera_snapshot',%s,'failed',%s,%s)",
                        (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "entity_id": camera["entity_id"]})),
                    )
                await _send_whatsapp_assistant_reply(sender, "La telecamera non è disponibile e non esiste un'immagine recente." if italian else "The camera is unavailable and no recent image is cached.", assignment)
            return
    if profile == "manager" and options["home_assistant_entities"]:
        device_request = await asyncio.to_thread(resolve_home_assistant_control_request, body, options["home_assistant_entities"])
        if device_request:
            code = str(int(hashlib.sha256(f"{sender}:{message_id}:{device_request['entity_id']}:{device_request['action']}".encode()).hexdigest()[:8], 16))[-6:]
            with transaction() as (_, cursor):
                cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_device_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({**device_request, "sender": sender, "message_id": message_id})))
            action_name = "accendere" if device_request["action"] == "turn_on" else "spegnere"
            prompt = f"Conferma per {action_name} {device_request['name']}. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirm to turn {'on' if device_request['action']=='turn_on' else 'off'} {device_request['name']}. Reply CONFIRM {code} within 24 hours."
            await _send_whatsapp_assistant_reply(sender, prompt, assignment, resolve_notice=False)
            return
    requested = next((process for process, phrases in commands.items() if process in options["manager_controls"] and any(phrase in lowered for phrase in phrases)), None)
    if profile == "manager" and requested:
        code = str(int(hashlib.sha256(f"{sender}:{message_id}:{requested}".encode()).hexdigest()[:8], 16))[-6:]
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"process": requested, "sender": sender, "message_id": message_id})))
        await _send_whatsapp_assistant_reply(sender, (f"Conferma richiesta. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirmation required. Reply CONFIRM {code} within 24 hours."), assignment, resolve_notice=False)
        return
    if profile in {"manager", "reporter"} and options["trusted_ingestion"] and record_id:
        try:
            if whatsapp_is_submission(body, analysis):
                if profile == "reporter":
                    summary = str(analysis.get("summary") or "Information ready for review")[:700]
                    notice = "\n\nInviato per la revisione del manager." if italian else "\n\nSubmitted for manager review."
                    await _send_whatsapp_assistant_reply(sender, summary + notice, assignment, resolve_notice=False)
                    return
                code = str(int(hashlib.sha256(f"{sender}:{record_id}".encode()).hexdigest()[:8], 16))[-6:]
                with transaction() as (_, cursor):
                    cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','intake_approval_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"record_id": record_id, "sender": sender, "classification": analysis.get("classification")})))
                summary = str(analysis.get("summary") or "Information ready for review")[:700]
                prompt = f"\n\nRispondi APPROVA {code} o RIFIUTA {code}." if italian else f"\n\nReply APPROVE {code} or REJECT {code}."
                await _send_whatsapp_assistant_reply(sender, summary + prompt, assignment, resolve_notice=False)
                return
        except Exception:
            pass
    limit = options["reply_limit_unknown"] if profile == "reception" else options["reply_limit_manager"]
    count = fetch_one("SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='chatbot_reply' AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender'))=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR)", (estate_id(), sender)) or {}
    if int(count.get("total") or 0) >= limit:
        await _send_whatsapp_assistant_reply(sender, "Limite giornaliero raggiunto. Il messaggio è stato salvato per la revisione." if italian else "Daily assistant limit reached. Your message was saved for review.", assignment, resolve_notice=False)
        return
    try:
        result = await asyncio.to_thread(whatsapp_chatbot_reply, body, profile if profile in {"manager", "reporter"} else "reception", language, options["home_assistant_entities"] if profile == "manager" else [], assignment.get("administrator", False))
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','chatbot_reply',%s,'failed',%s,%s)", (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "profile": profile, "language": language})))
        fallback = (
            "Il servizio di risposta è temporaneamente non disponibile. Il messaggio è stato conservato. Rispondi MENU per le opzioni o PERSONA se serve l'intervento del team."
            if italian else
            "The assistant is temporarily unavailable. Your message was retained. Reply MENU for options or HUMAN if the team needs to intervene."
        )
        await _send_whatsapp_assistant_reply(sender, fallback, assignment)
        return
    answer = str(result.get("answer") or result.get("message") or "")[:4096]
    if not result.get("configured") or not answer:
        answer = (
            "Non posso completare questa risposta in questo momento. Il messaggio è stato conservato. Rispondi MENU per richieste supportate o PERSONA per il team."
            if italian else
            "I cannot complete that answer right now. Your message was retained. Reply MENU for supported requests or HUMAN for the team."
        )
    await _send_whatsapp_assistant_reply(sender, answer, assignment)
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','chatbot_reply',%s,'processed',%s)", (estate_id(), message_id[:190], json.dumps({"sender": sender, "profile": profile, "language": language, "record_id": record_id})))


async def _handle_whatsapp_voice(sender: str, data: bytes, filename: str, message_id: str, sender_name: str, group_id: str = "") -> None:
    assignment = _whatsapp_sender_profile(sender)
    assignment["incoming_mode"] = "voice"
    if group_id:
        return
    if assignment["profile"] == "off":
        await _send_whatsapp_assistant_reply(sender, "Nota vocale ricevuta e salvata per la revisione." if assignment["language"] == "it" else "Voice note received and saved for review.", assignment)
        return
    try:
        transcript = await asyncio.to_thread(transcribe_whatsapp_voice, data, filename, assignment["language"])
        if not transcript:
            await _send_whatsapp_assistant_reply(sender, "Nota vocale ricevuta, ma non è stato possibile trascriverla. È stata conservata per la revisione." if assignment["language"] == "it" else "Voice note received, but it could not be transcribed. It was retained for review.", assignment)
            return
        record_id = save_intake_file(transcript.encode(), f"whatsapp-{message_id}-transcript.txt", "text/plain", "whatsapp", "WhatsApp voice transcript", transcript, message_id + ":transcript", sender_name, sender)
        await _handle_whatsapp_assistant(sender, transcript, message_id, record_id, group_id, "voice")
    except IntegrityError:
        return
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','voice_routing',%s,'failed',%s,%s)", (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender})))
        await _send_whatsapp_assistant_reply(sender, "La nota vocale è stata salvata, ma l'elaborazione non è riuscita." if assignment["language"] == "it" else "The voice note was saved, but processing failed.", assignment)


def _remember_whatsapp_contact(number: str, name: str | None = None) -> None:
    clean_number = re.sub(r"\D", "", number or "")
    clean_name = str(name or "").strip()[:180]
    if len(clean_number) < 8:
        return
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE",
            (estate_id(),),
        )
        row = cursor.fetchone() or {}
        book = _event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        groups = list(book.get("groups") or [])
        existing = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == clean_number), None)
        changed = False
        if existing is None:
            assistants = _whatsapp_assistant_settings()
            contacts.append({"name": clean_name or clean_number, "number": clean_number, "role": "", "assistant": "reception" if assistants["unknown_reception"] else "off", "language": "auto", "reply_mode": "match", "auto_unknown": True})
            changed = True
        elif clean_name and (not str(existing.get("name") or "").strip() or str(existing.get("name")) == clean_number):
            existing["name"] = clean_name
            changed = True
        if changed:
            stored = {"contacts": contacts[:100], "groups": groups[:30], "updated_by": "WhatsApp inbound"}
            cursor.execute(
                "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) "
                "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
                (estate_id(), json.dumps(stored)),
            )


@app.get("/api/v1/communications", dependencies=[Depends(authorize)])
def communication_center(request: Request, refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    system_admin = request_username(request) in admin_usernames(settings) | {"api"}
    try:
        mailbox_status = gmail_mailbox_status()
    except Exception as error:
        mailbox_status = {"configured": bool(settings.gmail_address and settings.gmail_app_password), "address": settings.gmail_address or None, "folder": settings.gmail_folder or "INBOX", "total": None, "unread": None, "error": str(error)[:240]}
    gmail_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,message_text,original_filename,classification,review_status,review_reason,reviewed_by,reviewed_at,ai_summary,processing_error FROM intake_items WHERE estate_id=%s AND source='gmail' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    whatsapp_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,message_text,classification,review_status,review_reason,reviewed_by,reviewed_at,ai_summary,processing_error FROM intake_items WHERE estate_id=%s AND source='whatsapp' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    sent_rows = fetch_all(
        "SELECT id,integration_name,status,payload,error_message,occurred_at FROM integration_events WHERE estate_id=%s AND integration_name IN ('gmail-mailbox','whatsapp-channel','system-whatsapp-channel') AND event_type='message_sent' ORDER BY occurred_at DESC LIMIT 120",
        (estate_id(),),
    )
    if not system_admin:
        return json_ready({
            "gmail": {"status": mailbox_status, "received": gmail_received, "sent": [{**row, "details": _event_payload(row.get("payload"))} for row in sent_rows if row["integration_name"] == "gmail-mailbox"]},
            "whatsapp": {"admin_only": True, "system_accounts": {"admin_only": True, "available": False, "accounts": [], "sent": []}},
        })
    receipt_rows = fetch_all(
        "SELECT external_id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='message_status' AND external_id IS NOT NULL ORDER BY id DESC LIMIT 360",
        (estate_id(),),
    )
    latest_receipts: dict[str, dict[str, Any]] = {}
    receipt_ranks = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}
    for receipt in receipt_rows:
        message_id = str(receipt.get("external_id") or "")
        payload = _event_payload(receipt.get("payload"))
        current = latest_receipts.get(message_id) or {}
        if message_id and receipt_ranks.get(str(payload.get("status") or "").lower(), 0) >= receipt_ranks.get(str(current.get("status") or "").lower(), 0):
            latest_receipts[message_id] = payload
    whatsapp_book = _whatsapp_contact_book()
    contacts = list(whatsapp_book.get("contacts", []))
    contact_numbers = {re.sub(r"\D", "", str(item.get("number") or "")) for item in contacts}
    for message in whatsapp_received:
        number = re.sub(r"\D", "", str(message.get("sender_address") or ""))
        if len(number) >= 8 and number not in contact_numbers:
            contacts.append({"name": str(message.get("sender_name") or number), "number": number, "role": "", "assistant": "off", "language": "auto", "reply_mode": "match"})
            contact_numbers.add(number)
    groups = whatsapp_book.get("groups", [])
    diagnostics = whatsapp_diagnostics(force=refresh)
    whatsapp_sent = []
    for row in sent_rows:
        if row["integration_name"] != "whatsapp-channel":
            continue
        details = _event_payload(row.get("payload"))
        receipt = latest_receipts.get(str(details.get("message_id") or "")) or {}
        delivery_status = str(receipt.get("status") or details.get("delivery_status") or _whatsapp_delivery_status(row)).lower()
        whatsapp_sent.append({**row, "details": details, "delivery_status": delivery_status})
    active_whatsapp_sender_id = whatsapp_phone_number_id()
    test_sender_id = re.sub(r"\D", "", str(settings.whatsapp_test_phone_number_id or ""))
    inbound_event_rows = fetch_all(
        "SELECT payload,occurred_at FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='message_received' ORDER BY occurred_at DESC LIMIT 180",
        (estate_id(),),
    )
    selected_inbound_events = []
    for row in inbound_event_rows:
        details = _event_payload(row.get("payload"))
        receiver_id = re.sub(r"\D", "", str(details.get("phone_number_id") or ""))
        if receiver_id and receiver_id == active_whatsapp_sender_id:
            selected_inbound_events.append({**row, "details": details})
    selected_outbound_events = [
        row for row in whatsapp_sent
        if re.sub(r"\D", "", str((row.get("details") or {}).get("phone_number_id") or "")) == active_whatsapp_sender_id
    ]
    activity_by_number: dict[str, dict[str, Any]] = {}
    for message in whatsapp_received:
        number = re.sub(r"\D", "", str(message.get("sender_address") or ""))
        if number and message.get("received_at"):
            activity = activity_by_number.setdefault(number, {})
            if not activity.get("last_inbound_at") or message["received_at"] > activity["last_inbound_at"]:
                activity["last_inbound_at"] = message["received_at"]
    for message in whatsapp_sent:
        details = message.get("details") or {}
        number = re.sub(r"\D", "", str(details.get("recipient") or ""))
        if number and message.get("occurred_at"):
            activity = activity_by_number.setdefault(number, {})
            if not activity.get("last_outbound_at") or message["occurred_at"] > activity["last_outbound_at"]:
                activity["last_outbound_at"] = message["occurred_at"]
                activity["delivery_status"] = message.get("delivery_status")
    now = datetime.now()
    for contact in contacts:
        number = re.sub(r"\D", "", str(contact.get("number") or ""))
        activity = activity_by_number.get(number) or {}
        inbound_at = activity.get("last_inbound_at")
        outbound_at = activity.get("last_outbound_at")
        last_activity = max((value for value in (inbound_at, outbound_at) if value), default=None)
        window_open = bool(inbound_at and now - inbound_at <= timedelta(hours=24))
        recently_active = bool(last_activity and now - last_activity <= timedelta(days=7))
        contact["presence"] = {
            **activity,
            "last_activity_at": last_activity,
            "conversation_window_open": window_open,
            "recently_active": recently_active,
            "label": "Conversation open" if window_open else "Recent activity" if recently_active else "No recent activity",
        }
    diagnostics["sender_verified"] = bool(
        diagnostics.get("connected") and diagnostics.get("registered") is not False
    )
    diagnostics["inbound_verified"] = bool(selected_inbound_events) or bool(
        whatsapp_received
        and active_whatsapp_sender_id
        and active_whatsapp_sender_id != test_sender_id
    )
    diagnostics["inbound_last_at"] = selected_inbound_events[0].get("occurred_at") if selected_inbound_events else None
    successful_outbound_states = {"sent", "delivered", "read"}
    diagnostics["outbound_verified"] = any(
        row.get("status") == "processed" and str(row.get("delivery_status") or "").lower() in successful_outbound_states
        for row in selected_outbound_events
    )
    diagnostics["outbound_last_at"] = selected_outbound_events[0].get("occurred_at") if selected_outbound_events else None
    latest_selected_event = selected_outbound_events[0] if selected_outbound_events else None
    latest_selected_failure = latest_selected_event if (latest_selected_event or {}).get("status") == "failed" else None
    diagnostics["outbound_error"] = str((latest_selected_failure or {}).get("error_message") or "")[:300] or None
    diagnostics["operational"] = bool(
        diagnostics.get("sender_verified")
        and (diagnostics["inbound_verified"] or diagnostics["outbound_verified"])
    )
    templates = whatsapp_templates(force=refresh)
    sender_catalog = whatsapp_phone_numbers(force=refresh)
    native_groups = whatsapp_native_groups(force=refresh) if settings.whatsapp_native_groups_enabled else {"configured": False, "groups": []}
    assistant_settings = _whatsapp_assistant_settings()
    try:
        assistant_settings["home_assistant_device_catalog"] = home_assistant_manager_devices()
        assistant_settings["home_assistant_camera_catalog"] = home_assistant_manager_camera_catalog()
    except Exception:
        assistant_settings["home_assistant_device_catalog"] = []
        assistant_settings["home_assistant_camera_catalog"] = []
    return json_ready({
        "gmail": {"status": mailbox_status, "received": gmail_received, "sent": [{**row, "details": _event_payload(row.get("payload"))} for row in sent_rows if row["integration_name"] == "gmail-mailbox"]},
        "whatsapp": {
            "configured": bool(settings.whatsapp_access_token and whatsapp_phone_number_id()),
            "diagnostics": diagnostics, "templates": templates.get("templates") or [], "templates_error": templates.get("error"),
            "phone_number_id": whatsapp_phone_number_id() or None, "senders": sender_catalog.get("senders") or [],
            "senders_error": sender_catalog.get("error"), "received": whatsapp_received,
            "sent": whatsapp_sent,
            "contacts": contacts, "groups": groups, "native_groups": native_groups, "assistants": assistant_settings,
            "system_accounts": ({
                **_system_whatsapp_center(settings),
                "sent": [{**row, "details": _event_payload(row.get("payload"))} for row in sent_rows if row["integration_name"] == "system-whatsapp-channel"],
                "separate_from_meta": True,
                "notice": "Linked system accounts are independent from the official Meta Business API.",
            } if system_admin else {"available": False, "admin_only": True, "accounts": [], "sent": []}),
        },
    })


def _system_whatsapp_slot(slot: int) -> int:
    if slot not in (1, 2):
        raise HTTPException(404, "Unknown system WhatsApp account")
    return slot


@app.get("/api/v1/communications/system-whatsapp", dependencies=[Depends(authorize_admin)])
def communication_system_whatsapp(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return json_ready(_system_whatsapp_center(settings))


@app.put("/api/v1/communications/system-whatsapp/settings", dependencies=[Depends(authorize_admin)])
def communication_save_system_whatsapp(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    stored = _save_system_whatsapp_settings(payload)
    with transaction() as (_, cursor):
        audit(cursor, "update", "system_whatsapp_accounts", estate_id(), stored, request.headers.get("X-Remote-User-Name") or "home-assistant")
    return json_ready(_system_whatsapp_center(get_settings()))


@app.post("/api/v1/communications/system-whatsapp/{slot}/connect", dependencies=[Depends(authorize_admin)])
def communication_connect_system_whatsapp(slot: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_connect(_system_whatsapp_slot(slot), bool((payload or {}).get("restart", False))))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/disconnect", dependencies=[Depends(authorize_admin)])
def communication_disconnect_system_whatsapp(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_disconnect(_system_whatsapp_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/relink", dependencies=[Depends(authorize_admin)])
def communication_relink_system_whatsapp(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_relink(_system_whatsapp_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.get("/api/v1/communications/system-whatsapp/{slot}/backup", dependencies=[Depends(authorize_admin)])
def communication_backup_system_whatsapp(slot: int) -> JSONResponse:
    slot = _system_whatsapp_slot(slot)
    try:
        return JSONResponse(
            json_ready(system_whatsapp_backup(slot)),
            headers={"Content-Disposition": f'attachment; filename="baiamonte-whatsapp-account-{slot}-backup.json"'},
        )
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/contacts", dependencies=[Depends(authorize_admin)])
def communication_add_system_whatsapp_contact(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    slot = _system_whatsapp_slot(slot)
    name = str(payload.get("name") or "").strip()[:120]
    number = re.sub(r"\D", "", str(payload.get("number") or ""))
    if len(number) < 7 or len(number) > 15:
        raise HTTPException(422, "Enter the complete international number without a leading +")
    try:
        result = system_whatsapp_add_contact(slot, name, number)
        with transaction() as (_, cursor):
            audit(cursor, "create", "system_whatsapp_contact", str(result.get("contact", {}).get("contact_id") or number), {"account_slot": slot, "name": name, "number": number}, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/contacts/import", dependencies=[Depends(authorize_admin)])
def communication_import_system_whatsapp_contacts(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    contacts = []
    for row in (payload.get("contacts") or [])[:2000]:
        name = str(row.get("name") or "").strip()[:120]
        number = re.sub(r"\D", "", str(row.get("number") or ""))
        if name and 7 <= len(number) <= 15:
            contacts.append({"name": name, "number": number})
    if not contacts:
        raise HTTPException(422, "No usable named phone contacts were found in that file")
    try:
        result = system_whatsapp_import_contacts(_system_whatsapp_slot(slot), contacts)
        with transaction() as (_, cursor):
            audit(cursor, "import", "system_whatsapp_contacts", str(slot), {"account_slot": slot, "imported": result.get("imported"), "paired": result.get("paired")}, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/catalog/refresh", dependencies=[Depends(authorize_admin)])
def communication_refresh_system_whatsapp_catalog(slot: int) -> dict[str, Any]:
    try:
        system_whatsapp_refresh_catalog(_system_whatsapp_slot(slot))
        return json_ready(_system_whatsapp_center(get_settings()))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.put("/api/v1/communications/system-whatsapp/{slot}/contacts/{contact_id:path}", dependencies=[Depends(authorize_admin)])
def communication_rename_system_whatsapp_contact(slot: int, contact_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()[:120]
    if not name:
        raise HTTPException(422, "Enter a contact name")
    try:
        result = system_whatsapp_rename_contact(_system_whatsapp_slot(slot), contact_id, name)
        with transaction() as (_, cursor):
            audit(cursor, "update", "system_whatsapp_contact", contact_id, {"account_slot": slot, "name": name}, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/history/sync", dependencies=[Depends(authorize_admin)])
def communication_sync_system_whatsapp_history(slot: int) -> dict[str, Any]:
    try:
        return json_ready(system_whatsapp_sync_history(_system_whatsapp_slot(slot)))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.get("/api/v1/communications/system-whatsapp/{slot}/chats/{chat_id:path}", dependencies=[Depends(authorize_admin)])
def communication_system_whatsapp_chat(slot: int, chat_id: str) -> dict[str, Any]:
    if not chat_id or len(chat_id) > 190:
        raise HTTPException(422, "Choose a visible chat")
    try:
        return json_ready(system_whatsapp_chat(_system_whatsapp_slot(slot), chat_id))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/membership/refresh", dependencies=[Depends(authorize_admin)])
def communication_refresh_system_whatsapp_membership(slot: int) -> dict[str, Any]:
    try:
        system_whatsapp_refresh_membership(_system_whatsapp_slot(slot))
        return json_ready(_system_whatsapp_center(get_settings()))
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/membership/{request_id:path}", dependencies=[Depends(authorize_admin)])
def communication_decide_system_whatsapp_membership(slot: int, request_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    slot = _system_whatsapp_slot(slot)
    decision = str(payload.get("decision") or "").lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(422, "Choose approve or reject")
    try:
        result = system_whatsapp_decide_membership(slot, request_id[:500], decision)
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'system-whatsapp-channel','internal','membership_decision',%s,'processed',%s)",
                (estate_id(), request_id[:190], json.dumps({"account_slot": slot, "request_id": request_id[:500], "decision": decision})),
            )
            audit(cursor, decision, "system_whatsapp_membership", request_id[:190], {"account_slot": slot, "decision": decision}, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except Exception as error:
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/api/v1/communications/system-whatsapp/{slot}/send", dependencies=[Depends(authorize_admin)])
def communication_send_system_whatsapp(slot: int, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    slot = _system_whatsapp_slot(slot)
    account = next(item for item in _system_whatsapp_settings()["accounts"] if item["slot"] == slot)
    if not account["send_enabled"]:
        raise HTTPException(403, "Sending is disabled for this linked system account")
    chat_id = str(payload.get("chat_id") or "").strip()[:190]
    body = str(payload.get("body") or "").strip()
    if not chat_id or not body or len(body) > 4096:
        raise HTTPException(422, "Choose a visible chat and enter a message of 1 to 4096 characters")
    if not _system_whatsapp_chat_allowed(account, chat_id):
        raise HTTPException(403, "This contact or group is outside the interaction scope for this system account")
    try:
        result = system_whatsapp_send(slot, chat_id, body)
        metadata = {"account_slot": slot, "chat_id": chat_id, "message_id": result.get("message_id"), "preview": body[:180]}
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'system-whatsapp-channel','outbound','message_sent',%s,'processed',%s)",
                (estate_id(), str(result.get("message_id") or new_id())[:190], json.dumps(metadata)),
            )
            audit(cursor, "send", "system_whatsapp_message", str(result.get("message_id") or chat_id), metadata, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except HTTPException:
        raise
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,error_message,payload) VALUES (%s,'system-whatsapp-channel','outbound','message_sent','failed',%s,%s)",
                (estate_id(), str(error)[:1000], json.dumps({"account_slot": slot, "chat_id": chat_id, "preview": body[:180]})),
            )
        raise HTTPException(502, str(error)[:300]) from error


@app.post("/internal/system-whatsapp/inbound")
def system_whatsapp_inbound(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    x_system_whatsapp_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    expected = os.environ.get("SYSTEM_WHATSAPP_BRIDGE_TOKEN", "")
    if not expected or not x_system_whatsapp_token or not hmac.compare_digest(expected, x_system_whatsapp_token):
        raise HTTPException(403, "Forbidden")
    slot = _system_whatsapp_slot(int(payload.get("account_slot") or 0))
    account = next(item for item in _system_whatsapp_settings()["accounts"] if item["slot"] == slot)
    chat_id = str(payload.get("chat_id") or "").strip()[:190]
    is_group = bool(payload.get("is_group"))
    source_enabled = account["ingest_groups"] if is_group else account["ingest_direct"]
    allowed = account["enabled"] and source_enabled and _system_whatsapp_chat_allowed(account, chat_id, is_group)
    if not allowed:
        return {"accepted": False, "reason": "Chat is not selected for ingestion"}
    message_id = re.sub(r"[^A-Za-z0-9_.:@=-]", "", str(payload.get("message_id") or ""))[:150]
    if not message_id:
        raise HTTPException(422, "Message ID is required")
    attachment = payload.get("attachment") if isinstance(payload.get("attachment"), dict) else None
    text = str(payload.get("text") or "").strip()
    sender_address = re.sub(r"(?::\d+)?@.+$", "", str(payload.get("sender_id") or chat_id)).strip()[:190]
    try:
        received_at = datetime.fromisoformat(str(payload.get("received_at") or "").replace("Z", "+00:00"))
        received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        received_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        if attachment:
            data = base64.b64decode(str(attachment.get("data_base64") or ""), validate=True)
            filename = str(attachment.get("filename") or f"system-whatsapp-{message_id}")[:180]
            media_type = str(attachment.get("content_type") or "application/octet-stream")[:120]
        else:
            data = text.encode("utf-8")
            filename = f"system-whatsapp-{slot}-{message_id}.txt"
            media_type = "text/plain"
        if not data and not text:
            return {"accepted": False, "reason": "Empty message"}
        digest = hashlib.sha256(data).hexdigest()
        duplicate = fetch_one(
            "SELECT id FROM intake_items WHERE estate_id=%s AND source='whatsapp' AND ABS(TIMESTAMPDIFF(SECOND,received_at,%s))<=120 "
            "AND ((sender_address=%s AND message_text=%s) OR (file_sha256=%s AND file_sha256 IS NOT NULL)) LIMIT 1",
            (estate_id(), received_at, sender_address, text, digest),
        )
        if duplicate:
            return {"accepted": True, "duplicate": True, "record_id": duplicate["id"]}
        record_id = save_intake_file(
            data, filename, media_type, "whatsapp",
            title=f"{account['label']} · {str(payload.get('chat_name') or 'WhatsApp chat')[:120]}",
            message_text=text or str(payload.get("attachment_error") or "Attachment received"),
            external_id=f"system-wa:{slot}:{message_id}",
            sender_name=str(payload.get("sender_name") or "WhatsApp contact")[:160],
            sender_address=sender_address,
        )
        with transaction() as (_, cursor):
            cursor.execute("UPDATE intake_items SET received_at=%s WHERE id=%s", (received_at, record_id))
    except IntegrityError:
        return {"accepted": True, "duplicate": True}
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)[:300]) from error
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'system-whatsapp-channel','inbound','message_received',%s,'received',%s)",
            (estate_id(), message_id, json.dumps({"account_slot": slot, "chat_id": chat_id, "is_group": is_group, "record_id": record_id, "message_type": payload.get("message_type")})),
        )
    if settings.openai_api_key:
        background_tasks.add_task(analyze_intake, record_id)
    return {"accepted": True, "record_id": record_id}


@app.get("/api/v1/communications/gmail/folders", dependencies=[Depends(authorize)])
def communication_gmail_folders() -> dict[str, Any]:
    try:
        return {"folders": gmail_folders()}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail folders failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/gmail/messages", dependencies=[Depends(authorize)])
def communication_gmail_messages(folder: str = "INBOX", view: str = "all", limit: int = 50) -> dict[str, Any]:
    try:
        return json_ready(gmail_messages(folder, view, limit))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail mailbox failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/gmail/messages/{uid}", dependencies=[Depends(authorize)])
def communication_gmail_message(uid: str, folder: str = "INBOX") -> dict[str, Any]:
    try:
        return json_ready(gmail_message(uid, folder))
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail message failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/gmail/messages/{uid}/download", dependencies=[Depends(authorize)])
def communication_gmail_download(uid: str, folder: str = "INBOX") -> Response:
    try:
        data, filename, content_type = gmail_download(uid, folder)
        return Response(data, media_type=content_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"})
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail download failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/gmail/messages/{uid}/attachments/{attachment_index}", dependencies=[Depends(authorize)])
def communication_gmail_attachment(uid: str, attachment_index: int, folder: str = "INBOX") -> Response:
    try:
        data, filename, content_type = gmail_download(uid, folder, attachment_index)
        return Response(data, media_type=content_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}"})
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail attachment failed: " + str(error)[:300]) from error


@app.patch("/api/v1/communications/gmail/messages/{uid}", dependencies=[Depends(authorize_write)])
def communication_gmail_action(uid: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        result = gmail_message_action(uid, str(payload.get("action") or ""), str(payload.get("folder") or "INBOX"))
        with transaction() as (_, cursor):
            audit(cursor, "gmail_message_action", "gmail_message", uid, {"action": result["action"], "folder": str(payload.get("folder") or "INBOX")}, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return result
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail action failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/gmail/send", dependencies=[Depends(authorize_write)])
def communication_send_gmail(payload: dict[str, Any]) -> dict[str, Any]:
    recipients = payload.get("recipients") or []
    if isinstance(recipients, str):
        recipients = [item.strip() for item in recipients.split(",") if item.strip()]
    try:
        return send_gmail_message(recipients, str(payload.get("subject") or ""), str(payload.get("body") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail send failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/gmail/send-files", dependencies=[Depends(authorize_write)])
async def communication_send_gmail_files(
    recipients: str = Form(...), subject: str = Form(...), body: str = Form(...), files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    try:
        attachments = []
        total_bytes = 0
        for file in files[:10]:
            data = await file.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Each attachment must be 20 MB or smaller")
            total_bytes += len(data)
            if total_bytes > 30 * 1024 * 1024:
                raise ValueError("The combined attachments must be 30 MB or smaller")
            if data:
                attachments.append((file.filename or "attachment", file.content_type or "application/octet-stream", data))
        return send_gmail_message([value.strip() for value in recipients.split(",")], subject, body, attachments)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Gmail send failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_admin)])
def communication_send_whatsapp(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return send_whatsapp_message(str(payload.get("recipient") or ""), str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp send failed: " + str(error)[:300]) from error


@app.put("/api/v1/communications/whatsapp/sender", dependencies=[Depends(authorize_admin)])
def communication_select_whatsapp_sender(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    phone_number_id = re.sub(r"\D", "", str(payload.get("phone_number_id") or ""))
    catalog = whatsapp_phone_numbers(force=True)
    allowed = {str(item.get("id") or "") for item in catalog.get("senders") or []}
    if not phone_number_id or phone_number_id not in allowed:
        raise HTTPException(422, "Choose a registered number from this WhatsApp Business Account")
    runtime_values: dict[str, Any] = {}
    try:
        runtime_values = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    runtime_values["whatsapp_active_phone_number_id"] = phone_number_id
    selected = next((item for item in catalog.get("senders") or [] if str(item.get("id")) == phone_number_id), {})
    business_account_id = re.sub(r"\D", "", str(selected.get("business_account_id") or ""))
    if not business_account_id:
        raise HTTPException(422, "The selected sender is not linked to a WhatsApp Business Account")
    runtime_values["whatsapp_active_business_account_id"] = business_account_id
    _write_runtime_options(runtime_values)
    clear_whatsapp_cache()
    with transaction() as (_, cursor):
        audit(cursor, "update", "whatsapp_sender", phone_number_id, {"business_account_id": business_account_id, "display_phone_number": selected.get("display_phone_number"), "verified_name": selected.get("verified_name"), "is_test": bool(selected.get("is_test"))}, request.headers.get("X-Remote-User-Name") or "api")
    return {"saved": True, "phone_number_id": phone_number_id, "business_account_id": business_account_id, "diagnostics": whatsapp_diagnostics(force=True), "templates": whatsapp_templates(force=True)}


@app.post("/api/v1/communications/whatsapp/send-file", dependencies=[Depends(authorize_admin)])
async def communication_send_whatsapp_file(
    recipient: str = Form(...), body: str = Form(""), recipient_type: str = Form("individual"), file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        data = await file.read(20 * 1024 * 1024 + 1)
        return send_whatsapp_media(recipient, data, file.filename or "attachment", file.content_type or "application/octet-stream", body, recipient_type)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp attachment failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/whatsapp/broadcast", dependencies=[Depends(authorize_admin)])
def communication_send_whatsapp_list(payload: dict[str, Any]) -> dict[str, Any]:
    group_id = re.sub(r"[^a-zA-Z0-9_.:@-]", "", str(payload.get("group_id") or ""))
    if group_id:
        try:
            result = send_whatsapp_message(group_id, str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"), "group")
            return {"completed": True, "sent": 1, "failed": 0, "native_group": True, "results": [result]}
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(502, "WhatsApp group send failed: " + str(error)[:300]) from error
    recipients = []
    for value in (payload.get("recipients") or [])[:20]:
        number = re.sub(r"\D", "", str(value))
        if len(number) >= 8 and number not in recipients:
            recipients.append(number)
    if not recipients:
        raise HTTPException(422, "Choose at least one contact")
    results = []
    for number in recipients:
        try:
            results.append({"recipient": number, "sent": True, "result": send_whatsapp_message(number, str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"))})
        except Exception as error:
            results.append({"recipient": number, "sent": False, "error": str(error)[:300]})
    return {"completed": True, "sent": sum(1 for row in results if row["sent"]), "failed": sum(1 for row in results if not row["sent"]), "results": results}


@app.get("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize_admin)])
def communication_whatsapp_groups(refresh: bool = False) -> dict[str, Any]:
    return json_ready(whatsapp_native_groups(force=refresh))


@app.post("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize_admin)])
def communication_create_whatsapp_group(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        result = create_whatsapp_group(
            str(payload.get("subject") or ""),
            str(payload.get("description") or ""),
            str(payload.get("join_approval_mode") or "auto_approve"),
        )
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload) "
                "VALUES (%s,'whatsapp-channel','outbound','group_create','processed',%s)",
                (estate_id(), json.dumps(result)),
            )
            audit(cursor, "create", "whatsapp_group", str(result.get("id") or result.get("group_id") or "pending"), result, request.headers.get("X-Remote-User-Name") or "home-assistant")
        return json_ready(result)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp group creation failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/whatsapp/groups/{group_id}/invite-link", dependencies=[Depends(authorize_admin)])
def communication_whatsapp_group_invite(group_id: str) -> dict[str, Any]:
    try:
        return json_ready(whatsapp_group_invite_link(group_id))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp invite link failed: " + str(error)[:300]) from error


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


@app.put("/api/v1/communications/whatsapp/contacts", dependencies=[Depends(authorize_admin)])
def save_whatsapp_contacts(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    contacts = []
    for row in (payload.get("contacts") or [])[:100]:
        name = str((row or {}).get("name") or "").strip()[:180]
        number = re.sub(r"\D", "", str((row or {}).get("number") or ""))
        role = str((row or {}).get("role") or "").strip()[:180]
        assistant = str((row or {}).get("assistant") or "off").lower()
        language = str((row or {}).get("language") or "auto").lower()
        reply_mode = str((row or {}).get("reply_mode") or "match").lower()
        administrator = bool((row or {}).get("administrator"))
        if assistant not in {"off", "reception", "reporter", "manager"}:
            assistant = "off"
        if language not in {"auto", "en", "it"}:
            language = "auto"
        if reply_mode not in {"text", "voice", "both", "match"}:
            reply_mode = "match"
        if name and len(number) >= 8:
            contacts.append({"name": name, "number": number, "role": role, "assistant": assistant, "language": language, "reply_mode": reply_mode, "administrator": administrator})
    known_numbers = {contact["number"] for contact in contacts}
    groups = []
    for row in (payload.get("groups") or [])[:30]:
        name = str((row or {}).get("name") or "").strip()[:180]
        group_id = re.sub(r"[^a-zA-Z0-9_.:@-]", "", str((row or {}).get("group_id") or ""))[:250]
        members = []
        for value in (row or {}).get("members") or []:
            number = re.sub(r"\D", "", str(value))
            if number in known_numbers and number not in members:
                members.append(number)
        if name and (members or group_id):
            groups.append({"name": name, "members": members, "group_id": group_id or None, "kind": "native_group" if group_id else "delivery_list"})
    stored = {"contacts": contacts, "groups": groups, "updated_by": request.headers.get("X-Remote-User-Name") or "api"}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
            (estate_id(), json.dumps(stored)),
        )
    return {"saved": True, "contacts": contacts, "groups": groups}


@app.get("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize_admin)])
def get_whatsapp_assistants() -> dict[str, Any]:
    try:
        catalog = home_assistant_manager_devices()
        camera_catalog = home_assistant_manager_camera_catalog()
    except Exception:
        catalog = []
        camera_catalog = []
    return json_ready({**_whatsapp_assistant_settings(), "home_assistant_device_catalog": catalog, "home_assistant_camera_catalog": camera_catalog})


@app.put("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize_admin)])
def save_whatsapp_assistants(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed_controls = {"full_refresh", "weather", "cistern", "disease", "public_feed"}
    try:
        safe_catalog = {item["entity_id"] for item in home_assistant_manager_devices()}
        safe_camera_catalog = {item["entity_id"] for item in home_assistant_manager_camera_catalog()}
    except Exception as error:
        raise HTTPException(503, "Home Assistant devices are temporarily unavailable; settings were not changed") from error
    stored = {
        "reception_enabled": bool(payload.get("reception_enabled")),
        "manager_enabled": bool(payload.get("manager_enabled")),
        "unknown_reception": bool(payload.get("unknown_reception")),
        "trusted_ingestion": bool(payload.get("trusted_ingestion")),
        "manager_controls": [code for code in payload.get("manager_controls", []) if code in allowed_controls],
        "reply_limit_unknown": min(20, max(1, int(payload.get("reply_limit_unknown") or 6))),
        "reply_limit_manager": min(100, max(1, int(payload.get("reply_limit_manager") or 30))),
        "voice": str(payload.get("voice") or "marin") if str(payload.get("voice") or "marin") in {"marin", "coral", "shimmer", "nova"} else "marin",
        "home_assistant_entities": [str(value) for value in payload.get("home_assistant_entities", []) if str(value) in safe_catalog][:100],
        "home_assistant_camera_entities": [str(value) for value in payload.get("home_assistant_camera_entities", []) if str(value) in safe_camera_catalog][:100],
        "updated_by": request.headers.get("X-Remote-User-Name") or "api",
    }
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_assistants',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (estate_id(), json.dumps(stored)))
        audit(cursor, "update", "whatsapp_assistants", "configuration", {key: value for key, value in stored.items() if key != "updated_by"}, stored["updated_by"])
    return {"saved": True, **stored}


@app.post("/api/v1/communications/whatsapp/assistants/invite", dependencies=[Depends(authorize_admin)])
def invite_whatsapp_manager(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    recipient = re.sub(r"\D", "", str(payload.get("recipient") or ""))
    assignment = _whatsapp_sender_profile(recipient)
    if assignment["profile"] not in {"manager", "reporter"}:
        raise HTTPException(422, "Assign this contact as Reporter or Manager and save the address book first")
    template_name = str(payload.get("template_name") or "")
    template_language = str(payload.get("template_language") or "")
    catalog = whatsapp_templates(force=True)
    if catalog.get("error"):
        raise HTTPException(503, "Approved WhatsApp templates could not be checked: " + str(catalog["error"])[:220])
    template = approved_whatsapp_template(catalog.get("templates") or [], template_name, template_language)
    if not template:
        raise HTTPException(422, "Choose an approved Meta template and language for first contact")
    try:
        result = send_whatsapp_message(recipient, template_name=template["name"], template_language=template["language"])
    except Exception as error:
        raise HTTPException(502, "Approved invitation could not be sent: " + str(error)[:260]) from error
    with transaction() as (_, cursor):
        audit(cursor, "send", "whatsapp_assistant_invitation", recipient[-6:], {"profile": assignment["profile"], "contact_language": assignment["language"], "template_name": template["name"], "template_language": template["language"]}, request.headers.get("X-Remote-User-Name") or "home-assistant")
    return {"sent": True, "recipient": recipient, "profile": assignment["profile"], "template_name": template["name"], "template_language": template["language"], "awaiting_reply": True, "result": result}


@app.get("/api/v1/intake/{record_id}", dependencies=[Depends(authorize)])
def intake_detail(record_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT id,source,sender_name,sender_address,received_at,title,message_text,original_filename,stored_path,file_sha256,media_type,classification,ai_summary,extracted_data,review_status,review_reason,reviewed_by,reviewed_at,processing_error FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row:
        raise HTTPException(404, "Inbox item not found")
    if isinstance(row.get("extracted_data"), str):
        try:
            row["extracted_data"] = json.loads(row["extracted_data"])
        except json.JSONDecodeError:
            row["extracted_data"] = None
    row["linked_records"] = fetch_all(
        "SELECT DISTINCT ea.entity_id,ea.entity_type,ls.sample_name,ls.lab_date,ls.vintage_year "
        "FROM entity_attachments ea LEFT JOIN lab_samples ls ON ea.entity_type='lab_sample' AND ls.id=ea.entity_id "
        "WHERE ea.estate_id=%s AND ea.file_sha256=%s ORDER BY ls.sample_name",
        (estate_id(), row.get("file_sha256")),
    ) if row.get("file_sha256") else []
    row.pop("stored_path", None)
    row.pop("file_sha256", None)
    return json_ready(row)


@app.get("/api/v1/intake/{record_id}/file", dependencies=[Depends(authorize)])
def intake_source_file(record_id: str, download: bool = Query(False)) -> FileResponse:
    row = fetch_one("SELECT original_filename,stored_path,media_type FROM intake_items WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
    if not row or not row.get("stored_path") or not Path(row["stored_path"]).is_file():
        raise HTTPException(404, "Source file is not available")
    filename = row.get("original_filename") or "intake-source"
    disposition = "attachment" if download else "inline"
    return FileResponse(
        row["stored_path"],
        media_type=row.get("media_type") or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{str(filename).replace(chr(34), "")}"'},
    )


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
    extracted = item.get("extracted_data")
    if isinstance(extracted, str):
        try:
            extracted = json.loads(extracted)
        except json.JSONDecodeError:
            extracted = {}
    suggestions = (extracted or {}).get("suggested_database_records") or []
    expected_lab_records = 0
    for record in suggestions:
        if "lab" not in str(record.get("destination_section") or record.get("section") or record.get("record_type") or "").casefold():
            continue
        fields = record.get("fields") or record.get("values") or {}
        results = fields.get("results") if isinstance(fields.get("results"), list) else []
        labels = [str(item.get("sample_name") or item.get("source_sample_label") or item.get("variety_name") or item.get("wine_type") or "").strip() for item in results if isinstance(item, dict)]
        distinct_labels = {label.casefold() for label in labels if label}
        combined_names = [name.strip() for name in re.split(r"\s*(?:/|\+|,|;|\band\b|\be\b)\s*", str(fields.get("sample_name") or fields.get("source_sample_label") or ""), flags=re.IGNORECASE) if name.strip()]
        expected_lab_records += max(1, len(distinct_labels), len(combined_names) if len(combined_names) == len(results) else 0)
    existing_attachment = fetch_one(
        "SELECT id FROM entity_attachments WHERE estate_id=%s AND entity_type=%s AND entity_id=%s AND file_sha256=%s LIMIT 1",
        (estate_id(), entity_type, entity_id, item.get("file_sha256")),
    ) if item.get("file_sha256") else None
    attachment_id = existing_attachment["id"] if existing_attachment else new_id()
    with transaction() as (_, cursor):
        if not existing_attachment:
            cursor.execute(
                "INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (attachment_id, estate_id(), entity_type, entity_id, item.get("original_filename") or "incoming-item", item.get("stored_path"), item.get("media_type"), item.get("file_sha256"), item.get("ai_summary") or item.get("title"), request.headers.get("X-Remote-User-Name") or "api"),
            )
        cursor.execute(
            "SELECT COUNT(DISTINCT entity_id) linked_count FROM entity_attachments WHERE estate_id=%s AND entity_type=%s AND file_sha256=%s",
            (estate_id(), entity_type, item.get("file_sha256")),
        )
        linked_count = int((cursor.fetchone() or {}).get("linked_count") or 0)
        remaining_records = max(0, expected_lab_records - linked_count) if entity_type == "lab_sample" and expected_lab_records > 1 else 0
        if remaining_records == 0:
            cursor.execute("UPDATE intake_items SET review_status='approved',reviewed_by=%s,reviewed_at=NOW() WHERE id=%s", (request.headers.get("X-Remote-User-Name") or "api", record_id))
        audit(cursor, "approve", "intake", record_id, {"entity_type": entity_type, "entity_id": entity_id, "attachment_id": attachment_id})
    return {"saved": True, "attachment_id": attachment_id, "entity_id": entity_id, "duplicate_link": bool(existing_attachment), "remaining_records": remaining_records}


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


@app.post("/api/v1/intake/mac", status_code=201, dependencies=[Depends(authorize_write)])
async def submit_mac_intake(payload: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    title = str(payload.get("title") or "Mac / ChatGPT vineyard update").strip()[:255]
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(422, "A message is required")
    if len(message.encode("utf-8")) > 512_000:
        raise HTTPException(413, "Mac update text must be 500 KB or smaller")
    external_id = str(payload.get("external_id") or hashlib.sha256(message.encode()).hexdigest())[:190]
    try:
        existing = fetch_one("SELECT id,review_status FROM intake_items WHERE estate_id=%s AND source='codex' AND external_id=%s", (estate_id(), external_id))
        if existing:
            return {"id": existing.get("id"), "status": existing.get("review_status") or "already_received", "message": "This Mac update was already received."}
        record_id = save_intake_file(message.encode("utf-8"), f"mac-{external_id}.txt", "text/plain", "codex", title, message, external_id, "Codex on David's Mac", "local")
        background_tasks.add_task(analyze_intake, record_id)
        return {"id": record_id, "status": "processing", "message": "Submitted to the review inbox; no authoritative record was changed."}
    except IntegrityError:
        existing = fetch_one("SELECT id,review_status FROM intake_items WHERE estate_id=%s AND source='codex' AND external_id=%s", (estate_id(), external_id)) or {}
        return {"id": existing.get("id"), "status": existing.get("review_status") or "already_received", "message": "This Mac update was already received."}


@app.post("/api/v1/intake/{record_id}/analyze", dependencies=[Depends(authorize_write)])
async def analyze_intake_item(record_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(analyze_intake, record_id, allow_reanalysis=True)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@app.patch("/api/v1/intake/{record_id}/review", dependencies=[Depends(authorize_write)])
def review_intake(record_id: str, payload: dict[str, Any], request: Request) -> dict[str, bool]:
    status = payload.get("review_status")
    if status not in {"approved", "rejected", "ready_for_review"}:
        raise HTTPException(422, "Unsupported review status")
    review_reason = str(payload.get("review_reason") or "").strip()[:2000] or None
    if status == "rejected" and not review_reason:
        raise HTTPException(422, "Enter why this item is being rejected")
    with transaction() as (_, cursor):
        changed = cursor.execute("UPDATE intake_items SET review_status=%s,review_reason=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, review_reason, request.headers.get("X-Remote-User-Name") or "api", record_id, estate_id()))
        if not changed:
            raise HTTPException(404, "Intake item not found")
    return {"saved": True}


@app.post("/api/v1/intake/flush-completed", dependencies=[Depends(authorize_write)])
def flush_completed_intake(request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT COUNT(*) n FROM intake_items WHERE estate_id=%s AND review_status IN ('approved','rejected')",
            (estate_id(),),
        )
        count = int((cursor.fetchone() or {}).get("n") or 0)
        cursor.execute(
            "UPDATE intake_items SET review_status='archived',archived_at=NOW() "
            "WHERE estate_id=%s AND review_status IN ('approved','rejected')",
            (estate_id(),),
        )
        audit(cursor, "archive", "intake", "completed", {"count": count}, actor)
    return {"flushed": count, "message": "Completed items were archived; source files and audit history were retained."}


@app.post("/api/v1/intake/clear-routine-whatsapp", dependencies=[Depends(authorize_write)])
def clear_routine_whatsapp(request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE intake_items i SET i.review_status='archived',i.review_reason='No database action required',"
            "i.reviewed_by=%s,i.reviewed_at=NOW(),i.archived_at=NOW() "
            "WHERE i.estate_id=%s AND i.source='whatsapp' AND i.review_status='ready_for_review' "
            "AND COALESCE(i.classification,'other')='other' "
            "AND COALESCE(JSON_LENGTH(JSON_EXTRACT(i.extracted_data,'$.facts')),0)=0 "
            "AND COALESCE(JSON_LENGTH(JSON_EXTRACT(i.extracted_data,'$.suggested_database_records')),0)=0 "
            "AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.estate_id=i.estate_id AND a.status IN ('open','acknowledged') "
            "AND JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intake_id'))=i.id "
            "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intervention_required')),'false')='true')",
            (actor, estate_id()),
        )
        count = int(cursor.rowcount or 0)
        audit(cursor, "archive", "intake", "routine-whatsapp", {"count": count, "rule": "other classification, no facts, no proposed records, no open intervention"}, actor)
    _reconcile_answered_whatsapp_notices()
    return {"cleared": count, "message": "Routine WhatsApp conversations were archived; source messages and audit history were retained."}


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
    if not settings.whatsapp_app_secret:
        raise HTTPException(503, "WhatsApp App Secret is required before accepting webhook messages")
    expected = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid webhook signature")
    payload = json.loads(raw or b"{}")
    allowed = {number.strip().replace("+", "") for number in settings.whatsapp_allowed_numbers.split(",") if number.strip()}
    expected_receiver_phone_number_id = re.sub(r"\D", "", str(whatsapp_phone_number_id() or ""))
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            receiver_phone_number_id = re.sub(r"\D", "", str((value.get("metadata") or {}).get("phone_number_id") or ""))
            field = str(change.get("field") or "")
            if receiver_phone_number_id and expected_receiver_phone_number_id and receiver_phone_number_id != expected_receiver_phone_number_id:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                        "VALUES (%s,'whatsapp-channel','inbound','receiver_ignored',%s,'processed',%s)",
                        (estate_id(), receiver_phone_number_id[:190], json.dumps({"field": field, "reason": "receiver_phone_number_id_mismatch"})),
                    )
                continue
            if field in {"group_lifecycle_update", "group_participants_update", "group_settings_update", "group_status_update"}:
                group_external_id = str(value.get("group_id") or value.get("id") or new_id())[:190]
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                        "VALUES (%s,'whatsapp-channel','inbound',%s,%s,'received',%s)",
                        (estate_id(), field, group_external_id, json.dumps(value)),
                    )
            for status_item in value.get("statuses", []):
                message_id = str(status_item.get("id") or "")[:190] or None
                delivery_status = str(status_item.get("status") or "unknown")[:60]
                event_status = "failed" if delivery_status == "failed" else "processed" if delivery_status in {"sent", "delivered", "read"} else "received"
                errors = status_item.get("errors") or []
                with transaction() as (_, cursor):
                    cursor.execute(
                        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
                        "AND event_type='message_sent' AND external_id=%s ORDER BY id DESC LIMIT 1 FOR UPDATE",
                        (estate_id(), message_id),
                    )
                    sent_row = cursor.fetchone()
                    if sent_row:
                        sent_payload = _event_payload(sent_row.get("payload"))
                        current_status = str(sent_payload.get("delivery_status") or "accepted").lower()
                        ranks = {"accepted": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}
                        if ranks.get(delivery_status, -1) >= ranks.get(current_status, -1):
                            sent_payload["delivery_status"] = delivery_status
                            sent_payload["delivery_timestamp"] = status_item.get("timestamp")
                            if status_item.get("conversation"):
                                sent_payload["conversation"] = status_item.get("conversation")
                            if status_item.get("pricing"):
                                sent_payload["pricing"] = status_item.get("pricing")
                            cursor.execute(
                                "UPDATE integration_events SET status=%s,payload=%s,error_message=%s WHERE id=%s",
                                (event_status, json.dumps(sent_payload), json.dumps(errors)[:1000] if errors else None, sent_row["id"]),
                            )
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload,error_message) VALUES (%s,'whatsapp-channel','inbound','message_status',%s,%s,%s,%s)",
                        (estate_id(), message_id, event_status, json.dumps(status_item), json.dumps(errors)[:1000] if errors else None),
                    )
            contacts = {contact.get("wa_id"): (contact.get("profile") or {}).get("name") for contact in value.get("contacts", [])}
            for message in value.get("messages", []):
                sender = str(message.get("from") or "").replace("+", "")
                sender_allowed = not allowed or sender in allowed
                sender_assignment = _whatsapp_sender_profile(sender)
                _remember_whatsapp_contact(sender, contacts.get(sender))
                message_type = message.get("type") or "unknown"
                typed_content = message.get(message_type)
                media = typed_content if isinstance(typed_content, dict) else {}
                body = (message.get("text") or {}).get("body") or media.get("caption") or ""
                message_id = str(message.get("id") or new_id())
                group_id = str(message.get("group_id") or "")[:300]
                source_title = f"WhatsApp group {group_id[-10:]} · {message_type}" if group_id else f"WhatsApp {message_type}"
                saved_any = False
                if body:
                    try:
                        record_id = save_intake_file(body.encode(), f"whatsapp-{message_id}.txt", "text/plain", "whatsapp", source_title, body, message_id + ":body", contacts.get(sender), sender)
                        saved_any = True
                        if sender_allowed:
                            if group_id and settings.openai_api_key:
                                _start_background_task(_analyze_intake_background(record_id))
                            else:
                                _start_background_task(_handle_whatsapp_assistant(sender, body, message_id, record_id, group_id))
                        else:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                    except IntegrityError:
                        pass
                media_id = str(media.get("id") or "") if message_type in {"image", "document", "audio", "video", "sticker"} else ""
                if media_id:
                    try:
                        data, generated_name, content_type = await asyncio.to_thread(download_whatsapp_media, media_id)
                        filename = str(media.get("filename") or generated_name)
                        media_title = f"{source_title}: {filename}"
                        record_id = save_intake_file(data, filename, content_type, "whatsapp", media_title, body, message_id + ":media", contacts.get(sender), sender)
                        saved_any = True
                        if not sender_allowed:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                        elif message_type == "audio" and not group_id and settings.openai_api_key and sender_assignment["profile"] in {"manager", "reporter"}:
                            _start_background_task(_handle_whatsapp_voice(sender, data, filename, message_id, contacts.get(sender) or sender, group_id))
                            _start_background_task(_analyze_intake_background(record_id))
                        elif not body and not group_id:
                            media_prompt = {
                                "image": "Photo received for vineyard review",
                                "document": "Document received for vineyard review",
                                "video": "Video received for vineyard review",
                                "sticker": "Sticker received",
                                "audio": "Voice note received for vineyard review",
                            }.get(message_type, "Attachment received for vineyard review")
                            _start_background_task(_handle_whatsapp_assistant(sender, media_prompt, message_id, record_id, group_id))
                        elif settings.openai_api_key:
                            _start_background_task(_analyze_intake_background(record_id))
                    except IntegrityError:
                        pass
                    except Exception as error:
                        with transaction() as (_, cursor):
                            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message) VALUES (%s,'whatsapp-channel','inbound','media_download',%s,'failed',%s)", (estate_id(), message_id[:190], str(error)[:1000]))
                        if sender_allowed and not group_id:
                            _start_background_task(_send_whatsapp_assistant_reply(sender, "Allegato ricevuto, ma il download non è riuscito. L'errore è stato registrato." if sender_assignment["language"] == "it" else "Attachment received, but download failed. The error was logged.", sender_assignment))
                if not body and not media_id:
                    fallback = json.dumps({"message_type": message_type, "content": typed_content, "context": message.get("context")}, ensure_ascii=False, default=str)[:12000]
                    try:
                        record_id = save_intake_file(fallback.encode(), f"whatsapp-{message_id}-{message_type}.json", "application/json", "whatsapp", source_title, fallback, message_id + ":unsupported", contacts.get(sender), sender)
                        saved_any = True
                        if not sender_allowed:
                            quarantine_intake(record_id, "Sender is not on the configured WhatsApp allowlist")
                        elif not group_id:
                            _start_background_task(_handle_whatsapp_assistant(sender, f"WhatsApp {message_type} message received for review", message_id, record_id, group_id))
                    except IntegrityError:
                        pass
                if saved_any:
                    route = "quarantine" if not sender_allowed else "group_review" if group_id else sender_assignment["profile"] if sender_assignment["profile"] != "off" else "administrator_review"
                    with transaction() as (_, cursor):
                        cursor.execute(
                            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','message_received',%s,'received',%s)",
                            (estate_id(), message_id[:190], json.dumps({"sender": sender, "sender_allowed": sender_allowed, "message_type": message_type, "route": route, "group_id": group_id or None, "phone_number_id": receiver_phone_number_id or None})),
                        )
    return {"received": True}


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


@app.get("/api/v1/history/overview", dependencies=[Depends(authorize)])
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


@app.get("/weather-map/{path:path}")
def weather_map_proxy(path: str, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    configured_url = str(runtime_option("tv_adsb_url", settings.tv_adsb_url) or "").strip()
    parts = urllib.parse.urlsplit(configured_url)
    if parts.scheme and parts.netloc:
        base_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
        configured_path = parts.path.rstrip("/")
    else:
        clean_url = configured_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        configured_path = "/tv" if clean_url.endswith("/tv") else ""
        base_url = clean_url.removesuffix("/tv").rstrip("/")
    if not base_url:
        raise HTTPException(503, "The precipitation map service is not configured")
    safe_path = urllib.parse.quote(path or "", safe="/@:._~!$&'()*+,;=-")
    root_path = configured_path or "/tv"
    upstream_path = f"/{safe_path}" if safe_path else root_path
    upstream_url = f"{base_url}{upstream_path}"
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


def _versioned_html(filename: str) -> HTMLResponse:
    document = (static_dir / filename).read_text(encoding="utf-8").replace("__ASSET_VERSION__", addon_version())
    return HTMLResponse(document, headers={"Cache-Control": "no-cache"})


@app.get("/")
def index() -> HTMLResponse:
    return _versioned_html("index.html")


@app.get("/crew")
def crew_entry_page() -> FileResponse:
    return FileResponse(static_dir / "crew.html")


@app.get("/display")
def vineyard_display_page() -> HTMLResponse:
    return _versioned_html("display.html")


app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
