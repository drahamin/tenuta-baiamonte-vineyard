"""Bounded internal adapter. No mobile route, grant or default connector.

Only synthetic connections have exercised this module. Reading full permitted
reporting columns to reproduce authoritative tokens needs separate live approval;
neither structural metadata nor a source review authorizes that operation.
The tasks-only Admin validator is the sole wired caller in this package.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import time
from types import MappingProxyType
from typing import Any, Callable
from collections.abc import Mapping
from uuid import UUID

from .mobile_work_review_projection import DATASETS, MAX_INPUT_ROWS, SnapshotEvidence, SourceUnavailable, _utc
from .mobile_work_review_snapshot import PreparedSnapshotInput, prepare_snapshot_input


TOKEN_SCHEME = "baiamonte.reporting-row-content-or-native.v1"
MAX_COLUMNS = 128
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
TOTAL_SECONDS = 12
PREFLIGHT_SCALAR_SLACK = 64
_COLUMN = re.compile(r"[a-z][a-z0-9_]{0,95}")
# Match existing remote_erp exporter policy; parity tests prevent silent drift.
_FORBIDDEN = ("password", "secret", "token", "credential", "authorization", "api_key",
              "private_key", "cookie", "webhook", "cost", "price", "amount", "value_eur")
_EXCLUDED = {"work_activities": {"cost_eur"}}
_VIEWS = frozenset({"v_open_work", "ro_lab_decision_queue"})
_CLOCKS = frozenset({"tasks", "work_activities", "lab_reviews"})


@dataclass(frozen=True)
class SourceBoundary:
    estate_id: str
    db_host: str = "core-mariadb"
    db_port: int = 3306
    db_name: str = "baiamonte_vineyard"


@dataclass(frozen=True)
class CapturedDataset:
    snapshot: PreparedSnapshotInput
    evidence: SnapshotEvidence
    token_scheme: str = TOKEN_SCHEME


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return value


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=_json_value, allow_nan=False)


def _reporting_token(data: dict[str, Any], canonical: str) -> int:
    revision = data.get("revision")
    # The exporter accepts bool as int; the adapter refuses that ambiguous input.
    if isinstance(revision, bool):
        raise SourceUnavailable("ambiguous native revision")
    if isinstance(revision, int) and revision >= 0:
        return revision
    return int.from_bytes(hashlib.sha256(canonical.encode()).digest()[:8], "big") >> 1


def view_definition_fingerprint(name: str, definition: Mapping[str, Any]) -> str:
    """Pin reviewed exact view SQL/semantics metadata; never expose the SQL."""
    keys = {"view_definition", "check_option", "security_type"}
    if name not in _VIEWS or not isinstance(definition, Mapping) or set(definition) != keys or any(
        not isinstance(definition[key], str) or not definition[key] or len(definition[key].encode()) > 65536
        for key in keys
    ):
        raise SourceUnavailable("view definition unavailable")
    return hashlib.sha256(_canonical({"scheme": "baiamonte.reviewed-view.v1", "object": name, **definition}).encode()).hexdigest()


def _preflight_sql(name: str, columns: list[str], identity: str) -> str:
    """Conservative canonical-byte bound, not a driver/RSS memory guarantee.

    JSON escaping needs at most six bytes per source octet. Per-field slack
    covers quotes, keys, separators, nulls and scalar representation differences.
    LIMIT remains inside the derived table: never scan/export an unbounded set
    to pretend a truncated page is a complete generation.
    """
    overhead = 128 + sum(len(_canonical({column: None}).encode()) + PREFLIGHT_SCALAR_SLACK for column in columns)
    octets = "+".join(f"COALESCE(OCTET_LENGTH(`{column}`),0)" for column in columns)
    return ("SELECT COUNT(*) AS row_count,COALESCE(SUM(row_bytes),0) AS capture_bytes FROM "
            f"(SELECT {overhead}+6*({octets}) AS row_bytes FROM `{name}` "
            f"WHERE estate_id=%s ORDER BY `{identity}` LIMIT 2001) AS bounded_capture")


def _bounded_integer(value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise SourceUnavailable("source preflight unavailable")
    if isinstance(value, Decimal) and (not value.is_finite() or value != value.to_integral_value()):
        raise SourceUnavailable("source preflight unavailable")
    if not 0 <= value <= maximum:
        raise SourceUnavailable("complete source bound exceeded")
    return int(value)


def reporting_columns_fingerprint(name: str, columns: list[str]) -> str:
    """Bind a reviewed permitted-column set; this is not an access credential."""
    if (name not in {spec[0] for spec in DATASETS.values()} - _VIEWS or not columns
            or len(columns) > MAX_COLUMNS or len(set(columns)) != len(columns)
            or any(not isinstance(column, str) or _COLUMN.fullmatch(column) is None for column in columns)):
        raise SourceUnavailable("reporting column contract unavailable")
    return hashlib.sha256(_canonical({"scheme": "baiamonte.reporting-columns.v1", "object": name, "columns": sorted(columns)}).encode()).hexdigest()


def capture_dataset(
    *, boundary: SourceBoundary, view: str, dataset: str,
    connection_factory: Callable[[], Any], clock: Callable[[], datetime],
    reviewed_column_fingerprints: Mapping[str, str] = MappingProxyType({}),
    reviewed_view_fingerprints: Mapping[str, str] = MappingProxyType({}),
    source_datetime_timezone: timezone | None = None,
    reporting_token_reference: Callable[[Mapping[str, Any]], int] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> CapturedDataset:
    """Capture a complete bounded dataset in one rollback-only transaction.

    Callers are trusted future server code, not HTTP parameters/authentication.
    Every future HTTP page must authorize its principal before invoking this.
    No live capability, connector, view attestation or timezone is supplied here.
    Unknown source clocks remain null. Snapshot creation/retrieval clocks do not
    become item clocks, and are excluded from stable pagination generations.
    """
    if not isinstance(boundary, SourceBoundary) or (boundary.db_host, boundary.db_port, boundary.db_name) != ("core-mariadb", 3306, "baiamonte_vineyard"):
        raise SourceUnavailable("database boundary unavailable")
    try:
        if str(UUID(boundary.estate_id)) != boundary.estate_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SourceUnavailable("estate boundary unavailable") from None
    if not isinstance(view, str) or not isinstance(dataset, str) or (view, dataset) not in DATASETS:
        raise ValueError("invalid dataset")
    name, fields = DATASETS[view, dataset]
    # A view fingerprint proves neither dependency engines nor estate joins.
    # No live/supplied fingerprint can bypass this explicit source-only hold.
    if name in _VIEWS:
        raise SourceUnavailable("view dependencies not qualified")
    # No historical UTC writer contract is supplied here. Even an explicit UTC
    # parameter must not reinterpret historical naive DATETIME values.
    if source_datetime_timezone is not None:
        raise SourceUnavailable("source clock reinterpretation unavailable")
    expected_columns = reviewed_column_fingerprints.get(name) if isinstance(reviewed_column_fingerprints, Mapping) else None
    if not isinstance(expected_columns, str) or re.fullmatch(r"[0-9a-f]{64}", expected_columns) is None:
        raise SourceUnavailable("source column authority not qualified")
    started = monotonic()
    captured_at = _utc(clock())
    if captured_at is None:
        raise SourceUnavailable("capture clock unavailable")
    connection = None
    try:
        connection = connection_factory()
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            if cursor.fetchone() != {"database_name": boundary.db_name}:
                raise SourceUnavailable("database boundary unavailable")
            cursor.execute("SET SESSION max_statement_time=2")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            transaction_at = _utc(clock())
            if transaction_at is None or transaction_at < captured_at:
                raise SourceUnavailable("capture clock unavailable")
            captured_at = transaction_at
            metadata_sql = (
                "SELECT c.column_name AS column_name,t.table_type AS table_type,t.engine AS engine FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema=c.table_schema AND t.table_name=c.table_name "
                "WHERE c.table_schema=DATABASE() AND c.table_name=%s ORDER BY c.ordinal_position LIMIT 129"
            )
            cursor.execute(metadata_sql, (name,))
            metadata = cursor.fetchall()
            if not metadata or len(metadata) > MAX_COLUMNS or any(row.get("table_type") != "BASE TABLE" or row.get("engine") != "InnoDB" for row in metadata):
                raise SourceUnavailable("source schema unavailable")
            columns = [row.get("column_name") for row in metadata]
            if any(not isinstance(column, str) or _COLUMN.fullmatch(column) is None for column in columns) or len(set(columns)) != len(columns):
                raise SourceUnavailable("source columns unavailable")
            selected = [column for column in columns if column not in _EXCLUDED.get(name, set()) and not any(part in column.casefold() for part in _FORBIDDEN)]
            if reporting_columns_fingerprint(name, selected) != expected_columns:
                raise SourceUnavailable("reviewed reporting columns changed")
            identity = "sample_id" if name == "ro_lab_decision_queue" else "id"
            required = {"estate_id", identity, *fields, *({"updated_at"} if name in _CLOCKS else set())}
            if not required.issubset(selected):
                raise SourceUnavailable("required source fields unavailable")
            if monotonic() - started >= TOTAL_SECONDS:
                raise SourceUnavailable("capture budget exceeded")
            cursor.execute(_preflight_sql(name, selected, identity), (boundary.estate_id,))
            preflight = cursor.fetchone()
            if not isinstance(preflight, dict) or set(preflight) != {"row_count", "capture_bytes"}:
                raise SourceUnavailable("source preflight unavailable")
            expected_count = _bounded_integer(preflight["row_count"], MAX_INPUT_ROWS)
            _bounded_integer(preflight["capture_bytes"], MAX_CAPTURE_BYTES)
            # The first source SELECT acquires a metadata lock. Revalidate the
            # entire selected schema/engine before payload fetch, catching DDL
            # that raced the initial schema lookup. Live MDL/engine behavior is
            # still a separate real-DB qualification gate, not proved by fakes.
            cursor.execute(metadata_sql, (name,))
            if cursor.fetchall() != metadata:
                raise SourceUnavailable("source schema changed during capture")
            if monotonic() - started >= TOTAL_SECONDS:
                raise SourceUnavailable("capture budget exceeded")
            cursor.execute("SELECT " + ",".join(f"`{column}`" for column in selected) +
                           f" FROM `{name}` WHERE estate_id=%s ORDER BY `{identity}` LIMIT 2001", (boundary.estate_id,))
            rows = cursor.fetchall()
            if len(rows) != expected_count or len(rows) > MAX_INPUT_ROWS:
                raise SourceUnavailable("source count changed during capture")
            records, byte_count = [], 0
            for row in rows:
                if not isinstance(row, dict) or set(row) != set(selected) or row.get("estate_id") != boundary.estate_id:
                    raise SourceUnavailable("source row boundary unavailable")
                data = {key: _json_value(value) for key, value in row.items()}
                canonical = _canonical(data)
                byte_count += len(canonical.encode())
                if byte_count > MAX_CAPTURE_BYTES or monotonic() - started >= TOTAL_SECONDS:
                    raise SourceUnavailable("capture budget exceeded")
                updated = row.get("updated_at") if name in _CLOCKS else None
                # Unknown naive/date-only clocks are never interpreted as UTC.
                updated = _utc(updated) if isinstance(updated, datetime) else None
                if updated is not None and updated > captured_at:
                    updated = None
                revision = _reporting_token(data, canonical)
                if reporting_token_reference is not None:
                    reference = reporting_token_reference(MappingProxyType(data))
                    if isinstance(reference, bool) or not isinstance(reference, int) or reference != revision:
                        raise SourceUnavailable("authoritative reporting token mismatch")
                # Do not retain full reporting-only fields after token creation.
                minimized = {key: data[key] for key in {"estate_id", identity, *fields} if key in data}
                records.append({"object": name, "id": row.get(identity),
                                "revision": str(revision),
                                "source_updated_at": updated, "data": minimized})
            snapshot = prepare_snapshot_input(records, estate_id=boundary.estate_id, view=view, dataset=dataset)
    except SourceUnavailable:
        raise
    except Exception:
        # No driver exception text, SQL, parameters, rows or credentials escape.
        raise SourceUnavailable("source capture unavailable") from None
    finally:
        if connection is not None:
            cleanup_failed = False
            try:
                connection.rollback()
            except Exception:
                cleanup_failed = True
            finally:
                try:
                    connection.close()
                except Exception:
                    cleanup_failed = True
            if cleanup_failed:
                raise SourceUnavailable("source cleanup unavailable") from None
    finished_at = _utc(clock())
    if finished_at is None or finished_at < captured_at or monotonic() - started >= TOTAL_SECONDS:
        raise SourceUnavailable("capture clock or budget unavailable")
    return CapturedDataset(snapshot, SnapshotEvidence(
        before=snapshot.generation, after=snapshot.generation,
        permitted_objects=frozenset({name}), source_generated_at=captured_at,
        last_success_at=finished_at, degraded=True,
    ))
