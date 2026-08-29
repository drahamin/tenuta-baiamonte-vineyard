"""Administrator-only Facebook and Instagram routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from ..access import authorize_admin
from ..service import json_ready
from ..social import import_relationship_export, publish_facebook, publish_instagram, publish_social_photo, social_dashboard


router = APIRouter(prefix="/api/v1/social", tags=["social"])


@router.get("", dependencies=[Depends(authorize_admin)])
def social_center(refresh: bool = Query(False)) -> dict[str, Any]:
    return social_dashboard(refresh=refresh)


@router.post("/facebook", dependencies=[Depends(authorize_admin)])
def social_publish_facebook(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_facebook(str(payload.get("message") or ""), str(payload.get("link") or "") or None, str(payload.get("image_url") or "") or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Facebook publish failed: " + str(error)[:300]) from error


@router.post("/instagram", dependencies=[Depends(authorize_admin)])
def social_publish_instagram(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return publish_instagram(str(payload.get("image_url") or ""), str(payload.get("caption") or ""))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Instagram publish failed: " + str(error)[:300]) from error


@router.post("/photo", dependencies=[Depends(authorize_admin)])
async def social_publish_photo(channel: str = Form(...), caption: str = Form(...), link: str = Form(""), file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Choose a photo smaller than 12 MB")
    try:
        return publish_social_photo(channel, data, file.filename or "social-photo.jpg", file.content_type or "application/octet-stream", caption, link or None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(502, "Social photo publish failed: " + str(error)[:300]) from error


@router.post("/audience-import", dependencies=[Depends(authorize_admin)])
async def social_audience_import(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(50 * 1024 * 1024 + 1)
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "Choose a Meta export smaller than 50 MB")
    try:
        username = (request.headers.get("X-Remote-User-Name") or "administrator").strip()
        return json_ready(import_relationship_export(data, file.filename or "instagram-export.zip", username))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(500, "Instagram relationship import failed: " + str(error)[:300]) from error
