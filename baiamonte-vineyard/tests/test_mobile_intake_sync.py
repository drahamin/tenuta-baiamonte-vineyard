import base64
import hashlib
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import mobile_intake_sync
from app import remote_erp
from app.domains import mobile_intake_routes


ESTATE = "00000000-0000-4000-8000-000000000001"
REPORT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def item(expected_container="8", expected_lot="4"):
    author = {"username": "david", "server_role": "admin"}
    payload = {
        "contract": "baiamonte.mobile-intake.v1", "report_uuid": REPORT, "idempotency_key": REPORT,
        "kind": "enology_reading", "estate_id": ESTATE,
        "occurred_at": "2026-10-20T07:00:00.000000Z", "client_created_at": "2026-10-20T07:01:00.000000Z",
        "source_timezone": "Europe/Rome", "entities": {"container_id": "tank-5", "wine_lot_id": "lot-1"},
        "expected_revisions": {"container_id": expected_container, "wine_lot_id": expected_lot},
        "measurements": [{"code": "babo", "value": 18.1, "unit": "degree_babo"}],
        "note": None, "instrument": None, "attachments": [], "correction_of_report_uuid": None,
        "author": author, "status": "pending_review", "applied": False, "side_effects": [], "immutable_raw_submission": True,
    }
    return {"report_uuid": REPORT, "estate_id": ESTATE, "actor": author, "kind": "enology_reading", "payload": payload, "lease_token": "x" * 43, "attachments": []}


def test_payload_revalidates_actor_kind_and_enology_units(monkeypatch):
    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    payload, expected = mobile_intake_sync._validate_payload(item())
    assert payload["author"]["username"] == "david"
    assert expected == {"container_id": "8", "wine_lot_id": "4"}
    wrong_actor = item(); wrong_actor["payload"]["author"] = {"username": "other", "server_role": "admin"}
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="actor_binding_mismatch"):
        mobile_intake_sync._validate_payload(wrong_actor)
    wrong_unit = item(); wrong_unit["payload"]["measurements"][0]["unit"] = "degree_brix"
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="enology_measurement_invalid"):
        mobile_intake_sync._validate_payload(wrong_unit)


def test_expected_revisions_and_current_tank_lot_assignment_are_enforced(monkeypatch):
    container = {"id": "tank-5", "estate_id": ESTATE, "status": "active"}
    lot = {"id": "lot-1", "estate_id": ESTATE, "current_container_id": "tank-5", "stage": "fermentation"}
    actual = {"container_id": str(remote_erp.reporting_row_revision(container)), "wine_lot_id": str(remote_erp.reporting_row_revision(lot))}

    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_sync, "_reporting_entity", lambda table, _id: container if table == "cellar_containers" else lot)
    payload = item(actual["container_id"], actual["wine_lot_id"])["payload"]
    assert mobile_intake_sync._validate_revisions(payload, payload["expected_revisions"]) == actual
    with pytest.raises(mobile_intake_sync.IntakeConflict, match="expected_revision_conflict"):
        mobile_intake_sync._validate_revisions(payload, {**actual, "container_id": "1"})
    lot["current_container_id"] = "tank-9"
    payload["expected_revisions"]["wine_lot_id"] = str(remote_erp.reporting_row_revision(lot))
    with pytest.raises(mobile_intake_sync.IntakeConflict, match="container_lot_assignment_conflict"):
        mobile_intake_sync._validate_revisions(payload, payload["expected_revisions"])


def test_source_uuid_retry_is_idempotent_but_changed_content_conflicts(monkeypatch):
    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    current = item(); digest = hashlib.sha256(remote_erp._canonical(current["payload"]).encode()).hexdigest()
    monkeypatch.setattr(mobile_intake_sync, "fetch_one", lambda *_: {"payload_sha256": digest, "status": "pending_review", "revision": 1})
    result = mobile_intake_sync._accept_report(None, current)
    assert result["reason"] == "pending_review"
    changed = item(); changed["payload"]["note"] = "different"
    with pytest.raises(mobile_intake_sync.IntakeConflict, match="source_uuid_collision"):
        mobile_intake_sync._accept_report(None, changed)


def test_outbound_processor_posts_bounded_result_without_applying_domain_side_effects(monkeypatch):
    secret = base64.urlsafe_b64encode(b"i" * 32).decode().rstrip("=")
    config = mobile_intake_sync.RemoteIntakeConfig(True, "https://cantinabaiamonte.com/erp", "baiamonte-intake-1", secret, 10)
    posted = []

    def signed_post(_config, path, payload, _timeout=180):
        if path.endswith("/requests"): return {"ok": True, "reports": [item()]}
        posted.append((path, payload)); return {"ok": True}

    monkeypatch.setattr(mobile_intake_sync, "_signed_post", signed_post)
    monkeypatch.setattr(mobile_intake_sync, "_accept_report", lambda *_: {"authoritative_record_ids": [REPORT], "actual_revisions": {}, "reason": "pending_review"})
    assert mobile_intake_sync.process_mobile_intake_once(config) == 1
    assert posted == [(f"/sync/mobile-intake/results/{REPORT}", {"lease_token": "x" * 43, "status": "accepted", "result": {"authoritative_record_ids": [REPORT], "actual_revisions": {}, "reason": "pending_review"}})]


def test_human_review_requires_exact_revision_and_has_no_domain_side_effect(monkeypatch):
    row = {"report_uuid": REPORT, "estate_id": ESTATE, "entry_kind": "enology_reading", "revision": 3}
    executed, approvals, audits = [], [], []

    class Cursor:
        def execute(self, sql, params):
            executed.append((sql, params))
            return 1

    @contextmanager
    def fake_transaction():
        yield None, Cursor()

    monkeypatch.setattr(mobile_intake_routes, "fetch_one", lambda *_: row)
    monkeypatch.setattr(mobile_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_routes, "transaction", fake_transaction)
    monkeypatch.setattr(mobile_intake_routes, "require_discipline_approval", lambda _request, discipline: approvals.append(discipline))
    monkeypatch.setattr(mobile_intake_routes, "audit", lambda *args: audits.append(args))
    request = Request({"type": "http", "method": "PATCH", "path": "/", "headers": [(b"x-remote-user-name", b"david")]})

    with pytest.raises(HTTPException) as conflict:
        mobile_intake_routes.review_mobile_intake(REPORT, {"status": "approved"}, request, "2")
    assert conflict.value.status_code == 409

    result = mobile_intake_routes.review_mobile_intake(REPORT, {"status": "approved"}, request, "3")
    assert result == {"saved": True, "report_uuid": REPORT, "status": "approved", "revision": "4", "domain_side_effects": []}
    assert approvals == ["enology"]
    assert len(executed) == 1 and "UPDATE mobile_intake_source_drafts" in executed[0][0]
    assert len(audits) == 1
