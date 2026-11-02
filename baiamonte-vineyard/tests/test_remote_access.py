from __future__ import annotations

import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import display_gateway as gateway, remote_access as access, remote_read_data as data


TANK = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
KIOSK = "33333333-3333-4333-8333-333333333333"
ISSUER = "https://test-team.cloudflareaccess.com"


def policy():
    return {"schema": 1, "enabled": True, "issuer": ISSUER,
            "applications": {s: {"host": s + ".example.com", "audience": n * 64} for s, n in (("labels", "a"), ("field", "b"), ("pos", "c"))},
            "profiles": [{"principal": "device-principal", "device_id": "pilot-label", "surface": "labels", "role": "label_device", "enabled": True, "expires_at": int(time.time()) + 3600, "resources": {"tank_ids": [TANK], "kiosk_ids": [KIOSK]}}]}


@pytest.fixture
def auth(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update(kid="test-key", use="sig", alg="RS256")
    configured = policy()
    monkeypatch.setattr(access, "load_policy", lambda: configured)
    monkeypatch.setattr(access, "fetch_jwks", lambda issuer: {"keys": [public]})
    monkeypatch.setattr(gateway, "get_settings", lambda: SimpleNamespace(display_gateway_enabled=True, display_gateway_origin_token="O" * 43))

    def token(**changes):
        now = int(time.time())
        claims = {"sub": "device-principal", "iss": ISSUER, "aud": "a" * 64, "iat": now - 1, "exp": now + 300}
        claims.update(changes)
        return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"})

    return configured, token, private, public


def headers(token):
    return {"Host": "labels.example.com", "X-Baiamonte-Display-Gateway": "O" * 43, "Cf-Access-Jwt-Assertion": token}


def test_valid_assertion_and_immediate_local_revocation(auth):
    configured, token, _, _ = auth
    assertion = token()
    profile = access.authorize_remote("labels.example.com", "labels", assertion)
    assert profile.device_id == "pilot-label"
    profile.require("tank_ids", TANK)
    configured["profiles"][0]["enabled"] = False
    with pytest.raises(HTTPException) as error:
        access.authorize_remote("labels.example.com", "labels", assertion)
    assert error.value.status_code == 401


@pytest.mark.parametrize("changes", [
    {"sub": "another-device"}, {"aud": "b" * 64}, {"iss": "https://other.cloudflareaccess.com"},
    {"exp": 1}, {"iat": int(time.time()) + 300}, {"exp": int(time.time()) + 90000},
    {"exp": str(int(time.time()) + 300)}, {"sub": None},
])
def test_wrong_expired_future_or_malformed_identity_denied(auth, changes):
    with pytest.raises(HTTPException) as error:
        access.authorize_remote("labels.example.com", "labels", auth[1](**changes))
    assert error.value.status_code == 401


def test_forged_none_hmac_header_urls_and_loss_of_keys_denied(auth, monkeypatch):
    _, token, private, _ = auth
    unsigned = jwt.encode({"sub": "device-principal"}, key="", algorithm="none")
    hmac_token = jwt.encode({"sub": "device-principal"}, "attacker-key-" * 4, algorithm="HS256", headers={"kid": "test-key"})
    foreign_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token(), options={"verify_signature": False})
    forged = jwt.encode(claims, foreign_private, algorithm="RS256", headers={"kid": "test-key"})
    header_url = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key", "jku": "http://127.0.0.1/private"})
    for assertion in (unsigned, hmac_token, forged, header_url, "invalid", "x" * 16385):
        with pytest.raises(HTTPException):
            access.authorize_remote("labels.example.com", "labels", assertion)
    monkeypatch.setattr(access, "fetch_jwks", lambda issuer: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(HTTPException):
        access.authorize_remote("labels.example.com", "labels", token())


def test_duplicate_jwk_and_wrong_key_use_denied(auth, monkeypatch):
    _, token, _, key = auth
    for keys in ([key, key], [{**key, "use": "enc"}], [{**key, "kty": "oct"}], [{**key, "alg": "HS256"}]):
        monkeypatch.setattr(access, "fetch_jwks", lambda issuer: {"keys": keys})
        with pytest.raises(HTTPException):
            access.authorize_remote("labels.example.com", "labels", token())


def test_policy_file_private_missing_symlink_duplicate_and_no_fallback(tmp_path):
    target = tmp_path / "policy.json"
    with pytest.raises(HTTPException):
        access.load_policy(target)
    target.write_text(json.dumps(policy()))
    target.chmod(0o600)
    assert access.load_policy(target)["enabled"] is True
    target.chmod(0o644)
    with pytest.raises(HTTPException):
        access.load_policy(target)
    target.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(HTTPException):
        access.load_policy(link)
    target.write_text('{"schema":1,"schema":1}')
    with pytest.raises(HTTPException):
        access.load_policy(target)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(enabled=False), lambda p: p.update(issuer="http://test.cloudflareaccess.com"),
    lambda p: p.update(issuer=ISSUER + "/path"), lambda p: p["profiles"].append(copy.deepcopy(p["profiles"][0])),
    lambda p: p["profiles"][0].update(role="admin"), lambda p: p["profiles"][0]["resources"].update(tank_ids=["*"]),
    lambda p: p["applications"]["field"].update(audience="a" * 64),
    lambda p: p["profiles"][0]["resources"].update(task_ids=[TANK]),
])
def test_invalid_policies_fail_closed(tmp_path, mutate):
    configured = policy()
    mutate(configured)
    target = tmp_path / "policy.json"
    target.write_text(json.dumps(configured))
    target.chmod(0o600)
    with pytest.raises(HTTPException):
        access.load_policy(target)


@pytest.mark.parametrize("route", [
    "/tv", "/tv/api/traffic/adsb", "/api", "/api/websocket", "/api/v1/admin", "/labels/enroll", "/labels/service-worker.js",
    "/labels/manifest/tank/token.webmanifest", "/labels/tank/valid-legacy-bearer-token", "/labels/api/camera/camera.gate",
    "/labels/assets/secret", "/labels/assets/%2e%2e/remote-read.js", "/labels%2ftank/" + TANK,
    "/labels/tank/" + TANK + "?token=secret", "/field/api/payroll", "/pos/api/payments",
])
def test_unknown_encoded_tokenized_or_control_routes_denied(auth, route):
    response = TestClient(gateway.display_gateway_app).get(route, headers=headers(auth[1]()), follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers
    assert "no-store" in response.headers["cache-control"]


def test_cross_tank_and_spoofed_identity_headers_denied_before_data(auth, monkeypatch):
    client = TestClient(gateway.display_gateway_app)
    monkeypatch.setattr(data, "tank", lambda *args: pytest.fail("cross-tank data read"))
    assert client.get("/labels/api/tank/" + OTHER, headers=headers(auth[1]())).status_code == 404
    spoofed = {"Host": "labels.example.com", "X-Baiamonte-Display-Gateway": "O" * 43, "X-Remote-User-Id": "device-principal", "X-Remote-User-Role": "admin"}
    assert client.get("/labels/api/tank/" + TANK, headers=spoofed).status_code == 401
    assert client.get("/labels/assets/remote-read.js", headers=spoofed).status_code == 401
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"):
        assert client.request(method, "/labels/api/tank/" + TANK, headers=headers(auth[1]())).status_code == 404


def test_minimized_tank_and_kiosk_projection_is_pure_read(auth, monkeypatch):
    profile = access.authorize_remote("labels.example.com", "labels", auth[1]())
    calls = []
    def fetch(sql, args):
        calls.append((sql, args))
        if "cellar_label_kiosks" in sql:
            return {"id": KIOSK, "name": "Pilot", "container_id": TANK}
        return {"id": TANK, "name": "Tank 1", "temp_c": 18, "observed_at": None}
    monkeypatch.setattr(data, "fetch_one", fetch)
    monkeypatch.setattr(data, "estate_id", lambda: "estate")
    result = data.kiosk(profile, KIOSK)
    assert result["tank"]["observed_at"] is None
    assert result["kiosk"] == {"id": KIOSK, "name": "Pilot"}
    assert all(sql.startswith("SELECT ") and "public_token" not in sql and "notes" not in sql and "last_seen" not in sql for sql, _ in calls)
    assert calls[1][1] == ("estate", TANK)
    calls.clear()
    monkeypatch.setattr(data, "fetch_one", lambda *args: {"id": KIOSK, "name": "Pilot", "container_id": OTHER})
    with pytest.raises(HTTPException):
        data.kiosk(profile, KIOSK)


def test_separate_human_read_profiles_and_no_payment_or_person_fields(auth, monkeypatch):
    configured, token, _, _ = auth
    calls = []
    monkeypatch.setattr(data, "estate_id", lambda: "estate")
    monkeypatch.setattr(data, "fetch_all", lambda sql, args: calls.append((sql, args)) or [{"id": TANK, "name": "Allowed"}])
    client = TestClient(gateway.display_gateway_app)
    for surface, role, key, endpoint, audience in (("field", "field_reader", "task_ids", "tasks", "b"), ("pos", "pos_reader", "catalog_ids", "catalog", "c")):
        configured["profiles"].append({"principal": surface + "-reader", "device_id": surface + "-device", "surface": surface, "role": role, "enabled": True, "expires_at": int(time.time()) + 600, "resources": {key: [TANK]}})
        request_headers = headers(token(sub=surface + "-reader", aud=audience * 64))
        request_headers["Host"] = surface + ".example.com"
        response = client.get(f"/{surface}/api/{endpoint}", headers=request_headers)
        assert response.status_code == 200
        assert response.json()["read_only"] is True
        assert "no-store" in response.headers["cache-control"]
        assert "worker-src 'none'" in response.headers["content-security-policy"]
        assert client.get("/labels/api/tank/" + TANK, headers=request_headers).status_code in (401, 404)
    assert response.json()["catalog"][0]["available_quantity"] is None
    assert all("SELECT *" not in sql and "price" not in sql and "notes" not in sql and "assigned_person" not in sql and "register_sales" not in sql for sql, _ in calls)


def test_noncacheable_static_and_auth_loss_no_stale_success(auth):
    configured, token, _, _ = auth
    client = TestClient(gateway.display_gateway_app)
    request_headers = headers(token())
    response = client.get("/labels/assets/remote-read.js", headers=request_headers)
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert "serviceWorker.register" not in response.text
    assert "localStorage." not in response.text
    assert "redirect:'error'" in response.text
    configured["profiles"][0]["enabled"] = False
    assert client.get("/labels/assets/remote-read.js", headers={**request_headers, "If-None-Match": "old"}).status_code == 401


def test_origin_disabled_duplicate_headers_wrong_host_and_head(auth, monkeypatch):
    client = TestClient(gateway.display_gateway_app)
    request_headers = headers(auth[1]())
    assert client.head("/labels/assets/remote-read.css", headers=request_headers).content == b""
    assert client.get("/labels/assets/remote-read.css", headers={**request_headers, "Host": "wrong.example"}).status_code == 404
    assert client.get("/labels/assets/remote-read.css", headers={**request_headers, "X-Baiamonte-Display-Gateway": "wrong"}).status_code == 401
    duplicate = list(request_headers.items()) + [("Cf-Access-Jwt-Assertion", auth[1]())]
    assert client.get("/labels/assets/remote-read.css", headers=duplicate).status_code == 401
    monkeypatch.setattr(gateway, "get_settings", lambda: SimpleNamespace(display_gateway_enabled=False, display_gateway_origin_token="O" * 43))
    assert client.get("/labels/assets/remote-read.css", headers=request_headers).status_code == 503


def test_remote_entrypoint_disables_sensitive_url_logging_and_proxy_headers():
    source = (Path(__file__).parents[1] / "entrypoint.py").read_text()
    command = next(line for line in source.splitlines() if '"app.display_gateway:display_gateway_app"' in line)
    assert '"--no-access-log"' in command
    assert '"--no-proxy-headers"' in command
    assert '"--proxy-headers"' not in command


def test_expired_profile_and_wrong_host_cannot_read(auth):
    configured, token, _, _ = auth
    configured["profiles"][0]["expires_at"] = int(time.time()) - 1
    with pytest.raises(HTTPException) as error:
        access.authorize_remote("labels.example.com", "labels", token())
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        access.authorize_remote("labels.example.com:443", "labels", token())
    assert error.value.status_code == 404


def test_jwks_fetch_pins_url_timeout_size_and_never_follows_redirect(monkeypatch):
    calls = []
    class Result:
        status = 200
        body = b'{"keys":[]}'
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, size):
            assert size == 65537
            return self.body
    result = Result()
    class Opener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout, dict(request.header_items())))
            return result
    monkeypatch.setattr(access.urllib.request, "build_opener", lambda *args: Opener())
    assert access.fetch_jwks(ISSUER) == {"keys": []}
    assert calls == [(ISSUER + "/cdn-cgi/access/certs", 5, {"Accept": "application/json"})]
    assert access._NoRedirect().redirect_request(None, None, 302, None, None, "http://127.0.0.1/private") is None
    for issuer in ("http://127.0.0.1", ISSUER + "/other", "https://user@team.cloudflareaccess.com", "https://team.cloudflareaccess.com:8443"):
        with pytest.raises(ValueError): access.fetch_jwks(issuer)
    result.body = b"x" * 65537
    with pytest.raises(ValueError): access.fetch_jwks(ISSUER)


def test_database_failure_is_sanitized_and_errors_never_cached(auth, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("secret DB details must not escape")
    monkeypatch.setattr(data, "tank", unavailable)
    response = TestClient(gateway.display_gateway_app).get("/labels/api/tank/" + TANK, headers=headers(auth[1]()))
    assert response.status_code == 503
    assert response.json() == {"detail": "remote data unavailable"}
    assert "no-store" in response.headers["cache-control"]


def test_empty_grants_do_not_read_any_unassigned_records(monkeypatch):
    monkeypatch.setattr(data, "fetch_all", lambda *args: pytest.fail("unassigned query"))
    field = access.RemoteProfile("human", "device", "field", "field_reader", {"task_ids": frozenset()})
    pos = access.RemoteProfile("human", "other-device", "pos", "pos_reader", {"catalog_ids": frozenset()})
    assert data.field_tasks(field)["tasks"] == []
    assert data.pos_catalog(pos)["catalog"] == []
