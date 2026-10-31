from contextlib import contextmanager
from contextvars import ContextVar, Token
from collections import deque
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
from queue import Empty, Full, LifoQueue
import re
import threading
import time
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection

from .config import get_settings
from .sql_migrations import split_sql_statements


logger = logging.getLogger("baiamonte.database")


# Every query is attributed to the request or background process which caused
# it. Context variables are copied into FastAPI's worker threads by AnyIO, so
# synchronous endpoints retain their caller without passing labels through the
# entire domain layer.
_query_context: ContextVar[str] = ContextVar("baiamonte_query_context", default="background")
_slow_query_seconds = max(0.01, float(os.environ.get("DB_SLOW_QUERY_MS", "250")) / 1000.0)
_profile_lock = threading.Lock()
_endpoint_profiles: dict[str, dict[str, Any]] = {}
_query_profiles: dict[str, dict[str, Any]] = {}
_recent_slow_queries: deque[dict[str, Any]] = deque(maxlen=50)
_MAX_ENDPOINT_PROFILES = 128
_MAX_QUERY_PROFILES = 256


def set_query_context(value: str) -> Token[str]:
    return _query_context.set(str(value or "background")[:180])


def reset_query_context(token: Token[str]) -> None:
    _query_context.reset(token)


def _query_identity(sql: str) -> tuple[str, str, str]:
    normalized = " ".join(str(sql or "").split())
    normalized = re.sub(r"'(?:''|[^'])*'", "'?'", normalized)
    normalized = re.sub(r'"(?:""|[^"])*"', '"?"', normalized)
    normalized = re.sub(r"\b(?:0x[0-9a-f]+|\d+(?:\.\d+)?)\b", "?", normalized, flags=re.IGNORECASE)
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    operation = (normalized.split(" ", 1)[0] if normalized else "UNKNOWN").upper()
    tables = []
    for match in re.finditer(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+`?([a-zA-Z0-9_]+)", normalized, re.IGNORECASE):
        table = match.group(1)
        if table not in tables:
            tables.append(table)
    label = f"{operation} {'+'.join(tables[:4])}".strip()
    return fingerprint, label, normalized[:240]


def _bounded_profile(profiles: dict[str, dict[str, Any]], key: str, seed: dict[str, Any], maximum: int) -> dict[str, Any]:
    profile = profiles.get(key)
    if profile is not None:
        return profile
    if len(profiles) >= maximum:
        oldest = min(profiles, key=lambda item: str(profiles[item].get("last_seen_at") or ""))
        profiles.pop(oldest, None)
    profiles[key] = seed
    return profiles[key]


def _record_query(sql: str, elapsed_seconds: float, *, succeeded: bool) -> None:
    endpoint = _query_context.get()
    fingerprint, label, normalized = _query_identity(sql)
    duration_ms = round(elapsed_seconds * 1000, 3)
    observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    slow = elapsed_seconds >= _slow_query_seconds
    with _profile_lock:
        endpoint_profile = _bounded_profile(
            _endpoint_profiles,
            endpoint,
            {"endpoint": endpoint, "query_count": 0, "failed_query_count": 0, "slow_query_count": 0,
             "query_seconds": 0.0, "max_query_ms": 0.0, "last_seen_at": observed_at},
            _MAX_ENDPOINT_PROFILES,
        )
        endpoint_profile["query_count"] += 1
        endpoint_profile["failed_query_count"] += 0 if succeeded else 1
        endpoint_profile["slow_query_count"] += 1 if slow else 0
        endpoint_profile["query_seconds"] = round(float(endpoint_profile["query_seconds"]) + elapsed_seconds, 6)
        endpoint_profile["max_query_ms"] = max(float(endpoint_profile["max_query_ms"]), duration_ms)
        endpoint_profile["last_seen_at"] = observed_at

        query_key = f"{endpoint}:{fingerprint}"
        query_profile = _bounded_profile(
            _query_profiles,
            query_key,
            {"endpoint": endpoint, "fingerprint": fingerprint, "label": label, "statement": normalized,
             "query_count": 0, "failed_query_count": 0, "slow_query_count": 0,
             "total_ms": 0.0, "max_ms": 0.0, "last_seen_at": observed_at},
            _MAX_QUERY_PROFILES,
        )
        query_profile["query_count"] += 1
        query_profile["failed_query_count"] += 0 if succeeded else 1
        query_profile["slow_query_count"] += 1 if slow else 0
        query_profile["total_ms"] = round(float(query_profile["total_ms"]) + duration_ms, 3)
        query_profile["max_ms"] = max(float(query_profile["max_ms"]), duration_ms)
        query_profile["last_seen_at"] = observed_at
        if slow:
            _recent_slow_queries.append({
                "endpoint": endpoint, "fingerprint": fingerprint, "label": label,
                "duration_ms": duration_ms, "succeeded": succeeded, "observed_at": observed_at,
            })
    if slow:
        logger.warning(
            "Slow database query endpoint=%s query=%s label=%s duration_ms=%.3f succeeded=%s",
            endpoint, fingerprint, label, duration_ms, succeeded,
        )


def database_profile_snapshot() -> dict[str, Any]:
    """Return bounded, parameter-free query diagnostics for administrators."""
    with _profile_lock:
        endpoints = [dict(item) for item in _endpoint_profiles.values()]
        queries = [dict(item) for item in _query_profiles.values()]
        recent = [dict(item) for item in _recent_slow_queries]
    for item in endpoints:
        count = max(1, int(item["query_count"]))
        item["average_query_ms"] = round(float(item["query_seconds"]) * 1000 / count, 3)
    for item in queries:
        count = max(1, int(item["query_count"]))
        item["average_ms"] = round(float(item["total_ms"]) / count, 3)
    return {
        "slow_query_threshold_ms": round(_slow_query_seconds * 1000, 3),
        "endpoints": sorted(endpoints, key=lambda item: (-float(item["query_seconds"]), item["endpoint"])),
        "queries": sorted(queries, key=lambda item: (-float(item["max_ms"]), item["endpoint"]))[:100],
        "recent_slow_queries": list(reversed(recent)),
        "pool": {"capacity": _CONNECTION_POOL_SIZE, "idle": _connection_pool.qsize()},
    }


class ProfilingDictCursor(pymysql.cursors.DictCursor):
    def execute(self, query: str, args: Any = None) -> int:
        started = time.perf_counter()
        succeeded = False
        try:
            result = super().execute(query, args)
            succeeded = True
            return result
        finally:
            _record_query(query, time.perf_counter() - started, succeeded=succeeded)

    def executemany(self, query: str, args: Any) -> int:
        started = time.perf_counter()
        succeeded = False
        try:
            result = super().executemany(query, args)
            succeeded = True
            return result
        finally:
            _record_query(query, time.perf_counter() - started, succeeded=succeeded)


# Reuse a bounded set of healthy connections. A dashboard refresh reads many
# independent sections, and reconnecting for every section was the dominant
# cold-refresh cost. Each leased connection is used by one thread at a time.
_CONNECTION_POOL_SIZE = 8
_connection_pool: LifoQueue[Connection] = LifoQueue(maxsize=_CONNECTION_POOL_SIZE)
_connection_registry_lock = threading.Lock()
_leased_connections: dict[int, Connection] = {}
_shutdown_closed_connection_ids: set[int] = set()


def connect(database: str | None = None) -> Connection:
    settings = get_settings()
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=database if database is not None else settings.db_name,
        charset="utf8mb4",
        cursorclass=ProfilingDictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


def _acquire_connection() -> Connection:
    while True:
        with _connection_registry_lock:
            try:
                connection = _connection_pool.get_nowait()
            except Empty:
                connection = connect()
                _shutdown_closed_connection_ids.discard(id(connection))
                _leased_connections[id(connection)] = connection
                return connection
            try:
                connection.ping(reconnect=True)
                _shutdown_closed_connection_ids.discard(id(connection))
                _leased_connections[id(connection)] = connection
                return connection
            except Exception:
                try:
                    connection.close()
                except Exception:
                    pass


def _release_connection(connection: Connection, *, reusable: bool) -> None:
    returned_to_pool = False
    with _connection_registry_lock:
        _leased_connections.pop(id(connection), None)
        shutdown_closed = id(connection) in _shutdown_closed_connection_ids
        _shutdown_closed_connection_ids.discard(id(connection))
        if reusable and not shutdown_closed:
            try:
                _connection_pool.put_nowait(connection)
                returned_to_pool = True
            except Full:
                pass
    if returned_to_pool:
        return
    try:
        connection.close()
    except Exception:
        pass


def close_connection_pool() -> None:
    """Close every pooled connection, including a lease active at shutdown."""
    connections: dict[int, Connection] = {}
    with _connection_registry_lock:
        while True:
            try:
                connection = _connection_pool.get_nowait()
            except Empty:
                break
            connections[id(connection)] = connection
        connections.update(_leased_connections)
        _shutdown_closed_connection_ids.update(_leased_connections)
    for connection in connections.values():
        try:
            connection.close()
        except Exception:
            pass


@contextmanager
def transaction() -> Iterator[tuple[Connection, Any]]:
    connection = _acquire_connection()
    reusable = False
    try:
        with connection.cursor() as cursor:
            yield connection, cursor
        connection.commit()
        reusable = True
    except Exception:
        try:
            connection.rollback()
            reusable = True
        except Exception:
            reusable = False
        raise
    finally:
        _release_connection(connection, reusable=reusable)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with transaction() as (_, cursor):
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with transaction() as (_, cursor):
        cursor.execute(sql, params)
        return cursor.fetchone()


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with transaction() as (_, cursor):
        return cursor.execute(sql, params)


def migration_files() -> list[Path]:
    root = Path(__file__).resolve().parents[1] / "db" / "migrations"
    return sorted(root.glob("*.sql"))


def configured_migration_allowlist() -> frozenset[str] | None:
    raw = os.environ.get("BAIAMONTE_MIGRATION_ALLOWLIST")
    if raw is None:
        return None
    versions = frozenset(item.strip() for item in raw.split(",") if item.strip())
    if not versions:
        raise ValueError("BAIAMONTE_MIGRATION_ALLOWLIST must name at least one migration")
    invalid = sorted(
        version
        for version in versions
        if Path(version).name != version or not version.endswith(".sql")
    )
    if invalid:
        raise ValueError(f"Invalid migration allowlist entries: {', '.join(invalid)}")
    return versions


def run_migrations() -> list[str]:
    applied: list[str] = []
    paths = migration_files()
    allowlist = configured_migration_allowlist()
    if allowlist is not None:
        packaged = {path.name for path in paths}
        missing = sorted(allowlist - packaged)
        if missing:
            raise RuntimeError(f"Allowlisted migrations are missing from the image: {', '.join(missing)}")
    connection = connect()
    lock_acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,60) acquired", ("baiamonte_schema_migrations",))
            lock_acquired = bool((cursor.fetchone() or {}).get("acquired"))
            if not lock_acquired:
                raise TimeoutError("Could not acquire the Baiamonte schema-migration lock")
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(80) PRIMARY KEY, "
                "applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
            cursor.execute("SELECT version FROM schema_migrations")
            existing = {row["version"] for row in cursor.fetchall()}
            for path in paths:
                if path.name in existing:
                    continue
                if allowlist is not None and path.name not in allowlist:
                    continue
                statements = split_sql_statements(path.read_text(encoding="utf-8"))
                for statement_number, statement in enumerate(statements, start=1):
                    try:
                        cursor.execute(statement)
                    except Exception:
                        operation = " ".join(statement.strip().split())[:180]
                        print(
                            f"Database migration failed: {path.name} statement {statement_number}/{len(statements)}: {operation}",
                            flush=True,
                        )
                        raise
                cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
                applied.append(path.name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if lock_acquired:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", ("baiamonte_schema_migrations",))
                connection.commit()
            except Exception:
                connection.rollback()
        connection.close()
    return applied
