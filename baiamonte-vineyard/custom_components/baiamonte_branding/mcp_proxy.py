"""Narrow HTTPS edge for the Baiamonte MCP server.

Home Assistant Cloud terminates public TLS. This view forwards only the MCP
protocol path to the locally exposed Vineyard Operations MCP port. The MCP
server remains responsible for validating its bearer token; no database or
other add-on route is exposed here.
"""

from __future__ import annotations

import logging

from aiohttp import ClientError, ClientTimeout, web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

_REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "last-event-id",
    "mcp-protocol-version",
    "mcp-session-id",
    "user-agent",
}
_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-type",
    "mcp-protocol-version",
    "mcp-session-id",
    "retry-after",
}


class BaiamonteMcpProxyView(HomeAssistantView):
    """Relay the public TLS MCP route to Vineyard Operations."""

    url = "/api/baiamonte_mcp"
    name = "api:baiamonte:mcp"
    requires_auth = False

    def __init__(self, target_url: str) -> None:
        self._target_url = target_url

    async def get(self, request: web.Request) -> web.StreamResponse:
        return await self._relay(request)

    async def post(self, request: web.Request) -> web.StreamResponse:
        return await self._relay(request)

    async def delete(self, request: web.Request) -> web.StreamResponse:
        return await self._relay(request)

    async def _relay(self, request: web.Request) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _REQUEST_HEADERS
        }
        body = await request.read()
        session = async_get_clientsession(hass)
        try:
            async with session.request(
                request.method,
                self._target_url,
                params=list(request.query.items()),
                data=body or None,
                headers=headers,
                allow_redirects=False,
                timeout=ClientTimeout(total=None, connect=10, sock_read=300),
            ) as upstream:
                response_headers = {
                    name: value
                    for name, value in upstream.headers.items()
                    if name.lower() in _RESPONSE_HEADERS
                }
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=response_headers,
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(16_384):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (ClientError, TimeoutError) as error:
            _LOGGER.warning("Baiamonte MCP HTTPS relay failed: %s", error)
            return web.json_response(
                {"error": "Vineyard Operations MCP is temporarily unavailable"},
                status=502,
            )
