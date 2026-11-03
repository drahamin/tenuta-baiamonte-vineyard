from __future__ import annotations

import ipaddress
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from ..config import addon_version, get_settings, runtime_option
from ..db import fetch_one, transaction
from ..display_data import display_payload, weather_context_payload
from ..etna import etna_status
from ..service import estate_id
from .mobile_energy_live import read_live_energy


router = APIRouter(prefix="/api/v1/mobile", tags=["mobile-site"])
_INGRESS_PATH = "/api/baiamonte_mobile/v1"
_EXCHANGE_PATH = "/api/v1/mobile/session/exchange"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
_EXCHANGE_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
_EXCHANGE_NONCE_PATTERN = re.compile(r"[A-Za-z0-9_-]{24,64}")
_ROLE_CAPABILITIES = {
    "admin": {"session", "status", "catalog", "records", "weather", "work", "review", "energy", "etna"},
    "enologist": {"session", "status", "catalog", "records", "weather", "work", "review", "etna"},
    "worker": {"session", "status", "catalog", "weather", "work"},
    "viewer": {"session", "status", "catalog", "weather", "etna"},
}
_ROLE_RECORDS = {
    "admin": {"tasks", "alerts", "issues", "labs", "cellar", "grapes"},
    "enologist": {"tasks", "issues", "labs", "cellar"},
    "worker": {"tasks"},
    "viewer": set(),
}
_RECORD_FIELDS = {
    "tasks": ("id", "title", "category", "status", "priority", "due_date", "block_code", "updated_at"),
    "alerts": ("id", "alert_type", "severity", "title", "message", "status", "triggered_at", "resolved_at"),
    "issues": ("id", "issue_text", "issue_type", "priority", "status", "due_date", "subject_ref", "decision_action"),
    "labs": ("id", "sample_name", "sample_type", "flagged_results", "review_status", "lab_date"),
    "cellar": ("id", "code", "name", "stage", "capacity_l", "volume_l", "fill_pct", "status", "temperature_c", "density_sg", "brix", "ph", "observed_at"),
    "grapes": ("id", "name", "variety_name", "planned_kg", "harvested_kg", "completion_pct", "first_pick_date", "last_pick_date"),
}
_CATALOG_VARIETY_FIELDS = ("id", "name", "variety_name")
_CATALOG_CONTAINER_FIELDS = ("id", "code", "name", "stage", "capacity_l", "status")
_WEATHER_CURRENT_FIELDS = (
    "observed_at", "condition", "temp_c", "feels_like_c", "humidity_pct", "dew_point_c",
    "vpd_kpa", "pressure_hpa", "wind_kph", "wind_gust_kph", "gust_max_today_kph",
    "wind_direction_deg", "wind_direction_10m_deg", "rain_mm", "rain_rate_mm_h",
    "solar_wm2", "uv_index", "leaf_wetness_pct", "soil_moisture_pct", "soil_temp_c",
    "sensor_battery_v", "sensor_capacitor_v", "raining_now",
)
_WEATHER_FORECAST_FIELDS = (
    "datetime", "condition", "temperature", "templow", "precipitation",
    "precipitation_probability", "wind_speed", "wind_bearing", "humidity", "pressure", "uv_index",
)
_WEATHER_ADVISORY_FIELDS = ("code", "severity", "title", "detail", "action", "timing")
_WEATHER_CACHE_FIELDS = ("status", "refreshed_at", "age_seconds", "refresh_pending")


def _normalized_rows(rows: Any, aliases: dict[str, str]) -> Any:
    """Map display-only source names onto the stable mobile API contract."""
    if not isinstance(rows, list):
        return rows
    normalized = []
    for item in rows:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        mapped = dict(item)
        for source, target in aliases.items():
            if target not in mapped and source in mapped:
                mapped[target] = mapped[source]
        normalized.append(mapped)
    return normalized


def _weather_mobile_dto(payload: Any) -> dict[str, Any]:
    """Return weather measurements and advisories without internal HA identifiers."""
    if not isinstance(payload, dict):
        return {"available": False, "current": {}, "forecast": [], "advisories": [], "source": None, "cache": {}}
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    cache = payload.get("cache") if isinstance(payload.get("cache"), dict) else {}
    return {
        "available": payload.get("available") is True,
        "current": {key: current.get(key) for key in _WEATHER_CURRENT_FIELDS if key in current},
        "forecast": _bounded(payload.get("forecast"), 7, _WEATHER_FORECAST_FIELDS),
        "advisories": _bounded(payload.get("advisories"), 20, _WEATHER_ADVISORY_FIELDS),
        "source": payload.get("source") if payload.get("source") in {"home_assistant", "database_last_known", "unavailable"} else None,
        "cache": {key: cache.get(key) for key in _WEATHER_CACHE_FIELDS if key in cache},
    }


def _enabled() -> None:
    if runtime_option("mobile_site_gateway_enabled", get_settings().mobile_site_gateway_enabled) is not True:
        raise HTTPException(503, "Direct-site mobile gateway is not enabled")


def _trusted_gateway_source(request: Request) -> bool:
    if request.headers.get("X-Ingress-Path") != _INGRESS_PATH:
        return False
    try:
        address = ipaddress.ip_address(str(request.client.host if request.client else ""))
    except ValueError:
        return False
    return address.is_loopback or address in ipaddress.ip_network("172.30.32.0/23")


def _unix_time() -> int:
    return int(time.time())


def _verify_exchange_proof(request: Request, user_id: str) -> None:
    if not _trusted_gateway_source(request):
        raise HTTPException(401, "Trusted Home Assistant gateway required")
    secret = str(runtime_option("mobile_site_exchange_hmac_key", get_settings().mobile_site_exchange_hmac_key)).strip()
    try:
        key = base64.urlsafe_b64decode(secret + "=")
    except (ValueError, TypeError):
        key = b""
    if _EXCHANGE_KEY_PATTERN.fullmatch(secret) is None or len(key) != 32:
        raise HTTPException(503, "Mobile exchange proof is not configured")
    timestamp_text = request.headers.get("X-Baiamonte-Mobile-Timestamp", "")
    nonce = request.headers.get("X-Baiamonte-Mobile-Nonce", "")
    signature = request.headers.get("X-Baiamonte-Mobile-Signature", "")
    try:
        issued_at = int(timestamp_text)
    except ValueError as error:
        raise HTTPException(401, "Mobile exchange proof is invalid") from error
    now = _unix_time()
    if abs(now - issued_at) > 60 or _EXCHANGE_NONCE_PATTERN.fullmatch(nonce) is None or not re.fullmatch(r"[0-9a-f]{64}", signature):
        raise HTTPException(401, "Mobile exchange proof is invalid")
    canonical = f"POST\n{_EXCHANGE_PATH}\n{issued_at}\n{nonce}\n{user_id}\n"
    expected = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if request.method != "POST" or request.url.path != _EXCHANGE_PATH or not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Mobile exchange proof is invalid")
    nonce_hash = hashlib.sha256(nonce.encode("ascii")).hexdigest()
    cutoff_at = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    expires_at = datetime.fromtimestamp(issued_at + 60, timezone.utc).replace(tzinfo=None)
    with transaction() as (_, cursor):
        cursor.execute("DELETE FROM mobile_site_exchange_nonces WHERE expires_at<%s", (cutoff_at,))
        claimed = cursor.execute(
            "INSERT IGNORE INTO mobile_site_exchange_nonces (nonce_hash,issued_at,expires_at) VALUES (%s,%s,%s)",
            (nonce_hash, issued_at, expires_at),
        )
        # The unique-key claim may have waited behind another transaction.
        # Recheck with the claim still uncommitted so expiry rolls it back.
        if abs(_unix_time() - issued_at) > 60:
            raise HTTPException(401, "Mobile exchange proof expired while waiting")
    if claimed != 1:
        raise HTTPException(409, "Mobile exchange proof was already used")


def _identity_policy() -> dict[str, Any]:
    raw = runtime_option("mobile_site_identity_policy", get_settings().mobile_site_identity_policy)
    try:
        policy = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(503, "Mobile identity policy is invalid") from error
    if not isinstance(policy, dict):
        raise HTTPException(503, "Mobile identity policy is invalid")
    return policy


def _policy_identity(user_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", user_id):
        raise HTTPException(403, "Mobile identity is not approved")
    entry = _identity_policy().get(user_id)
    if not isinstance(entry, dict) or entry.get("enabled") is not True:
        raise HTTPException(403, "Mobile identity is not approved")
    username = str(entry.get("username") or "").strip().casefold()
    role = str(entry.get("role") or "").strip().casefold()
    requested = entry.get("capabilities")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,63}", username) or role not in _ROLE_CAPABILITIES or not isinstance(requested, list):
        raise HTTPException(403, "Mobile identity policy entry is invalid")
    capabilities = {str(value) for value in requested}
    if not capabilities.issubset(_ROLE_CAPABILITIES[role]):
        raise HTTPException(403, "Mobile identity capability exceeds its role")
    identity_version = entry.get("version")
    if not isinstance(identity_version, int) or isinstance(identity_version, bool) or identity_version < 1:
        raise HTTPException(403, "Mobile identity policy entry is invalid")
    return {"ha_user_id": user_id, "username": username, "role": role,
            "capabilities": capabilities, "identity_version": identity_version}


def _mobile_identity(request: Request) -> dict[str, Any]:
    """Resolve immutable HA identity only for the one-time token exchange."""
    _enabled()
    user_id = str(request.headers.get("X-Remote-User-Id") or "").strip()
    _verify_exchange_proof(request, user_id)
    identity = _policy_identity(user_id)
    request.state.mobile_identity = identity
    return identity


def _session_audience() -> str:
    return str(runtime_option("mobile_site_session_audience", get_settings().mobile_site_session_audience)).strip()


def _session_ttl_seconds() -> int:
    return min(3600, max(300, int(runtime_option("mobile_site_session_ttl_seconds", get_settings().mobile_site_session_ttl_seconds))))


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Mobile app session required")
    token = authorization[7:]
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise HTTPException(401, "Mobile app session required")
    return token


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _app_session(request: Request) -> dict[str, Any]:
    """Validate a narrow app token and re-evaluate current server-owned policy."""
    _enabled()
    token_hash = hashlib.sha256(_bearer_token(request).encode("ascii")).hexdigest()
    row = fetch_one(
        "SELECT ha_user_id,identity_version,audience,capabilities_json,expires_at,revoked_at "
        "FROM mobile_site_sessions WHERE token_hash=%s",
        (token_hash,),
    )
    now = datetime.now(timezone.utc)
    expires_at = _as_utc((row or {}).get("expires_at"))
    if not row or row.get("revoked_at") is not None or expires_at is None or expires_at <= now:
        raise HTTPException(401, "Mobile app session expired or revoked")
    audience = _session_audience()
    if not audience or row.get("audience") != audience:
        raise HTTPException(401, "Mobile app session audience is invalid")
    identity = _policy_identity(str(row.get("ha_user_id") or ""))
    if row.get("identity_version") != identity["identity_version"]:
        raise HTTPException(401, "Mobile app session identity policy changed")
    try:
        stored_capabilities = json.loads(str(row.get("capabilities_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(401, "Mobile app session is invalid") from error
    if not isinstance(stored_capabilities, list):
        raise HTTPException(401, "Mobile app session is invalid")
    session_capabilities = {str(value) for value in stored_capabilities}
    if not session_capabilities or not session_capabilities.issubset(identity["capabilities"]):
        raise HTTPException(401, "Mobile app session permissions changed")
    identity.update({"capabilities": session_capabilities, "token_hash": token_hash,
                     "audience": audience, "expires_at": expires_at})
    request.state.mobile_identity = identity
    return identity


def _revocable_session(request: Request) -> dict[str, str]:
    """Resolve a known audience-bound token without requiring read authority."""
    token_hash = hashlib.sha256(_bearer_token(request).encode("ascii")).hexdigest()
    row = fetch_one("SELECT audience FROM mobile_site_sessions WHERE token_hash=%s", (token_hash,))
    audience = _session_audience()
    if not row or not audience or row.get("audience") != audience:
        raise HTTPException(401, "Mobile app session is not recognized")
    return {"token_hash": token_hash}


def _requires(capability: str) -> Callable[..., dict[str, Any]]:
    def require(identity: dict[str, Any] = Depends(_app_session)) -> dict[str, Any]:
        if capability not in identity["capabilities"]:
            raise HTTPException(403, "Mobile capability is not approved")
        return identity
    return require


require_session = _requires("session")
require_status = _requires("status")
require_catalog = _requires("catalog")
require_records = _requires("records")
require_weather = _requires("weather")
require_work = _requires("work")
require_review = _requires("review")
require_energy = _requires("energy")
require_etna = _requires("etna")


def _freshness(source_time: Any = None, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    parsed: datetime | None = None
    if source_time:
        try:
            parsed = datetime.fromisoformat(str(source_time).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            parsed = None
    age = max(0, int((current - parsed.astimezone(timezone.utc)).total_seconds())) if parsed else None
    return {"generated_at": current.isoformat(), "source_generated_at": parsed.isoformat() if parsed else None,
            "data_age_seconds": age, "stale": age is None or age > 7200}


def _bounded(items: Any, limit: int, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [{key: item.get(key) for key in fields if key in item} for item in items[:limit] if isinstance(item, dict)]


def _latest_item_source_time(items: Any, fields: tuple[str, ...]) -> datetime | None:
    """Return the newest actual domain timestamp, never payload construction time."""
    if not isinstance(items, list):
        return None
    parsed = [
        value
        for item in items if isinstance(item, dict)
        for field in fields
        if (value := _as_utc(item.get(field))) is not None
    ]
    return max(parsed) if parsed else None


def _weather_source_time(payload: dict[str, Any]) -> Any:
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    cache = payload.get("cache") if isinstance(payload.get("cache"), dict) else {}
    return current.get("observed_at") or cache.get("refreshed_at")


def _etna_source_health(payload: dict[str, Any]) -> tuple[Any, bool]:
    """Use the last complete source refresh, never the latest attempt time."""
    source_time = payload.get("last_complete_at")
    statuses = payload.get("source_status") if isinstance(payload.get("source_status"), dict) else {}
    errors = payload.get("errors") if isinstance(payload.get("errors"), dict) else {}
    states_current = bool(statuses) and all(
        isinstance(value, dict) and value.get("state") == "current" for value in statuses.values()
    )
    expires_at = _as_utc(payload.get("expires_at"))
    unexpired = expires_at is not None and expires_at > datetime.now(timezone.utc)
    return source_time, bool(source_time) and not errors and states_current and unexpired


@router.post("/session/exchange")
def mobile_session_exchange(identity: dict[str, Any] = Depends(_mobile_identity)) -> dict[str, Any]:
    audience = _session_audience()
    if not audience:
        raise HTTPException(503, "Mobile session audience is not configured")
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=_session_ttl_seconds())
    capabilities = sorted(identity["capabilities"])
    with transaction() as (_, cursor):
        # Keep the bearer-session table bounded. The indexed FOR UPDATE range
        # serializes concurrent exchanges for this immutable HA identity; a
        # successful exchange replaces any prior session for that user.
        cursor.execute(
            "DELETE FROM mobile_site_sessions WHERE expires_at<=%s OR revoked_at IS NOT NULL",
            (created_at.replace(tzinfo=None),),
        )
        cursor.execute(
            "SELECT token_hash FROM mobile_site_sessions WHERE ha_user_id=%s FOR UPDATE",
            (identity["ha_user_id"],),
        )
        cursor.execute(
            "DELETE FROM mobile_site_sessions WHERE ha_user_id=%s",
            (identity["ha_user_id"],),
        )
        cursor.execute(
            "INSERT INTO mobile_site_sessions "
            "(token_hash,ha_user_id,identity_version,audience,capabilities_json,created_at,expires_at,revoked_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)",
            (token_hash, identity["ha_user_id"], identity["identity_version"], audience,
             json.dumps(capabilities, separators=(",", ":")),
             created_at.replace(tzinfo=None), expires_at.replace(tzinfo=None)),
        )
    return {"contract": "baiamonte.direct-site.v1", "access_token": token, "token_type": "Bearer",
            "audience": audience, "expires_at": expires_at.isoformat(), "capabilities": capabilities,
            "user": {"username": identity["username"], "role": identity["role"]}}


@router.post("/session/revoke")
def mobile_session_revoke(session: dict[str, str] = Depends(_revocable_session)) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE mobile_site_sessions SET revoked_at=COALESCE(revoked_at,UTC_TIMESTAMP(6)) WHERE token_hash=%s",
            (session["token_hash"],),
        )
    return {"contract": "baiamonte.direct-site.v1", "revoked": True}


@router.get("/session")
def mobile_session(identity: dict[str, Any] = Depends(require_session)) -> dict[str, Any]:
    return {"contract": "baiamonte.direct-site.v1", "user": {"username": identity["username"],
            "role": identity["role"], "capabilities": sorted(identity["capabilities"])},
            "audience": identity["audience"], "expires_at": identity["expires_at"].isoformat()}


@router.get("/status")
def mobile_status(_: dict[str, Any] = Depends(require_status)) -> dict[str, Any]:
    return {"contract": "baiamonte.direct-site.v1", "ok": True, "version": addon_version(), "freshness": _freshness(None)}


@router.get("/catalog")
def mobile_catalog(_: dict[str, Any] = Depends(require_catalog)) -> dict[str, Any]:
    payload = display_payload(); estate = payload.get("estate", {}) if isinstance(payload.get("estate"), dict) else {}
    grapes = payload.get("grapes", {}) if isinstance(payload.get("grapes"), dict) else {}; cellar = payload.get("cellar", {}) if isinstance(payload.get("cellar"), dict) else {}
    return {"contract": "baiamonte.direct-site.v1", "estate": {"name": estate.get("name"), "location": estate.get("location"), "year": payload.get("year")},
            "varieties": _bounded(_normalized_rows(grapes.get("varieties"), {"variety_id": "id"}), 50, _CATALOG_VARIETY_FIELDS),
            "containers": _bounded(cellar.get("tanks"), 100, _CATALOG_CONTAINER_FIELDS),
            "freshness": _freshness(None)}


@router.get("/records")
def mobile_records(object: str = Query(...), limit: int = Query(50, ge=1, le=100), identity: dict[str, Any] = Depends(require_records)) -> dict[str, Any]:
    if object not in _ROLE_RECORDS[identity["role"]]:
        raise HTTPException(403, "Record type is not approved for this role")
    payload = display_payload(); dashboard = payload.get("dashboard", {}) if isinstance(payload.get("dashboard"), dict) else {}
    sources = {"tasks": dashboard.get("tasks"), "alerts": dashboard.get("alerts"), "issues": dashboard.get("issues"),
        "labs": (payload.get("labs") or {}).get("queue") if isinstance(payload.get("labs"), dict) else [],
        "cellar": _normalized_rows((payload.get("cellar") or {}).get("tanks"), {
            "level_pct": "fill_pct", "temp_c": "temperature_c", "reading_at": "observed_at",
        }) if isinstance(payload.get("cellar"), dict) else [],
        "grapes": _normalized_rows((payload.get("grapes") or {}).get("varieties"), {
            "variety_id": "id",
        }) if isinstance(payload.get("grapes"), dict) else []}
    items = _bounded(sources[object], limit, _RECORD_FIELDS[object])
    source_fields = {
        "tasks": ("updated_at",), "alerts": ("triggered_at", "resolved_at"), "issues": (),
        "labs": ("lab_date",), "cellar": ("observed_at",),
        "grapes": ("last_pick_date", "first_pick_date"),
    }
    return {"contract": "baiamonte.direct-site.v1", "object": object, "items": items,
            "freshness": _freshness(_latest_item_source_time(items, source_fields[object]))}


@router.get("/weather")
def mobile_weather(_: dict[str, Any] = Depends(require_weather)) -> dict[str, Any]:
    weather = weather_context_payload(); source_time = _weather_source_time(weather) if isinstance(weather, dict) else None
    return {"contract": "baiamonte.direct-site.v1", "weather": _weather_mobile_dto(weather), "freshness": _freshness(source_time)}


@router.get("/work")
def mobile_work(limit: int = Query(50, ge=1, le=100), _: dict[str, Any] = Depends(require_work)) -> dict[str, Any]:
    payload = display_payload(); dashboard = payload.get("dashboard", {}) if isinstance(payload.get("dashboard"), dict) else {}
    tasks = _bounded(dashboard.get("tasks"), limit, _RECORD_FIELDS["tasks"])
    return {"contract": "baiamonte.direct-site.v1", "tasks": tasks,
            "freshness": _freshness(_latest_item_source_time(tasks, ("updated_at",)))}


@router.get("/review")
def mobile_review(limit: int = Query(50, ge=1, le=100), identity: dict[str, Any] = Depends(require_review)) -> dict[str, Any]:
    payload = display_payload(); dashboard = payload.get("dashboard", {}) if isinstance(payload.get("dashboard"), dict) else {}; labs = payload.get("labs", {}) if isinstance(payload.get("labs"), dict) else {}
    allowed = _ROLE_RECORDS[identity["role"]]
    alerts = _bounded(dashboard.get("alerts"), limit, _RECORD_FIELDS["alerts"]) if "alerts" in allowed else []
    issues = _bounded(dashboard.get("issues"), limit, _RECORD_FIELDS["issues"]) if "issues" in allowed else []
    lab_queue = _bounded(labs.get("queue"), limit, _RECORD_FIELDS["labs"]) if "labs" in allowed else []
    source_times = [
        _latest_item_source_time(alerts, ("triggered_at", "resolved_at")),
        _latest_item_source_time(lab_queue, ("lab_date",)),
    ]
    return {"contract": "baiamonte.direct-site.v1", "alerts": alerts, "issues": issues,
            "lab_queue": lab_queue, "freshness": _freshness(max((value for value in source_times if value), default=None))}


@router.get("/energy")
async def mobile_energy(
    projection: Literal["solar", "battery"] = Query("solar"),
    range: Literal["24h", "7d"] = Query("24h"),
    identity: dict[str, Any] = Depends(require_energy),
) -> dict[str, Any]:
    if projection == "battery":
        telemetry = await read_live_energy(
            estate_id=estate_id(), role=identity["role"],
            capabilities=frozenset(identity["capabilities"]),
            range_value=range,
        )
        source = telemetry["source"]
        return {"contract": "baiamonte.direct-site.v1", "energy": telemetry,
                "freshness": {"generated_at": datetime.now(timezone.utc).isoformat(),
                              "source_generated_at": source["source_generated_at"],
                              "data_age_seconds": source["data_age_seconds"],
                              "stale": source["state"] != "current"}}
    payload = await run_in_threadpool(display_payload)
    solar = payload.get("solar", {}) if isinstance(payload.get("solar"), dict) else {}
    safe = {key: solar.get(key) for key in ("available", "current_power", "energy_today", "forecast_energy_remaining", "forecast_energy_tomorrow")}
    return {"contract": "baiamonte.direct-site.v1", "energy": safe, "freshness": _freshness(None)}


@router.get("/etna")
def mobile_etna(_: dict[str, Any] = Depends(require_etna)) -> dict[str, Any]:
    raw = etna_status()
    source_time, sources_healthy = _etna_source_health(raw)
    freshness = _freshness(source_time)
    safe = {key: raw.get(key) for key in ("generated_at", "last_complete_at", "activity", "communications", "seismic_events", "safety_note")}
    safe["fresh"] = sources_healthy and freshness["stale"] is False
    return {"contract": "baiamonte.direct-site.v1", "etna": safe, "freshness": freshness}
