from __future__ import annotations

from typing import Any


_PLACEHOLDER_MARKERS = ("replace this template", "template row", "first sample placeholder")


def maturity_has_evidence(row: dict[str, Any] | None) -> bool:
    """Return true only for a maturity row containing an actual observation."""
    if not row:
        return False
    if any(row.get(field) is not None for field in ("brix", "ph", "ta_g_l", "disease_pct", "provisional_pick_date")):
        return True
    if str(row.get("decision") or "monitor").casefold() != "monitor":
        return True
    if str(row.get("condition_notes") or "").strip():
        return True
    notes = str(row.get("notes") or "").strip().casefold()
    return bool(notes) and not any(marker in notes for marker in _PLACEHOLDER_MARKERS)


def maturity_evidence_sql(alias: str = "m") -> str:
    """SQL equivalent of maturity_has_evidence for selecting the latest valid row."""
    prefix = f"{alias}."
    return (
        f"({prefix}brix IS NOT NULL OR {prefix}ph IS NOT NULL OR {prefix}ta_g_l IS NOT NULL "
        f"OR {prefix}disease_pct IS NOT NULL OR {prefix}provisional_pick_date IS NOT NULL "
        f"OR {prefix}decision<>'monitor' OR NULLIF(TRIM({prefix}condition_notes),'') IS NOT NULL "
        f"OR (NULLIF(TRIM({prefix}notes),'') IS NOT NULL AND LOWER({prefix}notes) NOT LIKE '%%template%%'))"
    )
