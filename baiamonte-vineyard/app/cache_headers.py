from starlette.middleware.base import BaseHTTPMiddleware


class ReleaseAssetCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and request.url.path.endswith((".js", ".css", ".html", ".webmanifest")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
