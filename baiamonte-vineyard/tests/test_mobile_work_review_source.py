"""Synthetic adapter acceptance only: no real connections, settings or secrets."""
import copy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import re
import sqlite3

import pytest

from app import remote_erp
from app.domains import mobile_work_review_source as source
from app.domains.mobile_work_review_projection import DATASETS, SourceUnavailable, SnapshotChanged, project_page


ESTATE = "00000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
VIEW_DEFINITION = {"view_definition": "select synthetic_columns from synthetic_permitted_source where synthetic_predicate = 1", "check_option": "NONE", "security_type": "DEFINER"}
REVIEWED_VIEWS = {name: source.view_definition_fingerprint(name, VIEW_DEFINITION) for name in source._VIEWS}


def columns(view="work", dataset="tasks"):
    name, fields = DATASETS[view, dataset]
    identity = "sample_id" if name == "ro_lab_decision_queue" else "id"
    return list(dict.fromkeys(["estate_id", identity, *fields, *(["updated_at"] if name in source._CLOCKS else []), "notes", "owner_id", "password", "cost_eur"]))


def row(identifier="a", view="work", dataset="tasks", **overrides):
    result = dict.fromkeys(columns(view, dataset))
    name = DATASETS[view, dataset][0]
    result.update(estate_id=ESTATE, **{"sample_id" if name == "ro_lab_decision_queue" else "id": identifier},
                  notes="Synthetic reporting-only note", owner_id="not-mobile", password="not-selected", cost_eur=Decimal("1.2"))
    result.update(overrides)
    return result


class FakeConnection:
    def __init__(self, rows=None, *, view="work", dataset="tasks", metadata=None, fail=None, cleanup_fail=False, database_name="baiamonte_vineyard", during_read=None, definition=VIEW_DEFINITION):
        self.rows = rows if rows is not None else [row(view=view, dataset=dataset)]
        self.name = DATASETS[view, dataset][0]
        self.metadata = metadata if metadata is not None else [
            {"column_name": column, "table_type": "VIEW" if self.name in source._VIEWS else "BASE TABLE"}
            for column in columns(view, dataset)]
        for item in self.metadata:
            item.setdefault("engine", "InnoDB")
        self.fail, self.cleanup_fail = fail, cleanup_fail
        self.database_name, self.during_read = database_name, during_read
        self.definition = definition
        self.statements, self.rolled_back, self.closed = [], False, False

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, parameters=None):
        self.statements.append((sql, parameters))
        if self.fail and self.fail in sql:
            raise RuntimeError("private-driver-credential-query-data")
        if sql == "START TRANSACTION WITH CONSISTENT SNAPSHOT":
            self.snapshot = copy.deepcopy(self.rows)
        self.sql = sql
    def fetchall(self):
        if "information_schema" in self.sql:
            return copy.deepcopy(self.metadata)
        if self.during_read:
            self.during_read(self.rows)
        selected = re.findall(r"`([^`]+)`", self.sql.split(" FROM ", 1)[0])
        return [{key: record[key] for key in selected} for record in self.snapshot]
    def fetchone(self):
        if "AS bounded_capture" in self.sql:
            selected = re.findall(r"OCTET_LENGTH\(`([^`]+)`\)", self.sql)
            overhead = int(re.search(r"\(SELECT (\d+)\+6", self.sql).group(1))
            octets = lambda value: len(value if isinstance(value, bytes) else str(value).encode()) if value is not None else 0
            bounded = self.snapshot[:2001]
            return {"row_count": len(bounded), "capture_bytes": Decimal(sum(overhead + 6 * sum(octets(record[key]) for key in selected) for record in bounded))}
        return self.definition if "information_schema.views" in self.sql else {"database_name": self.database_name}
    def rollback(self):
        self.rolled_back = True
        if self.cleanup_fail: raise RuntimeError("private-rollback")
    def close(self): self.closed = True
    def commit(self): pytest.fail("read-only adapter committed")


def fixture_column_contract(connection):
    selected = [item["column_name"] for item in connection.metadata if isinstance(item.get("column_name"), str)
                and not any(part in item["column_name"] for part in source._FORBIDDEN)
                and item["column_name"] not in source._EXCLUDED.get(connection.name, set())]
    try:
        return {connection.name: source.reporting_columns_fingerprint(connection.name, selected)}
    except SourceUnavailable:
        return {connection.name: "0" * 64}


def capture(connection=None, **kwargs):
    view, dataset = kwargs.get("view", "work"), kwargs.get("dataset", "tasks")
    connection = connection or FakeConnection(view=view, dataset=dataset)
    kwargs.setdefault("reviewed_column_fingerprints", fixture_column_contract(connection))
    return source.capture_dataset(boundary=source.SourceBoundary(ESTATE), view=view, dataset=dataset,
                                  connection_factory=lambda: connection, clock=lambda: NOW,
                                  **{key: value for key, value in kwargs.items() if key not in {"view", "dataset"}})


def page(captured, *, dataset="tasks", cursor=None, **kwargs):
    return project_page(captured.snapshot.records, estate_id=ESTATE, principal_scope="synthetic-ha-principal",
                        role="admin", capabilities=frozenset({"work", f"work.{dataset}.read"}),
                        view="work", dataset=dataset, now=NOW, evidence=captured.evidence,
                        state="all", limit=1, cursor=cursor, **kwargs)


@pytest.mark.parametrize("view,dataset", [key for key in DATASETS if DATASETS[key][0] not in source._VIEWS])
def test_four_base_sources_transaction_rollback_and_minimization(view, dataset):
    connection = FakeConnection(view=view, dataset=dataset)
    captured = capture(connection, view=view, dataset=dataset, reviewed_view_fingerprints=REVIEWED_VIEWS)
    assert connection.rolled_back and connection.closed
    assert connection.statements[0] == ("SELECT DATABASE() AS database_name", None)
    assert [sql for sql, _ in connection.statements[1:5]] == [
        "SET SESSION max_statement_time=2", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        "SET TRANSACTION READ ONLY", "START TRANSACTION WITH CONSISTENT SNAPSHOT"]
    sql, args = connection.statements[-1]
    assert f"FROM `{connection.name}` WHERE estate_id=%s" in sql and args == (ESTATE,)
    assert "LIMIT 2001" in sql and "*" not in sql
    assert "password" not in sql and "cost_eur" not in sql
    record = captured.snapshot.records[0]
    assert "notes" not in record["data"] and "owner_id" not in record["data"]
    assert captured.evidence.source_generated_at == NOW == captured.evidence.last_success_at
    assert captured.evidence.degraded  # semantic/mobile gates not silently closed


@pytest.mark.parametrize("value", [None, "Échantillon", Decimal("1.2345"), date(2026, 11, 3), NOW, b"synthetic", 9007199254740993])
def test_exact_authoritative_reporting_token_for_supported_value_types(value):
    connection = FakeConnection([row(notes=value)])
    captured = capture(connection)
    permitted = {key: remote_erp._json_value(value) for key, value in connection.rows[0].items()
                 if not any(part in key for part in remote_erp.FORBIDDEN_COLUMN_FRAGMENTS)}
    assert captured.snapshot.records[0]["revision"] == str(remote_erp.reporting_row_revision(permitted))


def test_filter_policy_matches_current_exporter_for_all_six_sources():
    assert source._FORBIDDEN == remote_erp.FORBIDDEN_COLUMN_FRAGMENTS
    for name, _ in DATASETS.values():
        assert source._EXCLUDED.get(name, set()) == remote_erp.EXPLICIT_EXCLUSIONS.get(name, set())


def test_reporting_only_edit_changes_token_and_generation_without_leaking_field():
    connection = FakeConnection([row(notes="before")])
    before = capture(connection)
    connection.rows[0]["notes"] = "after"
    after = capture(connection)
    assert before.snapshot.records[0]["data"] == after.snapshot.records[0]["data"]
    assert before.snapshot.records[0]["revision"] != after.snapshot.records[0]["revision"]
    assert before.snapshot.generation != after.snapshot.generation


def test_unchanged_rows_keep_generation_across_fresh_snapshot_creation_times():
    first = capture()
    connection = FakeConnection()
    second = source.capture_dataset(boundary=source.SourceBoundary(ESTATE), view="work", dataset="tasks",
                                    connection_factory=lambda: connection, clock=lambda: NOW + timedelta(seconds=20), reviewed_column_fingerprints=fixture_column_contract(connection))
    assert first.snapshot.generation == second.snapshot.generation
    assert first.evidence.source_generated_at != second.evidence.source_generated_at


def test_rows_tokens_and_generation_share_captured_transaction_not_later_live_edit():
    connection = FakeConnection([row(title="before")], during_read=lambda rows: rows[0].update(title="after"))
    first = capture(connection)
    assert first.snapshot.records[0]["data"]["title"] == "before"
    assert connection.rows[0]["title"] == "after"
    second = capture(connection)
    assert second.snapshot.records[0]["data"]["title"] == "after"
    assert first.snapshot.generation != second.snapshot.generation


def test_actual_connection_database_mismatch_refuses_metadata_and_source_reads():
    connection = FakeConnection(database_name="unapproved_database")
    with pytest.raises(SourceUnavailable, match="database boundary"): capture(connection)
    assert connection.statements == [("SELECT DATABASE() AS database_name", None)]
    assert connection.rolled_back and connection.closed


@pytest.mark.parametrize("native", [0, 9007199254740993])
def test_future_native_integer_token_remains_lossless_and_authoritative(native):
    connection = FakeConnection()
    connection.metadata.append({"column_name": "revision", "table_type": "BASE TABLE", "engine": "InnoDB"})
    connection.rows[0]["revision"] = native
    assert capture(connection).snapshot.records[0]["revision"] == str(native)


def test_ambiguous_boolean_revision_fails_instead_of_changing_namespace():
    connection = FakeConnection()
    connection.metadata.append({"column_name": "revision", "table_type": "BASE TABLE", "engine": "InnoDB"})
    connection.rows[0]["revision"] = True
    with pytest.raises(SourceUnavailable, match="ambiguous native revision"): capture(connection)


def test_cooperative_budget_failure_rolls_back_without_returning_partial_page():
    connection = FakeConnection()
    ticks = iter([0, 13])
    with pytest.raises(SourceUnavailable, match="budget"): capture(connection, monotonic=lambda: next(ticks))
    assert connection.rolled_back and connection.closed


def test_unknown_source_timezone_cannot_be_silently_selected():
    with pytest.raises(SourceUnavailable, match="source clock reinterpretation"):
        capture(source_datetime_timezone=timezone(timedelta(hours=1)))


def test_later_page_membership_or_data_change_is_conflict_not_silent_mixing():
    connection = FakeConnection([row("a"), row("b")])
    initial = capture(connection)
    cursor = page(initial)["next_cursor"]
    assert cursor
    connection.rows.append(row("c"))
    with pytest.raises(SnapshotChanged): page(capture(connection), cursor=cursor)


def test_naive_source_clock_unknown_and_utc_override_cannot_invent_a_writer_contract():
    connection = FakeConnection([row(updated_at=NOW.replace(tzinfo=None))])
    assert capture(connection).snapshot.records[0]["source_updated_at"] is None
    with pytest.raises(SourceUnavailable, match="source clock reinterpretation"):
        capture(connection, source_datetime_timezone=timezone.utc)


@pytest.mark.parametrize("value", [date(2026, 11, 3), "2026-11-03", NOW + timedelta(seconds=1), None])
def test_date_only_missing_or_future_source_clock_not_replaced_by_capture(value):
    assert capture(FakeConnection([row(updated_at=value)])).snapshot.records[0]["source_updated_at"] is None


@pytest.mark.parametrize("dataset", ["open", "queue"])
def test_unverified_view_semantics_denied_before_connect(dataset):
    with pytest.raises(SourceUnavailable, match="view dependencies"):
        source.capture_dataset(boundary=source.SourceBoundary(ESTATE), view="review" if dataset == "queue" else "work",
                               dataset=dataset, connection_factory=lambda: pytest.fail("connected"), clock=lambda: NOW)


@pytest.mark.parametrize("boundary", [source.SourceBoundary("invalid"), source.SourceBoundary(ESTATE, db_name="other"), source.SourceBoundary(ESTATE, db_host="localhost")])
def test_database_scope_denied_before_connect(boundary):
    with pytest.raises(SourceUnavailable):
        source.capture_dataset(boundary=boundary, view="work", dataset="tasks", connection_factory=lambda: pytest.fail("connected"), clock=lambda: NOW)


@pytest.mark.parametrize("rows", [[row(), row()], [row(estate_id="other")], [row("a")] * 2001, [row(notes="x" * (source.MAX_CAPTURE_BYTES + 1))]])
def test_bad_scope_identity_or_overflow_rolls_back_whole_capture(rows):
    connection = FakeConnection(rows)
    with pytest.raises(SourceUnavailable): capture(connection)
    assert connection.rolled_back and connection.closed


def test_queue_logical_sample_identity_must_be_unique():
    connection = FakeConnection([row("same", view="review", dataset="queue")] * 2, view="review", dataset="queue")
    with pytest.raises(SourceUnavailable): capture(connection, view="review", dataset="queue", reviewed_view_fingerprints=REVIEWED_VIEWS)
    assert connection.statements == []  # No fingerprint can bypass dependency hold.


@pytest.mark.parametrize("fail", ["START TRANSACTION", "information_schema", "FROM `tasks`"])
def test_driver_errors_redacted_and_resources_closed(fail):
    connection = FakeConnection(fail=fail)
    with pytest.raises(SourceUnavailable) as caught: capture(connection)
    assert "private" not in str(caught.value)
    assert connection.rolled_back and connection.closed


def test_cleanup_failure_is_redacted_and_still_closes():
    connection = FakeConnection(cleanup_fail=True)
    with pytest.raises(SourceUnavailable, match="source cleanup unavailable"): capture(connection)
    assert connection.closed


@pytest.mark.parametrize("metadata", [[], [{"column_name": "id", "table_type": "VIEW"}], [{"column_name": "bad`column", "table_type": "BASE TABLE"}], [{"column_name": "id", "table_type": "BASE TABLE"}] * 129])
def test_schema_kind_missing_unsafe_or_over_bound_fails_without_source_select(metadata):
    connection = FakeConnection(metadata=metadata)
    with pytest.raises(SourceUnavailable): capture(connection)
    assert not any("FROM `tasks`" in sql for sql, _ in connection.statements)
    assert connection.rolled_back and connection.closed


def test_adapter_stays_unregistered_no_live_connector_or_proposed_grants():
    root = Path(__file__).parents[1]
    for path in (root / "app/main.py", root / "app/domains/mobile_site_routes.py"):
        assert "mobile_work_review_source" not in path.read_text()
    text = Path(source.__file__).read_text()
    for forbidden in ("from ..db", "get_settings", "pymysql", "APIRouter", "remote_erp import", "commit(", "SELECT *", "FOR UPDATE"):
        assert forbidden not in text


@pytest.mark.parametrize("definition", [None, {**VIEW_DEFINITION, "view_definition": None}, {**VIEW_DEFINITION, "view_definition": "changed predicate"}, {**VIEW_DEFINITION, "security_type": "INVOKER"}])
def test_missing_or_drifted_view_definition_refuses_data_without_fallback(definition):
    connection = FakeConnection(dataset="open", definition=definition)
    with pytest.raises(SourceUnavailable): capture(connection, dataset="open", reviewed_view_fingerprints=REVIEWED_VIEWS)
    assert not any("FROM `v_open_work`" in sql for sql, _ in connection.statements)
    assert connection.statements == []


def test_view_definition_access_denial_is_redacted_without_source_fallback():
    connection = FakeConnection(dataset="open", fail="information_schema.views")
    with pytest.raises(SourceUnavailable, match="view dependencies"):
        capture(connection, dataset="open", reviewed_view_fingerprints=REVIEWED_VIEWS)
    assert not any("FROM `v_open_work`" in sql for sql, _ in connection.statements)


@pytest.mark.parametrize("engine", [None, "MyISAM", "MEMORY", "Aria", "unknown"])
def test_nontransactional_or_unknown_engine_rejected_before_source_preflight(engine):
    connection = FakeConnection()
    for item in connection.metadata: item["engine"] = engine
    with pytest.raises(SourceUnavailable, match="schema unavailable"): capture(connection)
    assert not any("FROM `tasks`" in sql for sql, _ in connection.statements)
    assert connection.rolled_back and connection.closed


@pytest.mark.parametrize("rows", [[row()] * 2001, [row(notes="x" * source.MAX_CAPTURE_BYTES)]])
def test_preflight_rejects_overflow_before_fetching_full_payload(rows):
    connection = FakeConnection(rows)
    with pytest.raises(SourceUnavailable): capture(connection)
    assert any("AS bounded_capture" in sql for sql, _ in connection.statements)
    assert not any(sql.startswith("SELECT `") for sql, _ in connection.statements)
    assert connection.rolled_back and connection.closed


@pytest.mark.parametrize("preflight", [None, {}, {"row_count": True, "capture_bytes": 1}, {"row_count": 1, "capture_bytes": -1}, {"row_count": 1, "capture_bytes": Decimal("NaN")}, {"row_count": 1, "capture_bytes": Decimal("1.5")}])
def test_malformed_preflight_never_fetches_payload(preflight):
    connection = FakeConnection()
    original = connection.fetchone
    connection.fetchone = lambda: preflight if "AS bounded_capture" in connection.sql else original()
    with pytest.raises(SourceUnavailable): capture(connection)
    assert not any(sql.startswith("SELECT `") for sql, _ in connection.statements)


def test_schema_or_engine_ddl_race_detected_after_preflight_before_payload_fetch():
    connection = FakeConnection()
    original = connection.fetchone
    def race():
        result = original()
        if "AS bounded_capture" in connection.sql:
            connection.metadata[0]["engine"] = "MyISAM"
        return result
    connection.fetchone = race
    with pytest.raises(SourceUnavailable, match="schema changed"): capture(connection)
    assert not any(sql.startswith("SELECT `") for sql, _ in connection.statements)
    assert connection.rolled_back and connection.closed


def test_payload_count_mismatch_refuses_partial_dataset():
    connection = FakeConnection()
    original = connection.fetchone
    connection.fetchone = lambda: {"row_count": 0, "capture_bytes": 0} if "AS bounded_capture" in connection.sql else original()
    with pytest.raises(SourceUnavailable, match="count changed"): capture(connection)


def test_missing_column_authority_cannot_connect_or_autodiscover_a_grant():
    with pytest.raises(SourceUnavailable, match="column authority"):
        source.capture_dataset(boundary=source.SourceBoundary(ESTATE), view="work", dataset="tasks",
                               connection_factory=lambda: pytest.fail("connected"), clock=lambda: NOW)


def test_new_permitted_name_must_not_silently_expand_full_token_inputs():
    connection = FakeConnection()
    reviewed = fixture_column_contract(connection)
    connection.metadata.append({"column_name": "unexpected_sensitive_field", "table_type": "BASE TABLE", "engine": "InnoDB"})
    connection.rows[0]["unexpected_sensitive_field"] = "not approved"
    with pytest.raises(SourceUnavailable, match="reporting columns changed"):
        capture(connection, reviewed_column_fingerprints=reviewed)
    assert not any("FROM `tasks`" in sql for sql, _ in connection.statements)
    assert connection.rolled_back and connection.closed


def test_reference_hook_compares_on_immutable_full_permitted_input_then_discards_it():
    connection = FakeConnection([row(notes="synthetic-private-reference-canary")])
    seen = []
    def reference(data):
        seen.append(data["notes"])
        with pytest.raises(TypeError): data["notes"] = "changed"
        return remote_erp.reporting_row_revision(data)
    captured = capture(connection, reporting_token_reference=reference)
    assert seen == ["synthetic-private-reference-canary"]
    assert "notes" not in captured.snapshot.records[0]["data"]


@pytest.mark.parametrize("value", [True, -1, "1"])
def test_invalid_or_mismatched_reference_fails_closed(value):
    connection = FakeConnection()
    with pytest.raises(SourceUnavailable, match="reporting token mismatch"):
        capture(connection, reporting_token_reference=lambda _data: value)
    assert connection.closed and connection.rolled_back


@pytest.mark.parametrize("values", [[], ["\x00\n\r\t\\\""], ["Échantillon🍇"], [None, "", "abc"], ["x"] * 2001])
def test_exact_generated_preflight_sql_executes_and_bounds_canonical_json_in_sqlite(values):
    db = sqlite3.connect(":memory:")
    def octets(value):
        return len(value if isinstance(value, bytes) else str(value).encode()) if value is not None else None
    db.create_function("OCTET_LENGTH", 1, octets)
    db.execute("CREATE TABLE tasks(id TEXT,estate_id TEXT,notes TEXT)")
    db.executemany("INSERT INTO tasks VALUES(?,?,?)", [(str(index), ESTATE, value) for index, value in enumerate(values)])
    db.execute("INSERT INTO tasks VALUES('other','other-estate','excluded')")
    try:
        count, bound = db.execute(source._preflight_sql("tasks", ["id", "estate_id", "notes"], "id").replace("%s", "?"), (ESTATE,)).fetchone()
        rows = db.execute("SELECT id,estate_id,notes FROM tasks WHERE estate_id=? ORDER BY id LIMIT 2001", (ESTATE,)).fetchall()
        actual = sum(len(source._canonical(dict(zip(["id", "estate_id", "notes"], row))).encode()) for row in rows)
        assert count == min(len(values), 2001) and bound >= actual
    finally:
        db.close()
