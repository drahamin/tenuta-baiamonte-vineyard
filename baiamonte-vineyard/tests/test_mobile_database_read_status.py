from datetime import date, datetime, timezone

import pytest

from app.domains import mobile_site_routes as mobile
from test_direct_site_gateways import _mobile_client, _bearer


@pytest.mark.parametrize("value", [
    "2026-11-04T11:59:00", "2026-11-04 11:59:00", datetime(2026, 11, 4, 11, 59),
    date(2026, 11, 4), "2026-11-04", None, "invalid",
])
def test_domain_clocks_never_borrow_session_utc_assumption(value):
    now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    freshness = mobile._freshness(value, now=now)
    assert freshness["source_generated_at"] is None
    assert freshness["data_age_seconds"] is None and freshness["stale"] is True
    assert mobile._latest_item_source_time([{"updated_at": value}], ("updated_at",)) is None


def test_aware_domain_offsets_normalize_but_future_clock_stays_unknown():
    now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    result = mobile._freshness("2026-11-04T12:59:00+01:00", now=now)
    assert result["source_generated_at"] == "2026-11-04T11:59:00+00:00" and result["data_age_seconds"] == 60
    assert mobile._freshness("2026-11-04T14:00:00+01:00", now=now)["data_age_seconds"] is None
    assert mobile._latest_item_source_time([
        {"updated_at": "2026-11-04T12:59:00+01:00"}, {"updated_at": "2099-01-01 00:00:00"}
    ], ("updated_at",)) == datetime(2026, 11, 4, 11, 59, tzinfo=timezone.utc)


def test_explicit_utc_session_writer_clock_is_unchanged():
    assert mobile._as_utc("2026-11-04 12:00:00") == datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    assert mobile._as_utc(datetime(2026, 11, 4, 12)) == datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("path,sources", [
    ("work", {"tasks"}), ("review", {"alerts", "issues", "labs"}), ("records?object=tasks", {"tasks"}),
])
def test_read_completion_is_independent_of_record_edit_or_sample_date(monkeypatch, path, sources):
    client, _, _ = _mobile_client(monkeypatch)
    rows = {"tasks": [{"id": "one", "title": "Unchanged work", "updated_at": "2026-11-04 11:59:00"}],
            "alerts": [], "issues": [], "labs": [{"id": "lab", "lab_date": "2026-11-04"}]}
    monkeypatch.setattr(mobile, "read_records", lambda kind, *_args: rows[kind])
    response = client.get("/api/v1/mobile/" + path, headers=_bearer("admin"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["freshness"]["source_generated_at"] is None and payload["freshness"]["stale"] is True
    status = payload["read_status"]
    assert set(status) == {"state", "completed_at", "timestamp_basis", "sources"}
    assert status["state"] == "completed" and status["timestamp_basis"] == "database_read_completion"
    assert datetime.fromisoformat(status["completed_at"]).utcoffset().total_seconds() == 0
    assert set(status["sources"]) == sources
    for kind, entry in status["sources"].items():
        assert entry == {"returned_count": len(rows[kind]), "limit": 50, "limit_reached": False}


def test_limit_hit_is_explicit_and_unauthorized_review_sources_are_not_reported(monkeypatch):
    client, _, _ = _mobile_client(monkeypatch)
    status = client.get("/api/v1/mobile/work?limit=1", headers=_bearer("admin")).json()["read_status"]
    assert status["sources"]["tasks"] == {"returned_count": 1, "limit": 1, "limit_reached": True}
    status = client.get("/api/v1/mobile/review", headers=_bearer("enologist")).json()["read_status"]
    assert set(status["sources"]) == {"issues", "labs"}


def test_source_failure_never_produces_a_completed_read_status(monkeypatch):
    client, _, _ = _mobile_client(monkeypatch)
    def fail(*_):
        raise mobile.ReportingSourceUnavailable("private error")
    monkeypatch.setattr(mobile, "read_records", fail)
    response = client.get("/api/v1/mobile/records?object=tasks", headers=_bearer("admin"))
    assert response.status_code == 503 and "read_status" not in response.json() and "private" not in response.text
