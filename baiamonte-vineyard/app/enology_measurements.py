"""Canonical units and safety bounds for measurements used by enology decisions."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _unit_key(value: Any) -> str:
    raw = str(value or "").strip().casefold().replace("ℓ", "l").replace("₂", "2")
    raw = "".join(character for character in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9%]+", "", raw)


# canonical unit, accepted unit -> multiplier, plausible canonical range
_SPECS: dict[str, tuple[str, dict[str, float], tuple[float, float]]] = {
    "ph": ("pH", {"": 1, "ph": 1}, (2.0, 5.0)),
    "babo": ("°Babo", {"": 1, "babo": 1, "gradibabo": 1, "deg": 1}, (-5.0, 40.0)),
    "brix": ("°Bx", {"": 1, "bx": 1, "brix": 1, "deg": 1}, (-5.0, 50.0)),
    "potential_alcohol": ("% vol", {"%": 1, "%vol": 1, "vol%": 1, "abv": 1, "percent": 1}, (0.0, 25.0)),
    "actual_alcohol": ("% vol", {"%": 1, "%vol": 1, "vol%": 1, "abv": 1, "percent": 1}, (0.0, 25.0)),
    "yan": ("mg/L", {"mg/l": 1, "mgl": 1, "mgn/l": 1, "mgnl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "turbidity": ("NTU", {"ntu": 1}, (0.0, 10000.0)),
    "potassium": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 5000.0)),
    "free_so2": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "total_so2": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "dissolved_oxygen": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 20.0)),
    "total_acidity": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 30.0)),
    "volatile_acidity": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 5.0)),
    "residual_sugar": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 500.0)),
    "malic_acid": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 30.0)),
    "lactic_acid": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 30.0)),
    "tartaric_acid": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 30.0)),
    "citric_acid": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 10.0)),
    "ammonium_nitrogen": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "alpha_amino_nitrogen": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "calcium": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 5000.0)),
    "copper": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 100.0)),
    "iron": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 100.0)),
    "acetaldehyde": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 1000.0)),
    "anthocyanins": ("mg/L", {"mg/l": 1, "mgl": 1, "g/l": 1000, "gl": 1000}, (0.0, 10000.0)),
    "carbon_dioxide": ("g/L", {"g/l": 1, "gl": 1, "mg/l": 0.001, "mgl": 0.001}, (0.0, 20.0)),
}


def normalize_enology_measurement(code: str, value: Any, unit: Any) -> dict[str, Any]:
    """Return a decision-safe canonical value while retaining invalid evidence for review."""
    if value is None:
        return {"usable": False, "value": None, "unit": str(unit or "").strip(), "reason": "numeric value missing"}
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return {"usable": False, "value": value, "unit": str(unit or "").strip(), "reason": "numeric value invalid"}
    spec = _SPECS.get(str(code or ""))
    if not spec:
        return {"usable": True, "value": numeric, "unit": str(unit or "").strip(), "reason": None}
    canonical_unit, conversions, bounds = spec
    key = _unit_key(unit)
    # pH and sugar scales are commonly exported without a unit; concentration
    # and alcohol measurements must carry a compatible unit before decisions.
    if key not in conversions:
        return {
            "usable": False,
            "value": numeric,
            "unit": str(unit or "").strip(),
            "canonical_unit": canonical_unit,
            "reason": f"expected a unit compatible with {canonical_unit}",
        }
    canonical = numeric * conversions[key]
    if not bounds[0] <= canonical <= bounds[1]:
        return {
            "usable": False,
            "value": numeric,
            "unit": str(unit or "").strip(),
            "canonical_unit": canonical_unit,
            "reason": f"value outside the plausible {bounds[0]:g}–{bounds[1]:g} {canonical_unit} range",
        }
    return {"usable": True, "value": canonical, "unit": canonical_unit, "reason": None}
