from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.mcp_server import record_sebastiano_tank_reading


COMMON = {
    "platform_message_id": "3EB0-EXACT-MESSAGE",
    "observed_at": "2026-10-16T08:15:00+02:00",
    "source_text": "Grenache 9 Babo 24 C",
    "babo": 9,
    "temp_c": 24,
    "confirmation": "RECORD SEBASTIANO TANK READING",
}


@patch("app.mcp_server.require_write_confirmation")
def test_sebastiano_tool_rejects_wrong_source_or_pre_cutoff(require_confirmation):
    with pytest.raises(ValueError, match="exact direct chat"):
        record_sebastiano_tank_reading(**COMMON, chat_id="other@s.whatsapp.net")
    with pytest.raises(ValueError, match="does not apply before"):
        record_sebastiano_tank_reading(**{**COMMON, "observed_at": "2026-10-15T23:59:59+02:00"})


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.fetch_one")
def test_sebastiano_tool_deduplicates_by_system_account_and_message_id(fetch_one, require_confirmation):
    fetch_one.return_value = {"id": "reading-existing", "observed_at": datetime(2026, 10, 16, 8, 15), "wine_lot_id": "lot-1"}
    result = record_sebastiano_tank_reading(**COMMON)
    assert result["duplicate"] is True
    assert result["reading_id"] == "reading-existing"
    assert "whatsapp-system:1:" in fetch_one.call_args.args[1][1]


@patch("app.mcp_server.require_write_confirmation")
@patch("app.mcp_server.audit")
@patch("app.mcp_server.new_id", return_value="reading-new")
@patch("app.mcp_server.transaction")
@patch("app.mcp_server.fetch_one")
def test_sebastiano_tool_preserves_exact_metadata_and_defaults_to_grenache(fetch_one, transaction, new_id, audit, require_confirmation):
    fetch_one.side_effect = [
        None,
        {"id": "lot-2", "code": "GRN-2026-02", "stage": "fermentation", "variety_summary": "Grenache"},
        {"id": "tank-39", "code": "T-39", "name": "Tank 39"},
    ]
    cursor = MagicMock()

    @contextmanager
    def tx():
        yield None, cursor

    transaction.side_effect = tx
    result = record_sebastiano_tank_reading(**COMMON)

    assert result["recorded"] is True
    assert result["tank_code"] == "T-39"
    assert result["lot_code"] == "GRN-2026-02"
    assert result["platform_message_id"] == COMMON["platform_message_id"]
    assert result["source_text"] == COMMON["source_text"]
    assert cursor.execute.call_count == 2
    insert_values = cursor.execute.call_args_list[0].args[1]
    assert insert_values[2] == "lot-2"
    assert insert_values[5] == "Tank 39"
    assert insert_values[9] == COMMON["source_text"]
    audit.assert_called_once()
