"""Shared exact-lot MLF purchase-plan projection; no dosing authorization."""
from __future__ import annotations

from typing import Any

MLF_PLAN_COLUMNS = 'mp.product_name mlf_product_name,mp.formulation mlf_formulation,mp.timing_plan mlf_timing_plan,mp.volume_min_l mlf_volume_min_l,mp.volume_max_l mlf_volume_max_l,mp.volume_basis mlf_volume_basis,mp.volume_basis_note mlf_volume_basis_note,mp.small_sachet_coverage_l,mp.large_sachet_coverage_l,mp.exact_label_confirmed mlf_exact_label_confirmed,mp.suitability_confirmed mlf_suitability_confirmed,mp.approved_by mlf_approved_by,mp.notes mlf_plan_notes,mp.updated_at mlf_plan_updated_at,'
MLF_PLAN_JOIN = 'LEFT JOIN enology_mlf_plans mp ON mp.wine_lot_id=w.id AND mp.estate_id=w.estate_id '


def mlf_purchase_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    """Expose whole-sachet purchase math without turning estimates into dosing instructions."""
    if not row or str(row.get("wine_color") or "").casefold() != "red":
        return None
    minimum, maximum = row.get("mlf_volume_min_l"), row.get("mlf_volume_max_l")
    coverage = float(row.get("small_sachet_coverage_l") or 250)
    if minimum is None or maximum is None or coverage <= 0:
        return None
    import math
    minimum, maximum = float(minimum), float(maximum)
    return {
        "product_name": row.get("mlf_product_name") or "LALVIN VP41 MBR",
        "formulation": row.get("mlf_formulation") or "MBR",
        "timing_plan": row.get("mlf_timing_plan") or "sequential",
        "volume_min_l": minimum, "volume_max_l": maximum,
        "volume_basis": row.get("mlf_volume_basis"), "volume_basis_note": row.get("mlf_volume_basis_note"),
        "small_sachet_coverage_l": coverage, "large_sachet_coverage_l": float(row.get("large_sachet_coverage_l") or 2500),
        "equivalent_small_doses_min": round(minimum / coverage, 2), "equivalent_small_doses_max": round(maximum / coverage, 2),
        "whole_small_sachets_min": math.ceil(minimum / coverage), "whole_small_sachets_max": math.ceil(maximum / coverage),
        "exact_label_confirmed": bool(row.get("mlf_exact_label_confirmed")), "suitability_confirmed": bool(row.get("mlf_suitability_confirmed")),
        "approved_by": row.get("mlf_approved_by"), "notes": row.get("mlf_plan_notes"),
        "planning_only": True, "dosing_blocked": True,
        "dosing_guardrail": "Purchase planning only. Confirm current measured wine liters, the exact VP41 MBR sachet label and coverage, timing and suitability with Sebastiano before inoculation. Never divide a large sachet by weight or substitute VP41 1-STEP instructions.",
    }
