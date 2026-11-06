"""Regression coverage for PR293 freshness and scheduled-plan review findings."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains import laffort_catalog as catalog
from app.domains.enology_mlf import MLF_PLAN_COLUMNS, MLF_PLAN_JOIN, mlf_purchase_plan


NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
VALUES = {"ph": 3.35, "malic_acid": 2, "lactic_acid": 0.2,
          "total_so2": 35, "free_so2": 5, "actual_alcohol": 13.5, "residual_sugar": 1}


def protocol():
    return {"id": "vp41", "product_catalog_id": "vp41", "manufacturer": "LALLEMAND OENOLOGY",
            "product_name": "LALVIN VP41 MBR", "product_class": "bacteria",
            "protocol_name": "VP41 MBR", "purpose": "MLF", "wine_colors": "red",
            "trigger_code": "mlf_inoculation", "required_lab_analytes": ",".join(VALUES),
            "lab_max_age_days": 3}


def lot():
    return {"id": "lot-red", "wine_color": "red", "stage": "post-fermentation",
            "volume_l": 1600, "mlf_intent": "allow", "vintage_year": 2026,
            "mlf_volume_min_l": 1600, "mlf_volume_max_l": 1600,
            "mlf_volume_basis": "current_measured_wine", "small_sachet_coverage_l": 250,
            "mlf_exact_label_confirmed": 1, "mlf_suitability_confirmed": 1,
            "mlf_approved_by": "Enologist"}


def evidence():
    return {"status": "linked", "metrics": {code: {"code": code, "value": value,
            "lab_date": "2026-11-05", "age_days": 0, "decision_usable": True}
            for code, value in VALUES.items()}, "candidates": []}


def decision(*, readings=None, labs=None, row=None, now=NOW):
    row = deepcopy(row or lot())
    row["mlf_purchase_plan"] = mlf_purchase_plan(row)
    return catalog.additive_prediction_pipeline(row, [protocol()],
        [{"observed_at": "2026-11-05T10:00:00+01:00", "temp_c": 19}] if readings is None else readings,
        [], lab_evidence=evidence() if labs is None else labs, now=now)["decisions"][0]


def test_fresh_exact_lot_inputs_can_reach_review_without_releasing_dosing_guard():
    result = decision()
    assert result["operational_status"] == "recommended_now"
    plan = mlf_purchase_plan(lot())
    assert plan["dosing_blocked"] is True and plan["planning_only"] is True


@pytest.mark.parametrize("stamp", [None, "bad", "2026-11-05", "2026-10-15T10:00:00",
    "2026-11-04T23:59:59+01:00", "2026-11-05T14:00:01+01:00", "2026-11-06T10:00:00Z",
    "9999-12-31T23:59:59-12:00"])
def test_temperature_requires_nonfuture_current_estate_day(stamp):
    result = decision(readings=[{"observed_at": stamp, "temp_c": 19}])
    assert result["operational_status"] == "data_needed"
    assert any("current estate day" in message for message in result["blockers"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "invalid", True])
def test_invalid_temperature_fails_closed_without_crashing(value):
    assert decision(readings=[{"observed_at": "2026-11-05T10:00:00", "temp_c": value}])["operational_status"] == "data_needed"


def test_temperature_uses_latest_timestamp_not_input_order_and_rejects_tie_conflicts():
    warm = {"observed_at": "2026-11-05T10:00:00", "temp_c": 19}
    cold = {"observed_at": "2026-11-05T11:00:00", "temp_c": 15}
    for readings in ([warm, cold], [cold, warm]):
        assert any("above 16" in message for message in decision(readings=readings)["blockers"])
    assert decision(readings=[warm, {**warm, "temp_c": 15}])["operational_status"] == "data_needed"


def test_temperature_compares_aware_instants_in_estate_zone_at_midnight():
    # 00:30 estate time on Nov 6: 23:15Z is today, 22:59Z is yesterday.
    now = datetime(2026, 11, 5, 23, 30, tzinfo=timezone.utc)
    assert decision(now=now, readings=[{"observed_at": "2026-11-05T23:15:00Z", "temp_c": 19}])["operational_status"] == "recommended_now"
    assert decision(now=now, readings=[{"observed_at": "2026-11-05T22:59:00Z", "temp_c": 19}])["operational_status"] == "data_needed"


@pytest.mark.parametrize("code", list(VALUES))
@pytest.mark.parametrize("stamp", [None, "bad", "2026-11-01", "2026-11-06"])
def test_required_lab_dates_block_stale_unknown_and_future_despite_cached_zero_age(code, stamp):
    labs = evidence()
    labs["metrics"][code]["lab_date"] = stamp
    result = decision(labs=labs)
    assert result["operational_status"] == "data_needed"
    assert any(code.replace("_", " ") in message and "freshness limit" in message for message in result["blockers"])


def test_lab_calendar_boundary_and_sample_time_override_are_enforced():
    labs = evidence()
    labs["metrics"]["ph"]["lab_date"] = date(2026, 11, 2)
    assert decision(labs=labs)["operational_status"] == "recommended_now"
    labs["metrics"]["ph"]["sampled_at"] = "2026-11-05T15:00:00+01:00"
    assert decision(labs=labs)["operational_status"] == "data_needed"
    labs["metrics"]["ph"]["sampled_at"] = "invalid"
    assert decision(labs=labs)["operational_status"] == "data_needed"


def test_mlf_uses_source_date_instead_of_malformed_or_stale_cached_age():
    labs = evidence()
    labs["metrics"]["ph"]["age_days"] = "invalid"
    assert decision(labs=labs)["operational_status"] == "recommended_now"
    labs["metrics"]["ph"]["age_days"] = 999
    assert decision(labs=labs)["operational_status"] == "recommended_now"


def test_missing_labs_and_invalid_values_never_qualify_a_confirmed_plan():
    assert decision(labs={})["operational_status"] == "data_needed"
    labs = evidence()
    labs["metrics"]["ph"]["value"] = float("nan")
    assert decision(labs=labs)["operational_status"] == "data_needed"
    labs = evidence()
    labs["metrics"]["ph"]["decision_usable"] = False
    assert decision(labs=labs)["operational_status"] == "data_needed"


@pytest.mark.parametrize("field,value", [("mlf_exact_label_confirmed", 0),
    ("mlf_suitability_confirmed", 0), ("mlf_volume_basis", "old_must_estimate")])
def test_existing_label_volume_and_enologist_gates_remain_blocking(field, value):
    assert decision(row={**lot(), field: value})["operational_status"] == "data_needed"


def test_explicit_mlf_block_remains_not_indicated_with_fresh_approved_inputs():
    assert decision(row={**lot(), "mlf_intent": "block"})["operational_status"] == "not_indicated"


def test_scheduler_loads_shared_exact_plan_and_intent_and_signs_age_transitions(monkeypatch):
    rows = [lot()]
    readings = [{"wine_lot_id": "lot-red", "observed_at": "2026-11-05T10:00:00+01:00", "temp_c": 19}]
    clock = [NOW]
    snapshots = []
    queries = []
    monkeypatch.setattr(catalog, "estate_id", lambda: "estate")
    real_estate_now = catalog.estate_now
    monkeypatch.setattr(catalog, "estate_now", lambda value=None: real_estate_now(value or clock[0]))
    monkeypatch.setattr(catalog, "protocol_rows", lambda: [protocol()])
    monkeypatch.setattr(catalog, "catalog_rows", lambda: [])
    monkeypatch.setattr(catalog, "lab_evidence_rows", lambda year: [])
    monkeypatch.setattr(catalog, "lot_lab_evidence", lambda *a, **kw: evidence())
    from app.domains import lab_analyte_mapping
    monkeypatch.setattr(lab_analyte_mapping, "refresh_unmapped_lab_analytes", lambda: None)

    def fetch(sql, args):
        queries.append(sql)
        if "FROM wine_lots w JOIN seasons" in sql:
            assert MLF_PLAN_COLUMNS in sql and MLF_PLAN_JOIN in sql
            assert "rp.mlf_intent" in sql
            assert "rp.estate_id=w.estate_id AND rp.season_id=w.season_id" in sql
            return deepcopy(rows)
        if "FROM fermentation_observations" in sql:
            return deepcopy(readings)
        return []

    class Cursor:
        rowcount = 1

        def execute(self, sql, args):
            if sql.startswith("INSERT IGNORE INTO enology_additive_prediction_snapshots"):
                snapshots.append(args)

    @contextmanager
    def transaction():
        yield None, Cursor()

    monkeypatch.setattr(catalog, "fetch_all", fetch)
    monkeypatch.setattr(catalog, "transaction", transaction)

    def refresh():
        result = catalog.refresh_enology_additive_predictions()
        assert result["lots"] == 1
        import json
        return snapshots[-1][4], json.loads(snapshots[-1][-1])["decisions"][0]

    first, current = refresh()
    assert current["operational_status"] == "recommended_now"
    assert refresh()[0] == first
    rows[0]["mlf_exact_label_confirmed"] = 0
    unconfirmed, blocked = refresh()
    assert unconfirmed != first and blocked["operational_status"] == "data_needed"
    rows[0]["mlf_exact_label_confirmed"] = 1
    rows[0]["mlf_intent"] = "block"
    stopped, blocked = refresh()
    assert stopped != first and blocked["operational_status"] == "not_indicated"
    rows[0]["mlf_intent"] = "allow"
    assert refresh()[0] == first
    clock[0] = NOW + timedelta(days=1)
    expired, blocked = refresh()
    assert expired != first and blocked["operational_status"] == "data_needed"
    assert any("current estate day" in message for message in blocked["blockers"])
    clock[0] = NOW + timedelta(days=4)
    labs_expired, blocked = refresh()
    assert labs_expired != expired
    assert any("ph" in message and "freshness limit" in message for message in blocked["blockers"])
