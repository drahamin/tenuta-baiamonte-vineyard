from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings
from .db import fetch_all, transaction
from .service import estate_id, json_ready


GRAPH_ROOT = "https://graph.facebook.com/v24.0"


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


def social_dashboard() -> dict[str, Any]:
    settings = get_settings()
    token = settings.meta_page_access_token or settings.whatsapp_access_token
    output: dict[str, Any] = {
        "facebook": {"configured": bool(token), "connected": False, "posts": [], "error": None, "account": {}},
        "instagram": {"configured": bool(token), "connected": False, "posts": [], "error": None, "account": {}},
        "recent_activity": _social_events(),
    }
    if not token:
        message = "Add the permanent Meta system-user token in the protected app configuration"
        output["facebook"]["error"] = message
        output["instagram"]["error"] = message
        return json_ready(output)
    try:
        page, instagram = _accounts(token, settings.facebook_page_id, settings.instagram_business_account_id)
        page_token = page.get("access_token") or token
        output["facebook"]["account"] = {"id": page.get("id"), "name": page.get("name")}
        result = _graph(f"{page['id']}/posts", page_token, {"fields": "id,message,created_time,permalink_url,full_picture,status_type", "limit": 25})
        output["facebook"].update({"connected": True, "posts": result.get("data") or []})
        if instagram:
            output["instagram"]["account"] = {key: instagram.get(key) for key in ("id", "username", "name", "profile_picture_url")}
            result = _graph(f"{instagram['id']}/media", page_token, {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 25})
            output["instagram"].update({"connected": True, "posts": result.get("data") or []})
        else:
            output["instagram"]["error"] = "The Facebook Page is not linked to an Instagram professional account"
    except Exception as error:
        message = str(error)[:500]
        if not output["facebook"]["connected"]:
            output["facebook"]["error"] = message
        if not output["instagram"]["connected"]:
            output["instagram"]["error"] = message
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


def _audit(channel: str, external_id: str | None, metadata: dict[str, Any], status: str = "processed", error: Exception | None = None) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload,error_message) VALUES (%s,%s,'outbound','social_publish',%s,%s,%s,%s)",
            (estate_id(), f"social-{channel}", str(external_id or "")[:190] or None, status, json.dumps(metadata), str(error)[:1000] if error else None),
        )
