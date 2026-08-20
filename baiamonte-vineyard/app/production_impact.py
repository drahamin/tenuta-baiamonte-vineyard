"""Provisional production impact derived from authoritative scouting records."""

from __future__ import annotations

import re
from typing import Any

from .db import fetch_all
from .service import estate_id


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


def apply_damage_adjustments(
    forecasts: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
    total_area_by_variety: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Add a non-destructive, provisional damage layer to baseline forecast rows."""
    totals = {str(key).casefold(): float(value or 0) for key, value in (total_area_by_variety or {}).items()}
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw in impacts:
        row = {**raw, **derive_scouting_damage_fields(raw)}
        if str(row.get("yield_impact_review_status") or "provisional") == "rejected":
            continue
        affected = _percent(row.get("affected_area_pct"))
        loss = _percent(row.get("estimated_yield_loss_pct"))
        damage_type = row.get("damage_type")
        if affected is None or loss is None or not damage_type:
            continue
        key = (
            str(row.get("block_id") or ""),
            str(row.get("observed_date") or row.get("observed_at") or "")[:10],
            str(damage_type),
            str(row.get("variety_name") or "").casefold(),
        )
        effect = affected / 100.0 * loss / 100.0
        previous = deduped.get(key)
        if previous is None or effect > float(previous["effect"]):
            deduped[key] = {**row, "effect": effect}

    result: list[dict[str, Any]] = []
    for forecast in forecasts:
        row = dict(forecast)
        variety_key = str(row.get("variety_name") or "").casefold()
        baseline = float(row.get("grape_kg") or 0)
        relevant = [item for item in deduped.values() if str(item.get("variety_name") or "").casefold() == variety_key]
        total_area = totals.get(variety_key, 0.0)
        if total_area <= 0:
            total_area = sum(float(item.get("variety_area_ha") or 0) for item in relevant)
        remaining = 1.0
        confidences: list[str] = []
        for item in relevant:
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
        row.update({
            "baseline_grape_kg": round(baseline, 2),
            "adjusted_grape_kg": adjusted,
            "damage_reduction_pct": round(reduction, 2),
            "damage_evidence_count": len(relevant),
            "damage_confidence": confidence,
            "damage_status": "provisional" if relevant else None,
        })
        result.append(row)
    return result


def adjust_production_forecasts(forecasts: list[dict[str, Any]], vintage_year: int) -> list[dict[str, Any]]:
    impacts = fetch_all(
        "SELECT so.id,so.block_id,DATE(so.observed_at) observed_date,so.issue_type,so.severity,so.incidence_pct,so.notes,"
        "so.damage_type,so.affected_area_pct,so.estimated_yield_loss_pct,so.yield_impact_confidence,"
        "so.yield_impact_source,so.yield_impact_review_status,gv.name variety_name,"
        "COALESCE(bv.area_ha,vb.area_ha) variety_area_ha "
        "FROM scouting_observations so JOIN seasons s ON s.id=so.season_id "
        "JOIN vineyard_blocks vb ON vb.id=so.block_id JOIN block_varieties bv ON bv.block_id=so.block_id "
        "JOIN grape_varieties gv ON gv.id=bv.variety_id WHERE so.estate_id=%s AND s.vintage_year=%s",
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
