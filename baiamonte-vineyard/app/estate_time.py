"""Calendar helpers for the estate's operational year."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import get_settings


DEFAULT_ESTATE_TIME_ZONE = "Europe/Rome"


def estate_now(now: datetime | None = None) -> datetime:
    """Return a timezone-aware clock for the vineyard, independent of host time."""
    time_zone = get_settings().tv_time_zone or DEFAULT_ESTATE_TIME_ZONE
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_ESTATE_TIME_ZONE)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def estate_today(now: datetime | None = None) -> date:
    return estate_now(now).date()


def estate_year(now: datetime | None = None) -> int:
    return estate_today(now).year
