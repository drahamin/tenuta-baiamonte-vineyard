"""Official-source Mount Etna monitoring with an offline cache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
import json
from pathlib import Path
import re
import threading
import urllib.parse
import urllib.request
from typing import Any

from .config import get_settings, runtime_option


INGV_COMMUNICATIONS = "https://www.ct.ingv.it/sezioniesterne/Comunicati/ComunicatiVulcanici.php?I=0"
INGV_WEBCAMS = "https://www.ct.ingv.it/sezioniesterne/webcam/WebcamEtna.php"
INGV_BULLETINS = "https://www.ct.ingv.it/index.php/monitoraggio-e-sorveglianza/prodotti-del-monitoraggio/bollettini-settimanali-multidisciplinari?filter%5Bsearch%5D=Etna&limit=100&limitstart=0"
# The national FDSN service includes rapidly published SURVEY-INGV-CT
# locations. The Etna-only catalogue can lag preliminary nearby events.
INGV_EVENTS = "https://webservices.ingv.it/fdsnws/event/1/query"
CIVIL_PROTECTION = "https://rischi.protezionecivile.gov.it/en/approfondimento/etna-0/"
VAAC_ETNA = "https://vaac.meteo.fr/volcanoes/etna/"
GVP_ETNA = "https://volcano.si.edu/volcano.cfm?vn=211060"
CACHE_PATH = Path("/data/etna-status.json")
_cache: dict[str, Any] | None = None
_lock = threading.Lock()


def _fetch(url: str, limit: int = 2_000_000) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Tenuta-Baiamonte-Etna-Monitor/1.0", "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read(limit).decode("utf-8", errors="replace")


def _strip(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _communications(html: str) -> list[dict[str, str]]:
    pattern = re.compile(r"<tr><td[^>]*>(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)</td><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td><td[^>]*>.*?href=['\"]([^'\"]+)", re.I | re.S)
    rows = []
    for sent_at, description, volcano, href in pattern.findall(html):
        if _strip(volcano).upper() != "ETNA":
            continue
        rows.append({"sent_at": sent_at.replace(" ", "T") + "Z", "description": _strip(description), "url": urllib.parse.urljoin(INGV_COMMUNICATIONS, href)})
    # Keep the complete page of Etna notices.  A busy event can generate more
    # than twenty updates before INGV publishes the explicit closing notice;
    # truncating the list used to discard the opening notice and incorrectly
    # change an active event back to ordinary monitoring.
    return rows


def _webcams(html: str) -> tuple[list[dict[str, str]], str | None]:
    updated = re.search(r"Ultimo aggiornamento:([^<]+)", html, re.I)
    cameras = []
    pattern = re.compile(r"href\s*=\s*['\"]Webcam\.php\?Vulcano=([^'\"]+)['\"].*?<img\s+src\s*=\s*['\"]([^'\"]+)['\"].*?<div\s+class\s*=\s*['\"]text['\"]>([^<]+)", re.I | re.S)
    allowed = {value.strip().casefold() for value in str(runtime_option("etna_webcam_codes", get_settings().etna_webcam_codes)).split(",") if value.strip()}
    for code, src, label in pattern.findall(html):
        if allowed and code.casefold() not in allowed:
            continue
        cameras.append({"code": code, "name": _strip(label), "available": "nowork" not in src.casefold(), "image_url": urllib.parse.urljoin(INGV_WEBCAMS, src), "source_url": urllib.parse.urljoin(INGV_WEBCAMS, f"Webcam.php?Vulcano={code}")})
    return cameras, _strip(updated.group(1)) if updated else None


def _latest_link(html: str, base: str, label_pattern: str) -> dict[str, str] | None:
    match = re.search(r"href=['\"]([^'\"]+)['\"][^>]*>\s*(?:<[^>]+>\s*)*([^<]*" + label_pattern + r"[^<]*)", html, re.I | re.S)
    return {"title": _strip(match.group(2)), "url": urllib.parse.urljoin(base, match.group(1))} if match else None


def _vaa_details(html: str, url: str) -> dict[str, Any]:
    """Extract the operational ash facts from a Toulouse VAAC advisory."""
    block = re.search(r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>", html, re.I | re.S)
    raw = unescape(re.sub(r"<[^>]+>", "", block.group(1) if block else html)).replace("\r", "")

    def field(name: str) -> str | None:
        match = re.search(
            rf"^{re.escape(name)}\s*:\s*(.*?)(?=^[A-Z][A-Z0-9 +/_()-]*\s*:|\Z)",
            raw,
            re.M | re.S,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip().rstrip("=") if match else None

    observed = field("OBS VA CLD") or ""
    remarks = field("RMK") or ""
    movements = []
    for direction, speed in re.findall(r"\bMOV\s+([A-Z]{1,3})\s+(\d+)\s*KT\b", observed, re.I):
        label = f"{direction.upper()} at {int(speed)} kt"
        if label not in movements:
            movements.append(label)
    height_m = re.search(r"TOP HEIGHT\s+(?:AROUND\s+)?(\d+)\s*M\b", remarks, re.I)
    flight_levels = [int(value) for value in re.findall(r"(?:FL|/)(\d{3})\b", observed, re.I)]
    if height_m:
        meters = int(height_m.group(1))
        plume_top = f"≈{meters:,} m / {round(meters * 3.28084 / 100) * 100:,} ft"
    elif flight_levels:
        maximum = max(flight_levels)
        plume_top = f"FL{maximum:03d} / {maximum * 100:,} ft"
    else:
        plume_top = None
    forecasts = {
        "6h": field("FCST VA CLD +6 HR"),
        "12h": field("FCST VA CLD +12 HR"),
        "18h": field("FCST VA CLD +18 HR"),
    }
    return {
        "url": url,
        "issued_at": field("DTG"),
        "advisory_number": field("ADVISORY NR"),
        "information_source": field("INFO SOURCE"),
        "aviation_colour_code": (field("AVIATION COLOUR CODE") or "UNKNOWN").upper(),
        "eruption_details": field("ERUPTION DETAILS"),
        "observation_time": field("OBS VA DTG"),
        "observed_ash_cloud": observed or None,
        "ash_movements": movements,
        "ash_direction": " · ".join(movements) if movements else "Not reported",
        "plume_top": plume_top,
        "forecast": forecasts,
        "no_ash_expected_12h": bool(forecasts["12h"] and "NO VA EXP" in forecasts["12h"].upper()),
        "remarks": remarks or None,
        "next_advisory": field("NXT ADVISORY"),
    }


def _annotate_ash_advisory(ash: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    result = dict(ash or {})
    issued = str(result.get("issued_at") or "")
    match = re.search(r"(\d{8})/(\d{4})Z", issued)
    issued_at = None
    if match:
        try:
            issued_at = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    final = bool(result.get("no_ash_expected_12h")) and "NO FURTHER" in str(result.get("next_advisory") or "").upper()
    current = bool(issued_at and not final and timedelta(0) <= now - issued_at <= timedelta(hours=24))
    result.update({
        "issued_at_iso": issued_at.isoformat() if issued_at else None,
        "is_final": final,
        "current": current,
        "status": "concluded" if final else "current" if current else "stale",
    })
    return result


def _seismic_events(now: datetime) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "starttime": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "minlatitude": 37.3, "maxlatitude": 38.2,
        "minlongitude": 14.5, "maxlongitude": 15.7,
        "format": "geojson", "limit": 100, "orderby": "time",
    })
    payload = json.loads(_fetch(INGV_EVENTS + "?" + query))
    events = payload.get("features") or payload.get("events") or []
    result = []
    for item in events[:50]:
        props = item.get("properties", item) if isinstance(item, dict) else {}
        coords = (item.get("geometry") or {}).get("coordinates", []) if isinstance(item, dict) else []
        event_time = props.get("time") or props.get("origin_time")
        if isinstance(event_time, (int, float)):
            event_time = datetime.fromtimestamp(event_time / 1000, timezone.utc).isoformat()
        elif event_time:
            try:
                parsed_time = datetime.fromisoformat(str(event_time).replace("Z", "+00:00"))
                # FDSN event times are UTC.  INGV currently omits the offset
                # in its GeoJSON serialization, which made browsers interpret
                # the timestamp as local time and made calendar-day retention
                # unreliable.  Preserve the source instant explicitly.
                if parsed_time.tzinfo is None:
                    parsed_time = parsed_time.replace(tzinfo=timezone.utc)
                event_time = parsed_time.astimezone(timezone.utc).isoformat()
            except ValueError:
                event_time = str(event_time)
        result.append({"id": item.get("id") if isinstance(item, dict) else None, "time": event_time, "magnitude": props.get("mag") if props.get("mag") is not None else props.get("magnitude"), "place": props.get("place") or props.get("event_location_name") or "Etna area", "longitude": coords[0] if len(coords) > 0 else props.get("longitude"), "latitude": coords[1] if len(coords) > 1 else props.get("latitude"), "depth_km": coords[2] if len(coords) > 2 else props.get("depth")})
    return result


def _activity_state(rows: list[dict[str, str]], now: datetime) -> dict[str, Any]:
    starts = [row for row in rows if "PRIMO COMUNICATO" in row["description"].upper() or "NOTIFICA EVENTO" in row["description"].upper()]
    ends = [row for row in rows if any(term in row["description"].upper() for term in ("FINE FENOMENO", "FINE EVENTO", "CHIUSURA", "RIENTRO"))]
    start = max(starts, key=lambda row: row.get("sent_at") or "") if starts else None
    end = max(ends, key=lambda row: row.get("sent_at") or "") if ends else None
    active = bool(start and (not end or start["sent_at"] > end["sent_at"]))
    latest = max(rows, key=lambda row: row.get("sent_at") or "") if rows else None
    return {
        "code": "active_event" if active else "monitoring",
        "label": "Active volcanic event notice" if active else "Official monitoring",
        "active": active,
        "since": start.get("sent_at") if active else None,
        "source": latest,
        "opening_notice": start if active else None,
        "closing_notice": end if end else None,
    }


def refresh_etna() -> dict[str, Any]:
    global _cache
    with _lock:
        now = datetime.now(timezone.utc)
        errors: dict[str, str] = {}
        previous = _cache or _read_cache()
        result: dict[str, Any] = {"generated_at": now.isoformat(), "sources": {"communications": INGV_COMMUNICATIONS, "webcams": INGV_WEBCAMS, "seismic": INGV_EVENTS, "bulletins": INGV_BULLETINS, "civil_protection": CIVIL_PROTECTION, "vaac": VAAC_ETNA, "gvp": GVP_ETNA}}
        try:
            communications_html = _fetch(INGV_COMMUNICATIONS)
            result["communications"] = _communications(communications_html)
        except Exception as error:
            errors["communications"] = str(error)[:180]
            result["communications"] = previous.get("communications", [])
        try:
            webcam_html = _fetch(INGV_WEBCAMS)
            result["webcams"], result["webcam_updated_utc"] = _webcams(webcam_html)
        except Exception as error:
            errors["webcams"] = str(error)[:180]
            result["webcams"] = previous.get("webcams", [])
            result["webcam_updated_utc"] = previous.get("webcam_updated_utc")
        for key, url, pattern in (("bulletin", INGV_BULLETINS, r"Bollettino.*Etna"), ("vaac", VAAC_ETNA, r"ETNA\.\d+")):
            try:
                result[key] = _latest_link(_fetch(url), url, pattern)
            except Exception as error:
                errors[key] = str(error)[:180]
                result[key] = previous.get(key)
        try:
            vaac_link = result.get("vaac") or previous.get("vaac") or {}
            if not vaac_link.get("url"):
                raise ValueError("No current Etna VAAC advisory link")
            result["ash_advisory"] = _vaa_details(_fetch(vaac_link["url"]), vaac_link["url"])
        except Exception as error:
            errors["ash_advisory"] = str(error)[:180]
            result["ash_advisory"] = previous.get("ash_advisory")
        result["ash_advisory"] = _annotate_ash_advisory(result.get("ash_advisory"), now)
        try:
            civil_html = _strip(_fetch(CIVIL_PROTECTION))
            level = re.search(r"(?:current(?:ly)? the )?level of alert for Etna is\s+(green|yellow|orange|red)", civil_html, re.I)
            published_level = level.group(1).lower() if level else "unknown"
            result["civil_protection"] = {
                "level": published_level,
                "published_level": published_level,
                "url": CIVIL_PROTECTION,
                "source_note": "Reference page; verify the latest Civil Protection notices before acting.",
            }
        except Exception as error:
            errors["civil_protection"] = str(error)[:180]
            result["civil_protection"] = previous.get("civil_protection", {"level": "unknown", "url": CIVIL_PROTECTION})
        try:
            result["seismic_events"] = _seismic_events(now)
        except Exception as error:
            errors["seismic"] = str(error)[:180]
            result["seismic_events"] = previous.get("seismic_events", [])
        result["activity"] = _activity_state(result["communications"], now)
        result["fresh"] = not errors
        result["errors"] = errors
        result["stale_sources"] = sorted(errors)
        result["last_complete_at"] = (
            now.isoformat()
            if not errors
            else previous.get("last_complete_at") or (previous.get("generated_at") if previous.get("fresh") else None)
        )
        result["safety_note"] = "Decision support only. Follow INGV, Civil Protection and local authority instructions; Etna can change suddenly."
        _cache = result
        try:
            CACHE_PATH.write_text(json.dumps(result), encoding="utf-8")
        except OSError:
            pass
        return result


def _read_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def etna_status(refresh: bool = False) -> dict[str, Any]:
    global _cache
    if refresh:
        return refresh_etna()
    if _cache is None:
        _cache = _read_cache() or {"generated_at": None, "activity": {"code": "checking", "label": "Checking official sources", "active": False}, "communications": [], "webcams": [], "seismic_events": [], "errors": {}, "fresh": False, "safety_note": "Decision support only. Follow INGV, Civil Protection and local authority instructions."}
    return _cache
