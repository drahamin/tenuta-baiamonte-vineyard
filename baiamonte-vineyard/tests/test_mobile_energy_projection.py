from dataclasses import replace
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.domains.mobile_energy_projection import (
    CONTRACT, FIELDS, MAX_INPUT_ROWS, POWER_SIGN, REQUIRED_COLUMNS, PROJECTED_COLUMNS, SOURCE_OBJECT,
    EnergyProjectionForbidden, EnergyReadEvidence, EnergySnapshotChanged, project_energy_read,
)

ESTATE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
VERIFIED = EnergyReadEvidence(PROJECTED_COLUMNS, True, True, "UTC", NOW, NOW, "generation-1", "generation-1", True)


def record(at=NOW, **values):
    return {"object": SOURCE_OBJECT, "id": "redacted-row", "revision": "9007199254740993",
            "data": {"estate_id": ESTATE, "observed_at": at, "battery_soc_pct": 61, "battery_power_w": -420, **values}}


def project(rows, **kwargs):
    return project_energy_read(rows, estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=VERIFIED, **kwargs)


def test_battery_is_available_without_solar_and_no_private_fields_escape():
    payload = project([record(generator_power_w=9999, grid_power_w=100, evidence={"private": True}, entity_id="sensor.private")])
    assert payload["contract"] == CONTRACT and payload["ok"] is True
    assert payload["available"] is True and payload["source"]["state"] == "current"
    assert payload["metrics"]["battery_soc_pct"]["value"] == 61
    assert payload["metrics"]["battery_power_w"]["value"] == -420
    assert payload["metrics"]["pv_power_w"] == {"value": None, "unit": "W", "observed_at": None, "quality": "unavailable"}
    assert payload["battery_power_sign"] == POWER_SIGN
    assert set(payload["metrics"]) == set(FIELDS)
    assert not any(word in json.dumps(payload) for word in ("generator", "grid_power", "sensor.private", "9007199254740993"))


@pytest.mark.parametrize("role", ["operator", "enologist", "worker", "viewer", "unknown"])
def test_no_broader_erp_or_caller_role_permission(role):
    with pytest.raises(EnergyProjectionForbidden):
        project_energy_read([], estate_id=ESTATE, role=role, capabilities=frozenset({"energy"}), now=NOW)


def test_admin_without_energy_capability_is_denied():
    with pytest.raises(EnergyProjectionForbidden):
        project_energy_read([], estate_id=ESTATE, role="admin", capabilities=frozenset(), now=NOW)


@pytest.mark.parametrize("evidence,reason", [
    (EnergyReadEvidence(), "reporting_schema_unverified"),
    (replace(VERIFIED, schema_columns=PROJECTED_COLUMNS - {"observed_at"}), "reporting_schema_unverified"),
    (replace(VERIFIED, observation_clock_verified=False), "observation_clock_unverified"),
    (replace(VERIFIED, power_sign_verified=False), "battery_sign_unverified"),
])
def test_default_provenance_gates_fail_closed(evidence, reason):
    payload = project_energy_read([record()], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=evidence)
    assert payload["available"] is False and payload["unavailable_reason"] == reason
    assert payload["series"]["points"] == []
    assert all(metric["value"] is None and metric["observed_at"] is None for metric in payload["metrics"].values())


@pytest.mark.parametrize("value", [None, True, False, "unknown", "unavailable", "NaN", "Infinity", float("inf"), float("nan"), {}, "1e9999"])
def test_unknowns_and_invalid_numbers_never_become_zero(value):
    payload = project([record(battery_soc_pct=value, battery_power_w=value)])
    assert payload["metrics"]["battery_soc_pct"]["value"] is None
    assert payload["metrics"]["battery_power_w"]["value"] is None
    assert payload["available"] is False


def test_real_zero_and_signed_power_preserved():
    payload = project([record(battery_soc_pct=Decimal("0"), battery_power_w="0", pv_power_w=0, forecast_remaining_kwh="0.000")])
    assert payload["available"] is True
    for field in ("battery_soc_pct", "battery_power_w", "pv_power_w", "forecast_remaining_kwh"):
        assert payload["metrics"][field]["value"] == 0
    assert project([record(battery_power_w=420)])["metrics"]["battery_power_w"]["value"] == 420


def test_missing_solar_or_power_column_does_not_gate_verified_soc_column():
    evidence = replace(VERIFIED, schema_columns=REQUIRED_COLUMNS | {"battery_soc_pct"})
    payload = project_energy_read([record()], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=evidence)
    assert payload["available"] is True
    assert payload["metrics"]["battery_soc_pct"]["value"] == 61
    assert payload["metrics"]["pv_power_w"]["value"] is None
    assert payload["metrics"]["battery_power_w"]["value"] is None


def test_physical_bounds_do_not_fabricate_clamped_measurements():
    payload = project([record(battery_soc_pct=101, pv_power_w=-1, estate_load_w=-2, forecast_remaining_kwh=-1)])
    for field in ("battery_soc_pct", "pv_power_w", "estate_load_w", "forecast_remaining_kwh"):
        assert payload["metrics"][field]["value"] is None
    assert payload["metrics"]["battery_power_w"]["value"] == -420


def test_estate_and_reporting_object_boundaries():
    foreign = record(battery_soc_pct=99)
    foreign["data"]["estate_id"] = OTHER
    raw = record()
    raw["object"] = "estate_energy_observations"
    assert project([foreign, raw])["available"] is False


@pytest.mark.parametrize("at", [None, "2026-11-03", "2026-11-03T12:00", "bad date", NOW + timedelta(seconds=1), NOW - timedelta(days=8)])
def test_invalid_missing_date_future_and_out_of_window_are_not_current(at):
    payload = project([record(at)])
    assert payload["available"] is False and payload["data_age_seconds"] is None
    assert payload["series"]["points"] == []


def test_naive_datetime_needs_explicit_verified_timezone():
    evidence = replace(VERIFIED, naive_timestamp_timezone=None)
    payload = project_energy_read([record("2026-11-03 12:00:00.123456")], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=evidence)
    assert payload["available"] is False
    # DST's duplicated and missing wall times are rejected, not guessed.
    for value, clock in (("2026-10-25 02:30:00", datetime(2026, 10, 25, 3, tzinfo=timezone.utc)), ("2026-03-29 02:30:00", datetime(2026, 3, 29, 3, tzinfo=timezone.utc)), ("0001-01-01 00:00:00", NOW)):
        evidence = replace(VERIFIED, naive_timestamp_timezone="Europe/Rome", source_generated_at=clock, last_success_at=clock)
        payload = project_energy_read([record(value)], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=clock, evidence=evidence)
        assert payload["available"] is False


def test_old_measurement_and_missing_or_old_source_clock_are_stale():
    assert project([record(NOW - timedelta(seconds=901))])["source"]["state"] == "stale"
    for changes in ({"source_generated_at": None}, {"last_success_at": None}, {"source_generated_at": NOW + timedelta(seconds=1)}, {"last_success_at": NOW - timedelta(hours=1)}):
        payload = project_energy_read([record()], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=replace(VERIFIED, **changes))
        assert payload["available"] is True and payload["source"]["state"] == "stale"
        assert payload["metrics"]["battery_soc_pct"]["quality"] == "stale"


def test_latest_missing_measurement_not_backfilled_from_older_values():
    payload = project([record(NOW - timedelta(minutes=5)), record(battery_soc_pct=None, battery_power_w=None)])
    assert payload["available"] is False
    assert payload["metrics"]["battery_soc_pct"]["value"] is None
    assert len(payload["series"]["points"]) == 2


def test_unverified_solar_forecast_semantics_does_not_become_battery_remaining():
    payload = project_energy_read([record(forecast_remaining_kwh=7.5)], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=replace(VERIFIED, forecast_semantics_verified=False))
    assert payload["available"] is True
    assert payload["metrics"]["battery_soc_pct"]["value"] == 61
    assert payload["metrics"]["forecast_remaining_kwh"]["value"] is None
    assert payload["series"]["points"][0]["forecast_remaining_kwh"] is None


def test_equal_time_conflicts_stay_unknown_without_last_write_wins():
    payload = project([record(battery_soc_pct=60), record(battery_soc_pct=61), record(battery_soc_pct=60)])
    assert len(payload["series"]["points"]) == 1
    assert payload["metrics"]["battery_soc_pct"]["value"] is None
    assert payload["metrics"]["battery_power_w"]["value"] == -420


@pytest.mark.parametrize("range_value,count,expected,step", [("24h", 600, 289, 60), ("7d", 1200, 337, 300)])
def test_bounded_aggregation_keeps_null_gaps_and_latest_metric(range_value, count, expected, step):
    rows = [record(NOW - timedelta(seconds=(count - i - 1) * step), battery_soc_pct=i % 100, battery_power_w=None if i == 0 else i) for i in range(count)]
    payload = project(rows[::-1], range_value=range_value)
    points = payload["series"]["points"]
    assert len(points) == expected
    assert points[0]["battery_power_w"] is None
    assert points[-1]["observed_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert payload["metrics"]["battery_power_w"]["value"] == count - 1


def test_snapshot_change_invalidates_whole_projection():
    with pytest.raises(EnergySnapshotChanged, match="mobile_read_snapshot_changed"):
        project_energy_read([record()], estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=replace(VERIFIED, snapshot_after="generation-2"))


def test_invalid_range_clock_estate_and_input_bounds():
    for change in ({"range_value": "30d"}, {"now": datetime(2026, 11, 3)}, {"estate_id": "wrong"}):
        arguments = {"estate_id": ESTATE, "role": "admin", "capabilities": frozenset({"energy"}), "now": NOW, "evidence": VERIFIED, **change}
        with pytest.raises(ValueError):
            project_energy_read([], **arguments)
    with pytest.raises(ValueError, match="bounded read"):
        project([record()] * (MAX_INPUT_ROWS + 1))


def test_projection_is_not_registered_and_has_no_database_network_or_controls():
    root = Path(__file__).parents[1]
    assert "mobile_energy_projection" not in (root / "app/main.py").read_text()
    assert "mobile_energy_projection" not in (root / "app/domains/mobile_site_routes.py").read_text()
    source = (root / "app/domains/mobile_energy_projection.py").read_text()
    for forbidden in ("APIRouter", "fetch_all", "connect(", "urlopen", "requests.", "transaction(", "cursor.execute", "subprocess", "service_call"):
        assert forbidden not in source


def test_sanitized_native_fixture_is_generated_by_this_projection_without_mutation():
    rows = [record(NOW - timedelta(minutes=5), battery_soc_pct=62, battery_power_w=300, estate_load_w=196, forecast_remaining_kwh=7.5),
            record(battery_soc_pct=61, battery_power_w=-420, estate_load_w=196, forecast_remaining_kwh=7.2)]
    before = copy.deepcopy(rows)
    evidence = replace(VERIFIED, snapshot_before="fixture-generation", snapshot_after="fixture-generation", forecast_semantics_verified=False)
    result = project_energy_read(rows, estate_id=ESTATE, role="admin", capabilities=frozenset({"energy"}), now=NOW, evidence=evidence)
    fixture = json.loads((Path(__file__).parent / "fixtures/mobile_energy_battery_only.json").read_text())
    assert result == fixture
    assert rows == before
    assert result["available"] is True and result["metrics"]["pv_power_w"]["value"] is None
    assert result["metrics"]["forecast_remaining_kwh"]["value"] is None
