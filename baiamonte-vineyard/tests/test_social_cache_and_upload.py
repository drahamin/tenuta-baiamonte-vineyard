from pathlib import Path
from datetime import datetime, timezone
import io
import json
import zipfile
from types import SimpleNamespace

from app import social as social_module


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_social_api_exposes_cached_refresh_and_photo_upload():
    routes = read("app/domains/social_routes.py")
    social = read("app/social.py")
    assert "def social_center(refresh: bool = Query(False))" in routes
    assert '@router.post("/photo"' in routes
    assert "publish_social_photo" in routes
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


def test_instagram_export_parser_compares_official_relationship_data():
    followers = [
        {"string_list_data": [{"href": "https://instagram.com/alice", "value": "Alice", "timestamp": 1}]},
        {"string_list_data": [{"href": "https://instagram.com/bob", "value": "bob", "timestamp": 2}]},
    ]
    following = {"relationships_following": [
        {"title": "bob", "string_list_data": [{"href": "https://instagram.com/bob", "value": "Bob", "timestamp": 3}]},
        {"title": "carol", "string_list_data": [{"href": "https://instagram.com/carol", "value": "Carol", "timestamp": 4}]},
    ]}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("connections/followers_and_following/followers_1.json", json.dumps(followers))
        archive.writestr("connections/followers_and_following/following.json", json.dumps(following))
    parsed_followers, parsed_following = social_module._read_relationship_export(buffer.getvalue(), "instagram.zip")
    assert {row["username"] for row in parsed_followers} == {"alice", "bob"}
    assert {row["username"] for row in parsed_following} == {"bob", "carol"}


def test_social_admin_explains_meta_identity_limit_and_supports_export_import():
    html = read("app/static/index.html")
    javascript = read("app/static/assets/social-audience.js")
    migration = read("db/migrations/129_social_audience_history.sql")
    assert 'id="socialAudienceImport"' in html
    assert "Recent unfollowers" in html
    assert "api/v1/social/audience-import" in javascript
    assert "social_account_snapshots" in migration
    assert "social_relationship_members" in migration


def test_social_relationship_exports_use_safe_ten_day_cadence():
    social = read("app/social.py")
    html = read("app/static/index.html")
    javascript = read("app/static/assets/social-audience.js")
    assert "SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS = 10" in social
    assert "alert_type='social_export_due'" in social
    assert "Accounts Center" in html
    assert "Automatic 10-day check is current" in javascript
    assert "accountscenter.instagram.com/info_and_permissions/dyi/" in javascript


def test_social_relationship_due_state_starts_without_scraping(monkeypatch):
    monkeypatch.setattr(social_module, "fetch_all", lambda *_args, **_kwargs: [])
    result = social_module._relationship_history()
    assert result["export_due"] is True
    assert result["export_interval_days"] == 10
    assert result["next_export_due_at"] is None
