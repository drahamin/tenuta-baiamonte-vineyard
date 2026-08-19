from __future__ import annotations

from typing import Any

from ..db import fetch_all
from ..service import estate_id


def product_guidance(crop_scope: str, prediction: dict[str, Any]) -> dict[str, Any]:
    """Return only current, crop-specific verified candidates."""
    target_code = str(prediction.get("target_code") or "").strip()
    if not target_code:
        return {
            "status": "waiting_for_target", "target_code": None, "candidates": [],
            "message": "Confirm the treatment target before selecting what to apply.",
        }
    candidates = fetch_all(
        "SELECT u.*,p.name product_name,p.active_ingredient,p.registration_number,p.unit "
        "FROM product_authorized_uses u JOIN products p ON p.id=u.product_id "
        "WHERE u.estate_id=%s AND u.crop_scope=%s AND u.target_code=%s AND u.active=1 AND p.active=1 "
        "AND u.authorization_status='authorized' AND (u.authorization_expires_on IS NULL OR u.authorization_expires_on>=CURDATE()) "
        "AND u.label_verified_on>=CURDATE()-INTERVAL 30 DAY ORDER BY u.label_verified_on DESC,p.name",
        (estate_id(), crop_scope, target_code),
    )
    if not candidates:
        return {
            "status": "no_verified_candidate", "target_code": target_code, "candidates": [],
            "message": "No current crop-and-target authorization is verified in the database. Check the current Italian label and Sicily rules with the Agronomist; do not select a product from history alone.",
        }
    return {
        "status": "agronomist_selection_required", "target_code": target_code,
        "preferred_candidate": candidates[0], "candidates": candidates,
        "message": "Decision support only. Confirm the current label, dose, PHI, REI, resistance rotation, weather, PPE and block conditions before approval.",
    }
