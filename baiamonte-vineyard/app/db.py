from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection

from .config import get_settings
from .sql_migrations import split_sql_statements


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


@contextmanager
def transaction() -> Iterator[tuple[Connection, Any]]:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            yield connection, cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
    with transaction() as (_, cursor):
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
            for statement in statements:
                cursor.execute(statement)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied
