import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import mobile_intake_sync
from app import remote_erp
from app import access
from app.config import Settings, get_settings
from app.domains import attachments, mobile_intake_policy, mobile_intake_routes


ESTATE = "00000000-0000-4000-8000-000000000001"
REPORT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
AUTHOR_USER = "22456456-cc5e-11f1-b520-0200fd82860d"
AUTHOR_HA = "50302bdc5bed42ac92dbfc2b4b4e5181"


def item(expected_container="8", expected_lot="4"):
    author = {"user_id": AUTHOR_USER, "username": "david", "ha_user_id": AUTHOR_HA, "server_role": "admin"}
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
    return {"report_uuid": REPORT, "estate_id": ESTATE, "actor": author, "kind": "enology_reading", "payload": payload, "lease_token": "x" * 43, "attachments": [], "authority": {"capability": "intake.submit", "session_active": True, "checked_at": datetime.now(timezone.utc).isoformat()}}


def config():
    secret = base64.urlsafe_b64encode(b"i" * 32).decode().rstrip("=")
    return mobile_intake_sync.RemoteIntakeConfig(True, "https://cantinabaiamonte.com/erp", "baiamonte-intake-1", secret, 10, {"david": "admin"}, {"david": {"website_user_id": AUTHOR_USER, "ha_user_id": AUTHOR_HA}}, frozenset({"enology_reading"}))


def test_payload_revalidates_actor_kind_and_enology_units(monkeypatch):
    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    payload, expected = mobile_intake_sync._validate_payload(item(), config())
    assert payload["author"]["username"] == "david"
    assert expected == {"container_id": "8", "wine_lot_id": "4"}
    wrong_actor = item(); wrong_actor["payload"]["author"] = {**wrong_actor["actor"], "username": "other"}
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="actor_binding_mismatch"):
        mobile_intake_sync._validate_payload(wrong_actor, config())
    wrong_unit = item(); wrong_unit["payload"]["measurements"][0]["unit"] = "degree_brix"
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="enology_measurement_invalid"):
        mobile_intake_sync._validate_payload(wrong_unit, config())
    stale_role = item(); stale_role["actor"]["server_role"] = stale_role["payload"]["author"]["server_role"] = "operator"
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="actor_authority_not_current"):
        mobile_intake_sync._validate_payload(stale_role, config())
    wrong_identity = item(); wrong_identity["actor"]["ha_user_id"] = wrong_identity["payload"]["author"]["ha_user_id"] = "f402bf2ae76842088ac296979a9f4a8e"
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="actor_identity_binding_mismatch"):
        mobile_intake_sync._validate_payload(wrong_identity, config())
    wrong_kind = item(); wrong_kind["actor"]["username"] = wrong_kind["payload"]["author"]["username"] = "unrelated-operator"
    with pytest.raises(mobile_intake_sync.IntakeRejected, match="actor_authority_not_current"):
        mobile_intake_sync._validate_payload(wrong_kind, config())


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
    accepted = {"authoritative_record_ids": [REPORT], "actual_revisions": {"container_id": "8"}, "reason": "pending_review", "evidence_durable": True}
    monkeypatch.setattr(mobile_intake_sync, "fetch_one", lambda *_: {"payload_sha256": digest, "ingest_status": "validated", "ingest_result_json": json.dumps(accepted)})
    status, result = mobile_intake_sync._accept_report(config(), current)
    assert status == "accepted"
    assert result["reason"] == "pending_review"
    changed = item(); changed["payload"]["note"] = "different"
    with pytest.raises(mobile_intake_sync.IntakeConflict, match="source_uuid_collision"):
        mobile_intake_sync._accept_report(config(), changed)


def test_lost_conflict_ack_replays_exact_stored_conflict(monkeypatch):
    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    current = item(); digest = hashlib.sha256(remote_erp._canonical(current["payload"]).encode()).hexdigest()
    conflict = {"authoritative_record_ids": [REPORT], "actual_revisions": {"container_id": "91", "wine_lot_id": "44"}, "reason": "expected_revision_conflict", "evidence_durable": True}
    monkeypatch.setattr(mobile_intake_sync, "fetch_one", lambda *_: {"payload_sha256": digest, "ingest_status": "conflict", "ingest_result_json": json.dumps(conflict)})
    status, result = mobile_intake_sync._accept_report(config(), current)
    assert status == "conflict"
    assert result == conflict


def test_retry_replays_durable_result_only_while_all_evidence_is_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(mobile_intake_sync, "estate_id", lambda: ESTATE)
    evidence = b"\x89PNG\r\n\x1a\nproof"
    digest = hashlib.sha256(evidence).hexdigest()
    current = item()
    current["payload"]["attachments"] = [{"sha256": digest, "media_type": "image/png", "byte_count": len(evidence), "filename": "proof.png"}]
    payload_digest = hashlib.sha256(remote_erp._canonical(current["payload"]).encode()).hexdigest()
    accepted = {"authoritative_record_ids": [REPORT], "actual_revisions": {"container_id": "8"}, "reason": "pending_review", "evidence_durable": True}
    evidence_path = tmp_path / "proof.bin"; evidence_path.write_bytes(evidence)
    monkeypatch.setattr(mobile_intake_sync, "fetch_one", lambda *_: {"payload_sha256": payload_digest, "ingest_status": "validated", "ingest_result_json": json.dumps(accepted)})
    monkeypatch.setattr(mobile_intake_sync, "fetch_all", lambda *_: [{"stored_path": str(evidence_path), "media_type": "image/png", "file_sha256": digest}])
    assert mobile_intake_sync._accept_report(config(), current) == ("accepted", accepted)
    evidence_path.write_bytes(evidence + b"corrupt")
    with pytest.raises(RuntimeError, match="stored mobile intake evidence is incomplete"):
        mobile_intake_sync._accept_report(config(), current)


def test_attachment_publication_is_atomic_and_has_no_staging_residue(monkeypatch, tmp_path):
    monkeypatch.setattr(attachments, "ATTACHMENT_ROOT", tmp_path)
    stored = attachments.store_attachment(b"durable evidence", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "proof.pdf", "evidence")
    assert stored.path.read_bytes() == b"durable evidence"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_outbound_processor_posts_bounded_result_without_applying_domain_side_effects(monkeypatch):
    intake_config = config()
    posted = []

    def signed_post(_config, path, payload, _timeout=180):
        if path.endswith("/requests"): return {"ok": True, "reports": [item()]}
        posted.append((path, payload)); return {"ok": True}

    monkeypatch.setattr(mobile_intake_sync, "_intake_signed_post", signed_post)
    monkeypatch.setattr(mobile_intake_sync, "_accept_report", lambda *_: ("accepted", {"authoritative_record_ids": [REPORT], "actual_revisions": {}, "reason": "pending_review", "evidence_durable": True}))
    assert mobile_intake_sync.process_mobile_intake_once(intake_config) == 1
    assert posted == [(f"/sync/mobile-intake/results/{REPORT}", {"lease_token": "x" * 43, "status": "accepted", "result": {"authoritative_record_ids": [REPORT], "actual_revisions": {}, "reason": "pending_review", "evidence_durable": True}})]


def test_human_review_route_is_disabled_before_any_database_access(monkeypatch):
    request = Request({"type": "http", "method": "PATCH", "path": "/", "headers": []})
    with pytest.raises(HTTPException) as unavailable:
        mobile_intake_routes.review_mobile_intake(REPORT, {"status": "approved"}, request, "3")
    assert unavailable.value.status_code == 503


def test_actual_http_routes_disable_review_queue_and_bind_mine_to_exact_author(monkeypatch):
    seen = []
    monkeypatch.setattr(mobile_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_routes, "fetch_all", lambda sql, params: seen.append((sql, params)) or [])
    app = FastAPI()
    app.include_router(mobile_intake_routes.router)
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="route-test-key")
    monkeypatch.setattr(mobile_intake_policy, "runtime_option", lambda *_: {"enabled": True, "website_user_id": AUTHOR_USER, "website_username": "david", "ha_user_id": AUTHOR_HA, "ha_username": "rahamin", "allowed_kinds": ["enology_reading"]})
    client = TestClient(app)

    assert client.get("/api/v1/mobile-intake").status_code == 401
    assert client.get("/api/v1/mobile-intake", headers={"X-API-Key": "route-test-key"}).status_code == 503
    monkeypatch.setattr(mobile_intake_policy.access, "trusted_ingress_request", lambda _request: True)
    app.dependency_overrides[access.authorize] = lambda: None
    mine = client.get("/api/v1/mobile-intake/mine", headers={"X-Ingress-Path": "/api/hassio_ingress/mobile", "X-Remote-User-Name": "rahamin", "X-Remote-User-Id": AUTHOR_HA})
    assert mine.status_code == 200
    assert seen[-1][1] == (ESTATE, "david")


def test_actual_ha_ingress_keeps_full_intake_review_queue_disabled(monkeypatch):
    monkeypatch.setattr(mobile_intake_routes, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(mobile_intake_routes, "fetch_all", lambda *_: [])
    monkeypatch.setattr(access, "trusted_ingress_request", lambda _request: True)
    monkeypatch.setattr(access, "profile_access_level", lambda username: {"viewer": "viewer", "operator": "operations", "david": "admin"}.get(username))
    app = FastAPI(); app.include_router(mobile_intake_routes.router)
    app.dependency_overrides[get_settings] = lambda: Settings(api_key="")
    client = TestClient(app)
    ingress = {"X-Ingress-Path": "/api/hassio_ingress/test", "X-Remote-User-Name": "viewer"}
    assert client.get("/api/v1/mobile-intake", headers=ingress).status_code == 503
    ingress["X-Remote-User-Name"] = "operator"
    assert client.get("/api/v1/mobile-intake", headers=ingress).status_code == 503
    ingress["X-Remote-User-Name"] = "david"
    assert client.get("/api/v1/mobile-intake", headers=ingress).status_code == 503
