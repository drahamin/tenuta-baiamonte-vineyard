from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import intelligence


ROOT = Path(__file__).resolve().parents[1]


def test_scheduler_uses_latest_inserted_event_and_clamps_legacy_future_clock():
    future=datetime(2026,11,1,0,49,58)
    with (
        patch.object(intelligence,"estate_id",return_value="estate-1"),
        patch.object(intelligence,"fetch_all",return_value=[{"integration_name":"estate-energy-learning","occurred_at":future}]) as fetch,
    ):
        restored=intelligence._persisted_process_last_runs(datetime(2026,10,31,23,50,0))
    sql=fetch.call_args.args[0]
    assert "MAX(id)" in sql
    assert "MAX(occurred_at)" not in sql
    assert restored["energy"]==datetime(2026,10,31,23,50,0)


def test_scheduler_records_completion_with_explicit_utc_database_time():
    cursor=MagicMock()
    @contextmanager
    def transaction():
        yield MagicMock(),cursor
    with (
        patch.object(intelligence,"transaction",transaction),
        patch.object(intelligence,"estate_id",return_value="estate-1"),
    ):
        intelligence._record_scheduled_integration("estate-energy-learning","processed",{"recorded":True})
    sql=cursor.execute.call_args.args[0]
    assert "occurred_at" in sql
    assert "UTC_TIMESTAMP(6)" in sql


def test_scheduler_clock_is_explicit_utc_not_host_local_time():
    class FixedDatetime:
        @classmethod
        def now(cls, zone=None):
            assert zone is timezone.utc
            return datetime(2026, 11, 1, 0, 4, 15, tzinfo=timezone.utc)

    with patch.object(intelligence, "datetime", FixedDatetime):
        assert intelligence._scheduler_utc_now() == datetime(2026, 11, 1, 0, 4, 15)


def test_home_assistant_states_use_last_complete_snapshot_on_transient_failure():
    cached = [{"entity_id": "camera.gate", "state": "idle"}]
    previous = intelligence._ha_states_cache
    intelligence._ha_states_cache = (0.0, cached)
    try:
        with (
            patch.object(intelligence, "home_assistant_token", return_value="token"),
            patch("app.intelligence.urllib.request.urlopen", side_effect=OSError("HTTP Error 502: Bad Gateway")),
        ):
            assert intelligence._ha_get("/states") == cached
    finally:
        intelligence._ha_states_cache = previous


def test_home_assistant_states_degrade_to_empty_before_first_success():
    previous = intelligence._ha_states_cache
    intelligence._ha_states_cache = None
    try:
        with (
            patch.object(intelligence, "home_assistant_token", return_value="token"),
            patch("app.intelligence.urllib.request.urlopen", side_effect=OSError("HTTP Error 502: Bad Gateway")),
        ):
            assert intelligence._ha_get("/states") == []
    finally:
        intelligence._ha_states_cache = previous


def test_home_assistant_history_retries_transient_supervisor_gateway_errors():
    response = type("Response", (), {
        "__enter__": lambda self: self,
        "__exit__": lambda self, *args: None,
        "read": lambda self: b"[]",
    })()
    gateway_error = intelligence.urllib.error.HTTPError("url", 502, "Bad Gateway", {}, None)
    with (
        patch.object(intelligence, "home_assistant_token", return_value="token"),
        patch.object(intelligence.time, "sleep"),
        patch("app.intelligence.urllib.request.urlopen", side_effect=[gateway_error, response]) as urlopen,
    ):
        assert intelligence._ha_get("/history/period/2026-10-08") == []
    assert urlopen.call_count == 2


def test_gmail_poll_bounds_mailbox_and_retries_only_one_transient_failed_intake():
    source = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
    assert "GMAIL_RECENT_MESSAGE_WINDOW = 50" in source
    assert "GMAIL_NEW_MESSAGE_BUDGET = 8" in source
    assert "BODY.PEEK[HEADER.FIELDS" in source
    assert "LIKE '%%overload%%'" in source
    assert "i.updated_at<DATE_SUB(NOW(),INTERVAL 10 MINUTE)" in source
    assert "LIMIT 1" in source


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "dashboards" / "vineyard-overview.yaml",
        ROOT.parent / "dashboard" / "tenuta-baiamonte-dashboard-integrated.yaml",
    ],
)
def test_weather_radar_uses_keyless_openstreetmap_basemap(path: Path):
    text = path.read_text(encoding="utf-8")
    marker = "type: custom:weather-radar-card"
    block = text[text.index(marker) : text.index(marker) + 500]
    assert "map_style: OSM" in block
    assert "map_style: Dark" not in block
