"""Provisional production impact derived from authoritative scouting records."""

from __future__ import annotations

import json
import re
from typing import Any

from .db import fetch_all, fetch_one, transaction
from .service import estate_id, json_ready


_DAMAGE_TERMS = {
    "hail": ("hail", "hailstorm", "grandine"),
    "rot_disease": ("rot", "marciume", "botrytis", "muffa", "mildew", "oidio", "peronospora"),
    "sunburn_heat": ("sunburn", "sunscald", "scald", "heat damage", "bruciatura", "colpo di sole"),
    "pest_animal": ("pest", "insect", "bird", "animal", "boar", "cinghiale", "insetto"),
    "wind_storm": ("wind damage", "storm damage", "vento", "tempesta"),
    "frost": ("frost", "freeze", "gelata"),
    "drought_water_stress": ("drought", "water stress", "siccità", "siccita"),
}
_BASE_LOCAL_LOSS = {"trace": 2.0, "low": 7.0, "medium": 18.0, "high": 35.0, "critical": 60.0}
_HAIL_LOCAL_LOSS = {"trace": 5.0, "low": 12.0, "medium": 25.0, "high": 45.0, "critical": 70.0}


def _percent(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, number)), 2)


def canonical_damage_type(*parts: Any, explicit: Any = None) -> str | None:
    direct = re.sub(r"[^a-z0-9]+", "_", str(explicit or "").casefold()).strip("_")
    if direct in _DAMAGE_TERMS:
        return direct
    text = " ".join(str(part or "") for part in parts).casefold()
    for damage_type, terms in _DAMAGE_TERMS.items():
        if any(term in text for term in terms):
            return damage_type
    return direct[:80] or None


def derive_scouting_damage_fields(values: dict[str, Any]) -> dict[str, Any]:
    """Normalize explicit damage data and conservatively derive missing values from one scouting incident."""
    damage_type = canonical_damage_type(values.get("issue_type"), values.get("notes"), explicit=values.get("damage_type"))
    if not damage_type:
        return {}
    affected = _percent(values.get("affected_area_pct"))
    if affected is None:
        affected = _percent(values.get("incidence_pct"))
    local_loss = _percent(values.get("estimated_yield_loss_pct"))
    severity = str(values.get("severity") or "low").casefold()
    if local_loss is None:
        local_loss = (_HAIL_LOCAL_LOSS if damage_type == "hail" else _BASE_LOCAL_LOSS).get(severity, 7.0)
    explicit_estimate = values.get("estimated_yield_loss_pct") not in (None, "")
    confidence = str(values.get("yield_impact_confidence") or "").casefold()
    if confidence not in {"low", "medium", "high"}:
        confidence = "high" if explicit_estimate and affected is not None else "medium" if affected is not None else "low"
    return {
        "damage_type": damage_type,
        "affected_area_pct": affected,
        "estimated_yield_loss_pct": local_loss,
        "yield_impact_confidence": confidence,
        "yield_impact_source": values.get("yield_impact_source") or "manual",
        "yield_impact_review_status": values.get("yield_impact_review_status") or "provisional",
    }


def build_scouting_damage_proposal(
    observation: dict[str, Any],
    variety_mappings: list[dict[str, Any]],
    event_key: str,
) -> dict[str, Any]:
    """Calculate bounded, review-only loss options from one scouting report."""
    derived = {**observation, **derive_scouting_damage_fields(observation)}
    affected = _percent(derived.get("affected_area_pct"))
    local_loss = _percent(derived.get("estimated_yield_loss_pct"))
    damage_type = derived.get("damage_type")
    options: list[dict[str, Any]] = []
    if damage_type and affected is not None and local_loss is not None:
        local_effect = affected / 100.0 * local_loss / 100.0
        for mapping in variety_mappings:
            block_area = float(mapping.get("block_variety_area_ha") or 0)
            total_area = float(mapping.get("total_variety_area_ha") or 0)
            estate_share = min(1.0, block_area / total_area) if block_area > 0 and total_area > 0 else None
            estate_loss = local_effect * estate_share * 100.0 if estate_share is not None else None
            options.append({
                "scope_type": "block_variety",
                "block_id": observation.get("block_id"),
                "block_code": mapping.get("block_code"),
                "variety_id": mapping.get("variety_id"),
                "variety_name": mapping.get("variety_name"),
                "block_variety_area_ha": round(block_area, 4) if block_area else None,
                "total_variety_area_ha": round(total_area, 4) if total_area else None,
                "affected_area_pct": affected,
                "estimated_yield_loss_pct": local_loss,
                "proposed_variety_loss_pct": round(local_effect * 100.0, 2),
                "proposed_estate_loss_pct": round(estate_loss, 2) if estate_loss is not None else None,
            })
    confidence = str(derived.get("yield_impact_confidence") or "low").casefold()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    return {
        "status": "calculated" if options else "insufficient_evidence",
        "event_key": event_key,
        "damage_type": damage_type,
        "observed_at": observation.get("observed_at"),
        "source": derived.get("yield_impact_source") or "manual",
        "confidence": confidence,
        "review_status": "provisional",
        "calculation": "block variety share × affected area share × estimated local yield loss",
        "options": options,
        "recommended_option": options[0] if len(options) == 1 else None,
        "requires_variety_selection": len(options) > 1,
        "guardrail": "Calculated proposal only. It does not change harvest quantities until an Agronomist approves the supplementary assessment.",
    }


def _damage_event_key(observation: dict[str, Any], damage_type: str | None) -> str:
    saved = str(observation.get("damage_event_key") or "").strip()
    if saved:
        return saved[:120]
    if damage_type:
        existing = fetch_one(
            "SELECT a.event_key FROM vineyard_damage_assessments a "
            "WHERE a.estate_id=%s AND a.season_id=%s AND a.damage_type=%s AND a.active=1 "
            "AND ABS(DATEDIFF(a.event_date,DATE(%s)))<=120 ORDER BY ABS(DATEDIFF(a.event_date,DATE(%s))),a.assessed_at DESC LIMIT 1",
            (estate_id(), observation.get("season_id"), damage_type, observation.get("observed_at"), observation.get("observed_at")),
        ) or {}
        if existing.get("event_key"):
            return str(existing["event_key"])[:120]
    observed = str(observation.get("observed_at") or "")[:10] or "undated"
    block = re.sub(r"[^a-z0-9]+", "-", str(observation.get("block_code") or observation.get("block_id") or "estate").casefold()).strip("-")
    return f"{damage_type or 'damage'}-{observed}-{block}"[:120]


def refresh_scouting_damage_proposal(observation_id: str) -> dict[str, Any]:
    """Recalculate and persist the approval proposal for a scouting report."""
    observation = fetch_one(
        "SELECT so.*,vb.code block_code FROM scouting_observations so "
        "JOIN vineyard_blocks vb ON vb.id=so.block_id WHERE so.id=%s AND so.estate_id=%s",
        (observation_id, estate_id()),
    )
    if not observation:
        return {"status": "missing", "observation_id": observation_id}
    derived = derive_scouting_damage_fields(observation)
    event_key = _damage_event_key(observation, derived.get("damage_type"))
    mappings = fetch_all(
        "SELECT bv.variety_id,gv.name variety_name,vb.code block_code,COALESCE(bv.area_ha,vb.area_ha) block_variety_area_ha,"
        "(SELECT SUM(COALESCE(all_bv.area_ha,all_vb.area_ha)) FROM block_varieties all_bv "
        "JOIN vineyard_blocks all_vb ON all_vb.id=all_bv.block_id WHERE all_vb.estate_id=vb.estate_id AND all_vb.active=1 AND all_bv.variety_id=bv.variety_id) total_variety_area_ha "
        "FROM block_varieties bv JOIN vineyard_blocks vb ON vb.id=bv.block_id JOIN grape_varieties gv ON gv.id=bv.variety_id "
        "WHERE bv.block_id=%s ORDER BY gv.name",
        (observation.get("block_id"),),
    )
    proposal = build_scouting_damage_proposal(observation, mappings, event_key)
    proposed_estate = max(
        (float(item["proposed_estate_loss_pct"]) for item in proposal["options"] if item.get("proposed_estate_loss_pct") is not None),
        default=None,
    )
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE scouting_observations SET damage_event_key=%s,damage_proposal_status=%s,proposed_estate_loss_pct=%s,damage_proposal_json=%s "
            "WHERE id=%s AND estate_id=%s",
            (event_key, "calculated" if proposal["options"] else "not_calculated", proposed_estate,
             json.dumps(json_ready(proposal), ensure_ascii=False, default=str), observation_id, estate_id()),
        )
    return {**proposal, "observation_id": observation_id}


def apply_damage_adjustments(
    forecasts: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
    total_area_by_variety: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Apply approved, explicit damage estimates without changing forecast baselines.

    Impacts are vintage-scoped when both the forecast and impact carry a vintage
    year.  A later assessment for the same event replaces the earlier one.  The
    function deliberately refuses provisional/confirmed scouting heuristics:
    those remain review evidence until an Agronomist records an approved damage
    assessment with an explicit percentage.
    """
    totals = {str(key).casefold(): float(value or 0) for key, value in (total_area_by_variety or {}).items()}
    candidates: list[dict[str, Any]] = []
    latest_events: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raw in impacts:
        if str(raw.get("yield_impact_review_status") or "").casefold() != "approved":
            continue
        event_id = str(raw.get("damage_event_id") or "").strip()
        if not event_id:
            # Production effects must be tied to a durable event.  Date-based
            # scouting observations cannot safely distinguish follow-ups from
            # independent damage and therefore never alter forecast kilograms.
            continue
        event_key = (event_id, str(raw.get("block_id") or ""), str(raw.get("variety_name") or "").casefold())
        observed = str(raw.get("observed_date") or raw.get("observed_at") or "")
        previous = latest_events.get(event_key)
        previous_observed = str(previous.get("observed_date") or previous.get("observed_at") or "") if previous else ""
        if previous is None or observed > previous_observed:
            latest_events[event_key] = raw
    candidates.extend(latest_events.values())
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw in candidates:
        row = dict(raw)
        if str(row.get("yield_impact_review_status") or "").casefold() != "approved":
            continue
        estate_loss = _percent(row.get("estate_yield_loss_pct"))
        affected = _percent(row.get("affected_area_pct"))
        loss = _percent(row.get("estimated_yield_loss_pct"))
        damage_type = row.get("damage_type")
        if not damage_type or (estate_loss is None and (affected is None or loss is None)):
            continue
        event_id = str(row.get("damage_event_id") or "").strip()
        key = ("event", event_id, str(row.get("block_id") or ""), str(row.get("variety_name") or "").casefold())
        effect = estate_loss / 100.0 if estate_loss is not None else affected / 100.0 * loss / 100.0
        observed = str(row.get("observed_date") or row.get("observed_at") or "")
        previous = deduped.get(key)
        previous_observed = str(previous.get("observed_date") or previous.get("observed_at") or "") if previous else ""
        if previous is None or observed > previous_observed or (observed == previous_observed and effect > float(previous["effect"])):
            deduped[key] = {**row, "effect": effect}

    result: list[dict[str, Any]] = []
    for forecast in forecasts:
        row = dict(forecast)
        forecast_year = row.get("vintage_year")
        variety_key = str(row.get("variety_name") or "").casefold()
        baseline = float(row.get("grape_kg") or 0)
        relevant = [
            item for item in deduped.values()
            if (forecast_year in (None, "") or item.get("vintage_year") in (None, "")
                or int(item["vintage_year"]) == int(forecast_year))
            and (not str(item.get("variety_name") or "").strip()
                 or str(item.get("variety_name") or "").casefold() == variety_key)
        ]
        total_area = totals.get(variety_key, 0.0)
        if total_area <= 0:
            total_area = sum(float(item.get("variety_area_ha") or 0) for item in relevant)
        remaining = 1.0
        confidences: list[str] = []
        estate_effects = [
            min(0.8, float(item["effect"]))
            for item in relevant
            if item.get("estate_yield_loss_pct") is not None
        ]
        # Estate loss fields describe the whole-vintage result, not separable
        # acreage.  Use the strongest current approved value instead of
        # multiplying overlapping storm/disease estimates.
        if estate_effects:
            remaining = 1.0 - max(estate_effects)
        for item in relevant:
            if item.get("estate_yield_loss_pct") is not None:
                confidences.append(str(item.get("yield_impact_confidence") or "low"))
                continue
            if item.get("scope_type") == "variety":
                remaining *= 1.0 - min(0.8, float(item["effect"]))
                confidences.append(str(item.get("yield_impact_confidence") or "low"))
                continue
            block_area = float(item.get("variety_area_ha") or 0)
            if total_area <= 0 or block_area <= 0:
                continue
            estate_effect = min(1.0, block_area / total_area) * float(item["effect"])
            remaining *= 1.0 - min(0.8, estate_effect)
            confidences.append(str(item.get("yield_impact_confidence") or "low"))
        reduction = min(80.0, max(0.0, (1.0 - remaining) * 100.0))
        adjusted = round(baseline * (1.0 - reduction / 100.0), 2)
        rank = {"low": 1, "medium": 2, "high": 3}
        confidence = max(confidences, key=lambda item: rank.get(item, 0)) if confidences else None
        statuses = {str(item.get("yield_impact_review_status") or "provisional") for item in relevant}
        row.update({
            "baseline_grape_kg": round(baseline, 2),
            "adjusted_grape_kg": adjusted,
            "damage_reduction_pct": round(reduction, 2),
            "damage_evidence_count": len(relevant),
            "damage_confidence": confidence,
            "damage_status": "approved" if "approved" in statuses else "confirmed" if "confirmed" in statuses else "provisional" if relevant else None,
            "damage_combination_method": "maximum_approved_estate_loss_plus_non_overlapping_scoped_effects" if relevant else None,
        })
        result.append(row)
    return result


def adjust_production_forecasts(forecasts: list[dict[str, Any]], vintage_year: int) -> list[dict[str, Any]]:
    impacts = fetch_all(
        "SELECT a.id,a.event_key damage_event_id,s.vintage_year,a.assessed_at observed_at,DATE(a.assessed_at) observed_date,a.damage_type,"
        "a.scope_type,a.block_id,a.affected_area_pct,a.estimated_yield_loss_pct,a.estate_yield_loss_pct,"
        "a.confidence yield_impact_confidence,a.review_status yield_impact_review_status,gv.name variety_name,"
        "COALESCE(bv.area_ha,vb.area_ha) variety_area_ha,a.observer_name,a.trend,a.notes "
        "FROM vineyard_damage_assessments a JOIN seasons s ON s.id=a.season_id "
        "LEFT JOIN vineyard_blocks vb ON vb.id=a.block_id LEFT JOIN block_varieties bv ON bv.block_id=a.block_id AND bv.variety_id=a.variety_id "
        "LEFT JOIN grape_varieties gv ON gv.id=a.variety_id "
        "WHERE a.estate_id=%s AND s.vintage_year=%s AND a.active=1 AND a.review_status='approved'",
        (estate_id(), vintage_year),
    )
    area_rows = fetch_all(
        "SELECT gv.name variety_name,SUM(COALESCE(bv.area_ha,vb.area_ha)) total_area_ha "
        "FROM block_varieties bv JOIN vineyard_blocks vb ON vb.id=bv.block_id "
        "JOIN grape_varieties gv ON gv.id=bv.variety_id WHERE vb.estate_id=%s GROUP BY gv.id,gv.name",
        (estate_id(),),
    )
    totals = {str(row.get("variety_name") or ""): float(row.get("total_area_ha") or 0) for row in area_rows}
    return apply_damage_adjustments(forecasts, impacts, totals)
