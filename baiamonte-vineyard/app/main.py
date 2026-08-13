from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
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

from .ai_usage import ai_cost_summary, save_ai_cost_settings
from .config import RUNTIME_OPTIONS_PATH, Settings, addon_version, get_settings, runtime_option
from .cellar_demo import apply_live_sensor_readings, cellar_guardrails, demo_cellar, demo_enabled, evaluate_cellar_tanks, live_sensor_entity_ids
from .db import fetch_all, fetch_one, run_migrations, transaction
from .display_data import display_payload, system_status_payload, weather_context_payload
from .fattureincloud import pull_fattureincloud
from .ha_auth import home_assistant_token
from .etna import etna_status
from .intelligence import CISTERN_SNAPSHOT_PATH, analyze_intake, ask_assistant, control_home_assistant_manager_device, create_whatsapp_group, download_whatsapp_media, gmail_mailbox_status, home_assistant_manager_devices, home_assistant_state_map, integration_loop, poll_gmail_once, predict_next_treatment, refresh_disease_pressure, resolve_home_assistant_control_request, run_full_refresh, run_named_process, save_intake_file, send_gmail_message, send_whatsapp_media, send_whatsapp_message, synthesize_whatsapp_voice, transcribe_whatsapp_voice, whatsapp_chatbot_reply, whatsapp_diagnostics, whatsapp_group_invite_link, whatsapp_native_groups, whatsapp_templates
from .mailbox import gmail_download, gmail_folders, gmail_message, gmail_message_action, gmail_messages
from .imessage import imessage_conversations, imessage_status, send_imessage
from .process_control import PROCESS_ORDER, process_controls, save_process_controls
from .models import (
    ActivityCreate,
    BlockCreate,
    CashTransactionCreate,
    FinancialDocumentCreate,
    HarvestCreate,
    LabSampleCreate,
    ParcelMapUpdate,
    TaskCreate,
    TaskStatusUpdate,
    VarietyCreate,
    WeatherObservationCreate,
)
from .quick_entry import save_quick_entry
from .service import audit, estate_id, json_ready, new_id, public_harvest_feed, season_for_year
from .social import publish_facebook, publish_instagram, social_dashboard
from .weather_history import import_baiamonte_weather_csv


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
    """Persist GUI-managed options even when Supervisor API access is unavailable."""
    RUNTIME_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME_OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
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


def authorize_admin(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    authorize(request, x_api_key, settings)
    if settings.api_key and x_api_key == settings.api_key:
        return
    if (request.headers.get("X-Remote-User-Name") or "").strip().casefold() == "rahamin":
        return
    raise HTTPException(status_code=403, detail="System controls are limited to the vineyard administrator")


def authorize_crew(x_crew_token: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.crew_entry_token or x_crew_token != settings.crew_entry_token:
        raise HTTPException(status_code=401, detail="Valid crew entry code required")


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_migrations()
    tasks = [asyncio.create_task(integration_loop())]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Baiamonte Vineyard API", version="1.0.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
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
.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]{display:none!important;visibility:hidden!important}
.estate-map-marker,[class*="estate-marker"],[class*="home-marker"]{display:block!important;visibility:visible!important}
.map-controls,.weather-status,.weather-attribution,.altitude-legend,.map-attribution{z-index:40!important}
@media(prefers-reduced-motion:reduce){.sweep,.range-ring{animation:none!important}}
</style>
<script id="baiamonte-weather-map-cleanup">
(()=>{const hideAircraft=()=>document.querySelectorAll('.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]').forEach(node=>{node.style.setProperty('display','none','important');node.setAttribute('aria-hidden','true')});document.addEventListener('DOMContentLoaded',()=>{hideAircraft();new MutationObserver(hideAircraft).observe(document.body,{childList:true,subtree:true})})})();
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
            "admin": normalized == "rahamin" or username == "api",
        },
    }


PROCESS_INTEGRATIONS = {
    "full_refresh": "full-system-refresh", "planning": "google-planning", "weather": "home-assistant-weather", "cistern": "cistern-camera-level", "gmail": "gmail-intake",
    "finance": "fattureincloud", "etna": "etna-monitor", "public_feed": "public-harvest-publisher",
    "traffic": "home-assistant-traffic", "disease": "disease-pressure", "alerts": "operational-alerts",
}


@app.get("/api/v1/admin/control", dependencies=[Depends(authorize_admin)])
def admin_control(request: Request) -> dict[str, Any]:
    controls = process_controls()
    settings = get_settings()
    latest = {row["integration_name"]: row for row in fetch_all(
        "SELECT e.integration_name,e.status,e.occurred_at,e.error_message,e.payload FROM integration_events e "
        "JOIN (SELECT integration_name,MAX(id) id FROM integration_events WHERE estate_id=%s GROUP BY integration_name) x ON x.id=e.id",
        (estate_id(),),
    )}
    now = datetime.now()
    processes = []
    for code in PROCESS_ORDER:
        item = controls["processes"][code]
        # Keep the control page available if a new scheduled process is added
        # before its integration-event name is explicitly registered.
        event = latest.get(PROCESS_INTEGRATIONS.get(code, code)) or {}
        occurred = event.get("occurred_at")
        next_run = occurred + timedelta(minutes=item["interval_minutes"]) if occurred and item["enabled"] and not controls["paused"] else None
        age_minutes = max(0, int((now - occurred).total_seconds() / 60)) if occurred else None
        if controls["paused"] or not item["enabled"]:
            health = "paused"
        elif event.get("status") == "failed":
            health = "error"
        elif age_minutes is None:
            health = "waiting"
        elif age_minutes > item["interval_minutes"] * 2 + 2:
            health = "stale"
        else:
            health = "healthy"
        processes.append({**item, "code": code, "health": health, "last_status": event.get("status"), "last_run": occurred, "next_run": next_run, "last_error": event.get("error_message")})
    review = fetch_one("SELECT COUNT(*) total,SUM(review_status='ready_for_review') ready,SUM(review_status='failed') failed FROM intake_items WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed')", (estate_id(),)) or {}
    review_age = fetch_one("SELECT MIN(received_at) oldest_pending_at FROM intake_items WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed')", (estate_id(),)) or {}
    recent_errors = fetch_one("SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND status='failed' AND occurred_at >= DATE_SUB(NOW(),INTERVAL 24 HOUR)", (estate_id(),)) or {}
    recovery_errors = fetch_all(
        "SELECT id,integration_name,event_type,error_message,occurred_at FROM integration_events WHERE estate_id=%s AND status='failed' ORDER BY occurred_at DESC LIMIT 30",
        (estate_id(),),
    )
    failed_intake = fetch_all(
        "SELECT id,source,title,original_filename,processing_error,received_at occurred_at FROM intake_items WHERE estate_id=%s AND review_status='failed' ORDER BY received_at DESC LIMIT 20",
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
    return json_ready({
        "paused": controls["paused"], "updated_at": controls.get("updated_at"), "updated_by": controls.get("updated_by"),
        "checked_at": now, "processes": processes, "review_queue": review,
        "connections": {
            "mac_api": bool(settings.mcp_server_token or settings.api_key), "gmail": bool(settings.gmail_address and settings.gmail_app_password),
            "whatsapp": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id), "website": bool(settings.public_publish_url),
        },
        "runtime": {
            "version": addon_version(), "uptime_seconds": int(time.monotonic() - APP_STARTED_MONOTONIC),
            "database": "connected", "storage": storage_summary, "attachment_count": int(attachment_count.get("total") or 0),
            "processing_errors_24h": int(recent_errors.get("total") or 0), "oldest_review_at": review_age.get("oldest_pending_at"),
        },
        "mac_setup": {
            "endpoint": "http://192.168.0.10:8100/mcp", "token_configured": bool(settings.mcp_server_token),
            "writes_enabled": bool(settings.mcp_allow_writes), "allowed_host_ready": any(item.startswith("192.168.0.10:") for item in mcp_hosts),
            "setup_warnings": setup_warnings,
        },
        "ai_cost": ai_cost_summary(),
        "recovery_errors": [
            {**row, "kind": "integration", "recoverable": row["integration_name"] in set(PROCESS_INTEGRATIONS.values())} for row in recovery_errors
        ] + [{**row, "kind": "intake", "recoverable": True} for row in failed_intake],
    })


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
    return json_ready({"values": values, "display_url": "http://192.168.0.10:8101/", "saved_live": True})


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


@app.post("/api/v1/admin/run/{code}", dependencies=[Depends(authorize_admin)])
async def run_admin_process(code: str) -> dict[str, Any]:
    try:
        return await run_named_process(code)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
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
    try:
        apply_live_sensor_readings(tanks, settings, home_assistant_state_map(live_sensor_entity_ids(settings)))
    except Exception:
        pass
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
        row = saved.get(alert_type) or {
            "alert_type": alert_type, "enabled": 1, "min_severity": "warning",
            "notify_home_assistant": 1, "notify_email": 0, "notify_whatsapp": 0,
            "email_recipients": "", "whatsapp_recipients": "",
        }
        preferences.append({**row, "label": label})
    return json_ready({
        "preferences": preferences,
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


def _event_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def _whatsapp_contact_book() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts'", (estate_id(),)) or {}
    book = _event_payload(row.get("setting_value"))
    return {"contacts": list(book.get("contacts") or []), "groups": list(book.get("groups") or [])}


def _whatsapp_assistant_settings() -> dict[str, Any]:
    row = fetch_one("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_assistants'", (estate_id(),)) or {}
    saved = _event_payload(row.get("setting_value"))
    controls = [code for code in saved.get("manager_controls", []) if code in {"full_refresh", "weather", "cistern", "disease", "public_feed"}]
    ha_entities = [str(value) for value in saved.get("home_assistant_entities", []) if re.fullmatch(r"(?:light|switch|input_boolean|fan|media_player)\.[a-z0-9_]+", str(value))]
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
    return {"profile": profile, "language": language if language in {"auto", "en", "it"} else "auto", "contact": contact, "settings": assistants}


def _whatsapp_is_italian(text: str, configured: str) -> bool:
    if configured == "it":
        return True
    if configured == "en":
        return False
    return bool(re.search(r"\b(ciao|grazie|per favore|aggiorna|controlla|conferma|approva|rifiuta|vigneto|cantina|oggi)\b", text, re.I))


async def _send_whatsapp_assistant_reply(sender: str, text: str, assignment: dict[str, Any]) -> None:
    contact = assignment.get("contact") or {}
    if contact.get("reply_mode") == "voice" and assignment.get("profile") in {"manager", "reporter", "reception"}:
        try:
            audio = await asyncio.to_thread(synthesize_whatsapp_voice, text, assignment.get("language") or "auto", assignment.get("settings", {}).get("voice") or "marin")
            disclosure = "Baiamonte AI voice"
            await asyncio.to_thread(send_whatsapp_media, sender, audio, "baiamonte-reply.mp3", "audio/mpeg", disclosure)
            return
        except Exception:
            pass
    await asyncio.to_thread(send_whatsapp_message, sender, text)


def _pending_whatsapp_action(sender: str, code: str, event_type: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type=%s AND external_id=%s AND status='received' AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR) ORDER BY occurred_at DESC LIMIT 1",
        (estate_id(), event_type, f"{sender}:{code}"),
    )
    return {**_event_payload(row.get("payload")), "_event_id": row.get("id")} if row else None


async def _handle_whatsapp_assistant(sender: str, body: str, message_id: str, record_id: str | None = None, group_id: str = "") -> None:
    """Run bounded WhatsApp automation after the webhook has safely acknowledged Meta."""
    if group_id or not body:
        return
    assignment = _whatsapp_sender_profile(sender)
    profile, language, options = assignment["profile"], assignment["language"], assignment["settings"]
    if profile == "off" or profile == "reception" and not options["reception_enabled"] or profile in {"manager", "reporter"} and not options["manager_enabled"]:
        return
    analysis: dict[str, Any] = {}
    if record_id and profile in {"manager", "reporter"} and options["trusted_ingestion"] and get_settings().openai_api_key:
        try:
            analyzed = await asyncio.to_thread(analyze_intake, record_id)
            analysis = analyzed.get("analysis") or {}
        except Exception:
            pass
    italian = _whatsapp_is_italian(body, language)
    approval = re.fullmatch(r"\s*(?:APPROVE|APPROVA)\s+(\d{4,8})\s*", body, re.I)
    rejection = re.fullmatch(r"\s*(?:REJECT|RIFIUTA)\s+(\d{4,8})\s*", body, re.I)
    if profile in {"manager", "reporter"} and (approval or rejection):
        code = (approval or rejection).group(1)
        pending = _pending_whatsapp_action(sender, code, "intake_approval_pending")
        if pending:
            status = "approved" if approval else "rejected"
            with transaction() as (_, cursor):
                cursor.execute("UPDATE intake_items SET review_status=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, f"WhatsApp {sender}", pending.get("record_id"), estate_id()))
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
                await _send_whatsapp_assistant_reply(sender, "Aggiornamento non riuscito. Controlla Operations Control." if italian else "System update failed. Check Operations Control.", assignment)
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
                await _send_whatsapp_assistant_reply(sender, "Controllo non riuscito. Verifica Home Assistant." if italian else "Device control failed. Check Home Assistant.", assignment)
            return
    commands = {
        "full_refresh": ("refresh system", "aggiorna sistema", "aggiornamento completo"),
        "weather": ("refresh weather", "aggiorna meteo"),
        "cistern": ("check cistern", "controlla cisterna"),
        "disease": ("update disease", "aggiorna malattie", "pressione malattie"),
        "public_feed": ("publish website", "aggiorna sito", "pubblica sito"),
    }
    lowered = body.casefold()
    if profile == "manager" and options["home_assistant_entities"]:
        device_request = await asyncio.to_thread(resolve_home_assistant_control_request, body, options["home_assistant_entities"])
        if device_request:
            code = str(int(hashlib.sha256(f"{sender}:{message_id}:{device_request['entity_id']}:{device_request['action']}".encode()).hexdigest()[:8], 16))[-6:]
            with transaction() as (_, cursor):
                cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_device_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({**device_request, "sender": sender, "message_id": message_id})))
            action_name = "accendere" if device_request["action"] == "turn_on" else "spegnere"
            prompt = f"Conferma per {action_name} {device_request['name']}. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirm to turn {'on' if device_request['action']=='turn_on' else 'off'} {device_request['name']}. Reply CONFIRM {code} within 24 hours."
            await _send_whatsapp_assistant_reply(sender, prompt, assignment)
            return
    requested = next((process for process, phrases in commands.items() if process in options["manager_controls"] and any(phrase in lowered for phrase in phrases)), None)
    if profile == "manager" and requested:
        code = str(int(hashlib.sha256(f"{sender}:{message_id}:{requested}".encode()).hexdigest()[:8], 16))[-6:]
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"process": requested, "sender": sender, "message_id": message_id})))
        await _send_whatsapp_assistant_reply(sender, (f"Conferma richiesta. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirmation required. Reply CONFIRM {code} within 24 hours."), assignment)
        return
    if profile in {"manager", "reporter"} and options["trusted_ingestion"] and record_id:
        try:
            if not analysis.get("contains_question") and str(analysis.get("classification") or "other") != "other":
                code = str(int(hashlib.sha256(f"{sender}:{record_id}".encode()).hexdigest()[:8], 16))[-6:]
                with transaction() as (_, cursor):
                    cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','intake_approval_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"record_id": record_id, "sender": sender, "classification": analysis.get("classification")})))
                summary = str(analysis.get("summary") or "Information ready for review")[:700]
                prompt = f"\n\nRispondi APPROVA {code} o RIFIUTA {code}." if italian else f"\n\nReply APPROVE {code} or REJECT {code}."
                await _send_whatsapp_assistant_reply(sender, summary + prompt, assignment)
                return
        except Exception:
            pass
    limit = options["reply_limit_unknown"] if profile == "reception" else options["reply_limit_manager"]
    count = fetch_one("SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='chatbot_reply' AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender'))=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR)", (estate_id(), sender)) or {}
    if int(count.get("total") or 0) >= limit:
        return
    result = await asyncio.to_thread(whatsapp_chatbot_reply, body, profile if profile in {"manager", "reporter"} else "reception", language, options["home_assistant_entities"] if profile == "manager" else [])
    answer = str(result.get("answer") or result.get("message") or "")[:4096]
    if answer:
        await _send_whatsapp_assistant_reply(sender, answer, assignment)
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','chatbot_reply',%s,'processed',%s)", (estate_id(), message_id[:190], json.dumps({"sender": sender, "profile": profile, "language": language})))


async def _handle_whatsapp_voice(sender: str, data: bytes, filename: str, message_id: str, sender_name: str, group_id: str = "") -> None:
    assignment = _whatsapp_sender_profile(sender)
    if assignment["profile"] not in {"manager", "reporter"}:
        return
    try:
        transcript = await asyncio.to_thread(transcribe_whatsapp_voice, data, filename, assignment["language"])
        if not transcript:
            return
        record_id = save_intake_file(transcript.encode(), f"whatsapp-{message_id}-transcript.txt", "text/plain", "whatsapp", "WhatsApp voice transcript", transcript, message_id + ":transcript", sender_name, sender)
        await _handle_whatsapp_assistant(sender, transcript, message_id, record_id, group_id)
    except (IntegrityError, ValueError):
        return


def _remember_whatsapp_contact(number: str, name: str | None = None) -> None:
    """Add an allowed inbound sender to the small-team address book."""
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
            contacts.append({"name": clean_name or clean_number, "number": clean_number, "role": "", "assistant": "reception" if assistants["unknown_reception"] else "off", "language": "auto", "reply_mode": "text", "auto_unknown": True})
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


def _whatsapp_delivery_status(row: dict[str, Any]) -> str:
    details = _event_payload(row.get("payload"))
    value = str(details.get("delivery_status") or "").lower()
    if value in {"accepted", "sent", "delivered", "read", "failed"}:
        return value
    return "failed" if row.get("status") == "failed" else "accepted"


@app.get("/api/v1/communications", dependencies=[Depends(authorize)])
def communication_center(refresh: bool = False, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        mailbox_status = gmail_mailbox_status()
    except Exception as error:
        mailbox_status = {"configured": bool(settings.gmail_address and settings.gmail_app_password), "address": settings.gmail_address or None, "folder": settings.gmail_folder or "INBOX", "total": None, "unread": None, "error": str(error)[:240]}
    gmail_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,original_filename,classification,review_status,ai_summary FROM intake_items WHERE estate_id=%s AND source='gmail' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    whatsapp_received = fetch_all(
        "SELECT id,sender_name,sender_address,received_at,title,message_text,classification,review_status,ai_summary FROM intake_items WHERE estate_id=%s AND source='whatsapp' ORDER BY received_at DESC LIMIT 60",
        (estate_id(),),
    )
    sent_rows = fetch_all(
        "SELECT id,integration_name,status,payload,error_message,occurred_at FROM integration_events WHERE estate_id=%s AND integration_name IN ('gmail-mailbox','whatsapp-channel','imessage-channel') AND event_type='message_sent' ORDER BY occurred_at DESC LIMIT 120",
        (estate_id(),),
    )
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
            contacts.append({"name": str(message.get("sender_name") or number), "number": number, "role": "", "assistant": "off", "language": "auto", "reply_mode": "text"})
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
    diagnostics["sender_verified"] = bool(diagnostics.get("connected"))
    diagnostics["inbound_verified"] = bool(whatsapp_received)
    diagnostics["outbound_verified"] = any(row.get("status") == "processed" for row in whatsapp_sent)
    diagnostics["operational"] = bool(diagnostics.get("sender_verified") and (diagnostics["inbound_verified"] or diagnostics["outbound_verified"]))
    templates = whatsapp_templates(force=refresh)
    native_groups = whatsapp_native_groups(force=refresh) if settings.whatsapp_native_groups_enabled else {"configured": False, "groups": []}
    assistant_settings = _whatsapp_assistant_settings()
    try:
        assistant_settings["home_assistant_device_catalog"] = home_assistant_manager_devices()
    except Exception:
        assistant_settings["home_assistant_device_catalog"] = []
    return json_ready({
        "gmail": {"status": mailbox_status, "received": gmail_received, "sent": [{**row, "details": _event_payload(row.get("payload"))} for row in sent_rows if row["integration_name"] == "gmail-mailbox"]},
        "whatsapp": {
            "configured": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
            "diagnostics": diagnostics, "templates": templates.get("templates") or [], "templates_error": templates.get("error"),
            "phone_number_id": settings.whatsapp_phone_number_id or None, "received": whatsapp_received,
            "sent": whatsapp_sent,
            "contacts": contacts, "groups": groups, "native_groups": native_groups, "assistants": assistant_settings,
        },
        "imessage": {
            "status": imessage_status(),
            "received": fetch_all("SELECT id,sender_name,sender_address,received_at,title,message_text,classification,review_status,ai_summary FROM intake_items WHERE estate_id=%s AND source='imessage' ORDER BY received_at DESC LIMIT 60", (estate_id(),)),
            "sent": [{**row, "details": _event_payload(row.get("payload"))} for row in sent_rows if row["integration_name"] == "imessage-channel"],
        },
    })


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


@app.post("/api/v1/communications/whatsapp/send", dependencies=[Depends(authorize_write)])
def communication_send_whatsapp(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return send_whatsapp_message(str(payload.get("recipient") or ""), str(payload.get("body") or ""), str(payload.get("template_name") or ""), str(payload.get("template_language") or "en"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp send failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/whatsapp/send-file", dependencies=[Depends(authorize_write)])
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


@app.post("/api/v1/communications/whatsapp/broadcast", dependencies=[Depends(authorize_write)])
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


@app.get("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize)])
def communication_whatsapp_groups(refresh: bool = False) -> dict[str, Any]:
    return json_ready(whatsapp_native_groups(force=refresh))


@app.post("/api/v1/communications/whatsapp/groups", dependencies=[Depends(authorize_write)])
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


@app.get("/api/v1/communications/whatsapp/groups/{group_id}/invite-link", dependencies=[Depends(authorize)])
def communication_whatsapp_group_invite(group_id: str) -> dict[str, Any]:
    try:
        return json_ready(whatsapp_group_invite_link(group_id))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "WhatsApp invite link failed: " + str(error)[:300]) from error


@app.get("/api/v1/communications/imessage/conversations", dependencies=[Depends(authorize)])
def communication_imessage_conversations() -> dict[str, Any]:
    try:
        return {"conversations": json_ready(imessage_conversations())}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "iMessage bridge failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/imessage/send", dependencies=[Depends(authorize_write)])
def communication_send_imessage(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = {"recipient": str(payload.get("recipient") or "")[:250], "conversation_id": str(payload.get("conversation_id") or "")[:250], "preview": str(payload.get("body") or "")[:180]}
    try:
        result = send_imessage(metadata["recipient"], str(payload.get("body") or ""), metadata["conversation_id"])
        message_id = str(result.get("message_id") or result.get("guid") or "")[:190] or None
        metadata["message_id"] = message_id
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'imessage-channel','outbound','message_sent',%s,'processed',%s)", (estate_id(), message_id, json.dumps(metadata)))
        return {"sent": True, **metadata}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        try:
            with transaction() as (_, cursor):
                cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,status,payload,error_message) VALUES (%s,'imessage-channel','outbound','message_sent','failed',%s,%s)", (estate_id(), json.dumps(metadata), str(error)[:1000]))
        except Exception:
            pass
        raise HTTPException(502, "iMessage send failed: " + str(error)[:300]) from error


@app.post("/api/v1/communications/imessage/send-file", dependencies=[Depends(authorize_write)])
async def communication_send_imessage_file(
    recipient: str = Form(""), conversation_id: str = Form(""), body: str = Form(""), file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    metadata = {"recipient": recipient[:250], "conversation_id": conversation_id[:250], "preview": body[:180]}
    try:
        attachment = None
        if file and file.filename:
            data = await file.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Attachment must be 20 MB or smaller")
            attachment = (file.filename, file.content_type or "application/octet-stream", data)
            metadata["filename"] = file.filename[:180]
        result = send_imessage(recipient, body, conversation_id, attachment)
        message_id = str(result.get("message_id") or result.get("guid") or "")[:190] or None
        metadata["message_id"] = message_id
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'imessage-channel','outbound','message_sent',%s,'processed',%s)", (estate_id(), message_id, json.dumps(metadata)))
        return {"sent": True, **metadata}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "iMessage send failed: " + str(error)[:300]) from error


@app.get("/api/v1/social", dependencies=[Depends(authorize)])
def social_center() -> dict[str, Any]:
    return social_dashboard()


@app.post("/api/v1/social/facebook", dependencies=[Depends(authorize_write)])
def social_publish_facebook(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_facebook(str(payload.get("message") or ""), str(payload.get("link") or "") or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Facebook publish failed: " + str(error)[:300]) from error


@app.post("/api/v1/social/instagram", dependencies=[Depends(authorize_write)])
def social_publish_instagram(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_instagram(str(payload.get("image_url") or ""), str(payload.get("caption") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Instagram publish failed: " + str(error)[:300]) from error


@app.put("/api/v1/communications/whatsapp/contacts", dependencies=[Depends(authorize_write)])
def save_whatsapp_contacts(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    contacts = []
    for row in (payload.get("contacts") or [])[:100]:
        name = str((row or {}).get("name") or "").strip()[:180]
        number = re.sub(r"\D", "", str((row or {}).get("number") or ""))
        role = str((row or {}).get("role") or "").strip()[:180]
        assistant = str((row or {}).get("assistant") or "off").lower()
        language = str((row or {}).get("language") or "auto").lower()
        reply_mode = str((row or {}).get("reply_mode") or "text").lower()
        if assistant not in {"off", "reception", "reporter", "manager"}:
            assistant = "off"
        if language not in {"auto", "en", "it"}:
            language = "auto"
        if reply_mode not in {"text", "voice"}:
            reply_mode = "text"
        if name and len(number) >= 8:
            contacts.append({"name": name, "number": number, "role": role, "assistant": assistant, "language": language, "reply_mode": reply_mode})
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


@app.get("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize)])
def get_whatsapp_assistants() -> dict[str, Any]:
    try:
        catalog = home_assistant_manager_devices()
    except Exception:
        catalog = []
    return json_ready({**_whatsapp_assistant_settings(), "home_assistant_device_catalog": catalog})


@app.put("/api/v1/communications/whatsapp/assistants", dependencies=[Depends(authorize_admin)])
def save_whatsapp_assistants(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    allowed_controls = {"full_refresh", "weather", "cistern", "disease", "public_feed"}
    try:
        safe_catalog = {item["entity_id"] for item in home_assistant_manager_devices()}
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
    name = str((assignment.get("contact") or {}).get("name") or "").strip()
    greeting = f"Hello {name} / Ciao {name}" if name else "Hello / Ciao"
    role_line = "Manager / Responsabile" if assignment["profile"] == "manager" else "Reporter / Collaboratore"
    controls = "\n• View live solar, battery, grid, inverter and energy information.\n• Control administrator-approved ordinary devices with a confirmation code.\n• Ask for a weather, cistern, disease, website or complete data refresh; reply CONFIRM or CONFERMA with the code." if assignment["profile"] == "manager" else ""
    message = (
        f"{greeting},\n\nYou are invited to the Tenuta Baiamonte WhatsApp assistant as {role_line}.\n"
        "ENGLISH\n• Ask vineyard, weather, work, treatment-planning or cellar questions.\n"
        "• Send work reports, harvest totals, hours, observations, photos, documents or voice notes.\n"
        "• The assistant will show what it extracted. Reply APPROVE <code> or REJECT <code>."
        f"{controls}\n• Treatments and cellar corrections still require the responsible specialist.\n\n"
        "ITALIANO\n• Fai domande su vigneto, meteo, lavori, trattamenti pianificati o cantina.\n"
        "• Invia rapporti di lavoro, raccolta, ore, osservazioni, foto, documenti o messaggi vocali.\n"
        "• L'assistente mostrerà ciò che ha estratto. Rispondi APPROVA <codice> o RIFIUTA <codice>.\n"
        + ("• Visualizza informazioni in tempo reale su solare, batterie, rete, inverter ed energia.\n• Controlla i dispositivi ordinari autorizzati dall'amministratore con un codice di conferma.\n• Per aggiornare meteo, cisterna, pressione malattie, sito o tutti i dati, rispondi CONFERMA con il codice.\n" if assignment["profile"] == "manager" else "")
        + "• Trattamenti e correzioni di cantina richiedono sempre lo specialista responsabile.\n\n"
        "Language / Lingua: reply in English or Italian; the assistant follows you automatically. "
        "Voice replies use the Baiamonte AI voice / Le risposte vocali usano la voce AI Baiamonte."
    )
    try:
        result = send_whatsapp_message(recipient, message)
    except Exception as error:
        raise HTTPException(502, "Invitation could not be sent. Ask the contact to message Baiamonte first or use an approved WhatsApp template: " + str(error)[:220]) from error
    with transaction() as (_, cursor):
        audit(cursor, "send", "whatsapp_assistant_invitation", recipient[-6:], {"profile": assignment["profile"], "language": assignment["language"]}, request.headers.get("X-Remote-User-Name") or "home-assistant")
    return {"sent": True, "recipient": recipient, "profile": assignment["profile"], "result": result}


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


@app.post("/api/v1/intake/mac", status_code=201, dependencies=[Depends(authorize_write)])
async def submit_mac_intake(payload: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Accept bounded text from an authenticated Mac/Codex workflow into human review."""
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
            field = str(change.get("field") or "")
            if field in {"group_lifecycle_update", "group_participants_update", "group_settings_update", "group_status_update"}:
                group_external_id = str(value.get("group_id") or value.get("id") or new_id("wagroup"))[:190]
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                        "VALUES (%s,'whatsapp-channel','inbound',%s,%s,'received',%s)",
                        (estate_id(), field, group_external_id, json.dumps(value)),
                    )
            for status_item in value.get("statuses", []):
                message_id = str(status_item.get("id") or "")[:190] or None
                delivery_status = str(status_item.get("status") or "unknown")[:60]
                # Meta uses transport-specific states (sent, delivered, read,
                # failed), while integration_events deliberately keeps a
                # small cross-integration status vocabulary.  Preserve the
                # exact Meta state in payload and normalize only the indexed
                # database status so a delivery receipt cannot abort later
                # inbound messages in the webhook request.
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
                        # Meta notes that status callbacks can arrive out of order.
                        # Never replace a read/delivered state with an older state.
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
                sender_assignment = _whatsapp_sender_profile(sender)
                if allowed and sender not in allowed and sender_assignment["profile"] == "off":
                    continue
                _remember_whatsapp_contact(sender, contacts.get(sender))
                message_type = message.get("type") or "unknown"
                media = message.get(message_type) or {}
                body = (message.get("text") or {}).get("body") or media.get("caption") or ""
                message_id = str(message.get("id") or new_id())
                group_id = str(message.get("group_id") or "")[:300]
                source_title = f"WhatsApp group {group_id[-10:]} · {message_type}" if group_id else f"WhatsApp {message_type}"
                if body:
                    try:
                        record_id = save_intake_file(body.encode(), f"whatsapp-{message_id}.txt", "text/plain", "whatsapp", source_title, body, message_id + ":body", contacts.get(sender), sender)
                        if sender_assignment["profile"] != "off":
                            asyncio.create_task(_handle_whatsapp_assistant(sender, body, message_id, record_id, group_id))
                    except IntegrityError:
                        pass
                media_id = str(media.get("id") or "") if message_type in {"image", "document", "audio", "video", "sticker"} else ""
                if media_id:
                    try:
                        data, generated_name, content_type = await asyncio.to_thread(download_whatsapp_media, media_id)
                        filename = str(media.get("filename") or generated_name)
                        media_title = f"{source_title}: {filename}"
                        record_id = save_intake_file(data, filename, content_type, "whatsapp", media_title, body, message_id + ":media", contacts.get(sender), sender)
                        if message_type == "audio" and not group_id and settings.openai_api_key and sender_assignment["profile"] in {"manager", "reporter"}:
                            asyncio.create_task(_handle_whatsapp_voice(sender, data, filename, message_id, contacts.get(sender) or sender, group_id))
                        elif not group_id and settings.openai_api_key and sender_assignment["profile"] in {"manager", "reporter"}:
                            asyncio.create_task(asyncio.to_thread(analyze_intake, record_id))
                    except IntegrityError:
                        pass
                    except Exception as error:
                        with transaction() as (_, cursor):
                            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message) VALUES (%s,'whatsapp-channel','inbound','media_download',%s,'failed',%s)", (estate_id(), message_id[:190], str(error)[:1000]))
    return {"received": True}


@app.post("/webhooks/imessage")
async def receive_imessage_webhook(request: Request, authorization: str | None = Header(None), settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    """Receive allowlisted messages from the dedicated Baiamonte Mac relay."""
    if not settings.imessage_bridge_token or not authorization or not hmac.compare_digest(authorization, f"Bearer {settings.imessage_bridge_token}"):
        raise HTTPException(403, "Invalid iMessage bridge token")
    payload = await request.json()
    sender = str(payload.get("sender") or payload.get("handle") or "").strip()
    normalized = sender.casefold() if "@" in sender else re.sub(r"\D", "", sender)
    allowed = {value.strip().casefold() if "@" in value else re.sub(r"\D", "", value) for value in settings.imessage_allowed_handles.split(",") if value.strip()}
    if allowed and normalized not in allowed:
        return {"received": False}
    body = str(payload.get("text") or payload.get("body") or "").strip()
    message_id = str(payload.get("message_id") or payload.get("guid") or new_id("imsg"))
    if body:
        try:
            record_id = save_intake_file(body.encode(), f"imessage-{message_id}.txt", "text/plain", "imessage", str(payload.get("conversation_name") or "iMessage"), body, message_id + ":body", str(payload.get("sender_name") or ""), sender)
            if settings.openai_api_key:
                asyncio.create_task(asyncio.to_thread(analyze_intake, record_id))
        except IntegrityError:
            pass
    for index, attachment in enumerate((payload.get("attachments") or [])[:10]):
        if not isinstance(attachment, dict) or not attachment.get("data_base64"):
            continue
        try:
            data = base64.b64decode(str(attachment["data_base64"]), validate=True)
            record_id = save_intake_file(data, str(attachment.get("filename") or f"imessage-attachment-{index + 1}"), str(attachment.get("content_type") or "application/octet-stream"), "imessage", str(payload.get("conversation_name") or "iMessage attachment"), body, f"{message_id}:attachment:{index}", str(payload.get("sender_name") or ""), sender)
            if settings.openai_api_key:
                asyncio.create_task(asyncio.to_thread(analyze_intake, record_id))
        except (IntegrityError, ValueError):
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
    # The ADS-B app's precipitation view is served by its TV document. Keep
    # that configured path for the root request; discarding it loaded the
    # aircraft overview and broke relative assets inside the dashboard frame.
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
