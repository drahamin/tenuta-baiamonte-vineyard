from contextlib import contextmanager
from datetime import datetime
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from app.mcp_server import record_sebastiano_tank_reading
from app.personal_whatsapp_identity import source_key

COMMON = {
    "platform_message_id": "3EB0-EXACT-MESSAGE",
    "observed_at": "2026-10-16T08:15:00+02:00",
    "source_text": " Grenache 9 Babo 24 C ",
    "babo": 9,
    "temp_c": 24,
    "confirmation": "RECORD SEBASTIANO TANK READING",
}
LID = "237945617420500@lid"
COMPOSITE = f"false_{LID}_3EB0-EXACT-MESSAGE"


class FakeDatabase:
    """Models an estate-row lock held until transaction exit, not a live DB."""

    def __init__(self, rows=()):
        self.lock = Lock()
        self.rows = {row["source_observation_id"]: dict(row) for row in rows}
        self.inserts = 0
        self.events = []

    @contextmanager
    def transaction(self):
        cursor = FakeCursor(self)
        try:
            yield None, cursor
        finally:
            if cursor.locked:
                self.lock.release()


class FakeCursor:
    def __init__(self, db):
        self.db, self.locked, self.one, self.many = db, False, None, []

    def execute(self, sql, args):
        if "FROM estates" in sql:
            self.db.lock.acquire()
            self.locked = True
            self.one = {"id": "estate"}
        elif "FROM fermentation_observations" in sql:
            self.many = [self.db.rows[k] for k in args[1:] if k in self.db.rows]
        elif "FROM wine_lots" in sql:
            self.one = {"id": "lot", "code": "GRN-2026-02", "stage": "fermentation", "lot_status": "active", "current_container_id": "tank"}
        elif "FROM cellar_containers" in sql:
            self.one = {"id": "tank", "code": "T-39", "name": "Tank 39", "status": "in_use"}
        elif sql.startswith("INSERT INTO fermentation_observations"):
            assert self.locked
            key = args[3]
            assert key not in self.db.rows, "unique estate/source key"
            self.db.rows[key] = {"id": args[0], "source_observation_id": key, "observed_at": args[4], "wine_lot_id": args[2]}
            self.db.inserts += 1
        elif sql.startswith("INSERT INTO integration_events"):
            self.db.events.append(args)
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


@pytest.fixture
def invoke():
    def setup(db):
        stack = [patch("app.mcp_server.require_write_confirmation"),
                 patch("app.mcp_server.estate_id", return_value="estate"),
                 patch("app.mcp_server.transaction", side_effect=db.transaction),
                 patch("app.mcp_server.audit"),
                 patch("app.mcp_server.fetch_one", return_value={"reading_id": "stored", "status": "whatsapp_personal"})]
        for p in stack:
            p.start()
        return stack
    stacks = []
    def run(db):
        stacks.extend(setup(db))
        return record_sebastiano_tank_reading
    yield run
    for p in reversed(stacks):
        p.stop()


def row(key, ident):
    return {"id": ident, "source_observation_id": key, "observed_at": datetime(2026, 10, 16), "wine_lot_id": "lot"}


def test_exact_duplicate_is_returned_without_mutation(invoke):
    db = FakeDatabase([row(source_key(COMMON["platform_message_id"]), "existing")])
    result = invoke(db)(**COMMON, verified_lid=LID, mapping_provenance="current connector lookup")
    assert result["duplicate"] and result["reading_id"] == "existing"
    assert db.inserts == 0 and not db.events


def test_legacy_to_new_candidate_held_without_mutation_and_preserves_evidence(invoke):
    db = FakeDatabase([row(source_key(COMMON["platform_message_id"]), "legacy")])
    result = invoke(db)(**{**COMMON, "platform_message_id": COMPOSITE}, chat_id=LID,
                        sender_jid=LID, verified_lid=LID, mapping_provenance="current connector lookup")
    assert result["review_required"] and not result["duplicate"]
    assert result["reason"] == "unverified_cross_format_id_match"
    assert result["candidate_reading_id"] == "legacy"
    assert result["source_evidence"]["raw_platform_message_id"] == COMPOSITE
    assert result["source_evidence"]["source_text"] == COMMON["source_text"]
    assert result["source_evidence"]["source_message_at"] == COMMON["observed_at"]
    assert result["source_evidence"]["mapping_provenance"] == "current connector lookup"
    assert db.inserts == 0 and not db.events


def test_unverified_new_provider_message_never_inserts(invoke):
    db = FakeDatabase()
    result = invoke(db)(**{**COMMON, "platform_message_id": COMPOSITE}, chat_id=LID, sender_jid=LID, verified_lid=LID)
    assert result["reason"] == "provider_identity_and_historical_id_equivalence_unverified"
    assert db.inserts == 0


def test_missing_mapping_holds_new_legacy_candidate(invoke):
    db = FakeDatabase()
    result = invoke(db)(**COMMON)
    assert result["review_required"] and not result["recorded"]
    assert db.inserts == 0 and not db.events


def test_exact_provider_duplicate_returns_existing_without_insert(invoke):
    db = FakeDatabase([row(source_key(COMPOSITE), "already-recorded")])
    result = invoke(db)(**{**COMMON, "platform_message_id": COMPOSITE}, chat_id=LID, sender_jid=LID, verified_lid=LID)
    assert result["duplicate"] and result["reading_id"] == "already-recorded"
    assert db.inserts == 0 and not db.events


def test_multiple_candidates_block_even_with_exact_match(invoke):
    db = FakeDatabase([row(source_key(COMPOSITE), "one"), row(source_key(COMMON["platform_message_id"]), "two")])
    result = invoke(db)(**{**COMMON, "platform_message_id": COMPOSITE}, chat_id=LID, sender_jid=LID, verified_lid=LID)
    assert result["reason"] == "conflicting_multiple_candidate_records"
    assert result["candidate_count"] == 2 and db.inserts == 0


def test_legacy_unmatched_is_held_with_exact_provenance(invoke):
    db = FakeDatabase()
    result = invoke(db)(**COMMON, verified_lid=LID, mapping_provenance="current connector lookup")
    assert result["review_required"] and not result["recorded"]
    assert result["source_evidence"]["source_text"] == COMMON["source_text"]
    assert result["source_evidence"]["raw_platform_message_id"] == COMMON["platform_message_id"]
    assert db.inserts == 0 and not db.events


def test_concurrent_same_legacy_message_is_held(invoke):
    db = FakeDatabase()
    fn = invoke(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: fn(**COMMON, verified_lid=LID, mapping_provenance="current connector lookup"), range(2)))
    assert db.inserts == 0
    assert all(x["review_required"] and not x["recorded"] for x in results)


def test_rejects_conflicting_identity_and_pre_cutoff(invoke):
    db = FakeDatabase()
    fn = invoke(db)
    for kwargs in ({"chat_id": "other@s.whatsapp.net"}, {"sender_jid": "other@s.whatsapp.net"},
                   {"source_channel": "business_whatsapp"}, {"observed_at": "2026-10-15T23:59:59+02:00"},
                   {"platform_message_id": f"true_{LID}_3EB0-EXACT-MESSAGE", "chat_id": LID, "sender_jid": LID, "verified_lid": LID},
                   {"sample_at": "2026-10-16T08:00:00+02:00"}, {"sample_time_basis": "reported_sample_time"}):
        with pytest.raises(ValueError):
            fn(**{**COMMON, **kwargs})
    assert db.inserts == 0
