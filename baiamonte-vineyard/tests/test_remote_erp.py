import base64
import asyncio
import gzip
import hashlib
import hmac
import json

import pytest

from app import remote_erp


def test_manifest_is_exact_and_excludes_sensitive_columns():
    assert len(remote_erp.REPORTING_OBJECTS) == 60
    assert len(set(remote_erp.REPORTING_OBJECTS)) == 60
    assert len(remote_erp.ALL_REPORTING_OBJECTS) == 61
    assert remote_erp.SYNTHETIC_REPORTING_OBJECTS == ("ro_etna_status",)
    assert "ro_inventory_current" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_packages" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_schedule" in remote_erp.REPORTING_OBJECTS
    assert "v_finance_document_totals" not in remote_erp.REPORTING_OBJECTS
    assert "password" in remote_erp.FORBIDDEN_COLUMN_FRAGMENTS
    assert "cost" in remote_erp.FORBIDDEN_COLUMN_FRAGMENTS
    assert "calibration_evidence" in remote_erp.EXPLICIT_EXCLUSIONS["gdd_forecasts"]


def test_etna_reporting_uses_existing_cache_and_omits_fetch_errors(monkeypatch):
    monkeypatch.setattr(remote_erp, "etna_status", lambda: {
        "generated_at": "2026-10-20T13:00:00+00:00", "fresh": False,
        "stale_sources": ["vaac"], "errors": {"vaac": "private transport detail"},
        "source_status": {"vaac": {"state": "stale"}}, "communications": [],
        "seismic_events": [], "webcams": [], "sources": {}, "activity": {},
    })
    result = remote_erp._etna_reporting_data()
    assert result["generated_at"] == "2026-10-20T13:00:00+00:00"
    assert result["stale_sources"] == ["vaac"]
    assert "errors" not in result


def test_snapshot_declares_release_contract(monkeypatch):
    monkeypatch.setenv("BUILD_VERSION", "1.11.3")
    monkeypatch.setattr(remote_erp, "addon_version", lambda: "9.9.9")
    assert remote_erp.source_app_version() == "1.11.3"
    assert remote_erp.REMOTE_ERP_CONTRACT_VERSION == 1


def test_snapshot_version_fallback_uses_packaged_manifest(monkeypatch):
    monkeypatch.delenv("BUILD_VERSION", raising=False)
    monkeypatch.setattr(remote_erp, "addon_version", lambda: "1.11.3")
    assert remote_erp.source_app_version() == "1.11.3"


def test_pressure_guard_is_database_free(monkeypatch):
    monkeypatch.setattr(remote_erp.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(remote_erp.os, "getloadavg", lambda: (5.0, 1.0, 1.0))
    assert remote_erp._source_pressure_reason() == "host load is elevated"


def test_key_validation_requires_exact_256_bit_base64url():
    secret = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    config.validate()
    assert remote_erp._public_config(config)["secret_configured"] is True
    assert "secret" not in remote_erp._public_config(config)
    with pytest.raises(ValueError):
        remote_erp.RemoteERPConfig(True, "http://example.test/erp", "vineyard-1", secret, 15).validate()
    with pytest.raises(ValueError):
        remote_erp.RemoteERPConfig(True, "https://example.test/erp", "vineyard-1", "short", 15).validate()


def test_signed_transport_uses_textual_owner_handoff_key(monkeypatch):
    secret = base64.urlsafe_b64encode(b"z" * 32).decode().rstrip("=")
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b'{"ok":true}'

    def open_request(request, timeout):
        captured["request"], captured["timeout"] = request, timeout
        return Response()

    monkeypatch.setattr(remote_erp, "urlopen", open_request)
    monkeypatch.setattr(remote_erp.time, "time", lambda: 1_700_000_000)
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    payload = {"snapshot_id": "00000000-0000-4000-8000-000000000001", "records": []}
    assert remote_erp._signed_post(config, "/sync/snapshots", payload)["ok"] is True
    request = captured["request"]
    expected = hmac.new(secret.encode(), b"1700000000\n" + request.data, hashlib.sha256).hexdigest()
    assert request.full_url == "https://cantinabaiamonte.com/erp/sync/snapshots"
    assert request.headers["X-baiamonte-signature"] == "sha256=" + expected
    assert request.headers["Content-encoding"] == "gzip"
    assert request.headers["X-baiamonte-uncompressed-length"] == str(len(remote_erp._canonical(payload).encode()))
    assert json.loads(gzip.decompress(request.data)) == payload
    assert captured["timeout"] == 180


def test_remote_camera_config_is_separate_and_allowlist_is_exact():
    secret = base64.urlsafe_b64encode(b"c" * 32).decode().rstrip("=")
    config = remote_erp.RemoteCameraConfig(True, "https://cantinabaiamonte.com/erp", "baiamonte-camera-1", secret, 5)
    config.validate()
    assert len(remote_erp.CAMERA_ALLOWLIST) == 12
    assert "camera.cisterna" in remote_erp.CAMERA_ALLOWLIST
    assert "camera.192_168_0_54" not in remote_erp.CAMERA_ALLOWLIST
    assert config.poll_seconds == 5


def test_camera_metadata_poll_is_one_request_and_short_timeout(monkeypatch):
    secret = base64.urlsafe_b64encode(b"c" * 32).decode().rstrip("=")
    config = remote_erp.RemoteCameraConfig(True, "https://cantinabaiamonte.com/erp", "baiamonte-camera-1", secret, 5)
    captured = []

    def signed_post(*args):
        captured.append(args)
        return {"ok": True, "requests": []}

    monkeypatch.setattr(remote_erp, "_signed_post", signed_post)
    assert asyncio.run(remote_erp._process_one_camera_request(config, "supervisor-secret")) == 0
    assert captured == [(config, "/sync/camera-requests", {"limit": 1}, 10)]


def test_sign_camera_path_uses_core_auth_sign_path_without_leaking_token(monkeypatch):
    sent = []

    class Socket:
        replies = iter([
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
            json.dumps({"id": 1, "type": "result", "success": True, "result": {"path": "/api/camera_proxy/camera.vineyard_north?authSig=" + "a" * 48}}),
        ])
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def recv(self): return next(self.replies)
        async def send(self, value): sent.append(json.loads(value))

    monkeypatch.setattr(remote_erp.websockets, "connect", lambda *_args, **_kwargs: Socket())
    result = asyncio.run(remote_erp._sign_camera_path("camera.vineyard_north", "supervisor-secret"))
    assert result.startswith("/api/camera_proxy/camera.vineyard_north?authSig=")
    assert sent[0] == {"type": "auth", "access_token": "supervisor-secret"}
    assert sent[1] == {"id": 1, "type": "auth/sign_path", "path": "/api/camera_proxy/camera.vineyard_north", "expires": 30}
    assert "supervisor-secret" not in result


def test_reporting_revision_and_locked_record_match_snapshot_rules(monkeypatch):
    row = {"id": "task-1", "estate_id": "estate-1", "status": "planned", "updated_at": None}

    class Cursor:
        def execute(self, sql, parameters):
            assert "FOR UPDATE" in sql
            assert parameters == ("task-1", "estate-1")
        def fetchone(self): return row

    monkeypatch.setattr(remote_erp, "_safe_columns", lambda _cursor: {"tasks": list(row), "issues_decisions": []})
    data, revision = remote_erp.locked_reporting_record(Cursor(), "tasks", "task-1", "estate-1")
    assert data == row
    assert revision == remote_erp.reporting_row_revision(row)
    assert revision == int.from_bytes(hashlib.sha256(remote_erp._canonical(row).encode()).digest()[:8], "big") >> 1


def test_command_consumer_applies_conflicts_and_rejects_strictly(monkeypatch):
    secret = base64.urlsafe_b64encode(b"q" * 32).decode().rstrip("=")
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    commands = [
        {"command_id": "10000000-0000-4000-8000-000000000001", "command_type": "record.create", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000001", "expected_revision": None, "payload": {"title": "Inspect block", "status": "planned"}},
        {"command_id": "10000000-0000-4000-8000-000000000002", "command_type": "record.update", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000002", "expected_revision": 7, "payload": {"status": "done"}},
        {"command_id": "10000000-0000-4000-8000-000000000005", "command_type": "record.update", "object": "issues_decisions", "record_id": "issue-1", "expected_revision": 11, "payload": {"status": "monitoring", "notes": "Check after rain"}},
        {"command_id": "10000000-0000-4000-8000-000000000003", "command_type": "record.update", "object": "wine_lots", "record_id": "lot-1", "expected_revision": 2, "payload": {"notes": "unsafe generic edit"}},
    ]
    results = []

    def signed_post(_config, path, payload, _timeout=180):
        if path == "/sync/commands":
            return {"ok": True, "commands": commands}
        results.append(payload)
        return {"ok": True}

    def local_request(method, path, payload, headers):
        assert headers["X-Baiamonte-Command-ID"].startswith("10000000-")
        if path.endswith("/status"):
            assert method == "PATCH" and headers["X-Baiamonte-Expected-Revision"] == "7"
            raise remote_erp.RemoteCommandConflict({"reason": "revision_conflict", "actual_revision": 8})
        if path == "/api/v1/issues/issue-1":
            assert method == "PATCH" and headers["X-Baiamonte-Expected-Revision"] == "11"
            return {"saved": True, "id": "issue-1"}
        assert method == "POST" and path.startswith("/api/v1/tasks?year=") and payload["title"] == "Inspect block"
        return {"id": headers["X-Baiamonte-Record-ID"]}

    monkeypatch.setattr(remote_erp, "_signed_post", signed_post)
    monkeypatch.setattr(remote_erp, "_local_domain_request", local_request)
    assert remote_erp.process_remote_commands_once(config) == 4
    assert [item["status"] for item in results] == ["applied", "conflict", "applied", "rejected"]
    assert results[1]["result"]["actual_revision"] == 8
    assert results[3]["result"] == {"reason": "unsupported_domain_command"}


def test_command_consumer_leaves_transient_failures_for_lease_retry(monkeypatch):
    secret = base64.urlsafe_b64encode(b"r" * 32).decode().rstrip("=")
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    command = {"command_id": "10000000-0000-4000-8000-000000000004", "command_type": "record.create", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000004", "expected_revision": None, "payload": {"title": "Retry safely"}}
    posted = []

    def signed_post(_config, path, payload, _timeout=180):
        if path == "/sync/commands": return {"commands": [command]}
        posted.append(payload); return {"ok": True}

    monkeypatch.setattr(remote_erp, "_signed_post", signed_post)
    monkeypatch.setattr(remote_erp, "_local_domain_request", lambda *_args: (_ for _ in ()).throw(RuntimeError("temporary local outage")))
    with pytest.raises(RuntimeError, match="temporary local outage"):
        remote_erp.process_remote_commands_once(config)
    assert posted == []
