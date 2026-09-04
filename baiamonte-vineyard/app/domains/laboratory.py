from __future__ import annotations

import json
import hashlib
import re
from datetime import date, datetime, timedelta
from statistics import mean, median
from typing import Any

from ..db import fetch_all, fetch_one, transaction
from ..lab_authoritative_manifest import AUTHORITATIVE_LAB_REPORTS
from ..service import audit, estate_id, json_ready, new_id


_LAB_FEATURE_SCHEMA = "lab-series-features-v2"
_LAB_MODEL_VERSION = "lab-vintage-learning-v2"


def _canonical_sample_name(value: Any) -> str:
    """Normalize documented label variants without merging distinct wines."""
    name = re.sub(r"\s+", " ", str(value or "Unnamed sample").strip()).casefold()
    name = name.replace("granache", "grenache")
    name = name.replace("narello", "nerello").replace("macalase", "mascalese").replace("mascalase", "mascalese")
    name = re.sub(r"\s+(?:vintage\s+)?(?:20)?(?:23|24|25|26|27)$", "", name).strip()
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    if name in {"bianco grecanico", "grecanico bianco"}:
        return "grecanico"
    if name in {"nerello", "nerello mascalese"}:
        return "nerello mascalese"
    return name or "unnamed sample"


def _sample_display_name(value: Any) -> str:
    canonical = _canonical_sample_name(value)
    known = {
        "grecanico": "Grecanico",
        "grenache": "Grenache",
        "nerello": "Nerello",
        "nerello mascalese": "Nerello Mascalese",
    }
    return known.get(canonical, canonical.title())


def cellar_laboratory_evidence(
    tanks: list[dict[str, Any]],
    year: int,
    *,
    include_name_matches: bool = True,
) -> None:
    """Attach same-lot wine laboratory evidence to cellar tanks in place.

    A foreign-key lot match is authoritative. Older reports without that link
    may be displayed as probable evidence only when their normalized wine
    identity, vintage, and batch date are compatible.
    """
    if not tanks:
        return
    rows = fetch_all(
        "SELECT s.id sample_id,s.wine_lot_id,s.sample_code,s.sample_name,s.source_sample_name,s.canonical_sample_name,s.sample_type,s.sampled_at,s.lab_date,s.laboratory,s.source_document,s.needs_review,s.review_notes,"
        "COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) vintage_year,s.vintage_assignment_confidence,"
        "lr.review_status,lr.interpretation,lr.decision_action,lr.approved_by,lr.approved_at,"
        "r.id result_id,r.analyte_code,r.analyte_name,r.numeric_value,r.text_value,r.unit,r.flag "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN lab_reviews lr ON lr.sample_id=s.id "
        "LEFT JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s "
        "AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date))=%s "
        "AND (s.sample_type IN ('must','wine','other') OR s.wine_lot_id IS NOT NULL) "
        "ORDER BY s.lab_date DESC,s.sampled_at DESC,s.id,r.analyte_name",
        (estate_id(), year),
    )
    samples: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = str(row.get("sample_id") or "")
        if not sample_id:
            continue
        sample = samples.setdefault(sample_id, {
            key: row.get(key) for key in (
                "sample_id", "wine_lot_id", "sample_code", "sample_name", "source_sample_name",
                "canonical_sample_name", "sample_type", "sampled_at", "lab_date", "laboratory",
                "source_document", "needs_review", "review_notes", "vintage_year",
                "vintage_assignment_confidence", "review_status", "interpretation", "decision_action",
                "approved_by", "approved_at",
            )
        })
        sample.setdefault("results", [])
        if row.get("result_id"):
            sample["results"].append({
                key: row.get(key) for key in (
                    "result_id", "analyte_code", "analyte_name", "numeric_value", "text_value", "unit", "flag",
                )
            })

    def code(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

    tank_identities: dict[str, set[str]] = {}
    identity_tank_counts: dict[str, int] = {}
    for tank in tanks:
        identities = {
            _canonical_sample_name(value)
            for value in (
                tank.get("variety_summary"), tank.get("lot_name"),
                (tank.get("plaato") or {}).get("batch_name"),
            )
            if value
        } - {"unnamed sample"}
        tank_identities[str(tank.get("id") or id(tank))] = identities
        for identity in identities:
            identity_tank_counts[identity] = identity_tank_counts.get(identity, 0) + 1

    for tank in tanks:
        identities = tank_identities[str(tank.get("id") or id(tank))]
        tank_codes = {
            code(tank.get("code")),
            code(tank.get("lot_code")),
            code(tank.get("wine_lot_code")),
        } - {""}
        started = _as_date(tank.get("started_at") or (tank.get("plaato") or {}).get("batch_start"))
        matched: list[dict[str, Any]] = []
        for sample in samples.values():
            method = None
            confidence = None
            evidence = None
            if tank.get("wine_lot_id") and sample.get("wine_lot_id") == tank.get("wine_lot_id"):
                method, confidence, evidence = "wine_lot", "confirmed", "Laboratory sample is linked to this exact wine lot."
            elif code(sample.get("sample_code")) in tank_codes and code(sample.get("sample_code")):
                method, confidence, evidence = "lot_or_tank_code", "confirmed", "Laboratory sample code matches this lot or tank code."
            elif include_name_matches:
                canonical = _canonical_sample_name(sample.get("canonical_sample_name") or sample.get("source_sample_name") or sample.get("sample_name"))
                lab_date = _as_date(sample.get("sampled_at") or sample.get("lab_date"))
                date_compatible = not started or not lab_date or lab_date >= started - timedelta(days=14)
                if canonical in identities and date_compatible:
                    method = "normalized_wine_identity"
                    if identity_tank_counts.get(canonical, 0) == 1:
                        confidence = "probable"
                        evidence = "Normalized wine identity and vintage match; confirm the wine-lot link before treating this report as authoritative."
                    else:
                        confidence = "ambiguous"
                        evidence = "Wine identity and vintage match more than one tank; link the report to its wine lot before sensor comparison."
            if not method:
                continue
            item = dict(sample)
            item.update({
                "match_method": method,
                "match_confidence": confidence,
                "match_evidence": evidence,
                "authoritative_for_tank": bool(confidence == "confirmed" and not sample.get("needs_review")),
            })
            matched.append(item)
        matched.sort(key=lambda item: (str(item.get("sampled_at") or item.get("lab_date") or ""), str(item.get("sample_id") or "")), reverse=True)
        tank["laboratory_evidence"] = {
            "samples": matched[:24],
            "sample_count": len(matched),
            "confirmed_count": sum(item.get("match_confidence") == "confirmed" for item in matched),
            "probable_count": sum(item.get("match_confidence") == "probable" for item in matched),
            "ambiguous_count": sum(item.get("match_confidence") == "ambiguous" for item in matched),
            "authoritative_count": sum(bool(item.get("authoritative_for_tank")) for item in matched),
            "guardrail": "Only reviewed reports linked by wine lot or exact lot/tank code are authoritative for this tank. Name-based matches remain probable until confirmed.",
        }


def _series_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Keep projections within one physical sample/result definition."""
    sample_name = _canonical_sample_name(row.get("sample_name"))
    return (
        sample_name,
        str(row.get("sample_type") or "other").casefold(),
        str(row.get("stage") or "unspecified").strip().casefold(),
        str(row.get("analyte_code") or "").casefold(),
        str(row.get("unit") or "").strip().casefold(),
    )


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _project_lab_series(rows: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    """Build like-for-like vintage endpoint projections from measured evidence.

    The historical baseline is deliberately the final measured result in each
    prior vintage, not the average of every reading taken during that vintage.
    """
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("numeric_value") is None or not _as_date(row.get("lab_date")):
            continue
        groups.setdefault(_series_key(row), []).append(row)
    output: list[dict[str, Any]] = []
    for group_rows in groups.values():
        by_year: dict[int, list[dict[str, Any]]] = {}
        for row in group_rows:
            vintage = int(row.get("vintage_year") or 0)
            if vintage:
                by_year.setdefault(vintage, []).append(row)
        for vintage_rows in by_year.values():
            vintage_rows.sort(key=lambda row: (_as_date(row.get("lab_date")) or date.min, str(row.get("result_id") or "")))
        current = by_year.get(year, [])
        if not current:
            continue
        prior = {vintage: values for vintage, values in by_year.items() if vintage < year and values}
        endpoints = [values[-1] for _, values in sorted(prior.items())]
        endpoint_values = [float(row["numeric_value"]) for row in endpoints]
        endpoint_days: list[int] = []
        for values in prior.values():
            first_date, last_date = _as_date(values[0]["lab_date"]), _as_date(values[-1]["lab_date"])
            if first_date and last_date:
                endpoint_days.append((last_date - first_date).days)
        current_first = _as_date(current[0]["lab_date"])
        current_last = _as_date(current[-1]["lab_date"])
        current_day = (current_last - current_first).days if current_first and current_last else 0
        comparable_values: list[float] = []
        for values in prior.values():
            first_date = _as_date(values[0]["lab_date"])
            candidates = []
            for row in values:
                row_date = _as_date(row["lab_date"])
                if first_date and row_date:
                    candidates.append((abs((row_date - first_date).days - current_day), row))
            if candidates:
                distance, comparable = min(candidates, key=lambda item: item[0])
                if distance <= 21:
                    comparable_values.append(float(comparable["numeric_value"]))
        latest_value = float(current[-1]["numeric_value"])
        current_days = [(_as_date(row["lab_date"]) - current_first).days for row in current] if current_first else []
        current_values = [float(row["numeric_value"]) for row in current]
        slope_per_day = None
        if len(current_days) >= 2 and len(set(current_days)) >= 2:
            x_average, y_average = mean(current_days), mean(current_values)
            denominator = sum((value - x_average) ** 2 for value in current_days)
            if denominator:
                slope_per_day = sum((x - x_average) * (y - y_average) for x, y in zip(current_days, current_values)) / denominator
        endpoint_average = mean(endpoint_values) if endpoint_values else None
        stage_average = mean(comparable_values) if comparable_values else None
        adjustment = latest_value - stage_average if stage_average is not None else 0.0
        # Laboratory measurements cannot be negative. A large vintage-stage
        # adjustment can mathematically cross zero, so constrain the displayed
        # forecast while retaining the measured adjustment in the evidence.
        projected = max(0.0, endpoint_average + adjustment) if endpoint_average is not None else None
        projected_date = None
        if current_first and endpoint_days:
            projected_date = date.fromordinal(current_first.toordinal() + int(round(median(endpoint_days)))).isoformat()
        lower = max(0.0, min(endpoint_values) + adjustment) if len(endpoint_values) >= 2 else None
        upper = max(0.0, max(endpoint_values) + adjustment) if len(endpoint_values) >= 2 else None
        evidence_score = len(current) + min(len(endpoints), 3) + min(len(comparable_values), 2)
        if projected is None:
            confidence, confidence_reason = "not_available", "No matching prior-vintage endpoint is recorded."
        elif evidence_score >= 8 and len(endpoints) >= 3:
            confidence, confidence_reason = "high", f"{len(current)} current readings and {len(endpoints)} matching prior vintages."
        elif evidence_score >= 5 and len(endpoints) >= 2:
            confidence, confidence_reason = "medium", f"{len(current)} current readings and {len(endpoints)} matching prior vintages."
        else:
            confidence, confidence_reason = "low", f"Only {len(current)} current reading(s) and {len(endpoints)} matching prior vintage(s)."
        latest = current[-1]
        target_min = float(latest["target_min"]) if latest.get("target_min") is not None else None
        target_max = float(latest["target_max"]) if latest.get("target_max") is not None else None
        projected_status = "unconfigured"
        if projected is not None and (target_min is not None or target_max is not None):
            projected_status = "below" if target_min is not None and projected < target_min else "above" if target_max is not None and projected > target_max else "within"
        ai_value, ai_date, ai_method, ai_confidence = projected, projected_date, "like_for_like_vintage_model", confidence
        if ai_value is None and slope_per_day is not None and current_last:
            ai_value = max(0.0, latest_value + slope_per_day * 14)
            ai_date = (current_last + timedelta(days=14)).isoformat()
            ai_method, ai_confidence = "current_trajectory_14_day", "low"
        ai_status = "unconfigured"
        if ai_value is not None and (target_min is not None or target_max is not None):
            ai_status = "below" if target_min is not None and ai_value < target_min else "above" if target_max is not None and ai_value > target_max else "within"
        ai_drivers = [f"{len(current)} current measured result(s)", f"{len(endpoints)} exact prior-vintage endpoint(s)"]
        if slope_per_day is not None:
            ai_drivers.append(f"Measured current slope {slope_per_day:+.4f} per day")
        if target_min is not None or target_max is not None:
            ai_drivers.append("Approved marker range is shown separately and is not treated as a measurement")
        if any(bool(row.get("needs_review")) for row in current):
            ai_drivers.append("Source review remains required")
        first = current[0]
        output.append({
            "id": "|".join(_series_key(first)),
            "sample_name": _sample_display_name(first.get("sample_name")),
            "sample_type": first.get("sample_type"),
            "stage": first.get("stage"),
            "analyte_code": first.get("analyte_code"),
            "analyte_name": first.get("analyte_name"),
            "unit": first.get("unit"),
            "latest_value": latest_value,
            "latest_date": str(latest.get("lab_date"))[:10],
            "previous_value": float(current[-2]["numeric_value"]) if len(current) > 1 else None,
            "current_points": [{"date": str(row["lab_date"])[:10], "day": (_as_date(row["lab_date"]) - current_first).days if current_first else 0, "value": float(row["numeric_value"]), "flag": row.get("comparison_flag"), "sample_id": row.get("sample_id"), "report_url": row.get("report_url"), "source_document": row.get("source_document"), "laboratory": row.get("laboratory")} for row in current],
            "historical_series": [{"vintage_year": vintage, "points": [{"date": str(row["lab_date"])[:10], "day": (_as_date(row["lab_date"]) - _as_date(values[0]["lab_date"])).days, "value": float(row["numeric_value"]), "sample_id": row.get("sample_id"), "report_url": row.get("report_url"), "source_document": row.get("source_document"), "laboratory": row.get("laboratory")} for row in values]} for vintage, values in sorted(prior.items())],
            "historical_endpoints": [{"vintage_year": int(row["vintage_year"]), "date": str(row["lab_date"])[:10], "value": float(row["numeric_value"]), "sample_id": row.get("sample_id"), "report_url": row.get("report_url"), "source_document": row.get("source_document"), "laboratory": row.get("laboratory")} for row in endpoints],
            "historical_endpoint_average": endpoint_average,
            "same_relative_day_average": stage_average,
            "projection_adjustment": adjustment if stage_average is not None else None,
            "projected_endpoint": projected,
            "projected_endpoint_date": projected_date,
            "projection_low": lower,
            "projection_high": upper,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "target_min": target_min,
            "target_max": target_max,
            "target_source": latest.get("source_reference"),
            "projected_status": projected_status,
            "current_result_count": len(current),
            "historical_vintage_count": len(endpoints),
            "needs_review": any(bool(row.get("needs_review")) for row in current),
            "ai_projection": {
                "value": ai_value,
                "date": ai_date,
                "method": ai_method if ai_value is not None else "insufficient_measured_trajectory",
                "confidence": ai_confidence if ai_value is not None else "not_available",
                "status": ai_status,
                "slope_per_day": slope_per_day,
                "drivers": ai_drivers,
                "approved_marker_min": target_min,
                "approved_marker_max": target_max,
                "recalculation": "Calculated from current database measurements on every Laboratory outlook refresh.",
                "decision_boundary": "Decision support only; no cellar or harvest action is approved automatically.",
            },
        })
    return sorted(output, key=lambda row: (str(row["sample_name"]), str(row["analyte_name"]), str(row["unit"])))


def normalize_historical_lab_samples() -> dict[str, Any]:
    """Persist canonical identities while retaining every original report label."""
    rows = fetch_all(
        "SELECT id,sample_name,source_sample_name,canonical_sample_name FROM lab_samples WHERE estate_id=%s",
        (estate_id(),),
    )
    changed = 0
    with transaction() as (_, cursor):
        for row in rows:
            source_name = str(row.get("source_sample_name") or row.get("sample_name") or "Unnamed sample").strip()
            canonical = _canonical_sample_name(source_name)
            display = _sample_display_name(source_name)
            if row.get("source_sample_name") != source_name or row.get("canonical_sample_name") != canonical or row.get("sample_name") != display:
                cursor.execute(
                    "UPDATE lab_samples SET source_sample_name=%s,canonical_sample_name=%s,sample_name=%s WHERE id=%s AND estate_id=%s",
                    (source_name, canonical, display, row["id"], estate_id()),
                )
                audit(cursor, "normalize_identity", "lab_sample", row["id"], {
                    "source_sample_name": source_name, "canonical_sample_name": canonical, "sample_name": display,
                    "rule": "Original report label retained; canonical identity used for like-for-like historical learning.",
                }, "laboratory-learning")
                changed += 1
    return {"samples_checked": len(rows), "samples_normalized": changed, "original_labels_preserved": True}


def _lab_learning_source_rows() -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT c.*,c.wine_stage stage,s.needs_review,s.source_document,s.laboratory,s.vintage_assignment_confidence,"
        "COALESCE(s.vintage_year,se.vintage_year,c.vintage_year) authoritative_vintage_year "
        "FROM v_lab_comparison c JOIN lab_samples s ON s.id=c.sample_id LEFT JOIN seasons se ON se.id=s.season_id "
        "WHERE c.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,c.vintage_year) IS NOT NULL "
        "AND c.numeric_value IS NOT NULL ORDER BY c.sample_name,c.sample_type,c.wine_stage,c.analyte_code,c.unit,"
        "COALESCE(s.vintage_year,se.vintage_year,c.vintage_year),c.lab_date,c.result_id",
        (estate_id(),),
    )
    for row in rows:
        authoritative_vintage = row.pop("authoritative_vintage_year", None)
        if authoritative_vintage is not None:
            row["vintage_year"] = int(authoritative_vintage)
    return rows


def _direction_matches(start: float, projected: float, actual: float) -> bool:
    projected_delta, actual_delta = projected - start, actual - start
    return (projected_delta == 0 and actual_delta == 0) or (projected_delta > 0 and actual_delta > 0) or (projected_delta < 0 and actual_delta < 0)


def refresh_lab_learning(sample_id: str | None = None) -> dict[str, Any]:
    """Normalize, backtest, and persist the laboratory model after new evidence.

    Each historical case is walk-forward: its input includes prior vintages and
    measurements available through the cutoff result only. A later measurement
    from the same exact series becomes the outcome and is never leaked backward.
    """
    normalization = normalize_historical_lab_samples()
    rows = _lab_learning_source_rows()
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_series_key(row), []).append(row)
    generated_cases: list[dict[str, Any]] = []
    generated_outcomes: list[dict[str, Any]] = []
    for series_key, group_rows in groups.items():
        ordered = sorted(group_rows, key=lambda row: (int(row.get("vintage_year") or 0), _as_date(row.get("lab_date")) or date.min, str(row.get("result_id") or "")))
        for cutoff in ordered:
            vintage = int(cutoff.get("vintage_year") or 0)
            cutoff_date = _as_date(cutoff.get("lab_date"))
            if not vintage or not cutoff_date:
                continue
            eligible = [
                row for row in ordered
                if int(row.get("vintage_year") or 0) < vintage
                or (int(row.get("vintage_year") or 0) == vintage and (_as_date(row.get("lab_date")) or date.max) <= cutoff_date)
            ]
            projection_rows = _project_lab_series(eligible, vintage)
            projected = next((row for row in projection_rows if row["id"] == "|".join(series_key)), None)
            ai = (projected or {}).get("ai_projection") or {}
            input_rows = [{"result_id": row.get("result_id"), "vintage_year": row.get("vintage_year"), "lab_date": row.get("lab_date"), "numeric_value": row.get("numeric_value"), "needs_review": bool(row.get("needs_review"))} for row in eligible]
            signature = hashlib.sha256(json.dumps(json_ready(input_rows), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            status = "source_review" if any(bool(row.get("needs_review")) for row in eligible if int(row.get("vintage_year") or 0) == vintage) else "prediction_available" if ai.get("value") is not None else "insufficient_comparable_history"
            case = {
                "id": new_id(), "cutoff_result_id": cutoff["result_id"], "cutoff_sample_id": cutoff["sample_id"],
                "cutoff_date": cutoff_date, "vintage_year": vintage, "canonical_sample_name": series_key[0],
                "sample_type": series_key[1], "process_stage": series_key[2], "analyte_code": series_key[3], "unit": series_key[4],
                "series_key": "|".join(series_key), "input_signature": signature, "input_snapshot": input_rows,
                "projection_value": ai.get("value"), "projection_date": _as_date(ai.get("date")),
                "projection_method": ai.get("method") or "insufficient_measured_trajectory",
                "projection_confidence": ai.get("confidence") or "not_available",
                "current_result_count": int((projected or {}).get("current_result_count") or 0),
                "prior_vintage_count": int((projected or {}).get("historical_vintage_count") or 0),
                "learning_status": status,
            }
            generated_cases.append(case)
            later = [row for row in ordered if int(row.get("vintage_year") or 0) == vintage and (_as_date(row.get("lab_date")) or date.min) > cutoff_date]
            if later:
                if ai.get("method") == "current_trajectory_14_day":
                    target_date = _as_date(ai.get("date"))
                    ranked = sorted(later, key=lambda row: abs(((_as_date(row.get("lab_date")) or date.max) - (target_date or cutoff_date)).days))
                    actual = ranked[0]
                    if target_date and abs(((_as_date(actual.get("lab_date")) or target_date) - target_date).days) > 21:
                        continue
                    evaluation_kind = "14-day horizon measurement"
                else:
                    actual = later[-1]
                    evaluation_kind = "final later vintage measurement"
                actual_value = float(actual["numeric_value"])
                projection_value = float(ai["value"]) if ai.get("value") is not None else None
                signed_error = actual_value - projection_value if projection_value is not None else None
                absolute_error = abs(signed_error) if signed_error is not None else None
                percentage_error = absolute_error / abs(actual_value) * 100 if absolute_error is not None and actual_value != 0 else None
                generated_outcomes.append({
                    "case_cutoff_result_id": cutoff["result_id"], "actual_result_id": actual["result_id"], "actual_sample_id": actual["sample_id"],
                    "actual_date": _as_date(actual["lab_date"]), "actual_value": actual_value,
                    "forecast_horizon_days": ((_as_date(actual["lab_date"]) or cutoff_date) - cutoff_date).days,
                    "signed_error": signed_error, "absolute_error": absolute_error, "absolute_percentage_error": percentage_error,
                    "direction_correct": _direction_matches(float(cutoff["numeric_value"]), projection_value, actual_value) if projection_value is not None else None,
                    "outcome_status": "observed" if projection_value is not None else "unscored_insufficient_history",
                    "evaluation_kind": evaluation_kind,
                    "analyte_code": series_key[3], "unit": series_key[4],
                    "vintage_year": vintage,
                })
    with transaction() as (_, cursor):
        for case in generated_cases:
            cursor.execute(
                "INSERT INTO lab_learning_cases (id,estate_id,cutoff_result_id,cutoff_sample_id,cutoff_date,vintage_year,canonical_sample_name,sample_type,process_stage,analyte_code,unit,series_key,input_signature,input_snapshot,projection_value,projection_date,projection_method,projection_confidence,current_result_count,prior_vintage_count,feature_schema_version,model_version,learning_status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE cutoff_sample_id=VALUES(cutoff_sample_id),cutoff_date=VALUES(cutoff_date),vintage_year=VALUES(vintage_year),canonical_sample_name=VALUES(canonical_sample_name),sample_type=VALUES(sample_type),process_stage=VALUES(process_stage),analyte_code=VALUES(analyte_code),unit=VALUES(unit),series_key=VALUES(series_key),input_signature=VALUES(input_signature),input_snapshot=VALUES(input_snapshot),projection_value=VALUES(projection_value),projection_date=VALUES(projection_date),projection_method=VALUES(projection_method),projection_confidence=VALUES(projection_confidence),current_result_count=VALUES(current_result_count),prior_vintage_count=VALUES(prior_vintage_count),feature_schema_version=VALUES(feature_schema_version),model_version=VALUES(model_version),learning_status=VALUES(learning_status),learned_at=CURRENT_TIMESTAMP(6)",
                (case["id"], estate_id(), case["cutoff_result_id"], case["cutoff_sample_id"], case["cutoff_date"], case["vintage_year"], case["canonical_sample_name"], case["sample_type"], case["process_stage"], case["analyte_code"], case["unit"], case["series_key"], case["input_signature"], json.dumps(json_ready(case["input_snapshot"])), case["projection_value"], case["projection_date"], case["projection_method"], case["projection_confidence"], case["current_result_count"], case["prior_vintage_count"], _LAB_FEATURE_SCHEMA, _LAB_MODEL_VERSION, case["learning_status"]),
            )
        for outcome in generated_outcomes:
            cursor.execute("SELECT id FROM lab_learning_cases WHERE cutoff_result_id=%s", (outcome["case_cutoff_result_id"],))
            stored_case = cursor.fetchone()
            if not stored_case:
                continue
            summary = f"Walk-forward projection evaluated {outcome['forecast_horizon_days']} days later against the {outcome['evaluation_kind']} in the same exact series."
            cursor.execute(
                "INSERT INTO lab_learning_outcomes (id,estate_id,learning_case_id,actual_result_id,actual_sample_id,actual_date,actual_value,forecast_horizon_days,signed_error,absolute_error,absolute_percentage_error,direction_correct,outcome_status,outcome_summary,model_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE actual_result_id=VALUES(actual_result_id),actual_sample_id=VALUES(actual_sample_id),actual_date=VALUES(actual_date),actual_value=VALUES(actual_value),forecast_horizon_days=VALUES(forecast_horizon_days),signed_error=VALUES(signed_error),absolute_error=VALUES(absolute_error),absolute_percentage_error=VALUES(absolute_percentage_error),direction_correct=VALUES(direction_correct),outcome_status=VALUES(outcome_status),outcome_summary=VALUES(outcome_summary),model_version=VALUES(model_version),learned_at=CURRENT_TIMESTAMP(6)",
                (new_id(), estate_id(), stored_case["id"], outcome["actual_result_id"], outcome["actual_sample_id"], outcome["actual_date"], outcome["actual_value"], outcome["forecast_horizon_days"], outcome["signed_error"], outcome["absolute_error"], outcome["absolute_percentage_error"], outcome["direction_correct"], outcome["outcome_status"], summary, _LAB_MODEL_VERSION),
            )
    scored = [row for row in generated_outcomes if row["outcome_status"] == "observed" and row["absolute_error"] is not None]
    represented_vintages = sorted({case["vintage_year"] for case in generated_cases})
    observed_vintages = sorted({row["vintage_year"] for row in scored})
    metric_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in scored:
        metric_groups.setdefault((row["analyte_code"], row["unit"]), []).append(row)
    by_measurement = [{
        "analyte_code": key[0], "unit": key[1], "case_count": len(values),
        "mean_absolute_error": mean([row["absolute_error"] for row in values]),
        "signed_bias": mean([row["signed_error"] for row in values]),
    } for key, values in sorted(metric_groups.items())]
    mae = by_measurement[0]["mean_absolute_error"] if len(by_measurement) == 1 else None
    bias = by_measurement[0]["signed_bias"] if len(by_measurement) == 1 else None
    direction_accuracy = 100 * mean([1.0 if row["direction_correct"] else 0.0 for row in scored]) if scored else None
    coverage_ready = len(scored) >= 8 and len(observed_vintages) >= 2
    status = (
        "validated_walk_forward" if coverage_ready and direction_accuracy is not None and direction_accuracy >= 60 else
        "learning_active_low_accuracy" if coverage_ready else
        "provisional_walk_forward"
    )
    sample_quality = fetch_one(
        "SELECT COUNT(*) sample_count,SUM(needs_review) review_count,SUM(vintage_assignment_confidence='inferred') inferred_vintage_count,"
        "SUM(source_document IS NULL OR TRIM(source_document)='') missing_source_count FROM lab_samples WHERE estate_id=%s",
        (estate_id(),),
    ) or {}
    metrics = {"mean_absolute_error": mae, "signed_bias": bias, "mae_by_analyte_unit": by_measurement, "direction_accuracy_pct": direction_accuracy, "observed_walk_forward_cases": len(scored), "observed_vintages": observed_vintages, "validation_direction_threshold_pct": 60, "method": "Historical walk-forward; future measurements are excluded from every prediction input. Absolute errors are never averaged across unlike analytes or units."}
    quality = {**json_ready(sample_quality), "numeric_result_count": len(rows), "exact_series_count": len(groups), "represented_vintages": represented_vintages, "minimum_validation_cases": 8, "minimum_validation_vintages": 2}
    parameters = {"matching_rule": "canonical sample + sample type + process stage + analyte + unit", "historical_baseline": "final measured endpoint per prior vintage", "current_adjustment": "difference from matching prior readings at the same relative day", "fallback": "14-day current measured slope", "source_sample_id": sample_id}
    data_through = max((_as_date(row.get("lab_date")) for row in rows if _as_date(row.get("lab_date"))), default=None)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO lab_learning_models (id,estate_id,model_version,feature_schema_version,trained_at,data_through,normalized_sample_count,numeric_result_count,projection_case_count,observed_outcome_count,represented_vintage_count,model_status,parameters_snapshot,validation_metrics,data_quality_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE trained_at=VALUES(trained_at),data_through=VALUES(data_through),normalized_sample_count=VALUES(normalized_sample_count),numeric_result_count=VALUES(numeric_result_count),projection_case_count=VALUES(projection_case_count),observed_outcome_count=VALUES(observed_outcome_count),represented_vintage_count=VALUES(represented_vintage_count),model_status=VALUES(model_status),parameters_snapshot=VALUES(parameters_snapshot),validation_metrics=VALUES(validation_metrics),data_quality_snapshot=VALUES(data_quality_snapshot)",
            (new_id(), estate_id(), _LAB_MODEL_VERSION, _LAB_FEATURE_SCHEMA, datetime.now(), data_through, normalization["samples_checked"], len(rows), len(generated_cases), len(scored), len(represented_vintages), status, json.dumps(json_ready(parameters)), json.dumps(json_ready(metrics)), json.dumps(json_ready(quality))),
        )
    return {"normalization": normalization, "model_version": _LAB_MODEL_VERSION, "model_status": status, "projection_cases": len(generated_cases), "observed_outcomes": len(scored), "validation": metrics, "data_quality": quality}


def lab_learning_status() -> dict[str, Any]:
    row = fetch_one(
        "SELECT model_version,feature_schema_version,trained_at,data_through,normalized_sample_count,numeric_result_count,projection_case_count,observed_outcome_count,represented_vintage_count,model_status,parameters_snapshot,validation_metrics,data_quality_snapshot FROM lab_learning_models WHERE estate_id=%s ORDER BY trained_at DESC LIMIT 1",
        (estate_id(),),
    ) or {}
    for key in ("parameters_snapshot", "validation_metrics", "data_quality_snapshot"):
        if isinstance(row.get(key), str):
            try:
                row[key] = json.loads(row[key])
            except (TypeError, ValueError):
                row[key] = {}
    return row


def _lab_current_finding(rows: list[dict[str, Any]], series: list[dict[str, Any]], year: int) -> dict[str, Any]:
    """Summarize the newest current-vintage report from measured evidence."""
    current = [row for row in rows if int(row.get("vintage_year") or 0) == year and _as_date(row.get("lab_date"))]
    if not current:
        return {
            "status": "source_needed",
            "headline": "No current laboratory finding",
            "summary": f"No numeric laboratory report is recorded for vintage {year}.",
            "findings": [],
            "decision_boundary": "No laboratory value, projection, or cellar action is inferred without measured source evidence.",
        }
    latest_date = max(_as_date(row["lab_date"]) for row in current)
    latest_rows = [row for row in current if _as_date(row["lab_date"]) == latest_date]
    sample_ids = {str(row.get("sample_id")) for row in latest_rows}
    report_series = {"|".join(_series_key(row)) for row in latest_rows}
    modeled = [row for row in series if row["id"] in report_series and row.get("ai_projection", {}).get("value") is not None]
    flagged = [row for row in latest_rows if str(row.get("comparison_flag") or "normal") in {"review", "low", "high"}]
    needs_review = any(bool(row.get("needs_review")) for row in latest_rows)
    findings = [{
        "sample_name": _sample_display_name(row.get("sample_name")),
        "analyte_name": row.get("analyte_name") or row.get("analyte_code"),
        "value": float(row["numeric_value"]),
        "unit": row.get("unit"),
        "status": row.get("comparison_flag") or "normal",
        "marker_min": float(row["target_min"]) if row.get("target_min") is not None else None,
        "marker_max": float(row["target_max"]) if row.get("target_max") is not None else None,
    } for row in flagged[:8]]
    status = "source_review" if needs_review else "review" if flagged else "monitor"
    headline = "Source review required for the newest report" if needs_review else f"{len(flagged)} newest-report result{'s' if len(flagged) != 1 else ''} need attention" if flagged else "No recorded review-rule alert in the newest report"
    summary = f"{len(sample_ids)} sample{'s' if len(sample_ids) != 1 else ''}, {len(latest_rows)} numeric result{'s' if len(latest_rows) != 1 else ''}, and {len(modeled)} evidence projection{'s' if len(modeled) != 1 else ''} were evaluated."
    source_documents = sorted({str(row.get("source_document")) for row in latest_rows if row.get("source_document")})
    laboratories = sorted({str(row.get("laboratory")) for row in latest_rows if row.get("laboratory")})
    return {
        "status": status,
        "headline": headline,
        "summary": summary,
        "report_date": latest_date.isoformat(),
        "laboratory": ", ".join(laboratories) or None,
        "source_documents": source_documents,
        "findings": findings,
        "projection_note": "Projections were recalculated from all source-backed measurements after this report arrived.",
        "marker_note": "Known markers are comparison guides and are never substituted for measured values.",
        "decision_boundary": "AI-assisted interpretation only; no cellar, harvest, or treatment action is approved automatically.",
    }


def _variety_lab_standards(series: list[dict[str, Any]], varieties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose recorded markers by estate variety without inventing standards."""
    output: list[dict[str, Any]] = []
    for variety in varieties:
        name = str(variety.get("name") or "").strip()
        canonical = _canonical_sample_name(name)
        matching = [
            row for row in series
            if _canonical_sample_name(row.get("sample_name")) == canonical
            or canonical in _canonical_sample_name(row.get("sample_name"))
        ]
        standards = [{
            "analyte_code": row.get("analyte_code"),
            "analyte_name": row.get("analyte_name"),
            "sample_type": row.get("sample_type"),
            "stage": row.get("stage"),
            "minimum": row.get("target_min"),
            "maximum": row.get("target_max"),
            "unit": row.get("unit"),
            "source": row.get("target_source"),
        } for row in matching if row.get("target_min") is not None or row.get("target_max") is not None]
        unique = {
            (row["analyte_code"], row["sample_type"], row["stage"], row["unit"], row["minimum"], row["maximum"]): row
            for row in standards
        }
        output.append({
            "variety_name": _sample_display_name(name),
            "standards": sorted(unique.values(), key=lambda row: (str(row["sample_type"]), str(row["stage"]), str(row["analyte_name"]))),
            "measured_series_count": len(matching),
            "status": "recorded" if unique else "not_recorded",
        })
    return output


def _lab_source_audit() -> dict[str, Any]:
    sources = fetch_all(
        "SELECT id,title,original_filename,file_sha256,classification,extracted_data,review_status FROM intake_items "
        "WHERE estate_id=%s AND (classification='lab_report' OR extracted_data LIKE '%%lab%%') ORDER BY received_at",
        (estate_id(),),
    )
    links = fetch_all(
        "SELECT file_sha256,COUNT(DISTINCT entity_id) linked_samples FROM entity_attachments "
        "WHERE estate_id=%s AND entity_type='lab_sample' AND file_sha256 IS NOT NULL GROUP BY file_sha256",
        (estate_id(),),
    )
    linked_by_hash = {row["file_sha256"]: int(row["linked_samples"] or 0) for row in links}
    findings: list[dict[str, Any]] = []
    for source in sources:
        extracted = source.get("extracted_data") or {}
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except json.JSONDecodeError:
                extracted = {}
        records = extracted.get("suggested_database_records") if isinstance(extracted, dict) else []
        records = records if isinstance(records, list) else []
        lab_records = [record for record in records if isinstance(record, dict) and "lab" in str(record.get("destination_section") or record.get("section") or record.get("record_type") or "").casefold()]
        # Generic messages can mention a laboratory or lab result without being a
        # report awaiting sample import. Keep those out of the laboratory audit;
        # only an explicit lab classification may appear without extracted rows.
        if not lab_records and source.get("classification") != "lab_report":
            continue
        expected, merged = 0, False
        for record in lab_records:
            fields = record.get("fields") or record.get("values") or {}
            results = fields.get("results") if isinstance(fields.get("results"), list) else []
            labels = {str(item.get("sample_name") or item.get("source_sample_label") or item.get("variety_name") or item.get("wine_type") or "").strip().casefold() for item in results if isinstance(item, dict)} - {""}
            names = [name.strip() for name in re.split(r"\s*(?:/|\+|,|;|\band\b|\be\b)\s*", str(fields.get("sample_name") or fields.get("source_sample_label") or ""), flags=re.IGNORECASE) if name.strip()]
            physical = max(1, len(labels), len(names) if len(names) == len(results) else 0)
            expected += physical
            merged = merged or physical > 1
        linked = linked_by_hash.get(source.get("file_sha256"), 0)
        if not lab_records or linked < expected or merged:
            findings.append({"intake_id": source["id"], "source_name": source.get("original_filename") or source.get("title") or "Laboratory source", "expected_samples": expected, "linked_samples": linked, "merged_draft": merged, "status": "needs_reanalysis" if not lab_records or merged else "missing_samples"})
    duplicates = fetch_all(
        "SELECT sample_type,lab_date,MIN(sample_name) sample_name,vintage_year,MIN(laboratory) laboratory,COUNT(*) duplicate_count FROM lab_samples "
        "WHERE estate_id=%s GROUP BY sample_type,lab_date,LOWER(TRIM(sample_name)),vintage_year,LOWER(TRIM(laboratory)) HAVING COUNT(*)>1",
        (estate_id(),),
    )
    stored = fetch_all(
        "SELECT s.lab_date,s.vintage_year,s.sample_type,s.sample_name,COUNT(r.id) result_count FROM lab_samples s LEFT JOIN lab_results r ON r.sample_id=s.id WHERE s.estate_id=%s GROUP BY s.id,s.lab_date,s.vintage_year,s.sample_type,s.sample_name",
        (estate_id(),),
    )
    manifest_findings: list[dict[str, Any]] = []
    for report_date, vintage, sample_type, expected_samples in AUTHORITATIVE_LAB_REPORTS:
        for sample_name, result_count in expected_samples:
            matches = [
                row for row in stored
                if str(row.get("lab_date"))[:10] == report_date
                and _canonical_sample_name(row.get("sample_name")) == _canonical_sample_name(sample_name)
            ]
            exact = [row for row in matches if vintage is None or int(row.get("vintage_year") or 0) == vintage]
            row = exact[0] if exact else (matches[0] if matches else None)
            wrong_type = bool(row and str(row.get("sample_type") or "").casefold() != str(sample_type).casefold())
            if not row or int(row.get("result_count") or 0) < result_count or (vintage is not None and int(row.get("vintage_year") or 0) != vintage) or wrong_type:
                status = (
                    "missing_sample" if not row else
                    "incomplete_results" if int(row.get("result_count") or 0) < result_count else
                    "wrong_vintage" if vintage is not None and int(row.get("vintage_year") or 0) != vintage else
                    "wrong_sample_type"
                )
                manifest_findings.append({
                    "report_date": report_date,
                    "vintage_year": vintage,
                    "sample_type": sample_type,
                    "stored_sample_type": row.get("sample_type") if row else None,
                    "sample_name": sample_name,
                    "expected_results": result_count,
                    "stored_results": int(row.get("result_count") or 0) if row else 0,
                    "status": status,
                })
    return {"source_reports_checked": len(AUTHORITATIVE_LAB_REPORTS), "authoritative_samples": sum(len(row[3]) for row in AUTHORITATIVE_LAB_REPORTS), "sources_needing_review": len(findings), "missing_sample_count": sum(1 for row in manifest_findings if row["status"] == "missing_sample"), "incomplete_or_wrong_count": sum(1 for row in manifest_findings if row["status"] != "missing_sample"), "merged_source_count": sum(bool(row["merged_draft"]) for row in findings), "duplicate_groups": duplicates, "findings": findings[:100], "authoritative_findings": manifest_findings}


def decision_board(year: int, limit: int) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 250))
    return json_ready({
        "queue": fetch_all("SELECT q.* FROM v_lab_decision_queue q JOIN lab_samples s ON s.id=q.sample_id WHERE q.estate_id=%s AND COALESCE(s.vintage_year,YEAR(s.lab_date))=%s ORDER BY (q.review_status='decision_needed') DESC,q.flagged_results DESC,q.lab_date DESC LIMIT %s", (estate_id(), year, safe_limit)),
        "latest": fetch_all("SELECT c.* FROM v_lab_comparison c JOIN lab_samples s ON s.id=c.sample_id WHERE c.estate_id=%s AND COALESCE(s.vintage_year,YEAR(s.lab_date))=%s ORDER BY c.lab_date DESC,c.sample_name,c.analyte_name LIMIT %s", (estate_id(), year, safe_limit)),
        "reference_ranges": fetch_all("SELECT * FROM lab_reference_ranges WHERE estate_id=%s AND active=1 ORDER BY analyte_name,sample_type,stage", (estate_id(),)),
        "year": year,
    })


def vintage_outlook(year: int) -> dict[str, Any]:
    """Return source-backed, like-for-like vintage projections for the lab UI."""
    rows = fetch_all(
        "SELECT c.*,c.wine_stage stage,s.needs_review,s.source_document,s.laboratory,"
        "(SELECT CONCAT('api/v1/attachments/',ea.id,'/file') FROM entity_attachments ea "
        "WHERE ea.estate_id=c.estate_id AND ea.entity_type='lab_sample' AND ea.entity_id=c.sample_id "
        "ORDER BY ea.created_at DESC LIMIT 1) report_url,"
        "COALESCE(s.vintage_year,se.vintage_year,c.vintage_year) authoritative_vintage_year "
        "FROM v_lab_comparison c JOIN lab_samples s ON s.id=c.sample_id "
        "LEFT JOIN seasons se ON se.id=s.season_id "
        "WHERE c.estate_id=%s "
        "AND COALESCE(s.vintage_year,se.vintage_year,c.vintage_year) IS NOT NULL "
        "AND COALESCE(s.vintage_year,se.vintage_year,c.vintage_year)<=%s "
        "AND c.numeric_value IS NOT NULL "
        "ORDER BY c.sample_name,c.sample_type,c.wine_stage,c.analyte_code,c.unit,"
        "COALESCE(s.vintage_year,se.vintage_year,c.vintage_year),c.lab_date,c.result_id",
        (estate_id(), year),
    )
    for row in rows:
        authoritative_vintage = row.pop("authoritative_vintage_year", None)
        if authoritative_vintage is not None:
            row["vintage_year"] = authoritative_vintage
    available_vintages = sorted({int(row.get("vintage_year") or 0) for row in rows if int(row.get("vintage_year") or 0) > 0})
    analysis_year = year if year in available_vintages else (available_vintages[-1] if available_vintages else year)
    series = _project_lab_series(rows, analysis_year)
    try:
        learning_model = lab_learning_status()
    except Exception:
        learning_model = {}
    durable_summary = {
        "model_version": learning_model.get("model_version") or _LAB_MODEL_VERSION,
        "model_status": learning_model.get("model_status") or "awaiting_pipeline_refresh",
        "data_through": learning_model.get("data_through"),
        "projection_case_count": int(learning_model.get("projection_case_count") or 0),
        "observed_outcome_count": int(learning_model.get("observed_outcome_count") or 0),
        "represented_vintage_count": int(learning_model.get("represented_vintage_count") or 0),
        "validation": learning_model.get("validation_metrics") or {},
    }
    for row in series:
        row["ai_projection"]["durable_learning"] = durable_summary
    varieties = fetch_all("SELECT name FROM grape_varieties WHERE estate_id=%s AND active=1 ORDER BY name", (estate_id(),))
    projected = [row for row in series if row["projected_endpoint"] is not None]
    ai_projected = [row for row in series if row.get("ai_projection", {}).get("value") is not None]
    return json_ready({
        "year": year,
        "analysis_year": analysis_year,
        "using_latest_available_vintage": analysis_year != year,
        "availability_message": f"No numeric results are recorded for vintage {year}; showing the latest available vintage {analysis_year}." if analysis_year != year else "",
        "summary": {
            "series_count": len(series),
            "projected_count": len(projected),
            "ai_projected_count": len(ai_projected),
            "missing_history_count": len(series) - len(projected),
            "needs_review_count": sum(bool(row["needs_review"]) for row in series),
            "within_target_count": sum(row["projected_status"] == "within" for row in projected),
            "outside_target_count": sum(row["projected_status"] in {"below", "above"} for row in projected),
        },
        "current_finding": _lab_current_finding(rows, series, year),
        "learning_model": learning_model,
        "variety_standards": _variety_lab_standards(series, varieties),
        "definitions": {
            "historical_endpoint_average": "Arithmetic mean of the final matching measured result in each prior vintage.",
            "projection": "Historical endpoint average adjusted by how the current vintage differs from prior vintages at the same relative laboratory day.",
            "range": "Shifted minimum and maximum of matching prior-vintage endpoints; this is an evidence range, not a statistical confidence interval.",
            "matching_rule": "Same normalized wine identity, sample type, process stage, analyte and unit only. Vintage suffixes and documented Grecanico, Grenache and Nerello Mascalese naming variants are normalized; unrelated wines remain separate.",
            "ai_projection": "Uses exact like-for-like vintage evidence when available. With no matching vintage but at least two dated current readings, it shows a low-confidence 14-day measured-trend projection. Approved marker ranges remain separate from projections.",
            "durable_learning": "Every numeric result creates a versioned cutoff case. Later results in the same exact normalized series score the earlier projection through historical walk-forward validation; future evidence is never included in an earlier input.",
        },
        "series": series,
    })


def history(from_year: int, to_year: int, search: str) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%"
    return json_ready(fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,s.needs_review,s.review_notes,"
        "CASE WHEN s.sample_type='grape' THEN 'agronomy' WHEN s.sample_type IN ('must','wine') THEN 'enology' ELSE 'laboratory' END workflow_area,"
        "CASE WHEN s.sample_type='grape' THEN 'Agronomy · pre-harvest' WHEN s.sample_type IN ('must','wine') THEN 'Enology · post-harvest' ELSE 'Laboratory · supporting evidence' END workflow_label,"
        "s.vintage_assignment_source,s.vintage_assignment_confidence,s.vintage_assignment_evidence,"
        "COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) vintage_year,b.code block_code,v.name variety_name,w.code wine_lot_code,"
        "COUNT(r.id) result_count,GROUP_CONCAT(CONCAT(r.analyte_name,': ',COALESCE(CAST(r.numeric_value AS CHAR),r.text_value,''),' ',COALESCE(r.unit,'')) ORDER BY r.analyte_name SEPARATOR ' | ') results_summary "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN vineyard_blocks b ON b.id=s.block_id "
        "LEFT JOIN grape_varieties v ON v.id=s.variety_id LEFT JOIN wine_lots w ON w.id=s.wine_lot_id LEFT JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) BETWEEN %s AND %s AND (%s='' OR s.sample_name LIKE %s OR s.laboratory LIKE %s OR r.analyte_name LIKE %s) "
        "GROUP BY s.id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,s.needs_review,s.review_notes,s.vintage_assignment_source,s.vintage_assignment_confidence,s.vintage_assignment_evidence,s.vintage_year,se.vintage_year,b.code,v.name,w.code "
        "ORDER BY s.lab_date DESC,s.sample_name LIMIT 500",
        (estate_id(), from_year, to_year, search.strip(), pattern, pattern, pattern),
    ))


def records(year: int | None) -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT vintage_year,lab_date,sample_name,sample_type,laboratory,source_document,needs_review,review_notes FROM lab_samples "
        "WHERE estate_id=%s AND (%s IS NULL OR COALESCE(vintage_year,YEAR(lab_date))=%s) ORDER BY lab_date DESC LIMIT 250",
        (estate_id(), year, year),
    ))


def trends(from_year: int, to_year: int) -> dict[str, Any]:
    return json_ready({
        "annual": fetch_all(
            "SELECT COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) result_year,s.sample_type,r.analyte_code,MAX(r.analyte_name) analyte_name,MAX(r.unit) unit,"
            "COUNT(*) result_count,AVG(r.numeric_value) average_value,MIN(r.numeric_value) minimum_value,MAX(r.numeric_value) maximum_value,"
            "SUM(CASE WHEN COALESCE(r.flag,'normal') IN ('low','high','review') THEN 1 ELSE 0 END) flagged_count "
            "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id JOIN lab_results r ON r.sample_id=s.id "
            "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) BETWEEN %s AND %s AND r.numeric_value IS NOT NULL "
            "GROUP BY COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)),s.sample_type,r.analyte_code ORDER BY r.analyte_code,result_year,s.sample_type",
            (estate_id(), from_year, to_year),
        ),
        "coverage": fetch_all(
            "SELECT COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) result_year,s.sample_type,COUNT(*) sample_count,COUNT(DISTINCT s.laboratory) laboratory_count,"
            "SUM(s.needs_review) review_count FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id "
            "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) BETWEEN %s AND %s "
            "GROUP BY COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)),s.sample_type ORDER BY result_year,s.sample_type",
            (estate_id(), from_year, to_year),
        ),
        "audit": fetch_all(
            "SELECT COUNT(*) sample_count,COUNT(DISTINCT source_document) source_document_count,"
            "SUM(source_document IS NULL OR TRIM(source_document)='') missing_source_count,"
            "SUM(vintage_year IS NULL) missing_vintage_count,"
            "SUM(vintage_assignment_confidence='inferred') inferred_vintage_count,"
            "SUM(vintage_assignment_confidence='review_required') review_required_vintage_count,"
            "(SELECT COUNT(*) FROM lab_results r JOIN lab_samples rs ON rs.id=r.sample_id WHERE rs.estate_id=%s) result_count "
            "FROM lab_samples WHERE estate_id=%s",
            (estate_id(), estate_id()),
        )[0],
        "source_review": _lab_source_audit(),
    })
