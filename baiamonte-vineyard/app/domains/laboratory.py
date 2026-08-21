from __future__ import annotations

import json
import re
from typing import Any

from ..db import fetch_all
from ..lab_authoritative_manifest import AUTHORITATIVE_LAB_REPORTS
from ..service import estate_id, json_ready


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
