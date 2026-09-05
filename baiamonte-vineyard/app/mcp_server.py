"""Constrained ChatGPT/MCP access to the vineyard database.

This server intentionally exposes vineyard concepts, not arbitrary SQL.
Read tools are always available. Write tools require MCP_ALLOW_WRITES=true and
an explicit confirmation string in every call.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from .config import get_settings
from .db import fetch_all, fetch_one, transaction
from .process_control import process_controls
from .process_runtime import processing_runtime_snapshot
from .observation_catalog import phenology_stage, scouting_issue
from .production_impact import derive_scouting_damage_fields
from .quick_entry import route_saved_observation
from .prediction_refresh import request_harvest_refresh
from .domains.laboratory import refresh_lab_learning
from .planning_sync import apple_reminder_reconciliation, general_reminder_plan, import_apple_reminders, publish_task_to_google, treatment_reminder_plan, unified_work_plan
from .service import audit, estate_id, json_ready, new_id, season_for_year
from .official_facts import official_pipeline_context


settings_at_startup = get_settings()
mcp = FastMCP(
    "Tenuta Baiamonte Vineyard",
    instructions=(
        "Use this server for Tenuta Baiamonte vineyard, harvest, cellar, weather, olive, labor, "
        "equipment, laboratory, issue, and reporting questions. Blank database values mean unknown, "
        "not zero. Distinguish facts, estimates, forecasts, and unresolved issues. Never describe a "
        "planned treatment as approved or applied. Writes require the user to confirm the exact record."
    ),
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[item.strip() for item in settings_at_startup.mcp_allowed_hosts.split(",") if item.strip()],
    ),
)


def bounded(limit: int, maximum: int = 100) -> int:
    return max(1, min(int(limit), maximum))


WRITE_RECORDS: dict[str, dict[str, Any]] = {
    "task": {"table": "tasks", "fields": {"title", "category", "status", "priority", "due_date", "estimated_hours", "notes", "block_id"}, "required": {"title"}, "defaults": {"category": "general", "status": "planned", "priority": "normal", "source": "chatgpt"}},
    "work_activity": {"table": "work_activities", "fields": {"activity_date", "end_date", "category", "title", "status", "labor_hours", "worker_count", "cost_eur", "weather_note", "notes", "block_id"}, "required": {"activity_date", "title"}, "defaults": {"category": "general", "status": "done", "source": "chatgpt"}},
    "harvest_lot": {"table": "harvest_lots", "fields": {"harvested_at", "weight_kg", "crate_count", "destination", "brix", "babo", "ph", "ta_g_l", "condition_grade", "notes", "block_id", "variety_id"}, "required": {"harvested_at", "variety_id"}},
    "lab_sample": {"table": "lab_samples", "fields": {"sample_code", "sample_name", "sample_type", "sampled_at", "lab_date", "laboratory", "source_document", "needs_review", "review_notes", "notes", "block_id", "variety_id", "wine_lot_id"}, "required": {"sample_name", "sample_type", "lab_date"}},
    "issue_decision": {"table": "issues_decisions", "fields": {"source_issue_id", "opened_date", "subject_ref", "issue_type", "priority", "issue_text", "evidence_summary", "decision_action", "owner_text", "due_date", "status", "closed_date", "notes"}, "required": {"issue_text"}, "defaults": {"opened_date": "__today__", "issue_type": "Data", "priority": "medium", "status": "open"}},
    "labor_entry": {"table": "labor_entries", "fields": {"source_labor_id", "work_date", "shift_label", "person_or_crew", "role", "regular_hours", "overtime_hours", "hourly_rate_eur", "labor_cost_eur", "kg_handled", "incident_near_miss", "approved_by", "payment_status", "payroll_scope", "notes"}, "required": {"person_or_crew"}, "defaults": {"payment_status": "unknown", "payroll_scope": "unknown"}},
    "equipment_event": {"table": "equipment_service_events", "fields": {"source_record_id", "event_date", "asset_name", "pre_use_status", "cleaning_started_at", "cleaning_ended_at", "sanitation_method", "concentration", "released", "released_by", "downtime_hours", "maintenance_action", "next_due_date", "notes"}, "required": {"event_date", "asset_name"}},
    "olive_record": {"table": "olive_records", "fields": {"source_record_id", "record_year", "record_date", "activity", "details", "status", "worker_text", "labor_hours", "olives_harvested_kg", "mill_date", "oil_liters", "yield_pct", "notes", "evidence"}, "required": {"record_year", "activity"}},
    "harvest_plan": {"table": "harvest_plans", "fields": {"source_plan_id", "block_reference", "planned_pick_date", "status", "planned_kg", "planned_crates", "crew_size", "planned_hours", "cellar_destination", "weather_risk", "dependencies", "approved_by", "confidence", "forecast_method", "notes", "variety_id"}, "required": {"planned_pick_date", "variety_id"}, "defaults": {"status": "provisional"}},
    "phenology": {"table": "phenology_observations", "fields": {"observed_date", "stage_code", "stage_name", "percent_complete", "notes", "photo_url", "block_id", "variety_id"}, "required": {"observed_date", "stage_code", "block_id", "variety_id"}},
    "scouting": {"table": "scouting_observations", "fields": {"observed_at", "issue_type", "severity", "incidence_pct", "location_note", "action_required", "notes", "photo_url", "block_id"}, "required": {"observed_at", "issue_type", "block_id"}, "defaults": {"severity": "low", "action_required": 0}},
    "irrigation": {"table": "irrigation_events", "fields": {"started_at", "ended_at", "volume_l", "depth_mm", "notes", "block_id"}, "required": {"started_at", "block_id"}, "defaults": {"source": "manual"}},
    "cellar_operation": {"table": "cellar_operations", "fields": {"operation_at", "operation_type", "amount", "unit", "temp_c", "notes", "wine_lot_id", "container_id", "product_id"}, "required": {"operation_at", "operation_type"}},
    "note": {"table": "notes", "fields": {"note_date", "title", "body", "tags", "related_type", "related_id"}, "required": {"body"}, "defaults": {"note_date": "__now__"}},
    "spray_application": {"table": "spray_applications", "fields": {"crop_scope", "application_date", "purpose", "area_ha", "water_volume_l", "operator_name", "equipment_name", "temp_c", "wind_kph", "status", "notes", "block_id", "source_application_id", "evidence_status", "actual_details_confirmed", "agronomist_approved", "label_legal_confirmed", "phi_checked", "rei_checked", "weather_checked", "ppe_confirmed"}, "required": {"application_date", "purpose"}, "defaults": {"crop_scope": "vineyard", "status": "planned", "actual_details_confirmed": 0, "agronomist_approved": 0, "label_legal_confirmed": 0, "phi_checked": 0, "rei_checked": 0, "weather_checked": 0, "ppe_confirmed": 0}},
}


def resolve_named_references(values: dict[str, Any]) -> dict[str, Any]:
    values = dict(values)
    references = {
        "block_code": ("block_id", "SELECT id FROM vineyard_blocks WHERE estate_id=%s AND code=%s"),
        "variety_name": ("variety_id", "SELECT id FROM grape_varieties WHERE estate_id=%s AND name=%s"),
        "wine_lot_code": ("wine_lot_id", "SELECT id FROM wine_lots WHERE estate_id=%s AND code=%s"),
        "container_code": ("container_id", "SELECT id FROM cellar_containers WHERE estate_id=%s AND code=%s"),
        "product_name": ("product_id", "SELECT id FROM products WHERE estate_id=%s AND name=%s"),
    }
    for alias, (column, sql) in references.items():
        if alias not in values:
            continue
        name = values.pop(alias)
        row = fetch_one(sql, (estate_id(), name))
        if not row:
            raise ValueError(f"Unknown {alias}: {name}")
        values[column] = row["id"]
    return values


def record_year(values: dict[str, Any], fallback: int | None = None) -> int:
    if fallback:
        return fallback
    for key in ("activity_date", "harvested_at", "lab_date", "work_date", "record_date", "planned_pick_date", "observed_date", "observed_at", "started_at", "operation_at", "application_date", "due_date"):
        if values.get(key):
            return int(str(values[key])[:4])
    return date.today().year


def require_write_confirmation(confirmation: str) -> None:
    settings = get_settings()
    if not settings.mcp_allow_writes:
        raise ValueError("ChatGPT writes are disabled by the vineyard administrator")
    if confirmation.strip().upper() != "CONFIRM":
        raise ValueError("Write not performed. Pass confirmation='CONFIRM' only after the user confirms the exact record.")


@mcp.tool()
def processing_status(limit: int = 40) -> dict[str, Any]:
    """Read current process schedules, recent successes/failures, and the human-review queue. Credentials and source payloads are never returned."""
    return json_ready({
        "controls": process_controls(),
        "processing": processing_runtime_snapshot(),
        "recent_events": fetch_all(
            "SELECT integration_name,event_type,status,error_message,occurred_at FROM integration_events "
            "WHERE estate_id=%s ORDER BY occurred_at DESC LIMIT %s",
            (estate_id(), bounded(limit, 100)),
        ),
        "review_queue": fetch_all(
            "SELECT id,source,sender_name,received_at,title,classification,review_status,processing_error FROM intake_items "
            "WHERE estate_id=%s AND review_status IN ('new','processing','ready_for_review','failed') "
            "ORDER BY received_at DESC LIMIT %s",
            (estate_id(), bounded(limit, 100)),
        ),
    })


@mcp.tool()
def work_plan(include_completed: bool = False) -> dict[str, Any]:
    """Read the unified Baiamonte work plan. Projects are task groups; Google Tasks is the shared store and Apple list Baiamonte is the MCP-synchronized companion."""
    return unified_work_plan(include_completed=include_completed)


@mcp.tool()
def apple_reminder_lists(include_completed: bool = False) -> dict[str, Any]:
    """Read two disjoint desired Apple reminder lists and any exact cross-list copies to remove. Baiamonte receives general work only; Baiamonte Treatments receives treatment plans only."""
    return apple_reminder_reconciliation(include_completed=include_completed)


@mcp.tool()
def baiamonte_reminders(include_completed: bool = False) -> dict[str, Any]:
    """Read general work that belongs only in the Apple list Baiamonte. Treatment records are excluded."""
    return general_reminder_plan(include_completed=include_completed)


@mcp.tool()
def sync_apple_reminders(
    reminders_json: str,
    list_name: Literal["Baiamonte", "Baiamonte Treatments"] = "Baiamonte",
    confirmation: str = "",
) -> dict[str, Any]:
    """Merge a complete snapshot from Apple list Baiamonte or Baiamonte Treatments. This never deletes reminders or marks a treatment applied. Pass confirmation='CONFIRM' only after the user authorizes this exact list sync."""
    require_write_confirmation(confirmation)
    try:
        reminders = json.loads(reminders_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid reminders_json: {error}") from error
    if not isinstance(reminders, list):
        raise ValueError("reminders_json must contain a JSON array")
    return import_apple_reminders(reminders, list_name=list_name)


@mcp.tool()
def treatment_reminders(include_completed: bool = False) -> dict[str, Any]:
    """Read reminders that should be mirrored to Apple list Baiamonte Treatments. These are plans only; reminder completion never approves or records an application."""
    return treatment_reminder_plan(include_completed=include_completed)


@mcp.tool()
def queue_review_item(
    title: str,
    message: str,
    source_type: Literal["gmail", "whatsapp", "chatgpt", "other"] = "chatgpt",
    source_reference: str | None = None,
    sender_name: str | None = None,
    external_id: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Queue sourced text for AI extraction and human review. This never changes an authoritative vineyard record. Pass confirmation='QUEUE FOR REVIEW' only for a relevant source item the user has authorized this monitor to collect."""
    if confirmation.strip().upper() != "QUEUE FOR REVIEW":
        raise ValueError("Item not queued. Pass confirmation='QUEUE FOR REVIEW' for an authorized source item.")
    clean_title = title.strip()[:300]
    clean_message = message.strip()
    if not clean_title or not clean_message:
        raise ValueError("Title and message are required")
    if len(clean_message.encode("utf-8")) > 512_000:
        raise ValueError("Review text must be 500 KB or smaller")
    source_id = (external_id or hashlib.sha256(f"{source_type}|{source_reference or ''}|{clean_message}".encode()).hexdigest())[:255]
    existing = fetch_one("SELECT id,review_status FROM intake_items WHERE estate_id=%s AND source='codex' AND external_id=%s", (estate_id(), source_id))
    if existing:
        return {"queued": False, "duplicate": True, "id": existing["id"], "review_status": existing["review_status"]}
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO intake_items (id,estate_id,source,external_id,sender_name,sender_address,received_at,title,message_text,media_type,classification,review_status) "
            "VALUES (%s,%s,'codex',%s,%s,%s,NOW(),%s,%s,'text/plain',%s,'new')",
            (record_id, estate_id(), source_id, sender_name, source_reference, clean_title, clean_message, f"incoming_{source_type}"),
        )
        audit(cursor, "queue_for_review", "intake", record_id, {"source_type": source_type, "source_reference": source_reference, "title": clean_title}, actor="chatgpt")
    return {"queued": True, "id": record_id, "review_status": "new", "authoritative_record_changed": False}


@mcp.tool()
def vineyard_overview(vintage_year: int = datetime.now().year) -> dict[str, Any]:
    """Get a compact estate and vintage overview: blocks, varieties, open work, alerts, harvest, and current forecast dates."""
    season = fetch_one("SELECT id,status FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), vintage_year)) or {}
    season_id = season.get("id", "")
    return json_ready({
        "vintage_year": vintage_year,
        "season_status": season.get("status"),
        "official_facts": official_pipeline_context(vintage_year),
        "blocks": fetch_all("SELECT code,name,area_ha,vine_count,training_system,soil_type FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),)),
        "varieties": fetch_all("SELECT name,target_gdd,notes FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),)),
        "open_tasks": fetch_all("SELECT title,category,priority,due_date,block_code,days_until_due FROM v_open_work WHERE estate_id=%s ORDER BY due_date IS NULL,due_date LIMIT 20", (estate_id(),)),
        "open_issues": fetch_all("SELECT source_issue_id,priority,issue_type,issue_text,owner_text,due_date,status FROM issues_decisions WHERE estate_id=%s AND status IN ('open','monitoring') ORDER BY FIELD(priority,'critical','high','medium','low'),due_date LIMIT 20", (estate_id(),)),
        "harvest_actual": fetch_all("SELECT * FROM v_harvest_summary WHERE estate_id=%s AND vintage_year=%s AND LOWER(TRIM(variety_name)) NOT IN ('blend','other')", (estate_id(), vintage_year)),
        "harvest_plan": fetch_all("SELECT v.name variety,h.planned_pick_date,h.planned_kg,h.planned_crates,h.status,h.confidence,h.dependencies FROM harvest_plans h JOIN grape_varieties v ON v.id=h.variety_id WHERE h.season_id=%s AND h.status<>'cancelled' AND LOWER(TRIM(v.name)) NOT IN ('blend','other') ORDER BY h.planned_pick_date", (season_id,)),
    })


@mcp.tool()
def harvest_report(vintage_year: int, include_historical_comparison: bool = True) -> dict[str, Any]:
    """Report planned and actual harvest dates, weights, crates, fruit chemistry, and optionally comparable historical summaries."""
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), vintage_year)) or {}
    output = {
        "vintage_year": vintage_year,
        "official_facts": official_pipeline_context(vintage_year),
        "actual": fetch_all("SELECT * FROM v_harvest_summary WHERE estate_id=%s AND vintage_year=%s AND LOWER(TRIM(variety_name)) NOT IN ('blend','other') ORDER BY variety_name", (estate_id(), vintage_year)),
        "planned": fetch_all("SELECT p.source_plan_id,v.name variety,p.planned_pick_date,p.planned_kg,p.planned_crates,p.status,p.weather_risk,p.dependencies,p.confidence,p.notes FROM harvest_plans p JOIN grape_varieties v ON v.id=p.variety_id WHERE p.season_id=%s AND p.status<>'cancelled' AND LOWER(TRIM(v.name)) NOT IN ('blend','other') ORDER BY p.planned_pick_date", (season.get("id", ""),)),
    }
    if include_historical_comparison:
        output["history"] = fetch_all("SELECT vintage_year,variety_name,grapes_kg,wine_l,cassette_count,evidence_status,reconciliation_note FROM vintage_summaries WHERE estate_id=%s AND LOWER(TRIM(variety_name)) NOT IN ('blend','other') ORDER BY vintage_year,variety_name", (estate_id(),))
    return json_ready(output)


@mcp.tool()
def lab_history(
    vintage_year: int | None = None,
    sample_name_contains: str | None = None,
    analyte_code: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get laboratory results with sample date, vintage, matrix, sample name, analyte, value, unit, and review status."""
    sql = "SELECT s.sample_code,s.lab_date,COALESCE(s.vintage_year,se.vintage_year) vintage_year,s.vintage_assignment_source,s.vintage_assignment_confidence,s.vintage_assignment_evidence,s.sample_name,s.sample_type,s.laboratory,s.needs_review,s.review_notes,r.analyte_code,r.analyte_name,r.numeric_value,r.text_value,r.unit FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s"
    params: list[Any] = [estate_id()]
    if vintage_year is not None:
        sql += " AND COALESCE(s.vintage_year,se.vintage_year)=%s"; params.append(vintage_year)
    if sample_name_contains:
        sql += " AND s.sample_name LIKE %s"; params.append(f"%{sample_name_contains}%")
    if analyte_code:
        sql += " AND r.analyte_code=%s"; params.append(analyte_code)
    sql += " ORDER BY s.lab_date DESC,s.sample_name,r.analyte_code LIMIT %s"; params.append(bounded(limit, 250))
    return json_ready(fetch_all(sql, tuple(params)))


@mcp.tool()
def lab_decision_context(sample_id: str) -> dict[str, Any]:
    """Get one lab sample with comparable history, approved reference ranges, current interpretation, and decision notes. Measurements and suggestions remain distinct; an unapproved suggestion is never reported as an approved cellar action."""
    sample = fetch_one("SELECT * FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise ValueError("Lab sample not found")
    return json_ready({
        "sample": sample,
        "results": fetch_all("SELECT * FROM v_lab_comparison WHERE sample_id=%s ORDER BY analyte_name", (sample_id,)),
        "history": fetch_all("SELECT c.* FROM v_lab_comparison c JOIN (SELECT DISTINCT analyte_code FROM lab_results WHERE sample_id=%s) a ON a.analyte_code=c.analyte_code WHERE c.estate_id=%s AND c.sample_id<>%s ORDER BY c.analyte_code,c.lab_date DESC LIMIT 150", (sample_id, estate_id(), sample_id)),
        "review": fetch_one("SELECT * FROM lab_reviews WHERE sample_id=%s", (sample_id,)),
        "decision_notes": fetch_all("SELECT * FROM lab_decision_notes WHERE sample_id=%s ORDER BY noted_at", (sample_id,)),
    })


@mcp.tool()
def weather_summary(days: int = 14) -> dict[str, Any]:
    """Get recent vineyard weather plus current GDD forecasts. Use for context, not as automatic treatment approval."""
    return json_ready({
        "observations": fetch_all("SELECT observed_at,temp_c,feels_like_c,humidity_pct,dew_point_c,vpd_kpa,pressure_hpa,rain_mm,rain_rate_mm_h,wind_kph,wind_gust_kph,gust_max_today_kph,wind_direction_deg,wind_direction_10m_deg,solar_wm2,uv_index,leaf_wetness_pct,soil_moisture_pct,soil_temp_c,sensor_battery_v,sensor_capacitor_v FROM weather_observations WHERE estate_id=%s AND observed_at >= DATE_SUB(NOW(),INTERVAL %s DAY) ORDER BY observed_at", (estate_id(), bounded(days, 120))),
        "gdd_forecasts": fetch_all("SELECT s.vintage_year,v.name variety,g.target_gdd,g.observed_through,g.observed_gdd,g.forecast_through,g.forecast_gdd,g.final_forecast_date,g.confidence,g.calibration_evidence,g.computed_at FROM gdd_forecasts g JOIN seasons s ON s.id=g.season_id JOIN grape_varieties v ON v.id=g.variety_id WHERE g.estate_id=%s ORDER BY g.computed_at DESC,v.name LIMIT 12", (estate_id(),)),
    })


@mcp.tool()
def open_issues(priority: Literal["all", "critical", "high", "medium", "low"] = "all", limit: int = 50) -> list[dict[str, Any]]:
    """List open or monitored issues and decisions, including evidence, owner, next action, and due date."""
    sql = "SELECT source_issue_id,opened_date,subject_ref,issue_type,priority,issue_text,evidence_summary,decision_action,owner_text,due_date,status,notes FROM issues_decisions WHERE estate_id=%s AND status IN ('open','monitoring')"
    params: list[Any] = [estate_id()]
    if priority != "all": sql += " AND priority=%s"; params.append(priority)
    sql += " ORDER BY FIELD(priority,'critical','high','medium','low'),due_date LIMIT %s"; params.append(bounded(limit))
    return json_ready(fetch_all(sql, tuple(params)))


@mcp.tool()
def financial_overview(fiscal_year: int = datetime.now().year) -> dict[str, Any]:
    """Get private Baiamonte financial performance, budget, cash, invoices, VAT, inventory, and vineyard unit economics. Actual, budget, and forecast values remain distinct."""
    return json_ready({
        "fiscal_year": fiscal_year,
        "monthly": fetch_all("SELECT * FROM v_budget_vs_actual WHERE estate_id=%s AND fiscal_year=%s ORDER BY fiscal_month", (estate_id(), fiscal_year)),
        "annual": fetch_all("SELECT a.*,s.name scenario,s.scenario_type,s.selected FROM annual_financial_summary a JOIN financial_scenarios s ON s.id=a.scenario_id WHERE a.estate_id=%s AND a.fiscal_year=%s ORDER BY s.scenario_type", (estate_id(), fiscal_year)),
        "cash": fetch_all("SELECT * FROM v_cash_balances WHERE estate_id=%s ORDER BY name", (estate_id(),)),
        "open_invoices": fetch_all("SELECT * FROM v_finance_document_totals WHERE estate_id=%s AND payment_status IN ('unpaid','part_paid','unknown') ORDER BY due_date IS NULL,due_date LIMIT 30", (estate_id(),)),
        "vat": fetch_all("SELECT * FROM vat_returns WHERE estate_id=%s AND fiscal_year=%s", (estate_id(), fiscal_year)),
        "inventory": fetch_all("SELECT * FROM v_inventory_current WHERE estate_id=%s ORDER BY category_name,name", (estate_id(),)),
        "unit_economics": fetch_all("SELECT * FROM v_vineyard_unit_economics WHERE vintage_year=%s", (fiscal_year,)),
    })


@mcp.tool()
def funding_report(include_closed: bool = False) -> dict[str, Any]:
    """Get funding opportunities, applications, eligibility documents, milestones, capital budgets, and source verification dates. A planning or open status is never an award."""
    status_filter = "" if include_closed else " AND LOWER(o.status) NOT LIKE 'closed%'"
    return json_ready({
        "opportunities": fetch_all("SELECT * FROM v_funding_control o WHERE estate_id=%s" + status_filter + " ORDER BY FIELD(priority,'critical','high','medium','low'),deadline IS NULL,deadline", (estate_id(),)),
        "requirements": fetch_all("SELECT * FROM funding_requirements WHERE estate_id=%s ORDER BY FIELD(status,'blocked','in_progress','not_started','expired','complete','not_applicable'),due_date IS NULL,due_date", (estate_id(),)),
        "milestones": fetch_all("SELECT * FROM funding_milestones WHERE estate_id=%s ORDER BY starts_on IS NULL,starts_on,ends_on", (estate_id(),)),
        "projects": fetch_all("SELECT * FROM capital_projects WHERE estate_id=%s ORDER BY status,name", (estate_id(),)),
        "budget_lines": fetch_all("SELECT l.*,p.code project_code,p.name project_name FROM capital_budget_lines l JOIN capital_projects p ON p.id=l.project_id WHERE p.estate_id=%s ORDER BY p.code,l.cost_code", (estate_id(),)),
    })


@mcp.tool()
def search_vineyard_records(
    record_type: Literal["work", "tasks", "labor", "equipment", "olive", "treatments", "cellar"],
    year: int | None = None,
    text_contains: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search a bounded, approved vineyard record type. This never accepts or runs SQL from the caller."""
    definitions = {
        "work": ("work_activities", "activity_date", "CONCAT_WS(' ',title,category,notes)"),
        "tasks": ("tasks", "due_date", "CONCAT_WS(' ',title,category,notes)"),
        "labor": ("labor_entries", "work_date", "CONCAT_WS(' ',person_or_crew,role,notes)"),
        "equipment": ("equipment_service_events", "event_date", "CONCAT_WS(' ',asset_name,maintenance_action,notes)"),
        "olive": ("olive_records", "record_date", "CONCAT_WS(' ',activity,details,notes)"),
        "treatments": ("spray_applications", "application_date", "CONCAT_WS(' ',purpose,operator_name,notes)"),
        "cellar": ("cellar_operations", "operation_at", "CONCAT_WS(' ',operation_type,notes)"),
    }
    table, date_column, search_expression = definitions[record_type]
    sql = f"SELECT * FROM {table} WHERE estate_id=%s"
    params: list[Any] = [estate_id()]
    if year is not None:
        sql += f" AND YEAR({date_column})=%s"; params.append(year)
    if text_contains:
        sql += f" AND {search_expression} LIKE %s"; params.append(f"%{text_contains}%")
    sql += f" ORDER BY {date_column} DESC LIMIT %s"; params.append(bounded(limit))
    return json_ready(fetch_all(sql, tuple(params)))


@mcp.tool()
def create_task(
    title: str,
    due_date: str | None = None,
    category: str = "general",
    priority: Literal["low", "normal", "high", "urgent"] = "normal",
    block_code: str | None = None,
    notes: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Create one vineyard task only after the user confirms the exact title/date/block. Pass confirmation='CONFIRM' after confirmation."""
    require_write_confirmation(confirmation)
    parsed_due = date.fromisoformat(due_date) if due_date else None
    block = fetch_one("SELECT id FROM vineyard_blocks WHERE estate_id=%s AND code=%s", (estate_id(), block_code)) if block_code else None
    record_id = new_id()
    values = {"title": title, "due_date": parsed_due, "category": category, "priority": priority, "block_code": block_code, "notes": notes}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO tasks (id,estate_id,season_id,block_id,title,category,priority,due_date,notes,source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'chatgpt')", (record_id, estate_id(), season_for_year((parsed_due or date.today()).year), block.get("id") if block else None, title, category, priority, parsed_due, notes))
        audit(cursor, "create", "task", record_id, values, actor="chatgpt")
    try:
        google_sync = publish_task_to_google(record_id)
    except Exception as error:
        google_sync = {"published": False, "reason": str(error)[:300]}
    return {"created": True, "id": record_id, "google_sync": google_sync, **json_ready(values)}


@mcp.tool()
def save_vineyard_record(
    record_type: Literal["task", "work_activity", "harvest_lot", "lab_sample", "issue_decision", "labor_entry", "equipment_event", "olive_record", "harvest_plan", "phenology", "scouting", "irrigation", "cellar_operation", "note", "spray_application"],
    fields: dict[str, Any],
    record_id: str | None = None,
    vintage_year: int | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Create or update one approved vineyard record. First present the exact proposed fields to the user; write only after they explicitly confirm and then pass confirmation='CONFIRM'. Use record_id to update an existing row. Names may be supplied as block_code, variety_name, wine_lot_code, container_code, or product_name."""
    require_write_confirmation(confirmation)
    definition = WRITE_RECORDS[record_type]
    values = resolve_named_references(fields)
    allowed = set(definition["fields"])
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Fields not allowed for {record_type}: {', '.join(unknown)}")

    defaults = dict(definition.get("defaults", {}))
    defaults = {key: (date.today().isoformat() if value == "__today__" else datetime.now().isoformat(timespec="seconds") if value == "__now__" else value) for key, value in defaults.items()}
    if record_id is None:
        values = {**defaults, **values}
        missing = sorted(field for field in definition["required"] if values.get(field) in (None, ""))
        if missing:
            raise ValueError(f"Missing required fields for {record_type}: {', '.join(missing)}")
    elif not values:
        raise ValueError("At least one field is required for an update")

    if record_type == "lab_sample":
        existing_lab = fetch_one("SELECT sample_type,variety_id FROM lab_samples WHERE id=%s AND estate_id=%s", (record_id, estate_id())) if record_id else {}
        effective_type = values.get("sample_type") or (existing_lab or {}).get("sample_type")
        effective_variety = values.get("variety_id") or (existing_lab or {}).get("variety_id")
        if effective_type == "grape" and not effective_variety:
            raise ValueError("A grape laboratory sample requires variety_name or variety_id so it updates the correct forecast")

    if record_type == "phenology":
        existing_stage = fetch_one(
            "SELECT stage_code,variety_id FROM phenology_observations WHERE id=%s AND estate_id=%s",
            (record_id, estate_id()),
        ) if record_id else {}
        effective_stage = values.get("stage_code") or (existing_stage or {}).get("stage_code")
        if effective_stage:
            values["stage_code"], values["stage_name"] = phenology_stage(effective_stage)
        if not (values.get("variety_id") or (existing_stage or {}).get("variety_id")):
            raise ValueError("Phenology requires variety_name or variety_id so it updates the correct forecast")
        if values.get("percent_complete") is not None:
            completion = float(values["percent_complete"])
            if not 0 <= completion <= 100:
                raise ValueError("Percent complete must be from 0 to 100")
            values["percent_complete"] = round(completion, 2)
    if record_type == "scouting":
        existing_scouting = fetch_one(
            "SELECT issue_type,severity,incidence_pct,damage_type FROM scouting_observations WHERE id=%s AND estate_id=%s",
            (record_id, estate_id()),
        ) if record_id else {}
        issue = scouting_issue(values.get("issue_type") or (existing_scouting or {}).get("issue_type"))
        values["issue_type"] = issue["code"]
        if values.get("severity") is not None:
            severity = str(values["severity"]).strip().casefold()
            if severity not in {"trace", "low", "medium", "high", "critical"}:
                raise ValueError("Choose trace, low, medium, high, or critical severity")
            values["severity"] = severity
        if values.get("incidence_pct") is not None:
            incidence = float(values["incidence_pct"])
            if not 0 <= incidence <= 100:
                raise ValueError("Incidence must be from 0 to 100")
            values["incidence_pct"] = round(incidence, 2)
        if "damage_assessment" in issue.get("pipelines", ()):
            values.update(derive_scouting_damage_fields({**(existing_scouting or {}), **values, "damage_type": issue.get("damage_type") or values.get("damage_type")}))

    if record_type == "spray_application" and values.get("status") == "completed":
        safety = ("agronomist_approved", "label_legal_confirmed", "phi_checked", "rei_checked", "weather_checked", "ppe_confirmed", "actual_details_confirmed")
        if record_id:
            existing_safety = fetch_one("SELECT " + ",".join(safety) + " FROM spray_applications WHERE id=%s AND estate_id=%s", (record_id, estate_id())) or {}
        else:
            existing_safety = {}
        missing = [field for field in safety if not values.get(field, existing_safety.get(field))]
        if missing:
            raise ValueError("A completed treatment requires explicit confirmations: " + ", ".join(missing))

    table = definition["table"]
    before = None
    if record_id:
        before = fetch_one(f"SELECT * FROM {table} WHERE id=%s AND estate_id=%s", (record_id, estate_id()))
        if not before:
            raise ValueError(f"{record_type} record not found")
    else:
        record_id = new_id()

    if table in {"tasks", "work_activities", "harvest_lots", "lab_samples", "labor_entries", "harvest_plans", "phenology_observations", "scouting_observations", "irrigation_events", "cellar_operations", "spray_applications"} and (not record_id or not before):
        values["season_id"] = season_for_year(record_year(values, vintage_year))
    if record_type == "harvest_lot" and values.get("weight_kg") is not None and values.get("crate_count"):
        values["avg_crate_kg"] = float(values["weight_kg"]) / int(values["crate_count"])
    if record_type == "olive_record" and not values.get("record_year"):
        values["record_year"] = record_year(values, vintage_year)
    if record_type == "note" and isinstance(values.get("tags"), list):
        values["tags"] = json.dumps(values["tags"], ensure_ascii=False)

    with transaction() as (_, cursor):
        if before:
            assignments = ",".join(f"{column}=%s" for column in values)
            cursor.execute(f"UPDATE {table} SET {assignments} WHERE id=%s AND estate_id=%s", (*values.values(), record_id, estate_id()))
            action = "update"
        else:
            insert_values = {"id": record_id, "estate_id": estate_id(), **values}
            columns = ",".join(insert_values)
            placeholders = ",".join(["%s"] * len(insert_values))
            cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(insert_values.values()))
            action = "create"
        if record_type == "scouting":
            cursor.execute(
                "INSERT INTO scouting_damage_scopes (observation_id,estate_id,damage_scope,representative_survey) "
                "VALUES (%s,%s,'block',0) ON DUPLICATE KEY UPDATE observation_id=VALUES(observation_id)",
                (record_id, estate_id()),
            )
        cursor.execute(
            "INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data) VALUES (%s,'chatgpt',%s,%s,%s,%s,%s)",
            (estate_id(), action, record_type, record_id, json.dumps(json_ready(before), default=str) if before else None, json.dumps(json_ready(values), default=str)),
        )
    pipeline_results = route_saved_observation(record_type, record_id, values.get("issue_type"))
    prediction_refresh = record_type in {"harvest_lot", "harvest_plan", "spray_application"}
    if record_type == "lab_sample":
        effective_type = values.get("sample_type") or (before or {}).get("sample_type")
        effective_review = values.get("needs_review", (before or {}).get("needs_review", 0))
        prediction_refresh = effective_type == "grape" and not bool(effective_review)
    elif record_type in {"scouting", "phenology"}:
        prediction_refresh = any(row.get("code") == "harvest_prediction" and row.get("status") == "queued" for row in pipeline_results)
    if prediction_refresh:
        request_harvest_refresh(record_type, record_id, "Prediction evidence saved through MCP")
    lab_learning = None
    if record_type == "lab_sample":
        try:
            lab_learning = refresh_lab_learning(record_id)
        except Exception as error:
            lab_learning = {"model_status": "refresh_failed", "error": str(error)[:300]}
    return {"saved": True, "action": action, "record_type": record_type, "record_id": record_id, "prediction_refresh": "queued" if prediction_refresh else "not_applicable", "pipelines": pipeline_results, "lab_learning": lab_learning, "fields": json_ready(values)}


@mcp.tool()
def save_lab_result(
    sample_id: str,
    analyte_code: str,
    analyte_name: str,
    numeric_value: float | None = None,
    text_value: str | None = None,
    unit: str | None = None,
    method: str | None = None,
    flag: Literal["low", "normal", "high", "review"] | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Add or correct one result on an existing lab sample after showing the exact change and receiving confirmation."""
    require_write_confirmation(confirmation)
    if numeric_value is None and not text_value:
        raise ValueError("numeric_value or text_value is required")
    sample = fetch_one("SELECT id FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise ValueError("Lab sample not found")
    before = fetch_one("SELECT * FROM lab_results WHERE sample_id=%s AND analyte_code=%s", (sample_id, analyte_code))
    result_id = before["id"] if before else new_id()
    after = {"analyte_code": analyte_code, "analyte_name": analyte_name, "numeric_value": numeric_value, "text_value": text_value, "unit": unit, "method": method, "flag": flag}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_results (id,sample_id,analyte_code,analyte_name,numeric_value,text_value,unit,method,flag) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE analyte_name=VALUES(analyte_name),numeric_value=VALUES(numeric_value),text_value=VALUES(text_value),unit=VALUES(unit),method=VALUES(method),flag=VALUES(flag)", (result_id, sample_id, analyte_code, analyte_name, numeric_value, text_value, unit, method, flag))
        cursor.execute("INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data) VALUES (%s,'chatgpt',%s,'lab_result',%s,%s,%s)", (estate_id(), "update" if before else "create", result_id, json.dumps(json_ready(before), default=str) if before else None, json.dumps(after, default=str)))
    sample_type = (fetch_one("SELECT sample_type FROM lab_samples WHERE id=%s", (sample_id,)) or {}).get("sample_type")
    if sample_type == "grape":
        request_harvest_refresh("lab_result", result_id, "Grape laboratory result saved through MCP")
    try:
        lab_learning = refresh_lab_learning(sample_id)
    except Exception as error:
        lab_learning = {"model_status": "refresh_failed", "error": str(error)[:300]}
    return {"saved": True, "action": "update" if before else "create", "record_id": result_id, "prediction_refresh": "queued" if sample_type == "grape" else "not_applicable", "lab_learning": lab_learning, **after}


@mcp.tool()
def save_lab_review(
    sample_id: str,
    review_status: Literal["unreviewed", "reviewing", "decision_needed", "monitoring", "closed"],
    interpretation: str | None = None,
    decision_action: str | None = None,
    decision_type: Literal["observe", "repeat_test", "adjustment", "hold", "release", "investigate", "other"] | None = None,
    owner_text: str | None = None,
    next_check_at: str | None = None,
    enologist_approval_required: bool = True,
    approved_by: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Save a lab interpretation or decision after confirmation. If enologist approval is required, the record remains a recommendation unless approved_by is explicitly supplied from the user's confirmed facts."""
    require_write_confirmation(confirmation)
    sample = fetch_one("SELECT id FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id()))
    if not sample:
        raise ValueError("Lab sample not found")
    if approved_by and enologist_approval_required is False:
        raise ValueError("An approver can only be recorded on a review that tracks approval")
    review_id = new_id()
    approved_at = datetime.now() if approved_by else None
    after = {"review_status": review_status, "interpretation": interpretation, "decision_action": decision_action, "decision_type": decision_type, "owner_text": owner_text, "next_check_at": next_check_at, "enologist_approval_required": enologist_approval_required, "approved_by": approved_by, "approved_at": approved_at}
    before = fetch_one("SELECT * FROM lab_reviews WHERE sample_id=%s", (sample_id,))
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO lab_reviews (id,estate_id,sample_id,review_status,interpretation,decision_action,decision_type,owner_text,next_check_at,enologist_approval_required,approved_by,approved_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE review_status=VALUES(review_status),interpretation=VALUES(interpretation),decision_action=VALUES(decision_action),decision_type=VALUES(decision_type),owner_text=VALUES(owner_text),next_check_at=VALUES(next_check_at),enologist_approval_required=VALUES(enologist_approval_required),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at)", (review_id, estate_id(), sample_id, review_status, interpretation, decision_action, decision_type, owner_text, next_check_at, int(enologist_approval_required), approved_by, approved_at))
        audit(cursor, "update" if before else "create", "lab_review", sample_id, after, actor="chatgpt")
    return {"saved": True, "sample_id": sample_id, **json_ready(after)}


def finance_party_id(cursor: Any, name: str | None, party_type: str) -> str | None:
    if not name:
        return None
    row = fetch_one("SELECT id FROM finance_parties WHERE estate_id=%s AND name=%s", (estate_id(), name))
    if row:
        return row["id"]
    party_id = new_id()
    cursor.execute("INSERT INTO finance_parties (id,estate_id,party_type,name,source) VALUES (%s,%s,%s,%s,'chatgpt')", (party_id, estate_id(), party_type, name))
    return party_id


@mcp.tool()
def save_financial_document(
    document_type: Literal["sales_invoice", "purchase_invoice", "credit_note", "receipt", "other"],
    document_number: str,
    document_date: str,
    party_name: str | None = None,
    taxable_amount: float = 0,
    vat_amount: float = 0,
    withholding_tax: float = 0,
    due_date: str | None = None,
    payment_status: Literal["unpaid", "part_paid", "paid", "not_applicable", "unknown"] = "unknown",
    notes: str | None = None,
    record_id: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Record or correct an invoice/financial document after showing the exact fields and receiving confirmation. This records data only; it never issues an invoice, sends money, files tax, or submits anything externally."""
    require_write_confirmation(confirmation)
    parsed_date = date.fromisoformat(document_date)
    parsed_due = date.fromisoformat(due_date) if due_date else None
    before = fetch_one("SELECT * FROM financial_documents WHERE id=%s AND estate_id=%s", (record_id, estate_id())) if record_id else None
    if record_id and not before:
        raise ValueError("Financial document not found")
    record_id = record_id or new_id()
    gross_total = taxable_amount + vat_amount - withholding_tax
    after = {"document_type": document_type, "document_number": document_number, "document_date": parsed_date, "due_date": parsed_due, "party_name": party_name, "taxable_amount": taxable_amount, "vat_amount": vat_amount, "withholding_tax": withholding_tax, "gross_total": gross_total, "payment_status": payment_status, "notes": notes}
    with transaction() as (_, cursor):
        party_id = finance_party_id(cursor, party_name, "customer" if document_type == "sales_invoice" else "supplier")
        status = "issued" if document_type == "sales_invoice" else "received"
        if before:
            cursor.execute("UPDATE financial_documents SET document_type=%s,document_number=%s,document_date=%s,due_date=%s,party_id=%s,taxable_amount=%s,vat_amount=%s,withholding_tax=%s,gross_total=%s,status=%s,payment_status=%s,notes=%s WHERE id=%s AND estate_id=%s", (document_type, document_number, parsed_date, parsed_due, party_id, taxable_amount, vat_amount, withholding_tax, gross_total, status, payment_status, notes, record_id, estate_id()))
            action = "update"
        else:
            cursor.execute("INSERT INTO financial_documents (id,estate_id,document_type,document_number,document_date,due_date,party_id,taxable_amount,vat_amount,withholding_tax,gross_total,status,payment_status,source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'chatgpt',%s)", (record_id, estate_id(), document_type, document_number, parsed_date, parsed_due, party_id, taxable_amount, vat_amount, withholding_tax, gross_total, status, payment_status, notes))
            action = "create"
        cursor.execute("INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data) VALUES (%s,'chatgpt',%s,'financial_document',%s,%s,%s)", (estate_id(), action, record_id, json.dumps(json_ready(before), default=str) if before else None, json.dumps(json_ready(after), default=str)))
    return {"saved": True, "action": action, "record_id": record_id, **json_ready(after)}


@mcp.tool()
def save_cash_transaction(
    account_name: str,
    transaction_date: str,
    description: str,
    amount_in: float = 0,
    amount_out: float = 0,
    transaction_type: Literal["customer_receipt", "supplier_payment", "owner_contribution", "owner_draw", "bank_fee", "tax", "transfer", "refund", "other"] = "other",
    party_name: str | None = None,
    notes: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Record one cash movement after showing the exact account, date, description, direction, and amount and receiving confirmation. This records data only and never sends money."""
    require_write_confirmation(confirmation)
    if (amount_in > 0) == (amount_out > 0):
        raise ValueError("Enter exactly one positive amount: amount_in or amount_out")
    parsed_date = date.fromisoformat(transaction_date)
    record_id = new_id()
    after = {"account_name": account_name, "transaction_date": parsed_date, "description": description, "amount_in": amount_in, "amount_out": amount_out, "transaction_type": transaction_type, "party_name": party_name, "notes": notes}
    with transaction() as (_, cursor):
        account = fetch_one("SELECT id FROM cash_accounts WHERE estate_id=%s AND name=%s", (estate_id(), account_name))
        account_id = account["id"] if account else new_id()
        if not account:
            cursor.execute("INSERT INTO cash_accounts (id,estate_id,name,account_type) VALUES (%s,%s,%s,'other')", (account_id, estate_id(), account_name))
        party_id = finance_party_id(cursor, party_name, "other")
        cursor.execute("INSERT INTO cash_transactions (id,estate_id,cash_account_id,transaction_date,description,party_id,transaction_type,amount_in,amount_out,source,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'chatgpt',%s)", (record_id, estate_id(), account_id, parsed_date, description, party_id, transaction_type, amount_in, amount_out, notes))
        audit(cursor, "create", "cash_transaction", record_id, after, actor="chatgpt")
    return {"saved": True, "record_id": record_id, **json_ready(after)}


@mcp.tool()
def update_funding_requirement(
    requirement_id: str,
    status: Literal["not_started", "in_progress", "complete", "not_applicable", "blocked", "expired"],
    owner_text: str | None = None,
    due_date: str | None = None,
    evidence_url: str | None = None,
    notes: str | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Update an internal funding-readiness item after confirmation. This never submits an application or declares eligibility or an award."""
    require_write_confirmation(confirmation)
    before = fetch_one("SELECT * FROM funding_requirements WHERE id=%s AND estate_id=%s", (requirement_id, estate_id()))
    if not before:
        raise ValueError("Funding requirement not found")
    after = {"status": status, "owner_text": owner_text, "due_date": date.fromisoformat(due_date) if due_date else None, "evidence_url": evidence_url, "notes": notes}
    with transaction() as (_, cursor):
        cursor.execute("UPDATE funding_requirements SET status=%s,owner_text=COALESCE(%s,owner_text),due_date=COALESCE(%s,due_date),evidence_url=COALESCE(%s,evidence_url),notes=COALESCE(%s,notes) WHERE id=%s AND estate_id=%s", (status, owner_text, after["due_date"], evidence_url, notes, requirement_id, estate_id()))
        cursor.execute("INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,before_data,after_data) VALUES (%s,'chatgpt','update','funding_requirement',%s,%s,%s)", (estate_id(), requirement_id, json.dumps(json_ready(before), default=str), json.dumps(json_ready(after), default=str)))
    return {"saved": True, "record_id": requirement_id, **json_ready(after)}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if request.url.path.rstrip("/").endswith("/health"):
            return await call_next(request)
        expected = settings.mcp_server_token
        supplied = request.headers.get("Authorization", "")
        if not expected or supplied != f"Bearer {expected}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


mcp_http = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: Starlette):
    async with mcp.session_manager.run():
        yield


http_app = Starlette(routes=[Mount("/", app=mcp_http)], lifespan=lifespan)
http_app.add_middleware(BearerTokenMiddleware)


if __name__ == "__main__":
    mcp.run(transport="stdio")
