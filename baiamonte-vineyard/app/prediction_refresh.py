"""Durable invalidation for predictions derived from changing field evidence."""

from __future__ import annotations

import json
from typing import Any

from .db import fetch_all, fetch_one, transaction
from .service import estate_id


INTEGRATION_NAME = "harvest-prediction-refresh"


def request_harvest_refresh(source_type: str, source_id: str, reason: str) -> int:
    """Queue one durable refresh request without losing writes during a run."""
    payload = json.dumps({"source_type": source_type, "source_id": source_id, "reason": reason})
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,%s,'inbound','source_changed',%s,'received',%s)",
            (estate_id(), INTEGRATION_NAME, str(source_id)[:190], payload),
        )
        event_id = int(cursor.lastrowid)
    return event_id


def harvest_refresh_pending() -> bool:
    row = fetch_one(
        "SELECT COUNT(*) n FROM integration_events WHERE estate_id=%s AND integration_name=%s "
        "AND event_type='source_changed' AND status='received'",
        (estate_id(), INTEGRATION_NAME),
    ) or {}
    return int(row.get("n") or 0) > 0


def pending_harvest_refresh_ids() -> list[int]:
    return [
        int(row["id"])
        for row in fetch_all(
            "SELECT id FROM integration_events WHERE estate_id=%s AND integration_name=%s "
            "AND event_type='source_changed' AND status='received' ORDER BY occurred_at",
            (estate_id(), INTEGRATION_NAME),
        )
    ]


def complete_harvest_refreshes(event_ids: list[int]) -> None:
    if not event_ids:
        return
    placeholders = ",".join(["%s"] * len(event_ids))
    with transaction() as (_, cursor):
        cursor.execute(
            f"UPDATE integration_events SET status='processed',error_message=NULL WHERE estate_id=%s AND id IN ({placeholders})",
            (estate_id(), *event_ids),
        )
