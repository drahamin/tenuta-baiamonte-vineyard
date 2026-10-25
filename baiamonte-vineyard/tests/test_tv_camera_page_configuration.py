from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_configures_three_independent_camera_pages():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert html.count('data-tv-camera-page="') == 3
    for page in range(1, 4):
        assert f'name="tv_camera_page_{page}_name"' in html
        assert f'name="tv_camera_page_{page}_entities"' in html
        assert f'name="tv_camera_page_{page}_enabled"' in html
    assert "Each TV camera page can show up to six cameras" in javascript
    assert '"tv_camera_pages_configured": True' in backend
    assert "can contain no more than six cameras" in backend


def test_tv_display_supports_named_third_camera_page():
    html = (ROOT / "app/static/display.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/display.js").read_text(encoding="utf-8")
    display_data = (ROOT / "app/display_data.py").read_text(encoding="utf-8")
    assert 'data-screen="12"' in html
    assert 'id="additionalCameraWall"' in html
    assert "cameraScreens=[3,4,12]" in javascript
    assert "function setCameraPages" in javascript
    assert '"camera_pages": camera_pages' in display_data
    assert "range(1, 4)" in display_data
