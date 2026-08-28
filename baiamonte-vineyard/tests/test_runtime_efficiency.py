from pathlib import Path
from datetime import datetime
from unittest.mock import patch


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


def test_scheduled_tv_refresh_does_not_rebuild_the_visible_today_page():
    source = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "pendingDisplayData=null" in source
    assert "if(!force&&screen===0&&window.data)pendingDisplayData=payload" in source
    assert "if(screen!==0&&pendingDisplayData)" in source
    assert "$('refreshNow').onclick=()=>refresh(true)" in source


def test_scheduler_resumes_persisted_cadence_after_addon_restart():
    from app import intelligence

    observed = datetime(2026, 8, 28, 10, 0, 0)
    with patch.object(intelligence, "fetch_all", return_value=[
        {"integration_name": "home-assistant-weather", "occurred_at": observed},
        {"integration_name": "camera-awareness", "occurred_at": observed.isoformat()},
    ]):
        last_runs = intelligence._persisted_process_last_runs()

    assert last_runs == {"weather": observed, "cameras": observed}
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert "last_run: dict[str, datetime] = _persisted_process_last_runs()" in source
