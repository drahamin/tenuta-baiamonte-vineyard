"""Low-load, review-gated learning state for the fixed Vineyard North view."""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("VINEYARD_VISUAL_ROOT", "/data/vineyard-visual"))
STATE_PATH = ROOT / "state.json"
SNAPSHOT_PATH = ROOT / "latest.jpg"
MODEL_VERSION = "fixed-view-evidence-v2-etna"
CAPTURE_INTERVAL_SECONDS = 60 * 60
AI_INTERVAL_SECONDS = 6 * 60 * 60
# In the fixed Vineyard North composition, Mount Etna is the distant summit
# left of centre, behind the terraced vines and beside the tall pine.  The
# normalized box is descriptive evidence for the vision review, not a crop or
# alarm trigger by itself.
ETNA_REGION = {
    "label": "Mount Etna summit",
    "x": 0.08,
    "y": 0.05,
    "width": 0.42,
    "height": 0.55,
    "description": "Distant summit left of centre, behind the terraced vineyard and beside the tall pine",
}


def _read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(value: dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(STATE_PATH)


def save_snapshot(image: bytes) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_bytes(image)
    temporary.replace(SNAPSHOT_PATH)


def due_for_capture(now: float | None = None) -> bool:
    state = _read_state()
    return (now or time.time()) - float(state.get("last_capture_epoch") or 0) >= CAPTURE_INTERVAL_SECONDS


def _rgb_vector(image: bytes, width: int = 64, height: int = 36) -> bytes:
    completed = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
            "-vf", f"scale={width}:{height}:flags=area,format=rgb24", "-frames:v", "1",
            "-f", "rawvideo", "pipe:1",
        ],
        input=image,
        capture_output=True,
        check=False,
        timeout=12,
    )
    expected = width * height * 3
    if completed.returncode or len(completed.stdout) != expected:
        raise ValueError("The fixed-view frame could not be decoded")
    return completed.stdout


def _metrics(vector: bytes, previous: bytes | None) -> dict[str, Any]:
    pixels = [vector[index:index + 3] for index in range(0, len(vector), 3)]
    luminance = [(int(red) * 0.2126 + int(green) * 0.7152 + int(blue) * 0.0722) / 255 for red, green, blue in pixels]
    brightness = sum(luminance) / len(luminance)
    variance = sum((value - brightness) ** 2 for value in luminance) / len(luminance)
    green_share = sum(green > 48 and green > red * 1.06 and green > blue * 1.03 for red, green, blue in pixels) / len(pixels)
    green_index = sum((int(green) - (int(red) + int(blue)) / 2) / 255 for red, green, blue in pixels) / len(pixels)
    edge = sum(abs(luminance[index] - luminance[index - 1]) for index in range(1, len(luminance))) / max(1, len(luminance) - 1)
    frame_change = None
    if previous and len(previous) == len(vector):
        frame_change = sum(abs(current - prior) for current, prior in zip(vector, previous)) / (len(vector) * 255)
    dark_share = sum(value < 0.10 for value in luminance) / len(luminance)
    bright_share = sum(value > 0.94 for value in luminance) / len(luminance)
    suitable = 0.14 <= brightness <= 0.90 and dark_share < 0.55 and bright_share < 0.42 and math.sqrt(variance) >= 0.055 and edge >= 0.025
    return {
        "brightness": round(brightness, 4), "contrast": round(math.sqrt(variance), 4),
        "green_share_pct": round(green_share * 100, 1), "green_index": round(green_index, 4),
        "edge_detail": round(edge, 4), "dark_share_pct": round(dark_share * 100, 1),
        "bright_share_pct": round(bright_share * 100, 1),
        "frame_change_pct": round(frame_change * 100, 1) if frame_change is not None else None,
        "daylight_suitable": suitable,
        "quality_reason": "Suitable daylight evidence" if suitable else "Frame is dark, washed out, obscured, or lacks enough detail",
    }


def analyze_frame(image: bytes, captured_at: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _read_state()
    previous = None
    try:
        previous = base64.b64decode(state.get("latest_vector") or "", validate=True)
    except (ValueError, TypeError):
        previous = None
    vector = _rgb_vector(image)
    metrics = _metrics(vector, previous)
    captured_at = captured_at or datetime.now(timezone.utc)
    history = list(state.get("history") or [])[-399:]
    observation = {"captured_at": captured_at.isoformat(), **metrics}
    history.append(observation)
    state.update({
        "model_version": MODEL_VERSION,
        "last_capture_epoch": captured_at.timestamp(),
        "latest_vector": base64.b64encode(vector).decode(),
        "latest_metrics": metrics,
        "captured_at": captured_at.isoformat(),
        "history": history,
    })
    return state, observation


def should_run_ai(state: dict[str, Any], observation: dict[str, Any]) -> bool:
    if not observation.get("daylight_suitable"):
        return False
    # A released interpretation model must evaluate the next suitable frame
    # immediately. Reusing an older model's fresh result can otherwise leave
    # newly added outputs dormant until the normal daily review interval.
    if state.get("latest_ai_model_version") != MODEL_VERSION:
        return True
    elapsed = time.time() - float(state.get("last_ai_epoch") or 0)
    meaningful_change = float(observation.get("frame_change_pct") or 0) >= 8
    return not state.get("latest_ai") or elapsed >= 24 * 60 * 60 or (meaningful_change and elapsed >= AI_INTERVAL_SECONDS)


def accept_observation(state: dict[str, Any], observation: dict[str, Any], ai: dict[str, Any] | None = None) -> dict[str, Any]:
    if ai:
        state["latest_ai"] = ai
        state["latest_ai_model_version"] = MODEL_VERSION
        state["last_ai_epoch"] = time.time()
        state["ai_runs"] = int(state.get("ai_runs") or 0) + 1
        state["review_streak"] = int(state.get("review_streak") or 0) + 1 if ai.get("observation_status") == "review" else 0
    if observation.get("daylight_suitable"):
        state["usable_observations"] = int(state.get("usable_observations") or 0) + 1
    state["capture_count"] = int(state.get("capture_count") or 0) + 1
    _write_state(state)
    return public_status(state)


def public_status(state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state if state is not None else _read_state()
    history = list(state.get("history") or [])
    latest = state.get("latest_metrics") or {}
    ai = state.get("latest_ai") or {}
    suitable = [row for row in history if row.get("daylight_suitable")]
    green_values = [float(row["green_share_pct"]) for row in suitable if row.get("green_share_pct") is not None]
    trend = "building baseline"
    if len(green_values) >= 4:
        recent = sum(green_values[-2:]) / 2
        prior = sum(green_values[-4:-2]) / 2
        trend = "greener" if recent - prior >= 3 else "less green" if prior - recent >= 3 else "stable"
    return {
        # Report the active code model rather than a persisted pre-upgrade
        # label while the first new observation is being collected.
        "model_version": MODEL_VERSION,
        "status": "review" if ai.get("observation_status") == "review" else "clear" if ai else "learning",
        "status_label": "Visual change needs inspection" if ai.get("observation_status") == "review" else "No review-gated change" if ai else "Building a daylight baseline",
        "captured_at": state.get("captured_at"), "snapshot_available": SNAPSHOT_PATH.is_file(),
        "daylight_suitable": bool(latest.get("daylight_suitable")), "quality_reason": latest.get("quality_reason"),
        "frame_change_pct": latest.get("frame_change_pct"), "green_share_pct": latest.get("green_share_pct"),
        "canopy_trend": trend, "summary": ai.get("summary") or latest.get("quality_reason") or "Waiting for a fixed-view observation.",
        "inspection_reason": ai.get("inspection_reason"), "categories": ai.get("categories") or [],
        "visibility": ai.get("visibility") or ("usable" if latest.get("daylight_suitable") else "limited"),
        "operations": ai.get("operations") or "No reviewed visual observation yet.",
        "etna_region": ETNA_REGION,
        "etna_visible": bool(ai.get("etna_visible")),
        "etna_visibility": ai.get("etna_visibility") or "not assessed",
        "etna_activity": ai.get("etna_activity") or "not assessed",
        "etna_summary": ai.get("etna_summary") or "Mount Etna has not yet been assessed in a suitable clear frame.",
        "etna_official_active": bool(ai.get("etna_official_active")),
        "confidence": ai.get("confidence"), "evidence_note": "Fixed-view screening only; confirm changes in the field before action.",
        "review_streak": int(state.get("review_streak") or 0),
        "learning": {"captures": int(state.get("capture_count") or len(history)), "usable": int(state.get("usable_observations") or len(suitable)), "ai_reviews": int(state.get("ai_runs") or 0), "days": len({str(row.get("captured_at") or "")[:10] for row in suitable})},
    }


def record_failed_capture(message: str) -> dict[str, Any]:
    state = _read_state()
    state["last_capture_epoch"] = time.time()
    state["last_error"] = str(message)[:200]
    _write_state(state)
    return public_status(state)
