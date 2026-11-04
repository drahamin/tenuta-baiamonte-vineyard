"""Status-only reads of the eight reviewed ordinary lights. No control method."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Callable, Mapping

import httpx

from ..ha_auth import home_assistant_token
from .mobile_energy_projection import _estate, _iso, _time

CONTRACT = "baiamonte.mobile-lights.v1"
ALLOWLIST = {
    "light.switch_1_lightbulb": "Kitchen overhead",
    "light.switch_2_lightbulb": "Warehouse",
    "light.switch_3_lightbulb": "Toilette",
    "light.switch_4_lightbulb": "Palmento",
    "light.switch_5_lightbulb": "Patio",
    "light.switch_6_lightbulb": "Patio strip",
    "light.switch_7_lightbulb": "Kitchen sink",
    "light.switch_8_lightbulb": "Fox Den overhead",
}
MAX_SOURCE_BYTES = 16_384
TOTAL_SOURCE_DEADLINE = 2.0
MAX_REPORT_AGE = 900


class LightsReadForbidden(PermissionError):
    pass


def project_lights(*, estate_id: str, role: str, capabilities: frozenset[str],
                   states: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    if role != "admin" or not {"records", "lights.read"} <= capabilities:
        raise LightsReadForbidden("ordinary light status read is not permitted")
    estate = _estate(estate_id)
    clock = _time(now) if now is not None else datetime.now(timezone.utc)
    if clock is None:
        raise ValueError("invalid lights read clock")
    items = []
    for entity, name in ALLOWLIST.items():
        source = states.get(entity)
        source = source if isinstance(source, Mapping) and source.get("entity_id") == entity else {}
        value = source.get("state")
        # Only a timezone-qualified HA report dates this status. A changed-at,
        # fetch/cache clock or user-selected entity cannot substitute for it.
        reported = _time(source.get("last_reported"))
        if not isinstance(value, str) or value not in {"on", "off"} or reported is None or reported > clock:
            value, reported = None, None
        age = int((clock - reported).total_seconds()) if reported else None
        items.append({"entity_id": entity, "name": name, "state": value,
                      "reported_at": _iso(reported), "data_age_seconds": age,
                      "quality": "unavailable" if value is None else "current" if age <= MAX_REPORT_AGE else "stale"})
    return {"contract": CONTRACT, "estate_id": estate, "items": items,
            "timestamp_basis": "home_assistant_source_report"}


async def _read_light(entity: str, client: httpx.AsyncClient, token: str) -> Mapping[str, Any] | None:
    if entity not in ALLOWLIST:
        raise ValueError("unapproved ordinary light")
    async with client.stream("GET", "http://supervisor/core/api/states/" + entity,
                             headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                                      "Accept-Encoding": "identity"}) as response:
        if response.status_code != 200 or response.headers.get("content-encoding", "identity") != "identity":
            return None
        body = bytearray()
        async for chunk in response.aiter_raw():
            if len(body) + len(chunk) > MAX_SOURCE_BYTES:
                return None
            body.extend(chunk)
    value = json.loads(body)
    return value if isinstance(value, dict) else None


async def read_lights(*, estate_id: str, role: str, capabilities: frozenset[str],
                      client_factory: Callable[..., httpx.AsyncClient] | None = None) -> dict[str, Any]:
    # Authorization and estate checks precede credential lookup and every I/O.
    empty = project_lights(estate_id=estate_id, role=role, capabilities=capabilities, states={})
    token = home_assistant_token()
    if not token or any(ord(char) < 33 or ord(char) > 126 for char in token):
        return empty
    states: dict[str, Any] = {}
    factory = client_factory or httpx.AsyncClient
    try:
        async with asyncio.timeout(TOTAL_SOURCE_DEADLINE):
            async with factory(trust_env=False, follow_redirects=False,
                               timeout=httpx.Timeout(2.0, connect=1.0),
                               limits=httpx.Limits(max_connections=8, max_keepalive_connections=0)) as client:
                async def read(entity: str) -> None:
                    try:
                        states[entity] = await _read_light(entity, client, token)
                    except Exception:
                        states[entity] = None  # Never expose upstream credentials/errors.
                await asyncio.gather(*(read(entity) for entity in ALLOWLIST))
    except TimeoutError:
        pass
    return project_lights(estate_id=estate_id, role=role, capabilities=capabilities, states=states)
