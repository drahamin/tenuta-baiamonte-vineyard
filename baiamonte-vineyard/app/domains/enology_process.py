"""Traceable enology process plans and evidence-bounded fermentation outlooks."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import threading
import time
import unicodedata
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..access import authorize, authorize_write
from ..db import fetch_all, fetch_one, transaction
from ..enology_measurements import normalize_enology_measurement
from ..service import audit, estate_id, json_ready, new_id
from .laffort_catalog import (
    additive_prediction_pipeline,
    catalog_rows,
    lab_evidence_rows,
    lot_lab_evidence,
    lot_with_lab_measurements,
    protocol_rows,
    suggest_products,
)


router = APIRouter(tags=["enology-process"])
MODEL_VERSION = "fermentation-trend-v1"
TARGET_DRY_SG = 0.995
WINEMAKING_SOURCE = "PLAUD 2026-09-02 · 09-02 Vineyard Operations, Winemaking Strategy, and Administrative Coordination Meeting"
_DASHBOARD_CACHE_TTL_SECONDS = 30.0
_dashboard_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_dashboard_cache_lock = threading.Lock()


def _invalidate_dashboard_cache() -> None:
    with _dashboard_cache_lock:
        _dashboard_cache.clear()

WINEMAKING_STAGES = (
    {"code": "intake_traceability", "name": "1. Fruit reception & lot identity", "applies_to": "any", "gate": "Confirm harvest source, variety, weight, fruit condition, vessel and received time before processing."},
    {"code": "crush_press_preparation", "name": "2. Crush / destem / press preparation", "applies_to": "any", "gate": "Choose the red or white route, prepare the receiving vessel and record the first physical cellar operation."},
    {"code": "must_analysis", "name": "3. Must analysis before fermentation", "applies_to": "any", "gate": "Review pH, total acidity, Babo, calculated potential alcohol, potassium and YAN/APA before nutrient or inoculation decisions."},
    {"code": "yeast_nutrient_plan", "name": "4. Yeast, enzyme, tannin & nutrient plan", "applies_to": "any", "gate": "Select the purpose-specific product protocol, confirm the quantity from the recorded batch basis, and record the product lot. Nutrient quantity uses measured YAN and a verified product conversion."},
    {"code": "inoculation", "name": "5. Inoculation", "applies_to": "any", "gate": "Record yeast preparation, exact quantity, product lot and time. The authenticated enology operator's entry is the cellar authorization and audit record."},
    {"code": "fermentation_monitoring", "name": "6. Fermentation monitoring", "applies_to": "any", "gate": "Trend temperature, specific gravity, Brix and pH; record sensory condition and next check. Flat density requires review."},
    {"code": "red_pre_press", "name": "7. Red: final-two-day pre-press step", "applies_to": "red", "gate": "When the enologist confirms the final two fermentation days, review the proposed red enzyme at 1 g/hL and the target press time."},
    {"code": "pressing_transfer", "name": "8. Pressing, separation & transfer", "applies_to": "any", "gate": "Record press/transfer time, destination vessel, recovered volume, lees/solids handling and any addition."},
    {"code": "post_fermentation", "name": "9. Post-fermentation stability", "applies_to": "any", "gate": "Confirm stable completion evidence, pH, total acidity and sensory condition before stabilization or aging decisions."},
    {"code": "aging_release", "name": "10. Aging plan & release from active winemaking", "applies_to": "any", "gate": "Record the aging vessel and review cadence. Use an optional post-press tannin only from a purpose-specific bench trial with the selected dose recorded."},
)

ENOLOGY_ANALYTES = {
    "ph": {"name": "pH", "default_unit": "pH", "aliases": {"ph"}},
    "total_acidity": {"name": "Total acidity / Acidità totale", "default_unit": "", "aliases": {"total_acidity", "total_acidity_tartaric", "total_acid", "titratable_acidity", "ta", "acidita_totale"}},
    "babo": {"name": "Babo", "default_unit": "°Babo", "aliases": {"babo", "degrees_babo", "grado_babo", "gradi_babo"}},
    "brix": {"name": "Brix", "default_unit": "°Bx", "aliases": {"brix", "degrees_brix", "grado_brix", "gradi_brix"}},
    "potential_alcohol": {"name": "Calculated potential alcohol / Alcol potenziale calcolato", "default_unit": "% vol", "aliases": {"potential_alcohol", "potential_alc", "alcohol_potential", "alcol_potenziale", "alcol_potenziale_calcolato"}},
    "potassium": {"name": "Potassium / Potassio", "default_unit": "", "aliases": {"potassium", "potassio", "k"}},
    "yan": {"name": "Yeast assimilable nitrogen (YAN / APA)", "default_unit": "mg/L", "aliases": {"yan", "yeast_assimilable_nitrogen", "azoto_prontamente_assimilabile", "azoto_prontamente_assimilabile_apa_yan", "apa"}},
    "actual_alcohol": {"name": "Alcohol / Alcol effettivo", "default_unit": "% vol", "aliases": {"actual_alcohol", "alcohol", "ethanol", "alcol", "alcol_effettivo"}},
    "residual_sugar": {"name": "Residual sugar / Zuccheri residui", "default_unit": "", "aliases": {"residual_sugar", "glucose_fructose", "glucose_and_fructose", "zuccheri_residui"}},
    "volatile_acidity": {"name": "Volatile acidity / Acidità volatile", "default_unit": "", "aliases": {"volatile_acidity", "volatile_acid", "va", "acidita_volatile"}},
    "malic_acid": {"name": "Malic acid / Acido malico", "default_unit": "", "aliases": {"malic_acid", "malate", "acido_malico"}},
    "lactic_acid": {"name": "Lactic acid / Acido lattico", "default_unit": "", "aliases": {"lactic_acid", "lactate", "acido_lattico"}},
    "free_so2": {"name": "Free sulfur dioxide / SO₂ libera", "default_unit": "mg/L", "aliases": {"free_so2", "so2_free", "free_sulfur_dioxide", "so2_libera"}},
    "total_so2": {"name": "Total sulfur dioxide / SO₂ totale", "default_unit": "mg/L", "aliases": {"total_so2", "so2_total", "total_sulfur_dioxide", "so2_totale"}},
    "turbidity": {"name": "Turbidity / Torbidità", "default_unit": "NTU", "aliases": {"turbidity", "ntu", "torbidita", "torbidita_ntu"}},
    "catechins": {"name": "Catechins / Catechine", "default_unit": "", "aliases": {"catechins", "catechin", "catechine"}},
    "dissolved_oxygen": {"name": "Dissolved oxygen / Ossigeno disciolto", "default_unit": "mg/L", "aliases": {"dissolved_oxygen", "oxygen_dissolved", "do", "ossigeno_disciolto"}},
    "tartaric_acid": {"name": "Tartaric acid / Acido tartarico", "default_unit": "g/L", "aliases": {"tartaric_acid", "acido_tartarico"}},
    "citric_acid": {"name": "Citric acid / Acido citrico", "default_unit": "g/L", "aliases": {"citric_acid", "acido_citrico"}},
    "ammonium_nitrogen": {"name": "Ammonium nitrogen / Azoto ammoniacale", "default_unit": "mg/L", "aliases": {"ammonium_nitrogen", "ammonia_nitrogen", "azoto_ammoniacale"}},
    "alpha_amino_nitrogen": {"name": "Alpha-amino nitrogen / Azoto alfa-amminico", "default_unit": "mg/L", "aliases": {"alpha_amino_nitrogen", "amino_nitrogen", "azoto_alfa_amminico", "pan"}},
    "calcium": {"name": "Calcium / Calcio", "default_unit": "mg/L", "aliases": {"calcium", "calcio", "ca"}},
    "copper": {"name": "Copper / Rame", "default_unit": "mg/L", "aliases": {"copper", "rame", "cu"}},
    "iron": {"name": "Iron / Ferro", "default_unit": "mg/L", "aliases": {"iron", "ferro", "fe"}},
    "acetaldehyde": {"name": "Acetaldehyde / Acetaldeide", "default_unit": "mg/L", "aliases": {"acetaldehyde", "acetaldeide", "ethanal"}},
    "color_intensity": {"name": "Color intensity / Intensità colorante", "default_unit": "AU", "aliases": {"color_intensity", "intensita_colorante", "colour_intensity"}},
    "color_hue": {"name": "Color hue / Tonalità", "default_unit": "ratio", "aliases": {"color_hue", "hue", "tonalita"}},
    "total_polyphenols": {"name": "Total polyphenols / Polifenoli totali", "default_unit": "index", "aliases": {"total_polyphenols", "polyphenols", "polifenoli_totali", "tpi", "ipt"}},
    "anthocyanins": {"name": "Anthocyanins / Antociani", "default_unit": "mg/L", "aliases": {"anthocyanins", "anthocyanin", "antociani"}},
    "carbon_dioxide": {"name": "Carbon dioxide / Anidride carbonica", "default_unit": "g/L", "aliases": {"carbon_dioxide", "co2", "anidride_carbonica"}},
    "brettanomyces": {"name": "Brettanomyces", "default_unit": "cells/mL", "aliases": {"brett", "brettanomyces", "brettanomyces_bruxellensis", "brettanomyces_count", "brettanomyces_qpcr"}},
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
        "(SELECT CONCAT('api/v1/attachments/',ea.id,'/file') FROM entity_attachments ea WHERE ea.estate_id=s.estate_id AND ea.entity_type='lab_sample' AND ea.entity_id=s.id ORDER BY ea.created_at DESC LIMIT 1) report_url,"
        "v.name variety_name,b.code block_code,w.code wine_lot_code,"
        "(SELECT GROUP_CONCAT(DISTINCT linked.code ORDER BY linked.code SEPARATOR ' + ') FROM lab_sample_wine_lots sl JOIN wine_lots linked ON linked.id=sl.wine_lot_id WHERE sl.sample_id=s.id) linked_wine_lot_codes,"
        "COALESCE(m.canonical_code,r.analyte_code) analyte_code,COALESCE(m.canonical_name,r.analyte_name) analyte_name,"
        "CASE WHEN r.numeric_value IS NULL THEN NULL ELSE r.numeric_value*COALESCE(m.conversion_multiplier,1) END numeric_value,COALESCE(m.canonical_unit,r.unit) unit,r.method,"
        "r.analyte_code reported_analyte_code,r.analyte_name reported_analyte_name,r.numeric_value reported_numeric_value,r.unit reported_unit "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN grape_varieties v ON v.id=s.variety_id "
        "LEFT JOIN vineyard_blocks b ON b.id=s.block_id LEFT JOIN wine_lots w ON w.id=s.wine_lot_id JOIN lab_results r ON r.sample_id=s.id "
        "LEFT JOIN enology_analyte_mappings m ON m.id=r.analyte_mapping_id AND m.estate_id=s.estate_id "
        "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date))=%s "
        "AND s.sample_type IN ('grape','must','wine') AND r.numeric_value IS NOT NULL ORDER BY s.lab_date,s.sample_name,r.analyte_code",
        (estate_id(), year),
    )
    chart_rows: list[dict[str, Any]] = []
    babo_by_sample: dict[str, dict[str, Any]] = {}
    potential_samples: set[str] = set()
    for row in rows:
        metric = canonical_enology_analyte(row.get("analyte_code"), row.get("analyte_name"), row.get("unit"))
        recognized = metric is not None
        if not metric:
            fallback_code = "_".join(str(row.get("analyte_code") or row.get("analyte_name") or "unmapped").strip().casefold().split())
            metric = {"code": fallback_code, "name": row.get("analyte_name") or fallback_code.replace("_", " ").title(), "unit": str(row.get("unit") or "unit not reported")}
        normalized = normalize_enology_measurement(metric["code"], row.get("numeric_value"), row.get("unit"))
        identity = row.get("wine_lot_code") or row.get("linked_wine_lot_codes") or row.get("variety_name") or row.get("block_code") or row.get("sample_name")
        item = {
            **row, "metric_code": metric["code"], "metric_name": metric["name"],
            "display_unit": normalized["unit"] if normalized["usable"] else metric["unit"],
            "series_name": identity, "value": normalized["value"] if normalized["usable"] else row.get("numeric_value"),
            "recognized": recognized, "routing_status": "routed" if recognized else "unmapped",
            "unit_valid": normalized["usable"], "validation_error": normalized["reason"], "calculated": False,
        }
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
        "o.observed_at,o.temp_c,o.density_sg,o.brix,o.babo,o.ph "
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
        return {"status": "insufficient_data", "value_pct_vol": None, "confidence": "low", "message": "No paired estate Babo/potential-alcohol results are available; obtain a laboratory result or configure a documented calculation rule."}
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
        return enology_testing_pipeline("pre-harvest") + [
            {"code": "yan", "method": "measure", "why": "Required before nutrient correction or inoculation decisions"},
            {"code": "turbidity", "method": "measure", "why": "Must clarification, solids and nutrient-context input"},
            {"code": "catechins", "method": "measure", "why": "White-must oxidation and clarification context when reported"},
            {"code": "ammonium_nitrogen", "method": "laboratory_component", "why": "Nitrogen-form context when the laboratory reports it"},
            {"code": "alpha_amino_nitrogen", "method": "laboratory_component", "why": "Nitrogen-form context when the laboratory reports it"},
        ]
    if stage == "fermentation":
        return [{"code": code, "method": "measure_each_check", "why": why} for code, why in (("temperature", "Yeast conditions"), ("density_sg", "Fermentation trajectory"), ("brix", "Sugar trend"), ("babo", "Sugar trend and progress"), ("ph", "Acid stability"), ("yan", "Nutrition decision evidence"), ("turbidity", "Solids and nutrient context"), ("volatile_acidity", "Fermentation health when laboratory-tested"))]
    return [
        {"code": "density_sg", "method": "measure_until_stable", "why": "Confirm completion before the next cellar step"},
        {"code": "actual_alcohol", "method": "measure", "why": "Confirm final alcohol rather than relying on potential alcohol"},
        {"code": "residual_sugar", "method": "measure", "why": "Confirm dryness rather than relying on density alone"},
        {"code": "ph", "method": "measure", "why": "Post-fermentation stability context"},
        {"code": "total_acidity", "method": "measure", "why": "Post-fermentation balance context"},
        {"code": "volatile_acidity", "method": "measure", "why": "Fermentation health and spoilage-risk context"},
        {"code": "malic_acid", "method": "measure", "why": "Track malolactic conversion when applicable"},
        {"code": "lactic_acid", "method": "measure", "why": "Interpret malolactic progress with malic acid"},
        {"code": "free_so2", "method": "measure", "why": "Protection decision evidence after fermentation"},
        {"code": "total_so2", "method": "measure", "why": "Total sulfur dioxide control and legal context"},
        {"code": "dissolved_oxygen", "method": "measure", "why": "Transfer, aging and packaging oxidation-risk context"},
        {"code": "tartaric_acid", "method": "measure_when_relevant", "why": "Acid and tartrate-stability context"},
        {"code": "citric_acid", "method": "measure_when_relevant", "why": "Acid profile and microbial-stability context"},
        {"code": "ammonium_nitrogen", "method": "retain", "why": "Retain reported nitrogen-form evidence"},
        {"code": "alpha_amino_nitrogen", "method": "retain", "why": "Retain reported nitrogen-form evidence"},
        {"code": "calcium", "method": "measure_when_relevant", "why": "Stability and precipitation context"},
        {"code": "copper", "method": "measure_when_relevant", "why": "Reduction and metal-stability context"},
        {"code": "iron", "method": "measure_when_relevant", "why": "Oxidation and metal-stability context"},
        {"code": "acetaldehyde", "method": "measure_when_relevant", "why": "Oxidation and sulfur-binding context"},
        {"code": "color_intensity", "method": "measure_when_relevant", "why": "Red-wine extraction and aging context"},
        {"code": "color_hue", "method": "measure_when_relevant", "why": "Red-wine oxidation and aging context"},
        {"code": "total_polyphenols", "method": "measure_when_relevant", "why": "Phenolic structure and extraction context"},
        {"code": "anthocyanins", "method": "measure_when_relevant", "why": "Red-wine color and extraction context"},
        {"code": "carbon_dioxide", "method": "measure_when_relevant", "why": "Dissolved gas and packaging context"},
        {"code": "brettanomyces", "method": "measure_when_risk_indicated", "why": "Laboratory-confirm spoilage risk before any targeted microbial-control protocol"},
    ]


def next_recommended_lab_tests(
    lot: dict[str, Any], lab_evidence: dict[str, Any], readings: list[dict[str, Any]], now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Prioritize the next exact-lot lab work from process stage, kinetics and result freshness."""
    now = (now or datetime.now()).replace(tzinfo=None)
    stage = str(lot.get("process_stage") or lot.get("stage") or "must").strip().casefold().replace(" ", "_")
    color = str(lot.get("wine_color") or "").strip().casefold()
    metrics = lab_evidence.get("metrics") or {}
    dated = sorted(
        [row for row in readings if row.get("observed_at")], key=lambda row: str(row.get("observed_at"))
    )
    babo_values = [float(row["babo"]) for row in dated if row.get("babo") is not None]
    density_values = [float(row["density_sg"]) for row in dated if row.get("density_sg") is not None]
    babo_start = babo_values[0] if babo_values else None
    babo_latest = babo_values[-1] if babo_values else None
    babo_progress = (babo_start - babo_latest) / babo_start * 100 if babo_start else None
    near_dry = bool(
        (babo_latest is not None and babo_latest <= 3)
        or (density_values and density_values[-1] <= 1.000)
        or (babo_progress is not None and babo_progress >= 80)
    )
    recommendations: dict[str, dict[str, Any]] = {}

    def add(code: str, *, due_hours: int, priority: str, reason: str, max_age_days: int = 0, method: str = "laboratory") -> None:
        reported_metric = metrics.get(code)
        invalid_metric = reported_metric if reported_metric and not reported_metric.get("decision_usable", True) else None
        metric = reported_metric
        if invalid_metric:
            metric = None
        age = metric.get("age_days") if metric else None
        if metric and (not max_age_days or age is None or int(age) <= max_age_days):
            return
        definition = ENOLOGY_ANALYTES.get(code, {"name": code.replace("_", " ").title(), "default_unit": ""})
        candidate = {
            "wine_lot_id": lot.get("id"), "wine_lot_code": lot.get("code"), "stage": stage,
            "analyte_code": code, "analyte_name": definition["name"], "expected_unit": definition.get("default_unit"),
            "method": method, "priority": priority, "due_at": now + timedelta(hours=due_hours),
            "timing": "now" if due_hours <= 0 else "within 12 hours" if due_hours <= 12 else "within 24 hours" if due_hours <= 24 else f"within {round(due_hours / 24)} days",
            "reason": reason, "result_state": "invalid_unit" if invalid_metric else "repeat_due" if metric else "missing",
            "latest_value": (metric or invalid_metric or {}).get("value"), "latest_unit": (metric or invalid_metric or {}).get("unit"),
            "latest_date": (metric or invalid_metric or {}).get("lab_date"), "age_days": age,
            "validation_error": (invalid_metric or {}).get("validation_error"),
        }
        existing = recommendations.get(code)
        rank = {"critical": 0, "high": 1, "normal": 2}
        if existing is None or (rank.get(priority, 9), candidate["due_at"]) < (rank.get(str(existing["priority"]), 9), existing["due_at"]):
            recommendations[code] = candidate

    early = stage in {"receiving", "intake", "must", "pre_fermentation", "pre-fermentation", "inoculation"}
    fermenting = stage in {"fermentation", "fermenting", "primary_fermentation"}
    pressing = stage in {"pressing", "pressed", "transfer", "racking"}
    post = stage in {"post_fermentation", "post-fermentation", "malo", "malolactic", "stabilization"}
    aging = stage == "aging"
    if early:
        for code, reason in (
            ("ph", "Set the acid and microbial-risk baseline before inoculation or correction."),
            ("total_acidity", "Interpret pH and balance before acid or deacidification decisions."),
            ("babo", "Establish fermentable-sugar maturity and the potential-alcohol calculation input."),
            ("potassium", "Assess pH and tartrate-stability context before correction."),
            ("yan", "Required before yeast-nutrition quantity and timing decisions."),
            ("turbidity", "NTU guides white-must settling, solids balance and nutrient context."),
        ):
            add(code, due_hours=0, priority="critical" if code in {"yan", "ph", "turbidity"} else "high", reason=reason, max_age_days=3)
        if color in {"white", "rose", "rosé"}:
            add("catechins", due_hours=0, priority="high", reason="Use the reported catechin test for white-must oxidation and clarification decisions.", max_age_days=3)
        add("potential_alcohol", due_hours=0, priority="high", reason="Calculate from the current Babo result with the disclosed estate factor; confirm by the laboratory when reported.", max_age_days=3, method="calculate_from_babo")
    if fermenting:
        add("ph", due_hours=12, priority="high", reason="Refresh acid and microbial-risk context during active fermentation.", max_age_days=3)
        add("total_acidity", due_hours=24, priority="normal", reason="Track balance through the active fermentation transition.", max_age_days=5)
        add("volatile_acidity", due_hours=24, priority="high", reason="Check fermentation health and emerging spoilage risk.", max_age_days=3)
        if babo_progress is None or babo_progress <= 45:
            add("yan", due_hours=0, priority="critical", reason="The nutrition window is active or cannot yet be placed; YAN/APA is required for the decision.", max_age_days=3)
            add("turbidity", due_hours=0, priority="high", reason="Use NTU with YAN and fermentation progress for the nutrient and solids decision.", max_age_days=3)
        if near_dry:
            add("residual_sugar", due_hours=12, priority="critical", reason="Babo or density is near the completion range; confirm dryness analytically.", max_age_days=1)
            add("actual_alcohol", due_hours=24, priority="high", reason="Confirm final alcohol as fermentation approaches completion.", max_age_days=2)
    if pressing:
        for code, reason in (
            ("ph", "Confirm post-press acid and stability context."),
            ("total_acidity", "Confirm post-press balance before the next cellar correction."),
            ("volatile_acidity", "Establish the post-press fermentation-health baseline."),
        ):
            add(code, due_hours=12, priority="high", reason=reason, max_age_days=2)
        if color in {"white", "rose", "rosé"}:
            add("turbidity", due_hours=0, priority="critical", reason="Measure post-press NTU before settling, clarification or enzyme decisions.", max_age_days=1)
            add("catechins", due_hours=12, priority="high", reason="Recheck oxidation and clarification context on the pressed white fraction.", max_age_days=2)
    if post or (fermenting and near_dry):
        add("residual_sugar", due_hours=12, priority="critical", reason="Confirm dryness before stabilization, transfer or aging decisions.")
        add("actual_alcohol", due_hours=24, priority="high", reason="Record finished alcohol for the completed fermentation profile.")
        add("ph", due_hours=24, priority="high", reason="Set the post-fermentation stability baseline.", max_age_days=3)
        add("total_acidity", due_hours=24, priority="normal", reason="Set the post-fermentation balance baseline.", max_age_days=3)
        add("volatile_acidity", due_hours=24, priority="high", reason="Verify fermentation health before aging or stabilization.", max_age_days=3)
        if color == "red":
            add("malic_acid", due_hours=24, priority="high", reason="Establish or track malolactic conversion for the red wine.", max_age_days=3)
            add("lactic_acid", due_hours=24, priority="normal", reason="Interpret malolactic progress together with malic acid.", max_age_days=3)
        if stage == "stabilization":
            add("free_so2", due_hours=24, priority="high", reason="Set the protection decision from measured free SO₂ and pH.", max_age_days=7)
            add("total_so2", due_hours=24, priority="normal", reason="Track total SO₂ and legal context.", max_age_days=14)
            add("dissolved_oxygen", due_hours=24, priority="normal", reason="Assess oxidation exposure after transfer and during aging.", max_age_days=3)
    if aging:
        add("free_so2", due_hours=24, priority="critical", reason="Protect aroma and aging potential from measured free SO₂ together with pH.", max_age_days=7)
        add("ph", due_hours=24, priority="high", reason="Keep the protection target tied to the current pH.", max_age_days=14)
        add("volatile_acidity", due_hours=24, priority="high", reason="Catch quality loss early during élevage.", max_age_days=14)
        add("dissolved_oxygen", due_hours=24, priority="high", reason="Control oxidation exposure after movements and during élevage.", max_age_days=3)
        add("total_so2", due_hours=48, priority="normal", reason="Track total SO₂ and legal context without unnecessary repeat testing.", max_age_days=30)
    rank = {"critical": 0, "high": 1, "normal": 2}
    return sorted(recommendations.values(), key=lambda item: (rank.get(str(item["priority"]), 9), item["due_at"], str(item["wine_lot_code"])))


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
        state = "applied" if any(event.get("event_status") == "applied" for event in matching) else "planned" if matching else "recommended"
        reason = "Volume projection from the recorded lot volume and meeting rate; confirm the current technical sheet and lot condition."
        if quantity is None:
            reason = "No quantity projected because an exact rate or supported unit conversion is not recorded."
        if item.get("additive_type") == "nutrient":
            quantity = None
            reason = "Measured YAN/APA and a verified product-specific conversion are required before projecting nutrient quantity."
        output.append({**item, "lot_volume_l": volume_l or None, "projected_quantity": quantity, "projected_unit": "g" if quantity is not None else None, "projection_status": "calculated" if quantity is not None else "waiting_for_rule", "event_state": state, "projection_note": reason, "requires_enologist_approval": False, "operator_record_is_authoritative": True})
    return output


def winemaking_workflow(
    lot: dict[str, Any], readings: list[dict[str, Any]], additions: list[dict[str, Any]],
    stage_events: list[dict[str, Any]], lab_evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    color = str(lot.get("wine_color") or "").casefold()
    explicit = {event.get("stage_code"): event for event in stage_events}
    outlook = fermentation_outlook(readings)
    metrics = (lab_evidence or {}).get("metrics") or {}
    usable_metrics = {code: row for code, row in metrics.items() if row.get("decision_usable", True)}
    reading_babo = next((row.get("babo") for row in reversed(readings) if row.get("babo") is not None), None)
    evidence_present = {
        "ph": "ph" in usable_metrics or any(row.get("ph") is not None for row in readings),
        "total_acidity": "total_acidity" in usable_metrics,
        "babo": "babo" in usable_metrics or reading_babo is not None,
        "potential_alcohol": "potential_alcohol" in usable_metrics or lot.get("potential_alcohol_pct") is not None,
        "potassium": "potassium" in usable_metrics,
        "yan": "yan" in usable_metrics or lot.get("yan_mg_l") is not None,
        "residual_sugar": "residual_sugar" in usable_metrics,
        "actual_alcohol": "actual_alcohol" in usable_metrics,
        "volatile_acidity": "volatile_acidity" in usable_metrics,
    }
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
            required = ("ph", "total_acidity", "babo", "potential_alcohol", "potassium", "yan")
            missing = [code for code in required if not evidence_present[code]]
            status = event.get("stage_status") or ("ready" if not missing else "blocked")
            evidence = "Complete must panel is linked to this lot." if not missing else f"Missing decision evidence: {', '.join(code.replace('_', ' ') for code in missing)}."
        elif definition["code"] == "yeast_nutrient_plan":
            required = ("ph", "potential_alcohol", "yan")
            missing = [code for code in required if not evidence_present[code]]
            status = event.get("stage_status") or ("ready" if not missing else "blocked")
            evidence = "Core chemistry is ready; use the recommended purpose-specific product and working quantity, then record any operator adjustment." if not missing else f"Product planning needs: {', '.join(code.replace('_', ' ') for code in missing)}."
        elif definition["code"] == "inoculation":
            required = ("ph", "potential_alcohol", "yan")
            missing = [code for code in required if not evidence_present[code]]
            ready = not missing and "yeast" in applied_types
            status = event.get("stage_status") or ("ready" if ready else "blocked")
            evidence = "Exact yeast addition is applied with the required chemistry present." if ready else f"Missing or unapplied: {', '.join([*(code.replace('_', ' ') for code in missing), *([] if 'yeast' in applied_types else ['recorded yeast addition'])])}."
        elif definition["code"] == "fermentation_monitoring":
            status = event.get("stage_status") or ("in_progress" if readings else "not_started")
            evidence = outlook.get("message")
        elif definition["code"] == "red_pre_press":
            days = outlook.get("estimated_days_to_dry")
            status = event.get("stage_status") or ("ready" if days is not None and days <= 2 else "blocked")
            evidence = "Density trend is within the projected final two days; schedule and record the press decision." if status == "ready" else "Waiting for a supported final-two-day density projection and target press time."
        elif definition["code"] == "pressing_transfer":
            status = event.get("stage_status") or ("ready" if outlook.get("status") == "dryness_reached_or_near" else "blocked")
            evidence = "Kinetics are near the working dry threshold; record press/transfer timing and destination." if status == "ready" else "Completion evidence is not yet sufficient for a press/transfer recommendation."
        elif definition["code"] == "post_fermentation":
            required = ("residual_sugar", "actual_alcohol", "ph", "total_acidity", "volatile_acidity")
            missing = [code for code in required if not evidence_present[code]]
            status = event.get("stage_status") or ("ready" if not missing else "blocked")
            evidence = "Post-fermentation analytical panel is complete for enologist review." if not missing else f"Post-fermentation gate still needs: {', '.join(code.replace('_', ' ') for code in missing)}."
        if status == "blocked":
            recommended_action = evidence
        elif status in {"ready", "in_progress"}:
            recommended_action = "Complete the next recorded cellar operation and log its time, quantity, destination and observations."
        elif status == "complete":
            recommended_action = "Continue to the next incomplete stage."
        else:
            recommended_action = "Monitor the current lot evidence; this stage is not yet active."
        workflow.append({**definition, **event, "stage_status": status, "evidence": evidence, "recommended_action": recommended_action, "source_reference": WINEMAKING_SOURCE})
    return workflow


def _lot_process(row: dict[str, Any], readings: list[dict[str, Any]], additions: list[dict[str, Any]], stage_events: list[dict[str, Any]], catalog: list[dict[str, Any]], products: list[dict[str, Any]] | None = None, protocols: list[dict[str, Any]] | None = None, lab_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    row = lot_with_lab_measurements(row, lab_evidence or {})
    color = str(row.get("wine_color") or "").casefold()
    volume_l = float(row.get("volume_l") or row.get("initial_l") or 0)
    applied_types = {str(item.get("additive_type") or "").casefold() for item in additions if item.get("event_status") == "applied"}
    planned_types = {str(item.get("additive_type") or "").casefold() for item in additions if item.get("event_status") in {"planned", "approved"}}
    checks = []
    yan = row.get("yan_mg_l")
    if yan is None:
        checks.append({"code": "yan", "state": "blocked", "label": "Measure YAN before inoculation or nutrient correction", "detail": "The 150 mg/L working benchmark is context. Use the exact-lot result and the product-specific contribution shown in the recipe."})
    else:
        deficit = max(0.0, float(row.get("yan_target_mg_l") or 150) - float(yan))
        checks.append({"code": "yan", "state": "review" if deficit else "ready", "label": f"YAN {float(yan):g} mg/L", "detail": f"Measured deficit to the working benchmark: {deficit:g} mg/L. No nutrient quantity is inferred without a verified product rule."})
    if color == "white":
        checks.append({"code": "press_enzyme", "state": "done" if "enzyme" in applied_types else "planned" if "enzyme" in planned_types else "recommended", "label": "White pressing enzyme", "detail": "Use the current recipe's purpose-specific enzyme, working quantity and preparation directions at the indicated press/settling step."})
        yeast_qty = round(volume_l / 100 * 30, 1) if volume_l else None
        checks.append({"code": "yeast", "state": "done" if "yeast" in applied_types else "planned" if "yeast" in planned_types else "recommended", "label": "White-wine yeast inoculation", "detail": f"A 30 g/hL planning reference is {yeast_qty:g} g for {volume_l:g} L; use the lot-specific recipe to select the actual product and verified working rate." if yeast_qty is not None else "Use the lot-specific recipe to select the product and calculate the batch quantity from the verified volume."})
    if color == "red":
        checks.append({"code": "crush_tannin", "state": "done" if "tannin" in applied_types else "planned" if "tannin" in planned_types else "review", "label": "Crushing tannin for color stability", "detail": "Exact product and dose were not specified; excessive tannin was explicitly identified as a risk."})
        enzyme_qty = round(volume_l / 100, 2) if volume_l else None
        checks.append({"code": "red_enzyme", "state": "done" if "enzyme" in applied_types else "planned" if "enzyme" in planned_types else "recommended", "label": "Red pre-press enzyme", "detail": f"The original 1 g/hL planning reference equals {enzyme_qty:g} g for {volume_l:g} L; use it only when the selected product protocol supports that rate and the timing recommendation is active." if enzyme_qty is not None else "Use the selected product protocol and current fermentation timing recommendation."})
        checks.append({"code": "post_tannin", "state": "review", "label": "Optional post-press tannin review", "detail": "Consider only after pressing/fermentation based on wine condition; no automatic dose."})
    effective_stage = row.get("process_stage") or row.get("stage")
    return {**row, "effective_stage": effective_stage, "readings": readings, "additions": additions, "checks": checks, "lab_evidence": lab_evidence or {}, "next_lab_tests": next_recommended_lab_tests(row, lab_evidence or {}, readings), "prediction": fermentation_outlook(readings, stage=effective_stage), "workflow": winemaking_workflow(row, readings, additions, stage_events, lab_evidence or {}), "additive_projections": additive_volume_projections(row, catalog, additions), "product_suggestions": suggest_products(row, products or []), "additive_prediction_pipeline": additive_prediction_pipeline(row, protocols or [], readings, additions, products=products or [], lab_evidence=lab_evidence or {})}


@router.get("/api/v1/enology/process", dependencies=[Depends(authorize)])
def enology_process_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=2023)) -> dict[str, Any]:
    with _dashboard_cache_lock:
        cached = _dashboard_cache.get(year)
        if cached and time.monotonic() - cached[0] < _DASHBOARD_CACHE_TTL_SECONDS:
            return cached[1]
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    lots = fetch_all(
        "SELECT w.id,w.code,w.name,w.stage,cp.manual_stage process_stage,w.volume_l,w.fruit_kg,w.initial_l,w.variety_summary,w.started_at,c.code container_code,"
        "p.wine_color,p.target_style,p.target_press_at,p.yan_mg_l,p.yan_sampled_at,COALESCE(p.yan_target_mg_l,150) yan_target_mg_l,p.potential_alcohol_pct,p.target_potential_alcohol_pct,p.must_turbidity_ntu,p.fruit_condition,p.laccase_u_ml,p.anthocyanin_tannin_ratio,p.inoculated_at,p.planned_filtration_at,p.approved_yeast,p.process_status,p.approved_by,p.approved_at,p.notes "
        "FROM wine_lots w LEFT JOIN cellar_containers c ON c.id=w.current_container_id LEFT JOIN cellar_control_profiles cp ON cp.container_id=w.current_container_id AND cp.estate_id=w.estate_id LEFT JOIN enology_process_profiles p ON p.wine_lot_id=w.id AND p.estate_id=w.estate_id "
        "WHERE w.estate_id=%s AND w.season_id=%s ORDER BY w.started_at,w.code", (estate_id(), season.get("id", "")))
    readings = fetch_all("SELECT id,wine_lot_id,observed_at,temp_c,density_sg,brix,babo,ph,sensory_observation,next_check_at FROM fermentation_observations WHERE estate_id=%s AND wine_lot_id IN (SELECT id FROM wine_lots WHERE season_id=%s) ORDER BY observed_at", (estate_id(), season.get("id", ""))) if season else []
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
    vintage_lab_rows = lab_evidence_rows(year)
    lab_evidence_by_lot = {str(row["id"]): lot_lab_evidence(row, year, rows=vintage_lab_rows) for row in lots}
    lot_processes = [_lot_process(row, [r for r in readings if r.get("wine_lot_id") == row["id"]], [a for a in additions if a.get("wine_lot_id") == row["id"]], [event for event in stage_events if event.get("wine_lot_id") == row["id"]], catalog, products, protocols, lab_evidence_by_lot.get(str(row["id"]))) for row in lots]
    product_classes = sorted({str(product.get("product_class") or "other") for product in products})
    manufacturers = sorted({str(product.get("manufacturer") or "Unknown") for product in products})
    unmapped_lab_analytes = sorted({
        (str(row.get("metric_code")), str(row.get("metric_name")), str(row.get("display_unit")))
        for row in test_series if row.get("routing_status") == "unmapped"
    })
    response = json_ready({"year": year, "model_version": MODEL_VERSION, "source_reference": WINEMAKING_SOURCE, "lots": lot_processes, "next_lab_tests": [test for lot in lot_processes for test in lot.get("next_lab_tests", [])], "catalog": catalog, "product_catalog": products, "product_protocols": protocols, "product_catalog_summary": {"products": len(products), "laffort_products": sum(1 for product in products if product.get("manufacturer") == "LAFFORT"), "enartis_products": sum(1 for product in products if product.get("manufacturer") == "ENARTIS"), "cellar_products": sum(1 for product in products if product.get("in_cellar")), "manufacturers": manufacturers, "technical_sheets": sum(1 for product in products if product.get("pds_url")), "projection_ready": sum(1 for product in products if product.get("dose_verified")), "verified_protocols": len(protocols), "classes": product_classes, "latest_sync": catalog_sync}, "test_requests": requests, "test_series": test_series, "unmapped_lab_analytes": [{"code": code, "name": name, "unit": unit, "status": "AI mapping pending or ambiguous"} for code, name, unit in unmapped_lab_analytes], "chemistry_vintage_overlay": _chemistry_vintage_overlay(year, paired, test_series), "fermentation_vintage_overlay": _fermentation_vintage_overlay(year), "comparison_window": {"first_year": max(2023, year - 4), "last_year": year, "fermentation_alignment": "12-hour buckets from each lot's first recorded fermentation observation", "chemistry_alignment": "calendar month and day within each vintage"}, "analyte_definitions": ENOLOGY_ANALYTES, "testing_pipeline": {stage: enology_testing_pipeline(stage) for stage in ("pre-harvest","pre-fermentation","fermentation","post-fermentation")}, "potential_alcohol_model": potential_alcohol_from_babo(None, paired), "policy": "Recommendations recalculate from exact-lot laboratory evidence, verified volume or grape weight, current product sheets and current tank readings. The authenticated enology operator records the action directly; missing units, missing batch basis and required bench trials remain visible input checks rather than approval gates."})
    with _dashboard_cache_lock:
        _dashboard_cache[year] = (time.monotonic(), response)
    return response


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
    _invalidate_dashboard_cache()
    return {"saved": True, "id": request_id, "status": status}


@router.put("/api/v1/enology/lab-samples/{sample_id}/lot", dependencies=[Depends(authorize_write)])
def link_lab_sample_to_wine_lot(sample_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Make an operator-selected laboratory sample exact-lot evidence."""
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip()
    sample = fetch_one(
        "SELECT s.id,s.wine_lot_id,s.season_id,s.sample_name,s.sample_type FROM lab_samples s "
        "WHERE s.id=%s AND s.estate_id=%s AND s.needs_review=0",
        (sample_id, estate_id()),
    )
    lot = fetch_one("SELECT id,season_id,code FROM wine_lots WHERE id=%s AND estate_id=%s", (wine_lot_id, estate_id()))
    if not sample:
        raise HTTPException(404, "Reviewed laboratory sample not found")
    if not lot:
        raise HTTPException(404, "Wine lot not found")
    if str(sample.get("season_id") or "") != str(lot.get("season_id") or ""):
        raise HTTPException(422, "The laboratory sample and wine lot belong to different vintages")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT IGNORE INTO lab_sample_wine_lots (estate_id,sample_id,wine_lot_id,linked_by) VALUES (%s,%s,%s,%s)",
            (estate_id(), sample_id, wine_lot_id, actor),
        )
        audit(cursor, "link_lab_sample", "lab_sample", sample_id,
              {"wine_lot_id": wine_lot_id, "wine_lot_code": lot.get("code"), "sample_name": sample.get("sample_name")}, actor)
    _invalidate_dashboard_cache()
    return {"saved": True, "sample_id": sample_id, "wine_lot_id": wine_lot_id, "wine_lot_code": lot.get("code")}


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
        approved_by, approved_at = actor, datetime.now()
    yan = payload.get("yan_mg_l")
    if yan not in (None, "") and not 0 <= float(yan) <= 1000:
        raise HTTPException(422, "YAN must be between 0 and 1000 mg/L")
    target = float(payload.get("yan_target_mg_l") or 150)
    fruit_condition = str(payload.get("fruit_condition") or "unknown").casefold()
    if fruit_condition not in {"unknown", "sound", "botrytis", "infected"}:
        raise HTTPException(422, "Choose a supported fruit condition")
    bounded = {"potential_alcohol_pct": (0, 30), "target_potential_alcohol_pct": (0, 30), "must_turbidity_ntu": (0, 100000), "laccase_u_ml": (0, 100000), "anthocyanin_tannin_ratio": (0, 1000)}
    metrics: dict[str, float | None] = {}
    for field, (minimum, maximum) in bounded.items():
        value = payload.get(field)
        metrics[field] = None if value in (None, "") else float(value)
        if metrics[field] is not None and not minimum <= metrics[field] <= maximum:
            raise HTTPException(422, f"{field.replace('_', ' ')} must be between {minimum} and {maximum}")
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_process_profiles (id,estate_id,wine_lot_id,wine_color,target_style,target_press_at,yan_mg_l,yan_sampled_at,yan_target_mg_l,potential_alcohol_pct,target_potential_alcohol_pct,must_turbidity_ntu,fruit_condition,laccase_u_ml,anthocyanin_tannin_ratio,inoculated_at,planned_filtration_at,approved_yeast,process_status,approved_by,approved_at,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE wine_color=VALUES(wine_color),target_style=VALUES(target_style),target_press_at=VALUES(target_press_at),yan_mg_l=VALUES(yan_mg_l),yan_sampled_at=VALUES(yan_sampled_at),yan_target_mg_l=VALUES(yan_target_mg_l),potential_alcohol_pct=VALUES(potential_alcohol_pct),target_potential_alcohol_pct=VALUES(target_potential_alcohol_pct),must_turbidity_ntu=VALUES(must_turbidity_ntu),fruit_condition=VALUES(fruit_condition),laccase_u_ml=VALUES(laccase_u_ml),anthocyanin_tannin_ratio=VALUES(anthocyanin_tannin_ratio),inoculated_at=VALUES(inoculated_at),planned_filtration_at=VALUES(planned_filtration_at),approved_yeast=VALUES(approved_yeast),process_status=VALUES(process_status),approved_by=VALUES(approved_by),approved_at=VALUES(approved_at),notes=VALUES(notes)", (new_id(),estate_id(),wine_lot_id,color,payload.get("target_style") or None,payload.get("target_press_at") or None,None if yan in (None, "") else float(yan),payload.get("yan_sampled_at") or None,target,metrics["potential_alcohol_pct"],metrics["target_potential_alcohol_pct"],metrics["must_turbidity_ntu"],fruit_condition,metrics["laccase_u_ml"],metrics["anthocyanin_tannin_ratio"],payload.get("inoculated_at") or None,payload.get("planned_filtration_at") or None,payload.get("approved_yeast") or None,status,approved_by,approved_at,payload.get("notes") or None))
        audit(cursor,"update","enology_process_profile",wine_lot_id,{"wine_color":color,"yan_mg_l":yan,"status":status},actor)
    _invalidate_dashboard_cache()
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
        approved_by = actor
    completed_at = payload.get("completed_at") or (datetime.now() if status == "complete" else None)
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO enology_stage_events (id,estate_id,wine_lot_id,stage_code,stage_status,planned_at,completed_at,notes,approved_by,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE stage_status=VALUES(stage_status),planned_at=VALUES(planned_at),completed_at=VALUES(completed_at),notes=VALUES(notes),approved_by=VALUES(approved_by),updated_by=VALUES(updated_by)", (new_id(),estate_id(),wine_lot_id,stage_code,status,payload.get("planned_at") or None,completed_at,payload.get("notes") or None,approved_by,actor))
        audit(cursor,"update","enology_stage",f"{wine_lot_id}:{stage_code}",{"status":status,"completed_at":completed_at},actor)
    _invalidate_dashboard_cache()
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
    _invalidate_dashboard_cache()
    return {"saved": True, "id": record_id}
