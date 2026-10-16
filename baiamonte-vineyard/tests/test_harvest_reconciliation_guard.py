from datetime import date, datetime
from unittest.mock import patch

import pytest

from app.mcp_server import _harvest_reconciliation


def _plan(status: str = "complete") -> dict:
    return {
        "id": "plan-1",
        "variety_id": "variety-1",
        "variety": "Grecanico",
        "planned_pick_date": date(2026, 9, 9),
        "planned_kg": 1833.351,
        "planned_crates": None,
        "status": status,
        "confidence": "high",
        "forecast_method": "completed harvest record overrides forecast",
        "updated_at": datetime(2026, 10, 15, 12, 0),
    }


def _actual() -> dict:
    return {
        "variety_id": "variety-1",
        "variety": "Grecanico",
        "first_pick_date": date(2026, 9, 9),
        "last_pick_date": date(2026, 9, 9),
        "actual_estate_kg": 2299.53,
        "actual_other_source_kg": 0,
        "actual_total_kg": 2299.53,
        "actual_lot_count": 1,
        "actual_total_lot_count": 1,
        "first_recorded_at": datetime(2026, 9, 9, 18, 0),
        "latest_recorded_at": datetime(2026, 9, 9, 18, 0),
    }


@patch("app.mcp_server.fetch_all")
def test_completed_plan_remains_explained_by_actual_evidence(fetch_all) -> None:
    fetch_all.side_effect = [[_plan()], [_actual()]]

    result = _harvest_reconciliation("season-2026")

    assert result["states"][0]["state"] == "completed_with_actual"
    assert result["states"][0]["actual_estate_kg"] == 2299.53
    assert result["anomalies"] == []
    assert result["correction_required"] is True
    assert "earlier forecast is closed" in result["short_correction"]


@patch("app.mcp_server.fetch_all")
def test_completion_keeps_estate_and_purchased_fruit_separate(fetch_all) -> None:
    actual = _actual()
    actual.update(actual_estate_kg=399.25, actual_other_source_kg=1078.0, actual_total_kg=1477.25, actual_total_lot_count=2)
    fetch_all.side_effect = [[{**_plan(), "variety": "Grenache"}], [actual]]

    result = _harvest_reconciliation("season-2026")

    state = result["states"][0]
    assert state["actual_estate_kg"] == 399.25
    assert state["actual_other_source_kg"] == 1078.0
    assert state["actual_total_kg"] == 1477.25
    assert "including 1,078.00 kg non-estate fruit" in result["short_correction"]


@patch("app.mcp_server.fetch_all")
def test_completed_plan_without_actual_is_flagged_and_not_treated_as_complete(fetch_all) -> None:
    fetch_all.side_effect = [[_plan()], []]

    result = _harvest_reconciliation("season-2026")

    assert result["states"][0]["state"] == "completion_missing_actual_anomaly"
    assert result["correction_required"] is True
    assert "Do not report it as completed or scheduled" in result["short_correction"]


@patch("app.mcp_server.fetch_all")
def test_changed_since_prevents_duplicate_completion_correction(fetch_all) -> None:
    fetch_all.side_effect = [[_plan()], [_actual()]]

    result = _harvest_reconciliation("season-2026", "2026-10-15T12:01:00")

    assert result["states"][0]["state"] == "completed_with_actual"
    assert result["material_changes"] == []
    assert result["correction_required"] is False
    assert result["short_correction"] is None


def test_changed_since_must_be_iso_timestamp() -> None:
    with pytest.raises(ValueError, match="ISO-8601"):
        _harvest_reconciliation("season-2026", "not-a-date")
