from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from .db import fetch_one, transaction
from .inventory import sync_treatment_inventory_use
from .production_impact import derive_scouting_damage_fields, refresh_scouting_damage_proposal
from .service import estate_id, json_ready, new_id, season_for_year


DEFINITIONS: dict[str, dict[str, Any]] = {
    "maturity_sample": {
        "table": "maturity_samples",
        "fields": {"block_id", "variety_id", "sampled_at", "berry_count", "sample_kg", "brix", "ph", "ta_g_l", "yan_mg_l", "fruit_temp_c", "disease_pct", "condition_notes", "decision", "provisional_pick_date", "sampler", "notes"},
        "required": {"sampled_at"},
        "date_field": "sampled_at",
        "defaults": {"decision": "monitor"},
    },
    "harvest_plan": {
        "table": "harvest_plans",
        "fields": {"variety_id", "block_reference", "planned_pick_date", "status", "planned_kg", "planned_crates", "crew_size", "planned_hours", "cellar_destination", "weather_risk", "dependencies", "approved_by", "confidence", "forecast_method", "notes"},
        "required": {"variety_id", "planned_pick_date"},
        "date_field": "planned_pick_date",
        "defaults": {"status": "provisional", "forecast_method": "manual"},
    },
    "cellar_lot": {
        "table": "wine_lots",
        "fields": {"code", "harvest_lot_reference", "name", "stage", "lot_status", "volume_l", "fruit_kg", "initial_l", "free_run_l", "press_l", "loss_l", "variety_summary", "current_container_id", "started_at", "responsible", "notes"},
        "required": {"code", "name", "stage"},
        "date_field": "started_at",
        "defaults": {"stage": "must", "lot_status": "active"},
    },
    "blend_plan": {
        "table": "blend_plans",
        "fields": {"code", "name", "planned_blend_date", "target_grapes_kg", "target_volume_l", "planned_bottles", "crate_weight_kg", "expected_yield_l_per_kg", "components_text", "target_style", "decision_status", "approved_by", "notes"},
        "required": {"code", "name", "components_text"},
        "date_field": "planned_blend_date",
        "defaults": {"decision_status": "draft", "crate_weight_kg": 15},
    },
    "fermentation": {
        "table": "fermentation_observations",
        "fields": {"wine_lot_id", "observed_at", "vessel_name", "stage", "temp_c", "density_sg", "brix", "ph", "cap_management", "addition_action", "product_lot", "quantity", "unit", "sensory_observation", "owner_text", "next_check_at", "status"},
        "required": {"observed_at"},
        "date_field": "observed_at",
        "defaults": {"status": "monitoring"},
    },
    "mass_balance": {
        "table": "mass_balance_records",
        "fields": {"harvest_lot_reference", "block_reference", "variety_name", "net_grapes_kg", "must_wine_l", "free_run_l", "press_l", "recorded_loss_l", "reconciliation_status", "owner_text", "notes"},
        "required": {"harvest_lot_reference"},
        "date_field": "harvest_lot_reference",
        "defaults": {"reconciliation_status": "open"},
    },
    "equipment_event": {
        "table": "equipment_service_events",
        "fields": {"event_date", "asset_name", "pre_use_status", "cleaning_started_at", "cleaning_ended_at", "sanitation_method", "concentration", "released", "released_by", "downtime_hours", "maintenance_action", "next_due_date", "notes"},
        "required": {"event_date", "asset_name"},
        "date_field": "event_date",
        "defaults": {"released": 0},
    },
    "cellar_operation": {
        "table": "cellar_operations",
        "fields": {"operation_at", "operation_type", "wine_lot_id", "container_id", "amount", "unit", "product_id", "temp_c", "notes"},
        "required": {"operation_at", "operation_type"},
        "date_field": "operation_at",
    },
    "scouting": {
        "table": "scouting_observations",
        "fields": {"block_id", "variety_id", "observed_at", "issue_type", "severity", "incidence_pct", "damage_type", "damage_scope", "reported_zone_area_ha", "representative_survey", "affected_area_pct", "estimated_yield_loss_pct", "yield_impact_confidence", "yield_impact_source", "yield_impact_review_status", "location_note", "action_required", "notes", "photo_url"},
        "required": {"observed_at", "issue_type"},
        "date_field": "observed_at",
        "defaults": {"severity": "low", "action_required": 0},
    },
    "phenology": {
        "table": "phenology_observations",
        "fields": {"block_id", "variety_id", "observed_date", "stage_code", "stage_name", "percent_complete", "notes", "photo_url"},
        "required": {"block_id", "observed_date", "stage_code"},
        "date_field": "observed_date",
    },
    "labor": {
        "table": "labor_entries",
        "fields": {"work_date", "shift_label", "person_or_crew", "role", "work_category", "work_performed", "location_text", "start_time", "end_time", "regular_hours", "overtime_hours", "hourly_rate_eur", "labor_cost_eur", "other_cost_eur", "expense_amount_eur", "expense_category", "expense_notes", "kg_handled", "incident_near_miss", "approved_by", "payment_status", "payroll_scope", "entry_source", "notes"},
        "required": {"work_date", "person_or_crew"},
        "date_field": "work_date",
        "defaults": {"payment_status": "unknown", "payroll_scope": "unknown"},
    },
    "treatment": {
        "table": "spray_applications",
        "fields": {"crop_scope", "block_id", "application_date", "purpose", "area_ha", "water_volume_l", "operator_name", "equipment_name", "temp_c", "wind_kph", "status", "notes", "agronomist_approved", "label_legal_confirmed", "phi_checked", "rei_checked", "weather_checked", "ppe_confirmed", "actual_details_confirmed"},
        "required": {"application_date", "purpose"},
        "date_field": "application_date",
        "defaults": {"crop_scope": "vineyard", "status": "planned", "agronomist_approved": 0, "label_legal_confirmed": 0, "phi_checked": 0, "rei_checked": 0, "weather_checked": 0, "ppe_confirmed": 0, "actual_details_confirmed": 0},
        "item_fields": {"product_id", "dose_amount", "dose_unit", "total_used", "phi_days", "item_notes"},
    },
    "inventory_count": {
        "table": "inventory_snapshots",
        "fields": {"product_id", "snapshot_date", "quantity_on_hand", "opening_quantity", "average_cost", "average_sales_price", "inventory_value", "notes"},
        "required": {"product_id", "snapshot_date"},
        "date_field": "snapshot_date",
        "defaults": {"source": "home-assistant"},
    },
    "olive": {
        "table": "olive_records",
        "fields": {"record_year", "record_date", "activity", "details", "status", "worker_text", "labor_hours", "olives_harvested_kg", "mill_date", "oil_liters", "yield_pct", "notes", "evidence"},
        "required": {"record_date", "activity"},
        "date_field": "record_date",
    },
    "issue": {
        "table": "issues_decisions",
        "fields": {"opened_date", "subject_ref", "issue_type", "priority", "issue_text", "evidence_summary", "decision_action", "owner_text", "due_date", "status", "closed_date", "notes"},
        "required": {"issue_text"},
        "date_field": "opened_date",
        "defaults": {"opened_date": "__today__", "issue_type": "Data", "priority": "medium", "status": "open"},
    },
    "financial_document": {
        "table": "financial_documents",
        "fields": {"document_type", "document_number", "document_date", "due_date", "party_id", "currency", "taxable_amount", "vat_amount", "withholding_tax", "social_security_withholding", "gross_total", "deductible_pct", "vat_deductible_pct", "depreciation_years", "status", "payment_status", "source_document", "notes"},
        "required": {"document_type", "document_number", "document_date"},
        "date_field": "document_date",
        "defaults": {"currency": "EUR", "taxable_amount": 0, "vat_amount": 0, "withholding_tax": 0, "social_security_withholding": 0, "source": "home-assistant", "payment_status": "unknown"},
    },
}


def _year(values: dict[str, Any], field: str) -> int:
    raw = values.get(field)
    return int(str(raw)[:4]) if raw else date.today().year


def save_quick_entry(record_type: str, supplied: dict[str, Any]) -> dict[str, Any]:
    if record_type not in DEFINITIONS:
        raise ValueError("Unsupported quick-entry record type")
    definition = DEFINITIONS[record_type]
    values = {key: value for key, value in supplied.items() if value != ""}
    item_fields = definition.get("item_fields", set())
    item = {key: values.pop(key) for key in list(values) if key in item_fields}
    allowed = set(definition["fields"])
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError("Fields not allowed: " + ", ".join(unknown))
    defaults = {
        key: date.today().isoformat() if value == "__today__" else value
        for key, value in definition.get("defaults", {}).items()
    }
    values = {**defaults, **values}
    missing = sorted(key for key in definition["required"] if values.get(key) in (None, ""))
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))

    if record_type == "treatment" and values.get("status") == "completed":
        checks = ("agronomist_approved", "label_legal_confirmed", "phi_checked", "rei_checked", "weather_checked", "ppe_confirmed", "actual_details_confirmed")
        missing_checks = [key for key in checks if not values.get(key)]
        if missing_checks:
            raise ValueError("Completed treatments require: " + ", ".join(missing_checks))
        if not item.get("product_id") or item.get("dose_amount") is None or not item.get("dose_unit"):
            raise ValueError("Completed treatments require product and dose details")
    if record_type == "treatment" and values.get("crop_scope") not in {"vineyard", "olives"}:
        raise ValueError("Choose Vineyard or Olives for the treatment program")

    table = definition["table"]
    record_id = new_id()
    season_tables = {"maturity_samples", "harvest_plans", "wine_lots", "blend_plans", "cellar_operations", "scouting_observations", "phenology_observations", "labor_entries", "spray_applications"}
    if table in season_tables:
        raw_date = values.get(definition["date_field"])
        values["season_id"] = season_for_year(_year(values, definition["date_field"])) if raw_date else season_for_year(date.today().year)
    if record_type == "scouting":
        scope = str(values.get("damage_scope") or "block").strip().casefold()
        if scope not in {"zone", "block", "variety", "estate"}:
            raise ValueError("Choose reported zone, mapped block, selected variety, or whole estate scope")
        if scope in {"zone", "block"} and not values.get("block_id"):
            raise ValueError("Zone and block assessments require a mapped vineyard block")
        if scope == "zone":
            try:
                zone_area = float(values.get("reported_zone_area_ha") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("Enter the reported zone area in hectares") from exc
            if not 0 < zone_area <= 1000:
                raise ValueError("Reported-zone assessments require a valid zone area in hectares")
            values["reported_zone_area_ha"] = round(zone_area, 4)
        else:
            values["reported_zone_area_ha"] = None
        if scope == "variety" and not values.get("variety_id"):
            raise ValueError("Variety-wide assessments require a selected variety")
        if scope in {"variety", "estate"}:
            anchor = fetch_one(
                "SELECT id FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code,id LIMIT 1",
                (estate_id(),),
            )
            if not anchor:
                raise ValueError("A mapped vineyard block is required before recording an estate-wide survey")
            # The legacy scouting table requires a block. Scope remains authoritative;
            # this validated anchor is storage-only and is ignored by estate/variety math.
            values["block_id"] = anchor["id"]
        values["variety_id"] = values.get("variety_id") if scope == "variety" else None
        values["representative_survey"] = int(bool(values.get("representative_survey")))
        if scope in {"variety", "estate"} and not values["representative_survey"]:
            raise ValueError("Variety and whole-estate assessments must be marked as a representative survey")
        values["damage_scope"] = scope
        values.update(derive_scouting_damage_fields(values))
    if record_type == "olive":
        values["record_year"] = values.get("record_year") or _year(values, "record_date")
    if record_type == "labor":
        worker = str(values.get("person_or_crew") or "").strip()
        if not worker or worker == "__other__":
            raise ValueError("Choose a worker or enter a contractor name")
        values["person_or_crew"] = worker
        if values.get("regular_hours") is None and values.get("start_time") and values.get("end_time"):
            start = datetime.strptime(str(values["start_time"]), "%H:%M")
            end = datetime.strptime(str(values["end_time"]), "%H:%M")
            hours = (end - start).total_seconds() / 3600
            if hours < 0:
                hours += 24
            values["regular_hours"] = round(hours, 2)
        fixed_job = values.get("entry_source") == "manual_job" or values.get("work_category") == "one_off_charge"
        regular_hours = float(values.get("regular_hours") or 0)
        overtime_hours = float(values.get("overtime_hours") or 0)
        if fixed_job:
            job_cost = float(values.get("expense_amount_eur") or values.get("other_cost_eur") or 0)
            if job_cost <= 0 or job_cost > 100000:
                raise ValueError("Enter a valid agreed job cost")
            category = str(values.get("expense_category") or "contractor_job").strip().casefold().replace(" ", "_")
            allowed_categories = {"contractor_job", "water_delivery", "equipment", "transport", "materials", "fuel", "tools", "service", "other"}
            if category not in allowed_categories:
                raise ValueError("Choose a valid job or expense category")
            expense_notes = str(values.get("expense_notes") or values.get("work_performed") or "").strip() or None
            values.update({
                "regular_hours": 0,
                "overtime_hours": 0,
                "hourly_rate_eur": None,
                "labor_cost_eur": 0,
                "other_cost_eur": round(job_cost, 2),
                "expense_amount_eur": round(job_cost, 2),
                "expense_category": category,
                "expense_notes": expense_notes,
                "work_category": "one_off_charge",
                "entry_source": "manual_job",
                "payment_status": "unpaid",
            })
        else:
            if regular_hours < 0 or overtime_hours < 0 or regular_hours + overtime_hours <= 0 or regular_hours + overtime_hours > 24:
                raise ValueError("Enter worked hours, or choose Fixed-price job / service")
            values["regular_hours"] = round(regular_hours, 2)
            values["overtime_hours"] = round(overtime_hours, 2)
            values["entry_source"] = values.get("entry_source") or "manual_labor"
            values["payment_status"] = "unpaid"
            values["other_cost_eur"] = None
            values["expense_amount_eur"] = None
            values["expense_category"] = None
            values["expense_notes"] = None
            if values.get("labor_cost_eur") is None and values.get("hourly_rate_eur") is not None:
                values["labor_cost_eur"] = round((regular_hours + overtime_hours) * float(values["hourly_rate_eur"]), 2)
    if record_type == "financial_document":
        values["gross_total"] = values.get("gross_total") if values.get("gross_total") is not None else float(values.get("taxable_amount") or 0) + float(values.get("vat_amount") or 0) - float(values.get("withholding_tax") or 0) - float(values.get("social_security_withholding") or 0)
        if not values.get("status"):
            values["status"] = "issued" if values["document_type"] == "sales_invoice" else "received"
    values = {"id": record_id, "estate_id": estate_id(), **values}

    with transaction() as (_, cursor):
        columns = ",".join(values)
        cursor.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join(['%s'] * len(values))})", tuple(values.values()))
        if record_type == "treatment" and item.get("product_id"):
            item_id = new_id()
            cursor.execute(
                "INSERT INTO spray_application_items (id,application_id,product_id,dose_amount,dose_unit,total_used,phi_days,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (item_id, record_id, item.get("product_id"), item.get("dose_amount"), item.get("dose_unit"), item.get("total_used"), item.get("phi_days"), item.get("item_notes")),
            )
            if values.get("status") == "completed":
                sync_treatment_inventory_use(cursor, record_id)
        cursor.execute(
            "INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data) VALUES (%s,'home-assistant','create',%s,%s,%s)",
            (estate_id(), record_type, record_id, json.dumps(json_ready({**values, **item}), default=str)),
        )
    if record_type == "scouting":
        refresh_scouting_damage_proposal(record_id)
    return {"saved": True, "record_type": record_type, "record_id": record_id, "id": record_id}
