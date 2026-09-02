"""Transparent grape-to-wine yield and wine mass conversion helpers."""

from __future__ import annotations

from typing import Any


TYPICAL_RED_WINE_YIELD_MIN_L_PER_KG = 0.67
TYPICAL_RED_WINE_YIELD_MAX_L_PER_KG = 0.70
DEFAULT_RED_WINE_YIELD_L_PER_KG = 0.70


def yield_disclosure(factor_l_per_kg: float, source: str, *, estimated: bool = True) -> dict[str, Any]:
    """Describe grape-weight to finished-wine volume without calling it mass conversion."""
    factor = float(factor_l_per_kg)
    inverse = 1 / factor if factor > 0 else None
    return {
        "factor_l_per_kg": round(factor, 6),
        "inverse_kg_grapes_per_l": round(inverse, 6) if inverse is not None else None,
        "typical_min_l_per_kg": TYPICAL_RED_WINE_YIELD_MIN_L_PER_KG,
        "typical_max_l_per_kg": TYPICAL_RED_WINE_YIELD_MAX_L_PER_KG,
        "source": source,
        "is_estimate": estimated,
        "formula": "estimated finished wine L = grape kg × yield L/kg",
        "label": f"1 kg grapes × {factor:.3f} L/kg = {factor:.3f} L estimated finished wine",
        "inverse_label": f"1 L estimated finished wine corresponds to {inverse:.3f} kg grapes at this yield" if inverse else None,
        "typical_range_label": "Typical red-wine planning range: 0.67–0.70 L finished wine per kg grapes (67–70%)",
        "mass_warning": "This is a production-yield estimate, not a litre-to-kilogram mass conversion. Wine mass requires measured density: kg = L × density kg/L.",
    }


def wine_mass_kg(volume_l: float, density_kg_l: float | None) -> float | None:
    """Convert actual wine volume to mass only when a measured density is supplied."""
    if density_kg_l is None or float(volume_l) < 0 or float(density_kg_l) <= 0:
        return None
    return float(volume_l) * float(density_kg_l)
