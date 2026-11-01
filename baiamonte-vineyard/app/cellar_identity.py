"""Canonical physical-vessel and current-wine identities for the cellar."""

from __future__ import annotations

import re
from typing import Any, Mapping


TANK_LIKE_TYPES = {"tank", "fermenter", "aging"}
_TANK_NUMBER = re.compile(
    r"^(?:T|TANK|SERBATOIO|VASCA)?[\s._#-]*(\d{1,3})$",
    re.IGNORECASE,
)
_GENERAL_CODE = re.compile(r"^[A-Z][A-Z0-9]{0,7}(?:-[A-Z0-9]{1,12})+$")


def canonical_container_code(value: Any, container_type: Any = "tank") -> str:
    """Return one durable physical code, independent of the wine in the vessel."""
    raw = re.sub(r"\s+", " ", str(value or "").strip()).upper()
    if not raw:
        raise ValueError("Tank code is required")
    kind = str(container_type or "tank").strip().casefold()
    match = _TANK_NUMBER.fullmatch(raw)
    if match and kind in TANK_LIKE_TYPES:
        return f"T-{int(match.group(1)):02d}"
    normalized = re.sub(r"[\s._]+", "-", raw)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if kind in TANK_LIKE_TYPES and not re.fullmatch(r"T-\d{2,3}", normalized):
        raise ValueError("Tank codes must use T-01, T-02, T-03 …")
    if not _GENERAL_CODE.fullmatch(normalized):
        raise ValueError("Use a short physical code such as T-03, DJ-L54 or B-01")
    return normalized


def canonical_variety(value: Any) -> str | None:
    """Normalize known cellar aliases without discarding source-specific detail."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return None
    key = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    aliases = {
        "alicante": "Grenache / Alicante",
        "alicante bouschet": "Grenache / Alicante",
        "grenache": "Grenache / Alicante",
        "grenache noir": "Grenache / Alicante",
        "grecanico": "Grecanico",
        "grecanico dorato": "Grecanico",
        "nerello": "Nerello Mascalese",
        "nerello mascalese": "Nerello Mascalese",
    }
    return aliases.get(key, text)


def cellar_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """Build a uniform current identity while keeping the asset name separate."""
    try:
        code = canonical_container_code(row.get("code"), row.get("container_type"))
    except ValueError:
        code = re.sub(r"\s+", " ", str(row.get("code") or "Uncoded vessel").strip()).upper()
    variety = canonical_variety(row.get("variety_summary"))
    lot_code = re.sub(r"\s+", "", str(row.get("lot_code") or row.get("wine_lot_code") or "").strip()).upper() or None
    status = str(row.get("status") or "").strip().casefold()
    if status == "empty" and not lot_code:
        variety = None
    vintage = row.get("vintage_year") if lot_code or variety else None
    try:
        vintage = int(vintage) if vintage else None
    except (TypeError, ValueError):
        vintage = None
    stage = str(row.get("stage") or "").strip() or ("Empty" if status == "empty" and not lot_code else None)
    if status == "empty" and not lot_code:
        stage = "Empty"
    parts = [str(vintage) if vintage else None, code, variety, lot_code]
    label = " · ".join(part for part in parts if part)
    physical_name = re.sub(r"\s+", " ", str(row.get("name") or "").strip()) or code
    tank_match = re.fullmatch(r"T-(\d{2,3})", code)
    if tank_match:
        base_name = f"Tank {int(tank_match.group(1))}"
        changing_name = bool(
            re.match(r"^(?:tank|serbatoio|vasca|fermenter)\s*#?\s*\d+", physical_name, re.IGNORECASE)
            or re.search(r"(?:19|20)\d{2}|grenache|alicante|grecanico|nerello", physical_name, re.IGNORECASE)
        )
        physical_name = base_name if changing_name else f"{base_name} · {physical_name}"
    warnings: list[str] = []
    if re.search(r"(?:19|20)\d{2}|(?:^|-)(?:GRC|GRN|NM)(?:-|$)", code):
        warnings.append("Physical code contains wine or vintage information")
    if lot_code and not re.fullmatch(r"[A-Z]{2,5}-(?:19|20)\d{2}-\d{2}(?:-[A-Z0-9]+)?", lot_code):
        warnings.append("Wine lot code uses a legacy format")
    return {
        "identity_label": label,
        "identity_short": " · ".join(part for part in (code, str(vintage) if vintage else None, variety) if part),
        "canonical_container_code": code,
        "canonical_variety": variety,
        "identity_vintage": vintage,
        "identity_lot_code": lot_code,
        "identity_stage": stage,
        "asset_name": physical_name,
        "identity_needs_review": bool(warnings),
        "identity_warnings": warnings,
    }


def apply_cellar_identity(row: dict[str, Any]) -> dict[str, Any]:
    row.update(cellar_identity(row))
    return row
