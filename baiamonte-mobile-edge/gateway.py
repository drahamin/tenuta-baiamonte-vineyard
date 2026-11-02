"""Isolated mobile edge candidate. Never targets a caller-selected upstream.

No deployment or connector credentials are included. Serve on loopback only.
The static asset set must be frozen from the installed HA login flow.
"""
from collections import OrderedDict, deque
import re
import time

from aiohttp import ClientSession, ClientTimeout, web

HOST = "baiamonte.rhmproxy.com"
ORIGIN = "http://172.30.32.1:8123"
PREFIX = "/api/baiamonte_mobile/v1/"
READS = {"session", "status", "catalog", "records", "weather", "work", "review", "energy", "etna"}
GETS = {"/oauth/client-metadata.json", "/auth/authorize"}
POSTS = {"/auth/token", "/auth/revoke", "/auth/login_flow", PREFIX + "session/exchange", PREFIX + "session/revoke"}
LIMIT = 65536
RESPONSE_LIMIT = 2 * 1024 * 1024
HOP = {"connection", "upgrade", "keep-alive", "transfer-encoding", "te", "trailer", "proxy-authorization", "proxy-authenticate"}


def allowed_methods(path, assets):
    if path in GETS or path in assets:
        return {"GET", "HEAD"}
    if path in POSTS or re.fullmatch(r"/auth/login_flow/[0-9a-f]{32}", path):
        return {"POST"}
    if path.startswith(PREFIX) and path[len(PREFIX):] in READS:
        return {"GET"}
    return set()


def validate_assets(assets):
    result = set()
    for path in assets:
        if not re.fullmatch(r"/(?:frontend_latest|static)/[A-Za-z0-9_./-]+", path) or ".." in path or "//" in path:
            raise ValueError("invalid frozen asset path")
        result.add(path)
    # Explicit public branding images, never arbitrary /local content.
    result.update({"/local/baiamonte-branding/logon-logo.png", "/local/baiamonte-branding/favicon.png"})
    return frozenset(result)


def safe_headers(headers):
    connection_names = {s.strip().lower() for s in headers.get("Connection", "").split(",")}
    return {k: v for k, v in headers.items()
            if k.lower() not in HOP | connection_names | {"host", "forwarded", "content-length"}
            and not k.lower().startswith(("x-remote-", "x-ingress-", "x-baiamonte-", "x-forwarded-", "cf-"))}


def create_app(assets=(), *, upstream=ORIGIN):
    """upstream injection is for isolated tests, never an HTTP parameter."""
    assets = validate_assets(assets)
    buckets = OrderedDict()
    app = web.Application(client_max_size=LIMIT)

    async def lifecycle(app):
        app["client"] = ClientSession(timeout=ClientTimeout(total=25, connect=5), auto_decompress=False)
        yield
        await app["client"].close()

    async def handle(request):
        if request.host.lower() != HOST:
            raise web.HTTPNotFound()
        raw_path = request.raw_path.partition("?")[0]
        if raw_path != request.path or "//" in raw_path or ".." in raw_path or len(request.query_string) > 2048:
            raise web.HTTPNotFound()
        methods = allowed_methods(request.path, assets)
        if not methods:
            raise web.HTTPNotFound()
        if request.method not in methods:
            raise web.HTTPMethodNotAllowed(request.method, methods)
        if request.headers.get("Upgrade") or "upgrade" in request.headers.get("Connection", "").lower():
            raise web.HTTPNotFound()
        now = time.monotonic()
        # The listener is loopback-only behind the dedicated connector. Bound
        # both request rate and memory even if client headers are forged.
        key = request.remote or "unknown"
        bucket = buckets.pop(key, deque())
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= 120:
            raise web.HTTPTooManyRequests(headers={"Retry-After": "60"})
        bucket.append(now)
        buckets[key] = bucket
        if len(buckets) > 1024:
            buckets.popitem(last=False)
        if request.content_length and request.content_length > LIMIT:
            raise web.HTTPRequestEntityTooLarge(max_size=LIMIT, actual_size=request.content_length)
        body = await request.read()
        if request.method != "POST" and body:
            raise web.HTTPBadRequest()
        headers = safe_headers(request.headers)
        headers["Host"] = HOST
        try:
            async with app["client"].request(request.method, upstream + request.raw_path,
                    headers=headers, data=body, allow_redirects=False) as response:
                payload = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    payload.extend(chunk)
                    if len(payload) > RESPONSE_LIMIT:
                        raise web.HTTPBadGateway()
                response_headers = [(k, v) for k, v in response.headers.items()
                                    if k.lower() not in HOP | {"content-length", "server"}]
                result = web.Response(status=response.status, body=bytes(payload), headers=response_headers)
                result.headers["Cache-Control"] = "no-store"
                result.headers["Referrer-Policy"] = "no-referrer"
                result.headers["X-Content-Type-Options"] = "nosniff"
                return result
        except web.HTTPException:
            raise
        except Exception:
            # Do not log URLs, authorization, login bodies, or upstream errors.
            raise web.HTTPBadGateway() from None

    app.cleanup_ctx.append(lifecycle)
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


if __name__ == "__main__":
    import json
    from pathlib import Path
    frozen = json.loads(Path("/data/login-assets.json").read_text())
    web.run_app(create_app(frozen), host="127.0.0.1", port=8184, access_log=None)
