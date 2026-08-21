from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tv_data_refresh_ignores_window_focus_and_bypasses_cache():
    script = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "url.searchParams.set('_live'" in script
    assert "{cache:'no-store'}" in script
    assert "async function refresh(){if(refreshInFlight)return" in script
    assert "async function refreshTraffic(kind){if(trafficRefreshInFlight[kind])return" in script
    assert "if(document.hidden||refreshInFlight)" not in script
    assert "if(document.hidden||trafficRefreshInFlight" not in script
    assert "if(screen!==page||document.hidden)" not in script
    assert "||document.hidden||cameraRefreshInFlight" not in script
