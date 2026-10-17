import json
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.mcp_server import record_wendy_apple_messages_tank_reading


COMMON = {
    "message_guid": "A1B2C3D4-E5F6-APPLE-MESSAGE",
    "message_at": "2026-10-17T09:30:00-04:00",
    "source_text": "Tank 39 Babo 4; no temperature today",
    "babo": 4,
    "confirmation": "RECORD WENDY TANK READING",
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
def test_wendy_tool_rejects_wrong_source_identity_and_historical_backfill(require_confirmation):
    with pytest.raises(ValueError, match="verified one-to-one Apple Messages identity"):
        record_wendy_apple_messages_tank_reading(**COMMON, sender_handle="+10000000000")
    with pytest.raises(ValueError, match="native Apple Messages"):
        record_wendy_apple_messages_tank_reading(**COMMON, source_channel="personal_whatsapp")
    with pytest.raises(ValueError, match="prospective from 2026-10-17"):
        record_wendy_apple_messages_tank_reading(**{**COMMON, "message_at": "2026-10-16T23:59:00+02:00"})


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.fetch_one")
def test_wendy_tool_deduplicates_by_message_guid(fetch_one, require_confirmation):
    fetch_one.return_value = {
        "id": "reading-existing",
        "observed_at": datetime(2026, 10, 17, 15, 30),
        "temp_c": None,
        "babo": 4,
        "status": "apple_messages",
        "lot_code": "GRN-2026-02",
    }
    result = record_wendy_apple_messages_tank_reading(**COMMON)
    assert result["duplicate"] is True
    assert result["duplicate_basis"] == "message_guid"
    assert "apple-messages:" in fetch_one.call_args.args[1][1]


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.audit")
@patch("app.mcp_server.new_id", return_value="reading-wendy")
@patch("app.mcp_server.transaction")
@patch("app.mcp_server.fetch_one")
def test_wendy_tool_preserves_apple_provenance_optional_temperature_and_readback(
    fetch_one, transaction, new_id, audit, require_confirmation
):
    readback = {
        "reading_id": "reading-wendy",
        "source_observation_id": "apple-messages:hash",
        "observed_at": datetime(2026, 10, 17, 15, 30),
        "vessel_name": LINKAGE["tank_name"],
        "stage": "fermentation",
        "temp_c": None,
        "babo": 4,
        "owner_text": "Wendy Creque · Apple Messages",
        "status": "apple_messages",
        "lot_code": "GRN-2026-02",
        "tank_code": "T-39",
    }
    fetch_one.side_effect = [None, LINKAGE, None, readback]
    cursor = MagicMock()

    @contextmanager
    def tx():
        yield None, cursor

    transaction.side_effect = tx
    result = record_wendy_apple_messages_tank_reading(**COMMON)

    assert result["recorded"] is True
    assert result["details"]["sender_handle"] == "+17863938580"
    assert result["details"]["contact_identifier"].endswith(":ABPerson")
    assert result["details"]["temp_c"] is None
    assert result["readback"]["status"] == "apple_messages"
    insert_values = cursor.execute.call_args_list[0].args[1]
    assert insert_values[7] is None
    assert insert_values[8] == 4.0
    payload = json.loads(cursor.execute.call_args_list[1].args[1][2])
    assert payload["source"] == "apple_messages"
    assert payload["temperature_unit"] is None
    audit.assert_called_once()
