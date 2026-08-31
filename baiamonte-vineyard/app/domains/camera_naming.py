"""Stable estate-facing camera names without changing Home Assistant IDs."""

from __future__ import annotations

import re


# Entity ids remain the integration contract. These labels are the shared
# operator-facing contract used by dashboards, TV, People and AI workflows.
CANONICAL_CAMERA_NAMES: dict[str, str] = {
    "camera.vineyard_north": "Main Parking",
    "camera.rear_gate": "Rear Gate",
    "camera.t8171t1025291b5f": "Rear Gate 360",
    "camera.top_vineyard_360": "Rear Entrance Path 360",
    "camera.cistern_360": "Cistern 360",
}


def canonical_camera_name(entity_id: str, friendly_name: object = "") -> str:
    """Return one clean operational label while preserving the entity id."""
    entity_id = str(entity_id or "").strip()
    if entity_id in CANONICAL_CAMERA_NAMES:
        return CANONICAL_CAMERA_NAMES[entity_id]
    value = str(friendly_name or "").strip()
    if not value:
        value = entity_id.removeprefix("camera.").replace("_", " ")
    value = re.sub(r"\s*/\s*", " / ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Estate Camera"
