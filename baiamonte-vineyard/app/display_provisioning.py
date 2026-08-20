"""Fully Kiosk profiles plus local Start URL and managed-device QR builders."""

from __future__ import annotations

import io
from typing import Any
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Response
import segno

from .access import authorize_admin
from .config import Settings, get_settings
from .fully_kiosk import (
    FULLY_KIOSK_FILENAME,
    FULLY_KIOSK_SOURCE_URL,
    FULLY_KIOSK_VERSION,
    installer_is_valid,
    provisioning_payload_json,
    settings_token,
)


router = APIRouter(prefix="/api/v1/agronomy")


def cellar_label_origin(settings: Settings, *, required: bool = True) -> str:
    value = settings.cellar_label_public_origin.strip().rstrip("/")
    if not value:
        if not required:
            return ""
        raise HTTPException(503, "Configure cellar_label_public_origin with the HTTPS label gateway")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        if not required:
            return ""
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


@router.get("/label-provisioning/device-owner-qr", dependencies=[Depends(authorize_admin)])
def label_device_owner_qr() -> Response:
    settings = get_settings()
    origin = cellar_label_origin(settings)
    key = settings.cellar_label_enrollment_key.strip()
    if not key:
        raise HTTPException(404, "Tablet enrollment is not configured")
    if not installer_is_valid():
        raise HTTPException(503, "The local Fully Kiosk installer is not ready")
    return qr_response(provisioning_payload_json(origin, key, settings.tv_time_zone))


def provisioning_profile(settings: Settings, origin: str) -> dict[str, Any]:
    key = settings.cellar_label_enrollment_key.strip()
    token = settings_token(key) if key else ""
    return {
        "configured": bool(key),
        "public_origin": origin,
        "start_url": f"{origin}/enroll/$deviceID" if key else None,
        "basic_auth_username": "baiamonte-enroll" if key else None,
        "basic_auth_password": key or None,
        "managed_device_qr_url": (
            "/api/v1/agronomy/label-provisioning/device-owner-qr" if key else None
        ),
        "installer_ready": installer_is_valid(),
        "installer_version": FULLY_KIOSK_VERSION,
        "installer_url": f"{origin}/provision/{FULLY_KIOSK_FILENAME}" if key else None,
        "installer_source": FULLY_KIOSK_SOURCE_URL,
        "settings_url": f"{origin}/provision/{token}/fully-settings.json" if key else None,
        "ipad_dashboard_url": settings.cellar_ipad_dashboard_url,
        "note": "Scan the Android setup QR on a factory-reset tablet. Keep the fallback Start URL private.",
    }


def provisioning_qr(settings: Settings, origin: str) -> Response:
    if not settings.cellar_label_enrollment_key.strip():
        raise HTTPException(404, "Tablet enrollment is not configured")
    start_url = f"{origin}/enroll/$deviceID"
    return url_qr(start_url)


def url_qr(url: str) -> Response:
    """Return a private, non-cacheable QR code for one display URL."""
    return qr_response(url)


def qr_response(contents: str) -> Response:
    """Return private, non-cacheable SVG QR content."""
    output = io.BytesIO()
    segno.make(contents, error="m").save(
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
