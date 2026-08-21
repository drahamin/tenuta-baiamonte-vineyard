from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request

from ..access import authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..prediction_refresh import request_harvest_refresh
from .people_roles import require_discipline_approval
from ..production_impact import adjust_production_forecasts, refresh_scouting_damage_proposal
from ..service import audit, estate_id, json_ready, new_id


router = APIRouter(prefix="/api/v1/agronomy/damage-assessments", tags=["agronomy"])


def _assessment_loss_pct(row: dict[str, Any]) -> float | None:
    if row.get("estate_yield_loss_pct") is not None:
        return round(float(row["estate_yield_loss_pct"]), 2)
    if row.get("affected_area_pct") is not None and row.get("estimated_yield_loss_pct") is not None:
        return round(float(row["affected_area_pct"]) * float(row["estimated_yield_loss_pct"]) / 100.0, 2)
    return None


def damage_assessment_dashboard(year: int) -> dict[str, Any]:
    baseline_forecasts = fetch_all(
        "SELECT vintage_year,variety_name,grape_kg,crates_15kg,source,notes,updated_at "
        "FROM production_forecasts WHERE estate_id=%s AND vintage_year=%s AND scenario='base' ORDER BY variety_name",
        (estate_id(), year),
    )
    adjusted_forecasts = adjust_production_forecasts(baseline_forecasts, year)
    forecast_by_variety = {
        str(row.get("variety_name") or "").casefold(): row for row in adjusted_forecasts
    }
    baseline_total = round(sum(float(row.get("baseline_grape_kg") or row.get("grape_kg") or 0) for row in adjusted_forecasts), 2)
    adjusted_total = round(sum(float(row.get("adjusted_grape_kg") or row.get("grape_kg") or 0) for row in adjusted_forecasts), 2)
    rows = fetch_all(
        "SELECT a.*,s.vintage_year FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id "
        "WHERE a.estate_id=%s AND s.vintage_year=%s AND a.active=1 ORDER BY a.event_date,a.assessed_at",
        (estate_id(), year),
    )
    for row in rows:
        try:
            evidence = json.loads(row.pop("evidence_json", None) or "[]")
        except (TypeError, ValueError):
            evidence = []
        row["evidence"] = evidence if isinstance(evidence, list) else []
        try:
            calculation = json.loads(row.pop("calculation_json", None) or "{}")
        except (TypeError, ValueError):
            calculation = {}
        row["calculation"] = calculation if isinstance(calculation, dict) else {}
    attachments = fetch_all(
        "SELECT id,entity_id,original_filename,caption FROM entity_attachments "
        "WHERE estate_id=%s AND entity_type='damage_assessment' ORDER BY created_at",
        (estate_id(),),
    )
    attachments_by_assessment: dict[str, list[dict[str, Any]]] = {}
    for attachment in attachments:
        attachments_by_assessment.setdefault(str(attachment["entity_id"]), []).append({
            "url": f"api/v1/attachments/{attachment['id']}/file",
            "filename": attachment.get("original_filename"),
            "caption": attachment.get("caption"),
        })
    for row in rows:
        row["evidence"] = attachments_by_assessment.get(str(row["id"]), row["evidence"])
        row["damage_occurrence_confirmed"] = bool(
            row.get("review_status") == "approved"
            and (row["evidence"] or row.get("source_type") == "photo_field_report")
        )
        row["scope_coverage_pct"] = 100.0 if row.get("scope_type") == "estate" else row.get("affected_area_pct")
        row["yield_loss_quantified"] = row.get("estate_yield_loss_pct") is not None or (
            row.get("affected_area_pct") is not None and row.get("estimated_yield_loss_pct") is not None
        )
    proposal_rows = fetch_all(
        "SELECT so.id,so.damage_event_key,so.observed_at,so.issue_type,so.severity,so.damage_type,so.affected_area_pct,"
        "COALESCE(sds.damage_scope,'block') damage_scope,sds.reported_zone_area_ha,sds.representative_survey,so.estimated_yield_loss_pct,so.yield_impact_confidence,so.yield_impact_source,so.damage_proposal_status,"
        "sds.ai_zone_damage_pct,sds.ai_zone_damage_low_pct,sds.ai_zone_damage_high_pct,sds.ai_zone_yield_reduction_pct,sds.ai_zone_yield_reduction_low_pct,sds.ai_zone_yield_reduction_high_pct,sds.ai_zone_analysis_json,"
        "so.proposed_estate_loss_pct,so.damage_proposal_json,so.notes,vb.code block_code,vb.name block_name,gv.name selected_variety_name "
        "FROM scouting_observations so JOIN seasons s ON s.id=so.season_id LEFT JOIN scouting_damage_scopes sds ON sds.observation_id=so.id "
        "LEFT JOIN vineyard_blocks vb ON vb.id=so.block_id LEFT JOIN grape_varieties gv ON gv.id=sds.variety_id "
        "WHERE so.estate_id=%s AND s.vintage_year=%s AND so.damage_type IS NOT NULL "
        "ORDER BY so.observed_at DESC LIMIT 80",
        (estate_id(), year),
    )
    scouting_attachments = fetch_all(
        "SELECT entity_id,id,original_filename,caption FROM entity_attachments WHERE estate_id=%s AND entity_type='scouting' ORDER BY created_at",
        (estate_id(),),
    )
    scouting_evidence: dict[str, list[dict[str, Any]]] = {}
    for attachment in scouting_attachments:
        scouting_evidence.setdefault(str(attachment["entity_id"]), []).append({
            "url": f"api/v1/attachments/{attachment['id']}/file",
            "filename": attachment.get("original_filename"),
            "caption": attachment.get("caption"),
        })
    for proposal_row in proposal_rows:
        try:
            proposal = json.loads(proposal_row.pop("damage_proposal_json", None) or "{}")
        except (TypeError, ValueError):
            proposal = {}
        proposal_row["proposal"] = proposal if isinstance(proposal, dict) else {}
        try:
            zone_analysis = json.loads(proposal_row.pop("ai_zone_analysis_json", None) or "{}")
        except (TypeError, ValueError):
            zone_analysis = {}
        proposal_row["ai_zone_analysis"] = zone_analysis if isinstance(zone_analysis, dict) else {}
        proposal_row["evidence"] = scouting_evidence.get(str(proposal_row["id"]), [])
        for option in proposal_row["proposal"].get("options", []):
            linked = next(
                (row for row in rows if str(row.get("source_scouting_id") or "") == str(proposal_row["id"])
                 and str(row.get("variety_id") or "") == str(option.get("variety_id") or "")),
                None,
            )
            option["assessment_id"] = linked.get("id") if linked else None
            option["assessment_status"] = linked.get("review_status") if linked else None
            forecast = forecast_by_variety.get(str(option.get("variety_name") or "").casefold(), {})
            is_estate = option.get("scope_type") == "estate"
            baseline_kg = baseline_total if is_estate else float(forecast.get("baseline_grape_kg") or forecast.get("grape_kg") or 0)
            current_kg = adjusted_total if is_estate else float(forecast.get("adjusted_grape_kg") or baseline_kg)
            standalone_loss = float(option.get("proposed_estate_loss_pct") or 0)
            option["baseline_forecast_kg"] = round(baseline_kg, 2)
            option["current_approved_forecast_kg"] = round(current_kg, 2)
            option["standalone_proposed_reduction_kg"] = round(baseline_kg * standalone_loss / 100.0, 2)
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("review_status") == "approved":
            current["|".join((str(row["event_key"]), str(row.get("block_id") or ""), str(row.get("variety_id") or "")))] = row
    chains: dict[str, dict[str, Any]] = {}
    for row in rows:
        chain = chains.setdefault(str(row["event_key"]), {"event_key": row["event_key"], "damage_type": row.get("damage_type"), "reports": []})
        chain["reports"].append({"kind": "assessment", **row})
    for row in proposal_rows:
        key = str(row.get("damage_event_key") or f"unlinked:{row['id']}")
        chain = chains.setdefault(key, {"event_key": key, "damage_type": row.get("damage_type"), "reports": []})
        if not any(str(item.get("source_scouting_id") or "") == str(row["id"]) for item in chain["reports"]):
            chain["reports"].append({"kind": "scouting_proposal", **row})
    for chain in chains.values():
        chain["reports"].sort(key=lambda item: str(item.get("assessed_at") or item.get("observed_at") or ""))
        chain["current_approved_reports"] = [
            item for item in chain["reports"]
            if item.get("kind") == "assessment" and item.get("review_status") == "approved"
            and current.get("|".join((str(item["event_key"]), str(item.get("block_id") or ""), str(item.get("variety_id") or ""))), {}).get("id") == item.get("id")
        ]
        chain["current_approved"] = chain["current_approved_reports"][-1] if chain["current_approved_reports"] else None
        chain["damage_occurrence_confirmed"] = any(
            bool(item.get("damage_occurrence_confirmed")) for item in chain["reports"]
            if item.get("kind") == "assessment"
        )
        chain["scope_type"] = "estate" if any(
            item.get("kind") == "assessment" and item.get("scope_type") == "estate"
            for item in chain["reports"]
        ) else None
        chain["scope_coverage_pct"] = 100.0 if chain["scope_type"] == "estate" else None
        chain["yield_loss_quantified"] = any(
            bool(item.get("yield_loss_quantified")) for item in chain["current_approved_reports"]
        )
        agronomist_reports = [
            item for item in chain["reports"]
            if item.get("kind") == "assessment" and item.get("review_status") == "approved"
            and _assessment_loss_pct(item) is not None
        ]
        ai_reports = [
            item for item in chain["reports"]
            if item.get("kind") == "assessment" and item.get("source_type") == "photo_ai_chain"
            and item.get("review_status") in {"draft", "approved"} and _assessment_loss_pct(item) is not None
        ]
        agronomist = agronomist_reports[-1] if agronomist_reports else None
        ai = ai_reports[-1] if ai_reports else None
        ai_calculation = (ai or {}).get("calculation") or {}
        system_pct = ai_calculation.get("zone_yield_reduction_pct")
        if system_pct is None and ai:
            system_pct = _assessment_loss_pct(ai)
        evidence_urls: set[str] = set()
        for item in chain["reports"]:
            for value in item.get("evidence") or []:
                url = value if isinstance(value, str) else value.get("url")
                if url:
                    evidence_urls.add(str(url))
        # A recalculation is a proposal, never an implicit replacement for an
        # Agronomist-approved event result.  The first structured system result
        # may guide planning provisionally only while the chain has no final.
        ai_is_pending_proposal = bool(ai and ai.get("review_status") == "draft")
        current_forecast = agronomist or ai
        chain["estimate_comparison"] = {
            "agronomist_pct": _assessment_loss_pct(agronomist) if agronomist else None,
            "agronomist_confidence": (agronomist or {}).get("confidence"),
            "agronomist_date": (agronomist or {}).get("assessed_at"),
            "agronomist_status": (agronomist or {}).get("review_status"),
            "agronomist_assessment_id": (agronomist or {}).get("id"),
            "ai_pct": system_pct,
            "ai_low_pct": ai_calculation.get("zone_yield_reduction_low_pct"),
            "ai_high_pct": ai_calculation.get("zone_yield_reduction_high_pct"),
            "ai_adjustment_pct_points": ai_calculation.get("change_from_previous_ai_pct_points"),
            "ai_prior_pct": (ai_calculation.get("approved_prior") or {}).get("estimate_pct"),
            "ai_confidence": (ai or {}).get("confidence"),
            "ai_date": (ai or {}).get("assessed_at"),
            "ai_status": (ai or {}).get("review_status"),
            "ai_assessment_id": (ai or {}).get("id"),
            "proposal_pending_approval": bool(ai_is_pending_proposal),
            "proposal_change_from_final_pct_points": (
                round(float(system_pct) - float(_assessment_loss_pct(agronomist)), 2)
                if ai_is_pending_proposal and system_pct is not None and agronomist
                and _assessment_loss_pct(agronomist) is not None else None
            ),
            "report_count": len(chain["reports"]),
            "photo_count": len(evidence_urls),
            "forecast_pct": _assessment_loss_pct(current_forecast) if current_forecast else None,
            "forecast_basis": "agronomist_approved" if agronomist else "ai_provisional" if ai else "none",
        }
        chain["pending_supplements"] = sum(
            (item.get("kind") == "scouting_proposal" and item.get("damage_proposal_status") == "calculated")
            or (item.get("kind") == "assessment" and item.get("review_status") == "draft")
            for item in chain["reports"]
        )
    return json_ready({
        "damage_assessments": rows,
        "current_damage_assessments": list(current.values()),
        "damage_reduction_proposals": proposal_rows,
        "damage_event_chains": sorted(chains.values(), key=lambda item: str(item["event_key"])),
        "damage_forecast_impact": {
            "baseline_grape_kg": baseline_total,
            "approved_adjusted_grape_kg": adjusted_total,
            "approved_reduction_kg": round(baseline_total - adjusted_total, 2),
            "varieties": adjusted_forecasts,
            "guardrail": "Structured AI event estimates may guide the forecast provisionally while clearly requesting Agronomist confirmation; confirmation or replacement becomes authoritative.",
        },
        "damage_scope_options": {
            "blocks": fetch_all("SELECT id,code,name FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code", (estate_id(),)),
            "varieties": fetch_all("SELECT id,name FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),)),
        },
    })


@router.post("/from-scouting/{observation_id}", dependencies=[Depends(authorize_write)])
def create_assessment_from_scouting(observation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    if payload.get("event_key"):
        event_key = str(payload["event_key"]).strip()[:120]
        if not event_key:
            raise HTTPException(422, "Damage event key cannot be empty")
        with transaction() as (_, cursor):
            changed = cursor.execute(
                "UPDATE scouting_observations SET damage_event_key=%s WHERE id=%s AND estate_id=%s",
                (event_key, observation_id, estate_id()),
            )
            if not changed:
                raise HTTPException(404, "Scouting report not found")
    proposal = refresh_scouting_damage_proposal(observation_id)
    if proposal.get("status") == "missing":
        raise HTTPException(404, "Scouting report not found")
    if payload.get("calculate_only"):
        return {"saved": True, "calculated": True, "proposal": proposal}
    options = proposal.get("options") or []
    variety_id = str(payload.get("variety_id") or "").strip()
    if variety_id:
        option = next((item for item in options if str(item.get("variety_id")) == variety_id), None)
    else:
        option = proposal.get("recommended_option")
    if not option:
        raise HTTPException(422, "Choose which mapped variety this supplementary report evaluates")
    observation = fetch_one(
        "SELECT so.*,COALESCE(sds.damage_scope,'block') damage_scope,sds.variety_id,sds.reported_zone_area_ha,sds.representative_survey,"
        "sds.ai_zone_damage_pct,sds.ai_zone_damage_low_pct,sds.ai_zone_damage_high_pct,sds.ai_zone_yield_reduction_pct,"
        "sds.ai_zone_yield_reduction_low_pct,sds.ai_zone_yield_reduction_high_pct,sds.ai_zone_analysis_json,s.vintage_year,vb.code block_code "
        "FROM scouting_observations so JOIN seasons s ON s.id=so.season_id LEFT JOIN scouting_damage_scopes sds ON sds.observation_id=so.id "
        "LEFT JOIN vineyard_blocks vb ON vb.id=so.block_id WHERE so.id=%s AND so.estate_id=%s",
        (observation_id, estate_id()),
    ) or {}
    existing = fetch_one(
        "SELECT id,review_status FROM vineyard_damage_assessments WHERE source_scouting_id=%s AND variety_id<=>%s AND estate_id=%s AND active=1",
        (observation_id, option.get("variety_id"), estate_id()),
    ) or {}
    if existing.get("review_status") == "approved":
        raise HTTPException(409, "This scouting report is already approved in the event chain; record a new supplementary scouting report for new evidence")
    previous = fetch_one(
        "SELECT scope_type,estate_yield_loss_pct,affected_area_pct,estimated_yield_loss_pct FROM vineyard_damage_assessments "
        "WHERE estate_id=%s AND season_id=%s AND event_key=%s AND active=1 AND review_status='approved' "
        "AND variety_id<=>%s AND block_id<=>%s ORDER BY assessed_at DESC LIMIT 1",
        (estate_id(), observation.get("season_id"), proposal["event_key"], option.get("variety_id"), option.get("block_id")),
    ) or {}
    proposed_loss = float(option.get("proposed_variety_loss_pct") or 0)
    prior_loss = float(previous.get("estate_yield_loss_pct") or 0)
    if previous.get("estate_yield_loss_pct") is None:
        prior_loss = float(previous.get("affected_area_pct") or 0) * float(previous.get("estimated_yield_loss_pct") or 0) / 100.0
    if not previous:
        trend = "initial"
    elif proposed_loss > prior_loss + 1:
        trend = "worsening"
    elif proposed_loss < prior_loss - 1:
        trend = "improving"
    else:
        trend = "stable"
    evidence = fetch_all(
        "SELECT id,original_filename,caption FROM entity_attachments WHERE estate_id=%s AND entity_type='scouting' AND entity_id=%s ORDER BY created_at",
        (estate_id(), observation_id),
    )
    evidence_json = [{"url": f"api/v1/attachments/{item['id']}/file", "filename": item.get("original_filename"), "caption": item.get("caption")} for item in evidence]
    assessment_id = str(existing.get("id") or new_id())
    actor = request.headers.get("X-Remote-User-Name") or "api"
    notes = str(payload.get("notes") or observation.get("notes") or "Calculated supplementary scouting report; Agronomist approval required.").strip()
    scope_type = str(option.get("scope_type") or "block_variety")
    estate_loss = option.get("proposed_estate_loss_pct") if scope_type == "estate" else None
    affected_pct = None if scope_type == "estate" else option.get("affected_area_pct")
    local_loss_pct = None if scope_type == "estate" else option.get("estimated_yield_loss_pct")
    with transaction() as (_, cursor):
        if existing:
            cursor.execute(
                "UPDATE vineyard_damage_assessments SET event_key=%s,damage_type=%s,event_date=DATE(%s),assessed_at=%s,observer_name=%s,trend=%s,"
                "scope_type=%s,block_id=%s,variety_id=%s,estate_yield_loss_pct=%s,affected_area_pct=%s,estimated_yield_loss_pct=%s,"
                "confidence=%s,review_status='draft',approved_by=NULL,approved_at=NULL,source_type=%s,source_reference=%s,evidence_json=%s,calculation_json=%s,notes=%s "
                "WHERE id=%s AND estate_id=%s",
                (proposal["event_key"], proposal["damage_type"], observation.get("observed_at"), observation.get("observed_at"), actor, trend,
                 scope_type, option.get("block_id"), option.get("variety_id"), estate_loss, affected_pct, local_loss_pct,
                 proposal.get("confidence"), f"scouting_{proposal.get('source') or 'manual'}", observation_id, json.dumps(evidence_json),
                 json.dumps(json_ready(proposal), default=str), notes, assessment_id, estate_id()),
            )
        else:
            cursor.execute(
                "INSERT INTO vineyard_damage_assessments (id,estate_id,season_id,event_key,damage_type,event_date,assessed_at,observer_name,trend,scope_type,block_id,variety_id,estate_yield_loss_pct,affected_area_pct,estimated_yield_loss_pct,confidence,review_status,source_type,source_reference,source_scouting_id,evidence_json,calculation_json,notes) "
                "VALUES (%s,%s,%s,%s,%s,DATE(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s)",
                (assessment_id, estate_id(), observation.get("season_id"), proposal["event_key"], proposal["damage_type"], observation.get("observed_at"), observation.get("observed_at"), actor, trend,
                 scope_type, option.get("block_id"), option.get("variety_id"), estate_loss, affected_pct, local_loss_pct, proposal.get("confidence"),
                 f"scouting_{proposal.get('source') or 'manual'}", observation_id, observation_id, json.dumps(evidence_json), json.dumps(json_ready(proposal), default=str), notes),
            )
        audit(cursor, "calculate", "damage_assessment", assessment_id, {"source_scouting_id": observation_id, "event_key": proposal["event_key"], "option": option, "review_status": "draft"}, actor)
    return {"saved": True, "assessment_id": assessment_id, "review_status": "draft", "event_key": proposal["event_key"], "proposal": proposal}


@router.post("/event-ai-assessment", dependencies=[Depends(authorize_write)])
def create_ai_event_assessment(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    event_key = str(payload.get("event_key") or "").strip()[:120]
    if not event_key:
        raise HTTPException(422, "Choose a damage event chain")
    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Choose a valid vintage year") from exc
    actor = request.headers.get("X-Remote-User-Name") or "api"
    # Lazy import avoids coupling route registration to the intelligence worker.
    from ..intelligence import analyze_damage_event_evidence

    result = analyze_damage_event_evidence(event_key, year, actor)
    if result.get("status") == "missing":
        raise HTTPException(404, result.get("reason") or "Damage event chain not found")
    if result.get("status") == "review_required":
        raise HTTPException(422, result.get("reason") or "The current reports do not support an AI percentage")
    return result


@router.patch("/{assessment_id}", dependencies=[Depends(authorize_write)])
def update_damage_assessment(assessment_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    row = fetch_one(
        "SELECT a.*,s.vintage_year FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id "
        "WHERE a.id=%s AND a.estate_id=%s AND a.active=1",
        (assessment_id, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Damage assessment not found")
    trend = str(payload.get("trend") or row["trend"]).strip().casefold()
    confidence = str(payload.get("confidence") or row["confidence"]).strip().casefold()
    review_status = str(payload.get("review_status") or row["review_status"]).strip().casefold()
    scope_type = str(payload.get("scope_type") or row.get("scope_type") or "estate").strip().casefold()
    if trend not in {"initial", "worsening", "stable", "improving", "resolved"}:
        raise HTTPException(422, "Choose a valid damage trend")
    if confidence not in {"low", "medium", "high"}:
        raise HTTPException(422, "Choose low, medium or high confidence")
    if review_status not in {"draft", "approved", "rejected"}:
        raise HTTPException(422, "Choose draft, approved or rejected")
    if scope_type not in {"estate", "variety", "block_variety"}:
        raise HTTPException(422, "Choose estate, variety or block and variety scope")
    loss_value = payload.get("estate_yield_loss_pct", row.get("estate_yield_loss_pct"))
    if loss_value in (None, ""):
        loss_pct = None
    else:
        try:
            loss_pct = round(float(loss_value), 2)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Estate yield loss must be a percentage") from exc
        if loss_pct < 0 or loss_pct > 80:
            raise HTTPException(422, "Estate yield loss must be between 0 and 80 percent")
    block_id = str(payload.get("block_id") or row.get("block_id") or "").strip() or None
    variety_id = str(payload.get("variety_id") or row.get("variety_id") or "").strip() or None
    affected_value = payload.get("affected_area_pct", row.get("affected_area_pct"))
    local_loss_value = payload.get("estimated_yield_loss_pct", row.get("estimated_yield_loss_pct"))
    try:
        affected_pct = None if affected_value in (None, "") else round(float(affected_value), 2)
        local_loss_pct = None if local_loss_value in (None, "") else round(float(local_loss_value), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Affected area and local yield loss must be percentages") from exc
    if any(value is not None and not 0 <= value <= 100 for value in (affected_pct, local_loss_pct)):
        raise HTTPException(422, "Affected area and local yield loss must be between 0 and 100 percent")
    if scope_type == "estate":
        block_id = variety_id = local_loss_pct = None
        affected_pct = 100.0
    else:
        loss_pct = None
        if not variety_id or affected_pct is None or local_loss_pct is None:
            raise HTTPException(422, "Scoped loss requires a variety, affected area and local yield-loss percentage")
        if scope_type == "block_variety" and not block_id:
            raise HTTPException(422, "Block and variety scope requires a block")
        if not fetch_one("SELECT id FROM grape_varieties WHERE id=%s AND estate_id=%s AND active=1", (variety_id, estate_id())):
            raise HTTPException(422, "Choose a valid estate variety")
        if block_id and not fetch_one("SELECT id FROM vineyard_blocks WHERE id=%s AND estate_id=%s AND active=1", (block_id, estate_id())):
            raise HTTPException(422, "Choose a valid vineyard block")
        if block_id and not fetch_one("SELECT block_id FROM block_varieties WHERE block_id=%s AND variety_id=%s", (block_id, variety_id)):
            raise HTTPException(422, "The selected variety is not mapped to that block")
    if review_status == "approved" and scope_type == "estate" and loss_pct is None:
        raise HTTPException(422, "Enter the Agronomist final yield-loss percentage before approving")
    assessed_value = str(payload.get("assessed_at") or row["assessed_at"]).strip()
    if len(assessed_value) == 10:
        assessed_value += " 12:00:00"
    try:
        assessed_at = datetime.fromisoformat(assessed_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Assessment date is invalid") from exc
    if assessed_at.date() > datetime.now(ZoneInfo("Europe/Rome")).date():
        raise HTTPException(422, "Assessment date cannot be in the future")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    quantitative_change = any((
        loss_pct != row.get("estate_yield_loss_pct"), scope_type != str(row.get("scope_type") or "estate"),
        block_id != row.get("block_id"), variety_id != row.get("variety_id"),
        affected_pct != row.get("affected_area_pct"), local_loss_pct != row.get("estimated_yield_loss_pct"),
    ))
    if review_status == "approved" or row.get("review_status") == "approved" or quantitative_change:
        require_discipline_approval(request, "agronomy")
    approved_by = actor if review_status == "approved" else None
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE vineyard_damage_assessments SET assessed_at=%s,observer_name=%s,trend=%s,scope_type=%s,block_id=%s,variety_id=%s,estate_yield_loss_pct=%s,affected_area_pct=%s,estimated_yield_loss_pct=%s,"
            "confidence=%s,review_status=%s,approved_by=%s,approved_at=CASE WHEN %s='approved' THEN CURRENT_TIMESTAMP(6) ELSE NULL END,notes=%s "
            "WHERE id=%s AND estate_id=%s AND active=1",
            (assessed_value, str(payload.get("observer_name") or row["observer_name"]).strip(), trend, scope_type, block_id, variety_id, loss_pct, affected_pct, local_loss_pct,
             confidence, review_status, approved_by, review_status, str(payload.get("notes") or "").strip() or None,
             assessment_id, estate_id()),
        )
        if row.get("source_scouting_id"):
            cursor.execute(
                "UPDATE scouting_observations so SET damage_proposal_status=CASE "
                "WHEN (SELECT COUNT(*) FROM vineyard_damage_assessments a WHERE a.source_scouting_id=so.id AND a.active=1 AND a.review_status='approved') "
                ">= COALESCE(JSON_LENGTH(JSON_EXTRACT(so.damage_proposal_json,'$.options')),1) THEN 'promoted' "
                "ELSE 'calculated' END WHERE so.id=%s AND so.estate_id=%s",
                (row["source_scouting_id"], estate_id()),
            )
        audit(cursor, "update", "damage_assessment", assessment_id, {"trend": trend, "scope_type": scope_type, "block_id": block_id, "variety_id": variety_id, "estate_yield_loss_pct": loss_pct, "affected_area_pct": affected_pct, "estimated_yield_loss_pct": local_loss_pct, "review_status": review_status}, actor)
    recalculation_required = quantitative_change or review_status != str(row.get("review_status") or "")
    refresh_id = None
    refresh_error = None
    if recalculation_required:
        try:
            refresh_id = request_harvest_refresh(
                "damage_assessment", assessment_id,
                "Agronomist damage value or approval changed; recalculate yield and harvest projections",
            )
        except Exception as exc:  # The approved database write remains valid and the immediate calculation still runs.
            refresh_error = str(exc)[:300]
    dashboard = damage_assessment_dashboard(int(row["vintage_year"]))
    chain = next(
        (item for item in dashboard.get("damage_event_chains") or [] if str(item.get("event_key")) == str(row.get("event_key"))),
        {},
    )
    return {
        "saved": True,
        "assessment_id": assessment_id,
        "review_status": review_status,
        "authoritative": review_status == "approved",
        "prediction_refresh_queued": refresh_id is not None,
        "prediction_refresh_error": refresh_error,
        "recalculation": {
            "vintage_year": int(row["vintage_year"]),
            "event_key": row.get("event_key"),
            "estimate_comparison": chain.get("estimate_comparison") or {},
            "forecast_impact": dashboard.get("damage_forecast_impact") or {},
        },
    }


@router.delete("/{assessment_id}", dependencies=[Depends(authorize_write)])
def delete_damage_assessment(assessment_id: str, request: Request) -> dict[str, Any]:
    require_discipline_approval(request, "agronomy")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE vineyard_damage_assessments SET active=0,review_status='archived' WHERE id=%s AND estate_id=%s AND active=1",
            (assessment_id, estate_id()),
        )
        if not cursor.rowcount:
            raise HTTPException(404, "Damage assessment not found")
        audit(cursor, "archive", "damage_assessment", assessment_id, {"reason": "Removed from Agronomy; audit history preserved"}, actor)
    return {"deleted": True, "audit_preserved": True}
