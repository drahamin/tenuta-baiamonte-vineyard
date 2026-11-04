"""Opt-in exact current cellar assignments. No inferred observation history."""
from __future__ import annotations

from decimal import Decimal
import math
from typing import Any, Mapping
from uuid import UUID

from ..db import fetch_all
from .mobile_reporting_reads import ReportingSourceUnavailable

CONTRACT = "baiamonte.mobile-cellar.v1"
PROJECTION = "cellar-links-v1"
MAX_ROWS = 1000
MAX_CONTAINERS = 100
OBSERVATION_STATUS = "unavailable_container_observation_provenance_unverified"


def _id(value: Any) -> str:
    try:
        valid = isinstance(value, str) and str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ReportingSourceUnavailable("invalid cellar source identity")
    return value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ReportingSourceUnavailable("invalid cellar source number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ReportingSourceUnavailable("invalid cellar source number")
    return number


def project_cellar_links(rows: list[Mapping[str, Any]], estate: str) -> list[dict[str, Any]]:
    """Project one bounded SQL snapshot, rejecting conflicting/cross-estate rows."""
    _id(estate)
    if len(rows) > MAX_ROWS:
        raise ReportingSourceUnavailable("cellar source exceeds read boundary")
    containers: dict[str, dict[str, Any]] = {}
    lots_seen: set[str] = set()
    for row in rows:
        if row.get("container_estate_id") != estate:
            raise ReportingSourceUnavailable("cellar source estate mismatch")
        container_id = _id(row.get("container_id"))
        container = {
            "id": container_id, "code": row.get("container_code"), "name": row.get("container_name"),
            "container_type": row.get("container_type"), "material": row.get("material"),
            "capacity_l": _number(row.get("capacity_l")), "location": row.get("location"),
            "status": row.get("container_status"),
        }
        if container_id not in containers:
            containers[container_id] = {**container, "wine_lots": []}
        elif any(containers[container_id][key] != value for key, value in container.items()):
            raise ReportingSourceUnavailable("conflicting cellar container identity")
        lot_id = row.get("wine_lot_id")
        if lot_id is None:
            if containers[container_id]["wine_lots"]:
                raise ReportingSourceUnavailable("conflicting cellar assignment")
            continue
        _id(lot_id)
        if (row.get("lot_estate_id") != estate or row.get("season_estate_id") != estate
                or row.get("current_container_id") != container_id or lot_id in lots_seen):
            raise ReportingSourceUnavailable("invalid cellar assignment boundary")
        year = row.get("vintage_year")
        if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2200:
            raise ReportingSourceUnavailable("invalid cellar vintage")
        lots_seen.add(lot_id)
        containers[container_id]["wine_lots"].append({
            "id": lot_id, "code": row.get("wine_lot_code"), "name": row.get("wine_lot_name"),
            "vintage_year": year, "stage": row.get("stage"), "variety_summary": row.get("variety_summary"),
            "reported_volume_l": _number(row.get("volume_l")),
        })
    if len(containers) > MAX_CONTAINERS:
        raise ReportingSourceUnavailable("cellar source exceeds container boundary")
    for container in containers.values():
        count = len(container["wine_lots"])
        container["link_status"] = "unassigned" if count == 0 else "single" if count == 1 else "multiple"
        container["observations"] = []
        container["observation_status"] = OBSERVATION_STATUS
    return list(containers.values())


def read_cellar_links(estate: str) -> list[dict[str, Any]]:
    _id(estate)
    # One statement is one consistent snapshot. Preserve all current vintages
    # and every exact link; never pick MIN(id), match names or sum lot volumes.
    rows = fetch_all(
        "SELECT c.id container_id,c.estate_id container_estate_id,c.code container_code,c.name container_name,"
        "c.container_type,c.material,c.capacity_l,c.location,c.status container_status,"
        "w.id wine_lot_id,w.estate_id lot_estate_id,w.current_container_id,w.code wine_lot_code,w.name wine_lot_name,"
        "w.stage,w.variety_summary,w.volume_l,s.estate_id season_estate_id,s.vintage_year "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.estate_id=c.estate_id "
        "LEFT JOIN seasons s ON s.id=w.season_id AND s.estate_id=w.estate_id "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code,c.id,w.id LIMIT %s",
        (estate, MAX_ROWS + 1),
    )
    return project_cellar_links(rows, estate)
