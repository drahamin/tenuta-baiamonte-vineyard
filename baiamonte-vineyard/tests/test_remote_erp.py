import base64
import gzip
import hashlib
import hmac
import json

import pytest

from app import remote_erp


def test_manifest_is_exact_and_excludes_sensitive_columns():
    assert len(remote_erp.REPORTING_OBJECTS) == 60
    assert len(set(remote_erp.REPORTING_OBJECTS)) == 60
    assert "ro_inventory_current" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_packages" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_schedule" in remote_erp.REPORTING_OBJECTS
    assert "v_finance_document_totals" not in remote_erp.REPORTING_OBJECTS
    assert "password" in remote_erp.FORBIDDEN_COLUMN_FRAGMENTS
    assert "cost" in remote_erp.FORBIDDEN_COLUMN_FRAGMENTS


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
