"""In-memory truth for work that is actively running in this app process."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any


_lock = threading.Lock()
_active: dict[str, dict[str, Any]] = {}


def begin_process(integration_name: str, *, code: str | None = None, timeout_seconds: int = 180) -> bool:
    """Register a process once. False means the same integration is still active."""
    now = datetime.now(timezone.utc)
    with _lock:
        if integration_name in _active:
            return False
        _active[integration_name] = {
            "integration_name": integration_name,
            "code": code or integration_name,
            "state": "running",
            "started_at": now,
            "deadline_at": now + timedelta(seconds=timeout_seconds),
            "timeout_seconds": timeout_seconds,
            "error": None,
        }
    return True


def mark_process_timed_out(integration_name: str, message: str) -> None:
    """Keep a timed-out thread visible until it actually exits."""
    with _lock:
        item = _active.get(integration_name)
        if item:
            item["state"] = "timed_out"
            item["timed_out_at"] = datetime.now(timezone.utc)
            item["error"] = message


def finish_process(integration_name: str) -> None:
    with _lock:
        _active.pop(integration_name, None)


def processing_runtime_snapshot() -> dict[str, Any]:
    with _lock:
        jobs = [dict(item) for item in _active.values()]
    jobs.sort(key=lambda item: item["started_at"])
    return {
        "active": bool(jobs),
        "active_count": len(jobs),
        "timed_out_count": sum(item["state"] == "timed_out" for item in jobs),
        "jobs": jobs,
    }
