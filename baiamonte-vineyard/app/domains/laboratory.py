from __future__ import annotations

from typing import Any

from ..db import fetch_all
from ..service import estate_id, json_ready


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
        "SELECT s.id sample_id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,"
        "COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) vintage_year,b.code block_code,v.name variety_name,w.code wine_lot_code,"
        "COUNT(r.id) result_count,GROUP_CONCAT(CONCAT(r.analyte_name,': ',COALESCE(CAST(r.numeric_value AS CHAR),r.text_value,''),' ',COALESCE(r.unit,'')) ORDER BY r.analyte_name SEPARATOR ' | ') results_summary "
        "FROM lab_samples s LEFT JOIN seasons se ON se.id=s.season_id LEFT JOIN vineyard_blocks b ON b.id=s.block_id "
        "LEFT JOIN grape_varieties v ON v.id=s.variety_id LEFT JOIN wine_lots w ON w.id=s.wine_lot_id LEFT JOIN lab_results r ON r.sample_id=s.id "
        "WHERE s.estate_id=%s AND COALESCE(s.vintage_year,se.vintage_year,YEAR(s.lab_date)) BETWEEN %s AND %s AND (%s='' OR s.sample_name LIKE %s OR s.laboratory LIKE %s OR r.analyte_name LIKE %s) "
        "GROUP BY s.id,s.sample_name,s.sample_code,s.sample_type,s.lab_date,s.laboratory,s.source_document,s.notes,s.vintage_year,se.vintage_year,b.code,v.name,w.code "
        "ORDER BY s.lab_date DESC,s.sample_name LIMIT 500",
        (estate_id(), from_year, to_year, search.strip(), pattern, pattern, pattern),
    ))


def records(year: int | None) -> list[dict[str, Any]]:
    return json_ready(fetch_all(
        "SELECT vintage_year,lab_date,sample_name,sample_type,laboratory,source_document,needs_review,review_notes FROM lab_samples "
        "WHERE estate_id=%s AND (%s IS NULL OR COALESCE(vintage_year,YEAR(lab_date))=%s) ORDER BY lab_date DESC LIMIT 250",
        (estate_id(), year, year),
    ))
