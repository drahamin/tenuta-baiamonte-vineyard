from unittest.mock import patch

import pytest

from app.whatsapp_tanks import _resolve_tank, latest_tank_readings, list_tanks, parse_natural_tank_command, parse_tank_command, save_tank_update, tank_history


def test_parses_explicit_english_and_italian_updates_without_confusing_babo_and_brix():
    english = parse_tank_command("UPDATE T-03 BABO 16.9 TEMP 18.4 VOLUME 1069.8 L")
    italian = parse_tank_command("Aggiorna vasca T-44 babbo 14,2 temperatura 17,5 volume 225 litri")
    assert english == {"action": "update", "tank_code": "T-03", "babo": 16.9, "temp_c": 18.4, "volume_l": 1069.8}
    assert italian == {"action": "update", "tank_code": "T-44", "babo": 14.2, "temp_c": 17.5, "volume_l": 225.0}
    assert parse_tank_command("UPDATE T-03 BRIX 16.9")["error"] == "missing_reading"
    assert parse_tank_command("T-03 16.9 18.4") == {"action": "update", "tank_code": "T-03", "babo": 16.9, "temp_c": 18.4, "volume_l": None}
    assert parse_tank_command("vasca T-44 14,2 17,5 225") == {"action": "update", "tank_code": "T-44", "babo": 14.2, "temp_c": 17.5, "volume_l": 225.0}


def test_list_commands_are_bilingual():
    assert parse_tank_command("LIST TANKS") == {"action": "list"}
    assert parse_tank_command("lista vasche") == {"action": "list"}
    assert parse_tank_command("HISTORY T-03 3 DAYS") == {"action": "history", "tank_code": "T-03", "days": 3}
    assert parse_tank_command("storico vasca T-44 5 giorni") == {"action": "history", "tank_code": "T-44", "days": 5}
    assert parse_tank_command("last T-03") == {"action": "history", "tank_code": "T-03", "days": 3}
    assert parse_tank_command("T-44 ultime") == {"action": "history", "tank_code": "T-44", "days": 3}


def test_natural_voice_and_text_notes_support_updates_and_history_without_guessing():
    assert parse_natural_tank_command("Tank 44 Babo is 5") == {
        "action": "update", "tank_code": "TANK:44", "babo": 5.0, "temp_c": None, "volume_l": None,
    }
    assert parse_natural_tank_command("tank 3 temp is 15") == {
        "action": "update", "tank_code": "TANK:3", "babo": None, "temp_c": 15.0, "volume_l": None,
    }
    assert parse_natural_tank_command("Registra vasca T trattino 06, babbo è 12,2, temperatura 18 e volume 1069,8") == {
        "action": "update", "tank_code": "T-03", "babo": 12.2, "temp_c": 18.0, "volume_l": 1069.8,
    }
    assert parse_natural_tank_command("What are the last readings for tank 44?") == {
        "action": "history", "tank_code": "TANK:44", "days": 3, "metrics": ["babo", "temp_c"],
    }
    assert parse_natural_tank_command("Show the history for tank T 06 for 5 days") == {
        "action": "history", "tank_code": "T-03", "days": 5, "metrics": ["babo", "temp_c"],
    }
    assert parse_natural_tank_command("tank 44 babo") == {
        "action": "history", "tank_code": "TANK:44", "days": 3, "metrics": ["babo"],
    }
    assert parse_natural_tank_command("tank 3 temp") == {
        "action": "history", "tank_code": "TANK:3", "days": 3, "metrics": ["temp_c"],
    }
    assert parse_natural_tank_command("Show all tanks") == {"action": "list"}
    assert parse_natural_tank_command("Tank 44 is doing fine") is None


def test_natural_tank_notes_route_before_freeform_ai_for_text_and_voice():
    from pathlib import Path

    handler = (Path(__file__).resolve().parents[1] / "app/domains/communications_whatsapp_assistant.py").read_text()
    assert "tank_command = _parse_natural_whatsapp_tank_command(body)" in handler
    assert handler.index("_parse_natural_whatsapp_tank_command(body)") < handler.index("whatsapp_chatbot_reply, body")


@patch("app.whatsapp_tanks.fetch_all")
def test_physical_tank_number_resolves_against_system_code_or_name(fetch_all_mock):
    fetch_all_mock.return_value = [{"id": "tank-3", "code": "T-03", "name": "Tank 3 · Grecanico 2026 · Primary", "capacity_l": 2531.1}]
    assert _resolve_tank("TANK:3") == fetch_all_mock.return_value[0]
    assert fetch_all_mock.call_args.args[1][1] == "T-03"


@patch("app.whatsapp_tanks.fetch_all")
def test_tank_list_includes_babo_temperature_volume_and_exact_code(fetch_all_mock):
    fetch_all_mock.return_value = [{"code": "T-03", "name": "Primary", "capacity_l": 2531.1, "volume_l": 1069.8, "babo": 16.9, "temp_c": 18.4, "lot_code": "GRC-2026", "reading_mode": "manual"}]
    result = list_tanks(False)
    assert "T-03" in result
    assert "Babo 16.9°" in result
    assert "18.4°C" in result
    assert "1069.8/2531.1 L" in result


@patch("app.whatsapp_tanks.fetch_all")
@patch("app.whatsapp_tanks.fetch_one")
def test_recent_history_lists_timestamped_babo_and_temperature(fetch_one_mock, fetch_all_mock):
    from datetime import datetime

    fetch_one_mock.return_value = {"id": "tank-id", "code": "T-03", "name": "Primary"}
    fetch_all_mock.return_value = [{"observed_at": datetime(2026, 9, 15, 18, 30), "babo": 16.9, "temp_c": 18.4, "status": "whatsapp"}]
    result = tank_history("T-03", 3, False)
    assert "15/09 18:30" in result
    assert "Babo 16.9°" in result
    assert "18.4°C" in result


@patch("app.whatsapp_tanks.fetch_all")
@patch("app.whatsapp_tanks.fetch_one")
def test_post_save_receipt_lists_three_latest_readings(fetch_one_mock, fetch_all_mock):
    from datetime import datetime

    fetch_one_mock.return_value = {"id": "tank-id", "code": "T-03", "name": "Primary"}
    fetch_all_mock.return_value = [
        {"observed_at": datetime(2026, 9, 15, 20, 0), "babo": 15.9, "temp_c": 19.1},
        {"observed_at": datetime(2026, 9, 15, 8, 0), "babo": 16.9, "temp_c": 18.4},
    ]
    result = latest_tank_readings("T-03", False)
    assert "Latest readings:" in result
    assert "15/09 20:00 · Babo 15.9° · 19.1°C" in result
    assert fetch_all_mock.call_args.args[1][-1] == 3


@patch("app.whatsapp_tanks.fetch_one")
def test_sensor_mode_and_ranges_are_rejected(fetch_one_mock):
    fetch_one_mock.return_value = {"id": "tank", "code": "T-03", "capacity_l": 500, "reading_mode": "sensor"}
    with pytest.raises(ValueError, match="automatic sensor mode"):
        save_tank_update({"tank_code": "T-03", "babo": 18, "temp_c": None, "volume_l": None}, "tester")
    fetch_one_mock.return_value = {"id": "tank", "code": "T-03", "capacity_l": 500, "reading_mode": "manual"}
    with pytest.raises(ValueError, match="Babo must be"):
        save_tank_update({"tank_code": "T-03", "babo": 55, "temp_c": None, "volume_l": None}, "tester")


def test_schema_keeps_babo_distinct_and_handler_refreshes_enology_pipeline():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    migration = (root / "db/migrations/153_whatsapp_tank_babo_pipeline.sql").read_text()
    handler = (root / "app/domains/communications_whatsapp_assistant.py").read_text()
    assert "ADD COLUMN IF NOT EXISTS babo" in migration
    assert "manual_babo" in migration
    assert "refresh_enology_additive_predictions" in handler
    assert "enology-prediction-refresh" in handler
    assert handler.index("tank_command = _parse_natural_whatsapp_tank_command") < handler.index("_continue_whatsapp_submission_flow(sender")
    assert "_whatsapp_latest_tank_readings" in handler
