"""Attachments, operational alerts, processing log, and intake review routes."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pymysql.err import IntegrityError

from ..access import authorize, authorize_write, operations_usernames
from ..cellar_demo import cellar_guardrails
from ..config import Settings, get_settings
from ..db import fetch_all, fetch_one, transaction
from ..ha_auth import home_assistant_token
from ..intelligence import (
    alert_preference,
    analyze_intake,
    analyze_observation_attachment,
    poll_gmail_once,
    save_intake_file,
    whatsapp_templates,
)
from ..service import audit, estate_id, json_ready, new_id
from ..whatsapp_notices import reconcile_answered_notices
from .alerts import valid_alert_transition
from .attachments import MAX_ATTACHMENT_BYTES, store_attachment


logger = logging.getLogger("baiamonte")
router = APIRouter(tags=["alerts-intake"])


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


@router.post("/api/v1/attachments/{entity_type}/{entity_id}", status_code=201, dependencies=[Depends(authorize_write)])
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
    data = await file.read(MAX_ATTACHMENT_BYTES + 1)
    await file.close()
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(413, "Each photo or file must be 15 MB or smaller")
    media_type = file.content_type or "application/octet-stream"
    if not (media_type.startswith("image/") or media_type == "application/pdf"):
        raise HTTPException(422, "Choose a photo, screenshot, or PDF")
    attachment_id = new_id()
    stored = store_attachment(data, attachment_id, file.filename or "", "attachment")
    analysis_queued = entity_type in {"scouting", "phenology", "maturity_sample"} and media_type.startswith("image/")
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO entity_attachments (id,estate_id,entity_type,entity_id,original_filename,stored_path,media_type,file_sha256,caption,uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (attachment_id, estate_id(), entity_type, entity_id, stored.filename, str(stored.path), media_type, stored.sha256, caption or None, request.headers.get("X-Remote-User-Name") or "api"),
            )
            if analysis_queued:
                cursor.execute(
                    "INSERT INTO observation_photo_analyses "
                    "(id,estate_id,attachment_id,entity_type,entity_id,status) VALUES (%s,%s,%s,%s,%s,'queued')",
                    (new_id(), estate_id(), attachment_id, entity_type, entity_id),
                )
            audit(cursor, "attach", entity_type, entity_id, {"attachment_id": attachment_id, "filename": stored.filename})
    except Exception:
        stored.discard()
        raise
    if analysis_queued:
        background_tasks.add_task(analyze_observation_attachment, attachment_id)
    return {
        "id": attachment_id,
        "entity_id": entity_id,
        "analysis_status": "queued" if analysis_queued else None,
    }


@router.get("/api/v1/attachments/{attachment_id}/file", dependencies=[Depends(authorize)])
def entity_attachment_file(attachment_id: str) -> FileResponse:
    row = fetch_one("SELECT * FROM entity_attachments WHERE id=%s AND estate_id=%s", (attachment_id, estate_id()))
    if not row or not Path(row["stored_path"]).is_file():
        raise HTTPException(404, "Attachment not found")
    return FileResponse(row["stored_path"], media_type=row.get("media_type"), filename=row.get("original_filename"))

@router.get("/api/v1/alerts", dependencies=[Depends(authorize)])
def list_alerts(status: str = "open") -> list[dict[str, Any]]:
    if status in {"open", "all"}:
        try:
            reconcile_answered_notices()
        except Exception:
            logger.exception("Alert inbox reconciliation failed; returning stored alerts")
    return json_ready(fetch_all("SELECT * FROM alerts WHERE estate_id=%s AND (%s='all' OR status=%s) ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC LIMIT 250", (estate_id(), status, status)))


@router.patch("/api/v1/alerts/{alert_id}", dependencies=[Depends(authorize_write)])
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
    "power_recovery": "System monitoring restored",
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

@router.get("/api/v1/alert-settings", dependencies=[Depends(authorize)])
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


@router.put("/api/v1/alert-settings/cellar-thresholds", dependencies=[Depends(authorize_write)])
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


@router.put("/api/v1/alert-settings/{alert_type}", dependencies=[Depends(authorize_write)])
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


@router.get("/api/v1/intake", dependencies=[Depends(authorize)])
def list_intake() -> list[dict[str, Any]]:
    return json_ready(fetch_all("SELECT id,source,sender_name,sender_address,received_at,title,original_filename,media_type,classification,ai_summary,extracted_data,review_status,processing_error FROM intake_items WHERE estate_id=%s ORDER BY received_at DESC LIMIT 250", (estate_id(),)))


@router.get("/api/v1/processing-log", dependencies=[Depends(authorize)])
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


@router.post("/api/v1/intake/gmail/check", dependencies=[Depends(authorize_write)])
def check_gmail_now() -> dict[str, Any]:
    settings = get_settings()
    if not settings.gmail_address or not settings.gmail_app_password:
        return {"configured": False, "message": "Add the Gmail address and app password in Vineyard Operations configuration."}
    try:
        saved = poll_gmail_once()
        return {"configured": True, "saved": saved, "message": f"Gmail checked; {saved} new item(s) added for review."}
    except Exception as error:
        raise HTTPException(502, "Gmail check failed: " + str(error)[:300]) from error

@router.get("/api/v1/intake/{record_id}", dependencies=[Depends(authorize)])
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


@router.get("/api/v1/intake/{record_id}/file", dependencies=[Depends(authorize)])
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


@router.post("/api/v1/intake/{record_id}/link", dependencies=[Depends(authorize_write)])
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


@router.post("/api/v1/intake/upload", status_code=201, dependencies=[Depends(authorize_write)])
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


@router.post("/api/v1/intake/mac", status_code=201, dependencies=[Depends(authorize_write)])
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


@router.post("/api/v1/intake/{record_id}/analyze", dependencies=[Depends(authorize_write)])
async def analyze_intake_item(record_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(analyze_intake, record_id, allow_reanalysis=True)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.patch("/api/v1/intake/{record_id}/review", dependencies=[Depends(authorize_write)])
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


@router.post("/api/v1/intake/flush-completed", dependencies=[Depends(authorize_write)])
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


@router.post("/api/v1/intake/clear-routine-whatsapp", dependencies=[Depends(authorize_write)])
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
    reconcile_answered_notices()
    return {"cleared": count, "message": "Routine WhatsApp conversations were archived; source messages and audit history were retained."}
