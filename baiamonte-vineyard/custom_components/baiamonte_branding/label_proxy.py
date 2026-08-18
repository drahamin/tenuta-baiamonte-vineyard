"""Public, read-only HTTPS gateway for Baiamonte cellar displays.

Home Assistant Cloud terminates TLS.  This view exposes only the display
service's tokenized pages, assets and Basic-authenticated enrollment route;
administration and every other add-on port remain unreachable here.
"""

from __future__ import annotations

import logging
import re

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

PUBLIC_PREFIX = "/api/baiamonte_labels"
_SAFE_PATH = re.compile(
    r"^(?:"
    r"(?:tank|kiosk)/[A-Za-z0-9-]{16,128}|"
    r"enroll/[A-Za-z0-9._:-]{4,200}|"
    r"api/(?:tank|kiosk)/[A-Za-z0-9-]{16,128}|"
    r"api/enroll/[A-Za-z0-9._:-]{4,200}|"
    r"assets/[A-Za-z0-9._-]{1,120}|"
    r"brand/(?:(?:logo|icon)\.png|icon\.svg)|"
    r"manifest/(?:tank|kiosk|enroll)/[A-Za-z0-9._:-]{4,200}\.webmanifest|"
    r"robots\.txt"
    r")$"
)
_REQUEST_HEADERS = {"accept", "authorization", "user-agent"}
_RESPONSE_HEADERS = {
    "cache-control",
    "content-length",
    "content-type",
    "etag",
    "expires",
    "last-modified",
    "pragma",
    "referrer-policy",
    "www-authenticate",
    "x-content-type-options",
    "x-frame-options",
    "x-robots-tag",
}


class BaiamonteLabelProxyView(HomeAssistantView):
    """Relay only explicitly permitted cellar-display GET requests."""

    url = f"{PUBLIC_PREFIX}/{{path:.*}}"
    name = "api:baiamonte:labels"
    requires_auth = False

    def __init__(self, target_origin: str) -> None:
        self._target_origin = target_origin.rstrip("/")

    async def get(self, request: web.Request, path: str) -> web.Response:
        if not _SAFE_PATH.fullmatch(path):
            raise web.HTTPNotFound()
        hass: HomeAssistant = request.app["hass"]
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _REQUEST_HEADERS
        }
        session = async_get_clientsession(hass)
        try:
            async with session.get(
                f"{self._target_origin}/{path}",
                params=list(request.query.items()),
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=30, connect=10),
            ) as upstream:
                body = await upstream.read()
                content_type = upstream.headers.get("Content-Type", "")
                if content_type.startswith("text/html"):
                    body = body.replace(b'"/assets/', f'"{PUBLIC_PREFIX}/assets/'.encode())
                    body = body.replace(b'"/brand/', f'"{PUBLIC_PREFIX}/brand/'.encode())
                    body = body.replace(b'"/manifest/', f'"{PUBLIC_PREFIX}/manifest/'.encode())
                response_headers = {
                    name: value
                    for name, value in upstream.headers.items()
                    if name.lower() in _RESPONSE_HEADERS and name.lower() != "content-length"
                }
                location = upstream.headers.get("Location")
                if location:
                    response_headers["Location"] = (
                        f"{PUBLIC_PREFIX}{location}" if location.startswith("/") else location
                    )
                return web.Response(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=response_headers,
                    body=body,
                )
        except (ClientError, TimeoutError) as error:
            _LOGGER.warning("Baiamonte label HTTPS relay failed: %s", error)
            return web.Response(
                text="The cellar display service is temporarily unavailable.",
                status=502,
                headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
            )
