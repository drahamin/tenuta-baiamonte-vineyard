"""Disabled-by-default, identity/resource-bound remote reads. Never a proxy."""
from __future__ import annotations

import hmac
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from .config import get_settings
from .remote_access import authorize_remote, resource_id
from . import remote_read_data


display_gateway_app = FastAPI(title="Baiamonte Remote Read Gateway", docs_url=None, redoc_url=None, openapi_url=None)
_ORIGIN_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
_ASSET_ROOT = Path(__file__).parent / "remote_static"
_ASSETS = {"remote-read.js": "text/javascript", "remote-read.css": "text/css"}
_RESOURCE = re.compile(r"labels/(?:(api)/)?(tank|kiosk)/([a-f0-9-]{36})")
_SECURITY_HEADERS = {
    "Cache-Control": "no-store, private, max-age=0",
    "Pragma": "no-cache",
    "Vary": "Cf-Access-Jwt-Assertion, X-Baiamonte-Display-Gateway, Host",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; worker-src 'none'",
}


def classify_remote_path(path: str) -> tuple[str, str, str | None]:
    match = _RESOURCE.fullmatch(path)
    if match:
        api, kind, identifier = match.groups()
        return "labels", ("api_" if api else "page_") + kind, resource_id(identifier)
    if path in {"field/", "pos/", "field/api/tasks", "pos/api/catalog"}:
        surface = path.split("/", 1)[0]
        return surface, "page" if path.endswith("/") else "api", None
    for surface in ("labels", "field", "pos"):
        prefix = surface + "/assets/"
        if path.startswith(prefix) and path[len(prefix):] in _ASSETS:
            return surface, "asset", path[len(prefix):]
    raise HTTPException(404, "not found")


def _authorize_origin(value: str | None) -> None:
    settings = get_settings()
    configured = str(settings.display_gateway_origin_token or "").strip()
    if not settings.display_gateway_enabled or _ORIGIN_TOKEN.fullmatch(configured) is None:
        raise HTTPException(503, "remote access unavailable")
    if value is None or not hmac.compare_digest(value, configured):
        raise HTTPException(401, "authentication required")


@display_gateway_app.middleware("http")
async def remote_boundary(request: Request, call_next):
    if request.method not in {"GET", "HEAD"}:
        response = JSONResponse({"detail": "not found"}, status_code=404)
    elif b"%" in request.scope.get("raw_path", b"") or request.url.query or request.headers.get("transfer-encoding") or request.headers.get("content-length", "0") != "0":
        response = JSONResponse({"detail": "not found"}, status_code=404)
    else:
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse({"detail": "remote data unavailable"}, status_code=503)
    response.headers.update(_SECURITY_HEADERS)
    return response


@display_gateway_app.api_route("/{path:path}", methods=["GET", "HEAD"])
def remote_read(path: str, request: Request) -> Response:
    surface, kind, identifier = classify_remote_path(path)
    _authorize_origin(request.headers.get("X-Baiamonte-Display-Gateway"))
    assertions = request.headers.getlist("Cf-Access-Jwt-Assertion")
    if len(assertions) != 1:
        raise HTTPException(401, "authentication required")
    hosts = request.headers.getlist("Host")
    if len(hosts) != 1:
        raise HTTPException(404, "not found")
    profile = authorize_remote(hosts[0], surface, assertions[0])
    if kind.endswith("tank") or kind.endswith("kiosk"):
        profile.require("tank_ids" if kind.endswith("tank") else "kiosk_ids", identifier)
    if kind == "asset":
        return Response((_ASSET_ROOT / identifier).read_bytes() if request.method != "HEAD" else b"", media_type=_ASSETS[identifier])
    if kind.startswith("page"):
        # A kiosk page checks its current tank binding too, without last_seen writes.
        if kind == "page_kiosk":
            remote_read_data.kiosk(profile, identifier)
        elif kind == "page_tank":
            remote_read_data.tank(profile, identifier)
        page = (_ASSET_ROOT / "index.html").read_text(encoding="utf-8").replace("__SURFACE__", surface)
        return HTMLResponse(page if request.method != "HEAD" else "")
    if kind == "api_tank":
        payload = remote_read_data.tank(profile, identifier)
    elif kind == "api_kiosk":
        payload = remote_read_data.kiosk(profile, identifier)
    elif surface == "field":
        payload = remote_read_data.field_tasks(profile)
    else:
        payload = remote_read_data.pos_catalog(profile)
    return JSONResponse(remote_read_data.envelope(payload) if request.method != "HEAD" else None)
