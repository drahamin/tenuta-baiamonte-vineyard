from unittest.mock import MagicMock, patch

from app import intelligence


def test_inactive_condition_alerts_resolve_rows_and_home_assistant_cards():
    cursor = MagicMock()
    cursor.execute.return_value = 1
    context = MagicMock()
    context.__enter__.return_value = (None, cursor)
    rows = [
        {"id": "keep", "source_id": "weather:heat"},
        {"id": "clear", "source_id": "weather:rain"},
        {"id": "other", "source_id": "event:manual"},
    ]
    with (
        patch.object(intelligence, "fetch_all", return_value=rows),
        patch.object(intelligence, "transaction", return_value=context),
        patch.object(intelligence, "estate_id", return_value="estate"),
        patch.object(intelligence, "_dismiss_ha_alert_notification") as dismiss,
    ):
        resolved = intelligence.resolve_inactive_condition_alerts(
            "weather", {"weather:heat"}, source_prefix="weather:"
        )

    assert resolved == 1
    cursor.execute.assert_called_once()
    assert cursor.execute.call_args.args[1] == ("clear", "estate")
    dismiss.assert_called_once_with("weather", "weather:rain")


def test_filtered_condition_rule_resolves_an_existing_alert():
    with (
        patch.object(intelligence, "alert_preference", return_value={"enabled": 0, "min_severity": "warning"}),
        patch.object(intelligence, "resolve_condition_alert", return_value=1) as resolve,
    ):
        opened = intelligence.upsert_condition_alert(
            "weather", "warning", "Heat", "Details", "weather:heat"
        )

    assert opened is False
    resolve.assert_called_once_with("weather", "weather:heat")
