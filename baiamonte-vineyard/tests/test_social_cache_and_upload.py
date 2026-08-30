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
    assert 'reactions.limit(0).summary(true)' in social
    assert 'comments.limit(0).summary(true)' in social
    assert 'like_count,comments_count' in social
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


def test_social_post_audit_combines_supported_engagement_counts():
    stats = social_module._post_stats([
        {"timestamp": datetime.now(timezone.utc).isoformat(), "media_type": "IMAGE", "like_count": 12, "comments_count": 3},
        {"created_time": datetime.now(timezone.utc).isoformat(), "status_type": "VIDEO", "reactions": {"summary": {"total_count": 8}}, "comments": {"summary": {"total_count": 2}}, "shares": {"count": 1}},
    ])
    assert stats["total_engagements"] == 26
    assert stats["posts_30d"] == 2
    assert stats["average_engagements"] == 13


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


def test_media_heavy_meta_export_reads_relationship_members_from_disk(tmp_path):
    archive_path = tmp_path / "instagram-export.zip"
    followers = [{"string_list_data": [{"value": "alice"}]}]
    following = {"relationships_following": [{"title": "bob", "string_list_data": [{"value": "bob"}]}]}
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("media/other/large-photo.jpg", b"not relationship data" * 1000)
        archive.writestr("connections/followers_and_following/followers_1.json", json.dumps(followers))
        archive.writestr("connections/followers_and_following/following.json", json.dumps(following))
    parsed_followers, parsed_following = social_module._read_relationship_export_file(archive_path, archive_path.name)
    assert [row["username"] for row in parsed_followers] == ["alice"]
    assert [row["username"] for row in parsed_following] == ["bob"]


def test_social_admin_explains_meta_identity_limit_and_supports_export_import():
    html = read("app/static/index.html")
    javascript = read("app/static/assets/social-audience.js")
    routes = read("app/domains/social_routes.py")
    migration = read("db/migrations/129_social_audience_history.sql")
    assert 'id="socialAudienceImport"' in html
    assert 'class="panel social-followers-archive"' in html
    assert 'id="socialAuditMetrics"' in html
    assert "New followers" in html
    assert "Recent unfollowers" in html
    assert "api/v1/social/audience-import" in javascript
    assert "MAX_RELATIONSHIP_EXPORT_BYTES = 512 * 1024 * 1024" in routes
    assert "NamedTemporaryFile" in routes
    assert "social_account_snapshots" in migration
    assert "social_relationship_members" in migration


def test_social_audit_adds_supported_automatic_meta_statistics():
    social = read("app/social.py")
    html = read("app/static/index.html")
    javascript = read("app/static/assets/social-audience.js")
    assert "def _account_insights(" in social
    assert "page_post_engagements" in social
    assert "accounts_engaged" in social
    assert "total_engagements" in social
    assert "Audience, reciprocity & data quality" in html
    assert "follow_back_rate" in javascript
    assert "Audit source health" in javascript
    assert "No background profile scraping is used" in html


def test_social_insights_isolate_retired_metric_without_losing_supported_data(monkeypatch):
    def graph(_path, _token, params):
        if "," in params["metric"]:
            raise RuntimeError("one bundled metric is unavailable")
        if params["metric"] == "reach":
            return {"data": [{"name": "reach", "values": [{"value": 12}, {"value": 8}]}]}
        raise RuntimeError("unsupported")

    monkeypatch.setattr(social_module, "_graph", graph)
    result = social_module._account_insights("instagram", "ig-id", "token")
    assert result["available"] is True
    assert result["metrics"]["reach"] == 20
    assert "views" in result["missing_metrics"]


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
