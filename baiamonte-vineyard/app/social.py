from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import get_settings
from .db import fetch_all, transaction
from .service import estate_id, json_ready


GRAPH_ROOT = "https://graph.facebook.com/v24.0"
SOCIAL_CACHE_PATH = Path(os.getenv("SOCIAL_CACHE_PATH", "/data/social-cache.json"))
SOCIAL_CACHE_LIMIT = 50
SOCIAL_CACHE_MAX_AGE_SECONDS = 6 * 60 * 60


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
        "stats": _publishing_stats(),
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
        output["facebook"]["account"] = {"id": page.get("id"), "name": page.get("name")}
        facebook_fields: dict[str, Any] = {"fields": "id,message,created_time,permalink_url,full_picture,status_type", "limit": 25}
        result = _graph(f"{page['id']}/posts", page_token, facebook_fields)
        facebook_new = result.get("data") or []
        output["facebook"].update({"connected": True, "posts": _merge_posts(output["facebook"]["posts"], facebook_new), "error": None})
        output["cache"]["new_posts"] += len([row for row in facebook_new if row.get("id") not in {old.get("id") for old in (cached.get("facebook", {}).get("posts") or [])}])
        if instagram:
            output["instagram"]["account"] = {key: instagram.get(key) for key in ("id", "username", "name", "profile_picture_url")}
            instagram_fields: dict[str, Any] = {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 25}
            result = _graph(f"{instagram['id']}/media", page_token, instagram_fields)
            instagram_new = result.get("data") or []
            output["instagram"].update({"connected": True, "posts": _merge_posts(output["instagram"]["posts"], instagram_new), "error": None})
            output["cache"]["new_posts"] += len([row for row in instagram_new if row.get("id") not in {old.get("id") for old in (cached.get("instagram", {}).get("posts") or [])}])
        else:
            output["instagram"]["error"] = "The Facebook Page is not linked to an Instagram professional account"
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
