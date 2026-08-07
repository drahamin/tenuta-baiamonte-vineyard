"""LAN-only, read-only server for the 32-inch vineyard kiosk display."""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .display_data import display_payload
from .config import get_settings, runtime_option
from .ha_auth import home_assistant_token


static_dir = Path(__file__).resolve().parent / "static"
display_app = FastAPI(title="Tenuta Baiamonte Display", docs_url=None, redoc_url=None, openapi_url=None)


@display_app.get("/")
def display_home() -> FileResponse:
    return FileResponse(static_dir / "display.html", headers={"Cache-Control": "no-cache"})


@display_app.get("/display")
def display_alias() -> FileResponse:
    return display_home()


@display_app.get("/api/display-data")
def display_data() -> dict:
    return display_payload()


@display_app.get("/api/traffic/{service}")
def traffic_status(service: str) -> Response:
    """Proxy the local ADS-B and AIS status feeds for the kiosk display."""
    settings = get_settings()
    service_urls = {
        "adsb": str(runtime_option("tv_adsb_url", settings.tv_adsb_url)).rstrip("/"),
        "ais": str(runtime_option("tv_ais_url", settings.tv_ais_url)).rstrip("/"),
    }
    if service not in service_urls:
        raise HTTPException(404, "Traffic service is not available")
    request = urllib.request.Request(
        service_urls[service] + "/api/status",
        headers={"Accept": "application/json", "User-Agent": "Baiamonte-Vineyard-TV/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as upstream:
            content = upstream.read(2 * 1024 * 1024)
        payload = json.loads(content)
    except Exception as error:
        raise HTTPException(502, f"{service.upper()} status is temporarily unavailable") from error
    return Response(
        json.dumps(payload, separators=(",", ":")),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@display_app.get("/api/camera/{entity_id}")
def camera_snapshot(entity_id: str) -> Response:
    """Proxy configured cameras and automatically discovered gate/door cameras."""
    entity_id = urllib.parse.unquote(entity_id)
    camera_setting = str(runtime_option("tv_camera_entities", get_settings().tv_camera_entities))
    allowed = {value.strip() for value in camera_setting.split(",") if value.strip().startswith("camera.")}
    if entity_id not in allowed and not re.fullmatch(r"camera\.[a-z0-9_]+", entity_id):
        raise HTTPException(404, "Camera not available on this display")
    token = home_assistant_token()
    if not token:
        raise HTTPException(503, "Home Assistant camera access is unavailable")
    request = urllib.request.Request(
        "http://supervisor/core/api/camera_proxy/" + urllib.parse.quote(entity_id, safe="."),
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as upstream:
            content = upstream.read(8 * 1024 * 1024)
            media_type = upstream.headers.get_content_type() or "image/jpeg"
    except Exception as error:
        raise HTTPException(502, "Camera image is temporarily unavailable") from error
    return Response(content, media_type=media_type, headers={"Cache-Control": "no-store"})


@display_app.get("/health")
def display_health() -> dict[str, bool]:
    return {"ok": True, "read_only": True}


display_app.mount("/assets", StaticFiles(directory=static_dir), name="display-assets")
