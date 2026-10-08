from pathlib import Path
from unittest.mock import patch

import pytest

from app import intelligence


ROOT = Path(__file__).resolve().parents[1]


def test_home_assistant_states_use_last_complete_snapshot_on_transient_failure():
    cached = [{"entity_id": "camera.gate", "state": "idle"}]
    previous = intelligence._ha_states_cache
    intelligence._ha_states_cache = (0.0, cached)
    try:
        with (
            patch.object(intelligence, "home_assistant_token", return_value="token"),
            patch("app.intelligence.urllib.request.urlopen", side_effect=OSError("HTTP Error 502: Bad Gateway")),
        ):
            assert intelligence._ha_get("/states") == cached
    finally:
        intelligence._ha_states_cache = previous


def test_home_assistant_states_degrade_to_empty_before_first_success():
    previous = intelligence._ha_states_cache
    intelligence._ha_states_cache = None
    try:
        with (
            patch.object(intelligence, "home_assistant_token", return_value="token"),
            patch("app.intelligence.urllib.request.urlopen", side_effect=OSError("HTTP Error 502: Bad Gateway")),
        ):
            assert intelligence._ha_get("/states") == []
    finally:
        intelligence._ha_states_cache = previous


def test_home_assistant_history_retries_transient_supervisor_gateway_errors():
    response = type("Response", (), {
        "__enter__": lambda self: self,
        "__exit__": lambda self, *args: None,
        "read": lambda self: b"[]",
    })()
    gateway_error = intelligence.urllib.error.HTTPError("url", 502, "Bad Gateway", {}, None)
    with (
        patch.object(intelligence, "home_assistant_token", return_value="token"),
        patch.object(intelligence.time, "sleep"),
        patch("app.intelligence.urllib.request.urlopen", side_effect=[gateway_error, response]) as urlopen,
    ):
        assert intelligence._ha_get("/history/period/2026-10-08") == []
    assert urlopen.call_count == 2


def test_gmail_poll_bounds_mailbox_and_retries_only_one_transient_failed_intake():
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert ")[-50:]" in source
    assert "LIKE '%%overload%%'" in source
    assert "i.updated_at<DATE_SUB(NOW(),INTERVAL 10 MINUTE)" in source
    assert "LIMIT 1" in source


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "dashboards" / "vineyard-overview.yaml",
        ROOT.parent / "dashboard" / "tenuta-baiamonte-dashboard-integrated.yaml",
    ],
)
def test_weather_radar_uses_keyless_openstreetmap_basemap(path: Path):
    text = path.read_text(encoding="utf-8")
    marker = "type: custom:weather-radar-card"
    block = text[text.index(marker) : text.index(marker) + 500]
    assert "map_style: OSM" in block
    assert "map_style: Dark" not in block
