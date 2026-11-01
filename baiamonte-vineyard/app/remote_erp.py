"""Bounded reporting replication for the private website ERP."""

from __future__ import annotations

import asyncio
import base64
import gzip
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import websockets

from fastapi import APIRouter, Depends, Header, HTTPException, Request as FastAPIRequest

from .access import authorize_admin
from .config import RUNTIME_OPTIONS_PATH, addon_version, get_settings, runtime_option
from .db import connect, transaction
from .etna import etna_status
from .service import audit
from .ha_auth import home_assistant_token


logger = logging.getLogger("baiamonte.remote_erp")
router = APIRouter(prefix="/api/v1/admin/remote-erp", tags=["administration"])
STATE_PATH = Path("/data/remote-erp-state.json")
_snapshot_lock = threading.Lock()
_command_lock = threading.Lock()
_camera_lock = asyncio.Lock()
REMOTE_ERP_CONTRACT_VERSION = 1
AUTHORITATIVE_API_BASE_URL = "http://127.0.0.1:8099"


def source_app_version() -> str:
    """Return the injected build version or the packaged manifest version."""
    return os.environ.get("BUILD_VERSION", "").strip() or addon_version()

REPORTING_OBJECTS = (
    "alerts", "cadastral_parcels", "cellar_containers", "cellar_control_profiles",
    "cellar_lot_trace_records", "cellar_operations", "estates",
    "fermentation_observations", "gdd_forecasts", "grape_varieties", "harvest_lots",
    "harvest_lot_blocks", "harvest_lot_parcels", "harvest_plans", "issues_decisions",
    "lab_decision_notes", "lab_results", "lab_reviews", "lab_samples", "seasons",
    "tasks", "vineyard_blocks", "vintage_summaries", "weather_daily",
    "weather_observations", "wine_lots", "work_activities", "ro_system_whatsapp_events",
    "ro_system_whatsapp_intake", "ro_vehicle_presence_associations",
    "ro_vehicle_presence_events", "v_harvest_summary", "v_lab_comparison", "v_open_work",
    "ro_block_varieties", "ro_vineyard_terraces", "ro_phenology_observations",
    "ro_maturity_samples", "ro_scouting_observations", "ro_scouting_damage_scopes",
    "ro_vineyard_damage_assessments", "ro_irrigation_events", "ro_vineyard_soil_samples",
    "ro_weather_stations", "ro_latest_block_phenology", "ro_water_deliveries",
    "ro_water_delivery_observations", "ro_cistern_level_estimates",
    "ro_estate_energy_observations", "ro_equipment", "ro_equipment_service_events",
    "ro_cellar_maintenance_records", "ro_treatment_history", "ro_inventory_current",
    "ro_inventory_balance", "ro_lab_decision_queue", "ro_official_harvest_declarations",
    "ro_official_vineyard_basis", "ro_hospitality_packages", "ro_hospitality_schedule",
)
SYNTHETIC_REPORTING_OBJECTS = ("ro_etna_status", "olive_harvests", "ro_light_status")
ALL_REPORTING_OBJECTS = REPORTING_OBJECTS + SYNTHETIC_REPORTING_OBJECTS
if len(ALL_REPORTING_OBJECTS) != 63 or len(set(ALL_REPORTING_OBJECTS)) != 63:
    raise RuntimeError("remote ERP manifest must contain exactly 63 unique objects")

FORBIDDEN_COLUMN_FRAGMENTS = (
    "password", "secret", "token", "credential", "authorization", "api_key",
    "private_key", "cookie", "webhook", "cost", "price", "amount", "value_eur",
)
EXPLICIT_EXCLUSIONS = {
    "cellar_operations": {"amount"},
    # The remote UI uses forecast values, dates and confidence. This internal
    # evidence blob repeats tens of kilobytes in every historical forecast and
    # remains available only in authoritative Vineyard Operations.
    "gdd_forecasts": {"calibration_evidence"},
    "work_activities": {"cost_eur"},
}
UPDATED_CANDIDATES = (
    "updated_at", "observed_at", "recorded_at", "created_at", "sampled_at",
    "occurred_at", "activity_date", "harvest_date", "measurement_date", "date",
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
CAMERA_ALLOWLIST = {
    "camera.vineyard_north": "Main Parking", "camera.west_360": "West 360",
    "camera.bbq_grill_2": "BBQ Grill", "camera.kitchen": "Kitchen",
    "camera.west_etna_view": "West Etna View", "camera.east_360": "East 360",
    "camera.gate_doorbell_2": "Front Gate Doorbell", "camera.rear_gate": "Rear Gate",
    "camera.top_vineyard_360": "Rear Entrance Path 360", "camera.fox_ally": "Fox Alley",
    "camera.mid_vineyard_north": "Entrance Road", "camera.cisterna": "Cistern Internal",
}
LIGHT_ALLOWLIST = {
    "light.switch_1_lightbulb": "Kitchen overhead",
    "light.switch_2_lightbulb": "Warehouse",
    "light.switch_3_lightbulb": "Toilette",
    "light.switch_4_lightbulb": "Palmento",
    "light.switch_5_lightbulb": "Patio",
    "light.switch_6_lightbulb": "Patio strip",
    "light.switch_7_lightbulb": "Kitchen sink",
    "light.switch_8_lightbulb": "Fox Den overhead",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_value, allow_nan=False)


def reporting_row_revision(data: dict[str, Any]) -> int:
    revision = data.get("revision")
    if isinstance(revision, int) and revision >= 0:
        return revision
    canonical = _canonical({key: _json_value(value) for key, value in data.items()})
    return int.from_bytes(hashlib.sha256(canonical.encode()).digest()[:8], "big") >> 1


def locked_reporting_record(cursor: Any, object_name: str, record_id: str, estate: str) -> tuple[dict[str, Any], int] | None:
    """Lock and return one writable reporting row using the snapshot's exact revision rule."""
    if object_name not in {"tasks", "issues_decisions", "cellar_control_profiles"}:
        raise ValueError("unsupported remote command object")
    columns = _safe_columns(cursor)[object_name]
    if "id" not in columns or "estate_id" not in columns:
        raise RuntimeError("remote command object has no scoped identity")
    cursor.execute(
        f"SELECT {','.join(f'`{column}`' for column in columns)} FROM `{object_name}` "
        "WHERE id=%s AND estate_id=%s FOR UPDATE",
        (record_id, estate),
    )
    row = cursor.fetchone()
    if not row:
        return None
    data = {key: _json_value(value) for key, value in row.items()}
    return data, reporting_row_revision(data)


def _etna_reporting_data() -> dict[str, Any]:
    """Return only the approved public-source Etna cache, never fetch sources."""
    cached = etna_status()
    return {
        "generated_at": cached.get("generated_at"),
        "last_complete_at": cached.get("last_complete_at"),
        "expires_at": cached.get("expires_at"),
        "fresh": bool(cached.get("fresh")),
        "stale_sources": list(cached.get("stale_sources") or []),
        "source_status": dict(cached.get("source_status") or {}),
        "sources": dict(cached.get("sources") or {}),
        "activity": dict(cached.get("activity") or {}),
        "communications": list(cached.get("communications") or [])[:100],
        "bulletin": cached.get("bulletin"),
        "ash_advisory": cached.get("ash_advisory"),
        "civil_protection": cached.get("civil_protection"),
        "seismic_events": list(cached.get("seismic_events") or [])[:50],
        "webcams": list(cached.get("webcams") or [])[:12],
        "webcam_updated_utc": cached.get("webcam_updated_utc"),
        "webcam_checked_at": cached.get("webcam_checked_at"),
        "safety_note": cached.get("safety_note"),
        "updated_at": cached.get("generated_at"),
    }


def _olive_harvest_reporting_records(cursor: Any) -> list[dict[str, Any]]:
    """Return the explicit non-financial olive harvest projection.

    Worker identity, labor, notes, evidence and cost-model data remain only in
    the authoritative database. Missing harvest or mill dates stay null.
    """
    cursor.execute(
        "SELECT id,estate_id,record_year,record_date,activity,status,"
        "olives_harvested_kg,mill_date,oil_liters,yield_pct "
        "FROM olive_records WHERE estate_id=%s ORDER BY id",
        (get_settings().estate_id,),
    )
    records: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        record_id = str(row["id"])
        data = {key: _json_value(value) for key, value in row.items() if key != "id"}
        records.append({
            "object": "olive_harvests",
            "id": record_id,
            "revision": reporting_row_revision(data),
            "source_updated_at": data.get("mill_date") or data.get("record_date"),
            "data": data,
        })
    return records


def _light_status_reporting_records() -> list[dict[str, Any]]:
    """Return only state and age for the fixed ordinary-light allowlist."""
    token = home_assistant_token()
    states: dict[str, dict[str, Any]] = {}
    if token:
        request = Request(
            "http://supervisor/core/api/states",
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
            if isinstance(payload, list):
                states = {str(item.get("entity_id")): item for item in payload if isinstance(item, dict)}
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            states = {}
    records = []
    for entity_id, name in LIGHT_ALLOWLIST.items():
        item = states.get(entity_id, {})
        state = str(item.get("state") or "unavailable").casefold()
        if state not in {"on", "off"}:
            state = "unavailable"
        data = {"entity_id": entity_id, "name": name, "state": state, "observed_at": item.get("last_updated")}
        records.append({"object": "ro_light_status", "id": entity_id, "revision": reporting_row_revision(data), "source_updated_at": data["observed_at"], "data": data})
    return records


def _safe_columns(cursor: Any) -> dict[str, list[str]]:
    placeholders = ",".join(["%s"] * len(REPORTING_OBJECTS))
    cursor.execute(
        "SELECT table_name,column_name FROM information_schema.columns "
        f"WHERE table_schema=%s AND table_name IN ({placeholders}) ORDER BY table_name,ordinal_position",
        (get_settings().db_name, *REPORTING_OBJECTS),
    )
    result = {name: [] for name in REPORTING_OBJECTS}
    for row in cursor.fetchall():
        name, column = str(row["table_name"]), str(row["column_name"])
        lowered = column.casefold()
        if column in EXPLICIT_EXCLUSIONS.get(name, set()) or any(part in lowered for part in FORBIDDEN_COLUMN_FRAGMENTS):
            continue
        if not _IDENTIFIER.fullmatch(column):
            raise RuntimeError(f"unsafe reporting column name for {name}")
        result[name].append(column)
    missing = [name for name, columns in result.items() if not columns]
    if missing:
        raise RuntimeError(f"reporting manifest unavailable: {', '.join(missing)}")
    return result


def _primary_keys(cursor: Any) -> dict[str, list[str]]:
    placeholders = ",".join(["%s"] * len(REPORTING_OBJECTS))
    cursor.execute(
        "SELECT table_name,column_name FROM information_schema.statistics "
        f"WHERE table_schema=%s AND index_name='PRIMARY' AND table_name IN ({placeholders}) "
        "ORDER BY table_name,seq_in_index",
        (get_settings().db_name, *REPORTING_OBJECTS),
    )
    keys = {name: [] for name in REPORTING_OBJECTS}
    for row in cursor.fetchall():
        keys[str(row["table_name"])].append(str(row["column_name"]))
    return keys


def build_snapshot() -> dict[str, Any]:
    query_started = time.monotonic()
    object_seconds: dict[str, float] = {}
    connection = connect()
    try:
        with connection.cursor() as cursor:
            columns, primary_keys = _safe_columns(cursor), _primary_keys(cursor)
            connection.commit()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            records: list[dict[str, Any]] = []
            for object_name in REPORTING_OBJECTS:
                object_started = time.monotonic()
                selected = columns[object_name]
                cursor.execute(f"SELECT {','.join(f'`{column}`' for column in selected)} FROM `{object_name}`")
                rows = list(cursor.fetchall())
                object_seconds[object_name] = round(time.monotonic() - object_started, 4)
                rows.sort(key=_canonical)
                duplicate_counts: dict[str, int] = {}
                for row in rows:
                    data = {key: _json_value(value) for key, value in row.items()}
                    canonical = _canonical(data)
                    keys = primary_keys[object_name]
                    if keys and all(data.get(key) is not None for key in keys):
                        record_id = "|".join(str(data[key]) for key in keys)
                    elif data.get("id") is not None:
                        record_id = str(data["id"])
                    else:
                        digest = hashlib.sha256(canonical.encode()).hexdigest()
                        ordinal = duplicate_counts.get(digest, 0)
                        duplicate_counts[digest] = ordinal + 1
                        record_id = digest if ordinal == 0 else f"{digest}:{ordinal}"
                    revision = reporting_row_revision(data)
                    updated = next((data.get(key) for key in UPDATED_CANDIDATES if data.get(key) is not None), None)
                    records.append({"object": object_name, "id": record_id, "revision": revision, "source_updated_at": updated, "data": data})
            olive_started = time.monotonic()
            records.extend(_olive_harvest_reporting_records(cursor))
            object_seconds["olive_harvests"] = round(time.monotonic() - olive_started, 4)
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    light_started = time.monotonic()
    records.extend(_light_status_reporting_records())
    object_seconds["ro_light_status"] = round(time.monotonic() - light_started, 4)
    etna_data = _etna_reporting_data()
    etna_canonical = _canonical(etna_data)
    records.append({
        "object": "ro_etna_status", "id": "current",
        "revision": int.from_bytes(hashlib.sha256(etna_canonical.encode()).digest()[:8], "big") >> 1,
        "source_updated_at": etna_data.get("generated_at"), "data": etna_data,
    })
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    return {
        "snapshot_id": str(uuid4()), "source_generated_at": generated_at,
        "source_app_version": source_app_version(),
        "remote_contract_version": REMOTE_ERP_CONTRACT_VERSION,
        "record_count": len(records), "records": records,
        "body_sha256": hashlib.sha256(_canonical(records).encode()).hexdigest(),
        "snapshot_metrics": {
            "database_read_seconds": round(time.monotonic() - query_started, 3),
            "slowest_objects": sorted(object_seconds.items(), key=lambda item: item[1], reverse=True)[:5],
        },
    }


def _decode_key(value: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value.strip() + "=" * (-len(value.strip()) % 4))
    except Exception as error:
        raise ValueError("Remote ERP key must be base64url") from error
    if len(decoded) != 32:
        raise ValueError("Remote ERP key must contain exactly 256 bits")
    return decoded


@dataclass(frozen=True)
class RemoteERPConfig:
    enabled: bool
    base_url: str
    key_id: str
    secret: str
    interval_minutes: int

    @classmethod
    def current(cls) -> "RemoteERPConfig":
        return cls(
            bool(runtime_option("remote_erp_enabled", False)),
            str(runtime_option("remote_erp_url", "https://cantinabaiamonte.com/erp")).rstrip("/"),
            str(runtime_option("remote_erp_key_id", "baiamonte-vineyard-1")).strip(),
            str(runtime_option("remote_erp_hmac_key", "")).strip(),
            max(5, min(1440, int(runtime_option("remote_erp_snapshot_minutes", 15)))),
        )

    def validate(self, require_secret: bool = True) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Remote ERP URL must be an HTTPS origin/path")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.key_id):
            raise ValueError("Remote ERP key ID is invalid")
        if require_secret:
            _decode_key(self.secret)


@dataclass(frozen=True)
class RemoteCameraConfig:
    enabled: bool
    base_url: str
    key_id: str
    secret: str
    poll_seconds: int

    @classmethod
    def current(cls) -> "RemoteCameraConfig":
        return cls(
            bool(runtime_option("remote_camera_enabled", False)),
            str(runtime_option("remote_erp_url", "https://cantinabaiamonte.com/erp")).rstrip("/"),
            str(runtime_option("remote_camera_key_id", "baiamonte-camera-1")).strip(),
            str(runtime_option("remote_camera_hmac_key", "")).strip(),
            max(5, min(60, int(runtime_option("remote_camera_poll_seconds", 5)))),
        )

    def validate(self, require_secret: bool = True) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Remote camera URL must be an HTTPS origin/path")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", self.key_id):
            raise ValueError("Remote camera key ID is invalid")
        if require_secret:
            _decode_key(self.secret)


def _signed_post(
    config: RemoteERPConfig | RemoteCameraConfig,
    route: str,
    payload: dict[str, Any],
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    config.validate()
    plain_body = _canonical(payload).encode()
    body = gzip.compress(plain_body, compresslevel=6, mtime=0)
    timestamp = str(int(time.time()))
    signature = hmac.new(config.secret.encode("ascii"), timestamp.encode() + b"\n" + body, hashlib.sha256).hexdigest()
    request = Request(config.base_url + route, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Content-Encoding": "gzip", "X-Baiamonte-Uncompressed-Length": str(len(plain_body)),
        "X-Baiamonte-Key-Id": config.key_id, "X-Baiamonte-Timestamp": timestamp,
        "X-Baiamonte-Signature": "sha256=" + signature,
    })
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Remote ERP rejected the sync request ({error.code})") from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Remote ERP connection failed") from error
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("Remote ERP rejected the sync request")
    return result


def _read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(value: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":"), default=str), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(STATE_PATH)


def _source_pressure_reason() -> str | None:
    """Cheap due-time guard; it performs no database query or recurring scan."""
    try:
        cpu_count = max(1, os.cpu_count() or 1)
        if os.getloadavg()[0] > cpu_count * 2.0:
            return "host load is elevated"
    except (AttributeError, OSError):
        pass
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        if values.get("MemAvailable", 999_999_999) < 262_144:
            return "available memory is below 256 MiB"
    except (OSError, ValueError, IndexError):
        pass
    return None


def push_snapshot() -> dict[str, Any]:
    config = RemoteERPConfig.current()
    if not config.enabled:
        raise RuntimeError("Remote ERP synchronization is disabled")
    if not _snapshot_lock.acquire(blocking=False):
        raise RuntimeError("Remote ERP snapshot already running")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started_monotonic = time.monotonic()
    try:
        pressure = _source_pressure_reason()
        if pressure:
            raise RuntimeError("Remote ERP paused because " + pressure)
        snapshot = build_snapshot()
        payload_bytes = len(_canonical(snapshot).encode())
        _signed_post(config, "/sync/snapshots", snapshot)
        state = {"last_attempt_at": started, "last_success_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "last_error": None, "snapshot_id": snapshot["snapshot_id"], "record_count": snapshot["record_count"], "object_count": len(ALL_REPORTING_OBJECTS), "duration_seconds": round(time.monotonic()-started_monotonic,3), "database_read_seconds": snapshot["snapshot_metrics"]["database_read_seconds"], "payload_bytes": payload_bytes, "slowest_objects": snapshot["snapshot_metrics"]["slowest_objects"]}
        _write_state(state)
        return state
    except Exception as error:
        _write_state({**_read_state(), "last_attempt_at": started, "last_error": str(error)[:300]})
        raise
    finally:
        _snapshot_lock.release()


async def remote_erp_loop() -> None:
    await asyncio.sleep(15)
    while True:
        config, state = RemoteERPConfig.current(), _read_state()
        due = True
        if state.get("last_attempt_at"):
            try:
                due = time.time() - datetime.fromisoformat(str(state["last_attempt_at"])).timestamp() >= config.interval_minutes * 60
            except ValueError:
                pass
        if config.enabled and due:
            try:
                await asyncio.to_thread(push_snapshot)
            except Exception:
                logger.exception("Remote ERP snapshot failed")
        await asyncio.sleep(30)


def _local_domain_request(method: str, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.api_key:
        raise RuntimeError("authoritative application API key is unavailable")
    body = _canonical(payload).encode()
    request = Request(
        # app.main owns the validated mutation routes. Port 8101 serves the
        # read-only display application and must never receive commands.
        AUTHORITATIVE_API_BASE_URL + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "X-API-Key": settings.api_key, **headers},
    )
    try:
        with urlopen(request, timeout=20) as response:
            decoded = json.loads(response.read())
    except HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw).get("detail")
        except (json.JSONDecodeError, AttributeError):
            detail = None
        if error.code == 409:
            result = detail if isinstance(detail, dict) else {"reason": str(detail or "revision_conflict")}
            raise RemoteCommandConflict(result) from error
        if error.code in {400, 404, 422}:
            raise RemoteCommandRejected(str(detail or "domain_validation_failed")[:240]) from error
        raise RuntimeError(f"authoritative domain API returned HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError("authoritative domain API unavailable") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("authoritative domain API returned an invalid response")
    return decoded


class RemoteCommandConflict(Exception):
    def __init__(self, result: dict[str, Any]):
        super().__init__("revision conflict")
        self.result = result


class RemoteCommandRejected(Exception):
    pass


def _expected_revision(value: Any) -> int | None:
    """Parse the website's lossless decimal revision representation."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        revision = value
    elif isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        revision = int(value)
    else:
        return None
    return revision if 0 <= revision <= (2**63 - 1) else None


def _light_observation(entity_id: str, token: str) -> tuple[str, str | None]:
    request = Request(
        "http://supervisor/core/api/states/" + entity_id,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
            if not isinstance(payload, dict):
                return "unavailable", None
            state = str(payload.get("state") or "").casefold()
            observed_at = payload.get("last_updated")
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RemoteCommandRejected("light_state_unavailable") from error
    if state not in {"on", "off"} or not isinstance(observed_at, str):
        return "unavailable", None
    try:
        parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return "unavailable", None
    if parsed.tzinfo is None:
        return "unavailable", None
    return state, parsed.astimezone(timezone.utc).isoformat()


def _set_light_state(entity_id: str, desired_state: str, token: str) -> None:
    service = "turn_on" if desired_state == "on" else "turn_off"
    request = Request(
        "http://supervisor/core/api/services/light/" + service,
        data=_canonical({"entity_id": entity_id}).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise RemoteCommandRejected("light_service_unavailable") from error


def _light_event_payload(command_id: str) -> dict[str, Any] | None:
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT payload FROM integration_events WHERE estate_id=%s AND integration_name='remote-light-control' "
            "AND event_type='light_control' AND external_id=%s ORDER BY id DESC LIMIT 1",
            (get_settings().estate_id, command_id),
        )
        row = cursor.fetchone()
    if not row:
        return None
    value = row.get("payload")
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else None


def _light_event_start(command_id: str, fingerprint: str, actor: str, entity_id: str, expected: str, desired: str) -> dict[str, Any]:
    existing = _light_event_payload(command_id)
    if existing is not None:
        return existing
    value = {"request_fingerprint": fingerprint, "entity_id": entity_id, "expected_state": expected, "desired_state": desired, "terminal_status": None, "result": None}
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,'remote-light-control','inbound','light_control',%s,'received',%s)",
            (get_settings().estate_id, command_id, _canonical(value)),
        )
        audit(cursor, "light_control_started", "home_assistant_light", entity_id, {"command_id": command_id, "expected_state": expected, "desired_state": desired}, actor)
    return value


def _light_event_finish(command_id: str, fingerprint: str, actor: str, entity_id: str, expected: str, desired: str, terminal_status: str, result: dict[str, Any]) -> None:
    value = {"request_fingerprint": fingerprint, "entity_id": entity_id, "expected_state": expected, "desired_state": desired, "terminal_status": terminal_status, "result": result, "result_delivered": False}
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET status='processed',payload=%s,error_message=%s WHERE estate_id=%s "
            "AND integration_name='remote-light-control' AND event_type='light_control' AND external_id=%s",
            (_canonical(value), None if terminal_status == "applied" else str(result.get("reason") or terminal_status)[:1000], get_settings().estate_id, command_id),
        )
        audit(cursor, "light_control_" + terminal_status, "home_assistant_light", entity_id, {"command_id": command_id, **result}, actor)


def _pending_light_results(limit: int = 10) -> list[dict[str, Any]]:
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT external_id,payload FROM integration_events WHERE estate_id=%s AND integration_name='remote-light-control' "
            "AND event_type='light_control' AND status='processed' ORDER BY id LIMIT %s",
            (get_settings().estate_id, max(1, min(50, limit))),
        )
        rows = list(cursor.fetchall())
    pending = []
    for row in rows:
        value = row.get("payload")
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict) or value.get("result_delivered") is True:
            continue
        status, result = value.get("terminal_status"), value.get("result")
        if status in {"applied", "conflict", "rejected"} and isinstance(result, dict):
            pending.append({"command_id": str(row["external_id"]), "status": status, "result": result})
    return pending


def _mark_light_result_delivered(command_id: str) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='remote-light-control' "
            "AND event_type='light_control' AND external_id=%s ORDER BY id DESC LIMIT 1 FOR UPDATE",
            (get_settings().estate_id, command_id),
        )
        row = cursor.fetchone()
        if not row:
            return
        value = row.get("payload")
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return
        value["result_delivered"] = True
        cursor.execute(
            "UPDATE integration_events SET status='ignored',payload=%s WHERE id=%s",
            (_canonical(value), row["id"]),
        )


def _replay_light_terminal(event: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    if not hmac.compare_digest(str(event.get("request_fingerprint") or ""), fingerprint):
        raise RemoteCommandRejected("light_command_uuid_collision")
    status, result = event.get("terminal_status"), event.get("result")
    if status is None:
        return None
    if not isinstance(result, dict):
        raise RemoteCommandRejected("light_command_audit_invalid")
    if status == "applied":
        return result
    if status == "conflict":
        raise RemoteCommandConflict(result)
    raise RemoteCommandRejected(str(result.get("reason") or "light_command_rejected"))


def _apply_light_command(command_id: str, record_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    owner = str(runtime_option("remote_light_owner_username", "")).strip()
    if not bool(runtime_option("remote_light_control_enabled", False)) or not owner or not hmac.compare_digest(actor, owner):
        raise RemoteCommandRejected("light_actor_or_capability_not_authorized")
    if record_id not in LIGHT_ALLOWLIST or set(payload) != {"desired_state", "expected_state", "expected_observed_at", "expires_at"}:
        raise RemoteCommandRejected("light_request_not_permitted")
    desired, expected = payload.get("desired_state"), payload.get("expected_state")
    if desired not in {"on", "off"} or expected not in {"on", "off"} or desired == expected:
        raise RemoteCommandRejected("light_state_transition_invalid")
    try:
        expires = datetime.strptime(str(payload.get("expires_at")), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        expected_observed = datetime.fromisoformat(str(payload.get("expected_observed_at")).replace("Z", "+00:00"))
    except ValueError as error:
        raise RemoteCommandRejected("light_timestamp_invalid") from error
    if expected_observed.tzinfo is None:
        raise RemoteCommandRejected("light_timestamp_invalid")
    expected_observed = expected_observed.astimezone(timezone.utc)
    fingerprint = hashlib.sha256(_canonical({"actor": actor, "entity_id": record_id, "payload": payload}).encode()).hexdigest()
    event = _light_event_payload(command_id)
    resumed = event is not None
    if resumed:
        replay = _replay_light_terminal(event, fingerprint)
        if replay is not None:
            return replay
    now = datetime.now(timezone.utc)
    if not resumed and (expires <= now or expires > now + timedelta(seconds=45)):
        event = _light_event_start(command_id, fingerprint, actor, record_id, str(expected), str(desired))
        result = {"reason": "light_request_expiry_invalid"}
        _light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result)
        raise RemoteCommandRejected(result["reason"])
    if not resumed:
        event = _light_event_start(command_id, fingerprint, actor, record_id, str(expected), str(desired))
    token = home_assistant_token()
    if not token:
        result = {"reason": "light_state_unavailable"};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    current, current_observed_at = _light_observation(record_id, token)
    if current == "unavailable":
        result = {"reason": "light_state_unavailable"};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    if resumed:
        if current == desired:
            result = {"entity_id": record_id, "observed_state": current, "observed_at": current_observed_at, "reconciled": True};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "applied", result);return result
        result = {"reason": "light_command_outcome_uncertain", "actual_state": current, "observed_at": current_observed_at};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    if current != expected:
        result = {"reason": "light_state_changed", "actual_state": current, "observed_at": current_observed_at};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "conflict", result);raise RemoteCommandConflict(result)
    current_observed = datetime.fromisoformat(str(current_observed_at))
    if current_observed != expected_observed:
        result = {"reason": "light_observation_changed", "actual_state": current, "observed_at": current_observed_at};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "conflict", result);raise RemoteCommandConflict(result)
    if datetime.now(timezone.utc) >= expires:
        result = {"reason": "light_request_expired"};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    try:
        _set_light_state(record_id, str(desired), token)
    except RemoteCommandRejected:
        after_state, after_observed_at = _light_observation(record_id, token)
        if after_state == desired:
            result = {"entity_id": record_id, "observed_state": desired, "observed_at": after_observed_at, "reconciled": True};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "applied", result);return result
        result = {"reason": "light_command_outcome_uncertain", "actual_state": after_state, "observed_at": after_observed_at};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    final_state, final_observed_at = _light_observation(record_id, token)
    if final_state != desired:
        result = {"reason": "light_postcondition_failed"};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "rejected", result);raise RemoteCommandRejected(result["reason"])
    result = {"entity_id": record_id, "observed_state": final_state, "observed_at": final_observed_at};_light_event_finish(command_id, fingerprint, actor, record_id, str(expected), str(desired), "applied", result);return result


def _apply_remote_command(command: dict[str, Any]) -> dict[str, Any]:
    command_id = str(command.get("command_id") or "")
    command_type = str(command.get("command_type") or "")
    object_name = str(command.get("object") or "")
    record_id = str(command.get("record_id") or "")
    expected = command.get("expected_revision")
    payload = command.get("payload")
    if (
        not isinstance(command.get("actor_username"), str)
        or not command.get("actor_username").strip()
        or command.get("actor_role") != "admin"
        or command.get("actor_enabled") is not True
    ):
        raise RemoteCommandRejected("actor_not_authorized")
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", command_id, re.I):
        raise RemoteCommandRejected("invalid_command_id")
    if not isinstance(payload, dict):
        raise RemoteCommandRejected("invalid_payload")
    if command_type == "light.control" or object_name == "ha_light":
        if command_type != "light.control" or object_name != "ha_light":
            raise RemoteCommandRejected("light_contract_not_authorized")
        return _apply_light_command(command_id, record_id, payload, str(command["actor_username"]).strip())
    headers = {"X-Baiamonte-Command-ID": command_id, "X-Baiamonte-Record-ID": record_id}
    headers["X-Remote-User-Name"] = command["actor_username"].strip()
    if command_type == "record.create" and object_name == "tasks":
        if expected is not None:
            raise RemoteCommandRejected("create_must_not_include_revision")
        allowed = {"title", "category", "status", "priority", "due_date", "block_id", "estimated_hours", "notes"}
        if set(payload) - allowed:
            raise RemoteCommandRejected("unsupported_task_fields")
        year = date.today().year
        due = payload.get("due_date")
        if isinstance(due, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            year = int(due[:4])
        return _local_domain_request("POST", f"/api/v1/tasks?year={year}", payload, headers)
    if command_type == "record.update" and object_name == "tasks":
        expected = _expected_revision(expected)
        if expected is None or set(payload) != {"status"}:
            raise RemoteCommandRejected("task_updates_require_status_and_revision")
        headers["X-Baiamonte-Expected-Revision"] = str(expected)
        return _local_domain_request("PATCH", f"/api/v1/tasks/{record_id}/status", payload, headers)
    if command_type == "record.update" and object_name == "issues_decisions":
        allowed = {"priority", "decision_action", "owner_text", "due_date", "status", "closed_date", "notes"}
        expected = _expected_revision(expected)
        if expected is None or not payload or set(payload) - allowed:
            raise RemoteCommandRejected("issue_updates_require_supported_fields_and_revision")
        headers["X-Baiamonte-Expected-Revision"] = str(expected)
        return _local_domain_request("PATCH", f"/api/v1/issues/{record_id}", payload, headers)
    if command_type == "record.update" and object_name == "cellar_control_profiles":
        allowed = {"babo", "temp_c", "observed_at", "notes"}
        expected = _expected_revision(expected)
        if expected is None or set(payload) - allowed:
            raise RemoteCommandRejected("tank_readings_require_supported_fields_and_revision")
        if not payload.get("observed_at") or (payload.get("babo") in (None, "") and payload.get("temp_c") in (None, "")):
            raise RemoteCommandRejected("tank_readings_require_timestamp_and_measurement")
        headers["X-Baiamonte-Expected-Revision"] = str(expected)
        return _local_domain_request(
            "POST", f"/api/v1/agronomy/tank-profiles/{record_id}/reading", payload, headers,
        )
    raise RemoteCommandRejected("unsupported_domain_command")


def process_remote_commands_once(config: RemoteERPConfig | None = None) -> int:
    config = config or RemoteERPConfig.current()
    if not config.enabled:
        return 0
    if not _command_lock.acquire(blocking=False):
        return 0
    try:
        for pending in _pending_light_results(10):
            _signed_post(config, "/sync/results", pending, 30)
            _mark_light_result_delivered(str(pending["command_id"]))
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=90)).strftime("%Y-%m-%d %H:%M:%S.%f")
        response = _signed_post(config, "/sync/commands", {"limit": 10, "lease_until": lease_until}, 30)
        handled = 0
        for command in response.get("commands", []):
            if not isinstance(command, dict):
                continue
            try:
                result = _apply_remote_command(command)
                status = "applied"
            except RemoteCommandConflict as error:
                result, status = error.result, "conflict"
            except RemoteCommandRejected as error:
                result, status = {"reason": str(error)}, "rejected"
            _signed_post(config, "/sync/results", {
                "command_id": str(command.get("command_id") or ""),
                "status": status,
                "result": result,
            }, 30)
            if command.get("command_type") == "light.control":
                _mark_light_result_delivered(str(command.get("command_id") or ""))
            handled += 1
        return handled
    finally:
        _command_lock.release()


async def remote_command_loop() -> None:
    await asyncio.sleep(5)
    while True:
        config = RemoteERPConfig.current()
        if config.enabled and not _source_pressure_reason():
            try:
                await asyncio.to_thread(process_remote_commands_once, config)
            except Exception:
                logger.exception("Remote ERP command processing failed")
        await asyncio.sleep(5)


def _camera_available(camera_id: str, token: str) -> bool:
    request = Request(
        "http://supervisor/core/api/states/" + camera_id,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            state = json.loads(response.read()).get("state")
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise RuntimeError("ha_offline") from error
    return str(state).casefold() not in {"", "unknown", "unavailable"}


async def _sign_camera_path(camera_id: str, token: str) -> str:
    if camera_id not in CAMERA_ALLOWLIST:
        raise ValueError("camera_unavailable")
    path = "/api/camera_proxy/" + camera_id
    async with websockets.connect("ws://supervisor/core/api/websocket", open_timeout=5, close_timeout=2) as socket:
        required = json.loads(await asyncio.wait_for(socket.recv(), 5))
        if required.get("type") != "auth_required":
            raise RuntimeError("signing_failed")
        await socket.send(_canonical({"type": "auth", "access_token": token}))
        authenticated = json.loads(await asyncio.wait_for(socket.recv(), 5))
        if authenticated.get("type") != "auth_ok":
            raise RuntimeError("signing_failed")
        await socket.send(_canonical({"id": 1, "type": "auth/sign_path", "path": path, "expires": 30}))
        result = json.loads(await asyncio.wait_for(socket.recv(), 5))
    signed_path = result.get("result", {}).get("path") if result.get("success") is True else None
    parts = urlsplit(str(signed_path or ""))
    if parts.scheme or parts.netloc or parts.path != path or not parts.query:
        raise RuntimeError("signing_failed")
    return str(signed_path)


async def process_camera_requests() -> int:
    config = RemoteCameraConfig.current()
    if not config.enabled:
        return 0
    token = home_assistant_token()
    if not token:
        raise RuntimeError("ha_offline")
    if _camera_lock.locked():
        return 0
    async with _camera_lock:
        return await _process_one_camera_request(config, token)


async def _process_one_camera_request(config: RemoteCameraConfig, token: str) -> int:
    result = await asyncio.to_thread(
        _signed_post, config, "/sync/camera-requests", {"limit": 1}, 10
    )
    handled = 0
    for item in result.get("requests", []):
        request_uuid, camera_id = str(item.get("request_uuid", "")), str(item.get("camera_id", ""))
        if camera_id not in CAMERA_ALLOWLIST or not re.fullmatch(r"[0-9a-f-]{36}", request_uuid):
            continue
        try:
            if not await asyncio.to_thread(_camera_available, camera_id, token):
                raise RuntimeError("camera_unavailable")
            issued = datetime.now(timezone.utc)
            signed_path = await _sign_camera_path(camera_id, token)
            payload = {"status": "ready", "camera_id": camera_id, "signed_path": signed_path,
                       "issued_at": issued.isoformat(), "expires_at": datetime.fromtimestamp(issued.timestamp() + 30, timezone.utc).isoformat()}
        except Exception as error:
            reason = str(error) if str(error) in {"ha_offline", "camera_unavailable", "signing_failed"} else "signing_failed"
            payload = {"status": "failed", "camera_id": camera_id, "reason": reason}
        await asyncio.to_thread(
            _signed_post, config, "/sync/camera-results/" + request_uuid, payload, 10
        )
        handled += 1
    return handled


async def remote_camera_loop() -> None:
    await asyncio.sleep(10)
    idle_seconds = 5
    while True:
        config = RemoteCameraConfig.current()
        if config.enabled:
            pressure = _source_pressure_reason()
            if pressure:
                idle_seconds = 60
                logger.info("Remote camera polling paused: %s", pressure)
            else:
                try:
                    handled = await process_camera_requests()
                    idle_seconds = config.poll_seconds if handled else min(30, max(config.poll_seconds, idle_seconds * 2))
                except Exception:
                    idle_seconds = min(30, max(config.poll_seconds, idle_seconds * 2))
                    logger.warning("Remote camera request poll failed", exc_info=True)
        else:
            idle_seconds = 60
        await asyncio.sleep(idle_seconds)


def _csrf_admin(request: FastAPIRequest, x_baiamonte_csrf: str | None = Header(default=None)) -> None:
    authorize_admin(request, None, get_settings())
    if x_baiamonte_csrf != "same-origin":
        raise HTTPException(403, "Same-origin request confirmation required")


def _public_config(config: RemoteERPConfig) -> dict[str, Any]:
    return {"enabled": config.enabled, "url": config.base_url, "key_id": config.key_id, "secret_configured": bool(config.secret), "snapshot_minutes": config.interval_minutes, "object_count": len(ALL_REPORTING_OBJECTS)}


@router.get("", dependencies=[Depends(authorize_admin)])
def remote_erp_status() -> dict[str, Any]:
    return {"configuration": _public_config(RemoteERPConfig.current()), "status": _read_state()}


@router.put("", dependencies=[Depends(_csrf_admin)])
def update_remote_erp(payload: dict[str, Any], request: FastAPIRequest) -> dict[str, Any]:
    current = RemoteERPConfig.current()
    candidate = RemoteERPConfig(
        bool(payload.get("enabled", current.enabled)), str(payload.get("url", current.base_url)).strip().rstrip("/"),
        str(payload.get("key_id", current.key_id)).strip(), str(payload.get("secret") or "").strip() or current.secret,
        max(5, min(1440, int(payload.get("snapshot_minutes", current.interval_minutes)))),
    )
    candidate.validate(candidate.enabled or bool(candidate.secret))
    try:
        saved = json.loads(RUNTIME_OPTIONS_PATH.read_text(encoding="utf-8"))
        if not isinstance(saved, dict): saved = {}
    except (OSError, ValueError):
        saved = {}
    saved.update({"remote_erp_enabled": candidate.enabled, "remote_erp_url": candidate.base_url, "remote_erp_key_id": candidate.key_id, "remote_erp_hmac_key": candidate.secret, "remote_erp_snapshot_minutes": candidate.interval_minutes})
    temporary = RUNTIME_OPTIONS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(RUNTIME_OPTIONS_PATH)
    with transaction() as (_, cursor):
        audit(cursor, "update", "remote_erp", "configuration", {"enabled": candidate.enabled, "url": candidate.base_url, "key_id": candidate.key_id, "secret_changed": bool(payload.get("secret")), "snapshot_minutes": candidate.interval_minutes}, request.headers.get("X-Remote-User-Name") or "api")
    return {"saved": True, "configuration": _public_config(candidate)}


@router.post("/run", dependencies=[Depends(_csrf_admin)])
async def run_remote_erp() -> dict[str, Any]:
    try:
        return {"started": True, "status": await asyncio.to_thread(push_snapshot)}
    except RuntimeError as error:
        raise HTTPException(502, str(error)) from error
