"""Unregistered battery/history read projection. No SQL, HA calls or controls.

Input must come from the already-permitted reporting view in one consistent
read. This module neither obtains credentials nor widens an existing route.
The default evidence gates are closed: schema, sign and observation-clock
semantics need independent verification before a future adapter can use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any, Mapping, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo


CONTRACT = "baiamonte.mobile-telemetry.v1"
SOURCE_OBJECT = "ro_estate_energy_observations"
POWER_SIGN = "positive_discharge_negative_charge"
UNITS = {"pv_power_w": "W", "estate_load_w": "W", "battery_soc_pct": "%",
         "battery_power_w": "W", "forecast_remaining_kwh": "kWh"}
FIELDS = tuple(UNITS)
REQUIRED_COLUMNS = frozenset({"estate_id", "observed_at"})
PROJECTED_COLUMNS = REQUIRED_COLUMNS | frozenset(FIELDS)
MAX_INPUT_ROWS = 20_000
FRESH_SECONDS = 900


class EnergyProjectionForbidden(ValueError):
    """A future adapter must preserve the current direct-site admin-only gate."""


class EnergySnapshotChanged(ValueError):
    code = "mobile_read_snapshot_changed"


@dataclass(frozen=True)
class EnergyReadEvidence:
    # These are NOT feature switches or credentials. A future reviewed reader
    # supplies verified provenance; unchecked defaults yield unavailable.
    schema_columns: frozenset[str] = frozenset()
    observation_clock_verified: bool = False
    power_sign_verified: bool = False
    naive_timestamp_timezone: str | None = None
    source_generated_at: Any = None
    last_success_at: Any = None
    snapshot_before: str | None = None
    snapshot_after: str | None = None
    # Stored source is remaining SOLAR forecast, never stored battery energy.
    # Keep nullable until a reviewed consumer labels that meaning explicitly.
    forecast_semantics_verified: bool = False


def _estate(value: str) -> str:
    try:
        canonical = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("invalid estate boundary") from error
    if value != canonical:
        raise ValueError("estate boundary must be canonical")
    return canonical


def _time(value: Any, naive_zone: str | None = None) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        if not naive_zone:
            return None
        try:
            zone = ZoneInfo(naive_zone)
        except (KeyError, ValueError):
            return None
        try:
            first, second = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
            if first.utcoffset() != second.utcoffset():
                return None  # Ambiguous or nonexistent DST wall time is not guessed.
            if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != parsed:
                return None
        except (ValueError, OverflowError):
            return None
        parsed = first
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _number(value: Any, field: str) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        return None
    if isinstance(value, str) and (not value.strip() or len(value) > 64):
        return None
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite():
            return None
        result = float(number)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    if not math.isfinite(result):
        return None
    if field == "battery_soc_pct" and not 0 <= result <= 100:
        return None
    if field != "battery_power_w" and result < 0:
        return None
    return result


def _point_quality(point: Mapping[str, Any]) -> str:
    count = sum(point.get(field) is not None for field in FIELDS)
    return "unavailable" if count == 0 else "observed" if count == len(FIELDS) else "partial"


def _aggregate(points: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    result = []
    for bucket in range(limit):
        group = points[bucket * len(points) // limit:(bucket + 1) * len(points) // limit]
        point = {"observed_at": group[-1]["observed_at"]}
        for field in FIELDS:
            values = [row[field] for row in group]
            # A gap anywhere in a bucket remains a chart gap, never interpolation.
            point[field] = None if any(value is None for value in values) else math.fsum(value / len(values) for value in values)
        point["quality"] = _point_quality(point)
        result.append(point)
    return result


def project_energy_read(
    records: Sequence[Mapping[str, Any]], *, estate_id: str, role: str,
    capabilities: frozenset[str], now: datetime, range_value: str = "24h",
    evidence: EnergyReadEvidence = EnergyReadEvidence(),
) -> dict[str, Any]:
    """Build the native metrics/series DTO, without registering an endpoint.

    Identity/role/capabilities must be server-validated by a future adapter.
    Passing a caller-supplied role to this function is not authentication.
    Existing direct-site role policy permits energy only for admin: the ERP's
    separate operator role must not accidentally widen that policy.
    """
    if role != "admin" or "energy" not in capabilities:
        raise EnergyProjectionForbidden("energy read is not permitted")
    estate = _estate(estate_id)
    if range_value not in {"24h", "7d"}:
        raise ValueError("unsupported energy range")
    clock = _time(now)
    if clock is None:
        raise ValueError("an aware current clock is required")
    if len(records) > MAX_INPUT_ROWS:
        raise ValueError("energy input exceeds bounded read")
    if (evidence.snapshot_before is not None or evidence.snapshot_after is not None) and (
        not evidence.snapshot_before or evidence.snapshot_before != evidence.snapshot_after
    ):
        raise EnergySnapshotChanged(EnergySnapshotChanged.code)

    generated = _time(evidence.source_generated_at, evidence.naive_timestamp_timezone)
    success = _time(evidence.last_success_at, evidence.naive_timestamp_timezone)
    source_age = int((clock - generated).total_seconds()) if generated is not None and generated <= clock else None
    source = {"source_generated_at": _iso(generated) if source_age is not None else None,
              "last_success_at": _iso(success) if success is not None and success <= clock else None,
              "data_age_seconds": source_age, "state": "unavailable"}
    result = {"ok": True, "contract": CONTRACT, "estate_id": estate, "range": range_value,
              "available": False, "source": source, "data_age_seconds": None,
              "metrics": {field: {"value": None, "unit": unit, "observed_at": None, "quality": "unavailable"} for field, unit in UNITS.items()},
              "series": {"units": dict(UNITS), "points": []}, "battery_power_sign": POWER_SIGN}
    for gate, valid in (
        ("reporting_schema_unverified", REQUIRED_COLUMNS <= evidence.schema_columns and bool(frozenset(FIELDS) & evidence.schema_columns)),
        ("observation_clock_unverified", evidence.observation_clock_verified is True),
        ("battery_sign_unverified", evidence.power_sign_verified is True),
    ):
        if not valid:
            result["unavailable_reason"] = gate
            return result

    cutoff = clock - timedelta(days=1 if range_value == "24h" else 7)
    by_time: dict[datetime, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping) or record.get("object") != SOURCE_OBJECT:
            continue
        row = record.get("data")
        if not isinstance(row, Mapping) or row.get("estate_id") != estate:
            continue
        observed = _time(row.get("observed_at"), evidence.naive_timestamp_timezone)
        if observed is None or not cutoff <= observed <= clock:
            continue
        values = {field: _number(row.get(field), field) if field in evidence.schema_columns else None for field in FIELDS}
        if evidence.forecast_semantics_verified is not True:
            values["forecast_remaining_kwh"] = None
        if observed in by_time:
            # Conflicting equal-time observations are unknown, not last-write-wins.
            for field in FIELDS:
                if by_time[observed][field] != values[field]:
                    by_time[observed][field] = None
        else:
            by_time[observed] = {"observed_at": _iso(observed), **values}
    times = sorted(by_time)
    points = [{**by_time[at], "quality": _point_quality(by_time[at])} for at in times]
    result["series"]["points"] = _aggregate(points, 289 if range_value == "24h" else 337)
    if not times:
        return result
    latest = by_time[times[-1]]
    age = int((clock - times[-1]).total_seconds())
    result["data_age_seconds"] = age
    result["available"] = any(latest[field] is not None for field in FIELDS)
    current = (age <= FRESH_SECONDS and source_age is not None and source_age <= FRESH_SECONDS
               and success is not None and success <= clock and (clock - success).total_seconds() <= FRESH_SECONDS)
    state = "current" if current else "stale"
    source["state"] = state if result["available"] else "unavailable"
    result["metrics"] = {field: {"value": latest[field], "unit": unit,
                               "observed_at": latest["observed_at"] if latest[field] is not None else None,
                               "quality": state if latest[field] is not None else "unavailable"} for field, unit in UNITS.items()}
    return result
