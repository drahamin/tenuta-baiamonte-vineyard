from __future__ import annotations

import json
import re
from datetime import date
from statistics import mean, median
from typing import Any

from ..db import fetch_all
from ..lab_authoritative_manifest import AUTHORITATIVE_LAB_REPORTS
from ..service import estate_id, json_ready


def _series_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    """Keep projections within one physical sample/result definition."""
    sample_name = re.sub(r"\s+", " ", str(row.get("sample_name") or "Unnamed sample").strip()).casefold()
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
        endpoint_average = mean(endpoint_values) if endpoint_values else None
        stage_average = mean(comparable_values) if comparable_values else None
        adjustment = latest_value - stage_average if stage_average is not None else 0.0
        projected = endpoint_average + adjustment if endpoint_average is not None else None
        projected_date = None
        if current_first and endpoint_days:
            projected_date = date.fromordinal(current_first.toordinal() + int(round(median(endpoint_days)))).isoformat()
        lower = min(endpoint_values) + adjustment if len(endpoint_values) >= 2 else None
        upper = max(endpoint_values) + adjustment if len(endpoint_values) >= 2 else None
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
        first = current[0]
        output.append({
            "id": "|".join(_series_key(first)),
            "sample_name": first.get("sample_name"),
            "sample_type": first.get("sample_type"),
            "stage": first.get("stage"),
            "analyte_code": first.get("analyte_code"),
            "analyte_name": first.get("analyte_name"),
            "unit": first.get("unit"),
            "latest_value": latest_value,
            "latest_date": str(latest.get("lab_date"))[:10],
            "previous_value": float(current[-2]["numeric_value"]) if len(current) > 1 else None,
            "current_points": [{"date": str(row["lab_date"])[:10], "day": (_as_date(row["lab_date"]) - current_first).days if current_first else 0, "value": float(row["numeric_value"]), "flag": row.get("comparison_flag")} for row in current],
            "historical_series": [{"vintage_year": vintage, "points": [{"date": str(row["lab_date"])[:10], "day": (_as_date(row["lab_date"]) - _as_date(values[0]["lab_date"])).days, "value": float(row["numeric_value"])} for row in values]} for vintage, values in sorted(prior.items())],
            "historical_endpoints": [{"vintage_year": int(row["vintage_year"]), "date": str(row["lab_date"])[:10], "value": float(row["numeric_value"])} for row in endpoints],
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
        })
    return sorted(output, key=lambda row: (str(row["sample_name"]), str(row["analyte_name"]), str(row["unit"])))


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
    def canonical(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold()).replace("granache", "grenache")
    manifest_findings: list[dict[str, Any]] = []
    for report_date, vintage, sample_type, expected_samples in AUTHORITATIVE_LAB_REPORTS:
        for sample_name, result_count in expected_samples:
            matches = [row for row in stored if str(row.get("lab_date"))[:10] == report_date and canonical(row.get("sample_name")) == canonical(sample_name)]
            exact = [row for row in matches if vintage is None or int(row.get("vintage_year") or 0) == vintage]
            row = exact[0] if exact else (matches[0] if matches else None)
            if not row or int(row.get("result_count") or 0) < result_count or (vintage is not None and int(row.get("vintage_year") or 0) != vintage):
                manifest_findings.append({"report_date": report_date, "vintage_year": vintage, "sample_type": sample_type, "sample_name": sample_name, "expected_results": result_count, "stored_results": int(row.get("result_count") or 0) if row else 0, "status": "missing_sample" if not row else "incomplete_results" if int(row.get("result_count") or 0) < result_count else "wrong_vintage"})
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
        "SELECT c.*,c.wine_stage stage,s.needs_review,"
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
    series = _project_lab_series(rows, year)
    projected = [row for row in series if row["projected_endpoint"] is not None]
    return json_ready({
        "year": year,
        "summary": {
            "series_count": len(series),
            "projected_count": len(projected),
            "missing_history_count": len(series) - len(projected),
            "needs_review_count": sum(bool(row["needs_review"]) for row in series),
            "within_target_count": sum(row["projected_status"] == "within" for row in projected),
            "outside_target_count": sum(row["projected_status"] in {"below", "above"} for row in projected),
        },
        "definitions": {
            "historical_endpoint_average": "Arithmetic mean of the final matching measured result in each prior vintage.",
            "projection": "Historical endpoint average adjusted by how the current vintage differs from prior vintages at the same relative laboratory day.",
            "range": "Shifted minimum and maximum of matching prior-vintage endpoints; this is an evidence range, not a statistical confidence interval.",
            "matching_rule": "Same sample or wine name, sample type, process stage, analyte and unit only.",
        },
        "series": series,
    })


def history(from_year: int, to_year: int, search: str) -> list[dict[str, Any]]:
    pattern = f"%{search.strip()}%"
    return json_ready(fetch_all(
        "SELECT s.id sample_id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,s.needs_review,s.review_notes,"
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
