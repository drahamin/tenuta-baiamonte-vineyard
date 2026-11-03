"""Explicit, unregistered on-HA connection factory; never loads credentials.

Future authenticated server code supplies its existing app settings. No global
settings lookup, default connector, new principal, grant, pool or route exists.
"""
from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

import pymysql

from ..db import ProfilingDictCursor
from .mobile_work_review_source import SourceBoundary, SourceUnavailable


def make_connection_factory(settings: Any, boundary: SourceBoundary) -> Callable[[], Any]:
    if (not isinstance(boundary, SourceBoundary)
            or (boundary.db_host, boundary.db_port, boundary.db_name) != ("core-mariadb", 3306, "baiamonte_vineyard")
            or (settings.db_host, settings.db_port, settings.db_name) != (boundary.db_host, boundary.db_port, boundary.db_name)):
        raise SourceUnavailable("source connection boundary unavailable")
    try:
        valid_estate = isinstance(boundary.estate_id, str) and str(UUID(boundary.estate_id)) == boundary.estate_id
    except (ValueError, TypeError, AttributeError):
        valid_estate = False
    if not valid_estate or settings.estate_id != boundary.estate_id:
        raise SourceUnavailable("source estate boundary unavailable")
    user, password = settings.db_user, settings.db_password
    if not isinstance(user, str) or not user or len(user) > 96 or not isinstance(password, str) or len(password) > 4096:
        raise SourceUnavailable("source credential settings unavailable")

    def connect():
        # New dedicated connection, never a pooled app-write lease. Secrets stay
        # only in the existing HA app process and are never returned or logged.
        return pymysql.connect(host=boundary.db_host, port=boundary.db_port, database=boundary.db_name,
                               user=user, password=password, charset="utf8mb4", cursorclass=ProfilingDictCursor,
                               autocommit=False, connect_timeout=3, read_timeout=3, write_timeout=3)
    return connect
