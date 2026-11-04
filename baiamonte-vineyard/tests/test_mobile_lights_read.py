import asyncio
from datetime import datetime, timezone
import hashlib
import json
import time

import httpx
import pytest

from app.domains import mobile_lights_read as lights, mobile_site_routes
from test_direct_site_gateways import _mobile_client, _bearer, TOKENS

ESTATE = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
CAPS = frozenset({"records", "lights.read"})
ENTITY = "light.switch_1_lightbulb"


def project(source):
    return lights.project_lights(estate_id=ESTATE, role="admin", capabilities=CAPS, states={ENTITY: source}, now=NOW)


def test_exact_names_no_controls_or_unreviewed_entities():
    data = project({"entity_id": ENTITY, "state": "off", "last_reported": "2026-11-04T12:59:00+01:00",
                    "attributes": {"private": "secret", "brightness": 255}})
    assert len(data["items"]) == 8
    assert {item["entity_id"]: item["name"] for item in data["items"]} == lights.ALLOWLIST
    assert data["items"][0] == {"entity_id": ENTITY, "name": "Kitchen overhead", "state": "off",
                                "reported_at": "2026-11-04T11:59:00Z", "data_age_seconds": 60, "quality": "current"}
    assert "controllable" not in str(data) and "secret" not in str(data) and "brightness" not in str(data)


@pytest.mark.parametrize("changes", [
    {"entity_id": "light.camera_security"}, {"state": "unavailable"}, {"state": ["on"]},
    {"last_reported": None, "last_updated": "2026-11-04T11:59:00Z"},
    {"last_reported": "2026-11-04T11:59:00"}, {"last_reported": "2026-11-04"},
    {"last_reported": "2026-11-04T12:01:00Z"},
])
def test_unknown_wrong_or_unqualified_source_is_not_current(changes):
    item = project({"entity_id": ENTITY, "state": "on", "last_reported": "2026-11-04T11:59:00Z", **changes})["items"][0]
    assert item["state"] is None and item["reported_at"] is None and item["quality"] == "unavailable"


def test_stale_report_keeps_its_own_clock():
    item = project({"entity_id": ENTITY, "state": "on", "last_reported": "2026-11-04T11:00:00Z"})["items"][0]
    assert item["quality"] == "stale" and item["data_age_seconds"] == 3600


@pytest.mark.parametrize("role,caps", [("worker", CAPS), ("viewer", CAPS), ("enologist", CAPS),
                                      ("admin", frozenset({"records"})), ("admin", frozenset({"lights.read"}))])
def test_denial_precedes_credentials_and_io(monkeypatch, role, caps):
    monkeypatch.setattr(lights, "home_assistant_token", lambda: pytest.fail("credential lookup on denied request"))
    with pytest.raises(lights.LightsReadForbidden):
        asyncio.run(lights.read_lights(estate_id=ESTATE, role=role, capabilities=caps))


class Body(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value
        self.closed = False
    async def __aiter__(self):
        yield self.value
    async def aclose(self):
        self.closed = True


def network(monkeypatch, handler):
    monkeypatch.setattr(lights, "home_assistant_token", lambda: "fixture-token")
    def factory(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    return asyncio.run(lights.read_lights(estate_id=ESTATE, role="admin", capabilities=CAPS, client_factory=factory))


def test_network_gets_only_eight_reviewed_states(monkeypatch):
    calls = []
    async def handler(request):
        entity = request.url.path.removeprefix("/core/api/states/")
        assert entity in lights.ALLOWLIST and request.url.host == "supervisor"
        assert request.method == "GET" and request.content == b""
        calls.append(entity)
        return httpx.Response(200, stream=Body(json.dumps({"entity_id": entity, "state": "on", "last_reported": datetime.now(timezone.utc).isoformat()}).encode()))
    data = network(monkeypatch, handler)
    assert set(calls) == set(lights.ALLOWLIST) and len(calls) == 8
    assert all(item["quality"] == "current" for item in data["items"])


@pytest.mark.parametrize("mode", ["redirect", "oversized", "encoded", "bad-json"])
def test_untrusted_upstream_stays_unavailable(monkeypatch, mode):
    calls = []
    async def handler(request):
        calls.append(request)
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://untrusted.invalid"}, stream=Body(b""))
        if mode == "encoded":
            return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Body(b""))
        return httpx.Response(200, stream=Body(b"x" * (20_000 if mode == "oversized" else 1)))
    assert all(item["state"] is None for item in network(monkeypatch, handler)["items"])
    assert len(calls) == 8


def test_total_deadline_keeps_independent_completed_lights(monkeypatch):
    monkeypatch.setattr(lights, "TOTAL_SOURCE_DEADLINE", 0.05)
    async def handler(request):
        entity = request.url.path.removeprefix("/core/api/states/")
        if entity != ENTITY:
            await asyncio.sleep(1)
        return httpx.Response(200, stream=Body(json.dumps({"entity_id": entity, "state": "on", "last_reported": datetime.now(timezone.utc).isoformat()}).encode()))
    started = time.monotonic()
    result = network(monkeypatch, handler)
    assert time.monotonic() - started < 0.5
    assert result["items"][0]["state"] == "on" and result["items"][1]["state"] is None


def test_route_flag_and_separate_session_grant_default_closed(monkeypatch):
    client, sessions, _ = _mobile_client(monkeypatch)
    settings = mobile_site_routes.get_settings()
    settings.mobile_lights_status_enabled = False
    async def no_io(**kwargs):
        pytest.fail("disabled or denied route performed source I/O")
    monkeypatch.setattr(mobile_site_routes, "read_lights", no_io)
    path = "/api/v1/mobile/records?object=lights&projection=lights-v1"
    assert client.get(path, headers=_bearer("admin")).status_code == 404
    settings.mobile_lights_status_enabled = True
    for role in ("worker", "viewer", "enologist", "revoked_session", "expired"):
        assert client.get(path, headers=_bearer(role)).status_code in (401, 403)
    for query in ("object=lights&projection=lights-v1&entity_id=light.camera_security",
                  "object=lights&projection=lights-v1&limit=8", "object=cellar&projection=lights-v1",
                  "object=lights&projection=lights-v1&object=lights"):
        assert client.get("/api/v1/mobile/records?" + query, headers=_bearer("admin")).status_code == 422
    key = hashlib.sha256(TOKENS["admin"].encode()).hexdigest()
    granted = json.loads(sessions[key]["capabilities_json"])
    sessions[key]["capabilities_json"] = json.dumps([cap for cap in granted if cap != "lights.read"])
    assert client.get(path, headers=_bearer("admin")).status_code == 403
    assert client.post(path, headers=_bearer("admin")).status_code == 405
    sessions[key]["capabilities_json"] = json.dumps(granted)
    async def read(**kwargs):
        return lights.project_lights(**kwargs, states={})
    monkeypatch.setattr(mobile_site_routes, "read_lights", read)
    response = client.get(path, headers=_bearer("admin"))
    assert response.status_code == 200 and len(response.json()["lights"]["items"]) == 8
