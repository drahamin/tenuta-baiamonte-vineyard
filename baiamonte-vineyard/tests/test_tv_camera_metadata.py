from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tv_camera_payload_exposes_safe_useful_metadata():
    source = (ROOT / "app/display_data.py").read_text()
    for field in ("wifi", "snapshot_available", "snapshot_source", "snapshot_updated_at"):
        assert f'"{field}"' in source


def test_tv_labels_snapshot_source_without_exposing_identifiers():
    source = (ROOT / "app/static/display.js").read_text()
    assert "HOMEBASE EVENT" in source
    assert "CAMERA EVENT" in source
    assert "ON-DEMAND STILL" in source
    assert "snapshot_source" in source
