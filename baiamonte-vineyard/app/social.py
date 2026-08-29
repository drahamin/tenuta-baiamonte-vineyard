from __future__ import annotations

import json
import io
import os
from pathlib import Path
import secrets
import time
import zipfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one, transaction
from .service import estate_id, json_ready


GRAPH_ROOT = "https://graph.facebook.com/v24.0"
SOCIAL_CACHE_PATH = Path(os.getenv("SOCIAL_CACHE_PATH", "/data/social-cache.json"))
SOCIAL_CACHE_LIMIT = 50
SOCIAL_CACHE_MAX_AGE_SECONDS = 6 * 60 * 60
SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS = 10


class MetaGraphError(RuntimeError):
    """A useful, token-safe error returned by Meta Graph."""


def _graph(path: str, token: str, fields: dict[str, Any] | None = None, post: bool = False) -> dict[str, Any]:
    values = {**(fields or {}), "access_token": token}
    encoded = urllib.parse.urlencode(values).encode()
    request = urllib.request.Request(
        GRAPH_ROOT + "/" + path.lstrip("/"), data=encoded if post else None,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST" if post else "GET",
    )
    if not post:
        request.full_url += "?" + encoded.decode()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read() or b"{}")
            detail = payload.get("error") or {}
            message = str(detail.get("message") or "Meta rejected the request")
            code, subcode = detail.get("code"), detail.get("error_subcode")
            suffix = ", ".join(item for item in (f"code {code}" if code else "", f"subcode {subcode}" if subcode else "") if item)
            raise MetaGraphError(message + (f" ({suffix})" if suffix else "")) from error
        except (ValueError, AttributeError):
            raise MetaGraphError(f"Meta returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise MetaGraphError("Meta could not be reached: " + str(error.reason)[:180]) from error
    if payload.get("error"):
        raise MetaGraphError(str(payload["error"].get("message") or "Meta rejected the request"))
    return payload


def _graph_multipart(path: str, token: str, fields: dict[str, Any], filename: str, content_type: str, data: bytes) -> dict[str, Any]:
    """Upload one image without exposing a temporary public URL."""
    boundary = "----Baiamonte" + secrets.token_hex(12)
    parts: list[bytes] = []
    for key, value in {**fields, "access_token": token}.items():
        parts.extend([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n".encode(),
            str(value).encode(), b"\r\n",
        ])
    safe_name = Path(filename or "social-photo.jpg").name.replace('"', "")[:180]
    parts.extend([
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"{safe_name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
        data, b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        GRAPH_ROOT + "/" + path.lstrip("/"), data=b"".join(parts),
        headers={"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            detail = (json.loads(error.read() or b"{}").get("error") or {})
            raise MetaGraphError(str(detail.get("message") or f"Meta returned HTTP {error.code}")) from error
        except (ValueError, AttributeError):
            raise MetaGraphError(f"Meta returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise MetaGraphError("Meta could not be reached: " + str(error.reason)[:180]) from error
    if payload.get("error"):
        raise MetaGraphError(str(payload["error"].get("message") or "Meta rejected the upload"))
    return payload


def _read_cache() -> dict[str, Any]:
    try:
        payload = json.loads(SOCIAL_CACHE_PATH.read_text())
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(payload: dict[str, Any]) -> None:
    try:
        SOCIAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = SOCIAL_CACHE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str))
        temporary.replace(SOCIAL_CACHE_PATH)
    except OSError:
        # A read-only cache must never make social publishing fail.
        return


def _cache_is_fresh(payload: dict[str, Any]) -> bool:
    try:
        checked = datetime.fromisoformat(str(payload.get("last_checked_at") or "").replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return 0 <= (datetime.now(timezone.utc) - checked).total_seconds() < SOCIAL_CACHE_MAX_AGE_SECONDS
    except (TypeError, ValueError):
        return False


def _merge_posts(current: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in [*incoming, *current]:
        key = str(row.get("id") or row.get("permalink_url") or row.get("permalink") or "")
        if key and key not in merged:
            merged[key] = row
    return sorted(
        merged.values(), key=lambda row: str(row.get("created_time") or row.get("timestamp") or ""), reverse=True,
    )[:SOCIAL_CACHE_LIMIT]


def _post_stats(posts: list[dict[str, Any]]) -> dict[str, int]:
    images = sum(1 for row in posts if row.get("full_picture") or str(row.get("media_type") or "").upper() in {"IMAGE", "CAROUSEL_ALBUM"})
    videos = sum(1 for row in posts if "VIDEO" in str(row.get("media_type") or row.get("status_type") or "").upper())
    return {"cached_posts": len(posts), "images": images, "videos": videos}


def _publishing_stats() -> dict[str, Any]:
    try:
        rows = fetch_all(
            "SELECT integration_name,status,COUNT(*) total,MAX(created_at) last_at FROM integration_events "
            "WHERE estate_id=%s AND integration_name IN ('social-facebook','social-instagram') "
            "AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) GROUP BY integration_name,status",
            (estate_id(),),
        )
    except Exception:
        rows = []
    result = {"published_30d": 0, "failed_30d": 0, "last_publish_at": None}
    for row in rows:
        key = "published_30d" if row.get("status") == "processed" else "failed_30d"
        result[key] += int(row.get("total") or 0)
        if row.get("last_at") and (not result["last_publish_at"] or str(row["last_at"]) > str(result["last_publish_at"])):
            result["last_publish_at"] = row["last_at"]
    return result


def _accounts(token: str, page_id: str, instagram_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pages = (_graph("me/accounts", token, {
        "fields": "id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}", "limit": 100,
    }).get("data") or [])
    page = next((item for item in pages if str(item.get("id")) == page_id), None)
    if page is None and len(pages) == 1:
        page = pages[0]
    if page is None:
        if page_id:
            page = _graph(page_id, token, {"fields": "id,name,access_token,instagram_business_account{id,username,name,profile_picture_url}"})
        else:
            raise ValueError("No Facebook Page is available to this Meta token")
    instagram = page.get("instagram_business_account") or {}
    if instagram_id and str(instagram.get("id") or "") != instagram_id:
        instagram = _graph(instagram_id, token, {"fields": "id,username,name,profile_picture_url"})
    return page, instagram


def _social_events() -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            "SELECT integration_name,status,created_at,error_message,payload FROM integration_events "
            "WHERE estate_id=%s AND integration_name IN ('social-facebook','social-instagram') "
            "ORDER BY created_at DESC LIMIT 12", (estate_id(),),
        )
        for row in rows:
            try:
                row["details"] = json.loads(row.pop("payload") or "{}")
            except Exception:
                row["details"] = {}
        return rows
    except Exception:
        return []


def _audience_value(value: Any) -> int | None:
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _store_audience_snapshot(platform: str, account: dict[str, Any]) -> None:
    """Persist one immutable aggregate snapshot and its net change.

    Meta does not expose the identities of followers/unfollowers for professional
    accounts.  These rows therefore record only counts returned by Meta and never
    imply that an aggregate delta identifies a person.
    """
    external_id = str(account.get("id") or "").strip()
    followers = _audience_value(account.get("followers_count"))
    if platform not in {"facebook", "instagram"} or not external_id or followers is None:
        return
    following = _audience_value(account.get("follows_count"))
    media = _audience_value(account.get("media_count"))
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT followers_count FROM social_account_snapshots "
            "WHERE estate_id=%s AND platform=%s AND external_account_id=%s "
            "ORDER BY captured_at DESC,id DESC LIMIT 1",
            (estate_id(), platform, external_id),
        )
        previous = cursor.fetchone()
        cursor.execute(
            "INSERT INTO social_account_snapshots "
            "(estate_id,platform,external_account_id,account_name,account_username,followers_count,following_count,media_count,raw_metrics) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                estate_id(), platform, external_id, str(account.get("name") or "")[:255] or None,
                str(account.get("username") or "")[:190] or None, followers, following, media,
                json.dumps({key: account.get(key) for key in ("id", "name", "username", "profile_picture_url", "followers_count", "fan_count", "follows_count", "media_count")}),
            ),
        )
        snapshot_id = cursor.lastrowid
        prior_count = _audience_value((previous or {}).get("followers_count"))
        if prior_count is not None and prior_count != followers:
            cursor.execute(
                "INSERT INTO social_audience_events "
                "(estate_id,platform,external_account_id,event_type,audience_change,previous_count,current_count,snapshot_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    estate_id(), platform, external_id,
                    "net_follow" if followers > prior_count else "net_unfollow",
                    abs(followers - prior_count), prior_count, followers, snapshot_id,
                ),
            )


def _audience_history() -> dict[str, Any]:
    """Return durable account history without overstating Meta's identity access."""
    try:
        latest = fetch_all(
            "SELECT s.platform,s.external_account_id,s.account_name,s.account_username,s.followers_count,s.following_count,s.media_count,s.captured_at "
            "FROM social_account_snapshots s JOIN ("
            "SELECT platform,external_account_id,MAX(id) id FROM social_account_snapshots WHERE estate_id=%s GROUP BY platform,external_account_id"
            ") current ON current.id=s.id ORDER BY s.platform,s.account_name",
            (estate_id(),),
        )
        changes = fetch_all(
            "SELECT platform,event_type,SUM(audience_change) total FROM social_audience_events "
            "WHERE estate_id=%s AND detected_at>=DATE_SUB(NOW(),INTERVAL 30 DAY) GROUP BY platform,event_type",
            (estate_id(),),
        )
        events = fetch_all(
            "SELECT platform,event_type,audience_change,previous_count,current_count,detected_at "
            "FROM social_audience_events WHERE estate_id=%s ORDER BY detected_at DESC,id DESC LIMIT 100",
            (estate_id(),),
        )
        history = fetch_all(
            "SELECT platform,followers_count,captured_at FROM social_account_snapshots "
            "WHERE estate_id=%s AND captured_at>=DATE_SUB(NOW(),INTERVAL 90 DAY) ORDER BY captured_at,id",
            (estate_id(),),
        )
        totals = {"net_follows_30d": 0, "net_unfollows_30d": 0, "net_change_30d": 0}
        for row in changes:
            value = int(row.get("total") or 0)
            if row.get("event_type") == "net_follow":
                totals["net_follows_30d"] += value
                totals["net_change_30d"] += value
            else:
                totals["net_unfollows_30d"] += value
                totals["net_change_30d"] -= value
        return {
            "accounts": latest, "events": events, "history": history, "summary": totals,
            "identity_access": False,
            "identity_note": "Meta provides audience totals, not the identities of individual followers or unfollowers. Changes shown here are verified net account changes.",
        }
    except Exception:
        # The page remains usable while a new migration is being installed.
        return {
            "accounts": [], "events": [], "history": [],
            "summary": {"net_follows_30d": 0, "net_unfollows_30d": 0, "net_change_30d": 0},
            "identity_access": False,
            "identity_note": "Audience history will begin after the database migration and first successful Meta refresh.",
        }


def _relationship_rows(payload: Any, relationship_type: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        candidates = payload.get("relationships_following") or payload.get("relationships_followers") or []
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    rows: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        values = item.get("string_list_data") or []
        detail = values[0] if values and isinstance(values[0], dict) else {}
        username = str(detail.get("value") or item.get("title") or "").strip().lstrip("@").casefold()
        if not username:
            continue
        rows[username] = {
            "relationship_type": relationship_type, "username": username,
            "profile_url": str(detail.get("href") or "")[:500] or None,
            "relationship_timestamp": _audience_value(detail.get("timestamp")),
        }
    return list(rows.values())


def _read_relationship_export(data: bytes, filename: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    documents: list[tuple[str, Any]] = []
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            relevant = [member for member in archive.infolist() if member.filename.casefold().endswith(".json") and ("followers" in member.filename.casefold() or "following" in member.filename.casefold())]
            if len(relevant) > 20 or sum(member.file_size for member in relevant) > 50 * 1024 * 1024:
                raise ValueError("This Meta export contains too much relationship data to import safely")
            for member in relevant:
                lowered = member.filename.casefold()
                if member.file_size > 20 * 1024 * 1024 or not lowered.endswith(".json"):
                    continue
                try:
                    documents.append((lowered, json.loads(archive.read(member))))
                except (ValueError, UnicodeDecodeError):
                    continue
    else:
        try:
            documents.append((filename.casefold(), json.loads(data)))
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("Choose the Instagram followers/following JSON file or the Meta ZIP export") from error
    followers: dict[str, dict[str, Any]] = {}
    following: dict[str, dict[str, Any]] = {}
    for name, payload in documents:
        is_following = "following.json" in name or (isinstance(payload, dict) and "relationships_following" in payload)
        is_followers = "followers_" in name or "followers.json" in name or (isinstance(payload, dict) and "relationships_followers" in payload)
        if is_following:
            following.update({row["username"]: row for row in _relationship_rows(payload, "following")})
        elif is_followers:
            followers.update({row["username"]: row for row in _relationship_rows(payload, "follower")})
    if not followers and not following:
        raise ValueError("No Instagram follower or following records were found in this export")
    return list(followers.values()), list(following.values())


def import_relationship_export(data: bytes, filename: str, imported_by: str) -> dict[str, Any]:
    followers, following = _read_relationship_export(data, filename)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO social_relationship_imports (estate_id,platform,source_filename,followers_count,following_count,imported_by) "
            "VALUES (%s,'instagram',%s,%s,%s,%s)",
            (estate_id(), Path(filename).name[:255], len(followers), len(following), imported_by[:190] or None),
        )
        import_id = cursor.lastrowid
        for row in [*followers, *following]:
            cursor.execute(
                "INSERT INTO social_relationship_members (import_id,relationship_type,username,profile_url,relationship_timestamp) VALUES (%s,%s,%s,%s,%s)",
                (import_id, row["relationship_type"], row["username"], row["profile_url"], row["relationship_timestamp"]),
            )
        cursor.execute(
            "UPDATE alerts SET status='resolved',resolved_at=NOW() WHERE estate_id=%s "
            "AND alert_type='social_export_due' AND status IN ('open','acknowledged')",
            (estate_id(),),
        )
    return {"imported": True, "import_id": import_id, "followers": len(followers), "following": len(following), "relationships": _relationship_history()}


def _relationship_history() -> dict[str, Any]:
    try:
        imports = fetch_all(
            "SELECT id,source_filename,followers_count,following_count,imported_by,imported_at,"
            f"DATE_ADD(imported_at,INTERVAL {SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS} DAY) next_export_due_at "
            "FROM social_relationship_imports "
            "WHERE estate_id=%s AND platform='instagram' ORDER BY imported_at DESC,id DESC LIMIT 20",
            (estate_id(),),
        )
        if not imports:
            return {
                "imports": [], "not_following_back": [], "not_followed_back": [], "recent_unfollowers": [],
                "export_interval_days": SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS, "export_due": True,
                "next_export_due_at": None,
            }
        current_id = int(imports[0]["id"])
        not_following_back = fetch_all(
            "SELECT f.username,f.profile_url FROM social_relationship_members f LEFT JOIN social_relationship_members r "
            "ON r.import_id=f.import_id AND r.relationship_type='follower' AND r.username=f.username "
            "WHERE f.import_id=%s AND f.relationship_type='following' AND r.id IS NULL ORDER BY f.username",
            (current_id,),
        )
        not_followed_back = fetch_all(
            "SELECT f.username,f.profile_url FROM social_relationship_members f LEFT JOIN social_relationship_members r "
            "ON r.import_id=f.import_id AND r.relationship_type='following' AND r.username=f.username "
            "WHERE f.import_id=%s AND f.relationship_type='follower' AND r.id IS NULL ORDER BY f.username",
            (current_id,),
        )
        recent_unfollowers: list[dict[str, Any]] = []
        if len(imports) > 1:
            prior_id = int(imports[1]["id"])
            recent_unfollowers = fetch_all(
                "SELECT old.username,old.profile_url FROM social_relationship_members old LEFT JOIN social_relationship_members current "
                "ON current.import_id=%s AND current.relationship_type='follower' AND current.username=old.username "
                "WHERE old.import_id=%s AND old.relationship_type='follower' AND current.id IS NULL ORDER BY old.username",
                (current_id, prior_id),
            )
        due_row = fetch_one(
            f"SELECT NOW() >= DATE_ADD(MAX(imported_at),INTERVAL {SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS} DAY) due "
            "FROM social_relationship_imports WHERE estate_id=%s AND platform='instagram'", (estate_id(),),
        ) or {}
        return {
            "imports": imports, "not_following_back": not_following_back,
            "not_followed_back": not_followed_back, "recent_unfollowers": recent_unfollowers,
            "export_interval_days": SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS,
            "export_due": bool(due_row.get("due")),
            "next_export_due_at": imports[0].get("next_export_due_at"),
        }
    except Exception:
        return {
            "imports": [], "not_following_back": [], "not_followed_back": [], "recent_unfollowers": [],
            "export_interval_days": SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS, "export_due": False,
            "next_export_due_at": None,
        }


def _update_relationship_export_reminder() -> dict[str, Any]:
    """Maintain one non-urgent reminder for the manual Meta export step.

    Meta's supported API exposes aggregate audience metrics, but not the named
    follower/following export. The scheduler therefore automates cadence and
    comparison while leaving the account-authenticated export request to a human.
    """
    relationships = _relationship_history()
    due = bool(relationships.get("export_due"))
    with transaction() as (_, cursor):
        if due:
            cursor.execute(
                "SELECT id FROM alerts WHERE estate_id=%s AND alert_type='social_export_due' "
                "AND status IN ('open','acknowledged') LIMIT 1", (estate_id(),),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO alerts (id,estate_id,alert_type,severity,title,message,source,source_id,status,triggered_at,metadata) "
                    "VALUES (%s,%s,'social_export_due','info','Instagram relationship export due',%s,"
                    "'social-audience','instagram-relationship-export','open',NOW(),%s)",
                    (
                        str(uuid.uuid4()), estate_id(),
                        "Request the official Instagram Followers and following JSON export in Accounts Center, then import it in Admin → Social. The comparison runs automatically.",
                        json.dumps({"interval_days": SOCIAL_RELATIONSHIP_EXPORT_INTERVAL_DAYS, "supported_automation": "reminder_and_import"}),
                    ),
                )
        else:
            cursor.execute(
                "UPDATE alerts SET status='resolved',resolved_at=NOW() WHERE estate_id=%s "
                "AND alert_type='social_export_due' AND status IN ('open','acknowledged')", (estate_id(),),
            )
    return relationships


def social_dashboard(refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    token = settings.meta_page_access_token or settings.whatsapp_access_token
    activity = _social_events()
    cached = _read_cache()
    facebook_ready = bool(token and settings.facebook_page_id) or any(row.get("integration_name") == "social-facebook" and row.get("status") == "processed" for row in activity)
    instagram_ready = bool(token and settings.instagram_business_account_id) or any(row.get("integration_name") == "social-instagram" and row.get("status") == "processed" for row in activity)
    output: dict[str, Any] = {
        "facebook": {"configured": bool(token), "publishing_ready": facebook_ready, "connected": False, "posts": [], "error": None, "account": {}},
        "instagram": {"configured": bool(token), "publishing_ready": instagram_ready, "connected": False, "posts": [], "error": None, "account": {}},
        "recent_activity": activity, "cache": {"available": bool(cached), "last_checked_at": cached.get("last_checked_at"), "new_posts": 0},
        "stats": _publishing_stats(), "audience": _audience_history(), "relationships": _relationship_history(),
    }
    for channel in ("facebook", "instagram"):
        saved = cached.get(channel) if isinstance(cached.get(channel), dict) else {}
        if saved:
            output[channel].update({"connected": True, "posts": saved.get("posts") or [], "account": saved.get("account") or {}})
            output["stats"][channel] = _post_stats(output[channel]["posts"])
    if not token:
        message = "Add the permanent Meta system-user token in the protected app configuration"
        output["facebook"]["error"] = message
        output["instagram"]["error"] = message
        return json_ready(output)
    if cached and not refresh and _cache_is_fresh(cached):
        return json_ready(output)
    refreshed = False
    try:
        page, instagram = _accounts(token, settings.facebook_page_id, settings.instagram_business_account_id)
        page_token = page.get("access_token") or token
        page_metrics = _graph(str(page["id"]), page_token, {"fields": "id,name,fan_count,followers_count"})
        output["facebook"]["account"] = {
            "id": page_metrics.get("id") or page.get("id"), "name": page_metrics.get("name") or page.get("name"),
            "followers_count": page_metrics.get("followers_count", page_metrics.get("fan_count")),
            "fan_count": page_metrics.get("fan_count"),
        }
        facebook_fields: dict[str, Any] = {"fields": "id,message,created_time,permalink_url,full_picture,status_type", "limit": 25}
        result = _graph(f"{page['id']}/posts", page_token, facebook_fields)
        facebook_new = result.get("data") or []
        output["facebook"].update({"connected": True, "posts": _merge_posts(output["facebook"]["posts"], facebook_new), "error": None})
        output["cache"]["new_posts"] += len([row for row in facebook_new if row.get("id") not in {old.get("id") for old in (cached.get("facebook", {}).get("posts") or [])}])
        if instagram:
            instagram_metrics = _graph(str(instagram["id"]), page_token, {"fields": "id,username,name,profile_picture_url,followers_count,follows_count,media_count"})
            output["instagram"]["account"] = {key: instagram_metrics.get(key) for key in ("id", "username", "name", "profile_picture_url", "followers_count", "follows_count", "media_count")}
            instagram_fields: dict[str, Any] = {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 25}
            result = _graph(f"{instagram['id']}/media", page_token, instagram_fields)
            instagram_new = result.get("data") or []
            output["instagram"].update({"connected": True, "posts": _merge_posts(output["instagram"]["posts"], instagram_new), "error": None})
            output["cache"]["new_posts"] += len([row for row in instagram_new if row.get("id") not in {old.get("id") for old in (cached.get("instagram", {}).get("posts") or [])}])
        else:
            output["instagram"]["error"] = "The Facebook Page is not linked to an Instagram professional account"
        _store_audience_snapshot("facebook", output["facebook"]["account"])
        if output["instagram"]["account"]:
            _store_audience_snapshot("instagram", output["instagram"]["account"])
        output["audience"] = _audience_history()
        refreshed = True
    except Exception as error:
        message = str(error)[:500]
        if not output["facebook"]["connected"]:
            output["facebook"]["error"] = message
        if not output["instagram"]["connected"]:
            output["instagram"]["error"] = message
    if refreshed:
        checked = datetime.now(timezone.utc).isoformat()
        output["cache"].update({"available": True, "last_checked_at": checked})
        _write_cache({
            "last_checked_at": checked,
            "facebook": {"account": output["facebook"]["account"], "posts": output["facebook"]["posts"]},
            "instagram": {"account": output["instagram"]["account"], "posts": output["instagram"]["posts"]},
        })
    for channel in ("facebook", "instagram"):
        output["stats"][channel] = _post_stats(output[channel]["posts"])
    return json_ready(output)


def refresh_social_audience() -> dict[str, Any]:
    dashboard = social_dashboard(refresh=True)
    accounts = (dashboard.get("audience") or {}).get("accounts") or []
    connected = [name for name in ("facebook", "instagram") if (dashboard.get(name) or {}).get("connected")]
    relationships = _update_relationship_export_reminder()
    if not connected:
        errors = [str((dashboard.get(name) or {}).get("error") or "") for name in ("facebook", "instagram")]
        raise MetaGraphError(next((message for message in errors if message), "No Meta social account connected"))
    return {
        "connected": connected, "account_snapshots": len(accounts),
        "checked_at": (dashboard.get("cache") or {}).get("last_checked_at"),
        "relationship_export_due": relationships.get("export_due"),
        "next_relationship_export_due_at": relationships.get("next_export_due_at"),
    }


def _publishing_identity() -> tuple[dict[str, Any], dict[str, Any], str]:
    settings = get_settings()
    token = settings.meta_page_access_token or settings.whatsapp_access_token
    if not token:
        raise ValueError("Meta publishing is not configured")
    page, instagram = _accounts(token, settings.facebook_page_id, settings.instagram_business_account_id)
    return page, instagram, page.get("access_token") or token


def publish_facebook(message: str, link: str | None = None, image_url: str | None = None) -> dict[str, Any]:
    clean, image = message.strip(), (image_url or "").strip()
    if not clean:
        raise ValueError("A Facebook message is required")
    if image and not image.startswith("https://"):
        raise ValueError("A Facebook image must use a public HTTPS URL")
    metadata = {"preview": clean[:180], "link": link, "image_url": image or None}
    try:
        page, _, page_token = _publishing_identity()
        if image:
            result = _graph(f"{page['id']}/photos", page_token, {"url": image, "caption": clean[:63206]}, post=True)
        else:
            result = _graph(f"{page['id']}/feed", page_token, {"message": clean[:63206], **({"link": link.strip()} if link and link.strip() else {})}, post=True)
    except Exception as error:
        _audit("facebook", None, metadata, "failed", error)
        raise
    _audit("facebook", result.get("post_id") or result.get("id"), metadata)
    return {"published": True, "id": result.get("post_id") or result.get("id")}


def publish_instagram(image_url: str, caption: str) -> dict[str, Any]:
    image, text = image_url.strip(), caption.strip()
    if not image.startswith("https://") or not text:
        raise ValueError("Instagram requires a public HTTPS image URL and caption")
    metadata = {"preview": text[:180], "image_url": image}
    try:
        _, instagram, page_token = _publishing_identity()
        if not instagram:
            raise ValueError("The Facebook Page is not linked to an Instagram professional account")
        container = _graph(f"{instagram['id']}/media", page_token, {"image_url": image, "caption": text[:2200]}, post=True)
        creation_id = container.get("id")
        if not creation_id:
            raise ValueError("Instagram did not create the media container")
        status = {}
        for attempt in range(5):
            status = _graph(str(creation_id), page_token, {"fields": "status_code,status"})
            if status.get("status_code") in {"FINISHED", "ERROR", "EXPIRED"}:
                break
            if attempt < 4:
                time.sleep(2)
        if status.get("status_code") != "FINISHED":
            raise MetaGraphError("Instagram media preparation failed: " + str(status.get("status") or status.get("status_code") or "not ready"))
        result = _graph(f"{instagram['id']}/media_publish", page_token, {"creation_id": creation_id}, post=True)
    except Exception as error:
        _audit("instagram", None, metadata, "failed", error)
        raise
    _audit("instagram", result.get("id"), metadata)
    return {"published": True, "id": result.get("id"), "creation_id": creation_id}


def publish_social_photo(channel: str, data: bytes, filename: str, content_type: str, caption: str, link: str | None = None) -> dict[str, Any]:
    network, text = channel.casefold(), caption.strip()
    if network not in {"facebook", "instagram"}:
        raise ValueError("Choose Facebook or Instagram")
    if not text:
        raise ValueError("Enter a caption")
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("Choose a JPG, PNG or WebP photo")
    page, instagram, page_token = _publishing_identity()
    metadata = {"preview": text[:180], "filename": Path(filename).name[:180], "upload": True}
    try:
        if network == "facebook":
            fields = {"caption": text[:63206]}
            if link and link.strip():
                fields["link"] = link.strip()
            result = _graph_multipart(f"{page['id']}/photos", page_token, fields, filename, content_type, data)
            external_id = result.get("post_id") or result.get("id")
        else:
            if not instagram:
                raise ValueError("The Facebook Page is not linked to an Instagram professional account")
            staged = _graph_multipart(f"{page['id']}/photos", page_token, {"published": "false"}, filename, content_type, data)
            photo_id = staged.get("id")
            if not photo_id:
                raise MetaGraphError("Meta did not stage the uploaded photo")
            detail = _graph(str(photo_id), page_token, {"fields": "images"})
            images = detail.get("images") or []
            image_url = next((row.get("source") for row in images if row.get("source")), None)
            if not image_url:
                raise MetaGraphError("Meta did not return a usable staged photo URL")
            result = publish_instagram(str(image_url), text)
            external_id = result.get("id")
            # publish_instagram already audits the final Instagram publication.
            social_dashboard(refresh=True)
            return result
    except Exception as error:
        _audit(network, None, metadata, "failed", error)
        raise
    _audit(network, external_id, metadata)
    social_dashboard(refresh=True)
    return {"published": True, "id": external_id}


def _audit(channel: str, external_id: str | None, metadata: dict[str, Any], status: str = "processed", error: Exception | None = None) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload,error_message) VALUES (%s,%s,'outbound','social_publish',%s,%s,%s,%s)",
            (estate_id(), f"social-{channel}", str(external_id or "")[:190] or None, status, json.dumps(metadata), str(error)[:1000] if error else None),
        )
