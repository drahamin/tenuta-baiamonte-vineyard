"""Read-only airport weather, official notices, and Etna aviation context."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
import json
import math
import re
import threading
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings, runtime_option


AWC_API = "https://aviationweather.gov/api/data"
CATANIA_NEWS = "https://aeroporto.catania.it/en/news"
ETNA_LOCATION = (37.748, 15.000)
AIRPORT_FALLBACKS = {
    "LICC": {"icao": "LICC", "iata": "CTA", "name": "Catania Fontanarossa", "latitude": 37.4668, "longitude": 15.0664, "elevation_ft": 39},
}
_cache: dict[str, dict[str, Any]] = {}
_cache_at: dict[str, datetime] = {}
_lock = threading.Lock()


def _fetch(url: str, accept: str = "application/json,text/html;q=0.8") -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Tenuta-Baiamonte-Airport-Monitor/1.0", "Accept": accept})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(2_000_000).decode("utf-8", errors="replace")


def _json_rows(path: str, icao: str, **params: Any) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"ids": icao, "format": "json", **params})
    payload = json.loads(_fetch(f"{AWC_API}/{path}?{query}"))
    return payload if isinstance(payload, list) else []


def _strip(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _number(value: Any) -> float | None:
    try:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None
    except (TypeError, ValueError):
        return None


def _airport_notices(html: str) -> list[dict[str, str]]:
    """Extract operationally relevant entries from the official airport news page."""
    notices: list[dict[str, str]] = []
    seen: set[str] = set()
    next_data = re.search(r"<script[^>]+id=['\"]__NEXT_DATA__['\"][^>]*>(.*?)</script>", html, re.I | re.S)
    if next_data:
        try:
            payload = json.loads(unescape(next_data.group(1)))

            def walk(value: Any) -> None:
                if isinstance(value, dict):
                    title = _strip(str(value.get("title") or ""))
                    normalized = title.casefold()
                    if value.get("slug") and any(term in normalized for term in ("etna", "erupt", "ash", "volcan", "closure", "closed", "disruption", "delay", "cancel")):
                        url = urllib.parse.urljoin(CATANIA_NEWS + "/", str(value["slug"]))
                        if url not in seen:
                            seen.add(url)
                            notices.append({"title": title[:180], "summary": _strip(str(value.get("excerpt") or ""))[:350], "published_at": str(value.get("date") or ""), "url": url, "source": "Catania Airport"})
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)

            walk(payload)
        except (ValueError, TypeError):
            pass
    if notices:
        notices.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        return notices[:5]
    pattern = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
    terms = ("etna", "erupt", "ash", "volcan", "flight operation", "airspace", "closure", "closed", "disruption", "delay", "cancel")
    for href, body in pattern.findall(html):
        title = _strip(body)
        normalized = title.casefold()
        if len(title) < 8 or not any(term in normalized for term in terms):
            continue
        url = urllib.parse.urljoin(CATANIA_NEWS, href)
        if url in seen:
            continue
        seen.add(url)
        notices.append({"title": title[:180], "summary": "", "published_at": "", "url": url, "source": "Catania Airport"})
    return notices[:5]


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    y = math.sin(delta) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(delta)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _direction_degrees(value: str) -> float | None:
    points = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
    return points.get(value.upper())


def _impact_assessment(airport: dict[str, Any], etna: dict[str, Any]) -> dict[str, Any]:
    ash = etna.get("ash_advisory") or {}
    code = str(ash.get("aviation_colour_code") or "UNKNOWN").upper()
    closure_notice: dict[str, Any] | None = None
    restriction_notice: dict[str, Any] | None = None
    now = datetime.now(timezone.utc)
    for notice in airport.get("official_notices") or []:
        published_text = str(notice.get("published_at") or "").strip()
        try:
            published_at = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - published_at.astimezone(timezone.utc) > timedelta(days=7):
            continue
        text = f"{notice.get('title') or ''} {notice.get('summary') or ''}".casefold()
        if re.search(r"air(?:port|space).{0,24}clos|clos(?:ure|ed).{0,24}air(?:port|space)|flight operations.{0,20}suspend|all flights.{0,20}(?:suspend|cancel)|aeroporto.{0,16}chius|spazio aereo.{0,16}chius|sospensione.{0,20}voli", text):
            closure_notice = notice
            break
        if re.search(r"airspace restriction|flight restriction|operations limited|partial closure|runway closed|restrizion.{0,20}(?:voli|spazio aereo)", text):
            restriction_notice = notice
    airport_lat = float(airport.get("latitude") or AIRPORT_FALLBACKS["LICC"]["latitude"])
    airport_lon = float(airport.get("longitude") or AIRPORT_FALLBACKS["LICC"]["longitude"])
    airport_bearing = _bearing(*ETNA_LOCATION, airport_lat, airport_lon)
    airport_distance = _distance_km(*ETNA_LOCATION, airport_lat, airport_lon)
    toward = False
    for movement in ash.get("ash_movements") or []:
        direction = str(movement).split(" at ", 1)[0]
        degrees = _direction_degrees(direction)
        if degrees is not None and abs((degrees - airport_bearing + 180) % 360 - 180) <= 35:
            toward = True
            break
    metar = airport.get("metar") or {}
    visibility = _number(metar.get("visibility_sm"))
    volcanic_ash_reported = bool(metar.get("recent_volcanic_ash")) or " VA" in f" {metar.get('raw') or ''} " or "VA" in str(metar.get("weather") or "").split()
    if closure_notice:
        level, label = "critical", "Airspace closed"
    elif restriction_notice:
        level, label = "high", "Airspace restrictions"
    elif code == "RED" or volcanic_ash_reported:
        level, label = "critical", "Severe aviation attention"
    elif code == "ORANGE" and toward:
        level, label = "high", "Ash corridor toward Catania"
    elif code in {"ORANGE", "YELLOW"} or (visibility is not None and visibility < 3):
        level, label = "watch", "Enhanced monitoring"
    else:
        level, label = "normal", "No immediate ash impact indicated"
    reasons = [f"VAAC colour code {code}"]
    if ash.get("ash_direction"):
        reasons.append(f"ash {ash['ash_direction']}")
    if toward:
        reasons.append("reported drift aligns with the Etna–airport corridor")
    if visibility is not None:
        reasons.append(f"airport visibility {visibility:g} sm")
    if volcanic_ash_reported:
        reasons.append("volcanic ash reported in a recent Catania METAR")
    action = {
        "critical": "Expect material restrictions or disruption. Confirm the latest NOTAM, airport notice, airline status and air-traffic instructions before travel or operations.",
        "high": "Ash is reported moving toward the Catania corridor. Check the airport notice, airline status and current NOTAMs; conditions can change quickly.",
        "watch": "Monitor the next VAAC advisory, airport notices, METAR/TAF and airline status for changes.",
        "normal": "Continue normal monitoring of official airport, VAAC and aviation-weather sources.",
    }[level]
    return {
        "level": level,
        "label": label,
        "summary": " · ".join(reasons),
        "recommended_check": action,
        "airport_bearing_from_etna_deg": round(airport_bearing),
        "distance_from_etna_km": round(airport_distance, 1),
        "ash_toward_airport": toward,
        "airspace_status": "closed" if closure_notice else "restricted" if restriction_notice else "advisory" if level in {"critical", "high", "watch"} else "normal",
        "airspace_notice": closure_notice or restriction_notice,
        "guardrail": "Decision support only. Operational authority remains with NOTAMs, ATC, airport and airline instructions.",
    }


def _normalize_airport(icao: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    fallback = dict(AIRPORT_FALLBACKS.get(icao, {"icao": icao, "name": icao}))
    row = rows[0] if rows else {}
    latitude = row.get("lat") if row.get("lat") is not None else row.get("latitude")
    longitude = row.get("lon") if row.get("lon") is not None else row.get("longitude")
    return {
        **fallback,
        "icao": icao,
        "iata": row.get("iataId") or row.get("iata") or fallback.get("iata"),
        "name": row.get("name") or row.get("site") or fallback.get("name") or icao,
        "latitude": latitude if latitude is not None else fallback.get("latitude"),
        "longitude": longitude if longitude is not None else fallback.get("longitude"),
        "elevation_ft": row.get("elev") or row.get("elevation") or fallback.get("elevation_ft"),
    }


def _normalize_metar(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    row = rows[0]
    recent_ash = any("VA" in str(item.get("wxString") or "").split() or " VA" in f" {item.get('rawOb') or item.get('raw_text') or ''} " for item in rows)
    return {"raw": row.get("rawOb") or row.get("raw_text"), "observed_at": row.get("reportTime") or row.get("observation_time"), "flight_category": row.get("fltCat") or row.get("flight_category"), "wind_direction_deg": _number(row.get("wdir")), "wind_speed_kt": _number(row.get("wspd")), "wind_gust_kt": _number(row.get("wgst")), "visibility_sm": _number(row.get("visib")), "weather": row.get("wxString"), "recent_volcanic_ash": recent_ash, "temperature_c": _number(row.get("temp")), "dewpoint_c": _number(row.get("dewp")), "altimeter_hpa": _number(row.get("altim"))}


def _normalize_taf(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    row = rows[0]
    return {"raw": row.get("rawTAF") or row.get("raw_text"), "issued_at": row.get("issueTime") or row.get("issue_time"), "valid_from": row.get("validTimeFrom") or row.get("valid_time_from"), "valid_to": row.get("validTimeTo") or row.get("valid_time_to")}


def airport_status(etna: dict[str, Any] | None = None, refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    enabled = bool(runtime_option("tv_home_airport_enabled", settings.tv_home_airport_enabled))
    icao = str(runtime_option("tv_home_airport_icao", settings.tv_home_airport_icao) or "LICC").strip().upper()[:4]
    if not enabled:
        return {"enabled": False, "icao": icao}
    now = datetime.now(timezone.utc)
    with _lock:
        if not refresh and icao in _cache and now - _cache_at.get(icao, now - timedelta(hours=1)) < timedelta(minutes=10):
            cached = dict(_cache[icao])
            cached["assessment"] = _impact_assessment(cached, etna or {})
            return cached
        previous = _cache.get(icao, {})
        errors: dict[str, str] = {}
        try:
            airport = _normalize_airport(icao, _json_rows("airport", icao))
        except Exception as error:
            errors["airport"] = str(error)[:160]
            airport = {**AIRPORT_FALLBACKS.get(icao, {"icao": icao, "name": icao}), **{key: value for key, value in previous.items() if key in {"iata", "name", "latitude", "longitude", "elevation_ft"}}}
        try:
            airport["metar"] = _normalize_metar(_json_rows("metar", icao, hours=3))
        except Exception as error:
            errors["metar"] = str(error)[:160]
            airport["metar"] = previous.get("metar")
        try:
            airport["taf"] = _normalize_taf(_json_rows("taf", icao))
        except Exception as error:
            errors["taf"] = str(error)[:160]
            airport["taf"] = previous.get("taf")
        try:
            airport["official_notices"] = _airport_notices(_fetch(CATANIA_NEWS, "text/html"))
        except Exception as error:
            errors["official_notices"] = str(error)[:160]
            airport["official_notices"] = previous.get("official_notices", [])
        airport.update({"enabled": True, "generated_at": now.isoformat(), "errors": errors, "sources": {"airport": CATANIA_NEWS, "weather": "https://aviationweather.gov/data/api/"}})
        airport["assessment"] = _impact_assessment(airport, etna or {})
        _cache[icao], _cache_at[icao] = airport, now
        return dict(airport)
