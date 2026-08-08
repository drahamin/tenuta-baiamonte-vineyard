"""LAN-only, read-only server for the 32-inch vineyard kiosk display."""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .display_data import display_payload
from .config import get_settings, runtime_option
from .ha_auth import home_assistant_token


static_dir = Path(__file__).resolve().parent / "static"
display_app = FastAPI(title="Tenuta Baiamonte Display", docs_url=None, redoc_url=None, openapi_url=None)


TRAFFIC_KIOSK_STYLE = """
<style id="baiamonte-tv-map-mode">
html,body,.shell,main,#overview,.overview-grid,.map-panel,#tv-shell,#map{width:100%!important;height:100%!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important}
.shell{display:block!important;grid-template-columns:none!important;grid-template-rows:none!important}
#tv-shell{display:block!important;grid-template-columns:none!important;grid-template-rows:none!important}
#map{position:relative!important;display:block!important;height:100vh!important;min-height:100vh!important}
body{background:#071014!important}
aside,#fleet,main>header,.hero,.summary-strip,.status-column,.lower-grid,.section-head,.map-panel>.panel-head,.map-panel>.map-footer{display:none!important}
main{display:block!important;grid-column:auto!important;grid-row:auto!important;margin:0!important}
.page#overview{display:block!important}
.overview-grid{display:block!important}
.map-panel{display:block!important;border:0!important;border-radius:0!important;box-shadow:none!important;background:#071014!important}
.radar-map,.sea-map{width:100%!important;height:100vh!important;min-height:100vh!important;border:0!important;border-radius:0!important}
.map-controls{z-index:40!important}
.weather-status,.weather-attribution,.altitude-legend,.map-attribution{z-index:35!important}
@media (prefers-reduced-motion:reduce){.sweep,.range-ring{animation:none!important}}
</style>
"""

WEATHER_KIOSK_STYLE = """
<style id="baiamonte-tv-weather-mode">
.aircraft-marker,.altitude-legend,#map-empty{display:none!important}
.estate-map-marker{display:block!important}
</style>
<script id="baiamonte-tv-weather-zoom">
document.addEventListener('DOMContentLoaded',()=>{
  const zoom=()=>document.querySelector('button[aria-label="Zoom in"]')?.click();
  const steps=__WEATHER_ZOOM_STEPS__;
  for(let index=0;index<steps;index+=1)window.setTimeout(zoom,900+(index*350));
});
</script>
"""


def _traffic_origin(value: str) -> str:
    """Normalize saved /tv or query URLs to the traffic application's web origin."""
    parts = urllib.parse.urlsplit(str(value or "").strip())
    if parts.scheme and parts.netloc:
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
    return str(value or "").split("?", 1)[0].split("#", 1)[0].removesuffix("/tv").rstrip("/")


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
        "adsb": _traffic_origin(runtime_option("tv_adsb_url", settings.tv_adsb_url)),
        "ais": _traffic_origin(runtime_option("tv_ais_url", settings.tv_ais_url)),
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


@display_app.get("/traffic-app/{service}/{path:path}")
def traffic_app_proxy(service: str, path: str, request: Request) -> Response:
    """Serve the native traffic-app map under the TV origin for reliable iframe use."""
    settings = get_settings()
    service_urls = {
        "adsb": _traffic_origin(runtime_option("tv_adsb_url", settings.tv_adsb_url)),
        "ais": _traffic_origin(runtime_option("tv_ais_url", settings.tv_ais_url)),
    }
    base_url = service_urls.get(service)
    if not base_url:
        raise HTTPException(404, "Traffic service is not available")
    safe_path = urllib.parse.quote(path or "", safe="/@:._~!$&'()*+,;=-")
    upstream_url = f"{base_url}/{safe_path}"
    if request.url.query:
        upstream_url += "?" + request.url.query
    upstream_request = urllib.request.Request(
        upstream_url,
        headers={
            "Accept": request.headers.get("accept", "*/*"),
            "Accept-Encoding": "identity",
            "User-Agent": "Baiamonte-Vineyard-Samsung-TV/1.0",
        },
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=15) as upstream:
            content = upstream.read(12 * 1024 * 1024)
            media_type = upstream.headers.get_content_type() or "application/octet-stream"
    except Exception as error:
        raise HTTPException(502, f"{service.upper()} map is temporarily unavailable") from error
    if media_type == "text/html":
        document = content.decode("utf-8", errors="replace")
        kiosk_style = TRAFFIC_KIOSK_STYLE
        if service == "adsb" and request.query_params.get("weather") == "1":
            configured_zoom = runtime_option("tv_weather_zoom_level", settings.tv_weather_zoom_level)
            try:
                zoom_steps = int(request.query_params.get("zoom", configured_zoom))
            except (TypeError, ValueError):
                zoom_steps = int(configured_zoom)
            zoom_steps = min(6, max(0, zoom_steps))
            kiosk_style += WEATHER_KIOSK_STYLE.replace("__WEATHER_ZOOM_STEPS__", str(zoom_steps))
        document = document.replace("</head>", kiosk_style + "</head>", 1)
        content = document.encode("utf-8")
    cache_control = "no-store" if media_type in {"text/html", "application/json"} else "public, max-age=300"
    return Response(
        content,
        media_type=media_type,
        headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"},
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
