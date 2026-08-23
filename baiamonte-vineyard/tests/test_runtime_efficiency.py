from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_data_caches_match_real_client_cadence():
    source = (ROOT / "app" / "display_data.py").read_text(encoding="utf-8")
    assert "_HA_CACHE_SECONDS = 30" in source
    assert "_DISPLAY_CACHE_SECONDS = 90" in source


def test_frontend_uses_one_visibility_aware_status_poll():
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    # One request belongs to the initial parallel page load and one to the
    # single recurring poll. There must not be a second recurring timer.
    assert source.count("optionalApi('api/v1/system/status'") == 2
    assert "lastAssetVersionCheck" in source
    assert "},30000);" in source
    assert "},15000);" not in source
    assert "if(!document.hidden)updateAdminUptime()" in source


def test_tv_background_scrolling_stops_when_hidden_and_runs_once_per_second():
    source = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "if(document.hidden)return;scrollIntelligenceAlerts();scrollTvOverflowLists()},1000)" in source
