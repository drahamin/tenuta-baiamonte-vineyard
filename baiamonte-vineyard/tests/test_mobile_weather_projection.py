from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from app.domains.mobile_weather_projection import (
    WeatherProjectionForbidden, WeatherReadEvidence, project_station_weather,
)

ESTATE = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
VERIFIED = WeatherReadEvidence(True, True, True, True, "measured", NOW, NOW, NOW, "current")


def project(*, evidence=VERIFIED, **values):
    row = {"estate_id": ESTATE, "source_object": "weather_observations",
           "observed_at": NOW, "temp_c": Decimal("18.5"),
           "rain_rate_mm_h": 0, "wind_kph": 7, "wind_gust_kph": 11, **values}
    return project_station_weather(row, estate_id=ESTATE, role="admin",
                                   capabilities=frozenset({"weather"}), now=NOW, evidence=evidence)


def test_typed_measurements_and_real_zero_without_private_fields():
    result = project(entity_id="private_entity", notes="private_note", condition="invented")
    assert result["weather"]["state"] == "current"
    assert result["weather"]["temperature"] == {"value": 18.5, "unit": "celsius"}
    assert result["weather"]["rain"]["value"] == 0
    assert result["weather"]["wind"]["gust"] == 11
    assert result["weather"]["condition"] is None
    assert result["forecast"] == []
    assert "private_" not in json.dumps(result)


@pytest.mark.parametrize("changes", [
    {"estate_boundary_verified": False}, {"permitted_columns_verified": False},
    {"observation_clock_verified": False}, {"shared_metric_clock_verified": False},
    {"measurement_kind": "forecast"}, {"measurement_kind": None},
])
def test_evidence_gates_default_closed(changes):
    result = project(evidence=replace(VERIFIED, **changes))
    assert result["weather"]["state"] == "unavailable"
    assert result["weather"]["observed_at"] is None
    assert result["weather"]["temperature"]["value"] is None


def test_default_evidence_and_foreign_estate_never_leak():
    assert project(evidence=WeatherReadEvidence())["weather"]["state"] == "unavailable"
    assert project(estate_id="22222222-2222-4222-8222-222222222222")["weather"]["state"] == "unavailable"
    assert project(source_object="weather_daily")["weather"]["state"] == "unavailable"


@pytest.mark.parametrize("observed", [None, "2026-11-04", "2026-11-04 12:00:00", "bad",
                                      NOW.replace(tzinfo=None), NOW + timedelta(seconds=1)])
def test_missing_naive_or_future_measurement_time_is_never_fetch_time(observed):
    result = project(observed_at=observed)
    assert result["weather"]["observed_at"] is None
    assert result["weather"]["temperature"]["value"] is None
    assert result["source"]["data_age_seconds"] is None


@pytest.mark.parametrize("value", [None, True, "unknown", "NaN", float("inf"), {}, []])
def test_invalid_measurements_remain_null(value):
    result = project(temp_c=value, rain_rate_mm_h=value, wind_kph=value, wind_gust_kph=value)
    assert result["weather"]["state"] == "unavailable"
    assert result["weather"]["rain"]["value"] is None
    assert result["weather"]["wind"]["speed"] is None


def test_rain_total_is_not_rate_and_forecast_does_not_fill_observation():
    result = project(rain_rate_mm_h=None, rain_mm=40, temp_c=None, forecast_temperature=25)
    assert result["weather"]["rain"]["value"] is None
    assert result["weather"]["temperature"]["value"] is None


def test_old_measurement_not_freshened_by_cache_and_missing_source_clock_stays_degraded():
    result = project(observed_at=NOW - timedelta(hours=2))
    assert result["weather"]["state"] == "stale"
    assert result["source"]["data_age_seconds"] == 7200
    assert project(evidence=replace(VERIFIED, source_generated_at=None))["weather"]["state"] == "stale"
    assert project(evidence=replace(VERIFIED, source_state="stale"))["weather"]["state"] == "stale"
    assert project(observed_at=NOW - timedelta(seconds=3600, microseconds=1))["weather"]["state"] == "stale"


def test_existing_weather_role_ceiling_and_no_capability_creation():
    for role in ("admin", "enologist", "worker", "viewer"):
        result = project_station_weather(None, estate_id=ESTATE, role=role,
                                        capabilities=frozenset({"weather"}), now=NOW)
        assert result["weather"]["state"] == "unavailable"
    for role, capabilities in (("operator", {"weather"}), ("admin", set())):
        with pytest.raises(WeatherProjectionForbidden):
            project_station_weather(None, estate_id=ESTATE, role=role,
                                    capabilities=frozenset(capabilities), now=NOW)
