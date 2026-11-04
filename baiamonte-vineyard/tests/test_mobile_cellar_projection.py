from decimal import Decimal
from uuid import UUID

import pytest

from app.domains import mobile_cellar_projection as cellar
from app.domains import mobile_site_routes
from test_direct_site_gateways import _mobile_client, _bearer

ESTATE = "11111111-1111-4111-8111-111111111111"
TANK = "22222222-2222-4222-8222-222222222222"
LOT = "33333333-3333-4333-8333-333333333333"
OTHER_LOT = "44444444-4444-4444-8444-444444444444"


def row(**changes):
    return {"container_id": TANK, "container_estate_id": ESTATE, "container_code": "T1",
            "container_name": "Tank one", "container_type": "tank", "material": "steel",
            "capacity_l": Decimal("1000"), "location": "Cellar", "container_status": "in_use",
            "wine_lot_id": LOT, "lot_estate_id": ESTATE, "season_estate_id": ESTATE,
            "current_container_id": TANK, "wine_lot_code": "N-2025", "wine_lot_name": "Nerello",
            "stage": "aging", "variety_summary": "Nerello", "vintage_year": 2025,
            "volume_l": Decimal("635"), "private_notes": "must not leak", **changes}


def test_all_exact_lots_are_preserved_without_summing_or_selecting_a_winner():
    result = cellar.project_cellar_links([row(), row(wine_lot_id=OTHER_LOT, vintage_year=2026, volume_l=0)], ESTATE)
    tank = result[0]
    assert tank["link_status"] == "multiple"
    assert [(lot["id"], lot["vintage_year"], lot["reported_volume_l"]) for lot in tank["wine_lots"]] == [(LOT, 2025, 635), (OTHER_LOT, 2026, 0)]
    assert "volume_l" not in tank and "fill_pct" not in tank
    assert "private_notes" not in str(result)
    assert tank["observations"] == []
    assert tank["observation_status"] == cellar.OBSERVATION_STATUS


def test_unassigned_and_unknown_volume_are_distinct_from_zero():
    assert cellar.project_cellar_links([row(wine_lot_id=None)], ESTATE)[0]["link_status"] == "unassigned"
    tank = cellar.project_cellar_links([row(volume_l=None)], ESTATE)[0]
    assert tank["link_status"] == "single" and tank["wine_lots"][0]["reported_volume_l"] is None


@pytest.mark.parametrize("changes", [
    {"container_estate_id": OTHER_LOT}, {"lot_estate_id": OTHER_LOT}, {"season_estate_id": OTHER_LOT},
    {"current_container_id": OTHER_LOT}, {"wine_lot_id": "bad-id"}, {"container_id": "bad-id"},
    {"vintage_year": True}, {"vintage_year": None}, {"volume_l": float("nan")}, {"volume_l": -1},
    {"volume_l": True}, {"capacity_l": float("inf")},
])
def test_invalid_source_never_becomes_an_assignment(changes):
    with pytest.raises(cellar.ReportingSourceUnavailable):
        cellar.project_cellar_links([row(**changes)], ESTATE)


def test_conflicting_or_duplicate_ids_fail_closed():
    for rows in ([row(), row()], [row(), row(wine_lot_id=OTHER_LOT, capacity_l=1)]):
        with pytest.raises(cellar.ReportingSourceUnavailable):
            cellar.project_cellar_links(rows, ESTATE)


def test_snapshot_is_bounded_and_estate_scoped(monkeypatch):
    calls = []
    def fetch(sql, params):
        calls.append((sql, params))
        return [row()]
    monkeypatch.setattr(cellar, "fetch_all", fetch)
    assert cellar.read_cellar_links(ESTATE)[0]["wine_lots"][0]["id"] == LOT
    assert len(calls) == 1
    sql, params = calls[0]
    assert params == (ESTATE, 1001)
    assert "w.current_container_id=c.id AND w.estate_id=c.estate_id" in sql
    assert "s.id=w.season_id AND s.estate_id=w.estate_id" in sql
    assert "MIN(" not in sql and "SUM(" not in sql and "vessel_name" not in sql
    with pytest.raises(cellar.ReportingSourceUnavailable):
        cellar.project_cellar_links([row()] * 1001, ESTATE)
    with pytest.raises(cellar.ReportingSourceUnavailable):
        cellar.project_cellar_links([row(container_id=str(UUID(int=i + 1)), wine_lot_id=None) for i in range(101)], ESTATE)


def test_optin_uses_existing_authorization_and_preserves_legacy(monkeypatch):
    client, _, _ = _mobile_client(monkeypatch)
    calls = []
    monkeypatch.setattr(mobile_site_routes, "read_cellar_links", lambda estate: calls.append(estate) or cellar.project_cellar_links([row()], ESTATE))
    path = "/api/v1/mobile/records?object=cellar&projection=cellar-links-v1"
    for role in ("viewer", "worker", "revoked_identity", "revoked_session", "expired"):
        assert client.get(path, headers=_bearer(role)).status_code in (401, 403)
    assert calls == []
    assert client.post(path, headers=_bearer("admin")).status_code == 405
    for role in ("admin", "enologist"):
        result = client.get(path, headers=_bearer(role))
        assert result.status_code == 200
        data = result.json()
        assert data["projection_contract"] == cellar.CONTRACT and data["complete"] is True
        assert data["freshness"]["source_generated_at"] is None and data["freshness"]["stale"] is True
    before = len(calls)
    old = client.get("/api/v1/mobile/records?object=cellar", headers=_bearer("admin")).json()
    assert "projection_contract" not in old and len(calls) == before
    for query in ("object=tasks&projection=cellar-links-v1", "object=cellar&projection=unknown",
                  "object=cellar&projection=cellar-links-v1&year=2025",
                  "object=cellar&projection=cellar-links-v1&limit=1",
                  "object=cellar&projection=cellar-links-v1&object=cellar"):
        assert client.get("/api/v1/mobile/records?" + query, headers=_bearer("admin")).status_code == 422
    assert len(calls) == before
    monkeypatch.setattr(mobile_site_routes, "read_cellar_links", lambda _: (_ for _ in ()).throw(cellar.ReportingSourceUnavailable("private source error")))
    result = client.get(path, headers=_bearer("admin"))
    assert result.status_code == 503 and "private source" not in result.text
