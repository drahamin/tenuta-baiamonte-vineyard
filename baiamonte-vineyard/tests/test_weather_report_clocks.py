"""Synthetic report-clock regressions; no HA, database or network calls."""
from datetime import datetime, timedelta, timezone
import pytest
from app.ha_entities import home_assistant_state_is_fresh

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def item(stamp=None):
    result = {"state": "0"}
    if stamp is not None:
        result["last_reported"] = stamp
    return result


@pytest.mark.parametrize("stamp", [None, "", "2026-11-04", "2026-11-04T12:00:00", "bad", "2026-02-30T12:00:00Z"])
def test_unknown_naive_date_only_and_invalid_never_fresh(stamp):
    assert not home_assistant_state_is_fresh(item(stamp), now=NOW)


def test_real_zero_and_offset_report():
    assert home_assistant_state_is_fresh(item("2026-11-04T12:59:00+01:00"), now=NOW)


def test_report_time_keeps_unchanged_value_current():
    value = item("2026-11-04T11:59:00Z")
    value["last_updated"] = "2026-11-03T00:00:00Z"
    assert home_assistant_state_is_fresh(value, now=NOW)


@pytest.mark.parametrize("seconds,expected", [(600, True), (601, False), (-1, False)])
def test_exact_age_boundary_and_future(seconds, expected):
    assert home_assistant_state_is_fresh(item((NOW-timedelta(seconds=seconds)).isoformat()), now=NOW) is expected


def test_naive_validation_clock_is_not_guessed():
    assert not home_assistant_state_is_fresh(item("2026-11-04T11:59:00Z"), now=NOW.replace(tzinfo=None))


def test_unavailable_is_not_a_zero_reading():
    value = item("2026-11-04T11:59:00Z")
    value["state"] = "unavailable"
    assert not home_assistant_state_is_fresh(value, now=NOW)
