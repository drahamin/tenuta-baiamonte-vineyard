from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path

import pytest
import httpx

from app.domains.mobile_energy_live import ENTITIES, SOURCES, _read_sensor, live_energy_read
from app.domains import mobile_energy_live
from app.domains.mobile_energy_projection import EnergyProjectionForbidden


ESTATE = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def sample(entity, value, unit="W", at="2026-11-03T11:59:00Z"):
    return {"entity_id": entity, "state": value, "last_updated": at,
            "attributes": {"unit_of_measurement": unit, "private": "excluded"}}


def run(states, **kwargs):
    return live_energy_read(estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}),
                            now=NOW, read_state=lambda entity: states.get(entity), **kwargs)


def test_live_battery_survives_missing_pv_and_keeps_sign_and_zero():
    soc, power, load = (SOURCES[field][0] for field in ("battery_soc_pct", "battery_power_w", "estate_load_w"))
    result = run({soc: sample(soc, 61, "%"), power: sample(power, -0.42, "kW"), load: sample(load, 0)})
    assert result["available"] is True and result["source"]["state"] == "current"
    assert result["metrics"]["battery_power_w"]["value"] == -420
    assert result["metrics"]["estate_load_w"]["value"] == 0
    assert result["metrics"]["pv_power_w"]["value"] is None
    assert result["metrics"]["forecast_remaining_kwh"]["value"] is None
    assert result["series"]["points"] == []  # Never invent history from one read.
    assert "sensor." not in json.dumps(result) and "private" not in json.dumps(result)


@pytest.mark.parametrize("role,caps", [("worker", {"energy"}), ("enologist", {"energy"}), ("admin", set())])
def test_denial_precedes_any_source_read(role, caps):
    with pytest.raises(EnergyProjectionForbidden):
        live_energy_read(estate_id=ESTATE, role=role, capabilities=frozenset(caps), now=NOW,
                         read_state=lambda _: pytest.fail("unauthorized source read"))


@pytest.mark.parametrize("value,unit,at", [
    (True, "%", "2026-11-03T11:59:00Z"), (101, "%", "2026-11-03T11:59:00Z"),
    (61, "W", "2026-11-03T11:59:00Z"), (61, "%", None),
    (61, "%", "2026-11-03"), (61, "%", "2026-11-03T12:01:00Z"),
    ("NaN", "%", "2026-11-03T11:59:00Z"),
])
def test_invalid_soc_or_clock_is_unknown(value, unit, at):
    entity = SOURCES["battery_soc_pct"][0]
    result = run({entity: sample(entity, value, unit, at)})
    assert result["available"] is False and result["metrics"]["battery_soc_pct"]["value"] is None


def test_stale_report_is_preserved_as_stale_not_refreshed_to_now():
    entity = SOURCES["battery_soc_pct"][0]
    result = run({entity: sample(entity, 61, "%", "2026-11-03T10:00:00Z")})
    assert result["available"] is True and result["source"]["state"] == "stale"
    assert result["metrics"]["battery_soc_pct"]["observed_at"] == "2026-11-03T10:00:00Z"


def test_one_source_failure_and_wrong_entity_do_not_discard_another_metric():
    power = SOURCES["battery_power_w"][0]
    def read(entity):
        if entity == power:
            return sample(power, 300)
        raise TimeoutError("secret must not escape")
    result = live_energy_read(estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}),
                              now=NOW, read_state=read)
    assert result["metrics"]["battery_power_w"]["value"] == 300
    assert "secret" not in json.dumps(result)
    assert run({power: sample("sensor.wrong", 300)})["available"] is False


def test_exact_allowlist_only_and_invalid_range_never_fetches():
    called = []
    result = live_energy_read(estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}),
                              now=NOW, read_state=lambda entity: called.append(entity))
    assert set(called) == ENTITIES and result["available"] is False
    with pytest.raises(ValueError):
        asyncio.run(_read_sensor("switch.arbitrary", None, "synthetic-test-only"))
    with pytest.raises(ValueError):
        run({}, range_value="30d")


def test_overflow_after_unit_conversion_stays_unknown():
    entity = SOURCES["battery_power_w"][0]
    assert run({entity: sample(entity, "1e308", "kW")})["available"] is False


def test_sanitized_native_fixture_exactly_matches_live_projection():
    soc, power, load = (SOURCES[field][0] for field in ("battery_soc_pct", "battery_power_w", "estate_load_w"))
    result = run({soc: sample(soc, 61, "%"), power: sample(power, -420), load: sample(load, 196)})
    fixture = json.loads((Path(__file__).parent / "fixtures/mobile_energy_live_battery.json").read_text())
    assert fixture["contract"] == "baiamonte.direct-site.v1"
    assert fixture["energy"] == result
    assert "telemetry" not in fixture


class Body(httpx.AsyncByteStream):
    def __init__(self, content):
        self.content = content
        self.closed = False

    async def __aiter__(self):
        yield self.content

    async def aclose(self):
        self.closed = True


def network(handler, monkeypatch):
    monkeypatch.setattr(mobile_energy_live, "home_assistant_token", lambda: "synthetic-test-only")
    def factory(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    return asyncio.run(mobile_energy_live.read_live_energy(
        estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), client_factory=factory,
    ))


def test_source_transport_is_exact_get_and_ignores_proxy_environment(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://untrusted.invalid:1234")
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.method == "GET" and request.content == b""
        assert request.url.host == "supervisor" and request.url.port is None
        entity = request.url.path.removeprefix("/core/api/states/")
        assert entity in ENTITIES
        assert request.headers["accept-encoding"] == "identity"
        value = sample(entity, 61, "%", datetime.now(timezone.utc).isoformat())
        return httpx.Response(200, stream=Body(json.dumps(value).encode()))
    result = network(handler, monkeypatch)
    assert result["metrics"]["battery_soc_pct"]["value"] == 61
    assert len(calls) == len(ENTITIES)


def test_redirect_never_receives_another_request(monkeypatch):
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url.host == "supervisor"
        return httpx.Response(302, headers={"Location": "http://untrusted.invalid"}, stream=Body(b""))
    assert network(handler, monkeypatch)["available"] is False
    assert len(calls) == len(ENTITIES)  # No follow-up requests.


def test_oversized_source_response_is_unknown_and_closed(monkeypatch):
    streams = []
    async def handler(request):
        body = Body(b"x" * 20_000)
        streams.append(body)
        return httpx.Response(200, stream=body)
    assert network(handler, monkeypatch)["available"] is False
    assert all(body.closed for body in streams)


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_total_deadline_cancels_slow_headers_or_drip_body(monkeypatch, phase):
    import time
    monkeypatch.setattr(mobile_energy_live, "TOTAL_SOURCE_DEADLINE", 0.05)
    streams = []
    cancelled = []
    class SlowBody(Body):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b" "
    async def handler(request):
        if phase == "headers":
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        body = SlowBody(b"")
        streams.append(body)
        return httpx.Response(200, stream=body)
    start = time.monotonic()
    assert network(handler, monkeypatch)["available"] is False
    assert time.monotonic() - start < 0.5
    assert all(body.closed for body in streams)
    if phase == "headers":
        assert len(cancelled) == len(ENTITIES)


def test_deadline_preserves_independent_completed_sources(monkeypatch):
    monkeypatch.setattr(mobile_energy_live, "TOTAL_SOURCE_DEADLINE", 0.05)
    power = SOURCES["battery_power_w"][0]
    async def handler(request):
        entity = request.url.path.removeprefix("/core/api/states/")
        if entity != power:
            await asyncio.sleep(1)
        return httpx.Response(200, stream=Body(json.dumps(sample(entity, -420, at=datetime.now(timezone.utc).isoformat())).encode()))
    result = network(handler, monkeypatch)
    assert result["metrics"]["battery_power_w"]["value"] == -420
    assert result["metrics"]["battery_soc_pct"]["value"] is None


def test_async_authorization_denial_precedes_credential_lookup(monkeypatch):
    monkeypatch.setattr(mobile_energy_live, "home_assistant_token", lambda: pytest.fail("credential lookup"))
    with pytest.raises(EnergyProjectionForbidden):
        asyncio.run(mobile_energy_live.read_live_energy(estate_id=ESTATE, role="worker", capabilities=frozenset({"energy"})))
