from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..production_impact import adjust_production_forecasts
from ..service import audit, estate_id, json_ready, new_id, season_for_year


CATEGORIES = ("bottle", "cork", "front_label", "back_label", "capsule", "case")


def _projected_bottle_equivalents(year: int) -> tuple[int, str]:
    """Return the current working vintage projection without treating it as production."""
    forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg,crates_15kg,source,notes,updated_at "
        "FROM production_forecasts WHERE estate_id=%s AND scenario='base' AND vintage_year=%s ORDER BY variety_name",
        (estate_id(), year),
    )
    adjusted = adjust_production_forecasts(forecasts, year) if forecasts else []
    grape_kg = sum(float(row.get("adjusted_grape_kg", row.get("grape_kg")) or 0) for row in adjusted)
    settings = fetch_one(
        "SELECT expected_yield_l_per_kg FROM blend_program_settings WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    yield_l_per_kg = float(settings.get("expected_yield_l_per_kg") or 0.7)
    bottles = round(grape_kg * yield_l_per_kg / 0.75) if grape_kg > 0 else 0
    return bottles, "Damage-adjusted working production forecast" if adjusted else "No production forecast available"


def _bottle_quantity_basis(year: int, historical: list[dict[str, Any]], tanks: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    historical_row = next((row for row in historical if int(row["vintage_year"]) == year), None)
    historical_bottles = int((historical_row or {}).get("bottle_equivalents_750ml") or 0)
    seen_runs: set[str] = set()
    completed_equivalents = 0.0
    for row in runs:
        run_id = str(row.get("id") or "")
        if run_id and run_id in seen_runs:
            continue
        if run_id:
            seen_runs.add(run_id)
        completed_equivalents += float(row.get("bottles_produced") or 0) * float(row.get("bottle_size_ml") or 750) / 750
    completed_equivalents = round(completed_equivalents)
    projected_bottles, projection_note = _projected_bottle_equivalents(year) if year >= date.today().year else (0, "")
    if historical_row and str(historical_row.get("completion_status") or "") == "bottled_complete":
        selected, source, projected = historical_bottles, "actual_bottled_output", False
        note = "Authoritative completed vintage total"
    elif year == date.today().year and completed_equivalents > 0 and not tanks:
        selected, source, projected = completed_equivalents, "actual_bottled_output", False
        note = "Completed bottling runs; no active vintage wine remains"
    elif year >= date.today().year and projected_bottles > 0:
        selected, source, projected = projected_bottles, "current_vintage_projection", True
        note = projection_note
    elif historical_bottles > 0:
        selected, source, projected = historical_bottles, "historical_vintage_total", False
        note = str((historical_row or {}).get("evidence_note") or "Recorded historical vintage total")
    else:
        selected = round(sum(float(row.get("volume_l") or 0) for row in tanks) / 0.75)
        source, projected, note = "recorded_cellar_volume", True, "Interim 750 ml equivalent from active cellar volume"
    return {
        "planned_bottles": int(selected),
        "bottle_quantity_source": source,
        "bottle_quantity_is_projection": projected,
        "bottle_quantity_note": note,
        "actual_bottle_equivalents": int(completed_equivalents),
        "projected_bottle_equivalents": int(projected_bottles),
    }


def _cost_rows(year: int) -> list[dict[str, Any]]:
    profiles = fetch_all(
        "SELECT b.*,p.name product_name FROM bottling_cost_profiles b LEFT JOIN products p ON p.id=b.product_id "
        "WHERE b.estate_id=%s AND b.vintage_year<=%s ORDER BY b.cost_category,b.vintage_year DESC",
        (estate_id(), year),
    )
    profile_by_category: dict[str, dict[str, Any]] = {}
    for row in profiles:
        profile_by_category.setdefault(str(row["cost_category"]), row)
    invoice_rows = fetch_all(
        "SELECT p.name product_name,fd.id source_financial_document_id,fd.document_number,fd.document_date,fp.name supplier,"
        "fdl.quantity,fdl.unit_price,fdl.taxable_amount FROM financial_document_lines fdl "
        "JOIN financial_documents fd ON fd.id=fdl.document_id JOIN products p ON p.id=fdl.product_id "
        "LEFT JOIN finance_parties fp ON fp.id=fd.party_id WHERE fd.estate_id=%s AND p.product_type='packaging' "
        "AND YEAR(fd.document_date)<=%s AND COALESCE(fdl.quantity,0)>0 AND COALESCE(fdl.unit_price,0)>0 "
        "ORDER BY p.name,fd.document_date DESC,fd.created_at DESC",
        (estate_id(), year),
    )
    invoice_by_product: dict[str, list[dict[str, Any]]] = {}
    for row in invoice_rows:
        invoice_by_product.setdefault(str(row["product_name"]), []).append(row)
    output = []
    for category in CATEGORIES:
        profile = profile_by_category.get(category) or {}
        invoice_candidates = invoice_by_product.get(str(profile.get("product_name") or ""), [])
        source_year = int(profile.get("vintage_year") or year)
        row = {
            "category": category,
            "product_id": profile.get("product_id"),
            "product_name": profile.get("product_name") or category.replace("_", " ").title(),
            "cost_per_unit_eur": profile.get("cost_per_unit_eur"),
            "units_per_bottle": profile.get("units_per_bottle") or (Decimal("0.166667") if category == "case" else Decimal("1")),
            "fixed_cost_eur": profile.get("fixed_cost_eur") or 0,
            "supplier": profile.get("supplier"),
            "source_kind": profile.get("source_kind") or "missing",
            "source_document_number": profile.get("source_document_number"),
            "source_document_date": profile.get("source_document_date"),
            "source_year": source_year,
            "inherited": source_year < year,
            "notes": profile.get("notes"),
        }
        expected_supplier = str(profile.get("supplier") or "").casefold()
        invoice = next((candidate for candidate in invoice_candidates if not expected_supplier or expected_supplier in str(candidate.get("supplier") or "").casefold() or str(candidate.get("supplier") or "").casefold() in expected_supplier), None)
        if invoice and int(str(invoice["document_date"])[:4]) >= source_year:
            row.update(
                cost_per_unit_eur=invoice["unit_price"], supplier=invoice.get("supplier"), source_kind="fattureincloud",
                source_document_number=invoice.get("document_number"), source_document_date=invoice.get("document_date"),
                source_financial_document_id=invoice.get("source_financial_document_id"),
                source_year=int(str(invoice["document_date"])[:4]), inherited=int(str(invoice["document_date"])[:4]) < year,
            )
        output.append(row)
    return output


def _winemaking_plan(year: int) -> dict[str, Any]:
    plans = fetch_all(
        "SELECT * FROM winemaking_cost_plans WHERE estate_id=%s AND vintage_year<=%s ORDER BY vintage_year DESC",
        (estate_id(), year),
    )
    plan = next((row for row in plans if int(row["vintage_year"]) == year), plans[0] if plans else {})
    source_year = int(plan.get("vintage_year") or year)
    provider = str(plan.get("provider_name") or "Sebastiano Vinci")
    documents = fetch_all(
        "SELECT fd.id,fd.document_number,fd.document_date,fd.taxable_amount,fd.gross_total,fd.source_document,fp.name supplier "
        "FROM financial_documents fd JOIN finance_parties fp ON fp.id=fd.party_id "
        "WHERE fd.estate_id=%s AND fd.document_type='purchase_invoice' AND YEAR(fd.document_date) BETWEEN %s AND %s "
        "AND (UPPER(REPLACE(fp.name,' ','')) LIKE '%%GAMBINOSONIA%%' OR UPPER(REPLACE(fp.name,' ','')) LIKE '%%SEBASTIANOVINCI%%') "
        "AND fd.status<>'void' ORDER BY fd.document_date DESC,(fd.source_document IS NOT NULL) DESC,fd.created_at DESC",
        (estate_id(), source_year, source_year + 1),
    )
    provider_key = re.sub(r"[^a-z0-9]+", "", provider.casefold())
    matching_documents = [
        document for document in documents
        if provider_key and (
            provider_key in re.sub(r"[^a-z0-9]+", "", str(document.get("supplier") or "").casefold())
            or re.sub(r"[^a-z0-9]+", "", str(document.get("supplier") or "").casefold()) in provider_key
        )
    ]
    actual_documents = []
    seen_documents: set[tuple[str, str, str, str]] = set()
    for document in matching_documents:
        evidence_key = (
            str(document.get("document_date") or "")[:10],
            str(document.get("taxable_amount") or "0"),
            str(document.get("gross_total") or "0"),
            re.sub(r"[^a-z0-9]+", "", str(document.get("supplier") or "").casefold()),
        )
        if evidence_key in seen_documents:
            continue
        seen_documents.add(evidence_key)
        actual_documents.append(document)
        if len(actual_documents) == 2:
            break
    actual = actual_documents[0] if actual_documents else None
    plan_id = plan.get("id")
    attachments = fetch_all(
        "SELECT id,original_filename,media_type,caption,created_at FROM entity_attachments WHERE estate_id=%s AND entity_type='winemaking_plan' AND entity_id=%s ORDER BY created_at DESC",
        (estate_id(), plan_id),
    ) if plan_id else []
    planned = Decimal(str(plan.get("planned_cost_eur") or 0))
    actual_cost = sum((Decimal(str(document.get("taxable_amount") or 0)) for document in actual_documents), Decimal("0"))
    return {
        "id": plan_id, "year": year, "source_year": source_year, "inherited": source_year < year,
        "provider_name": (actual or {}).get("supplier") or provider, "planned_cost_eur": planned,
        "actual_cost_eur": actual_cost if actual else None, "finance_cost_eur": actual_cost if actual else planned,
        "status": "invoiced" if actual else "planned", "document": actual, "documents": actual_documents, "notes": plan.get("notes"),
        "invoice_vintage_year": source_year if actual else None,
        "attachments": attachments,
    }


def dashboard(year: int) -> dict[str, Any]:
    season_id = season_for_year(year)
    tanks = fetch_all(
        "SELECT c.id container_id,c.code container_code,c.name container_name,c.capacity_l,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,"
        "w.variety_summary,COALESCE(w.volume_l,cp.manual_volume_l,0) volume_l "
        "FROM wine_lots w JOIN cellar_containers c ON c.id=w.current_container_id "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id WHERE w.estate_id=%s AND w.season_id=%s "
        "AND w.stage NOT IN ('bottled','closed') AND c.active=1 ORDER BY c.code",
        (estate_id(), season_id),
    )
    runs = fetch_all(
        "SELECT br.*,fw.id finished_wine_lot_id,COALESCE(SUM(fm.bottle_delta),0) bottles_on_hand,"
        "GROUP_CONCAT(DISTINCT CONCAT(bs.container_code_snapshot,' · ',bs.wine_lot_code_snapshot) ORDER BY bs.container_code_snapshot SEPARATOR ' | ') source_tanks "
        "FROM bottling_runs br LEFT JOIN finished_wine_lots fw ON fw.bottling_run_id=br.id "
        "LEFT JOIN finished_wine_inventory_movements fm ON fm.finished_wine_lot_id=fw.id "
        "LEFT JOIN bottling_run_sources bs ON bs.bottling_run_id=br.id WHERE br.estate_id=%s AND br.season_id=%s "
        "GROUP BY br.id,fw.id ORDER BY br.bottled_at DESC",
        (estate_id(), season_id),
    )
    for run in runs:
        run["parcels"] = fetch_all(
            "SELECT municipality_snapshot municipality,cadastral_sheet_snapshot cadastral_sheet,parcel_number_snapshot parcel_number,source_harvest_lots "
            "FROM bottling_run_parcels WHERE bottling_run_id=%s ORDER BY municipality_snapshot,cadastral_sheet_snapshot,parcel_number_snapshot",
            (run["id"],),
        )
    historical = fetch_all("SELECT * FROM historical_bottling_summaries WHERE estate_id=%s ORDER BY vintage_year DESC", (estate_id(),))
    costs = _cost_rows(year)
    winemaking = _winemaking_plan(year)
    quantity_basis = _bottle_quantity_basis(year, historical, tanks, runs)
    planned_bottles = quantity_basis["planned_bottles"]
    total = Decimal("0")
    for row in costs:
        quantity = Decimal(planned_bottles) * Decimal(str(row["units_per_bottle"] or 0))
        row["estimated_quantity"] = quantity
        row["estimated_cost_eur"] = quantity * Decimal(str(row["cost_per_unit_eur"] or 0)) + Decimal(str(row["fixed_cost_eur"] or 0))
        total += row["estimated_cost_eur"]
    winemaking_total = Decimal(str(winemaking.get("finance_cost_eur") or 0))
    return json_ready({"year": year, "tanks": tanks, "runs": runs, "historical": historical, "costs": costs, "winemaking": winemaking, **quantity_basis, "estimated_packaging_cost_eur": total, "estimated_winemaking_cost_eur": winemaking_total, "estimated_total_cellar_cost_eur": total + winemaking_total, "estimated_cost_per_bottle_eur": (total + winemaking_total) / planned_bottles if planned_bottles else 0})


def save_cost(year: int, category: str, payload: dict[str, Any], actor: str) -> None:
    if category not in CATEGORIES:
        raise ValueError("Unknown bottling cost category")
    season_for_year(year)
    with transaction() as (_, cursor):
        cursor.execute("SELECT id,product_id FROM bottling_cost_profiles WHERE estate_id=%s AND vintage_year=%s AND cost_category=%s", (estate_id(), year, category))
        existing = cursor.fetchone()
        record_id = existing["id"] if existing else new_id()
        product_id = payload.get("product_id") or (existing or {}).get("product_id")
        cursor.execute(
            "INSERT INTO bottling_cost_profiles (id,estate_id,vintage_year,cost_category,product_id,cost_per_unit_eur,units_per_bottle,fixed_cost_eur,supplier,source_kind,source_document_number,source_document_date,notes,updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s,%s,%s,%s) ON DUPLICATE KEY UPDATE product_id=VALUES(product_id),cost_per_unit_eur=VALUES(cost_per_unit_eur),units_per_bottle=VALUES(units_per_bottle),fixed_cost_eur=VALUES(fixed_cost_eur),supplier=VALUES(supplier),source_kind='manual',source_document_number=VALUES(source_document_number),source_document_date=VALUES(source_document_date),notes=VALUES(notes),updated_by=VALUES(updated_by)",
            (record_id, estate_id(), year, category, product_id, Decimal(str(payload.get("cost_per_unit_eur") or 0)), Decimal(str(payload.get("units_per_bottle") or 1)), Decimal(str(payload.get("fixed_cost_eur") or 0)), payload.get("supplier"), payload.get("source_document_number"), payload.get("source_document_date"), payload.get("notes"), actor),
        )
        audit(cursor, "update", "bottling_cost_profile", record_id, {"year": year, "category": category}, actor)


def save_winemaking_plan(year: int, payload: dict[str, Any], actor: str) -> str:
    season_for_year(year)
    amount = Decimal(str(payload.get("planned_cost_eur") or 0))
    if amount < 0:
        raise ValueError("Planned winemaking cost cannot be negative")
    with transaction() as (_, cursor):
        cursor.execute("SELECT id FROM winemaking_cost_plans WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year))
        existing = cursor.fetchone()
        record_id = existing["id"] if existing else new_id()
        cursor.execute(
            "INSERT INTO winemaking_cost_plans (id,estate_id,vintage_year,provider_name,planned_cost_eur,status,notes,updated_by) VALUES (%s,%s,%s,%s,%s,'planned',%s,%s) "
            "ON DUPLICATE KEY UPDATE provider_name=VALUES(provider_name),planned_cost_eur=VALUES(planned_cost_eur),notes=VALUES(notes),updated_by=VALUES(updated_by)",
            (record_id, estate_id(), year, str(payload.get("provider_name") or "Sebastiano Vinci")[:180], amount, payload.get("notes"), actor),
        )
        audit(cursor, "update", "winemaking_cost_plan", record_id, {"year": year, "planned_cost_eur": str(amount)}, actor)
    return record_id


def complete_run(year: int, payload: dict[str, Any], actor: str) -> str:
    container_ids = list(dict.fromkeys(payload.get("container_ids") or []))
    bottles = int(payload.get("bottles_produced") or 0)
    size_ml = int(payload.get("bottle_size_ml") or 750)
    if not container_ids or bottles <= 0 or size_ml <= 0:
        raise ValueError("Choose at least one source tank and enter the finished bottle count")
    season_id = season_for_year(year)
    costs = _cost_rows(year)
    with transaction() as (_, cursor):
        placeholders = ",".join(["%s"] * len(container_ids))
        cursor.execute(
            f"SELECT c.id container_id,c.code container_code,c.name container_name,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,w.variety_summary,COALESCE(w.volume_l,cp.manual_volume_l,0) volume_l FROM cellar_containers c JOIN wine_lots w ON w.current_container_id=c.id LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id WHERE c.estate_id=%s AND w.season_id=%s AND c.id IN ({placeholders}) AND w.stage NOT IN ('bottled','closed') FOR UPDATE",
            (estate_id(), season_id, *container_ids),
        )
        sources = list(cursor.fetchall())
        if len(sources) != len(container_ids):
            raise ValueError("One or more selected tanks no longer contains an active wine lot")
        source_volume = sum(Decimal(str(row.get("volume_l") or 0)) for row in sources)
        bottled_volume = Decimal(bottles * size_ml) / Decimal("1000")
        if bottled_volume > source_volume:
            raise ValueError("Bottle volume exceeds the recorded wine in the selected tanks")
        run_id, finished_id = new_id(), new_id()
        run_code = str(payload.get("run_code") or f"BOT-{year}-{datetime.now().strftime('%m%d%H%M')}")[:100]
        legal_lot = str(payload.get("legal_lot_code") or "").strip()
        if not legal_lot:
            raise ValueError("Legal bottling lot code is required")
        bottled_at = payload.get("bottled_at") or date.today().isoformat()
        cases = math.floor(bottles / int(payload.get("bottles_per_case") or 6))
        cursor.execute(
            "INSERT INTO bottling_runs (id,estate_id,season_id,run_code,bottled_at,wine_name,legal_lot_code,denomination,origin_country,alcohol_pct,bottle_size_ml,bottles_produced,bottled_volume_l,source_volume_l,process_loss_l,bottles_per_case,cases_produced,legal_review_status,recorded_by,notes,completed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6))",
            (run_id, estate_id(), season_id, run_code, bottled_at, payload.get("wine_name") or "Baiamonte wine", legal_lot, payload.get("denomination"), payload.get("origin_country") or "Italia", payload.get("alcohol_pct") or None, size_ml, bottles, bottled_volume, source_volume, source_volume - bottled_volume, payload.get("bottles_per_case") or 6, cases, payload.get("legal_review_status") or "review_required", actor, payload.get("notes")),
        )
        wine_ids = []
        for row in sources:
            wine_ids.append(row["wine_lot_id"])
            cursor.execute("INSERT INTO bottling_run_sources (id,estate_id,bottling_run_id,wine_lot_id,container_id,drained_volume_l,wine_lot_code_snapshot,wine_lot_name_snapshot,variety_snapshot,container_code_snapshot,container_name_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (new_id(), estate_id(), run_id, row["wine_lot_id"], row["container_id"], row["volume_l"], row["wine_lot_code"], row["wine_lot_name"], row.get("variety_summary"), row["container_code"], row["container_name"]))
            cursor.execute("INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,container_id,operation_at,operation_type,amount,unit,notes) VALUES (%s,%s,%s,%s,%s,%s,'bottling',%s,'L',%s)", (new_id(), estate_id(), season_id, row["wine_lot_id"], row["container_id"], bottled_at, row["volume_l"], f"Closed into bottling run {run_code}; legal lot {legal_lot}."))
            cursor.execute("UPDATE wine_lots SET stage='bottled',volume_l=0,current_container_id=NULL WHERE id=%s", (row["wine_lot_id"],))
            cursor.execute("UPDATE cellar_containers SET status='empty' WHERE id=%s", (row["container_id"],))
            cursor.execute("UPDATE cellar_control_profiles SET manual_contents=NULL,manual_volume_l=0,manual_stage='empty',manual_updated_at=NOW(6),updated_by=%s WHERE container_id=%s", (actor, row["container_id"]))
        wine_placeholders = ",".join(["%s"] * len(wine_ids))
        cursor.execute(
            f"SELECT cp.id parcel_id,cp.municipality,cp.cadastral_sheet,cp.parcel_number,COUNT(DISTINCT tr.harvest_lot_id) source_lots FROM cellar_lot_trace_records tr JOIN harvest_lot_parcels hp ON hp.harvest_lot_id=tr.harvest_lot_id JOIN cadastral_parcels cp ON cp.id=hp.parcel_id WHERE tr.estate_id=%s AND tr.wine_lot_id IN ({wine_placeholders}) GROUP BY cp.id,cp.municipality,cp.cadastral_sheet,cp.parcel_number",
            (estate_id(), *wine_ids),
        )
        parcels = list(cursor.fetchall())
        for parcel in parcels:
            cursor.execute("INSERT INTO bottling_run_parcels (id,estate_id,bottling_run_id,parcel_id,municipality_snapshot,cadastral_sheet_snapshot,parcel_number_snapshot,source_harvest_lots) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (new_id(), estate_id(), run_id, parcel["parcel_id"], parcel["municipality"], parcel["cadastral_sheet"], parcel["parcel_number"], parcel["source_lots"]))
        legal = {"denomination": payload.get("denomination"), "origin_country": payload.get("origin_country") or "Italia", "alcohol_pct": payload.get("alcohol_pct"), "source_parcels": parcels}
        cursor.execute("INSERT INTO finished_wine_lots (id,estate_id,season_id,bottling_run_id,legal_lot_code,wine_name,bottle_size_ml,initial_bottles,legal_data_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (finished_id, estate_id(), season_id, run_id, legal_lot, payload.get("wine_name") or "Baiamonte wine", size_ml, bottles, json.dumps(legal, default=str)))
        cursor.execute("INSERT INTO finished_wine_inventory_movements (id,estate_id,finished_wine_lot_id,movement_at,movement_type,bottle_delta,reference_type,reference_id,notes) VALUES (%s,%s,%s,%s,'bottled',%s,'bottling_run',%s,%s)", (new_id(), estate_id(), finished_id, bottled_at, bottles, run_id, "Finished wine posted from cleared source tanks."))
        for cost in costs:
            quantity = Decimal(bottles) * Decimal(str(cost.get("units_per_bottle") or 0))
            total = quantity * Decimal(str(cost.get("cost_per_unit_eur") or 0)) + Decimal(str(cost.get("fixed_cost_eur") or 0))
            cursor.execute("INSERT INTO bottling_packaging_usage (id,estate_id,bottling_run_id,cost_category,product_id,quantity_used,unit_cost_eur,total_cost_eur,cost_source_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (new_id(), estate_id(), run_id, cost["category"], cost.get("product_id"), quantity, cost.get("cost_per_unit_eur"), total, f"{cost.get('source_kind')} {cost.get('source_document_number') or ''}".strip()))
            if cost.get("product_id") and quantity:
                cursor.execute("INSERT INTO inventory_movements (id,estate_id,product_id,movement_date,movement_type,quantity_delta,unit_cost_eur,reference_type,reference_id,notes) VALUES (%s,%s,%s,%s,'use',%s,%s,'bottling_run',%s,%s)", (new_id(), estate_id(), cost["product_id"], bottled_at, -quantity, cost.get("cost_per_unit_eur") or 0, run_id, "Packaging used in bottling; negative stock is retained until a delayed supplier invoice or receipt posts."))
        audit(cursor, "complete", "bottling_run", run_id, {"year": year, "bottles": bottles, "source_tanks": container_ids, "legal_parcels": len(parcels)}, actor)
    return run_id
