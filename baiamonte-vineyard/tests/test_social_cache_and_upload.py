from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_social_api_exposes_cached_refresh_and_photo_upload():
    main = read("app/main.py")
    social = read("app/social.py")
    assert "def social_center(refresh: bool = Query(False))" in main
    assert '@app.post("/api/v1/social/photo"' in main
    assert "publish_social_photo" in main
    assert "SOCIAL_CACHE_PATH" in social
    assert "def social_dashboard(refresh: bool = False)" in social


def test_social_admin_uses_cache_stats_and_local_photo_uploads():
    html = read("app/static/index.html")
    js = read("app/static/app.js")
    assert 'id="socialStats"' in html
    assert 'accept="image/jpeg,image/png,image/webp"' in html
    assert "?refresh=true" in js
    assert "api/v1/social/photo" in js
    assert "Cached posts" in js
