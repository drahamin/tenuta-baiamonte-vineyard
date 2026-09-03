"""Traceable enology process plans and evidence-bounded fermentation outlooks."""

from __future__ import annotations

from datetime import date, datetime, timezone
import unicodedata
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..access import authorize, authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..service import audit, estate_id, json_ready, new_id
from .people_roles import require_discipline_approval
from .laffort_catalog import additive_prediction_pipeline, catalog_rows, protocol_rows, suggest_products


router = APIRouter(tags=["enology-process"])
MODEL_VERSION = "fermentation-trend-v1"
TARGET_DRY_SG = 0.995
WINEMAKING_SOURCE = "PLAUD 2026-09-02 · 09-02 Vineyard Operations, Winemaking Strategy, and Administrative Coordination Meeting"

WINEMAKING_STAGES = (
    {"code": "intake_traceability", "name": "1. Fruit reception & lot identity", "applies_to": "any", "gate": "Confirm harvest source, variety, weight, fruit condition, vessel and received time before processing."},
    {"code": "crush_press_preparation", "name": "2. Crush / destem / press preparation", "applies_to": "any", "gate": "Choose the red or white route, prepare the receiving vessel and record the first physical cellar operation."},
    {"code": "must_analysis", "name": "3. Must analysis before fermentation", "applies_to": "any", "gate": "Review pH, total acidity, Babo, calculated potential alcohol, potassium and YAN/APA before nutrient or inoculation decisions."},
    {"code": "yeast_nutrient_plan", "name": "4. Yeast, enzyme, tannin & nutrient plan", "applies_to": "any", "gate": "Approve exact products, rates, technical-sheet rules and product lots. Nutrient quantity waits for measured YAN and a verified product conversion."},
    {"code": "inoculation", "name": "5. Inoculation", "applies_to": "any", "gate": "Record yeast preparation, exact quantity, product lot, time and enologist approval; do not treat a proposed rate as authorization."},
    {"code": "fermentation_monitoring", "name": "6. Fermentation monitoring", "applies_to": "any", "gate": "Trend temperature, specific gravity, Brix and pH; record sensory condition and next check. Flat density requires review."},
    {"code": "red_pre_press", "name": "7. Red: final-two-day pre-press step", "applies_to": "red", "gate": "When the enologist confirms the final two fermentation days, review the proposed red enzyme at 1 g/hL and the target press time."},
    {"code": "pressing_transfer", "name": "8. Pressing, separation & transfer", "applies_to": "any", "gate": "Record press/transfer time, destination vessel, recovered volume, lees/solids handling and any approved addition."},
    {"code": "post_fermentation", "name": "9. Post-fermentation stability", "applies_to": "any", "gate": "Confirm stable completion evidence, pH, total acidity and sensory condition before stabilization or aging decisions."},
    {"code": "aging_release", "name": "10. Aging plan & release from active winemaking", "applies_to": "any", "gate": "Record the aging vessel and review cadence. Optional post-press tannin remains a red-wine enologist decision with an exact approved dose."},
)

ENOLOGY_ANALYTES = {
    "ph": {"name": "pH", "default_unit": "pH", "aliases": {"ph"}},
    "total_acidity": {"name": "Total acidity / Acidità totale", "default_unit": "", "aliases": {"total_acidity", "total_acid", "titratable_acidity", "ta", "acidita_totale"}},
    "babo": {"name": "Babo", "default_unit": "°Babo", "aliases": {"babo", "degrees_babo", "grado_babo", "gradi_babo"}},
    "potential_alcohol": {"name": "Calculated potential alcohol / Alcol potenziale calcolato", "default_unit": "% vol", "aliases": {"potential_alcohol", "potential_alc", "alcohol_potential", "alcol_potenziale", "alcol_potenziale_calcolato"}},
    "potassium": {"name": "Potassium / Potassio", "default_unit": "", "aliases": {"potassium", "potassio", "k"}},
    "yan": {"name": "Yeast assimilable nitrogen (YAN)", "default_unit": "mg/L", "aliases": {"yan", "yeast_assimilable_nitrogen", "azoto_prontamente_assimilabile", "apa"}},
    "actual_alcohol": {"name": "Alcohol / Alcol effettivo", "default_unit": "% vol", "aliases": {"actual_alcohol", "alcohol", "ethanol", "alcol", "alcol_effettivo"}},
    "residual_sugar": {"name": "Residual sugar / Zuccheri residui", "default_unit": "", "aliases": {"residual_sugar", "glucose_fructose", "glucose_and_fructose", "zuccheri_residui"}},
    "volatile_acidity": {"name": "Volatile acidity / Acidità volatile", "default_unit": "", "aliases": {"volatile_acidity", "volatile_acid", "va", "acidita_volatile"}},
    "malic_acid": {"name": "Malic acid / Acido malico", "default_unit": "", "aliases": {"malic_acid", "malate", "acido_malico"}},
    "lactic_acid": {"name": "Lactic acid / Acido lattico", "default_unit": "", "aliases": {"lactic_acid", "lactate", "acido_lattico"}},
    "free_so2": {"name": "Free sulfur dioxide / SO₂ libera", "default_unit": "mg/L", "aliases": {"free_so2", "so2_free", "free_sulfur_dioxide", "so2_libera"}},
    "total_so2": {"name": "Total sulfur dioxide / SO₂ totale", "default_unit": "mg/L", "aliases": {"total_so2", "so2_total", "total_sulfur_dioxide", "so2_totale"}},
    "turbidity": {"name": "Turbidity / Torbidità", "default_unit": "NTU", "aliases": {"turbidity", "ntu", "torbidita"}},
    "dissolved_oxygen": {"name": "Dissolved oxygen / Ossigeno disciolto", "default_unit": "mg/L", "aliases": {"dissolved_oxygen", "oxygen_dissolved", "do", "ossigeno_disciolto"}},
}


def canonical_enology_analyte(code: str | None, name: str | None = None, unit: str | None = None) -> dict[str, str] | None:
    """Map Italian/English laboratory labels without changing the reported unit."""
    raw = str(code or name or "").strip().casefold().replace("°", "degrees_")
    normalized = "_".join("".join(character for character in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(character)).replace("-", " ").replace("/", " ").split())
    for metric_code, definition in ENOLOGY_ANALYTES.items():
        if normalized in definition["aliases"]:
            reported_unit = str(unit or "").strip()
            return {"code": metric_code, "name": definition["name"], "unit": reported_unit or definition["default_unit"]}
    return None


def _enology_test_series(year: int, paired_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_type,s.lab_date,s.sampled_at,s.needs_review,s.source_document,"
        "v.name variety_name,b.code block_code,w.code wine_lot_code,r.analyte_code,r.analyte_name,r.numeric_value,r.unit,r.method "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN grape_varieties v ON v.id=s.variety_id "
        "LEFT JOIN vineyard_blocks b ON b.id=s.block_id LEFT JOIN wine_lots w ON w.id=s.wine_lot_id JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date))=%s "
        "AND s.sample_type IN ('grape','must','wine') AND r.numeric_value IS NOT NULL ORDER BY s.lab_date,s.sample_name,r.analyte_code",
        (estate_id(), year),
    )
    chart_rows: list[dict[str, Any]] = []
    babo_by_sample: dict[str, dict[str, Any]] = {}
    potential_samples: set[str] = set()
    for row in rows:
        metric = canonical_enology_analyte(row.get("analyte_code"), row.get("analyte_name"), row.get("unit"))
        if not metric:
            continue
        identity = row.get("wine_lot_code") or row.get("variety_name") or row.get("block_code") or row.get("sample_name")
        item = {**row, "metric_code": metric["code"], "metric_name": metric["name"], "display_unit": metric["unit"], "series_name": identity, "value": row.get("numeric_value"), "calculated": False}
        chart_rows.append(item)
        if metric["code"] == "babo":
            babo_by_sample[str(row["sample_id"])] = item
        elif metric["code"] == "potential_alcohol":
            potential_samples.add(str(row["sample_id"]))
    for sample_id, babo_row in babo_by_sample.items():
        if sample_id in potential_samples or babo_row.get("needs_review"):
            continue
        estimate = potential_alcohol_from_babo(float(babo_row["value"]), paired_results)
        if estimate.get("value_pct_vol") is None:
            continue
        chart_rows.append({**babo_row, "metric_code": "potential_alcohol", "metric_name": ENOLOGY_ANALYTES["potential_alcohol"]["name"], "display_unit": "% vol", "value": estimate["value_pct_vol"], "calculated": True, "calculation_model": estimate.get("model_version"), "calculation_factor": estimate.get("factor"), "calculation_evidence_count": estimate.get("evidence_count"), "calculation_confidence": estimate.get("confidence")})
    return chart_rows


def normalize_fermentation_overlay_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Align fermentation readings by elapsed time so vintages remain comparable."""
    parsed: list[tuple[dict[str, Any], datetime]] = []
    for row in rows:
        observed = row.get("observed_at")
        if isinstance(observed, datetime):
            moment = observed
        else:
            try:
                moment = datetime.fromisoformat(str(observed or "").replace("Z", "+00:00"))
            except ValueError:
                continue
        if moment.tzinfo is not None:
            moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
        parsed.append((row, moment))
    first_by_lot: dict[str, datetime] = {}
    for row, moment in parsed:
        lot_id = str(row.get("wine_lot_id") or row.get("lot_id") or "")
        if lot_id and (lot_id not in first_by_lot or moment < first_by_lot[lot_id]):
            first_by_lot[lot_id] = moment
    normalized: list[dict[str, Any]] = []
    for row, moment in sorted(parsed, key=lambda item: (int(item[0].get("vintage_year") or 0), str(item[0].get("wine_lot_id") or item[0].get("lot_id") or ""), item[1])):
        lot_id = str(row.get("wine_lot_id") or row.get("lot_id") or "")
        if lot_id not in first_by_lot:
            continue
        elapsed_hours = max(0.0, (moment - first_by_lot[lot_id]).total_seconds() / 3600)
        normalized.append({
            **row,
            "elapsed_hours": round(elapsed_hours, 2),
            "elapsed_12h_bucket": int(round(elapsed_hours / 12) * 12),
            "comparison_group": row.get("variety_summary") or row.get("lot_name") or "Unclassified wine",
            "series_name": f"{row.get('vintage_year')} · {row.get('lot_code') or lot_id}",
        })
    return normalized


def _fermentation_vintage_overlay(year: int) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT se.vintage_year,w.id wine_lot_id,w.code lot_code,w.name lot_name,w.variety_summary,"
        "o.observed_at,o.temp_c,o.density_sg,o.brix,o.ph "
        "FROM fermentation_observations o JOIN wine_lots w ON w.id=o.wine_lot_id AND w.estate_id=o.estate_id "
        "JOIN seasons se ON se.id=w.season_id AND se.estate_id=w.estate_id "
        "WHERE o.estate_id=%s AND se.vintage_year BETWEEN %s AND %s ORDER BY se.vintage_year,w.code,o.observed_at",
        (estate_id(), max(2023, year - 4), year),
    )
    return normalize_fermentation_overlay_rows(rows)


def _chemistry_vintage_overlay(year: int, paired_results: list[dict[str, Any]], current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for vintage_year in range(max(2023, year - 4), year + 1):
        rows = current_rows if vintage_year == year else _enology_test_series(vintage_year, paired_results)
        for row in rows:
            lab_date = row.get("lab_date")
            if isinstance(lab_date, (date, datetime)):
                calendar_day = lab_date.strftime("%m-%d")
            else:
                try:
                    calendar_day = date.fromisoformat(str(lab_date)[:10]).strftime("%m-%d")
                except ValueError:
                    continue
            variety = str(row.get("variety_name") or "").strip()
            block = str(row.get("block_code") or "").strip()
            comparison_series = " · ".join(value for value in (variety, block) if value) or row.get("wine_lot_code") or row.get("series_name") or row.get("sample_name")
            history.append({**row, "vintage_year": vintage_year, "calendar_day": calendar_day, "comparison_series": comparison_series})
    return history


def potential_alcohol_from_babo(babo: float | None, paired_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate potential alcohol from estate-specific paired historical results."""
    if babo is None:
        return {"status": "waiting_for_babo", "value_pct_vol": None, "confidence": "low", "message": "Record Babo before calculating potential alcohol."}
    factors = []
    for row in paired_results:
        source_babo, alcohol = row.get("babo"), row.get("potential_alcohol")
        if source_babo not in (None, 0, "") and alcohol not in (None, ""):
            factor = float(alcohol) / float(source_babo)
            if 0.4 <= factor <= 0.9:
                factors.append(factor)
    if not factors:
        return {"status": "insufficient_data", "value_pct_vol": None, "confidence": "low", "message": "No paired estate Babo/potential-alcohol results are available; obtain or approve a calculation rule."}
    factor = median(factors)
    return {"status": "calculated", "value_pct_vol": round(float(babo) * factor, 2), "factor": round(factor, 5), "evidence_count": len(factors), "confidence": "medium" if len(factors) >= 3 else "low", "model_version": "estate-babo-alcohol-v1", "message": "Calculated from the median ratio in paired estate laboratory results; not a separately measured value."}


def enology_testing_pipeline(stage: str) -> list[dict[str, Any]]:
    """Return the minimum stage-specific evidence gates discussed for 2026."""
    stage = str(stage or "pre-harvest").casefold()
    if stage == "pre-harvest":
        return [
            {"code": "ph", "method": "measure", "why": "Acidity and maturity context"},
            {"code": "total_acidity", "method": "measure", "why": "Maturity and balance context"},
            {"code": "babo", "method": "measure", "why": "Sugar maturity and calculation input"},
            {"code": "potential_alcohol", "method": "calculate_from_babo", "why": "Derived estimate with disclosed estate factor"},
            {"code": "potassium", "method": "measure", "why": "Must chemistry and pH-stability context"},
        ]
    if stage in {"must", "pre-fermentation"}:
        return enology_testing_pipeline("pre-harvest") + [{"code": "yan", "method": "measure", "why": "Required before nutrient correction or inoculation decisions"}]
    if stage == "fermentation":
        return [{"code": code, "method": "measure_each_check", "why": why} for code, why in (("temperature", "Yeast conditions"), ("density_sg", "Fermentation trajectory"), ("brix", "Sugar trend"), ("ph", "Acid stability"))]
    return [
        {"code": "density_sg", "method": "measure_until_stable", "why": "Confirm completion before the next cellar step"},
        {"code": "residual_sugar", "method": "measure", "why": "Confirm dryness rather than relying on density alone"},
        {"code": "ph", "method": "measure", "why": "Post-fermentation stability context"},
        {"code": "total_acidity", "method": "measure", "why": "Post-fermentation balance context"},
        {"code": "volatile_acidity", "method": "measure", "why": "Fermentation health and spoilage-risk context"},
        {"code": "malic_acid", "method": "measure", "why": "Track malolactic conversion when applicable"},
        {"code": "lactic_acid", "method": "measure", "why": "Interpret malolactic progress with malic acid"},
        {"code": "free_so2", "method": "measure", "why": "Protection decision evidence after fermentation"},
        {"code": "total_so2", "method": "measure", "why": "Total sulfur dioxide control and legal context"},
    ]


def _paired_babo_alcohol_results() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT s.id,MAX(CASE WHEN r.analyte_code='babo' THEN r.numeric_value END) babo,"
        "MAX(CASE WHEN r.analyte_code IN ('potential_alcohol','potential_alc') THEN r.numeric_value END) potential_alcohol "
        "FROM lab_samples s JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s AND s.needs_review=0 "
        "GROUP BY s.id HAVING babo IS NOT NULL AND potential_alcohol IS NOT NULL", (estate_id(),))
    return rows


def fermentation_outlook(readings: list[dict[str, Any]], now: datetime | None = None, stage: str | None = None) -> dict[str, Any]:
    """Estimate a density trajectory without turning it into an automatic cellar instruction."""
    valid = []
    for row in readings:
        value = row.get("density_sg")
        stamp = row.get("observed_at")
        if value in (None, "") or not stamp:
            continue
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        valid.append((stamp, float(value)))
    valid.sort()
    result = {
        "model_version": MODEL_VERSION,
        "target_dry_sg": TARGET_DRY_SG,
        "reading_count": len(valid),
        "requires_enologist_review": True,
        "is_automatic_instruction": False,
    }
    normalized_stage = str(stage or "").strip().casefold()
    if normalized_stage in {"aging", "bottled", "closed"}:
        return {
            **result,
            "status": "not_applicable",
            "confidence": "not_applicable",
            "requires_enologist_review": False,
            "message": f"No active fermentation forecast: this lot is recorded as {normalized_stage}. Historical readings remain available for traceability.",
        }
    if len(valid) < 2:
        return {**result, "status": "insufficient_data", "confidence": "low", "message": "Record at least two dated density readings to estimate a trajectory."}
    first_at, first_sg = valid[0]
    last_at, last_sg = valid[-1]
    elapsed_days = (last_at - first_at).total_seconds() / 86400
    if elapsed_days <= 0:
        return {**result, "status": "insufficient_data", "confidence": "low", "message": "Density readings need different timestamps."}
    slope = (last_sg - first_sg) / elapsed_days
    recent_age_h = max(0.0, (((now or datetime.utcnow()) - last_at).total_seconds() / 3600))
    if slope >= -0.0005:
        return {**result, "status": "stalled_review", "confidence": "medium" if len(valid) >= 3 else "low", "density_change_per_day": round(slope, 5), "message": "Density is not falling enough to project completion. Verify the reading and review yeast health, temperature and YAN evidence with the enologist."}
    days = max(0.0, (last_sg - TARGET_DRY_SG) / -slope)
    return {
        **result,
        "status": "dryness_reached_or_near" if last_sg <= TARGET_DRY_SG else "active_projection",
        "confidence": "medium" if len(valid) >= 3 and recent_age_h <= 48 else "low",
        "density_change_per_day": round(slope, 5),
        "estimated_days_to_dry": round(days, 1),
        "estimated_dry_at": datetime.fromtimestamp((last_at.replace(tzinfo=timezone.utc) if last_at.tzinfo is None else last_at).timestamp() + days * 86400, timezone.utc).isoformat(),
        "message": "Trend estimate from recorded density only; confirm sampling, temperature, sensory condition and the next action with the enologist.",
    }


def additive_volume_projections(lot: dict[str, Any], catalog: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project supported volume-based quantities without inventing product rules."""
    color = str(lot.get("wine_color") or "").casefold()
    volume_l = float(lot.get("volume_l") or lot.get("initial_l") or 0)
    output = []
    for item in catalog:
        if str(item.get("wine_color") or "any").casefold() not in {"any", color}:
            continue
        rate = item.get("proposed_rate")
        rate_unit = str(item.get("proposed_rate_unit") or "")
        quantity = round(volume_l / 100 * float(rate), 2) if volume_l and rate not in (None, "") and rate_unit.casefold() == "g/hl" else None
        matching = [event for event in additions if event.get("additive_id") == item.get("id") or str(event.get("additive_name") or "").casefold() == str(item.get("name") or "").casefold()]
        state = "applied" if any(event.get("event_status") == "applied" for event in matching) else "approved" if any(event.get("event_status") == "approved" for event in matching) else "planned" if matching else "review_required"
        reason = "Volume projection from the recorded lot volume and meeting rate; confirm the current technical sheet and lot condition."
        if quantity is None:
            reason = "No quantity projected because an exact rate or supported unit conversion has not been approved."
        if item.get("additive_type") == "nutrient":
            quantity = None
            reason = "Measured YAN/APA and a verified product-specific conversion are required before projecting nutrient quantity."
        output.append({**item, "lot_volume_l": volume_l or None, "projected_quantity": quantity, "projected_unit": "g" if quantity is not None else None, "projection_status": "calculated" if quantity is not None else "waiting_for_rule", "event_state": state, "projection_note": reason, "requires_enologist_approval": True})
    return output


def winemaking_workflow(lot: dict[str, Any], readings: list[dict[str, Any]], additions: list[dict[str, Any]], stage_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    color = str(lot.get("wine_color") or "").casefold()
    explicit = {event.get("stage_code"): event for event in stage_events}
    outlook = fermentation_outlook(readings)
    applied_types = {str(event.get("additive_type") or "").casefold() for event in additions if event.get("event_status") == "applied"}
    workflow = []
    for definition in WINEMAKING_STAGES:
        if definition["applies_to"] not in {"any", color}:
            continue
        event = explicit.get(definition["code"]) or {}
        status = event.get("stage_status") or "not_started"
        evidence = "Awaiting an enologist stage update."
        if definition["code"] == "intake_traceability":
            status = event.get("stage_status") or ("ready" if lot.get("container_code") and (lot.get("volume_l") or lot.get("initial_l")) else "blocked")
            evidence = "Lot volume and vessel are recorded." if status == "ready" else "Record the receiving vessel and lot volume."
        elif definition["code"] == "must_analysis":
            status = event.get("stage_status") or ("ready" if lot.get("yan_mg_l") is not None else "blocked")
            evidence = f"YAN/APA {float(lot['yan_mg_l']):g} mg/L recorded; review the complete must panel." if lot.get("yan_mg_l") is not None else "YAN/APA is missing; nutrient and inoculation decisions remain blocked."
        elif definition["code"] in {"yeast_nutrient_plan", "inoculation"}:
            status = event.get("stage_status") or ("ready" if lot.get("yan_mg_l") is not None else "blocked")
            evidence = "At least one yeast addition is applied." if "yeast" in applied_types else "Exact products, product lots and approved quantities are not fully applied."
        elif definition["code"] == "fermentation_monitoring":
            status = event.get("stage_status") or ("in_progress" if readings else "not_started")
            evidence = outlook.get("message")
        elif definition["code"] == "red_pre_press":
            days = outlook.get("estimated_days_to_dry")
            status = event.get("stage_status") or ("ready" if days is not None and days <= 2 else "blocked")
            evidence = "Density trend is within the projected final two days; enologist confirmation is still required." if status == "ready" else "Waiting for a supported final-two-day density projection and target press confirmation."
        elif definition["code"] in {"pressing_transfer", "post_fermentation"}:
            status = event.get("stage_status") or ("ready" if outlook.get("status") == "dryness_reached_or_near" else "blocked")
            evidence = "Density is at or near the working dry threshold; verify stability and sensory condition." if status == "ready" else "Completion evidence is not yet sufficient for this gate."
        workflow.append({**definition, **event, "stage_status": status, "evidence": evidence, "source_reference": WINEMAKING_SOURCE})
    return workflow


def _lot_process(row: dict[str, Any], readings: list[dict[str, Any]], additions: list[dict[str, Any]], stage_events: list[dict[str, Any]], catalog: list[dict[str, Any]], products: list[dict[str, Any]] | None = None, protocols: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    color = str(row.get("wine_color") or "").casefold()
    volume_l = float(row.get("volume_l") or row.get("initial_l") or 0)
    applied_types = {str(item.get("additive_type") or "").casefold() for item in additions if item.get("event_status") == "applied"}
    planned_types = {str(item.get("additive_type") or "").casefold() for item in additions if item.get("event_status") in {"planned", "approved"}}
    checks = []
    yan = row.get("yan_mg_l")
    if yan is None:
        checks.append({"code": "yan", "state": "blocked", "label": "Measure YAN before inoculation or nutrient correction", "detail": "The meeting discussed 150 mg/L as a benchmark; the actual target and nutrient conversion require enologist approval."})
    else:
        deficit = max(0.0, float(row.get("yan_target_mg_l") or 150) - float(yan))
        checks.append({"code": "yan", "state": "review" if deficit else "ready", "label": f"YAN {float(yan):g} mg/L", "detail": f"Measured deficit to the working benchmark: {deficit:g} mg/L. No nutrient quantity is inferred without a verified product rule."})
    if color == "white":
        checks.append({"code": "press_enzyme", "state": "done" if "enzyme" in applied_types else "planned" if "enzyme" in planned_types else "review", "label": "White pressing enzyme", "detail": "Use at the first press step; exact product and rate remain to be approved."})
        yeast_qty = round(volume_l / 100 * 30, 1) if volume_l else None
        checks.append({"code": "yeast", "state": "done" if "yeast" in applied_types else "planned" if "yeast" in planned_types else "review", "label": "Proposed Zymaflor Alpha inoculation", "detail": f"Meeting proposal: 30 g/hL{f' = {yeast_qty:g} g for {volume_l:g} L' if yeast_qty is not None else ''}; confirm technical sheet, fruit and lot before approval."})
    if color == "red":
        checks.append({"code": "crush_tannin", "state": "done" if "tannin" in applied_types else "planned" if "tannin" in planned_types else "review", "label": "Crushing tannin for color stability", "detail": "Exact product and dose were not specified; excessive tannin was explicitly identified as a risk."})
        enzyme_qty = round(volume_l / 100, 2) if volume_l else None
        checks.append({"code": "red_enzyme", "state": "done" if "enzyme" in applied_types else "planned" if "enzyme" in planned_types else "review", "label": "Red pre-press enzyme", "detail": f"Meeting proposal: final two fermentation days at 1 g/hL{f' = {enzyme_qty:g} g for {volume_l:g} L' if enzyme_qty is not None else ''}; target press time and approval required."})
        checks.append({"code": "post_tannin", "state": "review", "label": "Optional post-press tannin review", "detail": "Consider only after pressing/fermentation based on wine condition; no automatic dose."})
    return {**row, "readings": readings, "additions": additions, "checks": checks, "prediction": fermentation_outlook(readings, stage=row.get("stage")), "workflow": winemaking_workflow(row, readings, additions, stage_events), "additive_projections": additive_volume_projections(row, catalog, additions), "product_suggestions": suggest_products(row, products or []), "additive_prediction_pipeline": additive_prediction_pipeline(row, protocols or [], readings, additions, products=products or [])}


@router.get("/api/v1/enology/process", dependencies=[Depends(authorize)])
def enology_process_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=2023)) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,w.volume_l,w.fruit_kg,w.initial_l,w.variety_summary,w.started_at,c.code container_code,"
        "p.wine_color,p.target_style,p.target_press_at,p.yan_mg_l,p.yan_sampled_at,COALESCE(p.yan_target_mg_l,150) yan_target_mg_l,p.potential_alcohol_pct,p.must_turbidity_ntu,p.fruit_condition,p.laccase_u_ml,p.anthocyanin_tannin_ratio,p.inoculated_at,p.planned_filtration_at,p.approved_yeast,p.process_status,p.approved_by,p.approved_at,p.notes "
        "FROM wine_lots w LEFT JOIN cellar_containers c ON c.id=w.current_container_id LEFT JOIN enology_process_profiles p ON p.wine_lot_id=w.id AND p.estate_id=w.estate_id "
        "WHERE w.estate_id=%s AND w.season_id=%s ORDER BY w.started_at,w.code", (estate_id(), season.get("id", "")))
    readings = fetch_all("SELECT id,wine_lot_id,observed_at,temp_c,density_sg,brix,ph,sensory_observation,next_check_at FROM fermentation_observations WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE season_id=%s) ORDER BY observed_at", (estate_id(), season.get("id", ""))) if season else []
    additions = fetch_all("SELECT * FROM enology_addition_events WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE season_id=%s) ORDER BY COALESCE(applied_at,scheduled_at,created_at) DESC", (estate_id(), season.get("id", ""))) if season else []
    stage_events = fetch_all("SELECT * FROM enology_stage_events WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE season_id=%s) ORDER BY updated_at", (estate_id(), season.get("id", ""))) if season else []
    catalog = fetch_all("SELECT id,name,additive_type,wine_color,process_stage,proposed_rate,proposed_rate_unit,timing_rule,purpose,source_reference,approval_required FROM enology_additive_catalog WHERE estate_id=%s AND active=1 ORDER BY additive_type,name", (estate_id(),))
    products = catalog_rows()
    protocols = protocol_rows()
    catalog_sync = fetch_one("SELECT status,source_rows,imported_rows,failed_ranges,started_at,completed_at FROM enology_product_catalog_sync_runs ORDER BY started_at DESC LIMIT 1") or {}
    requests = fetch_all(
        "SELECT r.*,v.name variety_name,b.code block_code,s.sample_name result_sample_name,s.lab_date result_date "
        "FROM enology_test_requests r LEFT JOIN grape_varieties v ON v.id=r.variety_id LEFT JOIN vineyard_blocks b ON b.id=r.block_id "
        "LEFT JOIN lab_samples s ON s.id=r.result_sample_id WHERE r.estate_id=%s AND r.season_id=%s ORDER BY r.due_at",
        (estate_id(), season.get("id", "")),
    ) if season else []
    paired = _paired_babo_alcohol_results()
    test_series = _enology_test_series(year, paired)
    for request in requests:
        request["pipeline"] = enology_testing_pipeline(request.get("process_stage"))
        request["potential_alcohol_model"] = potential_alcohol_from_babo(None, paired)
    lot_processes = [_lot_process(row, [r for r in readings if r.get("wine_lot_id") == row["id"]], [a for a in additions if a.get("wine_lot_id") == row["id"]], [event for event in stage_events if event.get("wine_lot_id") == row["id"]], catalog, products, protocols) for row in lots]
    product_classes = sorted({str(product.get("product_class") or "other") for product in products})
    return json_ready({"year": year, "model_version": MODEL_VERSION, "source_reference": WINEMAKING_SOURCE, "lots": lot_processes, "catalog": catalog, "product_catalog": products, "product_protocols": protocols, "product_catalog_summary": {"products": len(products), "laffort_products": sum(1 for product in products if product.get("manufacturer") == "LAFFORT"), "technical_sheets": sum(1 for product in products if product.get("pds_url")), "projection_ready": sum(1 for product in products if product.get("dose_verified")), "verified_protocols": len(protocols), "classes": product_classes, "latest_sync": catalog_sync}, "test_requests": requests, "test_series": test_series, "chemistry_vintage_overlay": _chemistry_vintage_overlay(year, paired, test_series), "fermentation_vintage_overlay": _fermentation_vintage_overlay(year), "comparison_window": {"first_year": max(2023, year - 4), "last_year": year, "fermentation_alignment": "12-hour buckets from each lot's first recorded fermentation observation", "chemistry_alignment": "calendar month and day within each vintage"}, "analyte_definitions": ENOLOGY_ANALYTES, "testing_pipeline": {stage: enology_testing_pipeline(stage) for stage in ("pre-harvest","pre-fermentation","fermentation","post-fermentation")}, "potential_alcohol_model": potential_alcohol_from_babo(None, paired), "policy": "Product matches and projections are decision support only. Current product data sheets, measured chemistry, applicable rules and enologist approval govern every addition."})


@router.put("/api/v1/enology/test-requests/{request_id}", dependencies=[Depends(authorize_write)])
def update_test_request(request_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM enology_test_requests WHERE id=%s AND estate_id=%s", (request_id, estate_id()))
    if not row:
        raise HTTPException(404, "Test request not found")
    status = str(payload.get("status") or row.get("status") or "scheduled").casefold()
    if status not in {"scheduled", "sampled", "result_received", "reviewed", "cancelled"}:
        raise HTTPException(422, "Choose a supported test status")
    sample_id = payload.get("result_sample_id") or row.get("result_sample_id")
    if sample_id and not fetch_one("SELECT id FROM lab_samples WHERE id=%s AND estate_id=%s", (sample_id, estate_id())):
        raise HTTPException(422, "Linked laboratory sample was not found")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("UPDATE enology_test_requests SET status=%s,result_sample_id=%s,variety_id=COALESCE(%s,variety_id),block_id=COALESCE(%s,block_id),notes=CONCAT_WS(' · ',NULLIF(notes,''),NULLIF(%s,'')) WHERE id=%s AND estate_id=%s", (status,sample_id,payload.get("variety_id") or None,payload.get("block_id") or None,payload.get("notes") or None,request_id,estate_id()))
        audit(cursor,"update","enology_test_request",request_id,{"status":status,"result_sample_id":sample_id},actor)
    return {"saved": True, "id": request_id, "status": status}


@router.put("/api/v1/enology/process/lots/{wine_lot_id}", dependencies=[Depends(authorize_write)])
def save_process_profile(wine_lot_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    lot = fetch_one("SELECT id FROM wine_lots WHERE id=%s AND estate_id=%s", (wine_lot_id, estate_id()))
    if not lot:
        raise HTTPException(404, "Wine lot not found")
    color = str(payload.get("wine_color") or "").casefold()
    if color not in {"red", "white", "rose"}:
        raise HTTPException(422, "Choose red, white or rosé")
    status = str(payload.get("process_status") or "draft").casefold()
    if status not in {"draft", "approved", "active", "complete", "held"}:
        raise HTTPException(422, "Choose a supported process status")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    approved_by = approved_at = None
    if status in {"approved", "active"}:
        require_discipline_approval(request, "enology")
        approved_by, approved_at = actor, datetime.now()
    yan = payload.get("yan_mg_l")
    if yan not in (None, "") and not 0 <= float(yan) <= 1000:
        raise HTTPException(422, "YAN must be between 0 and 1000 mg/L")
    target = float(payload.get("yan_target_mg_l") or 150)
    fruit_condition = str(payload.get("fruit_condition") or "unknown").casefold()
    if fruit_condition not in {"unknown", "sound", "botrytis", "infected"}:
        raise HTTPException(422, "Choose a supported fruit condition")
    bounded = {"potential_alcohol_pct": (0, 30), "must_turbidity_ntu": (0, 100000), "laccase_u_ml": (0, 100000), "anthocyanin_tannin_ratio": (0, 1000)}
    metrics: dict[str, float | None] = {}
    for field, (minimum, maximum) in bounded.items():
        value = payload.get(field)
        metrics[field] = None if value in (None, "") else float(value)
        if metrics[field] is not None and not minimum <= metrics[field] <= maximum:
            raise HTTPException(422, f"{field.replace('_', ' ')} must be between {minimum} and {maximum}")
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_process_profiles (id,estate_id,wine_lot_id,wine_color,target_style,target_press_at,yan_mg_l,yan_sampled_at,yan_target_mg_l,potential_alcohol_pct,must_turbidity_ntu,fruit_condition,laccase_u_ml,anthocyanin_tannin_ratio,inoculated_at,planned_filtration_at,approved_yeast,process_status,approved_by,approved_at,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE wine_color=VALUES(wine_color),target_style=VALUES(target_style),target_press_at=VALUES(target_press_at),yan_mg_l=VALUES(yan_mg_l),yan_sampled_at=VALUES(yan_sampled_at),yan_target_mg_l=VALUES(yan_target_mg_l),potential_alcohol_pct=VALUES(potential_alcohol_pct),must_turbidity_ntu=VALUES(must_turbidity_ntu),fruit_condition=VALUES(fruit_condition),laccase_u_ml=VALUES(laccase_u_ml),anthocyanin_tannin_ratio=VALUES(anthocyanin_tannin_ratio),inoculated_at=VALUES(inoculated_at),planned_filtration_at=VALUES(planned_filtration_at),approved_yeast=VALUES(approved_yeast),process_status=VALUES(process_status),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),notes=VALUES(notes)", (new_id(),estate_id(),wine_lot_id,color,payload.get("target_style") or None,payload.get("target_press_at") or None,None if yan in (None, "") else float(yan),payload.get("yan_sampled_at") or None,target,metrics["potential_alcohol_pct"],metrics["must_turbidity_ntu"],fruit_condition,metrics["laccase_u_ml"],metrics["anthocyanin_tannin_ratio"],payload.get("inoculated_at") or None,payload.get("planned_filtration_at") or None,payload.get("approved_yeast") or None,status,approved_by,approved_at,payload.get("notes") or None))
        audit(cursor,"update","enology_process_profile",wine_lot_id,{"wine_color":color,"yan_mg_l":yan,"status":status},actor)
    return {"saved": True, "wine_lot_id": wine_lot_id}


@router.post("/api/v1/enology/process-profiles", dependencies=[Depends(authorize_write)])
def create_or_update_process_profile(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip()
    if not wine_lot_id:
        raise HTTPException(422, "Choose a wine lot")
    return save_process_profile(wine_lot_id, request, payload)


@router.put("/api/v1/enology/process/lots/{wine_lot_id}/stages/{stage_code}", dependencies=[Depends(authorize_write)])
def save_winemaking_stage(wine_lot_id: str, stage_code: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    lot = fetch_one("SELECT id FROM wine_lots WHERE id=%s AND estate_id=%s", (wine_lot_id, estate_id()))
    if not lot:
        raise HTTPException(404, "Wine lot not found")
    if stage_code not in {stage["code"] for stage in WINEMAKING_STAGES}:
        raise HTTPException(422, "Choose a supported winemaking stage")
    status = str(payload.get("stage_status") or "in_progress").casefold()
    if status not in {"not_started", "ready", "in_progress", "blocked", "complete", "held", "skipped"}:
        raise HTTPException(422, "Choose a supported stage status")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    approved_by = None
    if status in {"complete", "skipped"}:
        require_discipline_approval(request, "enology")
        approved_by = actor
    completed_at = payload.get("completed_at") or (datetime.now() if status == "complete" else None)
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_stage_events (id,estate_id,wine_lot_id,stage_code,stage_status,planned_at,completed_at,notes,approved_by,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE stage_status=VALUES(stage_status),planned_at=VALUES(planned_at),completed_at=VALUES(completed_at),notes=VALUES(notes),approved_by=VALUES(approved_by),updated_by=VALUES(updated_by)", (new_id(),estate_id(),wine_lot_id,stage_code,status,payload.get("planned_at") or None,completed_at,payload.get("notes") or None,approved_by,actor))
        audit(cursor,"update","enology_stage",f"{wine_lot_id}:{stage_code}",{"status":status,"completed_at":completed_at},actor)
    return {"saved": True, "wine_lot_id": wine_lot_id, "stage_code": stage_code, "stage_status": status}


@router.post("/api/v1/enology/additions", dependencies=[Depends(authorize_write)])
def save_addition(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    lot_id = str(payload.get("wine_lot_id") or "")
    lot = fetch_one("SELECT id,season_id FROM wine_lots WHERE id=%s AND estate_id=%s", (lot_id, estate_id()))
    if not lot:
        raise HTTPException(422, "Choose a wine lot")
    additive_type = str(payload.get("additive_type") or "").casefold()
    if additive_type not in {"yeast", "enzyme", "nutrient", "tannin", "other"}:
        raise HTTPException(422, "Choose an additive type")
    status = str(payload.get("event_status") or "planned").casefold()
    if status not in {"planned", "approved", "applied", "cancelled"}:
        raise HTTPException(422, "Choose a supported addition status")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    approved_by = approved_at = None
    if status in {"approved", "applied"}:
        require_discipline_approval(request, "enology")
        approved_by, approved_at = actor, datetime.now()
    additive_name = str(payload.get("additive_name") or "").strip()
    if not additive_name:
        raise HTTPException(422, "Enter the exact additive product name")
    quantity = payload.get("quantity")
    if quantity not in (None, "") and float(quantity) <= 0:
        raise HTTPException(422, "Addition quantity must be greater than zero")
    if status == "applied" and (quantity in (None, "") or not payload.get("unit") or not payload.get("product_lot") or not payload.get("applied_at")):
        raise HTTPException(422, "Applied additions require applied time, quantity, unit and product lot")
    record_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_addition_events (id,estate_id,wine_lot_id,additive_id,additive_name,additive_type,event_status,scheduled_at,applied_at,quantity,unit,product_lot,reason_text,approved_by,approved_at,recorded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (record_id,estate_id(),lot_id,payload.get("additive_id") or None,additive_name,additive_type,status,payload.get("scheduled_at") or None,payload.get("applied_at") or None,None if quantity in (None, "") else float(quantity),payload.get("unit") or None,payload.get("product_lot") or None,payload.get("reason_text") or None,approved_by,approved_at,actor))
        cursor.execute("INSERT INTO cellar_operations (id,estate_id,season_id,wine_lot_id,operation_at,operation_type,amount,unit,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (new_id(),estate_id(),lot["season_id"],lot_id,payload.get("applied_at") or payload.get("scheduled_at") or datetime.now(),f"{status} {additive_type}",None if quantity in (None, "") else float(quantity),payload.get("unit") or None,f"{additive_name}; product lot {payload.get('product_lot') or 'not yet recorded'}; {payload.get('reason_text') or ''}".strip()))
        audit(cursor,"create","enology_addition",record_id,{"wine_lot_id":lot_id,"type":additive_type,"status":status},actor)
    return {"saved": True, "id": record_id}
