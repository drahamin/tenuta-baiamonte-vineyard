import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


def _vector(value: tuple[int, int, int], pixels: int = 64 * 36) -> bytes:
    return bytes(value) * pixels


def test_dark_frame_is_not_ai_suitable():
    from app.domains import vineyard_visual

    with tempfile.TemporaryDirectory() as directory, \
         patch.object(vineyard_visual, "ROOT", Path(directory)), \
         patch.object(vineyard_visual, "STATE_PATH", Path(directory) / "state.json"), \
         patch.object(vineyard_visual, "SNAPSHOT_PATH", Path(directory) / "latest.jpg"), \
         patch.object(vineyard_visual, "_rgb_vector", return_value=_vector((5, 5, 5))):
        state, observation = vineyard_visual.analyze_frame(b"image", datetime.now(timezone.utc))
        assert observation["daylight_suitable"] is False
        assert vineyard_visual.should_run_ai(state, observation) is False


def test_green_signal_and_change_are_forward_only():
    from app.domains import vineyard_visual

    current = _vector((55, 130, 60))
    changed = _vector((80, 170, 65))
    with tempfile.TemporaryDirectory() as directory, \
         patch.object(vineyard_visual, "ROOT", Path(directory)), \
         patch.object(vineyard_visual, "STATE_PATH", Path(directory) / "state.json"), \
         patch.object(vineyard_visual, "SNAPSHOT_PATH", Path(directory) / "latest.jpg"), \
         patch.object(vineyard_visual, "_rgb_vector", side_effect=[current, changed]):
        first_state, first = vineyard_visual.analyze_frame(b"first")
        vineyard_visual.accept_observation(first_state, first)
        second_state, second = vineyard_visual.analyze_frame(b"second")
        assert first["frame_change_pct"] is None
        assert second["frame_change_pct"] is not None
        assert second["green_share_pct"] == 100.0


def test_public_copy_is_inspection_gated_not_diagnostic():
    from app.domains.vineyard_visual import public_status

    status = public_status({
        "latest_metrics": {"daylight_suitable": True, "green_share_pct": 62, "frame_change_pct": 9},
        "latest_ai": {"observation_status": "review", "summary": "A changed terrace area should be inspected.", "categories": ["canopy_change"]},
        "review_streak": 2,
    })
    assert status["status"] == "review"
    assert "confirm changes in the field" in status["evidence_note"].lower()
    assert "disease" not in status["summary"].lower()
    assert status["etna_region"]["label"] == "Mount Etna summit"
    assert status["etna_activity"] == "not assessed"


def test_etna_visual_finding_is_exposed_with_official_correlation_flag():
    from app.domains.vineyard_visual import public_status

    status = public_status({
        "latest_metrics": {"daylight_suitable": True},
        "latest_ai": {
            "observation_status": "review", "confidence": 0.88,
            "categories": ["etna_summit_activity"], "etna_visible": True,
            "etna_visibility": "clear", "etna_activity": "possible_plume",
            "etna_summary": "A summit-attached plume may be visible.",
            "etna_official_active": False,
        },
    })
    assert status["etna_visible"] is True
    assert status["etna_visibility"] == "clear"
    assert status["etna_activity"] == "possible_plume"
    assert status["etna_official_active"] is False


def test_dashboard_and_tv_surface_visual_watch():
    root = Path(__file__).resolve().parents[1] / "app" / "static"
    assert "vineyardVisualWatch" in (root / "index.html").read_text()
    assert "renderVineyardVisualWatch" in (root / "app.js").read_text()
    assert "tvVisualWatch" in (root / "display.html").read_text()
    assert "VINEYARD NORTH · FIXED-VIEW EVIDENCE" in (root / "display.js").read_text()
    assert "ETNA SUMMIT" in (root / "display.js").read_text()
    assert "Etna summit" in (root / "assets" / "operations-enhancements.js").read_text()


def test_rtsp_credentials_are_not_part_of_public_status():
    from app.domains.vineyard_visual import public_status

    output = str(public_status({"latest_metrics": {}, "rtsp_url": "rtsp://user:secret@example/live0"}))
    assert "secret" not in output
    assert "rtsp://" not in output
