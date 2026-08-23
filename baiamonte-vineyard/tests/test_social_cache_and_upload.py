from pathlib import Path
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from app import social as social_module


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
    assert "SOCIAL_CACHE_MAX_AGE_SECONDS" in social
    assert "_cache_is_fresh(cached)" in social
    assert "def social_dashboard(refresh: bool = False)" in social


def test_social_refresh_replaces_expiring_meta_media_urls_for_visible_posts():
    social = read("app/social.py")
    assert 'facebook_fields: dict[str, Any] = {"fields": "id,message,created_time,permalink_url,full_picture,status_type", "limit": 25}' in social
    assert 'instagram_fields: dict[str, Any] = {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 25}' in social
    assert 'facebook_fields["since"]' not in social
    assert 'instagram_fields["since"]' not in social


def test_expired_social_cache_retries_without_marking_failed_refresh_fresh(tmp_path, monkeypatch):
    cache = tmp_path / "social.json"
    old_checked = "2026-08-18T16:18:38+00:00"
    cache.write_text(json.dumps({"last_checked_at": old_checked, "facebook": {"posts": [{"id": "1", "full_picture": "https://expired.invalid/photo.jpg"}]}}))
    monkeypatch.setattr(social_module, "SOCIAL_CACHE_PATH", cache)
    monkeypatch.setattr(social_module, "get_settings", lambda: SimpleNamespace(meta_page_access_token="token", whatsapp_access_token="", facebook_page_id="page", instagram_business_account_id="ig"))
    monkeypatch.setattr(social_module, "_social_events", lambda: [])
    monkeypatch.setattr(social_module, "_publishing_stats", lambda: {})
    monkeypatch.setattr(social_module, "_accounts", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    result = social_module.social_dashboard()
    assert result["cache"]["last_checked_at"] == old_checked
    assert json.loads(cache.read_text())["last_checked_at"] == old_checked


def test_social_cache_freshness_expires_temporary_meta_links():
    assert social_module._cache_is_fresh({"last_checked_at": datetime.now(timezone.utc).isoformat()})
    assert not social_module._cache_is_fresh({"last_checked_at": "2020-01-01T00:00:00+00:00"})


def test_social_admin_uses_cache_stats_and_local_photo_uploads():
    html = read("app/static/index.html")
    js = read("app/static/app.js")
    assert 'id="socialStats"' in html
    assert 'accept="image/jpeg,image/png,image/webp"' in html
    assert "?refresh=true" in js
    assert "api/v1/social/photo" in js
    assert "Cached posts" in js
