from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from .db import fetch_one, transaction
from .inventory import sync_treatment_inventory_use
from .observation_catalog import PHENOLOGY_PIPELINES, PIPELINE_LABELS, phenology_stage, scouting_issue
from .production_impact import derive_scouting_damage_fields, refresh_scouting_damage_proposal
from .service import estate_id, json_ready, new_id, season_for_year


DEFINITIONS: dict[str, dict[str, Any]] = {
    "maturity_sample": {
        "table": "maturity_samples",
        "fields": {"block_id", "variety_id", "sampled_at", "berry_count", "sample_kg", "brix", "ph", "ta_g_l", "yan_mg_l", "fruit_temp_c", "disease_pct", "condition_notes", "decision", "provisional_pick_date", "sampler", "notes"},
        "required": {"sampled_at", "variety_id"},
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
        "fields": {"block_id", "variety_id", "observed_at", "issue_type", "severity", "incidence_pct", "damage_type", "damage_event_key", "linked_issue_id", "existing_chain", "damage_scope", "reported_zone_area_ha", "representative_survey", "affected_area_pct", "estimated_yield_loss_pct", "yield_impact_confidence", "yield_impact_source", "yield_impact_review_status", "location_note", "action_required", "notes", "photo_url", "treatment_application_id", "treatment_observation_phase", "treatment_target_code"},
        "required": {"observed_at", "issue_type"},
        "date_field": "observed_at",
        "defaults": {"severity": "low", "action_required": 0},
    },
    "phenology": {
        "table": "phenology_observations",
        "fields": {"block_id", "variety_id", "observed_date", "stage_code", "stage_name", "percent_complete", "notes", "photo_url"},
        "required": {"block_id", "variety_id", "observed_date", "stage_code"},
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


def _run_observation_pipelines(record_type: str, record_id: str, pipelines: tuple[str, ...]) -> list[dict[str, str]]:
    """Run every applicable pipeline and report each outcome independently."""
    results: list[dict[str, str]] = []
    for pipeline in pipelines:
        status = "queued"
        detail = "Evidence accepted"
        try:
            if pipeline == "damage_assessment":
                refresh_scouting_damage_proposal(record_id)
                status, detail = "processed", "Damage percentage proposal created for approval"
            elif pipeline == "phenology_model":
                status = "processed"
                detail = "Growth stage saved as structured seasonal evidence; GDD and year-over-year features will be read by the harvest refresh"
            elif pipeline in {"treatment_prediction", "stress_prediction"}:
                # Imported lazily to avoid coupling the quick-entry schema to the
                # intelligence service during application startup.
                from .intelligence import refresh_disease_pressure

                refresh_disease_pressure()
                status = "processed"
                detail = "Treatment/stress evidence recalculated; Agronomist approval remains required"
            elif pipeline == "treatment_followup":
                status = "review_required"
                detail = "Request representative wound photos now and again in 24–72 hours; no product is inferred until mold/rot or another treatment target is supported"
            elif pipeline == "harvest_prediction":
                from .prediction_refresh import request_harvest_refresh

                request_harvest_refresh(record_type, record_id, "Routed field evidence saved")
                status, detail = "queued", "Yield and pick-date model refresh queued"
            elif pipeline == "harvest_evidence_review":
                status = "evidence_required"
                detail = "Attach representative fruit photos or a maturity report; AI must identify usable ripening evidence before the harvest model is refreshed"
            elif pipeline == "agronomy_review":
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO issues_decisions "
                        "(id,estate_id,source_issue_id,opened_date,subject_ref,issue_type,priority,issue_text,evidence_summary,decision_action,owner_text,status) "
                        "VALUES (%s,%s,%s,CURDATE(),%s,'Agronomy','medium',%s,%s,%s,'Agronomist','open') "
                        "ON DUPLICATE KEY UPDATE evidence_summary=VALUES(evidence_summary),decision_action=VALUES(decision_action),"
                        "owner_text='Agronomist',status=IF(status IN ('resolved','deferred'),status,'open')",
                        (
                            new_id(), estate_id(), f"scouting-review:{record_id}", record_id,
                            "Classify field scouting observation",
                            f"Structured scouting record {record_id} requires classification before a safety-sensitive action is inferred.",
                            "Review the observation and attachments; classify the target and route any approved follow-up.",
                        ),
                    )
                status, detail = "review_required", "Held for Agronomist classification; no treatment was inferred"
        except Exception as error:  # The source record remains durable if a downstream service is unavailable.
            status, detail = "retry_required", str(error)[:300]
        results.append({"code": pipeline, "label": PIPELINE_LABELS[pipeline], "status": status, "detail": detail})
    return results


def route_saved_observation(record_type: str, record_id: str, issue_type: Any = None) -> list[dict[str, str]]:
    """Apply the same deterministic routes regardless of the input channel."""
    if record_type not in {"scouting", "phenology"}:
        return []
    pipelines = PHENOLOGY_PIPELINES if record_type == "phenology" else tuple(
        scouting_issue(issue_type).get("pipelines") or ("agronomy_review",)
    )
    return _run_observation_pipelines(record_type, record_id, pipelines)


def save_quick_entry(record_type: str, supplied: dict[str, Any]) -> dict[str, Any]:
    if record_type not in DEFINITIONS:
        raise ValueError("Unsupported quick-entry record type")
    definition = DEFINITIONS[record_type]
    scouting_scope_values: dict[str, Any] = {}
    scouting_pair_values: dict[str, Any] = {}
    scouting_pipelines: tuple[str, ...] = ()
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

    if record_type == "phenology":
        values["stage_code"], values["stage_name"] = phenology_stage(values.get("stage_code"))
        if values.get("percent_complete") is not None:
            try:
                completion = float(values["percent_complete"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Percent complete must be a number from 0 to 100") from exc
            if not 0 <= completion <= 100:
                raise ValueError("Percent complete must be from 0 to 100")
            values["percent_complete"] = round(completion, 2)

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
        for key in ("treatment_application_id", "treatment_observation_phase", "treatment_target_code"):
            scouting_pair_values[key] = values.pop(key, None)
        selected_chain = str(values.pop("existing_chain", "") or "").strip()
        issue = scouting_issue(values.get("issue_type"))
        legacy_detail = str(issue.get("legacy_detail") or "").strip()
        values["issue_type"] = issue["code"]
        scouting_pipelines = tuple(issue["pipelines"])
        severity = str(values.get("severity") or "low").strip().casefold()
        if severity not in {"trace", "low", "medium", "high", "critical"}:
            raise ValueError("Choose trace, low, medium, high, or critical severity")
        values["severity"] = severity
        if values.get("incidence_pct") is not None:
            try:
                incidence = float(values["incidence_pct"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Incidence must be a percentage from 0 to 100") from exc
            if not 0 <= incidence <= 100:
                raise ValueError("Incidence must be from 0 to 100")
            values["incidence_pct"] = round(incidence, 2)
        if legacy_detail:
            note = str(values.get("notes") or "").strip()
            values["notes"] = f"Original observation: {legacy_detail}" + (f"\n{note}" if note else "")
        if issue.get("requires_detail") and not any(str(values.get(key) or "").strip() for key in ("location_note", "notes")):
            raise ValueError("Add a short detail for Other / not listed so the Agronomist can classify it")
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
        if selected_chain:
            chain_kind, separator, chain_id = selected_chain.partition(":")
            chain_id = chain_id.strip()
            if not separator or chain_kind not in {"event", "issue"} or not chain_id:
                raise ValueError("Choose a valid existing issue or event chain")
            if chain_kind == "event":
                existing = fetch_one(
                    "SELECT event_key,damage_type FROM vineyard_damage_assessments "
                    "WHERE estate_id=%s AND season_id=%s AND event_key=%s AND active=1 LIMIT 1",
                    (estate_id(), values["season_id"], chain_id),
                )
                if not existing:
                    raise ValueError("The selected damage event is not active in this vintage")
                if "damage_assessment" not in scouting_pipelines:
                    raise ValueError("Only a damage observation can be added to a damage-event chain")
                expected_damage = str(existing.get("damage_type") or "").strip().casefold()
                actual_damage = str(issue.get("damage_type") or "").strip().casefold()
                if expected_damage and actual_damage and expected_damage != actual_damage:
                    raise ValueError("The observation type does not match the selected damage event")
                values["damage_event_key"] = chain_id
            else:
                existing = fetch_one(
                    "SELECT id FROM issues_decisions WHERE id=%s AND estate_id=%s AND status NOT IN ('resolved','closed','cancelled')",
                    (chain_id, estate_id()),
                )
                if not existing:
                    raise ValueError("The selected issue is no longer open")
                values["linked_issue_id"] = chain_id
        if "damage_assessment" in scouting_pipelines:
            values["damage_type"] = issue.get("damage_type") or values.get("damage_type")
            values.update(derive_scouting_damage_fields(values))
        else:
            for key in ("damage_type", "affected_area_pct", "estimated_yield_loss_pct", "yield_impact_confidence", "yield_impact_source", "yield_impact_review_status"):
                values.pop(key, None)
        for key in ("variety_id", "damage_scope", "reported_zone_area_ha", "representative_survey"):
            scouting_scope_values[key] = values.pop(key, None)
        from .domains.treatment_scouting import validate_observation_pair

        validate_observation_pair({**values, **scouting_pair_values})
    if record_type == "olive":
        values["record_year"] = values.get("record_year") or _year(values, "record_date")
    if record_type == "inventory_count":
        product = fetch_one("SELECT unit,category_name FROM products WHERE id=%s AND estate_id=%s", (values.get("product_id"), estate_id())) or {}
        if str(product.get("unit") or "").strip().casefold() == "bt." and str(product.get("category_name") or "").strip().casefold() == "vino" and values.get("average_sales_price") is None:
            values["average_sales_price"] = 12.0
        if values.get("quantity_on_hand") is not None and values.get("average_sales_price") is not None:
            values["inventory_value"] = round(float(values["quantity_on_hand"]) * float(values["average_sales_price"]), 2)
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
        if record_type == "scouting":
            cursor.execute(
                "INSERT INTO scouting_damage_scopes (observation_id,estate_id,variety_id,damage_scope,reported_zone_area_ha,representative_survey) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE variety_id=VALUES(variety_id),damage_scope=VALUES(damage_scope),"
                "reported_zone_area_ha=VALUES(reported_zone_area_ha),representative_survey=VALUES(representative_survey)",
                (record_id, estate_id(), scouting_scope_values.get("variety_id"), scouting_scope_values.get("damage_scope") or "block",
                 scouting_scope_values.get("reported_zone_area_ha"), scouting_scope_values.get("representative_survey") or 0),
            )
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
            (estate_id(), record_type, record_id, json.dumps(json_ready({**values, **scouting_scope_values, **item}), default=str)),
        )
    # A selected growth stage is structured harvest evidence. It must not
    # recalculate treatment chemistry merely because phenology changed.
    pipeline_results = route_saved_observation(record_type, record_id, values.get("issue_type"))
    if record_type == "scouting":
        try:
            from .domains.treatment_scouting import auto_link_observation, link_observation
            from .intelligence import refresh_treatment_weather_learning

            pair_source = "explicit" if scouting_pair_values.get("treatment_application_id") else "automatic"
            pairing = (link_observation({**values, **scouting_pair_values}, record_id) if pair_source == "explicit"
                       else auto_link_observation(values, record_id))
            if pairing:
                refresh_treatment_weather_learning(pairing["application_id"])
                pipeline_results.append({
                    "code": "paired_treatment_outcome",
                    "label": "Paired treatment scouting → outcome learning",
                    "status": "processed",
                    "detail": f"{str(pairing.get('phase') or '').title()}-treatment evidence linked by {pair_source} match; outcome and learning metrics recalculated.",
                })
        except Exception as error:
            pipeline_results.append({
                "code": "paired_treatment_outcome", "label": "Paired treatment scouting → outcome learning",
                "status": "retry_required", "detail": str(error)[:300],
            })
        try:
            from .intelligence import fit_disease_pressure_model

            disease_learning = fit_disease_pressure_model()
            pipeline_results.append({
                "code": "disease_pressure_learning", "label": "Disease pressure calibration",
                "status": disease_learning.get("model_status") or "learning",
                "detail": "Comparable field scouting was added to the bounded disease-pressure calibration model.",
            })
        except Exception as error:
            pipeline_results.append({
                "code": "disease_pressure_learning", "label": "Disease pressure calibration",
                "status": "retry_required", "detail": str(error)[:300],
            })
    if record_type == "treatment" and values.get("status") == "completed" and values.get("crop_scope") == "vineyard":
        try:
            from .intelligence import refresh_treatment_weather_learning

            learning = refresh_treatment_weather_learning(record_id)
            pipeline_results.append({
                "code": "treatment_weather_learning",
                "label": "Weather treatment learning",
                "status": "processed" if learning.get("updated") else "evidence_required",
                "detail": "Pre-treatment weather and the completed Agronomist program were added to the prediction model.",
            })
        except Exception as error:
            pipeline_results.append({
                "code": "treatment_weather_learning", "label": "Weather treatment learning",
                "status": "retry_required", "detail": str(error)[:300],
            })
    if pipeline_results:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO audit_events (estate_id,actor,action,entity_type,entity_id,after_data) VALUES (%s,'observation-router','route',%s,%s,%s)",
                (estate_id(), record_type, record_id, json.dumps({"pipelines": pipeline_results}, default=str)),
            )
    return {"saved": True, "record_type": record_type, "record_id": record_id, "id": record_id, "pipelines": pipeline_results}
