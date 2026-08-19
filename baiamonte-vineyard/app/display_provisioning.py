"""Fully Kiosk profile and local QR builders."""

from __future__ import annotations

import io
from typing import Any
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Response
import segno

from .access import authorize_admin
from .config import Settings, get_settings


router = APIRouter(prefix="/api/v1/agronomy")


def cellar_label_origin(settings: Settings) -> str:
    value = settings.cellar_label_public_origin.strip().rstrip("/")
    if not value:
        raise HTTPException(503, "Configure cellar_label_public_origin with the HTTPS label gateway")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise HTTPException(422, "cellar_label_public_origin must be a clean HTTPS origin or gateway prefix")
    return value


@router.get("/label-provisioning", dependencies=[Depends(authorize_admin)])
def label_provisioning_profile() -> dict[str, Any]:
    settings = get_settings()
    return provisioning_profile(settings, cellar_label_origin(settings))


@router.get("/label-provisioning/qr", dependencies=[Depends(authorize_admin)])
def label_provisioning_qr() -> Response:
    settings = get_settings()
    return provisioning_qr(settings, cellar_label_origin(settings))


def provisioning_profile(settings: Settings, origin: str) -> dict[str, Any]:
    key = settings.cellar_label_enrollment_key.strip()
    return {
        "configured": bool(key),
        "public_origin": origin,
        "start_url": f"{origin}/enroll/$deviceID" if key else None,
        "basic_auth_username": "baiamonte-enroll" if key else None,
        "basic_auth_password": key or None,
        "ipad_dashboard_url": settings.cellar_ipad_dashboard_url,
        "note": "Use this Start URL in the Fully Kiosk QR provisioning profile. Keep it private.",
    }


def provisioning_qr(settings: Settings, origin: str) -> Response:
    if not settings.cellar_label_enrollment_key.strip():
        raise HTTPException(404, "Tablet enrollment is not configured")
    start_url = f"{origin}/enroll/$deviceID"
    return url_qr(start_url)


def url_qr(url: str) -> Response:
    """Return a private, non-cacheable QR code for one display URL."""
    output = io.BytesIO()
    segno.make(url, error="m").save(
        output,
        kind="svg",
        scale=6,
        border=2,
        dark="#0b0d0b",
        light="#ffffff",
        xmldecl=False,
    )
    return Response(
        content=output.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
