from unittest.mock import patch

import pytest

from app.whatsapp_tanks import latest_tank_readings, list_tanks, parse_tank_command, save_tank_update, tank_history


def test_parses_explicit_english_and_italian_updates_without_confusing_babo_and_brix():
    english = parse_tank_command("UPDATE T-06 BABO 16.9 TEMP 18.4 VOLUME 1069.8 L")
    italian = parse_tank_command("Aggiorna vasca T-44 babbo 14,2 temperatura 17,5 volume 225 litri")
    assert english == {"action": "update", "tank_code": "T-06", "babo": 16.9, "temp_c": 18.4, "volume_l": 1069.8}
    assert italian == {"action": "update", "tank_code": "T-44", "babo": 14.2, "temp_c": 17.5, "volume_l": 225.0}
    assert parse_tank_command("UPDATE T-06 BRIX 16.9")["error"] == "missing_reading"
    assert parse_tank_command("T-06 16.9 18.4") == {"action": "update", "tank_code": "T-06", "babo": 16.9, "temp_c": 18.4, "volume_l": None}
    assert parse_tank_command("vasca T-44 14,2 17,5 225") == {"action": "update", "tank_code": "T-44", "babo": 14.2, "temp_c": 17.5, "volume_l": 225.0}


def test_list_commands_are_bilingual():
    assert parse_tank_command("LIST TANKS") == {"action": "list"}
    assert parse_tank_command("lista vasche") == {"action": "list"}
    assert parse_tank_command("HISTORY T-06 3 DAYS") == {"action": "history", "tank_code": "T-06", "days": 3}
    assert parse_tank_command("storico vasca T-44 5 giorni") == {"action": "history", "tank_code": "T-44", "days": 5}
    assert parse_tank_command("last T-06") == {"action": "history", "tank_code": "T-06", "days": 3}
    assert parse_tank_command("T-44 ultime") == {"action": "history", "tank_code": "T-44", "days": 3}


@patch("app.whatsapp_tanks.fetch_all")
def test_tank_list_includes_babo_temperature_volume_and_exact_code(fetch_all_mock):
    fetch_all_mock.return_value = [{"code": "T-06", "name": "Primary", "capacity_l": 2531.1, "volume_l": 1069.8, "babo": 16.9, "temp_c": 18.4, "lot_code": "GRC-2026", "reading_mode": "manual"}]
    result = list_tanks(False)
    assert "T-06" in result
    assert "Babo 16.9°" in result
    assert "18.4°C" in result
    assert "1069.8/2531.1 L" in result


@patch("app.whatsapp_tanks.fetch_all")
@patch("app.whatsapp_tanks.fetch_one")
def test_recent_history_lists_timestamped_babo_and_temperature(fetch_one_mock, fetch_all_mock):
    from datetime import datetime

    fetch_one_mock.return_value = {"id": "tank-id", "code": "T-06", "name": "Primary"}
    fetch_all_mock.return_value = [{"observed_at": datetime(2026, 9, 15, 18, 30), "babo": 16.9, "temp_c": 18.4, "status": "whatsapp"}]
    result = tank_history("T-06", 3, False)
    assert "15/09 18:30" in result
    assert "Babo 16.9°" in result
    assert "18.4°C" in result


@patch("app.whatsapp_tanks.fetch_all")
@patch("app.whatsapp_tanks.fetch_one")
def test_post_save_receipt_lists_three_latest_readings(fetch_one_mock, fetch_all_mock):
    from datetime import datetime

    fetch_one_mock.return_value = {"id": "tank-id", "code": "T-06", "name": "Primary"}
    fetch_all_mock.return_value = [
        {"observed_at": datetime(2026, 9, 15, 20, 0), "babo": 15.9, "temp_c": 19.1},
        {"observed_at": datetime(2026, 9, 15, 8, 0), "babo": 16.9, "temp_c": 18.4},
    ]
    result = latest_tank_readings("T-06", False)
    assert "Latest readings:" in result
    assert "15/09 20:00 · Babo 15.9° · 19.1°C" in result
    assert fetch_all_mock.call_args.args[1][-1] == 3


@patch("app.whatsapp_tanks.fetch_one")
def test_sensor_mode_and_ranges_are_rejected(fetch_one_mock):
    fetch_one_mock.return_value = {"id": "tank", "code": "T-06", "capacity_l": 500, "reading_mode": "sensor"}
    with pytest.raises(ValueError, match="automatic sensor mode"):
        save_tank_update({"tank_code": "T-06", "babo": 18, "temp_c": None, "volume_l": None}, "tester")
    fetch_one_mock.return_value = {"id": "tank", "code": "T-06", "capacity_l": 500, "reading_mode": "manual"}
    with pytest.raises(ValueError, match="Babo must be"):
        save_tank_update({"tank_code": "T-06", "babo": 55, "temp_c": None, "volume_l": None}, "tester")


def test_schema_keeps_babo_distinct_and_handler_refreshes_enology_pipeline():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    migration = (root / "db/migrations/153_whatsapp_tank_babo_pipeline.sql").read_text()
    handler = (root / "app/domains/communications_whatsapp_assistant.py").read_text()
    assert "ADD COLUMN IF NOT EXISTS babo" in migration
    assert "manual_babo" in migration
    assert "refresh_enology_additive_predictions" in handler
    assert "enology-prediction-refresh" in handler
    assert handler.index("tank_command = _parse_whatsapp_tank_command") < handler.index("_continue_whatsapp_submission_flow(sender")
    assert "_whatsapp_latest_tank_readings" in handler
