from __future__ import annotations

from typing import Any

from .db import fetch_one


def operational_data_quality(estate: str) -> dict[str, Any]:
    """Small, stable integrity checks used by the admin control surface."""
    counts = fetch_one(
        "SELECT "
        "(SELECT COUNT(*) FROM labor_entries WHERE estate_id=%s AND work_date>CURDATE()) future_labor_records,"
        "(SELECT COUNT(*) FROM lab_samples WHERE estate_id=%s AND vintage_year IS NULL) labs_missing_vintage,"
        "(SELECT COUNT(*) FROM lab_samples WHERE estate_id=%s AND needs_review=1) labs_needing_review,"
        "(SELECT COUNT(*) FROM spray_applications WHERE estate_id=%s AND status='completed' "
        "AND (actual_details_confirmed=0 OR COALESCE(phi_checked,0)=0 OR COALESCE(agronomist_approved,0)=0)) treatment_safety_gaps,"
        "(SELECT COUNT(*) FROM (SELECT current_container_id FROM wine_lots WHERE estate_id=%s "
        "AND current_container_id IS NOT NULL GROUP BY current_container_id HAVING COUNT(*)>1) conflicts) shared_planned_containers,"
        "(SELECT COUNT(*) FROM (SELECT current_container_id FROM wine_lots WHERE estate_id=%s "
        "AND current_container_id IS NOT NULL AND COALESCE(volume_l,initial_l,0)>0 "
        "GROUP BY current_container_id HAVING COUNT(*)>1) conflicts) shared_occupied_containers",
        (estate, estate, estate, estate, estate, estate),
    ) or {}
    result = {key: int(value or 0) for key, value in counts.items()}
    result["blocking_issues"] = (
        result["labs_missing_vintage"]
        + result["shared_occupied_containers"]
    )
    result["review_items"] = (
        result["future_labor_records"]
        + result["labs_needing_review"]
        + result["treatment_safety_gaps"]
        + result["shared_planned_containers"]
    )
    return result
