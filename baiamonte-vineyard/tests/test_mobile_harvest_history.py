from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from app.domains import mobile_harvest_history as history, mobile_site_routes
from test_direct_site_gateways import _mobile_client, _bearer, TOKENS

ESTATE = "11111111-1111-4111-8111-111111111111"
ID = "22222222-2222-4222-8222-222222222222"


def sample(dataset):
    if dataset == "vintages":
        return {"estate_id": ESTATE, "vintage_year": 2025, "variety_name": "Nerello",
                "grapes_kg": Decimal("2825"), "wine_l": Decimal("1640"), "evidence_status": "recorded"}
    if dataset == "grapes":
        return {"id": ID, "estate_id": ESTATE, "vintage_year": 2025, "season_id": ID,
                "variety_id": ID, "season_estate_id": ESTATE, "variety_estate_id": ESTATE,
                "variety_name": "Nerello", "harvest_date": date(2025, 9, 30),
                "source_type": "estate_harvest", "weight_kg": Decimal("100"), "crate_count": 0}
    return {"id": ID, "estate_id": ESTATE, "record_year": 2025, "record_date": date(2025, 10, 10),
            "mill_date": date(2025, 10, 11), "olives_harvested_kg": Decimal("100"),
            "oil_liters": None, "yield_pct": None}


@pytest.mark.parametrize("dataset", sorted(history.DATASETS))
def test_closed_source_fields_exact_id_or_composite_key_and_no_invented_clock(dataset):
    row = {**sample(dataset), "private_notes": "private", "created_at": "2026-11-04T12:00:00Z"}
    result = history.project_history([row], ESTATE, dataset, 2023, 2026)[0]
    assert "private" not in str(result) and "created_at" not in result and "observed_at" not in result
    if dataset == "vintages":
        assert result["key"] == {"vintage_year": 2025, "variety_name": "Nerello"}
        assert "id" not in result
    else:
        assert result["id"] == ID
    if dataset == "grapes":
        assert result["harvest_date"] == "2025-09-30" and result["reported_crate_count"] == 0
    if dataset == "olives":
        assert result["reported_oil_l"] is None and result["reported_yield_pct"] is None


@pytest.mark.parametrize("dataset", sorted(history.DATASETS))
def test_wrong_estate_year_duplicate_or_overflow_fails_closed(dataset):
    original = sample(dataset)
    year_key = "record_year" if dataset == "olives" else "vintage_year"
    for rows in ([{**original, "estate_id": ID}], [{**original, year_key: 2022}],
                 [original, original], [original] * 1001):
        with pytest.raises(history.ReportingSourceUnavailable):
            history.project_history(rows, ESTATE, dataset, 2023, 2026)


def test_wrong_grape_join_or_ambiguous_date_is_rejected():
    for changes in ({"variety_estate_id": ID}, {"season_estate_id": None},
                    {"harvest_date": datetime(2025, 9, 30, tzinfo=timezone.utc)},
                    {"harvest_date": "2025-09"}, {"harvest_date": "2025-02-30"},
                    {"weight_kg": float("inf")}, {"id": "invented"}):
        with pytest.raises(history.ReportingSourceUnavailable):
            history.project_history([{**sample("grapes"), **changes}], ESTATE, "grapes", 2023, 2026)


@pytest.mark.parametrize("dataset", sorted(history.DATASETS))
def test_one_bounded_explicit_estate_year_select_per_dataset(monkeypatch, dataset):
    calls = []
    def fetch(sql, params):
        calls.append((sql, params))
        return [sample(dataset)]
    monkeypatch.setattr(history, "fetch_all", fetch)
    assert len(history.read_history(ESTATE, dataset, 2023, 2026)) == 1
    assert len(calls) == 1 and calls[0][1] == (ESTATE, 2023, 2026, 1001)
    sql = calls[0][0]
    assert sql.startswith("SELECT ") and "SELECT *" not in sql
    for excluded in ("notes", "details", "worker_text", "labor_hours", "reconciliation_note", "source_document", "cost"):
        assert excluded not in sql
    with pytest.raises(ValueError):
        history.read_history(ESTATE, "unknown", 2023, 2026)
    assert len(calls) == 1


def test_route_defaults_off_and_explicit_grant_filters_and_scope(monkeypatch):
    client, sessions, _ = _mobile_client(monkeypatch)
    settings = mobile_site_routes.get_settings()
    settings.mobile_harvest_history_enabled = False
    calls = []
    monkeypatch.setattr(mobile_site_routes, "read_history", lambda *args: calls.append(args) or [])
    path = "/api/v1/mobile/records?object=harvest&projection=harvest-history-v1&dataset=grapes"
    assert client.get(path, headers=_bearer("admin")).status_code == 404
    settings.mobile_harvest_history_enabled = True
    for role in ("worker", "viewer", "enologist", "revoked_session", "expired"):
        assert client.get(path, headers=_bearer(role)).status_code in (401, 403)
    for suffix in ("&from_year=2022", "&from_year=2026&to_year=2025", "&to_year=2027",
                   "&estate_id=" + ID, "&limit=1", "&dataset=olives", "&from_year=unknown"):
        assert client.get(path + suffix, headers=_bearer("admin")).status_code == 422
    assert calls == []
    for dataset in history.DATASETS:
        response = client.get(path.replace("dataset=grapes", "dataset=" + dataset), headers=_bearer("admin"))
        assert response.status_code == 200
        data = response.json()
        assert data["dataset"] == dataset and data["projection_contract"] == history.CONTRACT
        assert data["complete"] is True and data["filters"] == {"from_year": 2023, "to_year": 2026}
        assert data["freshness"]["source_generated_at"] is None
    assert all(args[0] == ESTATE for args in calls)
    key = hashlib.sha256(TOKENS["admin"].encode()).hexdigest()
    granted = json.loads(sessions[key]["capabilities_json"])
    sessions[key]["capabilities_json"] = json.dumps([cap for cap in granted if cap != "harvest.read"])
    previous = len(calls)
    assert client.get(path, headers=_bearer("admin")).status_code == 403
    assert len(calls) == previous
