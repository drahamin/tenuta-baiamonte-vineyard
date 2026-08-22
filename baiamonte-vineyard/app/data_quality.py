from __future__ import annotations

from typing import Any

from .db import fetch_all, fetch_one


def operational_data_quality(estate: str) -> dict[str, Any]:
    """Small, stable integrity checks used by the admin control surface."""
    counts = fetch_one(
        "SELECT "
        "(SELECT COUNT(*) FROM labor_entries WHERE estate_id=%s AND work_date>CURDATE()) future_labor_records,"
        "(SELECT COUNT(*) FROM lab_samples WHERE estate_id=%s AND vintage_year IS NULL) labs_missing_vintage,"
        "(SELECT COUNT(*) FROM lab_samples WHERE estate_id=%s AND needs_review=1) labs_needing_review,"
        "(SELECT COUNT(*) FROM spray_applications treatment WHERE treatment.estate_id=%s AND treatment.status='completed' "
        "AND (treatment.actual_details_confirmed=0 OR COALESCE(treatment.phi_checked,0)=0 OR COALESCE(treatment.agronomist_approved,0)=0) "
        "AND NOT EXISTS (SELECT 1 FROM treatment_safety_dispositions disposition WHERE disposition.estate_id=treatment.estate_id "
        "AND disposition.application_id=treatment.id AND disposition.disposition='restricted_historical')) treatment_safety_gaps,"
        "(SELECT COUNT(*) FROM treatment_safety_dispositions disposition JOIN spray_applications treatment ON treatment.id=disposition.application_id "
        "WHERE disposition.estate_id=%s AND treatment.status='completed' AND disposition.disposition='restricted_historical') treatment_safety_restricted_records,"
        "(SELECT COUNT(*) FROM (SELECT current_container_id FROM wine_lots WHERE estate_id=%s "
        "AND current_container_id IS NOT NULL GROUP BY current_container_id HAVING COUNT(*)>1) conflicts) shared_planned_containers,"
        "(SELECT COUNT(*) FROM (SELECT current_container_id FROM wine_lots WHERE estate_id=%s "
        "AND current_container_id IS NOT NULL AND COALESCE(volume_l,initial_l,0)>0 "
        "GROUP BY current_container_id HAVING COUNT(*)>1) conflicts) shared_occupied_containers",
        (estate, estate, estate, estate, estate, estate, estate),
    ) or {}
    result = {key: int(value or 0) for key, value in counts.items()}
    learned = fetch_all(
        "SELECT finding_type,severity,COUNT(*) finding_count,MAX(last_seen_at) last_seen_at "
        "FROM learned_data_quality_findings WHERE estate_id=%s AND status='open' "
        "GROUP BY finding_type,severity ORDER BY FIELD(severity,'critical','warning','info'),finding_type", (estate,),
    )
    result["learned_findings"] = learned
    result["learned_open_findings"] = sum(int(row.get("finding_count") or 0) for row in learned)
    result["learned_critical_findings"] = sum(int(row.get("finding_count") or 0) for row in learned if row.get("severity") == "critical")
    result["blocking_issues"] = (
        result["labs_missing_vintage"]
        + result["shared_occupied_containers"]
        + result["learned_critical_findings"]
    )
    result["review_items"] = (
        result["future_labor_records"]
        + result["labs_needing_review"]
        + result["treatment_safety_gaps"]
        + result["shared_planned_containers"]
        + result["learned_open_findings"] - result["learned_critical_findings"]
    )
    return result
