import json
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.mcp_server import record_user_dictated_tank_reading


COMMON = {
    "source_reference": "chat-message-01M54EXAMPLE",
    "sample_at": "2026-10-17T10:30:00+02:00",
    "original_text": "Tank 39 is 5 Babo; no temperature supplied",
    "babo": 5,
    "confirmation": "RECORD DICTATED TANK READING",
}


LINKAGE = {
    "wine_lot_id": "lot-grenache",
    "lot_code": "GRN-2026-02",
    "stage": "fermentation",
    "lot_status": "active",
    "current_container_id": "tank-39",
    "tank_id": "tank-39",
    "tank_code": "T-39",
    "tank_name": "Tank 39 · Purchased Grenache 2026",
    "tank_status": "in_use",
    "tank_active": 1,
}


@patch("app.mcp_server.require_write_confirmation")
def test_dictated_tool_rejects_historical_or_timezone_free_sample_time(require_confirmation):
    with pytest.raises(ValueError, match="must include a timezone"):
        record_user_dictated_tank_reading(**{**COMMON, "sample_at": "2026-10-17T10:30:00"})
    with pytest.raises(ValueError, match="prospective from 2026-10-17"):
        record_user_dictated_tank_reading(**{**COMMON, "sample_at": "2026-10-16T23:59:59+02:00"})


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.fetch_one")
def test_dictated_tool_deduplicates_by_stable_source_reference(fetch_one, require_confirmation):
    fetch_one.return_value = {
        "id": "reading-existing",
        "observed_at": datetime(2026, 10, 17, 10, 30),
        "temp_c": None,
        "babo": 5,
        "status": "user_dictated",
        "lot_code": "GRN-2026-02",
    }
    result = record_user_dictated_tank_reading(**COMMON)
    assert result["recorded"] is False
    assert result["duplicate"] is True
    assert result["duplicate_basis"] == "source_reference"
    assert "chatgpt-dictation:" in fetch_one.call_args.args[1][1]


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.audit")
@patch("app.mcp_server.new_id", return_value="reading-new")
@patch("app.mcp_server.transaction")
@patch("app.mcp_server.fetch_one")
def test_dictated_tool_records_babo_without_inventing_temperature_and_reads_back(
    fetch_one, transaction, new_id, audit, require_confirmation
):
    readback = {
        "reading_id": "reading-new",
        "source_observation_id": "chatgpt-dictation:hash",
        "observed_at": datetime(2026, 10, 17, 10, 30),
        "vessel_name": LINKAGE["tank_name"],
        "stage": "fermentation",
        "temp_c": None,
        "babo": 5,
        "owner_text": "David Rahamin · dictated to ChatGPT (voice)",
        "status": "user_dictated",
        "lot_code": "GRN-2026-02",
        "tank_code": "T-39",
    }
    fetch_one.side_effect = [None, LINKAGE, None, readback]
    cursor = MagicMock()

    @contextmanager
    def tx():
        yield None, cursor

    transaction.side_effect = tx
    result = record_user_dictated_tank_reading(
        **COMMON,
        source_kind="voice",
        sample_time_basis="message_time",
    )

    assert result["recorded"] is True
    assert result["readback"]["reading_id"] == "reading-new"
    assert result["readback"]["temp_c"] is None
    assert result["details"]["temperature_unit"] is None
    assert result["details"]["sample_time_basis"] == "message_time"
    insert_values = cursor.execute.call_args_list[0].args[1]
    assert insert_values[7] is None
    assert insert_values[8] == 5.0
    payload = json.loads(cursor.execute.call_args_list[1].args[1][2])
    assert payload["temp_c"] is None
    assert payload["babo_unit"] == "°Babo"
    audit.assert_called_once()


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.fetch_one")
def test_dictated_tool_rejects_unconfirmed_tank_link_change(fetch_one, require_confirmation):
    fetch_one.side_effect = [None, {**LINKAGE, "current_container_id": "tank-other"}]
    with pytest.raises(ValueError, match="not currently linked"):
        record_user_dictated_tank_reading(**COMMON)


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.fetch_one")
def test_dictated_tool_deduplicates_same_actor_time_and_values(fetch_one, require_confirmation):
    fetch_one.side_effect = [
        None,
        LINKAGE,
        {
            "id": "reading-repeat",
            "source_observation_id": "older-source",
            "observed_at": datetime(2026, 10, 17, 10, 30),
            "temp_c": None,
            "babo": 5,
            "status": "user_dictated",
            "lot_code": "GRN-2026-02",
        },
    ]
    result = record_user_dictated_tank_reading(**COMMON)
    assert result["recorded"] is False
    assert result["duplicate"] is True
    assert result["duplicate_basis"] == "same_actor_sample_time_and_values"
