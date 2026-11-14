"""Private, hash-verified owner frames for fixed-camera waterline comparison."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


def reference_image(snapshot: Path, row: dict[str, Any], camera: str, calibration: str) -> bytes | None:
    """Archive only the exact owner-reviewed image, never a later replacement."""
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            return None
    digest = str(row.get("image_sha256") or "")
    if (not isinstance(metadata, dict) or not metadata.get("owner_assisted")
            or metadata.get("calibration_reference") != calibration
            or row.get("source") != "owner_assisted_camera_review"
            or row.get("camera_entity_id") != camera
            or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
        return None
    archive = snapshot.parent / "cistern-owner-references" / digest
    for candidate in (archive, snapshot):
        try:
            image = candidate.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(image).hexdigest() != digest:
            continue
        if candidate == snapshot and not archive.exists():
            archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            archive.write_bytes(image)
            archive.chmod(0o600)
        return image
    return None


def accepted_fraction(analysis: dict[str, Any], reference: dict[str, Any] | None) -> float:
    """A single full anchor supports same-level matching, not arbitrary interpolation."""
    if analysis.get("usable") is not True or analysis.get("visible_waterline") is not True:
        raise ValueError("Current water surface is not visible")
    try:
        fraction = float(analysis.get("waterline_height_fraction"))
        confidence = float(analysis.get("confidence"))
    except (ValueError, TypeError):
        raise ValueError("Waterline measurement or confidence is missing") from None
    if not math.isfinite(fraction) or not 0 <= fraction <= 1 or not math.isfinite(confidence) or not .6 <= confidence <= 1:
        raise ValueError("Waterline measurement or confidence is outside the accepted range")
    mode = analysis.get("measurement_method", "visible_landmarks")
    if mode == "owner_reference_match":
        if (not reference or analysis.get("reference_id") != reference.get("id")
                or analysis.get("camera_geometry_matches_reference") is not True
                or analysis.get("same_surface_height_as_reference") is not True
                or confidence < .8):
            raise ValueError("Owner reference does not match the current camera and water surface")
        anchor = float(reference["level_percent"]) / 100
        if not math.isfinite(anchor) or not 0 <= anchor <= 1 or abs(fraction - anchor) > .03:
            raise ValueError("A single owner reference cannot calibrate a different water level")
        # Return the actual reviewed anchor, rather than an unsupported nearby estimate.
        return anchor
    if mode != "visible_landmarks" or analysis.get("calibration_landmarks_visible") is not True:
        raise ValueError("Both height landmarks are required away from an owner reference")
    return fraction
