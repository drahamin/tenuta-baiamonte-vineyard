"""Exact-source read-only battery telemetry; no history collection or controls."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
from typing import Any, Callable, Mapping
import httpx

from ..ha_auth import home_assistant_token
from .mobile_energy_projection import (
    CONTRACT, POWER_SIGN, UNITS, EnergyProjectionForbidden, _estate, _iso, _number, _time,
)


SOURCES = {
    "battery_soc_pct": ("sensor.baiamonte_can_bank_soc",),
    "battery_power_w": ("sensor.baiamonte_can_bank_power",),
    "estate_load_w": ("sensor.wifi_din_rail_40a_main_power",),
    "pv_power_w": ("sensor.baiamonte_growatt_solar_input_power", "sensor.total_dc_input_power"),
}
ENTITIES = frozenset(entity for entities in SOURCES.values() for entity in entities)
MAX_SOURCE_AGE = 900
TOTAL_SOURCE_DEADLINE = 2.0
MAX_SOURCE_BYTES = 16_384


async def _read_sensor(entity: str, client: httpx.AsyncClient, token: str) -> Mapping[str, Any] | None:
    if entity not in ENTITIES:
        raise ValueError("unapproved energy source")
    async with client.stream(
        "GET",
        "http://supervisor/core/api/states/" + entity,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json", "Accept-Encoding": "identity"},
    ) as response:
        if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity":
            return None
        body = bytearray()
        async for chunk in response.aiter_raw():
            if len(body) + len(chunk) > MAX_SOURCE_BYTES:
                return None
            body.extend(chunk)
    value = json.loads(body)
    return value if isinstance(value, dict) else None


async def read_live_energy(
    *, estate_id: str, role: str, capabilities: frozenset[str], range_value: str = "24h",
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> dict[str, Any]:
    # Validate authorization and boundaries before credential lookup or I/O.
    empty = live_energy_read(estate_id=estate_id, role=role, capabilities=capabilities,
                             range_value=range_value, read_state=lambda _: None)
    token = home_assistant_token()
    if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
        return empty
    states: dict[str, Mapping[str, Any] | None] = {}
    factory = client_factory or httpx.AsyncClient
    try:
        # This is a total deadline across DNS/connect/headers/streaming body,
        # not a per-socket-operation timeout. Run on the existing ASGI loop;
        # never create/run/close a private loop that waits for DNS threads.
        async with asyncio.timeout(TOTAL_SOURCE_DEADLINE):
            async with factory(
                trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(2.0, connect=1.0),
                limits=httpx.Limits(max_connections=len(ENTITIES), max_keepalive_connections=0),
            ) as client:
                async def read(entity: str) -> None:
                    try:
                        states[entity] = await _read_sensor(entity, client, token)
                    except Exception:
                        states[entity] = None  # Never log credential-bearing errors.
                await asyncio.gather(*(read(entity) for entity in sorted(ENTITIES)))
    except TimeoutError:
        pass  # Keep independent sources completed before the total deadline.
    return live_energy_read(estate_id=estate_id, role=role, capabilities=capabilities,
                             range_value=range_value, read_state=states.get)


def live_energy_read(
    *, estate_id: str, role: str, capabilities: frozenset[str],
    now: datetime | None = None, range_value: str = "24h",
    read_state: Callable[[str], Mapping[str, Any] | None],
) -> dict[str, Any]:
    if role != "admin" or "energy" not in capabilities:
        raise EnergyProjectionForbidden("energy read is not permitted")
    estate = _estate(estate_id)
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    if clock is None or range_value not in {"24h", "7d"}:
        raise ValueError("invalid energy read boundary")

    def read(entity: str) -> Mapping[str, Any]:
        try:
            value = read_state(entity)
            # Never accept an unexpected entity substituted by the upstream.
            return value if isinstance(value, Mapping) and value.get("entity_id") == entity else {}
        except Exception:
            # A partial source failure does not discard independent battery data.
            # Never return or log exception details (which may include headers).
            return {}

    # Pure projection input only; network I/O belongs to read_live_energy.
    states = {entity: read(entity) for entity in sorted(ENTITIES)}
    if now is None:
        # A source may legitimately report while this read is in flight.
        # Validate against completion time, never request-start time.
        clock = datetime.now(timezone.utc)
    metrics: dict[str, Any] = {}
    for field, unit in UNITS.items():
        metric = {"value": None, "unit": unit, "observed_at": None, "quality": "unavailable"}
        for entity in SOURCES.get(field, ()):
            state = states[entity]
            attributes = state.get("attributes")
            attributes = attributes if isinstance(attributes, Mapping) else {}
            source_unit = attributes.get("unit_of_measurement")
            expected_units = {"%"} if field == "battery_soc_pct" else {"W", "kW"}
            if source_unit not in expected_units:
                continue
            value = _number(state.get("state"), field)
            observed = _time(state.get("last_reported") or state.get("last_updated"))
            if value is None or observed is None or observed > clock:
                continue
            if source_unit == "kW":
                value *= 1000
            if not math.isfinite(value):
                continue
            # Source timestamps are HA reports, not request completion time.
            age = int((clock - observed).total_seconds())
            metric = {"value": value, "unit": unit, "observed_at": _iso(observed),
                      "quality": "current" if age <= MAX_SOURCE_AGE else "stale"}
            break
        metrics[field] = metric
    battery_fields = ("battery_soc_pct", "battery_power_w", "estate_load_w")
    available = any(metrics[field]["value"] is not None for field in battery_fields)
    accepted_times = [_time(metrics[field]["observed_at"]) for field in battery_fields
                      if metrics[field]["value"] is not None]
    source_time = min(accepted_times) if accepted_times else None
    source_age = int((clock - source_time).total_seconds()) if source_time else None
    current = available and all(metrics[field]["quality"] == "current" for field in battery_fields)
    return {
        "ok": True, "contract": CONTRACT, "estate_id": estate, "range": range_value,
        "available": available, "battery_power_sign": POWER_SIGN,
        "source": {"source_generated_at": _iso(source_time), "last_success_at": _iso(source_time),
                   "data_age_seconds": source_age, "state": "current" if current else "stale" if available else "unavailable"},
        "data_age_seconds": source_age, "metrics": metrics,
        "series": {"units": dict(UNITS), "points": []},
        "history_status": "unavailable_observation_provenance_unverified",
        "timestamp_basis": "home_assistant_source_report",
    }
