"""Stable estate-facing camera names without changing Home Assistant IDs."""

from __future__ import annotations

import re


# Entity ids remain the integration contract. These labels are the shared
# operator-facing contract used by dashboards, TV, People and AI workflows.
CANONICAL_CAMERA_NAMES: dict[str, str] = {
    "camera.topvineyard": "Back Driveway Mid",
    "camera.mid_vineyard_north": "Entrance Road",
    "camera.gate_doorbell_2": "Front Gate Doorbell",
    "camera.front_gate": "Inside Front Gate",
    "camera.vineyard_north": "Main Parking",
    "camera.solar_wall_light_cam": "BBQ Front",
    "camera.bbq_grill_2": "BBQ Grill",
    "camera.rear_gate": "Rear Gate",
    "camera.t8171t1025291b5f": "Rear Gate 360",
    "camera.top_vineyard_360": "Rear Entrance Path 360",
    "camera.cistern_360": "Cistern 360",
    "camera.cisterna": "Cistern Internal",
    "camera.generator_room": "Generator Room",
    "camera.kitchen": "Kitchen",
    "camera.palmento": "Palmento",
    "camera.solar_room": "Solar Room",
    "camera.rear_gate_360": "Backyard",
    "camera.east_360": "East 360",
    "camera.front_yard": "Front Yard",
    "camera.west_360": "West 360",
    "camera.fox_ally": "Fox Alley",
    "camera.giangreco_360": "Giangreco 360",
    "camera.lower_vineyard": "Lower Vineyard 360",
    "camera.vineyard_top": "Top Vineyard",
    "camera.top_vineyard_360_2": "Top Vineyard 360",
    "camera.solar_wall_light_cam_2": "Top Vineyard Path",
    "camera.vineyard_north_2": "Vineyard North",
    "camera.west_etna_view": "West Etna View",
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
