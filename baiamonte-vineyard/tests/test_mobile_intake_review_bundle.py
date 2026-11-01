import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.proposed import mobile_intake_review as review


ESTATE = "00000000-0000-4000-8000-000000000001"
REPORT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DECISION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class Cursor:
    def __init__(self, row=None):
        self.row = row
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        return 1

    def fetchone(self):
        return self.row


def use_cursor(monkeypatch, cursor):
    @contextmanager
    def fake_transaction():
        yield None, cursor
    monkeypatch.setattr(review, "transaction", fake_transaction)
    monkeypatch.setattr(review, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(review, "new_id", lambda: DECISION)
    monkeypatch.setattr(review, "audit", lambda *args: None)


def test_independent_enology_decision_is_atomic_outbox_only(monkeypatch):
    cursor = Cursor({"report_uuid": REPORT, "actor_username": "david", "entry_kind": "enology_reading", "status": "pending_review", "revision": 3})
    use_cursor(monkeypatch, cursor)
    result = review.decide_initial_enology_report(REPORT, 3, "approved", "Checked image and typed value.", "Sebastian", "Agronomist & Enologist")
    assert result["review_status"] == "approved"
    assert result["business_application_status"] == "not_applied"
    assert result["domain_side_effects"] == []
    assert result["delivery_status"] == "pending"
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "UPDATE mobile_intake_source_drafts" in sql
    assert "INSERT INTO mobile_intake_review_outbox" in sql
    assert "cellar_operations" not in sql and "inventory_movements" not in sql and "fermentation_observations" not in sql


def test_initial_flow_rejects_self_or_out_of_scope_review(monkeypatch):
    cursor = Cursor({"report_uuid": REPORT, "actor_username": "david", "entry_kind": "field_observation", "status": "pending_review", "revision": 1})
    use_cursor(monkeypatch, cursor)
    with pytest.raises(review.ReviewRejected, match="reviewer_not_authorized"):
        review.decide_initial_enology_report(REPORT, 1, "approved", "note", "david", "Agronomist & Enologist")
    with pytest.raises(review.ReviewRejected, match="outside_initial_activation_scope"):
        review.decide_initial_enology_report(REPORT, 1, "approved", "note", "sebastian", "Agronomist & Enologist")


def test_review_delivery_retries_exact_payload_and_marks_receipt(monkeypatch):
    payload = {"contract": review.CONTRACT, "decision_uuid": DECISION, "report_uuid": REPORT}
    monkeypatch.setattr(review, "estate_id", lambda: ESTATE)
    monkeypatch.setattr(review, "fetch_all", lambda *_: [{"decision_uuid": DECISION, "report_uuid": REPORT, "payload_json": json.dumps(payload)}])
    sent = []
    monkeypatch.setattr(review, "_intake_signed_post", lambda _config, path, body, _timeout: sent.append((path, body)) or {"ok": True})
    cursor = Cursor(); use_cursor(monkeypatch, cursor)
    class Config:
        enabled = True
        def validate(self): return None
    assert review.deliver_review_decisions_once(Config()) == 1
    assert sent == [(f"/sync/mobile-intake/reviews/{REPORT}", payload)]
    assert "status='delivered'" in cursor.executed[0][0]


def test_review_bundle_is_source_disabled_and_responsive():
    root = Path(__file__).resolve().parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    index = (root / "app" / "static" / "index.html").read_text(encoding="utf-8")
    css = (root / "app" / "static" / "proposed" / "mobile-intake-review.css").read_text(encoding="utf-8")
    panel = (root / "app" / "static" / "proposed" / "mobile-intake-review-panel.html").read_text(encoding="utf-8")
    assert "proposed.mobile_intake_review" not in main
    assert "mobile-intake-review.js" not in index
    assert "@media(max-width:600px)" in css
    assert "Received for review is not business-applied" in panel
    assert (root / "db" / "proposed" / "234_mobile_intake_review_outbox.sql").is_file()
    assert not (root / "db" / "migrations" / "234_mobile_intake_review_outbox.sql").exists()
