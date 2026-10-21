from contextlib import contextmanager
import json
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

from app.domains import cellar_routes


COMMAND_ID = "10000000-0000-4000-8000-000000000009"
PROFILE_ID = "20000000-0000-4000-8000-000000000009"


def command_request(expected: int = 23) -> Request:
    headers = {
        "X-API-Key": "local-secret", "X-Baiamonte-Command-ID": COMMAND_ID,
        "X-Baiamonte-Record-ID": PROFILE_ID, "X-Baiamonte-Expected-Revision": str(expected),
        "X-Remote-User-Name": "configured-owner",
    }
    return Request({
        "type": "http", "method": "POST", "path": f"/api/v1/agronomy/tank-profiles/{PROFILE_ID}/reading",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 8099), "scheme": "http",
        "query_string": b"",
    })


class Cursor:
    def __init__(self, update_count: int = 1, prior_reads=None, traced_lot=None, current_lot=None):
        self.update_count = update_count
        self.prior_reads = iter(prior_reads or [None, None])
        self.traced_lot = traced_lot
        self.current_lot = current_lot or {
            "id": "wine-1", "stage": "fermentation", "started_at": "2026-10-20T09:00:00",
        }
        self.last_sql = ""
        self.executed = []

    def execute(self, sql, parameters=()):
        self.last_sql = sql
        self.executed.append((sql, parameters))
        if sql.startswith("UPDATE cellar_control_profiles"):
            return self.update_count
        return 1

    def fetchone(self):
        if "FROM audit_events" in self.last_sql:
            prior = next(self.prior_reads, None)
            return None if prior is None else {"after_data": json.dumps({"result": prior})}
        if "FROM cellar_containers" in self.last_sql:
            return {"id": "tank-1", "code": "T-01", "name": "Tank 1"}
        if "FROM wine_lots w WHERE" in self.last_sql:
            return self.current_lot
        if "FROM cellar_lot_trace_records" in self.last_sql:
            return self.traced_lot
        return None


def install(monkeypatch, cursor: Cursor, revision: int = 23, mode: str = "manual", profile_time: str = "2026-10-20T17:00:00"):
    monkeypatch.setattr(cellar_routes, "get_settings", lambda: SimpleNamespace(api_key="local-secret"))
    monkeypatch.setattr(cellar_routes, "estate_id", lambda: "estate-1")
    monkeypatch.setattr(cellar_routes, "new_id", lambda: "30000000-0000-4000-8000-000000000009")
    monkeypatch.setattr(cellar_routes, "locked_reporting_record", lambda *_args: ({
        "id": PROFILE_ID, "estate_id": "estate-1", "container_id": "tank-1",
        "reading_mode": mode, "manual_reading_at": profile_time,
    }, revision))
    monkeypatch.setattr(cellar_routes, "audit", lambda *args: None)

    @contextmanager
    def transaction():
        yield None, cursor
    monkeypatch.setattr(cellar_routes, "transaction", transaction)


def test_babo_only_preserves_unknown_temperature_and_appends_attributed_history(monkeypatch):
    cursor = Cursor()
    install(monkeypatch, cursor)
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "babo": 7.5, "observed_at": "2026-10-20T18:15", "notes": "Manual hydrometer reading",
    })
    assert result["current_profile_updated"] is True
    update = next(parameters for sql, parameters in cursor.executed if sql.startswith("UPDATE cellar_control_profiles"))
    assert update[0] is None
    assert update[1] == 7.5
    history = next(parameters for sql, parameters in cursor.executed if sql.startswith("INSERT INTO fermentation_observations"))
    assert history[3] == COMMAND_ID
    assert history[7] is None
    assert history[8] == 7.5
    assert history[9] == "Manual hydrometer reading"
    assert history[10] == "configured-owner"


def test_backdated_reading_appends_history_without_replacing_current_profile(monkeypatch):
    cursor = Cursor(update_count=0, traced_lot={
        "id": "historical-wine", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
        "current_container_id": "other-tank", "next_transfer_at": "2026-10-20T12:00:00",
    })
    install(monkeypatch, cursor)
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "temp_c": 19, "observed_at": "2026-10-19T08:00", "notes": "Entered from dated cellar notes",
    })
    assert result["current_profile_updated"] is False
    history = next(parameters for sql, parameters in cursor.executed if sql.startswith("INSERT INTO fermentation_observations"))
    assert history[2] == "historical-wine"


def test_newer_reading_before_current_lot_start_uses_dated_tank_occupancy(monkeypatch):
    cursor = Cursor(
        traced_lot={
            "id": "prior-wine", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
            "current_container_id": "other-tank", "next_transfer_at": "2026-10-20T12:00:00",
        },
        current_lot={"id": "new-wine", "stage": "fermentation", "started_at": "2026-10-20T12:00:00"},
    )
    install(monkeypatch, cursor, profile_time="2026-10-20T09:00:00")
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "babo": 7.8, "observed_at": "2026-10-20T10:00", "notes": "Before the current lot entered",
    })
    assert result["current_profile_updated"] is False
    history = next(parameters for sql, parameters in cursor.executed if sql.startswith("INSERT INTO fermentation_observations"))
    assert history[2] == "prior-wine"


def test_departed_lot_without_a_proven_end_is_not_attributed(monkeypatch):
    cursor = Cursor(
        traced_lot={
            "id": "departed-wine", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
            "current_container_id": "other-tank", "next_transfer_at": None,
        },
        current_lot={"id": "new-wine", "stage": "fermentation", "started_at": "2026-10-20T12:00:00"},
    )
    install(monkeypatch, cursor, profile_time="2026-10-20T09:00:00")
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "temp_c": 18.5, "observed_at": "2026-10-20T10:00",
    })
    assert result["current_profile_updated"] is False
    history = next(parameters for sql, parameters in cursor.executed if sql.startswith("INSERT INTO fermentation_observations"))
    assert history[2] is None


def test_current_lot_uses_tank_entry_time_not_original_lot_start(monkeypatch):
    cursor = Cursor(
        traced_lot={
            "id": "prior-wine", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
            "current_container_id": "other-tank", "next_transfer_at": "2026-10-20T12:00:00",
        },
        current_lot={
            "id": "new-wine", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
            "current_container_started_at": "2026-10-20T12:00:00",
        },
    )
    install(monkeypatch, cursor, profile_time="2026-10-20T09:00:00")
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "babo": 7.7, "observed_at": "2026-10-20T10:00",
    })
    assert result["current_profile_updated"] is False
    history = next(parameters for sql, parameters in cursor.executed if sql.startswith("INSERT INTO fermentation_observations"))
    assert history[2] == "prior-wine"


def test_same_tank_addition_does_not_reset_continuous_occupancy_start(monkeypatch):
    cursor = Cursor(current_lot={
        "id": "wine-1", "stage": "fermentation", "started_at": "2026-10-01T00:00:00",
        "current_container_started_at": "2026-10-20T09:00:00",
    })
    install(monkeypatch, cursor, profile_time="2026-10-20T08:00:00")
    result = cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "temp_c": 18.7, "observed_at": "2026-10-20T10:00",
    })
    assert result["current_profile_updated"] is True
    current_query = next(sql for sql, _ in cursor.executed if "FROM wine_lots w WHERE" in sql)
    assert "NOT EXISTS" in current_query
    assert "ORDER BY tr.transferred_at,tr.id LIMIT 1" in current_query


def test_stale_revision_conflicts_before_any_business_write(monkeypatch):
    cursor = Cursor()
    install(monkeypatch, cursor, revision=24)
    try:
        cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(expected=23), {
            "babo": 8, "observed_at": "2026-10-20T18:15",
        })
    except HTTPException as error:
        assert error.status_code == 409
        assert error.detail["actual_revision"] == 24
    else:
        raise AssertionError("stale revision was applied")
    assert not any(sql.startswith(("UPDATE cellar_control_profiles", "INSERT INTO fermentation_observations")) for sql, _ in cursor.executed)


def test_retry_returns_durable_result_without_duplicate_history(monkeypatch):
    prior = {"saved": True, "id": "existing-reading", "current_profile_updated": True}
    cursor = Cursor(prior_reads=[prior])
    install(monkeypatch, cursor)
    assert cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "babo": 8, "observed_at": "2026-10-20T18:15",
    }) == prior
    assert not any(sql.startswith("INSERT INTO fermentation_observations") for sql, _ in cursor.executed)


def test_concurrent_retry_is_rechecked_after_profile_lock(monkeypatch):
    prior = {"saved": True, "id": "winning-reading", "current_profile_updated": True}
    cursor = Cursor(prior_reads=[None, prior])
    install(monkeypatch, cursor)
    assert cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
        "temp_c": 20, "observed_at": "2026-10-20T18:15",
    }) == prior
    assert not any(sql.startswith("INSERT INTO fermentation_observations") for sql, _ in cursor.executed)
    audit_reads = [sql for sql, _ in cursor.executed if "FROM audit_events" in sql]
    assert len(audit_reads) == 2 and not audit_reads[0].endswith("FOR UPDATE") and audit_reads[1].endswith("FOR UPDATE")


def test_remote_reading_rejects_sensor_profiles_and_missing_dates(monkeypatch):
    cursor = Cursor()
    install(monkeypatch, cursor, mode="sensor")
    try:
        cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
            "babo": 8, "observed_at": "2026-10-20T18:15",
        })
    except HTTPException as error:
        assert error.status_code == 409
    else:
        raise AssertionError("sensor profile accepted a manual remote reading")
    try:
        cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {"babo": 8})
    except HTTPException as error:
        assert error.status_code == 422
    else:
        raise AssertionError("missing observation timestamp was inferred")
    try:
        cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
            "babo": 8, "observed_at": "2026-10-20",
        })
    except HTTPException as error:
        assert error.status_code == 422
    else:
        raise AssertionError("date-only reading was accepted without an actual time")


def test_offset_timestamp_is_normalized_to_existing_rome_cellar_time():
    observed = cellar_routes._remote_reading_time("2026-10-20T18:15:00Z")
    assert observed.isoformat() == "2026-10-20T20:15:00"


def test_future_timestamp_is_rejected_before_any_write(monkeypatch):
    cursor = Cursor()
    install(monkeypatch, cursor)
    try:
        cellar_routes.save_remote_manual_tank_reading(PROFILE_ID, command_request(), {
            "babo": 8, "observed_at": "2099-10-20T18:15",
        })
    except HTTPException as error:
        assert error.status_code == 422
        assert "future" in str(error.detail).casefold()
    else:
        raise AssertionError("future reading was accepted")
    assert cursor.executed == []
