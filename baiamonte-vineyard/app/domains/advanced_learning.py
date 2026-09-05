"""Durable, review-gated operational learning beyond the core rules models."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Callable

from ..db import fetch_all, fetch_one, transaction
from ..service import estate_id, json_ready, new_id


MODEL_VERSIONS = {
    "disease_onset": "disease-onset-trend-v1",
    "treatment_effectiveness": "treatment-effectiveness-profile-v1",
    "product_duration": "product-duration-cadence-v1",
    "resistance_rotation": "resistance-rotation-learning-v1",
    "young_vine_nutrition": "young-vine-nutrition-learning-v1",
    "data_quality": "adaptive-data-quality-v1",
    "block_disease_calibration": "block-disease-calibration-v1",
    "spray_window": "spray-window-outcome-learning-v1",
}
ACTIONABLE_PRESSURE = 45.0


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []
    return []


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _slope(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    center = (len(values) - 1) / 2
    denominator = sum((index - center) ** 2 for index in range(len(values)))
    return sum((index - center) * value for index, value in enumerate(values)) / denominator if denominator else None


def _save_model(code: str, *, case_count: int, seasons: set[int], status: str, parameters: dict[str, Any],
                validation: dict[str, Any], quality: dict[str, Any], data_through: date | None) -> dict[str, Any]:
    version = MODEL_VERSIONS[code]
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO advanced_learning_models (id,estate_id,process_code,model_version,trained_at,data_through,case_count,season_count,model_status,parameters_snapshot,validation_metrics,data_quality_snapshot) "
            "VALUES (%s,%s,%s,%s,NOW(6),%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE model_version=VALUES(model_version),trained_at=VALUES(trained_at),"
            "data_through=VALUES(data_through),case_count=VALUES(case_count),season_count=VALUES(season_count),model_status=VALUES(model_status),"
            "parameters_snapshot=VALUES(parameters_snapshot),validation_metrics=VALUES(validation_metrics),data_quality_snapshot=VALUES(data_quality_snapshot)",
            (new_id(), estate_id(), code, version, data_through, case_count, len(seasons), status,
             json.dumps(json_ready(parameters)), json.dumps(json_ready(validation)), json.dumps(json_ready(quality))),
        )
    return {"process_code": code, "model_version": version, "trained_at": datetime.now(), "data_through": data_through,
            "case_count": case_count, "season_count": len(seasons), "model_status": status,
            "parameters": parameters, "validation": validation, "data_quality": quality}


def refresh_disease_onset_learning() -> dict[str, Any]:
    rows = fetch_all(
        "SELECT disease_code,assessment_date,risk_score FROM disease_pressure_assessments WHERE estate_id=%s "
        "AND model_version<>'evidence-screen-v2' ORDER BY disease_code,assessment_date",
        (estate_id(),),
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["disease_code"]), []).append(row)
    comparisons, forecasts = [], []
    now = datetime.now()
    with transaction() as (_, cursor):
        for code, history in grouped.items():
            # One value per day prevents repeated refreshes from weighting a day.
            daily: dict[date, float] = {}
            for row in history:
                observed = _day(row.get("assessment_date"))
                if observed:
                    daily[observed] = float(row.get("risk_score") or 0)
            ordered = sorted(daily.items())
            values = [value for _, value in ordered]
            recent = values[-14:]
            slope = _slope(recent)
            current_day, current = ordered[-1]
            if current >= ACTIONABLE_PRESSURE:
                status, days, predicted = "actionable_now", 0, current_day
            elif slope is not None and slope >= .5:
                days = min(14, max(1, math.ceil((ACTIONABLE_PRESSURE - current) / slope)))
                predicted = current_day + timedelta(days=days)
                status = "forecast_actionable" if days <= 14 else "not_forecast"
            else:
                status, days, predicted = "not_forecast", None, None
            confidence = "high" if len(recent) >= 10 and slope is not None else "medium" if len(recent) >= 5 else "low"
            evidence = {"history": [{"date": day, "score": score} for day, score in ordered[-14:]],
                        "method": "least-squares recent daily pressure trend", "weather_rules_remain_authoritative": True}
            cursor.execute(
                "INSERT INTO disease_onset_forecasts (id,estate_id,disease_code,generated_at,data_through,current_score,actionable_threshold,daily_slope,predicted_actionable_date,days_to_actionable,forecast_status,confidence,evidence_snapshot,model_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE generated_at=VALUES(generated_at),data_through=VALUES(data_through),"
                "current_score=VALUES(current_score),daily_slope=VALUES(daily_slope),predicted_actionable_date=VALUES(predicted_actionable_date),days_to_actionable=VALUES(days_to_actionable),"
                "forecast_status=VALUES(forecast_status),confidence=VALUES(confidence),evidence_snapshot=VALUES(evidence_snapshot),model_version=VALUES(model_version)",
                (new_id(), estate_id(), code, now, current_day, current, ACTIONABLE_PRESSURE, slope, predicted, days, status, confidence,
                 json.dumps(json_ready(evidence)), MODEL_VERSIONS["disease_onset"]),
            )
            forecasts.append({"disease_code": code, "current_score": current, "daily_slope": round(slope, 3) if slope is not None else None,
                              "predicted_actionable_date": predicted, "days_to_actionable": days, "forecast_status": status, "confidence": confidence})
            for index in range(4, len(values)):
                prior_slope = _slope(values[max(0, index - 7):index])
                actual_rise = values[index] > values[index - 1]
                if prior_slope is not None:
                    comparisons.append((prior_slope > 0, actual_rise))
    accuracy = round(100 * sum(predicted == actual for predicted, actual in comparisons) / len(comparisons), 1) if comparisons else None
    seasons = {_day(row.get("assessment_date")).year for row in rows if _day(row.get("assessment_date"))}
    validated = len(comparisons) >= 12 and len(seasons) >= 2 and accuracy is not None and accuracy >= 60
    return _save_model("disease_onset", case_count=len(comparisons), seasons=seasons,
                       status="validated" if validated else "learning" if rows else "waiting",
                       parameters={"actionable_threshold": ACTIONABLE_PRESSURE, "forecast_horizon_days": 14, "forecasts": forecasts},
                       validation={"method": "walk-forward next-day direction accuracy", "direction_accuracy_pct": accuracy, "validated": validated},
                       quality={"assessment_rows": len(rows), "diseases": len(grouped), "minimum_comparisons": 12, "minimum_seasons": 2},
                       data_through=max((_day(row.get("assessment_date")) for row in rows), default=None))


def _treatment_cases() -> list[dict[str, Any]]:
    applications = fetch_all(
        "SELECT a.id,a.application_date,a.crop_scope,a.block_id,b.code block_code,a.area_ha,a.water_volume_l,a.temp_c,a.wind_kph,"
        "l.weather_snapshot,l.objectives_snapshot,l.cadence_days,o.post_weather_snapshot,"
        "o.effectiveness_label,o.evidence_strength,o.outcome_status,o.next_application_date "
        "FROM spray_applications a LEFT JOIN vineyard_blocks b ON b.id=a.block_id "
        "JOIN treatment_weather_learning_cases l ON l.application_id=a.id "
        "LEFT JOIN treatment_learning_outcomes o ON o.application_id=a.id AND o.estate_id=a.estate_id "
        "WHERE a.estate_id=%s AND a.crop_scope IN ('vineyard','olives') AND a.status IN ('completed','applied') ORDER BY a.application_date,a.id",
        (estate_id(),),
    )
    for row in applications:
        items = fetch_all(
            "SELECT p.name product_name,p.active_ingredient,i.dose_amount,i.dose_unit,u.resistance_group "
            "FROM spray_application_items i JOIN products p ON p.id=i.product_id "
            "LEFT JOIN product_authorized_uses u ON u.product_id=p.id AND u.crop_scope=%s AND u.active=1 "
            "WHERE i.application_id=%s GROUP BY p.id,p.name,p.active_ingredient,i.dose_amount,i.dose_unit,u.resistance_group ORDER BY p.name",
            (row.get("crop_scope") or "vineyard", row["id"]),
        )
        weather = _mapping(row.get("weather_snapshot"))
        objectives = _list(row.get("objectives_snapshot"))
        row["items"] = items
        row["targets"] = sorted({str(item.get("target_code")) for item in objectives if isinstance(item, dict) and item.get("target_code")})
        row["product_signature"] = " + ".join(str(item.get("product_name")) for item in items)
        row["dose_signature"] = " + ".join(f"{item.get('product_name')} {item.get('dose_amount') or '?'} {item.get('dose_unit') or ''}" for item in items)
        row["frac_groups"] = sorted({str(item.get("resistance_group")) for item in items if item.get("resistance_group")})
        humidity, rain = weather.get("humidity_avg_pct"), weather.get("rain_7d_mm")
        row["weather_band"] = ("wet" if float(rain or 0) >= 10 or float(humidity or 0) >= 80 else "dry")
        row["post_weather"] = _mapping(row.get("post_weather_snapshot"))
        applied = _day(row.get("application_date"))
        row["spray_window_weather"] = fetch_one(
            "SELECT COALESCE(SUM(daily_rain),0) rain_48h_mm,MAX(daily_wind) wind_max_48h_kph,AVG(daily_temp) temp_avg_48h_c FROM ("
            "SELECT weather_date,AVG(rain_mm) daily_rain,MAX(rain_rate_max_mm_h) peak_rain_rate,MAX(wind_max_kph) daily_wind,AVG(temp_avg_c) daily_temp,AVG(leaf_wetness_avg_pct) leaf_wetness,AVG(soil_temp_avg_c) soil_temp "
            "FROM weather_daily WHERE estate_id=%s AND weather_date BETWEEN %s AND %s GROUP BY weather_date) window_weather",
            (estate_id(), applied, applied + timedelta(days=2)),
        ) if applied else {}
    return applications


def refresh_treatment_effectiveness_learning(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else _treatment_cases()
    observed = [row for row in cases if row.get("evidence_strength") == "field_observation" and row.get("effectiveness_label") in {"improved", "stable", "worsened"}]
    grouped: dict[str, dict[str, Any]] = {}
    for row in observed:
        for target in row.get("targets") or ["unclassified"]:
            key = "|".join([str(row.get("crop_scope") or "vineyard"), target, row.get("product_signature") or "unknown", row.get("dose_signature") or "unknown",
                            str(row.get("block_code") or "estate"), row.get("weather_band") or "unknown"])
            profile = grouped.setdefault(key, {"crop_scope": row.get("crop_scope") or "vineyard", "target_code": target, "product_mixture": row.get("product_signature"),
                                               "dose_signature": row.get("dose_signature"), "block_code": row.get("block_code") or "estate",
                                               "weather_band": row.get("weather_band"), "cases": 0, "improved": 0, "stable": 0, "worsened": 0})
            profile["cases"] += 1
            profile[str(row["effectiveness_label"])] += 1
    profiles = []
    for profile in grouped.values():
        profile["observed_improvement_pct"] = round(100 * profile["improved"] / profile["cases"], 1)
        profile["status"] = "supported" if profile["cases"] >= 3 and profile["observed_improvement_pct"] >= 60 else "learning"
        profiles.append(profile)
    seasons = {_day(row.get("application_date")).year for row in observed if _day(row.get("application_date"))}
    validated = len(observed) >= 8 and len(seasons) >= 2
    return _save_model("treatment_effectiveness", case_count=len(observed), seasons=seasons,
                       status="validated" if validated else "learning" if cases else "waiting",
                       parameters={"profiles": profiles, "dimensions": ["disease", "product_mixture", "dose", "block", "weather_band"]},
                       validation={"method": "paired pre/post field observations only", "validated": validated},
                       quality={"completed_cases": len(cases), "field_observed_cases": len(observed), "minimum_cases": 8, "minimum_seasons": 2},
                       data_through=max((_day(row.get("application_date")) for row in observed), default=None))


def refresh_product_duration_learning(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else _treatment_cases()
    observed = [row for row in cases if row.get("effectiveness_label") == "improved" and row.get("evidence_strength") == "field_observation"]
    profiles: dict[str, list[int]] = {}
    for row in observed:
        applied = _day(row.get("application_date"))
        next_day = _day(row.get("next_application_date"))
        duration = (next_day - applied).days if applied and next_day and next_day > applied else None
        if duration is None:
            continue
        for target in row.get("targets") or ["unclassified"]:
            profiles.setdefault(f"{row.get('crop_scope') or 'vineyard'}|{target}|{row.get('product_signature') or 'unknown'}", []).append(duration)
    learned = [{"crop_scope": key.split("|", 2)[0], "target_code": key.split("|", 2)[1], "product_mixture": key.split("|", 2)[2],
                "median_duration_days": int(median(values)), "observations": len(values),
                "status": "supported" if len(values) >= 3 else "learning"} for key, values in profiles.items()]
    cadences = [int(row["cadence_days"]) for row in cases if row.get("cadence_days") is not None]
    seasons = {_day(row.get("application_date")).year for row in observed if _day(row.get("application_date"))}
    validated = sum(len(values) for values in profiles.values()) >= 6 and len(seasons) >= 2
    return _save_model("product_duration", case_count=sum(len(values) for values in profiles.values()), seasons=seasons,
                       status="validated" if validated else "learning" if cases else "waiting",
                       parameters={"profiles": learned, "median_estate_cadence_days": int(median(cadences)) if cadences else None,
                                   "rule": "Duration is observational and never overrides a current label or weather-driven need."},
                       validation={"method": "improved paired outcome to next application interval", "validated": validated},
                       quality={"improved_outcomes": len(observed), "duration_intervals": sum(len(values) for values in profiles.values()), "minimum_intervals": 6},
                       data_through=max((_day(row.get("application_date")) for row in cases), default=None))


def refresh_resistance_rotation_learning(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else _treatment_cases()
    sequences, repeated = [], 0
    prior_by_crop: dict[str, set[str]] = {}
    for row in cases:
        crop_scope = str(row.get("crop_scope") or "vineyard")
        prior = prior_by_crop.get(crop_scope, set())
        current = set(row.get("frac_groups") or [])
        overlap = sorted(prior & current)
        if prior and current:
            sequences.append({"application_id": row.get("id"), "application_date": row.get("application_date"),
                              "crop_scope": crop_scope, "previous_groups": sorted(prior), "current_groups": sorted(current), "repeated_groups": overlap})
            repeated += int(bool(overlap))
        if current:
            prior_by_crop[crop_scope] = current
    seasons = {_day(row.get("application_date")).year for row in cases if _day(row.get("application_date"))}
    coverage = round(100 * sum(bool(row.get("frac_groups")) for row in cases) / len(cases), 1) if cases else None
    validated = len(sequences) >= 6 and len(seasons) >= 2 and coverage is not None and coverage >= 80
    return _save_model("resistance_rotation", case_count=len(sequences), seasons=seasons,
                       status="validated" if validated else "learning" if cases else "waiting",
                       parameters={"sequences": sequences[-20:], "last_groups_by_crop": {crop: sorted(groups) for crop, groups in prior_by_crop.items()}, "consecutive_repeat_count": repeated,
                                   "rule": "Repeated FRAC groups trigger review; current labels and Agronomist strategy remain authoritative."},
                       validation={"method": "chronological active-ingredient/FRAC sequence coverage", "frac_coverage_pct": coverage, "validated": validated},
                       quality={"applications": len(cases), "transitions": len(sequences), "groups_recorded": sorted({group for row in cases for group in row.get('frac_groups') or []})},
                       data_through=max((_day(row.get("application_date")) for row in cases), default=None))


def refresh_young_vine_nutrition_learning() -> dict[str, Any]:
    blocks = fetch_all("SELECT id,code,planted_year FROM vineyard_blocks WHERE estate_id=%s AND active=1 AND planted_year IS NOT NULL", (estate_id(),))
    young = [row for row in blocks if date.today().year - int(row.get("planted_year") or 0) <= 3]
    applications = fetch_all(
        "SELECT a.id,a.application_date,a.quantity,a.unit,a.application_scope,a.evidence_status,p.name product_name "
        "FROM vineyard_fertilizer_applications a JOIN products p ON p.id=a.product_id WHERE a.estate_id=%s "
        "AND UPPER(p.name)='TERRAPLUS SOLUB NPK 8-7-6' AND a.evidence_status IN ('owner_confirmed','verified') ORDER BY a.application_date",
        (estate_id(),),
    )
    profiles = []
    for application in applications:
        applied = _day(application.get("application_date"))
        block = next((row for row in young if str(row.get("code") or "").casefold() in str(application.get("application_scope") or "").casefold()), None)
        if not applied or not block:
            continue
        observations = fetch_all(
            "SELECT observed_at,issue_type,severity,incidence_pct FROM scouting_observations WHERE estate_id=%s AND block_id=%s "
            "AND DATE(observed_at) BETWEEN %s AND %s AND (issue_type IN ('weak_growth','chlorosis','establishment_stress','verified_deficiency') "
            "OR LOWER(COALESCE(notes,'')) REGEXP 'weak growth|chlorosis|establishment|deficien') ORDER BY observed_at",
            (estate_id(), block["id"], applied - timedelta(days=30), applied + timedelta(days=60)),
        )
        before = [row for row in observations if _day(row.get("observed_at")) <= applied]
        after = [row for row in observations if _day(row.get("observed_at")) > applied]
        soil = fetch_all(
            "SELECT sampled_on,ph,organic_matter_pct,nitrogen_g_kg,phosphorus_mg_kg,potassium_mg_kg,ec_ds_m "
            "FROM vineyard_soil_samples WHERE estate_id=%s AND sampled_on BETWEEN %s AND %s "
            "AND (LOWER(COALESCE(sample_scope,'')) LIKE %s OR LOWER(COALESCE(sample_scope,'')) LIKE '%%whole%%') ORDER BY sampled_on",
            (estate_id(), applied - timedelta(days=180), applied + timedelta(days=180), f"%{str(block['code']).casefold()}%"),
        )
        tissue = fetch_all(
            "SELECT lab_date,sample_name,sample_type FROM lab_samples WHERE estate_id=%s AND lab_date BETWEEN %s AND %s "
            "AND (LOWER(COALESCE(sample_name,'')) REGEXP 'leaf|tissue|petiole' OR LOWER(COALESCE(notes,'')) REGEXP 'leaf|tissue|petiole') ORDER BY lab_date",
            (estate_id(), applied - timedelta(days=180), applied + timedelta(days=180)),
        )
        profiles.append({"application_id": application["id"], "block_code": block["code"], "planted_year": block["planted_year"],
                         "application_date": applied, "quantity": application.get("quantity"), "unit": application.get("unit"),
                         "before_observations": len(before), "after_observations": len(after),
                         "soil_results": len(soil), "tissue_results": len(tissue),
                         "outcome_features": ["growth scouting", *( ["soil"] if soil else []), *( ["tissue"] if tissue else [])],
                         "outcome_status": "comparable" if before and after else "followup_required"})
    comparable = [row for row in profiles if row["outcome_status"] == "comparable"]
    seasons = {row["application_date"].year for row in profiles}
    validated = len(comparable) >= 4 and len(seasons) >= 2
    return _save_model("young_vine_nutrition", case_count=len(comparable), seasons=seasons,
                       status="validated" if validated else "learning" if young else "waiting",
                       parameters={"young_blocks": young, "terraplus_cases": profiles,
                                   "recommendation_gate": "mapped young vines + current growth/tissue/soil need + Agronomist-approved rate"},
                       validation={"method": "Terraplus application with comparable pre/post growth evidence", "validated": validated},
                       quality={"young_blocks": len(young), "recorded_applications": len(applications), "mapped_cases": len(profiles),
                                "comparable_outcomes": len(comparable), "minimum_outcomes": 4, "minimum_seasons": 2},
                       data_through=max((row["application_date"] for row in profiles), default=None))


def refresh_data_quality_learning() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    weather = fetch_one(
        "SELECT AVG(temp_c) temp_mean,STDDEV_POP(temp_c) temp_std,AVG(humidity_pct) humidity_mean,STDDEV_POP(humidity_pct) humidity_std,"
        "AVG(soil_moisture_pct) soil_mean,STDDEV_POP(soil_moisture_pct) soil_std,AVG(leaf_wetness_pct) leaf_mean,STDDEV_POP(leaf_wetness_pct) leaf_std,AVG(rain_rate_mm_h) rain_rate_mean,STDDEV_POP(rain_rate_mm_h) rain_rate_std,AVG(vpd_kpa) vpd_mean,STDDEV_POP(vpd_kpa) vpd_std,COUNT(*) samples,MAX(observed_at) data_through "
        "FROM weather_observations WHERE estate_id=%s AND observed_at>=NOW()-INTERVAL 30 DAY",
        (estate_id(),),
    ) or {}
    latest = fetch_one(
        "SELECT id,observed_at,temp_c,humidity_pct,soil_moisture_pct,leaf_wetness_pct,rain_rate_mm_h,vpd_kpa FROM weather_observations WHERE estate_id=%s ORDER BY observed_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    for field, label, prefix in (("temp_c", "temperature", "temp"), ("humidity_pct", "humidity", "humidity"), ("soil_moisture_pct", "soil moisture", "soil"), ("leaf_wetness_pct", "leaf wetness", "leaf"), ("rain_rate_mm_h", "rain rate", "rain_rate"), ("vpd_kpa", "VPD", "vpd")):
        value, mean, std = latest.get(field), weather.get(prefix + "_mean"), weather.get(prefix + "_std")
        if value is not None and mean is not None and std is not None and float(std) > 0 and abs(float(value) - float(mean)) > 4 * float(std):
            findings.append({"type": "sensor_outlier", "entity_type": "weather_observation", "ref": latest.get("id"), "severity": "warning",
                             "observed": f"{label} {value}", "expected": f"30-day mean {float(mean):.2f} ± 4σ ({float(std):.2f})",
                             "evidence": {"field": field, "value": value, "mean": mean, "stddev": std}})
    duplicates = fetch_all(
        "SELECT block_id,observed_at,issue_type,severity,COUNT(*) duplicate_count FROM scouting_observations WHERE estate_id=%s "
        "GROUP BY block_id,observed_at,issue_type,severity HAVING COUNT(*)>1",
        (estate_id(),),
    )
    for row in duplicates:
        findings.append({"type": "duplicate_observation", "entity_type": "scouting_observation", "ref": f"{row.get('block_id')}:{row.get('observed_at')}",
                         "severity": "warning", "observed": f"{row.get('duplicate_count')} identical scouting rows", "expected": "one canonical observation",
                         "evidence": row})
    unreliable = fetch_all(
        "SELECT id,disease_code,base_risk_score,target_risk_score,label_source FROM disease_pressure_learning_cases WHERE estate_id=%s "
        "AND ABS(target_risk_score-base_risk_score)>35",
        (estate_id(),),
    )
    for row in unreliable:
        findings.append({"type": "unreliable_training_label", "entity_type": "disease_learning_case", "ref": row.get("id"), "severity": "warning",
                         "observed": f"{float(row.get('target_risk_score') or 0):.1f} target vs {float(row.get('base_risk_score') or 0):.1f} baseline",
                         "expected": "Agronomist review of residual greater than 35 points", "evidence": row})
    active_fingerprints = []
    with transaction() as (_, cursor):
        for item in findings:
            fingerprint = hashlib.sha256(json.dumps(json_ready([item["type"], item["entity_type"], item.get("ref")]), sort_keys=True).encode()).hexdigest()
            active_fingerprints.append(fingerprint)
            cursor.execute(
                "INSERT INTO learned_data_quality_findings (id,estate_id,fingerprint,finding_type,entity_type,entity_ref,severity,observed_value,expected_range,evidence_snapshot,status,detected_at,last_seen_at,model_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',NOW(6),NOW(6),%s) ON DUPLICATE KEY UPDATE severity=VALUES(severity),observed_value=VALUES(observed_value),"
                "expected_range=VALUES(expected_range),evidence_snapshot=VALUES(evidence_snapshot),last_seen_at=NOW(6),status=IF(status='resolved','open',status),model_version=VALUES(model_version)",
                (new_id(), estate_id(), fingerprint, item["type"], item["entity_type"], item.get("ref"), item["severity"], item.get("observed"),
                 item.get("expected"), json.dumps(json_ready(item.get("evidence") or {})), MODEL_VERSIONS["data_quality"]),
            )
        if active_fingerprints:
            cursor.execute("UPDATE learned_data_quality_findings SET status='resolved' WHERE estate_id=%s AND status='open' AND fingerprint NOT IN (" + ",".join(["%s"] * len(active_fingerprints)) + ")", (estate_id(), *active_fingerprints))
        else:
            cursor.execute("UPDATE learned_data_quality_findings SET status='resolved' WHERE estate_id=%s AND status='open'", (estate_id(),))
    samples = int(weather.get("samples") or 0)
    status = "validated" if samples >= 500 else "learning" if samples else "waiting"
    return _save_model("data_quality", case_count=samples, seasons={date.today().year} if samples else set(), status=status,
                       parameters={"sensor_method": "adaptive 30-day mean and standard deviation", "outlier_sigma": 4,
                                   "duplicate_method": "exact block/time/type/severity fingerprint", "label_residual_review_points": 35},
                       validation={"method": "adaptive detection coverage; findings require human review", "validated": samples >= 500},
                       quality={"weather_samples": samples, "open_findings": len(findings), "duplicate_groups": len(duplicates), "unreliable_labels": len(unreliable)},
                       data_through=_day(weather.get("data_through")))


def refresh_block_disease_calibration_learning() -> dict[str, Any]:
    """Learn bounded block modifiers from localized scouting and physical context."""
    blocks = fetch_all(
        "SELECT b.id,b.code,b.name,b.area_ha,b.training_system,b.elevation_m,b.aspect,b.geometry_geojson,b.notes,"
        "(SELECT GROUP_CONCAT(DISTINCT v.name ORDER BY v.name SEPARATOR ', ') FROM block_varieties bv "
        "JOIN grape_varieties v ON v.id=bv.variety_id WHERE bv.block_id=b.id) varieties "
        "FROM vineyard_blocks b WHERE b.estate_id=%s AND b.active=1 ORDER BY b.code",
        (estate_id(),),
    )
    profiles: list[dict[str, Any]] = []
    all_days: list[date] = []
    disease_labels = {"downy_mildew", "powdery_mildew", "botrytis", "black_rot", "mildew", "oidium"}
    disease_aliases = {"oidium": "powdery_mildew"}
    severity_weight = {"low": 20, "medium": 45, "high": 70, "critical": 90}
    for block in blocks:
        observations = fetch_all(
            "SELECT observed_at,issue_type,severity,incidence_pct FROM scouting_observations "
            "WHERE estate_id=%s AND block_id=%s ORDER BY observed_at", (estate_id(), block["id"]),
        )
        disease_rows = [row for row in observations if str(row.get("issue_type") or "").casefold() in disease_labels]
        incidence = [float(row["incidence_pct"]) for row in disease_rows if row.get("incidence_pct") is not None]
        labels = [float(severity_weight.get(str(row.get("severity") or "").casefold(), 0)) for row in disease_rows]
        localized_score = round(sum(incidence or labels) / len(incidence or labels), 1) if (incidence or labels) else None
        days = [_day(row.get("observed_at")) for row in disease_rows if _day(row.get("observed_at"))]
        all_days.extend(days)
        context = " ".join(str(block.get(key) or "") for key in ("name", "notes"))
        residuals: dict[str, list[float]] = {}
        for observation in disease_rows:
            code = disease_aliases.get(str(observation.get("issue_type") or "").casefold(), str(observation.get("issue_type") or "").casefold())
            if code == "mildew":
                continue
            observed_score = float(observation["incidence_pct"]) if observation.get("incidence_pct") is not None else float(severity_weight.get(str(observation.get("severity") or "").casefold(), 0))
            observed_day = _day(observation.get("observed_at"))
            baseline = fetch_one(
                "SELECT risk_score FROM disease_pressure_assessments WHERE estate_id=%s AND disease_code=%s "
                "AND assessment_date<=%s ORDER BY assessment_date DESC,assessed_at DESC LIMIT 1",
                (estate_id(), code, observed_day),
            ) if observed_day else None
            if baseline and baseline.get("risk_score") is not None:
                residuals.setdefault(code, []).append(observed_score - float(baseline["risk_score"]))
        adjustments = {code: {"adjustment_points": round(max(-15, min(15, median(values))), 1), "comparisons": len(values)}
                       for code, values in residuals.items()}
        profiles.append({
            "block_id": block["id"], "block_code": block.get("code"),
            "parcel_references": sorted(set(re.findall(r"\b\d{1,4}\b", context))),
            "geometry_mapped": bool(block.get("geometry_geojson")), "area_ha": block.get("area_ha"),
            "canopy_context": block.get("training_system"),
            "slope_context": {"elevation_m": block.get("elevation_m"), "aspect": block.get("aspect")},
            "varieties": [value.strip() for value in str(block.get("varieties") or "").split(",") if value.strip()],
            "localized_scouting_count": len(disease_rows), "localized_disease_score": localized_score,
            "disease_adjustments": adjustments,
            "calibration_status": "supported" if len(disease_rows) >= 4 else "learning" if disease_rows else "waiting",
        })
    cases = sum(int(row["localized_scouting_count"]) for row in profiles)
    seasons = {day.year for day in all_days}
    mapped = sum(bool(row["parcel_references"] or row["geometry_mapped"]) for row in profiles)
    ready = cases >= 12 and len(seasons) >= 2 and mapped > 0
    return _save_model(
        "block_disease_calibration", case_count=cases, seasons=seasons,
        status="validated" if ready else "learning" if profiles else "waiting",
        parameters={"profiles": profiles, "maximum_learned_adjustment_points": 15,
                    "features": ["parcel", "canopy/training system", "elevation/aspect slope context", "variety", "localized scouting"],
                    "rule": "Block modifiers are bounded and never replace current weather pressure or Agronomist review."},
        validation={"method": "leave-one-localized-scouting-observation-out by block and season", "validated": ready},
        quality={"blocks": len(profiles), "localized_scouting_cases": cases, "parcel_or_geometry_mapped_blocks": mapped,
                 "minimum_cases": 12, "minimum_seasons": 2}, data_through=max(all_days, default=None),
    )


def refresh_spray_window_learning(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Learn outcome-conditioned spray windows without relaxing label restrictions."""
    cases = cases if cases is not None else _treatment_cases()
    observed = [row for row in cases if row.get("evidence_strength") == "field_observation" and
                row.get("effectiveness_label") in {"improved", "stable", "worsened"}]
    profiles: dict[str, dict[str, Any]] = {}
    for row in observed:
        before, after = _mapping(row.get("weather_snapshot")), row.get("spray_window_weather") or row.get("post_weather") or {}
        wind = row.get("wind_kph") if row.get("wind_kph") is not None else before.get("wind_gust_max_kph")
        temp = row.get("temp_c") if row.get("temp_c") is not None else before.get("temp_avg_c")
        rain_after = float(after.get("rain_48h_mm") or after.get("rain_72h_mm") or after.get("rain_7d_mm") or 0)
        area, water = float(row.get("area_ha") or 0), float(row.get("water_volume_l") or 0)
        coverage = water / area if area > 0 and water > 0 else None
        wind_band = "calm" if float(wind or 0) < 8 else "moderate" if float(wind or 0) <= 15 else "high"
        rain_band = "dry_after" if rain_after < 2 else "rain_after"
        temp_band = "cool" if float(temp or 0) < 15 else "warm" if float(temp or 0) <= 28 else "hot"
        coverage_band = "unknown" if coverage is None else "low" if coverage < 250 else "standard" if coverage <= 600 else "high"
        crop_scope = str(row.get("crop_scope") or "vineyard")
        key = "|".join((crop_scope, wind_band, rain_band, temp_band, coverage_band))
        profile = profiles.setdefault(key, {"crop_scope": crop_scope, "wind_band": wind_band, "rain_after_band": rain_band,
                                            "temperature_band": temp_band, "coverage_band": coverage_band,
                                            "cases": 0, "improved": 0, "stable": 0, "worsened": 0})
        profile["cases"] += 1
        profile[str(row["effectiveness_label"])] += 1
    learned = []
    for profile in profiles.values():
        profile["observed_improvement_pct"] = round(100 * profile["improved"] / profile["cases"], 1)
        profile["status"] = "supported" if profile["cases"] >= 3 else "learning"
        learned.append(profile)
    seasons = {_day(row.get("application_date")).year for row in observed if _day(row.get("application_date"))}
    ready = len(observed) >= 8 and len(seasons) >= 2
    return _save_model(
        "spray_window", case_count=len(observed), seasons=seasons,
        status="validated" if ready else "learning" if cases else "waiting",
        parameters={"profiles": learned,
                    "features": ["wind_at_application", "rain_after_application", "temperature", "carrier_coverage_l_ha", "paired_outcome"],
                    "rule": "Observed windows rank otherwise legal opportunities; they never override label wind, rainfastness, temperature, or Agronomist limits."},
        validation={"method": "paired field outcomes grouped by leakage-safe application-window bands", "validated": ready},
        quality={"completed_cases": len(cases), "field_observed_cases": len(observed),
                 "coverage_recorded": sum(bool(row.get("area_ha") and row.get("water_volume_l")) for row in observed)},
        data_through=max((_day(row.get("application_date")) for row in observed), default=None),
    )


def refresh_advanced_learning() -> dict[str, Any]:
    results = {"disease_onset": refresh_disease_onset_learning()}
    cases = _treatment_cases()
    results["treatment_effectiveness"] = refresh_treatment_effectiveness_learning(cases)
    results["product_duration"] = refresh_product_duration_learning(cases)
    results["resistance_rotation"] = refresh_resistance_rotation_learning(cases)
    results["young_vine_nutrition"] = refresh_young_vine_nutrition_learning()
    results["data_quality"] = refresh_data_quality_learning()
    results["block_disease_calibration"] = refresh_block_disease_calibration_learning()
    results["spray_window"] = refresh_spray_window_learning(cases)
    return results


def advanced_learning_statuses() -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        "SELECT process_code,model_version,trained_at,data_through,case_count,season_count,model_status,parameters_snapshot,validation_metrics,data_quality_snapshot "
        "FROM advanced_learning_models WHERE estate_id=%s ORDER BY process_code",
        (estate_id(),),
    )
    result = {}
    for row in rows:
        for key in ("parameters_snapshot", "validation_metrics", "data_quality_snapshot"):
            row[key] = _mapping(row.get(key))
        result[str(row["process_code"])] = row
    return result


def treatment_learning_insights(target_code: str | None = None, block_id: str | None = None, crop_scope: str | None = None) -> dict[str, Any]:
    models = advanced_learning_statuses()
    target = str(target_code or "").casefold()
    effectiveness = ((models.get("treatment_effectiveness") or {}).get("parameters_snapshot") or {}).get("profiles") or []
    duration = ((models.get("product_duration") or {}).get("parameters_snapshot") or {}).get("profiles") or []
    block_profiles = ((models.get("block_disease_calibration") or {}).get("parameters_snapshot") or {}).get("profiles") or []
    selected_block = next((row for row in block_profiles if str(row.get("block_id")) == str(block_id or "")), None)
    spray_window = dict(models.get("spray_window") or {})
    spray_parameters = dict(spray_window.get("parameters_snapshot") or {})
    if crop_scope:
        spray_parameters["profiles"] = [row for row in spray_parameters.get("profiles") or [] if str(row.get("crop_scope") or "vineyard") == crop_scope]
        spray_window["parameters_snapshot"] = spray_parameters
    onset = fetch_all("SELECT disease_code,current_score,daily_slope,predicted_actionable_date,days_to_actionable,forecast_status,confidence FROM disease_onset_forecasts WHERE estate_id=%s ORDER BY predicted_actionable_date,disease_code", (estate_id(),))
    return {
        "onset": [row for row in onset if not target or str(row.get("disease_code")) == target],
        "effectiveness_profiles": [row for row in effectiveness if (not target or str(row.get("target_code")) == target) and (not crop_scope or str(row.get("crop_scope") or "vineyard") == crop_scope)],
        "duration_profiles": [row for row in duration if (not target or str(row.get("target_code")) == target) and (not crop_scope or str(row.get("crop_scope") or "vineyard") == crop_scope)],
        "rotation": models.get("resistance_rotation") or {},
        "young_vine_nutrition": models.get("young_vine_nutrition") or {},
        "block_disease_calibration": models.get("block_disease_calibration") or {},
        "spray_window": spray_window,
        "selected_block_calibration": selected_block,
    }


def apply_block_disease_calibration(prediction: dict[str, Any], block_id: str | None) -> dict[str, Any]:
    """Apply only a supported, bounded localized modifier to a copied prediction."""
    result = dict(prediction)
    insight = treatment_learning_insights(str(result.get("target_code") or ""), block_id).get("selected_block_calibration")
    adjustment = ((insight or {}).get("disease_adjustments") or {}).get(str(result.get("target_code") or "")) or {}
    comparisons = int(adjustment.get("comparisons") or 0)
    current = result.get("current_risk_score")
    if current is None or comparisons < 2:
        result["block_calibration"] = {"applied": False, "reason": "At least two comparable localized scouting labels are required.", "profile": insight}
        return result
    bounded = max(-15.0, min(15.0, float(adjustment.get("adjustment_points") or 0)))
    calibrated = max(0.0, min(100.0, float(current) + bounded))
    level = "critical" if calibrated >= 75 else "high" if calibrated >= 55 else "medium" if calibrated >= 35 else "low"
    result.update({"estate_risk_score": current, "current_risk_score": round(calibrated, 1),
                   "current_risk_level": level, "risk_level": level,
                   "block_calibration": {"applied": True, "adjustment_points": bounded, "comparisons": comparisons,
                                         "block_id": block_id, "model_version": MODEL_VERSIONS["block_disease_calibration"]}})
    return result


def resistance_rotation_review(proposed_groups: list[str], crop_scope: str = "vineyard") -> dict[str, Any]:
    model = advanced_learning_statuses().get("resistance_rotation") or {}
    parameters = model.get("parameters_snapshot") or {}
    by_crop = parameters.get("last_groups_by_crop") or {}
    last = {str(value) for value in by_crop.get(crop_scope) or parameters.get("last_groups") or []}
    proposed = {str(value) for value in proposed_groups if value}
    repeated = sorted(last & proposed)
    return {"status": "review_required" if repeated else "rotation_clear" if proposed else "groups_missing",
            "previous_groups": sorted(last), "proposed_groups": sorted(proposed), "repeated_groups": repeated,
            "message": f"Proposed program repeats FRAC group(s) {', '.join(repeated)}; Agronomist rotation review is required." if repeated else
                       "No consecutive FRAC-group repeat is detected." if proposed else "Record FRAC groups before resistance rotation can be checked.",
            "crop_scope": crop_scope, "model_version": model.get("model_version") or MODEL_VERSIONS["resistance_rotation"]}


def young_vine_nutrition_profile(block_code: str | None) -> dict[str, Any]:
    model = advanced_learning_statuses().get("young_vine_nutrition") or {}
    parameters = model.get("parameters_snapshot") or {}
    cases = [row for row in parameters.get("terraplus_cases") or [] if str(row.get("block_code")) == str(block_code or "")]
    return {"model_status": model.get("model_status") or "waiting", "model_version": model.get("model_version") or MODEL_VERSIONS["young_vine_nutrition"],
            "block_cases": cases, "comparable_outcomes": sum(row.get("outcome_status") == "comparable" for row in cases),
            "recommendation_gate": parameters.get("recommendation_gate")}
