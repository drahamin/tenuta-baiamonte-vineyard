from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tv_data_refresh_ignores_window_focus_and_bypasses_cache():
    script = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "url.searchParams.set('_live'" in script
    assert "{cache:'no-store'}" in script
    assert "async function refresh(force=false){if(refreshInFlight)return" in script
    assert "async function refreshTraffic(kind){if(trafficRefreshInFlight[kind])return" in script
    assert "if(document.hidden||refreshInFlight)" not in script
    assert "if(document.hidden||trafficRefreshInFlight" not in script
    assert "if(screen!==page||document.hidden)" not in script
    assert "||document.hidden||cameraRefreshInFlight" not in script


def test_camera_pages_do_not_force_refresh_on_every_rotation_or_focus():
    script = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "cameraRefreshSeconds=Math.max(900,refreshSeconds)" in script
    assert "cameraPageRefreshAt={3:0,4:0}" in script
    assert "lastRefresh=cameraPageRefreshAt[page]||0" in script
    assert "if(completed)cameraPageRefreshAt[page]=Date.now()" in script
    assert "if([3,4].includes(screen)&&screen!==page)setTimeout(()=>refreshCameras(),0)" in script
    assert "refreshCameras(true)" not in script


def test_etna_camera_reloads_only_when_the_source_marker_changes():
    script = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
    assert "e.webcam_updated_utc||camera.updated_at||camera.image_url" in script
    assert "if(image.dataset.cameraVersion!==cameraVersion)" in script
    assert "t=${Date.now()}" not in script
