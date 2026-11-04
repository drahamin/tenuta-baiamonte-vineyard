from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.domains import mobile_weather_reports as reports, mobile_site_routes as mobile
from app.ha_entities import DEFAULT_GW2000_ENTITIES, gw2000_metric_value
from test_direct_site_gateways import _mobile_client, _bearer

ESTATE = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)


def evidence(metric="temp_c", state="20", unit="°C", at="2026-11-04T11:59:00Z", **extras):
    entity = DEFAULT_GW2000_ENTITIES[metric]
    return reports.build_station_evidence({entity: {"entity_id": entity, "state": state,
        "last_reported": at, "attributes": {"unit_of_measurement": unit, "secret": "private"}, **extras}},
        {metric: entity}, ESTATE, now=NOW)


def projected(raw, now=NOW, source="home_assistant", estate=ESTATE):
    return reports.project_station_reports(raw, estate, source, now)


@pytest.mark.parametrize("metric,state,unit,expected", [
    ("temp_c", "68", "°F", 20), ("wind_kph", "10", "m/s", 36),
    ("wind_gust_kph", "10", "mph", 16.09344), ("rain_mm", "1", "in", 25.4),
    ("rain_rate_mm_h", "0", "mm/h", 0), ("pressure_hpa", "1000", "hPa", 1000),
    ("solar_wm2", "1", "kW/m²", 1000), ("vpd_kpa", "1000", "Pa", 1),
    ("humidity_pct", "0", "%", 0), ("uv_index", "2", "", 2),
])
def test_each_report_retains_its_own_clock_verified_conversion_and_zero(metric, state, unit, expected):
    raw = evidence(metric, state, unit)
    item = projected(raw)["metrics"][metric]
    assert item["value"] == pytest.approx(expected)
    assert item["quality"] == "current" and item["reported_at"] == "2026-11-04T11:59:00Z"
    assert item["clock_field"] == "last_reported" and item["data_age_seconds"] == 60
    assert "private" not in str(raw) and "entity_id" not in str(projected(raw))


def test_distinct_sensor_reports_never_become_one_shared_observation():
    raw = evidence()
    wind = evidence("wind_kph", "10", "km/h", "2026-11-04T11:57:00Z")
    raw["metrics"]["wind_kph"] = wind["metrics"]["wind_kph"]
    result = projected(raw)
    assert "observed_at" not in result and "source_generated_at" not in result
    assert result["metrics"]["temp_c"]["data_age_seconds"] == 60
    assert result["metrics"]["wind_kph"]["data_age_seconds"] == 180


def test_source_update_and_change_clocks_are_labeled_separately():
    raw = evidence(at=None, last_updated="2026-11-04T12:59:00+01:00")
    item = projected(raw)["metrics"]["temp_c"]
    assert item["clock_field"] == "last_updated" and item["data_age_seconds"] == 60
    raw = evidence(at=None, last_changed="2026-11-04T11:59:00Z")
    assert projected(raw)["metrics"]["temp_c"]["clock_field"] == "last_changed"


@pytest.mark.parametrize("at", [None, "2026-11-04", "2026-11-04T11:59:00", "invalid", "2026-11-04T12:01:00Z"])
def test_unqualified_clocks_never_borrow_request_cache_or_other_sensor_time(at):
    raw = evidence(at=at)
    item = projected(raw)["metrics"]["temp_c"]
    assert item["value"] is None and item["reported_at"] is None and item["quality"] == "unavailable"
    assert projected(raw, now=NOW + timedelta(minutes=5))["metrics"]["temp_c"]["value"] is None


def test_staleness_recomputed_on_read_not_trusted_from_cache():
    raw = evidence()
    raw["metrics"]["temp_c"]["quality"] = "current"
    item = projected(raw, now=NOW + timedelta(minutes=15))["metrics"]["temp_c"]
    assert item["quality"] == "stale" and item["value"] == 20 and item["data_age_seconds"] == 960


@pytest.mark.parametrize("state,unit", [("nan", "°C"), ("inf", "°C"), (True, "°C"), ("20", "unknown"), ("9999", "°C")])
def test_invalid_values_and_unknown_physical_units_stay_null(state, unit):
    raw = evidence(state=state, unit=unit)
    assert projected(raw)["metrics"]["temp_c"]["value"] is None
    json.dumps(raw, allow_nan=False)
    if state in ("nan", "inf", True):
        assert gw2000_metric_value({"state": state}, "temp_c") is None


def test_unknown_alias_substituted_entity_foreign_estate_or_fallback_is_not_attested():
    entity = DEFAULT_GW2000_ENTITIES["temp_c"]
    raw = reports.build_station_evidence({entity: {"entity_id": "sensor.other", "state": "20", "last_reported": "2026-11-04T11:59:00Z", "attributes": {"unit_of_measurement": "°C"}}}, {"temp_c": entity}, ESTATE, now=NOW)
    assert projected(raw)["metrics"]["temp_c"]["value"] is None
    for source in ("database_last_known", "unavailable", None):
        assert projected(evidence(), source=source)["metrics"]["temp_c"]["value"] is None
    raw = evidence(); raw["estate_id"] = "22222222-2222-4222-8222-222222222222"
    assert projected(raw)["metrics"]["temp_c"]["value"] is None
    raw = reports.build_station_evidence({"sensor.alias": {"entity_id": "sensor.alias", "state": "20", "last_reported": "2026-11-04T11:59:00Z", "attributes": {"unit_of_measurement": "°C"}}}, {"temp_c": "sensor.alias"}, ESTATE, now=NOW)
    assert projected(raw)["metrics"]["temp_c"]["value"] is None


def test_optin_uses_existing_weather_authorization_and_legacy_shape(monkeypatch):
    client, _, _ = _mobile_client(monkeypatch)
    raw = evidence(at="2026-11-04T11:59:00Z")
    payload = {"available": True, "source": "home_assistant", "current": {"observed_at": "2099-01-01T00:00:00Z", "temp_c": 20}, "forecast": [], "station_reports": raw}
    calls = []
    monkeypatch.setattr(mobile, "weather_context_payload", lambda: calls.append(True) or deepcopy(payload))
    before = client.get("/api/v1/mobile/weather", headers=_bearer("viewer")).json()
    assert "reports" not in before and "projection" not in before
    assert before["weather"]["current"]["observed_at"] is None and before["freshness"]["source_generated_at"] is None
    for role in ("admin", "enologist", "worker", "viewer"):
        result = client.get("/api/v1/mobile/weather?projection=station-reports-v1", headers=_bearer(role))
        assert result.status_code == 200
        data = result.json()
        assert data["projection_contract"] == reports.CONTRACT and data["reports"]["estate_id"] == ESTATE
        assert data["weather"] == before["weather"] and data["freshness"]["source_generated_at"] is None
        assert set(data["reports"]["metrics"]) == set(reports.SPECS)
    count = len(calls)
    for query in ("projection=station-reports-v1&entity_id=sensor.private", "projection=station-reports-v1&projection=station-reports-v1", "projection=unknown"):
        assert client.get("/api/v1/mobile/weather?" + query, headers=_bearer("admin")).status_code == 422
    assert client.get("/api/v1/mobile/weather?projection=station-reports-v1", headers=_bearer("revoked_session")).status_code == 401
    assert client.post("/api/v1/mobile/weather?projection=station-reports-v1", headers=_bearer("admin")).status_code == 405
    assert len(calls) == count


def test_existing_weather_context_carries_evidence_separately_from_legacy_values():
    from app.display_data import _weather_context_from_home_assistant
    raw = evidence()
    context = _weather_context_from_home_assistant({"available": True,
        "live_weather": {"temp_c": 20, "observed_at": "2099-01-01T00:00:00Z"},
        "weather_station_reports": raw})
    assert context["current"] == {"temp_c": 20, "observed_at": "2099-01-01T00:00:00Z"}
    assert context["station_reports"] == raw
    assert projected(context["station_reports"])["metrics"]["temp_c"]["reported_at"] == "2026-11-04T11:59:00Z"
