import base64
import asyncio
import gzip
import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app import remote_erp


def light_expiry(seconds: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")


def test_manifest_is_exact_and_excludes_sensitive_columns():
    assert len(remote_erp.REPORTING_OBJECTS) == 60
    assert len(set(remote_erp.REPORTING_OBJECTS)) == 60
    assert len(remote_erp.ALL_REPORTING_OBJECTS) == 63
    assert remote_erp.SYNTHETIC_REPORTING_OBJECTS == ("ro_etna_status", "olive_harvests", "ro_light_status")
    assert "ro_inventory_current" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_packages" in remote_erp.REPORTING_OBJECTS
    assert "ro_hospitality_schedule" in remote_erp.REPORTING_OBJECTS
    assert "ro_mobile_directory" not in remote_erp.REPORTING_OBJECTS
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


def test_olive_harvest_projection_is_explicit_private_and_preserves_unknown_dates(monkeypatch):
    class Cursor:
        def execute(self, sql, parameters):
            normalized = " ".join(sql.lower().split())
            assert normalized == (
                "select id,estate_id,record_year,record_date,activity,status,"
                "olives_harvested_kg,mill_date,oil_liters,yield_pct "
                "from olive_records where estate_id=%s order by id"
            )
            assert parameters == ("00000000-0000-4000-8000-000000000001",)
            for excluded in ("worker_text", "labor_hours", "notes", "evidence", "cost"):
                assert excluded not in normalized

        def fetchall(self):
            return [{
                "id": "olive-1",
                "estate_id": "00000000-0000-4000-8000-000000000001",
                "record_year": 2026,
                "record_date": None,
                "activity": "harvest",
                "status": "recorded",
                "olives_harvested_kg": 720,
                "mill_date": None,
                "oil_liters": None,
                "yield_pct": None,
            }]

    monkeypatch.setattr(remote_erp, "get_settings", lambda: type("Settings", (), {
        "estate_id": "00000000-0000-4000-8000-000000000001",
    })())
    records = remote_erp._olive_harvest_reporting_records(Cursor())
    assert len(records) == 1
    assert records[0]["object"] == "olive_harvests"
    assert records[0]["id"] == "olive-1"
    assert records[0]["source_updated_at"] is None
    assert records[0]["data"]["record_date"] is None
    assert records[0]["data"]["mill_date"] is None
    assert isinstance(records[0]["revision"], int)
    assert set(records[0]["data"]) == {
        "estate_id", "record_year", "record_date", "activity", "status",
        "olives_harvested_kg", "mill_date", "oil_liters", "yield_pct",
    }


def test_light_status_projection_is_exact_and_attribute_free(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self):
            return json.dumps([
                {"entity_id": "light.switch_1_lightbulb", "state": "on", "last_updated": "2026-11-01T10:00:00+00:00", "attributes": {"brightness": 99}},
                {"entity_id": "switch.generator", "state": "on", "last_updated": "2026-11-01T10:00:00+00:00"},
            ]).encode()
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "urlopen", lambda request, timeout: Response())
    records = remote_erp._light_status_reporting_records()
    assert len(records) == 8
    first = next(item for item in records if item["id"] == "light.switch_1_lightbulb")
    assert first["data"] == {"entity_id": "light.switch_1_lightbulb", "name": "Kitchen overhead", "state": "on", "observed_at": "2026-11-01T10:00:00+00:00"}
    assert all(item["id"] in remote_erp.LIGHT_ALLOWLIST for item in records)
    assert "switch.generator" not in json.dumps(records)


def test_snapshot_declares_release_contract(monkeypatch):
    monkeypatch.setenv("BUILD_VERSION", "1.11.3")
    monkeypatch.setattr(remote_erp, "addon_version", lambda: "9.9.9")
    assert remote_erp.source_app_version() == "1.11.3"
    assert remote_erp.REMOTE_ERP_CONTRACT_VERSION == 1


def test_restricted_intake_release_builds_contract_one_snapshot_without_directory(monkeypatch):
    executed = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, parameters=None):
            executed.append((sql, parameters))
            self.sql = sql
        def fetchall(self):
            if "information_schema.columns" in self.sql:
                return [{"table_name": name, "column_name": "id"} for name in remote_erp.REPORTING_OBJECTS]
            if "information_schema.statistics" in self.sql:
                return [{"table_name": name, "column_name": "id"} for name in remote_erp.REPORTING_OBJECTS]
            return []

    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def rollback(self): raise AssertionError("snapshot should not roll back")
        def close(self): pass

    monkeypatch.setattr(remote_erp, "connect", lambda: Connection())
    monkeypatch.setattr(remote_erp, "_etna_reporting_data", lambda: {"generated_at": None})
    monkeypatch.setattr(remote_erp, "_olive_harvest_reporting_records", lambda _cursor: [])
    monkeypatch.setattr(remote_erp, "_light_status_reporting_records", lambda: [])
    snapshot = remote_erp.build_snapshot()
    assert snapshot["remote_contract_version"] == 1
    assert snapshot["record_count"] == 1
    assert snapshot["records"][0]["object"] == "ro_etna_status"
    assert all("ro_mobile_directory" not in str(item) for item in executed)


def test_command_consumer_targets_authoritative_application_port():
    assert remote_erp.AUTHORITATIVE_API_BASE_URL == "http://127.0.0.1:8099"


def test_light_control_is_exact_david_allowlisted_on_off_and_postcondition_checked(monkeypatch):
    observations = iter([("off", "2026-11-01T10:00:00+00:00"), ("on", "2026-11-01T10:00:01+00:00")])
    calls = []
    events = {}
    def start(command_id, fingerprint, actor, entity, expected, desired):
        events.setdefault(command_id, {"request_fingerprint": fingerprint, "entity_id": entity, "expected_state": expected, "desired_state": desired, "terminal_status": None, "result": None})
        return events[command_id]
    def finish(command_id, fingerprint, actor, entity, expected, desired, status, result):
        events[command_id] = {"request_fingerprint": fingerprint, "entity_id": entity, "expected_state": expected, "desired_state": desired, "terminal_status": status, "result": result}
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: next(observations))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda entity, desired, token: calls.append((entity, desired, token)))
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: events.get(command_id))
    monkeypatch.setattr(remote_erp, "_light_event_start", start)
    monkeypatch.setattr(remote_erp, "_light_event_finish", finish)
    command = {
        "command_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_1_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "on", "expected_state": "off", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    result = remote_erp._apply_remote_command(command)
    assert result == {"entity_id": "light.switch_1_lightbulb", "observed_state": "on", "observed_at": "2026-11-01T10:00:01+00:00"}
    assert calls == [("light.switch_1_lightbulb", "on", "supervisor-token")]
    # Simulate a lost /sync/results response: the website retries the same UUID,
    # HA replays its durable applied result without calling the service again.
    assert remote_erp._apply_remote_command(command) == result
    assert calls == [("light.switch_1_lightbulb", "on", "supervisor-token")]
    assert events[command["command_id"]]["terminal_status"] == "applied"


def test_light_control_rejects_other_actor_entity_and_arbitrary_fields(monkeypatch):
    base = {
        "command_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_2_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    with pytest.raises(remote_erp.RemoteCommandRejected):
        remote_erp._apply_remote_command(base | {"actor_username": "other"})
    with pytest.raises(remote_erp.RemoteCommandRejected):
        remote_erp._apply_remote_command(base | {"record_id": "light.unapproved"})
    with pytest.raises(remote_erp.RemoteCommandRejected):
        remote_erp._apply_remote_command(base | {"payload": base["payload"] | {"service": "toggle"}})


def test_light_control_reconciles_crash_after_physical_change(monkeypatch):
    command = {
        "command_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_3_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    fingerprint = hashlib.sha256(remote_erp._canonical({"actor": "david", "entity_id": command["record_id"], "payload": command["payload"]}).encode()).hexdigest()
    event = {"request_fingerprint": fingerprint, "entity_id": command["record_id"], "expected_state": "on", "desired_state": "off", "terminal_status": None, "result": None}
    finished = []
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: event)
    monkeypatch.setattr(remote_erp, "_light_event_finish", lambda *args: finished.append(args))
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: ("off", "2026-11-01T10:00:01+00:00"))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda *args: pytest.fail("reconciliation must not call the service twice"))
    result = remote_erp._apply_remote_command(command)
    assert result == {"entity_id": command["record_id"], "observed_state": "off", "observed_at": "2026-11-01T10:00:01+00:00", "reconciled": True}
    assert finished and finished[0][6] == "applied"


def test_light_control_fresh_request_conflicts_if_state_already_changed_to_desired(monkeypatch):
    command = {
        "command_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_3_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    finished = []
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: None)
    monkeypatch.setattr(remote_erp, "_light_event_start", lambda command_id, fingerprint, actor, entity, expected, desired: {"request_fingerprint": fingerprint, "entity_id": entity, "expected_state": expected, "desired_state": desired, "terminal_status": None, "result": None})
    monkeypatch.setattr(remote_erp, "_light_event_finish", lambda *args: finished.append(args))
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: ("off", "2026-11-01T10:00:01+00:00"))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda *args: pytest.fail("a fresh stale-state conflict must not call the service"))
    with pytest.raises(remote_erp.RemoteCommandConflict) as conflict:
        remote_erp._apply_remote_command(command)
    assert conflict.value.result == {"reason": "light_state_changed", "actual_state": "off", "observed_at": "2026-11-01T10:00:01+00:00"}
    assert finished and finished[0][6] == "conflict"


def test_light_control_rejects_aba_observation_change_and_distant_expiry(monkeypatch):
    base = {
        "command_id": "12121212-1212-4121-8121-121212121212", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_4_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    finished = []
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: None)
    monkeypatch.setattr(remote_erp, "_light_event_start", lambda command_id, fingerprint, actor, entity, expected, desired: {"request_fingerprint": fingerprint, "terminal_status": None, "result": None})
    monkeypatch.setattr(remote_erp, "_light_event_finish", lambda *args: finished.append(args))
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: ("on", "2026-11-01T10:00:02+00:00"))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda *args: pytest.fail("ABA observation mismatch must not call a service"))
    with pytest.raises(remote_erp.RemoteCommandConflict) as conflict:
        remote_erp._apply_remote_command(base)
    assert conflict.value.result["reason"] == "light_observation_changed"
    distant = base | {"command_id": "13131313-1313-4131-8131-131313131313", "payload": base["payload"] | {"expires_at": light_expiry(300)}}
    with pytest.raises(remote_erp.RemoteCommandRejected, match="light_request_expiry_invalid"):
        remote_erp._apply_remote_command(distant)


def test_light_control_resumed_uncertain_command_never_calls_service(monkeypatch):
    command = {
        "command_id": "14141414-1414-4141-8141-141414141414", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_5_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T10:00:00+00:00", "expires_at": light_expiry()},
    }
    fingerprint = hashlib.sha256(remote_erp._canonical({"actor": "david", "entity_id": command["record_id"], "payload": command["payload"]}).encode()).hexdigest()
    event = {"request_fingerprint": fingerprint, "terminal_status": None, "result": None}
    finished = []
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: event)
    monkeypatch.setattr(remote_erp, "_light_event_finish", lambda *args: finished.append(args))
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: ("on", "2026-11-01T10:00:00+00:00"))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda *args: pytest.fail("an incomplete durable UUID must never be actuated again"))
    with pytest.raises(remote_erp.RemoteCommandRejected, match="light_command_outcome_uncertain"):
        remote_erp._apply_remote_command(command)
    assert finished and finished[0][6] == "rejected"


def test_light_control_rechecks_expiry_immediately_before_service(monkeypatch):
    base_time = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    class AdvancingDateTime(datetime):
        calls = 0
        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            value = base_time if cls.calls == 1 else base_time + timedelta(seconds=31)
            return value if tz is None else value.astimezone(tz)
    command = {
        "command_id": "15151515-1515-4151-8151-151515151515", "command_type": "light.control", "object": "ha_light",
        "record_id": "light.switch_6_lightbulb", "expected_revision": None,
        "actor_username": "david", "actor_role": "admin", "actor_enabled": True,
        "payload": {"desired_state": "off", "expected_state": "on", "expected_observed_at": "2026-11-01T09:59:59+00:00", "expires_at": "2026-11-01 10:00:30.000000"},
    }
    monkeypatch.setattr(remote_erp, "datetime", AdvancingDateTime)
    monkeypatch.setattr(remote_erp, "runtime_option", lambda key, default=None: {"remote_light_control_enabled": True, "remote_light_owner_username": "david"}.get(key, default))
    monkeypatch.setattr(remote_erp, "home_assistant_token", lambda: "supervisor-token")
    monkeypatch.setattr(remote_erp, "_light_event_payload", lambda command_id: None)
    monkeypatch.setattr(remote_erp, "_light_event_start", lambda command_id, fingerprint, actor, entity, expected, desired: {"request_fingerprint": fingerprint, "terminal_status": None, "result": None})
    monkeypatch.setattr(remote_erp, "_light_event_finish", lambda *args: None)
    monkeypatch.setattr(remote_erp, "_light_observation", lambda entity, token: ("on", "2026-11-01T09:59:59+00:00"))
    monkeypatch.setattr(remote_erp, "_set_light_state", lambda *args: pytest.fail("an expired command must not call the service"))
    with pytest.raises(remote_erp.RemoteCommandRejected, match="light_request_expired"):
        remote_erp._apply_remote_command(command)


def test_light_result_delivery_failure_retries_durable_terminal_result(monkeypatch):
    secret = base64.urlsafe_b64encode(b"r" * 32).decode().rstrip("=")
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    pending = [{"command_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "status": "applied", "result": {"entity_id": "light.switch_4_lightbulb", "observed_state": "on"}}]
    marked = []
    attempts = []
    monkeypatch.setattr(remote_erp, "_pending_light_results", lambda limit=10: list(pending))
    monkeypatch.setattr(remote_erp, "_mark_light_result_delivered", lambda command_id: (marked.append(command_id), pending.clear()))
    def fail_delivery(*args):
        attempts.append(args[1])
        raise RuntimeError("lost result response")
    monkeypatch.setattr(remote_erp, "_signed_post", fail_delivery)
    with pytest.raises(RuntimeError):
        remote_erp.process_remote_commands_once(config)
    assert marked == [] and attempts == ["/sync/results"]
    def succeed(*args):
        attempts.append(args[1])
        return {"ok": True, "commands": []}
    monkeypatch.setattr(remote_erp, "_signed_post", succeed)
    assert remote_erp.process_remote_commands_once(config) == 0
    assert marked == ["dddddddd-dddd-4ddd-8ddd-dddddddddddd"]
    assert attempts[-2:] == ["/sync/results", "/sync/commands"]


def test_light_result_delivery_marker_uses_schema_permitted_status(monkeypatch):
    statements = []
    class Cursor:
        def execute(self, sql, params):
            statements.append((sql, params))
        def fetchone(self):
            return {"id": 7, "payload": json.dumps({"terminal_status": "applied", "result_delivered": False})}
    @contextmanager
    def fake_transaction():
        yield object(), Cursor()
    monkeypatch.setattr(remote_erp, "transaction", fake_transaction)
    monkeypatch.setattr(remote_erp, "get_settings", lambda: type("Settings", (), {"estate_id": "estate-1"})())
    remote_erp._mark_light_result_delivered("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
    update_sql, update_params = statements[-1]
    assert "status='ignored'" in update_sql
    assert json.loads(update_params[0])["result_delivered"] is True


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
        {"command_id": "10000000-0000-4000-8000-000000000002", "command_type": "record.update", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000002", "expected_revision": "7", "payload": {"status": "done"}},
        {"command_id": "10000000-0000-4000-8000-000000000005", "command_type": "record.update", "object": "issues_decisions", "record_id": "issue-1", "expected_revision": "11", "payload": {"status": "monitoring", "notes": "Check after rain"}},
        {"command_id": "10000000-0000-4000-8000-000000000003", "command_type": "record.update", "object": "wine_lots", "record_id": "lot-1", "expected_revision": 2, "payload": {"notes": "unsafe generic edit"}},
        {"command_id": "10000000-0000-4000-8000-000000000006", "command_type": "record.create", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000006", "expected_revision": None, "payload": {"title": "Viewer attempt"}, "actor_username": "viewer", "actor_role": "viewer", "actor_enabled": True},
    ]
    for command in commands[:4]:
        command.update(actor_username="configured-owner", actor_role="admin", actor_enabled=True)
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
    monkeypatch.setattr(remote_erp, "_pending_light_results", lambda limit=10: [])
    assert remote_erp.process_remote_commands_once(config) == 5
    assert [item["status"] for item in results] == ["applied", "conflict", "applied", "rejected", "rejected"]
    assert results[1]["result"]["actual_revision"] == 8
    assert results[3]["result"] == {"reason": "unsupported_domain_command"}
    assert results[4]["result"] == {"reason": "actor_not_authorized"}


def test_command_consumer_leaves_transient_failures_for_lease_retry(monkeypatch):
    secret = base64.urlsafe_b64encode(b"r" * 32).decode().rstrip("=")
    config = remote_erp.RemoteERPConfig(True, "https://cantinabaiamonte.com/erp", "vineyard-1", secret, 15)
    command = {"command_id": "10000000-0000-4000-8000-000000000004", "command_type": "record.create", "object": "tasks", "record_id": "20000000-0000-4000-8000-000000000004", "expected_revision": None, "payload": {"title": "Retry safely"}, "actor_username": "configured-owner", "actor_role": "admin", "actor_enabled": True}
    posted = []

    def signed_post(_config, path, payload, _timeout=180):
        if path == "/sync/commands": return {"commands": [command]}
        posted.append(payload); return {"ok": True}

    monkeypatch.setattr(remote_erp, "_signed_post", signed_post)
    monkeypatch.setattr(remote_erp, "_local_domain_request", lambda *_args: (_ for _ in ()).throw(RuntimeError("temporary local outage")))
    monkeypatch.setattr(remote_erp, "_pending_light_results", lambda limit=10: [])
    with pytest.raises(RuntimeError, match="temporary local outage"):
        remote_erp.process_remote_commands_once(config)
    assert posted == []


def test_command_consumer_maps_only_narrow_manual_tank_reading(monkeypatch):
    command = {
        "command_id": "10000000-0000-4000-8000-000000000007",
        "command_type": "record.update", "object": "cellar_control_profiles",
        "record_id": "20000000-0000-4000-8000-000000000007", "expected_revision": "9007199254740993",
        "payload": {"babo": 7.5, "observed_at": "2026-10-20T18:15", "notes": "Manual hydrometer reading"},
        "actor_username": "configured-owner", "actor_role": "admin", "actor_enabled": True,
    }
    captured = {}

    def local_request(method, path, payload, headers):
        captured.update(method=method, path=path, payload=payload, headers=headers)
        return {"saved": True}

    monkeypatch.setattr(remote_erp, "_local_domain_request", local_request)
    assert remote_erp._apply_remote_command(command) == {"saved": True}
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/tank-profiles/20000000-0000-4000-8000-000000000007/reading")
    assert captured["headers"]["X-Baiamonte-Expected-Revision"] == "9007199254740993"
    assert captured["headers"]["X-Remote-User-Name"] == "configured-owner"
    assert "temp_c" not in captured["payload"]


@pytest.mark.parametrize("payload", [
    {"babo": 7.5},
    {"observed_at": "2026-10-20T18:15"},
    {"babo": 7.5, "observed_at": "2026-10-20T18:15", "volume_l": 100},
])
def test_command_consumer_rejects_incomplete_or_broad_tank_edits(payload):
    command = {
        "command_id": "10000000-0000-4000-8000-000000000008",
        "command_type": "record.update", "object": "cellar_control_profiles",
        "record_id": "20000000-0000-4000-8000-000000000008", "expected_revision": 17,
        "payload": payload, "actor_username": "configured-owner", "actor_role": "admin", "actor_enabled": True,
    }
    with pytest.raises(remote_erp.RemoteCommandRejected):
        remote_erp._apply_remote_command(command)


@pytest.mark.parametrize("revision", [True, -1, "-1", "01", "1.0", "9223372036854775808"])
def test_command_consumer_rejects_invalid_revision_encodings(revision):
    command = {
        "command_id": "10000000-0000-4000-8000-000000000009",
        "command_type": "record.update", "object": "cellar_control_profiles",
        "record_id": "20000000-0000-4000-8000-000000000009", "expected_revision": revision,
        "payload": {"babo": 7.5, "observed_at": "2026-10-20T18:15"},
        "actor_username": "configured-owner", "actor_role": "admin", "actor_enabled": True,
    }
    with pytest.raises(remote_erp.RemoteCommandRejected):
        remote_erp._apply_remote_command(command)
