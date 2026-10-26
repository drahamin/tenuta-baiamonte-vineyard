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
INGV_VONA = "https://www.ct.ingv.it/sezioniesterne/Comunicati/ComunicatiVonaN.php"
INGV_WEBCAMS = "https://www.ct.ingv.it/sezioniesterne/webcam/WebcamEtna.php"
INGV_BULLETINS = "https://www.ct.ingv.it/index.php/monitoraggio-e-sorveglianza/prodotti-del-monitoraggio/bollettini-settimanali-multidisciplinari?filter%5Bsearch%5D=Etna&limit=100&limitstart=0"
INGV_SATELLITE = "https://www.ct.ingv.it/technolab/SezioniEsterne/pippo.php"
# The national FDSN service includes rapidly published SURVEY-INGV-CT
# locations. The Etna-only catalogue can lag preliminary nearby events.
INGV_EVENTS = "https://webservices.ingv.it/fdsnws/event/1/query"
CIVIL_PROTECTION = "https://rischi.protezionecivile.gov.it/en/approfondimento/etna-0/"
REGIONAL_CIVIL_PROTECTION = "https://www.protezionecivilesicilia.it/it/news/?pageid=74"
VAAC_ETNA = "https://vaac.meteo.fr/volcanoes/etna/"
GVP_ETNA = "https://volcano.si.edu/volcano.cfm?vn=211060"
CACHE_PATH = Path("/data/etna-status.json")
_cache: dict[str, Any] | None = None
_cache_mtime_ns = 0
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


def _vona_notices(html: str) -> list[dict[str, str]]:
    """Extract Etna's authoritative aviation colour-code history."""
    pattern = re.compile(
        r"<tr><td[^>]*>\s*(.*?)\s*</td><td[^>]*>\s*(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)\s*</td>"
        r"<td[^>]*>\s*(.*?)\s*</td><td[^>]*>.*?href=['\"]([^'\"]+)",
        re.I | re.S,
    )
    rows: list[dict[str, str]] = []
    for volcano, issued_at, description, href in pattern.findall(html):
        if _strip(volcano).upper() != "ETNA":
            continue
        detail = _strip(description)
        colour = re.search(r"(?:COLOR|COLOUR)\s+CODE\s*:\s*(GREEN|YELLOW|ORANGE|RED)", detail, re.I)
        rows.append({
            "issued_at": issued_at.replace(" ", "T") + "Z",
            "description": detail,
            "aviation_colour_code": colour.group(1).upper() if colour else "UNKNOWN",
            "url": urllib.parse.urljoin(INGV_VONA, href),
        })
    return sorted(rows, key=lambda row: row.get("issued_at") or "", reverse=True)


def _regional_etna_notices(html: str) -> list[dict[str, str]]:
    """Extract Sicily Civil Protection's Etna operational-phase notices."""
    pattern = re.compile(r"<a[^>]+href=['\"]([^'\"]+)['\"][^>]+title=['\"]([^'\"]*ETNA[^'\"]*)['\"]", re.I | re.S)
    rows: list[dict[str, str]] = []
    for href, title in pattern.findall(html):
        decoded = urllib.parse.unquote(href)
        combined = f"{title} {decoded}".upper()
        date_match = re.search(r"(\d{2})[./ -](\d{2})[./ -](20\d{2})", combined)
        date = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}" if date_match else ""
        notice_number = re.search(r"(?:\bN\.?\s*|[-–]\s*)(\d{1,2})\s+(?:DEL|ETNAS)", combined)
        phase = next((value for value in ("PREALLARME", "PREALLARNE", "ALLARME", "ATTENZIONE", "BASE") if value in combined), "UNKNOWN")
        if phase == "PREALLARNE":
            phase = "PREALLARME"
        etnas = next((value for value in ("F2", "F1", "F0") if re.search(rf"\b{value}\b", combined)), "UNKNOWN")
        rows.append({
            "published_at": date,
            "title": _strip(title),
            "phase": phase.lower(),
            "etnas_level": etnas,
            "notice_number": notice_number.group(1) if notice_number else "",
            "url": urllib.parse.urljoin(REGIONAL_CIVIL_PROTECTION, href),
        })
    rows.sort(key=lambda row: (row.get("published_at") or "", int(row.get("notice_number") or 0)), reverse=True)
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


def _activity_state(
    rows: list[dict[str, str]],
    now: datetime,
    vona: dict[str, Any] | None = None,
) -> dict[str, Any]:
    starts = [row for row in rows if "PRIMO COMUNICATO" in row["description"].upper() or "NOTIFICA EVENTO" in row["description"].upper()]
    ends = [row for row in rows if any(term in row["description"].upper() for term in ("FINE FENOMENO", "FINE EVENTO", "CHIUSURA", "RIENTRO"))]
    start = max(starts, key=lambda row: row.get("sent_at") or "") if starts else None
    end = max(ends, key=lambda row: row.get("sent_at") or "") if ends else None
    chain_active = bool(start and (not end or start["sent_at"] > end["sent_at"]))
    latest = max(rows, key=lambda row: row.get("sent_at") or "") if rows else None
    colour = str((vona or {}).get("aviation_colour_code") or "UNKNOWN").upper()
    vona_time = str((vona or {}).get("issued_at") or "")
    start_time = str((start or {}).get("sent_at") or "")
    vona_controls = bool(vona_time and (not start_time or vona_time >= start_time))
    if vona_controls and colour == "GREEN":
        active, alerting = False, False
        code, label = "monitoring", "Official monitoring · aviation GREEN"
    elif vona_controls and colour in {"YELLOW", "ORANGE", "RED"}:
        active, alerting = True, True
        code, label = "aviation_elevated", f"Etna aviation code {colour}"
    else:
        active = chain_active
        try:
            latest_at = datetime.fromisoformat(str((latest or {}).get("sent_at") or "").replace("Z", "+00:00"))
            notice_age_hours = max(0.0, (now - latest_at).total_seconds() / 3600)
        except ValueError:
            notice_age_hours = None
        alerting = bool(active and notice_age_hours is not None and notice_age_hours <= 48)
        code = "active_event" if alerting else "unclosed_notice" if active else "monitoring"
        label = "Active volcanic event notice" if alerting else "Unclosed older activity notice" if active else "Official monitoring"
    return {
        "code": code,
        "label": label,
        "active": active,
        "alerting": alerting,
        "since": (start or {}).get("sent_at") if active else None,
        "source": vona if vona_controls else latest,
        "communications_source": latest,
        "aviation_colour_code": colour,
        "vona_controls": vona_controls,
        "opening_notice": start if active else None,
        "closing_notice": end if end else None,
    }


def _operational_status(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize current official signals without promoting historical advisories."""
    activity = result.get("activity") or {}
    ash = result.get("ash_advisory") or {}
    civil = result.get("civil_protection") or {}
    regional = result.get("regional_civil_protection") or {}
    vona_code = str(activity.get("aviation_colour_code") or "UNKNOWN").upper()
    vaac_code = str(ash.get("aviation_colour_code") or "UNKNOWN").upper() if ash.get("current") else "INACTIVE"
    civil_level = str(civil.get("level") or "unknown").lower()
    regional_phase = str(regional.get("phase") or "unknown").lower()
    if "allarme" == regional_phase or "red" == civil_level or "RED" in {vona_code, vaac_code}:
        level = "critical"
    elif "orange" == civil_level or "ORANGE" in {vona_code, vaac_code}:
        level = "high"
    elif "yellow" == civil_level or "YELLOW" == vona_code:
        level = "watch"
    else:
        level = "monitoring"
    return {
        "level": level,
        "label": {
            "critical": "Immediate official attention",
            "high": "Elevated official monitoring",
            "watch": "Watch official updates",
            "monitoring": "Routine official monitoring",
        }[level],
        "vona_code": vona_code,
        "vaac_code": vaac_code,
        "civil_protection_level": civil_level,
        "regional_phase": regional_phase,
        "actionable": level != "monitoring",
        "summary": f"INGV VONA {vona_code} · VAAC {vaac_code} · Civil Protection {civil_level} · Sicily phase {regional_phase}",
    }


def refresh_etna() -> dict[str, Any]:
    global _cache, _cache_mtime_ns
    with _lock:
        now = datetime.now(timezone.utc)
        errors: dict[str, str] = {}
        previous = _cache or _read_cache()
        result: dict[str, Any] = {"generated_at": now.isoformat(), "sources": {"communications": INGV_COMMUNICATIONS, "vona": INGV_VONA, "webcams": INGV_WEBCAMS, "seismic": INGV_EVENTS, "bulletins": INGV_BULLETINS, "satellite": INGV_SATELLITE, "civil_protection": CIVIL_PROTECTION, "regional_civil_protection": REGIONAL_CIVIL_PROTECTION, "vaac": VAAC_ETNA, "gvp": GVP_ETNA}}
        try:
            communications_html = _fetch(INGV_COMMUNICATIONS)
            result["communications"] = _communications(communications_html)
        except Exception as error:
            errors["communications"] = str(error)[:180]
            result["communications"] = previous.get("communications", [])
        try:
            result["vona_notices"] = _vona_notices(_fetch(INGV_VONA))
            result["current_vona"] = result["vona_notices"][0] if result["vona_notices"] else None
            if not result["current_vona"]:
                raise ValueError("INGV returned no Etna VONA notices")
        except Exception as error:
            errors["vona"] = str(error)[:180]
            result["vona_notices"] = previous.get("vona_notices", [])
            result["current_vona"] = previous.get("current_vona")
        try:
            webcam_html = _fetch(INGV_WEBCAMS)
            webcams, webcam_updated_utc = _webcams(webcam_html)
            if not webcams:
                raise ValueError("INGV returned no configured Etna webcams")
            result["webcams"] = webcams
            result["webcam_updated_utc"] = webcam_updated_utc
            # INGV image paths and its page-level timestamp can remain stable
            # across more than one source poll.  Record every successful check
            # so kiosk browsers receive a bounded cache-busting token instead
            # of holding yesterday's image indefinitely.
            result["webcam_checked_at"] = now.isoformat()
        except Exception as error:
            errors["webcams"] = str(error)[:180]
            result["webcams"] = previous.get("webcams", [])
            result["webcam_updated_utc"] = previous.get("webcam_updated_utc")
            result["webcam_checked_at"] = previous.get("webcam_checked_at")
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
            regional_notices = _regional_etna_notices(_fetch(REGIONAL_CIVIL_PROTECTION))
            if not regional_notices:
                raise ValueError("Sicily Civil Protection returned no Etna notices")
            result["regional_civil_protection_notices"] = regional_notices[:10]
            result["regional_civil_protection"] = regional_notices[0]
        except Exception as error:
            errors["regional_civil_protection"] = str(error)[:180]
            result["regional_civil_protection_notices"] = previous.get("regional_civil_protection_notices", [])
            result["regional_civil_protection"] = previous.get("regional_civil_protection", {"phase": "unknown", "url": REGIONAL_CIVIL_PROTECTION})
        try:
            result["seismic_events"] = _seismic_events(now)
        except Exception as error:
            errors["seismic"] = str(error)[:180]
            result["seismic_events"] = previous.get("seismic_events", [])
        result["activity"] = _activity_state(result["communications"], now, result.get("current_vona"))
        result["operational_status"] = _operational_status(result)
        result["fresh"] = not errors
        result["errors"] = errors
        result["stale_sources"] = sorted(errors)
        result["last_complete_at"] = (
            now.isoformat()
            if not errors
            else previous.get("last_complete_at") or (previous.get("generated_at") if previous.get("fresh") else None)
        )
        cadence = max(2, int(runtime_option("etna_refresh_minutes", get_settings().etna_refresh_minutes)))
        ttl = timedelta(minutes=max(30, cadence * 3))
        previous_status = previous.get("source_status") if isinstance(previous.get("source_status"), dict) else {}
        status_keys = ("communications", "vona", "webcams", "bulletin", "vaac", "ash_advisory", "civil_protection", "regional_civil_protection", "seismic")
        source_status: dict[str, dict[str, Any]] = {}
        for key in status_keys:
            prior = previous_status.get(key) if isinstance(previous_status.get(key), dict) else {}
            failed = key in errors
            last_success = prior.get("last_success_at") if failed else now.isoformat()
            if failed and not last_success and previous.get("generated_at"):
                last_success = previous.get("generated_at")
            expires_at = prior.get("expires_at") if failed else (now + ttl).isoformat()
            source_status[key] = {
                "state": "stale" if failed and last_success else "unavailable" if failed else "current",
                "last_attempt_at": now.isoformat(),
                "last_success_at": last_success,
                "expires_at": expires_at,
                "error": "fetch_failed" if failed else None,
            }
        result["source_status"] = source_status
        expiries = [str(item["expires_at"]) for item in source_status.values() if item.get("expires_at")]
        result["expires_at"] = min(expiries) if expiries else None
        result["safety_note"] = "Decision support only. Follow INGV, Civil Protection and local authority instructions; Etna can change suddenly."
        _cache = result
        try:
            CACHE_PATH.write_text(json.dumps(result), encoding="utf-8")
            _cache_mtime_ns = CACHE_PATH.stat().st_mtime_ns
        except OSError:
            pass
        return result


def _read_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def etna_status(refresh: bool = False) -> dict[str, Any]:
    global _cache, _cache_mtime_ns
    if refresh:
        return refresh_etna()
    # The API scheduler and LAN TV server are separate processes sharing
    # /data.  Reload a newer durable snapshot so the display does not retain
    # the first in-memory Etna image it saw until the add-on restarts.
    try:
        disk_mtime_ns = CACHE_PATH.stat().st_mtime_ns
    except OSError:
        disk_mtime_ns = 0
    if _cache is None or disk_mtime_ns > _cache_mtime_ns:
        disk_cache = _read_cache()
        if disk_cache:
            _cache = disk_cache
            _cache_mtime_ns = disk_mtime_ns
    if _cache is None:
        _cache = {"generated_at": None, "activity": {"code": "checking", "label": "Checking official sources", "active": False}, "communications": [], "webcams": [], "seismic_events": [], "errors": {}, "fresh": False, "safety_note": "Decision support only. Follow INGV, Civil Protection and local authority instructions."}
    return _cache


def etna_display_status() -> dict[str, Any]:
    """Return Etna data with a current webcam pointer for the LAN display.

    Full Etna refreshes intentionally include several slower official sources.
    The TV only needs one lightweight INGV gallery request to keep its image
    current, so do that independently when the last successful webcam check is
    older than the configured cadence.
    """
    global _cache
    payload = etna_status()
    marker = payload.get("webcam_checked_at") or payload.get("generated_at")
    try:
        checked_at = datetime.fromisoformat(str(marker).replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        checked_at = datetime.min.replace(tzinfo=timezone.utc)
    cadence = max(2, int(runtime_option("etna_refresh_minutes", get_settings().etna_refresh_minutes)))
    if datetime.now(timezone.utc) - checked_at < timedelta(minutes=cadence):
        return payload
    with _lock:
        now = datetime.now(timezone.utc)
        try:
            webcams, updated = _webcams(_fetch(INGV_WEBCAMS))
            if not webcams:
                raise ValueError("INGV returned no configured Etna webcams")
            refreshed = dict(_cache or payload)
            refreshed["webcams"] = webcams
            refreshed["webcam_updated_utc"] = updated
            refreshed["webcam_checked_at"] = now.isoformat()
            _cache = refreshed
        except Exception:
            return _cache or payload
    return _cache or payload
