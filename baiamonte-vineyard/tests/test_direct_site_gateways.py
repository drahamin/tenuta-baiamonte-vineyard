from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.display_gateway import classify_display_path, display_gateway_app, rewrite_label_body
from app.domains import mobile_site_routes
from scripts.integration_manager import deploy_mobile_gateway_runtime


ROOT = Path(__file__).parents[1]
PROXY_IO_SPEC = importlib.util.spec_from_file_location(
    "baiamonte_proxy_io", ROOT / "custom_components/baiamonte_branding/proxy_io.py"
)
assert PROXY_IO_SPEC and PROXY_IO_SPEC.loader
proxy_io = importlib.util.module_from_spec(PROXY_IO_SPEC)
PROXY_IO_SPEC.loader.exec_module(proxy_io)


def test_mobile_gateway_is_packaged_narrow_and_default_off() -> None:
    proxy = (ROOT / "custom_components/baiamonte_branding/mobile_proxy.py").read_text(encoding="utf-8")
    init = (ROOT / "custom_components/baiamonte_branding/__init__.py").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "requires_auth = True" in proxy  # HA is required only for session exchange.
    assert 'ALLOWED_ROUTES = {"session", "status", "catalog", "records", "weather", "work", "review", "energy", "etna"}' in proxy
    assert 'request.get("hass_user")' in proxy
    assert 'headers={"Accept": "application/json", "Authorization": authorization}' in proxy
    assert "X-Remote-User-Id" in proxy and "X-Remote-User-Name" not in proxy
    assert 'OAUTH_CLIENT_ID = f"{PUBLIC_ORIGIN}/oauth/client-metadata.json"' in proxy
    assert 'OAUTH_REDIRECT_URI = "baiamonte-vineyard://auth/callback"' in proxy
    assert "BaiamonteMobileProxyView(config_dir)" in init
    assert "load_mobile_gateway_runtime(self._config_dir)" in proxy
    entrypoint = (ROOT / "entrypoint.py").read_text(encoding="utf-8")
    manager = (ROOT / "scripts/integration_manager.py").read_text(encoding="utf-8")
    assert "deploy_mobile_gateway_runtime(options)" in entrypoint
    assert '"baiamonte_mobile_gateway.json"' in manager
    assert "BaiamonteMobileRevokeView" in init
    assert "mobile_site_gateway_enabled: false" in config
    assert "display_gateway_enabled: false" in config


def test_mobile_target_origin_rejects_extensions_and_canonicalizes() -> None:
    assert proxy_io.validated_mobile_target_origin("http://0c04eef6-baiamonte-vineyard:8099") == "http://0c04eef6-baiamonte-vineyard:8099"
    for value in (
        "https://0c04eef6-baiamonte-vineyard:8099", "http://0c04eef6-baiamonte-vineyard:8099/path",
        "http://user@0c04eef6-baiamonte-vineyard:8099", "http://0c04eef6-baiamonte-vineyard:8099?x=1",
        "http://0c04eef6-baiamonte-vineyard:8099#fragment", "http://example.com:8099",
    ):
        with pytest.raises(ValueError):
            proxy_io.validated_mobile_target_origin(value)


def test_mobile_runtime_handoff_requires_private_validated_file(tmp_path: Path) -> None:
    options = {
        "mobile_site_gateway_enabled": True,
        "mobile_site_exchange_hmac_key": "H" * 43,
    }
    assert deploy_mobile_gateway_runtime(options, tmp_path) is True
    storage = tmp_path / ".storage"
    runtime = storage / "baiamonte_mobile_gateway.json"
    assert runtime.stat().st_mode & 0o777 == 0o600
    assert proxy_io.load_mobile_gateway_runtime(tmp_path) == {
        "enabled": True,
        "public_host": "baiamonte.rhmproxy.com",
        "target_origin": "http://0c04eef6-baiamonte-vineyard:8099",
        "exchange_hmac_key": "H" * 43,
    }
    assert deploy_mobile_gateway_runtime(options, tmp_path) is False
    runtime.chmod(0o644)
    assert proxy_io.load_mobile_gateway_runtime(tmp_path) == {}
    runtime.unlink()
    private_target = storage / "private-target.json"
    private_target.write_text("{}", encoding="utf-8")
    private_target.chmod(0o600)
    runtime.symlink_to(private_target)
    assert proxy_io.load_mobile_gateway_runtime(tmp_path) == {}


def test_mobile_runtime_handoff_disables_invalid_secret_without_persisting_it(tmp_path: Path) -> None:
    assert deploy_mobile_gateway_runtime({
        "mobile_site_gateway_enabled": True,
        "mobile_site_exchange_hmac_key": "invalid-secret",
    }, tmp_path) is True
    runtime = tmp_path / ".storage" / "baiamonte_mobile_gateway.json"
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    assert payload["enabled"] is False
    assert payload["exchange_hmac_key"] == ""
    assert runtime.stat().st_mode & 0o777 == 0o600
    assert proxy_io.load_mobile_gateway_runtime(tmp_path) == {}


def test_disabled_mobile_runtime_retains_only_validated_revoke_route_metadata(tmp_path: Path) -> None:
    assert deploy_mobile_gateway_runtime({
        "mobile_site_gateway_enabled": False,
        "mobile_site_exchange_hmac_key": "H" * 43,
    }, tmp_path) is True
    assert proxy_io.load_mobile_gateway_runtime(tmp_path) == {}
    assert proxy_io.load_mobile_gateway_runtime(tmp_path, require_enabled=False) == {
        "enabled": False,
        "public_host": "baiamonte.rhmproxy.com",
        "target_origin": "http://0c04eef6-baiamonte-vineyard:8099",
        "exchange_hmac_key": "",
    }


def test_bounded_response_reads_to_eof_and_closes_on_overflow() -> None:
    class Content:
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = chunks

        async def iter_chunked(self, _size: int):
            for chunk in self.chunks:
                yield chunk

    class Upstream:
        def __init__(self, chunks: list[bytes]) -> None:
            self.content = Content(chunks)
            self.closed = False

        def close(self) -> None:
            self.closed = True

    complete = Upstream([b"first", b"-", b"last"])
    assert asyncio.run(proxy_io.bounded_response_body(complete, 32)) == b"first-last"
    assert complete.closed is False
    oversized = Upstream([b"1234", b"5678"])
    with pytest.raises(ValueError, match="response_too_large"):
        asyncio.run(proxy_io.bounded_response_body(oversized, 7))
    assert oversized.closed is True


def test_display_route_classifier_allows_only_bounded_read_surfaces() -> None:
    assert classify_display_path("tv") == (8101, "/")
    assert classify_display_path("tv/api/display-data") == (8101, "/api/display-data")
    assert classify_display_path("tv/assets/display.js") == (8101, "/assets/display.js")
    assert classify_display_path("tv/api/traffic/adsb") == (8101, "/api/traffic/adsb")
    assert classify_display_path("labels/tank/1234567890abcdef") == (8102, "/tank/1234567890abcdef")
    for path in (
        "tv/api/camera/camera.gate", "tv/api/client-error", "tv/../api/display-data",
        "tv/assets/../../secret", "labels/../../api/v1/admin", "labels/assets/../secret",
        "api/v1/admin", "health",
    ):
        with pytest.raises(HTTPException) as error:
            classify_display_path(path)
        assert error.value.status_code == 404


def test_remote_label_gateway_rewrites_assets_refresh_and_worker_scope() -> None:
    html = b'<link href="/assets/tank-label.css"><img src="/brand/logo.png"><link href="/manifest/tank/token.webmanifest">'
    rewritten_html = rewrite_label_body("/tank/1234567890abcdef", "text/html; charset=utf-8", html)
    assert b'"/labels/assets/tank-label.css"' in rewritten_html
    assert b'"/labels/brand/logo.png"' in rewritten_html
    assert b'"/labels/manifest/tank/token.webmanifest"' in rewritten_html
    javascript = b'const gateway = location.pathname.startsWith("/api/baiamonte_labels/") ? "/api/baiamonte_labels" : "";'
    rewritten_js = rewrite_label_body("/assets/tank-label.js", "text/javascript", javascript)
    assert b'location.pathname.startsWith("/labels/") ? "/labels"' in rewritten_js
    assert classify_display_path("labels/assets/tank-label.js") == (8102, "/assets/tank-label.js")
    assert classify_display_path("labels/api/tank/1234567890abcdef") == (8102, "/api/tank/1234567890abcdef")
    assert classify_display_path("labels/service-worker.js") == (8102, "/service-worker.js")


def test_display_gateway_cannot_start_without_enable_and_origin_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.display_gateway.get_settings",
        lambda: SimpleNamespace(
            display_gateway_enabled=False,
            display_gateway_origin_token="",
            display_gateway_public_host="displays.rhmproxy.com",
        ),
    )
    client = TestClient(display_gateway_app)
    assert client.get("/tv", headers={"Host": "wrong.example", "X-Baiamonte-Display-Gateway": "anything"}).status_code == 404
    assert client.get("/tv", headers={"Host": "displays.rhmproxy.com", "X-Baiamonte-Display-Gateway": "anything"}).status_code == 503
    monkeypatch.setattr(
        "app.display_gateway.get_settings",
        lambda: SimpleNamespace(
            display_gateway_enabled=True,
            display_gateway_origin_token="predictable",
            display_gateway_public_host="displays.rhmproxy.com",
        ),
    )
    assert client.get("/tv", headers={"Host": "displays.rhmproxy.com", "X-Baiamonte-Display-Gateway": "predictable"}).status_code == 503
    valid_token = "T" * 43
    monkeypatch.setattr(
        "app.display_gateway.get_settings",
        lambda: SimpleNamespace(
            display_gateway_enabled=True,
            display_gateway_origin_token=valid_token,
            display_gateway_public_host="displays.rhmproxy.com",
        ),
    )
    response = client.get(
        "/tv",
        headers={"Host": "displays.rhmproxy.com", "X-Baiamonte-Display-Gateway": valid_token},
        follow_redirects=False,
    )
    assert response.status_code == 308 and response.headers["location"] == "/tv/"
    entrypoint = (ROOT / "entrypoint.py").read_text(encoding="utf-8")
    assert 're.fullmatch(r"[A-Za-z0-9_-]{43}", display_gateway_token)' in entrypoint


def test_freshness_is_deterministic_and_never_fabricates_source_time() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    fresh = mobile_site_routes._freshness("2026-11-01T11:59:00Z", now=now)
    assert fresh == {
        "generated_at": "2026-11-01T12:00:00+00:00",
        "source_generated_at": "2026-11-01T11:59:00+00:00",
        "data_age_seconds": 60,
        "stale": False,
    }
    unknown = mobile_site_routes._freshness(None, now=now)
    assert unknown["source_generated_at"] is None
    assert unknown["data_age_seconds"] is None
    assert unknown["stale"] is True


TOKENS = {
    "admin": "A" * 43,
    "worker": "B" * 43,
    "enologist": "C" * 43,
    "viewer": "D" * 43,
    "revoked_identity": "E" * 43,
    "revoked_session": "F" * 43,
    "expired": "G" * 43,
}
EXCHANGE_HMAC_KEY = "H" * 43


def _mobile_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, dict[str, dict[str, object]], list[tuple[str, tuple[object, ...]]]]:
    payload = {
        "year": 2026,
        "generated_at": "2026-11-01T11:59:00Z",
        "estate": {"name": "Tenuta Baiamonte", "location": "Etna", "private": "no"},
        "dashboard": {
            "tasks": [{"id": "task-1", "title": "Inspect", "status": "planned", "updated_at": "2026-11-01T10:00:00Z", "secret": "not-selected"}],
            "alerts": [{"id": "alert-1", "title": "Wind", "severity": "warning"}], "issues": [],
        },
        "grapes": {"varieties": [{"variety_id": "variety-1", "name": "Nerello", "planned_kg": 1000, "harvested_kg": 500}]},
        "cellar": {"tanks": [{"id": "tank-1", "name": "Tank 1", "capacity_l": 1200, "volume_l": 800,
                                "level_pct": 66.7, "temp_c": 18.2, "density_sg": 0.998,
                                "reading_at": "2026-11-01T10:30:00Z"}]},
        "labs": {"queue": []},
        "solar": {"available": True, "current_power": 1200, "energy_today": 5.2, "forecast_energy_remaining": 2.1,
                  "forecast_energy_tomorrow": 7.0, "power_controls": {"relay": "on"}},
        "system_status": {},
    }
    monkeypatch.setattr(mobile_site_routes, "display_payload", lambda: payload)
    monkeypatch.setattr(mobile_site_routes, "weather_context_payload", lambda: {"observed_at": "2026-11-01T11:59:00Z", "temperature_c": 18.2})
    monkeypatch.setattr(mobile_site_routes, "etna_status", lambda: {
        "generated_at": "2026-11-01T11:59:00Z", "last_complete_at": "2026-11-01T11:59:00Z",
        "expires_at": "2099-01-01T00:00:00Z", "errors": {},
        "source_status": {"communications": {"state": "current"}}, "activity": {"label": "normal"},
    })
    policy = {
        "ha-admin-0001": {"enabled": True, "version": 1, "username": "pilot_owner", "role": "admin", "capabilities": sorted(mobile_site_routes._ROLE_CAPABILITIES["admin"])},
        "ha-worker-001": {"enabled": True, "version": 1, "username": "worker", "role": "worker", "capabilities": sorted(mobile_site_routes._ROLE_CAPABILITIES["worker"])},
        "ha-enology-01": {"enabled": True, "version": 1, "username": "enologist", "role": "enologist", "capabilities": sorted(mobile_site_routes._ROLE_CAPABILITIES["enologist"])},
        "ha-viewer-001": {"enabled": True, "version": 1, "username": "viewer", "role": "viewer", "capabilities": sorted(mobile_site_routes._ROLE_CAPABILITIES["viewer"])},
        "ha-revoked-01": {"enabled": False, "version": 2, "username": "former", "role": "admin", "capabilities": sorted(mobile_site_routes._ROLE_CAPABILITIES["admin"])},
    }
    settings = SimpleNamespace(
        mobile_site_gateway_enabled=True,
        mobile_site_identity_policy=json.dumps(policy),
        mobile_site_exchange_hmac_key=EXCHANGE_HMAC_KEY,
        mobile_site_session_audience="com.cantinabaiamonte.vineyard",
        mobile_site_session_ttl_seconds=3600,
    )
    monkeypatch.setattr(mobile_site_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(mobile_site_routes, "runtime_option", lambda _name, fallback: fallback)
    monkeypatch.setattr(mobile_site_routes, "_trusted_gateway_source", lambda _request: True)

    sessions: dict[str, dict[str, object]] = {}
    role_ids = {"admin": "ha-admin-0001", "worker": "ha-worker-001", "enologist": "ha-enology-01", "viewer": "ha-viewer-001"}
    for role, user_id in role_ids.items():
        sessions[hashlib.sha256(TOKENS[role].encode()).hexdigest()] = {
            "ha_user_id": user_id,
            "identity_version": 1,
            "audience": settings.mobile_site_session_audience,
            "capabilities_json": json.dumps(policy[user_id]["capabilities"]),
            "expires_at": "2099-01-01 00:00:00",
            "revoked_at": None,
        }
    sessions[hashlib.sha256(TOKENS["revoked_identity"].encode()).hexdigest()] = {
        "ha_user_id": "ha-revoked-01", "identity_version": 2, "audience": settings.mobile_site_session_audience,
        "capabilities_json": json.dumps(sorted(mobile_site_routes._ROLE_CAPABILITIES["admin"])),
        "expires_at": "2099-01-01 00:00:00", "revoked_at": None,
    }
    sessions[hashlib.sha256(TOKENS["revoked_session"].encode()).hexdigest()] = {
        "ha_user_id": "ha-admin-0001", "identity_version": 1, "audience": settings.mobile_site_session_audience,
        "capabilities_json": json.dumps(policy["ha-admin-0001"]["capabilities"]),
        "expires_at": "2099-01-01 00:00:00", "revoked_at": "2026-11-01 00:00:00",
    }
    sessions[hashlib.sha256(TOKENS["expired"].encode()).hexdigest()] = {
        "ha_user_id": "ha-admin-0001", "identity_version": 1, "audience": settings.mobile_site_session_audience,
        "capabilities_json": json.dumps(policy["ha-admin-0001"]["capabilities"]),
        "expires_at": "2000-01-01 00:00:00", "revoked_at": None,
    }
    monkeypatch.setattr(mobile_site_routes, "fetch_one", lambda _sql, params=(): sessions.get(params[0]))
    statements: list[tuple[str, tuple[object, ...]]] = []
    claimed_nonces: dict[str, datetime] = {}

    class Cursor:
        def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
            statements.append((sql, params))
            if sql.startswith("DELETE FROM mobile_site_exchange_nonces"):
                cutoff = params[0]
                expired = [nonce_hash for nonce_hash, expires_at in claimed_nonces.items() if expires_at < cutoff]
                for nonce_hash in expired:
                    claimed_nonces.pop(nonce_hash)
                return len(expired)
            if sql.startswith("INSERT IGNORE INTO mobile_site_exchange_nonces"):
                nonce_hash = str(params[0])
                if nonce_hash in claimed_nonces:
                    return 0
                claimed_nonces[nonce_hash] = params[2]
                return 1
            if sql.startswith("UPDATE mobile_site_sessions") and params[0] in sessions:
                sessions[params[0]]["revoked_at"] = "2026-11-01 00:00:00"
            return 1

    @contextmanager
    def fake_transaction():
        nonce_snapshot = dict(claimed_nonces)
        try:
            yield object(), Cursor()
        except Exception:
            claimed_nonces.clear()
            claimed_nonces.update(nonce_snapshot)
            raise

    monkeypatch.setattr(mobile_site_routes, "transaction", fake_transaction)
    app = FastAPI()
    app.include_router(mobile_site_routes.router)
    return TestClient(app), sessions, statements


def _bearer(role: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[role]}", **extra}


def test_actual_app_sessions_enforce_roles_capabilities_and_record_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    assert client.get("/api/v1/mobile/energy", headers=_bearer("admin")).status_code == 200
    assert client.get("/api/v1/mobile/work", headers=_bearer("worker")).status_code == 200
    assert client.get("/api/v1/mobile/energy", headers=_bearer("worker")).status_code == 403
    assert client.get("/api/v1/mobile/records?object=tasks", headers=_bearer("worker")).status_code == 403
    assert client.get("/api/v1/mobile/review", headers=_bearer("enologist")).status_code == 200
    assert client.get("/api/v1/mobile/records?object=labs", headers=_bearer("enologist")).status_code == 200
    assert client.get("/api/v1/mobile/records?object=alerts", headers=_bearer("enologist")).status_code == 403
    assert client.get("/api/v1/mobile/catalog", headers=_bearer("viewer")).status_code == 200
    assert client.get("/api/v1/mobile/work", headers=_bearer("viewer")).status_code == 403
    enology_review = client.get("/api/v1/mobile/review", headers=_bearer("enologist")).json()
    assert enology_review["alerts"] == []
    assert client.get("/api/v1/mobile/review", headers=_bearer("admin")).json()["alerts"][0]["id"] == "alert-1"


def test_unknown_revoked_and_spoofed_identity_cannot_bind_or_read(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    assert client.get("/api/v1/mobile/session", headers={"Authorization": f"Bearer {'Z' * 43}"}).status_code == 401
    assert client.get("/api/v1/mobile/session", headers=_bearer("revoked_session")).status_code == 401
    assert client.get("/api/v1/mobile/session", headers=_bearer("revoked_identity")).status_code == 403
    viewer = client.get(
        "/api/v1/mobile/session",
        headers=_bearer("viewer", **{"X-Remote-User-Id": "ha-admin-0001", "X-Remote-User-Name": "pilot_owner"}),
    )
    assert viewer.status_code == 200
    assert viewer.json()["user"]["username"] == "viewer"
    assert viewer.json()["user"]["role"] == "viewer"


def test_exchange_uses_immutable_ha_id_and_revoke_is_immediate(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, statements = _mobile_client(monkeypatch)
    proof = proxy_io.signed_exchange_headers(EXCHANGE_HMAC_KEY, "ha-viewer-001")
    exchange = client.post(
        "/api/v1/mobile/session/exchange",
        headers={"X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", "X-Remote-User-Name": "pilot_owner", **proof},
    )
    assert exchange.status_code == 200
    assert exchange.json()["user"] == {"username": "viewer", "role": "viewer"}
    assert len(exchange.json()["access_token"]) == 43
    insert = next(params for sql, params in statements if sql.startswith("INSERT INTO mobile_site_sessions"))
    assert insert[1] == "ha-viewer-001"
    revoke = client.post("/api/v1/mobile/session/revoke", headers=_bearer("admin"))
    assert revoke.status_code == 200 and revoke.json()["revoked"] is True
    assert client.get("/api/v1/mobile/session", headers=_bearer("admin")).status_code == 401


def test_exchange_proof_rejects_forgery_replay_and_policy_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions, _ = _mobile_client(monkeypatch)
    proof = proxy_io.signed_exchange_headers(EXCHANGE_HMAC_KEY, "ha-viewer-001", nonce="N" * 32)
    headers = {"X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **proof}
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 200
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 409
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 409
    forged = dict(headers)
    forged["X-Remote-User-Id"] = "ha-admin-0001"
    forged["X-Baiamonte-Mobile-Nonce"] = "M" * 32
    assert client.post("/api/v1/mobile/session/exchange", headers=forged).status_code == 401
    admin_hash = hashlib.sha256(TOKENS["admin"].encode()).hexdigest()
    sessions[admin_hash]["identity_version"] = 0
    assert client.get("/api/v1/mobile/session", headers=_bearer("admin")).status_code == 401


def test_exchange_proof_window_boundaries_are_inclusive_and_nonce_claim_is_timestamp_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, statements = _mobile_client(monkeypatch)
    monkeypatch.setattr(mobile_site_routes, "_unix_time", lambda: 2_000_000)
    for offset, nonce in ((-60, "P" * 32), (60, "Q" * 32)):
        proof = proxy_io.signed_exchange_headers(
            EXCHANGE_HMAC_KEY, "ha-viewer-001", timestamp=2_000_000 + offset, nonce=nonce,
        )
        response = client.post("/api/v1/mobile/session/exchange", headers={
            "X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **proof,
        })
        assert response.status_code == 200
    claims = [params for sql, params in statements if sql.startswith("INSERT IGNORE INTO mobile_site_exchange_nonces")]
    assert claims[0][2] == datetime.fromtimestamp(2_000_000, timezone.utc).replace(tzinfo=None)
    assert claims[1][2] == datetime.fromtimestamp(2_000_120, timezone.utc).replace(tzinfo=None)
    too_old = proxy_io.signed_exchange_headers(EXCHANGE_HMAC_KEY, "ha-viewer-001", timestamp=1_999_939, nonce="R" * 32)
    assert client.post("/api/v1/mobile/session/exchange", headers={
        "X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **too_old,
    }).status_code == 401


def test_exchange_final_fractional_second_uses_same_clock_for_validation_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, statements = _mobile_client(monkeypatch)
    monkeypatch.setattr(mobile_site_routes, "_unix_time", lambda: 2_000_060)
    proof = proxy_io.signed_exchange_headers(
        EXCHANGE_HMAC_KEY, "ha-viewer-001", timestamp=2_000_000, nonce="S" * 32,
    )
    headers = {"X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **proof}
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 200
    cleanup = [params for sql, params in statements if sql.startswith("DELETE FROM mobile_site_exchange_nonces")][-1]
    assert cleanup == (datetime.fromtimestamp(2_000_060, timezone.utc).replace(tzinfo=None),)
    assert all("UTC_TIMESTAMP" not in sql for sql, _params in statements if sql.startswith("DELETE FROM mobile_site_exchange_nonces"))

    monkeypatch.setattr(mobile_site_routes, "_unix_time", lambda: 2_000_061)
    expired = proxy_io.signed_exchange_headers(
        EXCHANGE_HMAC_KEY, "ha-viewer-001", timestamp=2_000_000, nonce="T" * 32,
    )
    assert client.post("/api/v1/mobile/session/exchange", headers={
        "X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **expired,
    }).status_code == 401


def test_exchange_expiring_while_waiting_rolls_back_nonce_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    proof = proxy_io.signed_exchange_headers(
        EXCHANGE_HMAC_KEY, "ha-viewer-001", timestamp=2_000_000, nonce="U" * 32,
    )
    headers = {"X-Ingress-Path": "/api/baiamonte_mobile/v1", "X-Remote-User-Id": "ha-viewer-001", **proof}
    observed_times = iter((2_000_060.0, 2_000_061.0))
    monkeypatch.setattr(mobile_site_routes, "_unix_time", lambda: int(next(observed_times)))
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 401

    # The failed delayed claim was rolled back; the same proof can still make
    # one legitimate claim while it is within the signed window.
    monkeypatch.setattr(mobile_site_routes, "_unix_time", lambda: 2_000_060)
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 200
    assert client.post("/api/v1/mobile/session/exchange", headers=headers).status_code == 409


def test_revoke_is_idempotent_and_independent_of_read_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    assert client.post("/api/v1/mobile/session/revoke", headers=_bearer("expired")).status_code == 200
    assert client.post("/api/v1/mobile/session/revoke", headers=_bearer("revoked_session")).status_code == 200
    assert client.post("/api/v1/mobile/session/revoke", headers=_bearer("revoked_session")).status_code == 200
    # This identity is disabled in current policy, but its known token remains revocable.
    assert client.post("/api/v1/mobile/session/revoke", headers=_bearer("revoked_identity")).status_code == 200
    monkeypatch.setattr(mobile_site_routes, "_enabled", lambda: (_ for _ in ()).throw(AssertionError("revoke must not require gateway enablement")))
    assert client.post("/api/v1/mobile/session/revoke", headers=_bearer("viewer")).status_code == 200


def test_read_adapter_minimizes_real_payload_dtos(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    status = client.get("/api/v1/mobile/status", headers=_bearer("admin"))
    assert status.status_code == 200 and status.json()["freshness"]["data_age_seconds"] is not None
    catalog = client.get("/api/v1/mobile/catalog", headers=_bearer("admin")).json()
    assert catalog["estate"] == {"name": "Tenuta Baiamonte", "location": "Etna", "year": 2026}
    assert "private" not in catalog["estate"]
    viewer_catalog = client.get("/api/v1/mobile/catalog", headers=_bearer("viewer")).json()
    assert viewer_catalog["containers"] == [{"id": "tank-1", "name": "Tank 1", "capacity_l": 1200}]
    assert viewer_catalog["varieties"] == [{"id": "variety-1", "name": "Nerello"}]
    for forbidden in ("volume_l", "fill_pct", "temperature_c", "density_sg"):
        assert forbidden not in viewer_catalog["containers"][0]
    for forbidden in ("planned_kg", "harvested_kg", "completion_pct"):
        assert forbidden not in viewer_catalog["varieties"][0]
    energy = client.get("/api/v1/mobile/energy", headers=_bearer("admin")).json()["energy"]
    assert "power_controls" not in energy and energy["current_power"] == 1200
    task = client.get("/api/v1/mobile/records?object=tasks", headers=_bearer("admin")).json()["items"][0]
    assert task == {"id": "task-1", "title": "Inspect", "status": "planned", "updated_at": "2026-11-01T10:00:00Z"}
    assert "secret" not in task and "revision" not in task
    cellar = client.get("/api/v1/mobile/records?object=cellar", headers=_bearer("admin")).json()["items"][0]
    assert cellar == {
        "id": "tank-1", "name": "Tank 1", "capacity_l": 1200, "volume_l": 800,
        "fill_pct": 66.7, "temperature_c": 18.2, "density_sg": 0.998,
        "observed_at": "2026-11-01T10:30:00Z",
    }
    display_source = (ROOT / "app/display_data.py").read_text(encoding="utf-8")
    assert '"generated_at": datetime.now(timezone.utc).isoformat()' in display_source
    assert '"SELECT id,title,category,status,priority,due_date,updated_at,"' in display_source


def test_weather_and_etna_freshness_use_source_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _mobile_client(monkeypatch)
    monkeypatch.setattr(mobile_site_routes, "weather_context_payload", lambda: {
        "current": {"observed_at": "2026-11-01T10:00:00Z", "temp_c": 18},
        "cache": {"refreshed_at": "2026-11-01T11:00:00Z", "status": "fresh"},
    })
    weather = client.get("/api/v1/mobile/weather", headers=_bearer("admin")).json()
    assert weather["freshness"]["source_generated_at"] == "2026-11-01T10:00:00+00:00"

    monkeypatch.setattr(mobile_site_routes, "etna_status", lambda: {
        "generated_at": datetime.now(timezone.utc).isoformat(), "last_complete_at": None,
        "expires_at": "2099-01-01T00:00:00Z", "errors": {"vona": "failed"},
        "source_status": {"vona": {"state": "unavailable"}},
    })
    failed = client.get("/api/v1/mobile/etna", headers=_bearer("admin")).json()
    assert failed["freshness"]["source_generated_at"] is None and failed["etna"]["fresh"] is False

    monkeypatch.setattr(mobile_site_routes, "etna_status", lambda: {
        "generated_at": datetime.now(timezone.utc).isoformat(), "last_complete_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": "2000-01-01T00:00:00Z", "errors": {},
        "source_status": {"vona": {"state": "current"}},
    })
    expired = client.get("/api/v1/mobile/etna", headers=_bearer("admin")).json()
    assert expired["etna"]["fresh"] is False


def test_adapter_routes_require_narrow_session_and_exchange_is_only_ha_identity_path() -> None:
    source = (ROOT / "app/domains/mobile_site_routes.py").read_text(encoding="utf-8")
    assert source.count("Depends(require_") == 9
    assert 'request.headers.get("X-Remote-User-Id")' in source
    assert "Depends(_app_session)" in source
    assert 'row.get("audience") != audience' in source
    assert 'entry.get("enabled") is not True' in source
    assert 'session_capabilities.issubset(identity["capabilities"])' in source
    assert '@router.post("/session/exchange")' in source
    assert '@router.post("/session/revoke")' in source
    assert "@router.put" not in source and "@router.patch" not in source and "@router.delete" not in source
    for forbidden in ("finance", "payroll", "camera", "service_call", "power_control", "3306"):
        assert forbidden not in source.casefold()
