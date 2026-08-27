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
