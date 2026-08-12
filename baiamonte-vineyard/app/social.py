from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings
from .db import transaction
from .service import estate_id, json_ready


GRAPH_ROOT = "https://graph.facebook.com"


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
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"{}")


def social_dashboard() -> dict[str, Any]:
    settings = get_settings()
    token = settings.meta_page_access_token
    output: dict[str, Any] = {
        "facebook": {"configured": bool(token and settings.facebook_page_id), "posts": [], "error": None},
        "instagram": {"configured": bool(token and settings.instagram_business_account_id), "posts": [], "error": None},
    }
    if output["facebook"]["configured"]:
        try:
            result = _graph(f"{settings.facebook_page_id}/posts", token, {"fields": "id,message,created_time,permalink_url,full_picture", "limit": 20})
            output["facebook"]["posts"] = result.get("data") or []
        except Exception as error:
            output["facebook"]["error"] = str(error)[:300]
    if output["instagram"]["configured"]:
        try:
            result = _graph(f"{settings.instagram_business_account_id}/media", token, {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 20})
            output["instagram"]["posts"] = result.get("data") or []
        except Exception as error:
            output["instagram"]["error"] = str(error)[:300]
    return json_ready(output)


def publish_facebook(message: str, link: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.meta_page_access_token or not settings.facebook_page_id:
        raise ValueError("Facebook Page publishing is not configured")
    clean = message.strip()
    if not clean:
        raise ValueError("A Facebook message is required")
    metadata = {"preview": clean[:180], "link": link}
    try:
        result = _graph(f"{settings.facebook_page_id}/feed", settings.meta_page_access_token, {"message": clean[:63206], **({"link": link.strip()} if link and link.strip() else {})}, post=True)
    except Exception as error:
        _audit("facebook", None, metadata, "failed", error)
        raise
    _audit("facebook", result.get("id"), metadata)
    return {"published": True, "id": result.get("id")}


def publish_instagram(image_url: str, caption: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.meta_page_access_token or not settings.instagram_business_account_id:
        raise ValueError("Instagram business publishing is not configured")
    image, text = image_url.strip(), caption.strip()
    if not image.startswith("https://") or not text:
        raise ValueError("Instagram requires a public HTTPS image URL and caption")
    metadata = {"preview": text[:180], "image_url": image}
    try:
        container = _graph(f"{settings.instagram_business_account_id}/media", settings.meta_page_access_token, {"image_url": image, "caption": text[:2200]}, post=True)
        creation_id = container.get("id")
        if not creation_id:
            raise ValueError("Instagram did not create the media container")
        result = _graph(f"{settings.instagram_business_account_id}/media_publish", settings.meta_page_access_token, {"creation_id": creation_id}, post=True)
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
