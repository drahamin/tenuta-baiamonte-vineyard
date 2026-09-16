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
    startup = (ROOT / "app" / "static" / "assets" / "performance.js").read_text(encoding="utf-8")
    # Full refresh and phased startup are mutually exclusive paths; the third
    # occurrence is the one visibility-aware recurring poll.
    assert source.count("optionalApi('api/v1/system/status'") + startup.count("optionalApi('api/v1/system/status'") == 3
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
    assert "if(!force&&screen===0&&window.data&&!paused)pendingDisplayData=payload" in source
    assert "if(screen!==0&&pendingDisplayData)" in source
    assert "$('refreshNow').onclick=()=>refresh(true)" in source


def test_tv_uses_the_preferred_human_harvest_plan_date():
    source = (ROOT / "app" / "display_data.py").read_text(encoding="utf-8")
    assert "preferred_display_plans = fetch_all(" in source
    assert "(p2.approved_by IS NOT NULL) DESC,p2.updated_at DESC" in source
    assert 'row["planned_pick_date"] = preferred.get("planned_pick_date")' in source


def test_tv_self_reloads_new_release_assets_and_supports_connectivity_head():
    javascript = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    html = (ROOT / "app" / "static" / "display.html").read_text(encoding="utf-8")
    server = (ROOT / "app" / "display_server.py").read_text(encoding="utf-8")
    data = (ROOT / "app" / "display_data.py").read_text(encoding="utf-8")
    assert 'meta name="baiamonte-version" content="__ASSET_VERSION__"' in html
    assert "loadedVersion!==currentVersion){location.reload();return}" in javascript
    assert '@display_app.head("/")' in server
    assert '"version": addon_version()' in data


def test_camera_alerts_exclude_retired_unselected_aliases():
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert "monitored_camera_entities = {" in source
    assert 'if str(row["camera_entity_id"]) in monitored_camera_entities' in source


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
    assert "async def _integration_loop_worker()" in source
    assert "Integration scheduler stopped unexpectedly; restarting" in source


def test_scheduler_staggers_remote_work_and_backs_off_failures():
    from app import intelligence

    assert intelligence._process_failure_delay({"interval_minutes": 15}, 1).total_seconds() == 30 * 60
    assert intelligence._process_failure_delay({"interval_minutes": 15}, 4).total_seconds() == 240 * 60
    assert intelligence._process_failure_delay({"interval_minutes": 60}, 8).total_seconds() == 360 * 60
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert "await asyncio.sleep(_PROCESS_STAGGER_SECONDS.get(code, 2))" in source
    assert "retry_after[code] = datetime.now() + _process_failure_delay" in source
