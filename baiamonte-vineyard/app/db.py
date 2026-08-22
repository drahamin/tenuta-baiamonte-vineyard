from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Full, LifoQueue
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection

from .config import get_settings
from .sql_migrations import split_sql_statements


# Reuse a bounded set of healthy connections. A dashboard refresh reads many
# independent sections, and reconnecting for every section was the dominant
# cold-refresh cost. Each leased connection is used by one thread at a time.
_CONNECTION_POOL_SIZE = 8
_connection_pool: LifoQueue[Connection] = LifoQueue(maxsize=_CONNECTION_POOL_SIZE)


def connect(database: str | None = None) -> Connection:
    settings = get_settings()
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=database if database is not None else settings.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


def _acquire_connection() -> Connection:
    while True:
        try:
            connection = _connection_pool.get_nowait()
        except Empty:
            return connect()
        try:
            connection.ping(reconnect=True)
            return connection
        except Exception:
            try:
                connection.close()
            except Exception:
                pass


def _release_connection(connection: Connection, *, reusable: bool) -> None:
    if reusable:
        try:
            _connection_pool.put_nowait(connection)
            return
        except Full:
            pass
    try:
        connection.close()
    except Exception:
        pass


def close_connection_pool() -> None:
    """Close idle connections during shutdown and isolated test runs."""
    while True:
        try:
            connection = _connection_pool.get_nowait()
        except Empty:
            return
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


def run_migrations() -> list[str]:
    applied: list[str] = []
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
            for path in migration_files():
                if path.name in existing:
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
