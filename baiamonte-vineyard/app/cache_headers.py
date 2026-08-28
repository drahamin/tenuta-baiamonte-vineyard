from starlette.middleware.base import BaseHTTPMiddleware


class ReleaseAssetCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and request.url.path.endswith((".js", ".css", ".html", ".webmanifest")):
            # Release URLs carry the add-on version (``?v=1.7.0``).  They are
            # immutable by definition and can stay in the browser cache until
            # the next release changes the URL.  Unversioned URLs keep their
            # revalidation behavior so development and recovery remain safe.
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
                if request.query_params.get("v")
                else "no-cache, must-revalidate"
            )
        return response
