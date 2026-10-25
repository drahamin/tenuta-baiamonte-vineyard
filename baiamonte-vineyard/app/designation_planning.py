"""Vintage designation simulation with explicit legal-review guardrails."""

from __future__ import annotations

import json
from typing import Any

from .db import fetch_all, fetch_one, transaction
from .production_capability import production_capability
from .service import audit, estate_id, json_ready, new_id, season_for_year
from .varietal_yield import variety_key
from .wine_conversion import DEFAULT_RED_WINE_YIELD_L_PER_KG


OFFICIAL_ETNA_SOURCE = "https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/17936"
OFFICIAL_SICILIA_SOURCE = "https://www.masaf.gov.it/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/23111"

DESIGNATIONS = {
    "terre_siciliane_igt": {
        "label": "Terre Siciliane IGT",
        "purpose": "Flexible final-wine plan, including Nerello Mascalese + Grenache blends",
    },
    "etna_doc_rosso": {
        "label": "Etna DOC Rosso",
        "purpose": "Nerello Mascalese-led wine; every grape source and legal requirement still needs verification",
    },
    "sicilia_doc_grecanico_superiore": {
        "label": "Sicilia DOC Grecanico Superiore",
        "purpose": "Separate Grecanico designation scenario",
    },
    "sicilia_doc_grecanico": {
        "label": "Sicilia DOC Grecanico",
        "purpose": "Ordinary Grecanico designation; use this to back off the Superiore plan",
    },
    "vino": {"label": "Vino", "purpose": "No DOC/IGT designation selected"},
}

SEBASTIAN_2026_RECONCILIATION = {
    "source_label": "Sebastian handwritten cellar reconciliation · 24 Oct 2026",
    "status": "review_required",
    "working_actuals": [
        {"lot": "Alicante 1", "volume_l": 250, "note": "pulito / cleaned"},
        {"lot": "Alicante 2", "volume_l": 385, "note": "handwriting says in pulito / not cleaned; confirm wording"},
        {"lot": "Nerello 1", "volume_l": 1640, "note": "pulito / cleaned"},
        {"lot": "Nerello 2", "volume_l": 300, "note": "pulito / cleaned"},
    ],
    "source_calculations": [
        {"wine": "Alicante", "calculation": "250 L + 385 L = 635 L; about 846 full 750 ml bottles", "confidence": "high"},
        {"wine": "Nerello 1", "calculation": "1,640 L; about 2,186 full 750 ml bottles", "confidence": "high"},
        {"wine": "Nerello 2", "calculation": "300 L noted separately; note says it may be used to fill Alicante 1 + Alicante 2", "confidence": "medium"},
        {"wine": "Grecanico", "calculation": "1,550 L appears on the sheet, but the handwritten bottle figure is inconsistent or unclear", "confidence": "needs_confirmation"},
    ],
    "reporting_rule": "Use measured cleaned liquid as actual. Keep kg-to-liter and bottle arithmetic as calculated evidence until the cellar volumes and intended blend are confirmed.",
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _component_kind(name: str) -> str:
    value = variety_key(name)
    if "nerello" in value and ("cappuccio" in value or "mantellato" in value):
        return "nerello_cappuccio"
    if "nerello" in value:
        return "nerello_mascalese"
    if "grenache" in value or "alicante" in value:
        return "grenache"
    if "grecanico" in value:
        return "grecanico"
    return "other"


def _legal_scenarios_for_designation(code: str, scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def normalized(value: Any) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    matches = []
    for scenario in scenarios:
        denomination = normalized(scenario.get("denomination"))
        selected = (
            (code == "terre_siciliane_igt" and denomination == "terre siciliane igt")
            or (code == "etna_doc_rosso" and denomination == "etna doc rosso")
            or (code == "sicilia_doc_grecanico_superiore" and denomination == "sicilia doc grecanico superiore")
            or (code == "sicilia_doc_grecanico" and denomination == "sicilia doc")
        )
        if selected:
            matches.append(scenario)
    return matches


def _cellar_lots_for_year(year: int) -> list[dict[str, Any]]:
    season_id = season_for_year(year)
    return fetch_all(
        "SELECT w.id,w.code,w.name,w.variety_summary,w.volume_l,w.initial_l,w.loss_l,w.stage,c.code container_code "
        "FROM wine_lots w LEFT JOIN cellar_containers c ON c.id=w.current_container_id "
        "WHERE w.estate_id=%s AND w.season_id=%s AND w.stage<>'closed' ORDER BY w.code",
        (estate_id(), season_id),
    )


def simulate_designation(year: int, payload: dict[str, Any], capability: dict[str, Any] | None = None) -> dict[str, Any]:
    code = str(payload.get("designation_code") or "").strip()
    if code not in DESIGNATIONS:
        raise ValueError("Choose a supported wine designation")
    supplied = payload.get("components") or []
    if not isinstance(supplied, list) or not supplied:
        raise ValueError("Add at least one grape component")
    capability = capability or production_capability(year)
    streams = capability.get("streams") or []
    cellar_lots = capability.get("cellar_lots") if "cellar_lots" in capability else _cellar_lots_for_year(year)
    legal_scenarios = _legal_scenarios_for_designation(code, capability.get("legal_scenarios") or [])
    ratios = {variety_key(row.get("variety_name")): _number(row.get("predictive_l_per_kg")) for row in streams}
    availability = {
        (variety_key(row.get("variety_name")), source): _number(row.get(field))
        for row in streams
        for source, field in (("estate", "estate_fruit_kg"), ("purchased", "purchased_fruit_kg"))
    }
    components = []
    errors: list[str] = []
    warnings: list[str] = []
    for raw in supplied:
        if not isinstance(raw, dict):
            raise ValueError("Each component must identify a grape and quantity")
        name = str(raw.get("variety_name") or "").strip()[:120]
        source = str(raw.get("source_type") or "estate").strip().casefold()
        allocation = str(raw.get("allocation") or "final_wine").strip().casefold()
        kg = _number(raw.get("kg"))
        if not name or kg <= 0:
            continue
        if source not in {"estate", "purchased", "planned_purchase"}:
            raise ValueError("Choose estate, purchased, or planned purchase for every component")
        if allocation not in {"final_wine", "grenache_single"}:
            raise ValueError("Choose final wine or separate Grenache wine for every allocation")
        key, kind = variety_key(name), _component_kind(name)
        ratio = ratios.get(key) or DEFAULT_RED_WINE_YIELD_L_PER_KG
        available = availability.get((key, "purchased" if source == "planned_purchase" else source), 0)
        if source == "planned_purchase":
            warnings.append(f"{name}: {kg:g} kg is a planned purchase and is not yet a received lot.")
        if source in {"purchased", "planned_purchase"} and not bool(raw.get("eligibility_documented")):
            warnings.append(f"{name}: purchased-grape DOC eligibility and traceability are not yet documented.")
        components.append({
            "variety_name": name, "kind": kind, "source_type": source, "allocation": allocation, "kg": round(kg, 3),
            "eligibility_documented": bool(raw.get("eligibility_documented")),
            "available_received_kg": round(available, 3), "predictive_l_per_kg": round(ratio, 4),
            "predicted_wine_l": round(kg * ratio, 3),
        })
    if not components:
        raise ValueError("Add a positive grape quantity")
    used: dict[tuple[str, str], float] = {}
    for row in components:
        if row["source_type"] != "planned_purchase":
            key = (variety_key(row["variety_name"]), row["source_type"])
            used[key] = used.get(key, 0) + row["kg"]
    for key, kg in used.items():
        available = availability.get(key, 0)
        if kg > available + 0.001:
            errors.append(f"{key[0].title()} ({key[1]}): {kg:g} kg allocated exceeds the {available:g} kg received from this source.")
    final_components = [row for row in components if row["allocation"] == "final_wine"]
    secondary_components = [row for row in components if row["allocation"] == "grenache_single"]
    if not final_components:
        errors.append("Allocate grapes to the final wine before locking the plan.")
    total_kg = sum(row["kg"] for row in final_components)
    total_l = sum(row["predicted_wine_l"] for row in final_components)
    secondary_kg = sum(row["kg"] for row in secondary_components)
    secondary_l = sum(row["predicted_wine_l"] for row in secondary_components)
    allocation_totals = {
        "final_wine": total_kg,
        "grenache_single": secondary_kg,
    }
    for row in components:
        allocation_total = allocation_totals[row["allocation"]]
        row["share_pct"] = round(row["kg"] / allocation_total * 100, 2) if allocation_total else 0
    blend_parameters = payload.get("blend_parameters") if isinstance(payload.get("blend_parameters"), dict) else {}
    if blend_parameters:
        target_grenache_pct = _number(blend_parameters.get("grenache_pct"))
        target_estate_pct = _number(blend_parameters.get("estate_grenache_pct"))
        final_grenache = sum(row["predicted_wine_l"] for row in final_components if row["kind"] == "grenache")
        estate_grenache = sum(row["predicted_wine_l"] for row in final_components if row["kind"] == "grenache" and row["source_type"] == "estate")
        actual_grenache_pct = final_grenache / total_l * 100 if total_l else 0
        actual_estate_pct = estate_grenache / final_grenache * 100 if final_grenache else 0
        if not 5 <= target_grenache_pct <= 20:
            errors.append("Choose a Grenache share between 5% and 20% for the Nerello blend.")
        if not 0 <= target_estate_pct <= 100:
            errors.append("Choose an estate Grenache source share from 0% to 100%.")
        if abs(actual_grenache_pct - target_grenache_pct) > 0.05:
            errors.append("The predicted liquid Grenache allocation does not match the selected blend percentage.")
        if final_grenache and abs(actual_estate_pct - target_estate_pct) > 0.05:
            errors.append("The estate/purchased Grenache allocation does not match the selected source split.")
        blend_parameters = {
            "grenache_pct": round(target_grenache_pct, 2),
            "estate_grenache_pct": round(target_estate_pct, 2),
            "purchased_grenache_pct": round(100 - target_estate_pct, 2),
            "actual_grenache_pct": round(actual_grenache_pct, 2),
            "actual_estate_grenache_pct": round(actual_estate_pct, 2),
        }
    source_selection = payload.get("source_lot_ids") if isinstance(payload.get("source_lot_ids"), dict) else {}
    requested_lots = {
        "nerello": [str(value) for value in source_selection.get("nerello", []) if str(value).strip()],
        "grenache": [str(value) for value in source_selection.get("grenache", []) if str(value).strip()],
    }
    lot_by_id = {str(row.get("id")): row for row in cellar_lots or []}
    selected_source_lots = []
    seen_lot_ids: set[str] = set()
    for role, identifiers in requested_lots.items():
        for lot_id in identifiers:
            lot = lot_by_id.get(lot_id)
            if not lot:
                errors.append(f"Selected {role} source lot is not available in this vintage.")
                continue
            if lot_id in seen_lot_ids:
                errors.append(f"Cellar lot {lot.get('code') or lot_id} cannot be assigned to both blend roles.")
                continue
            seen_lot_ids.add(lot_id)
            actual_kind = _component_kind(str(lot.get("variety_summary") or lot.get("name") or ""))
            expected = "nerello_mascalese" if role == "nerello" else "grenache"
            if actual_kind != expected:
                errors.append(f"Cellar lot {lot.get('code') or lot_id} does not match the selected {role} role.")
                continue
            available_l = _number(lot.get("volume_l")) or _number(lot.get("initial_l"))
            if available_l <= 0:
                errors.append(f"Cellar lot {lot.get('code') or lot_id} needs a measured liquid volume before it can drive the blend.")
                continue
            selected_source_lots.append({
                "wine_lot_id": lot_id, "role": role, "code": lot.get("code"), "name": lot.get("name"),
                "variety_summary": lot.get("variety_summary"), "available_l": round(available_l, 3),
                "recorded_loss_l": round(_number(lot.get("loss_l")), 3), "container_code": lot.get("container_code"),
            })
    nerello_lots_l = sum(row["available_l"] for row in selected_source_lots if row["role"] == "nerello")
    grenache_lots_l = sum(row["available_l"] for row in selected_source_lots if row["role"] == "grenache")
    output_basis = "predicted_from_grapes"
    if nerello_lots_l and grenache_lots_l and blend_parameters:
        target_pct = _number(blend_parameters.get("grenache_pct"))
        required_grenache_l = nerello_lots_l * target_pct / (100 - target_pct) if 0 < target_pct < 100 else 0
        used_grenache_l = min(required_grenache_l, grenache_lots_l)
        if required_grenache_l > grenache_lots_l + 0.001:
            errors.append(f"Selected Alicante / Grenache lots are {required_grenache_l - grenache_lots_l:.3f} L short of the chosen blend percentage.")
        for row in selected_source_lots:
            row["allocated_to_final_wine_l"] = round(
                row["available_l"] if row["role"] == "nerello" else row["available_l"] * used_grenache_l / grenache_lots_l,
                3,
            )
            row["remaining_separate_wine_l"] = round(max(row["available_l"] - row["allocated_to_final_wine_l"], 0), 3)
        total_l = nerello_lots_l + used_grenache_l
        secondary_l = max(grenache_lots_l - used_grenache_l, 0)
        output_basis = "measured_source_lots"
        blend_parameters["actual_grenache_pct"] = round(used_grenache_l / total_l * 100, 2) if total_l else 0
        # Once both measured cellar sides are selected, their exact liquid allocation
        # supersedes the earlier grape-yield estimate used by the planning form.
        errors = [
            error for error in errors
            if error != "The predicted liquid Grenache allocation does not match the selected blend percentage."
        ]
    elif selected_source_lots:
        warnings.append("Both measured Nerello and Alicante / Grenache source lots are required before lot volumes can replace the grape-based prediction.")
    loss_parameters = payload.get("loss_parameters") if isinstance(payload.get("loss_parameters"), dict) else {}
    tails_pct = _number(loss_parameters.get("tails_pct"))
    racking_pct = _number(loss_parameters.get("racking_pct"))
    if not 0 <= tails_pct <= 30:
        errors.append("Choose a tails / excluded fraction loss from 0% to 30%.")
    if not 0 <= racking_pct <= 30:
        errors.append("Choose a racking loss from 0% to 30%.")
    tails_pct, racking_pct = max(0, min(tails_pct, 30)), max(0, min(racking_pct, 30))

    def loss_waterfall(gross_l: float) -> dict[str, float | int]:
        tails_l = gross_l * tails_pct / 100
        after_tails_l = max(gross_l - tails_l, 0)
        racking_l = after_tails_l * racking_pct / 100
        finished_l = max(after_tails_l - racking_l, 0)
        return {
            "gross_wine_l": round(gross_l, 3), "tails_loss_pct": round(tails_pct, 2),
            "tails_loss_l": round(tails_l, 3), "after_tails_l": round(after_tails_l, 3),
            "racking_loss_pct": round(racking_pct, 2), "racking_loss_l": round(racking_l, 3),
            "finished_wine_l": round(finished_l, 3), "finished_bottles_750ml": int(finished_l / 0.75),
        }

    primary_waterfall = loss_waterfall(total_l)
    secondary_waterfall = loss_waterfall(secondary_l)
    if code == "etna_doc_rosso":
        nerello = sum(row["kg"] for row in final_components if row["kind"] == "nerello_mascalese")
        cappuccio = sum(row["kg"] for row in final_components if row["kind"] == "nerello_cappuccio")
        grenache = sum(row["kg"] for row in final_components if row["kind"] == "grenache")
        if not total_kg or nerello / total_kg < 0.80:
            errors.append("Etna DOC Rosso requires at least 80% Nerello Mascalese.")
        if total_kg and cappuccio / total_kg > 0.20:
            errors.append("Nerello Cappuccio / Mantellato cannot exceed 20% in this Etna DOC Rosso simulation.")
        if grenache:
            errors.append("Alicante is the recognized Grenache synonym, but Alicante N. is not listed as an admitted Etna DOC Rosso component in the current official production specification. Keep this as a what-if or choose a compatible IGT/Vino plan unless written authority confirms eligibility.")
        other = sum(row["kg"] for row in final_components if row["kind"] not in {"nerello_mascalese", "nerello_cappuccio", "grenache"})
        if other:
            errors.append("This simulator cannot qualify the other component for Etna DOC Rosso; record its exact authorized variety and obtain legal review.")
        warnings.append("Composition is only one test. Vineyard/source zone, registered area, yields, records, analysis and certification remain subject to documentary verification.")
    elif code == "sicilia_doc_grecanico_superiore":
        if any(row["kind"] != "grecanico" for row in final_components):
            errors.append("The Grecanico Superiore scenario cannot contain the selected non-Grecanico component in this planner.")
        warnings.append("Superiore remains a planning choice until its designation requirements and supporting records are verified.")
    elif code == "sicilia_doc_grecanico":
        if any(row["kind"] != "grecanico" for row in final_components):
            errors.append("The Sicilia DOC Grecanico plan cannot contain the selected non-Grecanico component in this planner.")
        warnings.append("Backing off Grecanico Superiore does not require a laboratory report in this system. The lower designation decision is retained in the audit trail; ordinary DOC eligibility still requires its normal documentary review.")
    elif code == "terre_siciliane_igt":
        warnings.append("IGT variety, origin, yield, record and labeling requirements still need legal review before use.")
    else:
        warnings.append("This plan records production intent without claiming a DOC or IGT entitlement.")
    secondary_products = []
    if secondary_components:
        if any(row["kind"] != "grenache" for row in secondary_components):
            errors.append("Only Grenache / Alicante can be allocated to the separate Grenache wine in this simulator.")
        secondary_code = str(payload.get("secondary_designation_code") or "vino").strip()
        if secondary_code not in {"terre_siciliane_igt", "vino"}:
            errors.append("Choose Terre Siciliane IGT or Vino for the separate Grenache wine plan.")
            secondary_code = "vino"
        secondary_products.append({
            "allocation": "grenache_single",
            "wine_name": str(payload.get("secondary_wine_name") or f"Grenache {year} single wine").strip()[:190],
            "designation_code": secondary_code,
            "designation_label": DESIGNATIONS[secondary_code]["label"],
            "components": secondary_components,
            "grapes_kg": round(secondary_kg, 3),
            "predicted_gross_wine_l": secondary_waterfall["gross_wine_l"],
            "predicted_wine_l": secondary_waterfall["finished_wine_l"],
            "predicted_bottles_750ml": secondary_waterfall["finished_bottles_750ml"],
            "loss_waterfall": secondary_waterfall,
            "legal_review_status": "review_required",
        })
        warnings.append("Remaining Grenache is reserved as a separate wine; its selected IGT/Vino designation remains review-required and is not part of the Nerello blend percentage.")
    return json_ready({
        "year": year, "wine_name": str(payload.get("wine_name") or DESIGNATIONS[code]["label"]).strip()[:190],
        "designation_code": code, "designation_label": DESIGNATIONS[code]["label"],
        "components": components, "total_grapes_kg": round(total_kg, 3),
        "predicted_gross_wine_l": primary_waterfall["gross_wine_l"],
        "predicted_wine_l": primary_waterfall["finished_wine_l"],
        "predicted_finished_wine_l": primary_waterfall["finished_wine_l"],
        "predicted_bottles_750ml": primary_waterfall["finished_bottles_750ml"],
        "loss_parameters": {"tails_pct": round(tails_pct, 2), "racking_pct": round(racking_pct, 2)},
        "loss_waterfall": primary_waterfall, "output_basis": output_basis,
        "source_lots": selected_source_lots,
        "blend_parameters": blend_parameters, "secondary_products": secondary_products,
        "legal_production_scenarios": legal_scenarios,
        "all_allocated_grapes_kg": round(total_kg + secondary_kg, 3),
        "all_predicted_wine_l": round(primary_waterfall["finished_wine_l"] + secondary_waterfall["finished_wine_l"], 3),
        "composition_pass": not errors, "can_lock": not errors, "errors": errors, "warnings": list(dict.fromkeys(warnings)),
        "legal_review_status": "review_required", "legal_entitlement_confirmed": False,
        "official_source": OFFICIAL_ETNA_SOURCE if code == "etna_doc_rosso" else OFFICIAL_SICILIA_SOURCE if code.startswith("sicilia_doc_") else None,
        "decision_note": "Locking records the estate's production decision; it does not confer or verify a legal designation.",
    })


def designation_planning_dashboard(year: int) -> dict[str, Any]:
    season_id = season_for_year(year)
    capability = production_capability(year)
    rows = fetch_all(
        "SELECT * FROM vintage_designation_plans WHERE estate_id=%s AND season_id=%s AND decision_status<>'retired' ORDER BY locked_at DESC,created_at DESC",
        (estate_id(), season_id),
    )
    for row in rows:
        for key in ("components_json", "simulation_json"):
            try:
                raw = row.get(key) or ("[]" if key == "components_json" else "{}")
                row[key.removesuffix("_json")] = json.loads(raw)
            except (TypeError, ValueError):
                row[key.removesuffix("_json")] = [] if key == "components_json" else {}
    return json_ready({
        "year": year, "catalog": [{"code": code, **item} for code, item in DESIGNATIONS.items()],
        "streams": capability.get("streams") or [], "legal_scenarios": capability.get("legal_scenarios") or [],
        "cellar_lots": _cellar_lots_for_year(year),
        "plans": rows, "official_etna_source": OFFICIAL_ETNA_SOURCE, "official_sicilia_source": OFFICIAL_SICILIA_SOURCE,
        "reconciliation_draft": SEBASTIAN_2026_RECONCILIATION if year == 2026 else None,
        "guardrail": "A locked plan is an internal production decision. DOC/IGT use remains review-required until source, eligibility, yield, traceability and certification evidence is verified.",
    })


def save_designation_plan(year: int, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    simulation = simulate_designation(year, payload)
    status = str(payload.get("decision_status") or "draft").strip().casefold()
    if status not in {"draft", "locked"}:
        raise ValueError("Choose draft or locked decision status")
    if status == "locked" and not simulation["can_lock"]:
        raise ValueError("Resolve the simulator errors before locking this designation plan")
    season_id, record_id = season_for_year(year), new_id()
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip() or None
    if wine_lot_id and not fetch_one("SELECT id FROM wine_lots WHERE id=%s AND estate_id=%s AND season_id=%s", (wine_lot_id, estate_id(), season_id)):
        raise ValueError("Choose a wine batch from this vintage")
    plan_code = str(payload.get("plan_code") or f"DES-{year}-{record_id[:8]}").strip()[:80]
    with transaction() as (_, cursor):
        if status == "locked":
            if wine_lot_id:
                cursor.execute(
                    "UPDATE vintage_designation_plans SET decision_status='retired' WHERE estate_id=%s AND season_id=%s AND wine_lot_id=%s AND decision_status='locked'",
                    (estate_id(), season_id, wine_lot_id),
                )
            else:
                cursor.execute(
                    "UPDATE vintage_designation_plans SET decision_status='retired' WHERE estate_id=%s AND season_id=%s AND wine_lot_id IS NULL AND wine_name=%s AND decision_status='locked'",
                    (estate_id(), season_id, simulation["wine_name"]),
                )
        cursor.execute(
            "INSERT INTO vintage_designation_plans (id,estate_id,season_id,wine_lot_id,plan_code,wine_name,designation_code,designation_label,decision_status,legal_review_status,components_json,simulation_json,projected_grapes_kg,projected_wine_l,projected_bottles_750ml,notes,locked_by,locked_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'review_required',%s,%s,%s,%s,%s,%s,%s,IF(%s='locked',NOW(6),NULL))",
            (record_id, estate_id(), season_id, wine_lot_id, plan_code, simulation["wine_name"], simulation["designation_code"], simulation["designation_label"], status,
             json.dumps(simulation["components"], ensure_ascii=False), json.dumps(simulation, ensure_ascii=False, default=str), simulation["total_grapes_kg"], simulation["predicted_wine_l"], simulation["predicted_bottles_750ml"],
             str(payload.get("notes") or "").strip() or None, actor if status == "locked" else None, status),
        )
        for source in simulation.get("source_lots") or []:
            cursor.execute(
                "INSERT INTO vintage_designation_plan_source_lots (id,estate_id,plan_id,wine_lot_id,component_role,available_volume_l_snapshot,allocated_volume_l_snapshot,remaining_volume_l_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (new_id(), estate_id(), record_id, source["wine_lot_id"], source["role"], source["available_l"],
                 source.get("allocated_to_final_wine_l", 0), source.get("remaining_separate_wine_l", 0)),
            )
        if wine_lot_id:
            components_text = "; ".join(f"{row['variety_name']} {row['kg']:g} kg ({row['source_type']})" for row in simulation["components"] if row.get("allocation") == "final_wine")
            cursor.execute(
                "UPDATE wine_lots SET designation_intent=%s,designation_label=%s,designation_decision_status=%s,blend_components_text=%s WHERE id=%s AND estate_id=%s",
                (simulation["designation_code"], simulation["designation_label"], "locked_review_required" if status == "locked" else "draft", components_text, wine_lot_id, estate_id()),
            )
        audit(cursor, "lock" if status == "locked" else "create", "vintage_designation_plan", record_id, {"simulation": simulation, "wine_lot_id": wine_lot_id}, actor)
    return {"saved": True, "id": record_id, "decision_status": status, "legal_review_status": "review_required", "simulation": simulation}
