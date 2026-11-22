"""Capture-time evidence shared by TV stills and recognition input."""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def snapshot_evidence(value: object, *, now: datetime | None = None) -> dict:
    """Unknown/future timestamps cannot establish current image evidence."""
    now = now or datetime.now(timezone.utc)
    try:
        captured = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        captured = captured.astimezone(timezone.utc)
        if captured > now + timedelta(minutes=5):
            raise ValueError("Future capture time")
    except (ValueError, TypeError, OverflowError):
        return {"captured_at": None, "age_seconds": None, "current": False}
    age = max(0, int((now - captured).total_seconds()))
    return {"captured_at": captured.isoformat(), "age_seconds": age, "current": age <= 600}


def saved_snapshot_evidence(image_path: Path, *, content: bytes | None = None) -> dict:
    """Read capture metadata; file modification time is not a capture time."""
    try:
        metadata = json.loads(image_path.with_suffix(".json").read_text())
        if metadata.get("sha256") and hashlib.sha256(content if content is not None else image_path.read_bytes()).hexdigest() != metadata["sha256"]:
            return snapshot_evidence(None)
        value = metadata.get("captured_at")
    except (OSError, ValueError, TypeError, AttributeError):
        value = None
    return snapshot_evidence(value)


def write_saved_snapshot(image_path: Path, content: bytes, captured_at: str | None) -> None:
    """Readers see complete files; digest checks prevent mixed image/time pairs."""
    image_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.dumps({"captured_at": captured_at, "sha256": hashlib.sha256(content).hexdigest()}).encode()
    for destination, payload in ((image_path, content), (image_path.with_suffix(".json"), metadata)):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=image_path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def source_capture_value(attributes: dict | None) -> object:
    """A bridge receipt time cannot date the pixels in a replayed push image."""
    attributes = attributes or {}
    if attributes.get("snapshot_time_basis") in {"received", "unknown"}:
        return None
    return attributes.get("snapshot_updated_at")
