"""Token-gated public feeds, weather-map proxy, and static-page routes."""

from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from ..config import Settings, addon_version, get_settings, runtime_option
from ..db import fetch_all
from ..service import estate_id, json_ready, public_harvest_feed


router = APIRouter(tags=["public"])
static_dir = Path(__file__).resolve().parent.parent / "static"


WEATHER_MAP_STYLE = """
<style id="baiamonte-weather-map-mode">
html,body,.shell,main,#overview,.overview-grid,.map-panel,#tv-shell,#map,.map,.map-canvas,.map-container,.leaflet-container{width:100%!important;height:100%!important;min-width:100%!important;min-height:0!important;margin:0!important;padding:0!important;overflow:hidden!important}
.shell,#tv-shell{display:block!important;grid-template-columns:none!important;grid-template-rows:none!important}
body{background:#071014!important}
aside,main>header,.hero,.summary-strip,.status-column,.lower-grid,.section-head,.map-panel>.panel-head,.map-panel>.map-footer{display:none!important}
main,.page#overview,.overview-grid,.map-panel,#map,.map,.map-canvas,.map-container,.leaflet-container{display:block!important;margin:0!important;grid-column:auto!important;grid-row:auto!important}
.map-panel{border:0!important;border-radius:0!important;box-shadow:none!important;background:#071014!important}
.radar-map,#map,.map,.map-canvas,.map-container,.leaflet-container{position:relative!important;width:100%!important;height:100vh!important;min-width:100%!important;min-height:100vh!important;border:0!important;border-radius:0!important}
.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,.plane,.plane-icon,.target-aircraft,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]{display:none!important;visibility:hidden!important}
.estate-map-marker,[class*="estate-marker"],[class*="home-marker"]{display:block!important;visibility:visible!important}
.map-controls,.weather-status,.weather-attribution,.altitude-legend,.map-attribution{z-index:40!important}
@media(prefers-reduced-motion:reduce){.sweep,.range-ring{animation:none!important}}
</style>
<script id="baiamonte-weather-map-cleanup">
(()=>{const hideAircraft=()=>document.querySelectorAll('.aircraft-marker,.aircraft-label,.aircraft-icon,.plane-marker,.plane-label,.plane,.plane-icon,.target-aircraft,[class*="aircraft-marker"],[class*="aircraft-label"],[class*="plane-marker"],[data-aircraft],[data-hex]').forEach(node=>{node.style.setProperty('display','none','important');node.setAttribute('aria-hidden','true')});document.addEventListener('DOMContentLoaded',()=>{hideAircraft();const root=document.body||document.documentElement;if(root)new MutationObserver(hideAircraft).observe(root,{childList:true,subtree:true})})})();
</script>
"""


def validate_feed_token(token: str | None, settings: Settings) -> None:
    if not settings.public_feed_token or token != settings.public_feed_token:
        raise HTTPException(404, "Not found")

@router.get("/public/v1/harvest.json")
def harvest_feed(response: Response, token: str | None = None, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    validate_feed_token(token, settings)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "public, max-age=300"
    return json_ready(public_harvest_feed())


@router.get("/public/v1/harvest.ics", response_class=PlainTextResponse)
def harvest_calendar(token: str | None = None, settings: Settings = Depends(get_settings)) -> str:
    validate_feed_token(token, settings)
    rows = fetch_all("SELECT vintage_year,variety_name,first_pick_date,last_pick_date FROM v_harvest_summary WHERE estate_id=%s ORDER BY vintage_year DESC,variety_name", (estate_id(),))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Tenuta Baiamonte//Harvest//EN", "CALSCALE:GREGORIAN"]
    for row in rows:
        if not row["first_pick_date"]:
            continue
        start = row["first_pick_date"].strftime("%Y%m%d")
        end_date = row["last_pick_date"] or row["first_pick_date"]
        end = end_date.fromordinal(end_date.toordinal() + 1).strftime("%Y%m%d")
        lines.extend(["BEGIN:VEVENT", f"UID:{row['vintage_year']}-{row['variety_name']}@baiamonte", f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}", f"SUMMARY:Harvest — {row['variety_name']}", "END:VEVENT"])
    lines.extend(["END:VCALENDAR", ""])
    return "\r\n".join(lines)


@router.get("/weather-map/{path:path}")
def weather_map_proxy(path: str, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    configured_url = str(runtime_option("tv_adsb_url", settings.tv_adsb_url) or "").strip()
    parts = urllib.parse.urlsplit(configured_url)
    if parts.scheme and parts.netloc:
        base_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
        configured_path = parts.path.rstrip("/")
    else:
        clean_url = configured_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        configured_path = "/tv" if clean_url.endswith("/tv") else ""
        base_url = clean_url.removesuffix("/tv").rstrip("/")
    if not base_url:
        raise HTTPException(503, "The precipitation map service is not configured")
    safe_path = urllib.parse.quote(path or "", safe="/@:._~!$&'()*+,;=-")
    root_path = configured_path or "/tv"
    upstream_path = f"/{safe_path}" if safe_path else root_path
    upstream_url = f"{base_url}{upstream_path}"
    if request.url.query:
        upstream_url += "?" + request.url.query
    upstream_request = urllib.request.Request(
        upstream_url,
        headers={"Accept": request.headers.get("accept", "*/*"), "Accept-Encoding": "identity", "User-Agent": "Baiamonte-Vineyard-Weather/1.0"},
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=15) as upstream:
            content = upstream.read(12 * 1024 * 1024)
            media_type = upstream.headers.get_content_type() or "application/octet-stream"
    except Exception as error:
        raise HTTPException(502, "The precipitation map service is temporarily unavailable") from error
    if media_type == "text/html":
        document = content.decode("utf-8", errors="replace")
        document = document.replace("</head>", WEATHER_MAP_STYLE + "</head>", 1)
        content = document.encode("utf-8")
    cache_control = "no-store" if media_type in {"text/html", "application/json"} else "public, max-age=300"
    return Response(content, media_type=media_type, headers={"Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"})


def _versioned_html(filename: str) -> HTMLResponse:
    document = (static_dir / filename).read_text(encoding="utf-8").replace("__ASSET_VERSION__", addon_version())
    return HTMLResponse(document, headers={"Cache-Control": "no-cache"})


@router.get("/")
def index() -> HTMLResponse:
    return _versioned_html("index.html")


@router.get("/crew")
def crew_entry_page() -> FileResponse:
    return FileResponse(static_dir / "crew.html")


@router.get("/display")
def vineyard_display_page() -> HTMLResponse:
    return _versioned_html("display.html")

