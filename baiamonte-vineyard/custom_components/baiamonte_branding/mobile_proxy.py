"""Route-closed proxy for narrow Baiamonte native-app sessions."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from aiohttp import ClientError, ClientTimeout, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .proxy_io import bounded_response_body, load_mobile_gateway_runtime, signed_exchange_headers


_LOGGER = logging.getLogger(__name__)
PUBLIC_PREFIX = "/api/baiamonte_mobile/v1"
PUBLIC_ORIGIN = "https://baiamonte.rhmproxy.com"
OAUTH_CLIENT_ID = f"{PUBLIC_ORIGIN}/oauth/client-metadata.json"
OAUTH_REDIRECT_URI = "baiamonte-vineyard://auth/callback"
ALLOWED_ROUTES = {"session", "status", "catalog", "records", "weather", "work", "review", "energy", "etna"}
RESPONSE_HEADERS = {"cache-control", "content-type", "etag", "last-modified", "retry-after", "x-content-type-options"}
_BEARER_PATTERN = re.compile(r"Bearer [A-Za-z0-9_-]{43}")


class _MobileRelay:
    def __init__(self, config_dir: str | Path) -> None:
        self._config_dir = Path(config_dir)

    def _require_runtime(
        self,
        request: web.Request,
        *,
        require_enabled: bool = True,
    ) -> dict[str, str | bool]:
        runtime = load_mobile_gateway_runtime(self._config_dir, require_enabled=require_enabled)
        if not runtime:
            raise web.HTTPNotFound()
        if request.host.partition(":")[0].casefold() != runtime["public_host"]:
            raise web.HTTPNotFound()
        return runtime

    async def _response(self, upstream: object) -> web.Response:
        try:
            body = await bounded_response_body(upstream)
        except ValueError:
            return web.json_response({"error": "response_too_large"}, status=502)
        response_headers = {
            name: value for name, value in upstream.headers.items() if name.lower() in RESPONSE_HEADERS
        }
        response_headers["Cache-Control"] = "no-store"
        response_headers["Referrer-Policy"] = "no-referrer"
        return web.Response(status=upstream.status, headers=response_headers, body=body)


class BaiamonteMobileProxyView(HomeAssistantView, _MobileRelay):
    url = f"{PUBLIC_PREFIX}/{{route}}"
    name = "api:baiamonte:mobile"
    requires_auth = False

    def __init__(self, config_dir: str | Path) -> None:
        _MobileRelay.__init__(self, config_dir)

    async def get(self, request: web.Request, route: str) -> web.Response:
        runtime = self._require_runtime(request)
        if route not in ALLOWED_ROUTES:
            raise web.HTTPNotFound()
        if len(request.query_string) > 2048:
            raise web.HTTPRequestEntityTooLarge(max_size=2048, actual_size=len(request.query_string))
        authorization = request.headers.get("Authorization", "")
        if _BEARER_PATTERN.fullmatch(authorization) is None:
            raise web.HTTPUnauthorized()
        session = async_get_clientsession(request.app["hass"])
        try:
            async with session.get(
                f"{runtime['target_origin']}/api/v1/mobile/{route}",
                params=list(request.query.items()),
                headers={"Accept": "application/json", "Authorization": authorization},
                allow_redirects=False,
                timeout=ClientTimeout(total=20, connect=5),
            ) as upstream:
                return await self._response(upstream)
        except (ClientError, TimeoutError) as error:
            _LOGGER.warning("Baiamonte mobile site relay failed: %s", error)
            return web.json_response({"error": "site_unavailable"}, status=502, headers={"Cache-Control": "no-store"})


class BaiamonteMobileExchangeView(HomeAssistantView, _MobileRelay):
    url = f"{PUBLIC_PREFIX}/session/exchange"
    name = "api:baiamonte:mobile-exchange"
    requires_auth = True

    def __init__(self, config_dir: str | Path) -> None:
        _MobileRelay.__init__(self, config_dir)

    async def post(self, request: web.Request) -> web.Response:
        runtime = self._require_runtime(request)
        user = request.get("hass_user")
        user_id = str(getattr(user, "id", "") or "") if user and getattr(user, "is_active", True) else ""
        if not user_id:
            raise web.HTTPForbidden()
        try:
            proof = signed_exchange_headers(str(runtime["exchange_hmac_key"]), user_id)
        except ValueError:
            return web.json_response({"error": "exchange_not_configured"}, status=503, headers={"Cache-Control": "no-store"})
        session = async_get_clientsession(request.app["hass"])
        try:
            async with session.post(
                f"{runtime['target_origin']}/api/v1/mobile/session/exchange",
                headers={"X-Ingress-Path": PUBLIC_PREFIX, "X-Remote-User-Id": user_id, **proof},
                allow_redirects=False,
                timeout=ClientTimeout(total=20, connect=5),
            ) as upstream:
                return await self._response(upstream)
        except (ClientError, TimeoutError) as error:
            _LOGGER.warning("Baiamonte mobile session exchange failed: %s", error)
            return web.json_response({"error": "site_unavailable"}, status=502, headers={"Cache-Control": "no-store"})


class BaiamonteMobileRevokeView(HomeAssistantView, _MobileRelay):
    url = f"{PUBLIC_PREFIX}/session/revoke"
    name = "api:baiamonte:mobile-revoke"
    requires_auth = False

    def __init__(self, config_dir: str | Path) -> None:
        _MobileRelay.__init__(self, config_dir)

    async def post(self, request: web.Request) -> web.Response:
        runtime = self._require_runtime(request, require_enabled=False)
        authorization = request.headers.get("Authorization", "")
        if _BEARER_PATTERN.fullmatch(authorization) is None:
            raise web.HTTPUnauthorized()
        session = async_get_clientsession(request.app["hass"])
        try:
            async with session.post(
                f"{runtime['target_origin']}/api/v1/mobile/session/revoke",
                headers={"Authorization": authorization},
                allow_redirects=False,
                timeout=ClientTimeout(total=20, connect=5),
            ) as upstream:
                return await self._response(upstream)
        except (ClientError, TimeoutError) as error:
            _LOGGER.warning("Baiamonte mobile session revoke failed: %s", error)
            return web.json_response({"error": "site_unavailable"}, status=502, headers={"Cache-Control": "no-store"})


class BaiamonteOAuthClientMetadataView(HomeAssistantView):
    url = "/oauth/client-metadata.json"
    name = "api:baiamonte:mobile-oauth-metadata"
    requires_auth = False

    def __init__(self, config_dir: str | Path) -> None:
        self._config_dir = Path(config_dir)

    async def get(self, request: web.Request) -> web.Response:
        runtime = load_mobile_gateway_runtime(self._config_dir)
        if runtime.get("enabled") is not True:
            raise web.HTTPNotFound()
        if request.host.partition(":")[0].casefold() != runtime["public_host"]:
            raise web.HTTPNotFound()
        return web.json_response(
            {"client_id": OAUTH_CLIENT_ID, "redirect_uris": [OAUTH_REDIRECT_URI]},
            headers={"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"},
        )
