"""Bounded reporting replication for the private website ERP."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request as FastAPIRequest

from .access import authorize_admin
from .config import RUNTIME_OPTIONS_PATH, get_settings, runtime_option
from .db import connect, transaction
from .service import audit


logger = logging.getLogger("baiamonte.remote_erp")
router = APIRouter(prefix="/api/v1/admin/remote-erp", tags=["administration"])
STATE_PATH = Path("/data/remote-erp-state.json")

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
    "ro_official_vineyard_basis",
)
if len(REPORTING_OBJECTS) != 58 or len(set(REPORTING_OBJECTS)) != 58:
    raise RuntimeError("remote ERP manifest must contain exactly 58 unique objects")

FORBIDDEN_COLUMN_FRAGMENTS = (
    "password", "secret", "token", "credential", "authorization", "api_key",
    "private_key", "cookie", "webhook", "cost", "price", "amount", "value_eur",
)
EXPLICIT_EXCLUSIONS = {
    "cellar_operations": {"amount"},
    "work_activities": {"cost_eur"},
}
UPDATED_CANDIDATES = (
    "updated_at", "observed_at", "recorded_at", "created_at", "sampled_at",
    "occurred_at", "activity_date", "harvest_date", "measurement_date", "date",
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,95}$")


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
    connection = connect()
    try:
        with connection.cursor() as cursor:
            columns, primary_keys = _safe_columns(cursor), _primary_keys(cursor)
            connection.commit()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            records: list[dict[str, Any]] = []
            for object_name in REPORTING_OBJECTS:
                selected = columns[object_name]
                cursor.execute(f"SELECT {','.join(f'`{column}`' for column in selected)} FROM `{object_name}`")
                rows = list(cursor.fetchall())
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
                    revision = data.get("revision")
                    if not isinstance(revision, int) or revision < 0:
                        revision = int.from_bytes(hashlib.sha256(canonical.encode()).digest()[:8], "big") >> 1
                    updated = next((data.get(key) for key in UPDATED_CANDIDATES if data.get(key) is not None), None)
                    records.append({"object": object_name, "id": record_id, "revision": revision, "source_updated_at": updated, "data": data})
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    return {
        "snapshot_id": str(uuid4()), "source_generated_at": generated_at,
        "record_count": len(records), "records": records,
        "body_sha256": hashlib.sha256(_canonical(records).encode()).hexdigest(),
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


def _signed_post(config: RemoteERPConfig, route: str, payload: dict[str, Any]) -> dict[str, Any]:
    config.validate()
    body = _canonical(payload).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(config.secret.encode("ascii"), timestamp.encode() + b"\n" + body, hashlib.sha256).hexdigest()
    request = Request(config.base_url + route, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "X-Baiamonte-Key-Id": config.key_id, "X-Baiamonte-Timestamp": timestamp,
        "X-Baiamonte-Signature": "sha256=" + signature,
    })
    try:
        with urlopen(request, timeout=45) as response:
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


def push_snapshot() -> dict[str, Any]:
    config = RemoteERPConfig.current()
    if not config.enabled:
        raise RuntimeError("Remote ERP synchronization is disabled")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        snapshot = build_snapshot()
        _signed_post(config, "/sync/snapshots", snapshot)
        state = {"last_attempt_at": started, "last_success_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "last_error": None, "snapshot_id": snapshot["snapshot_id"], "record_count": snapshot["record_count"], "object_count": 58}
        _write_state(state)
        return state
    except Exception as error:
        _write_state({**_read_state(), "last_attempt_at": started, "last_error": str(error)[:300]})
        raise


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


def _csrf_admin(request: FastAPIRequest, x_baiamonte_csrf: str | None = Header(default=None)) -> None:
    authorize_admin(request, None, get_settings())
    if x_baiamonte_csrf != "same-origin":
        raise HTTPException(403, "Same-origin request confirmation required")


def _public_config(config: RemoteERPConfig) -> dict[str, Any]:
    return {"enabled": config.enabled, "url": config.base_url, "key_id": config.key_id, "secret_configured": bool(config.secret), "snapshot_minutes": config.interval_minutes, "object_count": 58}


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
