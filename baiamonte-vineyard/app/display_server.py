"""LAN-only, read-only server for the 32-inch vineyard kiosk display."""

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .display_data import display_payload
from .config import addon_version, get_settings, runtime_option
from .ha_auth import home_assistant_token


static_dir = Path(__file__).resolve().parent / "static"
display_app = FastAPI(title="Tenuta Baiamonte Display", docs_url=None, redoc_url=None, openapi_url=None)


# Eufy cameras are sensitive to bursts of camera-proxy requests. Keep one
# shared cache for the kiosk and serialize upstream captures across viewers.
CAMERA_CACHE_SECONDS = 90
CAMERA_STALE_SECONDS = 15 * 60
_camera_cache: dict[str, tuple[float, bytes, str]] = {}
_camera_capture_lock = threading.Lock()
CAMERA_CACHE_DIR = Path("/data/tv-camera-cache")


def _saved_camera_path(entity_id: str) -> Path:
    return CAMERA_CACHE_DIR / (re.sub(r"[^a-z0-9_.-]", "_", entity_id.casefold()) + ".image")


def _saved_camera(entity_id: str) -> tuple[bytes, str, int] | None:
    path = _saved_camera_path(entity_id)
    try:
        content = path.read_bytes()
        if not content:
            return None
        media_type = "image/png" if content.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        age_seconds = max(0, int(time.time() - path.stat().st_mtime))
        return content, media_type, age_seconds
    except OSError:
        return None


def _remember_camera(entity_id: str, content: bytes) -> None:
    try:
        CAMERA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _saved_camera_path(entity_id).write_bytes(content)
    except OSError:
        pass


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
.boat-icon{width:20px!important;height:29px!important;transform:translate(-10px,-14.5px) rotate(var(--heading))!important}.boat{filter:drop-shadow(0 2px 4px rgba(0,0,0,.58))!important}
.boat-label,.map-vessel-label{border:1px solid rgba(212,175,55,.72)!important;border-left:3px solid var(--vessel-color,#d4af37)!important;border-radius:6px!important;background:linear-gradient(135deg,rgba(8,18,20,.97),rgba(18,22,22,.96))!important;box-shadow:0 5px 16px rgba(0,0,0,.62)!important;color:#faf6f0!important;backdrop-filter:none!important}
.boat-label{height:20px!important;padding:4px 6px!important;font-size:8px!important;line-height:10px!important}
.boat-label b,.map-vessel-label b{color:#fffaf0!important}.boat-label span,.map-vessel-label span,.boat-label em,.map-vessel-label em{color:#bdb4a7!important}
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


def _scope_ais_payload(payload: dict, area_id: str = "baiamonte") -> dict:
    """Keep the kiosk AIS list in the same configured area as its map."""
    scoped = dict(payload)
    config = dict(scoped.get("config") or {})
    areas = config.get("map_areas") or []
    area = next(
        (item for item in areas if str(item.get("id") or "").lower() == area_id),
        None,
    )
    bounds = dict((area or {}).get("bounds") or config.get("bounds") or {})

    def belongs(vessel: dict) -> bool:
        vessel_area = str(vessel.get("area_id") or "").strip().lower()
        if vessel_area:
            return vessel_area == area_id
        try:
            latitude = float(vessel.get("latitude"))
            longitude = float(vessel.get("longitude"))
            return (
                float(bounds["south"]) <= latitude <= float(bounds["north"])
                and float(bounds["west"]) <= longitude <= float(bounds["east"])
            )
        except (KeyError, TypeError, ValueError):
            return False

    vessels = [item for item in scoped.get("vessels") or [] if isinstance(item, dict) and belongs(item)]
    nearest = [item for item in scoped.get("nearest_vessels") or [] if isinstance(item, dict) and belongs(item)]

    def distance(vessel: dict) -> float:
        try:
            return float(vessel.get("distance_km"))
        except (TypeError, ValueError):
            return float("inf")

    scoped["vessels"] = vessels
    scoped["nearest_vessels"] = nearest or sorted(
        vessels,
        key=distance,
    )[:10]
    config["area_id"] = area_id
    if bounds:
        config["bounds"] = bounds
    scoped["config"] = config
    return scoped


@display_app.get("/")
def display_home() -> HTMLResponse:
    document = (static_dir / "display.html").read_text(encoding="utf-8").replace("__ASSET_VERSION__", addon_version())
    return HTMLResponse(document, headers={"Cache-Control": "no-cache"})


@display_app.get("/display")
def display_alias() -> HTMLResponse:
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
    status_url = service_urls[service] + "/api/status"
    if service == "ais":
        status_url += "?area=baiamonte"
    request = urllib.request.Request(
        status_url,
        headers={"Accept": "application/json", "User-Agent": "Baiamonte-Vineyard-TV/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as upstream:
            content = upstream.read(2 * 1024 * 1024)
        payload = json.loads(content)
        if service == "ais":
            payload = _scope_ais_payload(payload, "baiamonte")
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
        configured_target_size = runtime_option(
            "tv_adsb_target_size_percent" if service == "adsb" else "tv_ais_target_size_percent",
            settings.tv_adsb_target_size_percent if service == "adsb" else settings.tv_ais_target_size_percent,
        )
        try:
            target_size = min(180, max(70, int(request.query_params.get("target_size", configured_target_size))))
        except (TypeError, ValueError):
            target_size = 100
        kiosk_style += (
            "<style>:root{--baiamonte-target-scale:" + str(round(target_size / 100, 2)) + "}"
            ".leaflet-marker-icon:not(.leaflet-div-icon),.maplibregl-marker,.mapboxgl-marker,.aircraft-marker,.vessel-marker,.ship-marker{"
            "scale:var(--baiamonte-target-scale)!important;transform-origin:center center!important}"
            ".leaflet-marker-icon img,.leaflet-marker-icon svg,.maplibregl-marker img,.maplibregl-marker svg{max-width:none!important}</style>"
        )
        if service == "adsb" and request.query_params.get("weather") == "1":
            configured_zoom = runtime_option("tv_weather_zoom_level", settings.tv_weather_zoom_level)
            try:
                zoom_steps = int(request.query_params.get("zoom", configured_zoom))
            except (TypeError, ValueError):
                zoom_steps = int(configured_zoom)
            zoom_steps = min(6, max(0, zoom_steps))
            kiosk_style += WEATHER_KIOSK_STYLE.replace("__WEATHER_ZOOM_STEPS__", str(zoom_steps))
        elif request.query_params.get("map_zoom"):
            try:
                zoom_steps = min(20, max(-6, int(request.query_params.get("map_zoom", "0"))))
            except (TypeError, ValueError):
                zoom_steps = 0
            if service == "adsb":
                apply_zoom = (
                    "if(typeof geoMap==='undefined'||!geoMap.currentView)return false;"
                    f"geoMap.manualCenter=geoMap.currentView.center;geoMap.manualZoom=Math.max(5,Math.min(18,geoMap.currentView.zoom+({zoom_steps})));"
                    "geoMap.notifyViewChange();return true;"
                )
            else:
                apply_zoom = (
                    "if(typeof latest==='undefined'||!latest||typeof currentTvView!=='function')return false;"
                    f"manualZoom=Math.max(2,Math.min(18,currentTvView().zoom+({zoom_steps})));"
                    "if(typeof rerenderMap==='function')rerenderMap();return true;"
                )
            kiosk_style += (
                "<script id='baiamonte-saved-map-zoom'>window.addEventListener('load',function(){var attempts=0;var timer=setInterval(function(){attempts++;try{if((function(){"
                + "if(window.BaiamonteNativeMapControls)return true;" + apply_zoom +
                "})())clearInterval(timer)}catch(error){}if(attempts>=20)clearInterval(timer)},250)});</script>"
            )
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
    """Serve a gentle, cached still without opening parallel Eufy sessions."""
    entity_id = urllib.parse.unquote(entity_id)
    camera_setting = str(runtime_option("tv_camera_entities", get_settings().tv_camera_entities))
    allowed = {value.strip() for value in camera_setting.split(",") if value.strip().startswith("camera.")}
    if entity_id not in allowed and not re.fullmatch(r"camera\.[a-z0-9_]+", entity_id):
        raise HTTPException(404, "Camera not available on this display")
    now = time.monotonic()
    cached = _camera_cache.get(entity_id)
    if cached and now - cached[0] < CAMERA_CACHE_SECONDS:
        return Response(cached[1], media_type=cached[2], headers={"Cache-Control": "private, max-age=60", "X-Baiamonte-Camera": "cache"})

    # If another tile/viewer is already obtaining a frame, immediately serve
    # the last good frame. With no prior frame, wait briefly instead of adding
    # another simultaneous request to Home Assistant/Eufy.
    acquired = _camera_capture_lock.acquire(timeout=2)
    if not acquired:
        if cached:
            return Response(cached[1], media_type=cached[2], headers={"Cache-Control": "private, max-age=30", "X-Baiamonte-Camera": "stale-busy"})
        saved = _saved_camera(entity_id)
        if saved:
            content, media_type, age_seconds = saved
            return Response(content, media_type=media_type, headers={"Cache-Control": "private, max-age=30", "X-Baiamonte-Camera": "saved-stale", "X-Baiamonte-Camera-Age": str(age_seconds)})
        raise HTTPException(503, "Camera refresh is busy; retry shortly")
    try:
        # A frame may have been refreshed while this request waited for the
        # lock, so check the cache again before touching Home Assistant.
        now = time.monotonic()
        cached = _camera_cache.get(entity_id)
        if cached and now - cached[0] < CAMERA_CACHE_SECONDS:
            return Response(cached[1], media_type=cached[2], headers={"Cache-Control": "private, max-age=60", "X-Baiamonte-Camera": "cache-after-wait"})
        token = home_assistant_token()
        if not token:
            raise RuntimeError("Home Assistant camera access is unavailable")
        request = urllib.request.Request(
            "http://supervisor/core/api/camera_proxy/" + urllib.parse.quote(entity_id, safe="."),
            headers={"Authorization": f"Bearer {token}", "Accept": "image/jpeg,image/png"},
        )
        with urllib.request.urlopen(request, timeout=12) as upstream:
            content = upstream.read(8 * 1024 * 1024)
            media_type = upstream.headers.get_content_type() or "image/jpeg"
        if not content:
            raise RuntimeError("Camera returned an empty image")
        _camera_cache[entity_id] = (time.monotonic(), content, media_type)
        _remember_camera(entity_id, content)
        return Response(content, media_type=media_type, headers={"Cache-Control": "private, max-age=60", "X-Baiamonte-Camera": "fresh"})
    except Exception as error:
        cached = _camera_cache.get(entity_id)
        if cached:
            age_seconds = max(0, int(time.monotonic() - cached[0]))
            return Response(cached[1], media_type=cached[2], headers={"Cache-Control": "private, max-age=30", "X-Baiamonte-Camera": "stale-error", "X-Baiamonte-Camera-Age": str(age_seconds)})
        saved = _saved_camera(entity_id)
        if saved:
            content, media_type, age_seconds = saved
            return Response(content, media_type=media_type, headers={"Cache-Control": "private, max-age=30", "X-Baiamonte-Camera": "saved-stale", "X-Baiamonte-Camera-Age": str(age_seconds)})
        raise HTTPException(502, "Camera image is temporarily unavailable") from error
    finally:
        _camera_capture_lock.release()


@display_app.get("/health")
def display_health() -> dict[str, bool]:
    return {"ok": True, "read_only": True}


display_app.mount("/assets", StaticFiles(directory=static_dir), name="display-assets")
