from dataclasses import replace
from pathlib import Path

import pytest

from app.domains import mobile_work_review_projection as projection
from app.domains import mobile_work_review_snapshot as snapshot
from test_mobile_work_review_projection import ESTATE, OTHER, EVIDENCE, page, row as projection_row


def row(identifier="a", **kwargs):
    record = projection_row(identifier, **kwargs)
    if record["object"] != "ro_lab_decision_queue":
        record["data"]["id"] = identifier
    return record


def prepare(records, **kwargs):
    return snapshot.prepare_snapshot_input(records, **{"estate_id": ESTATE, "view": "work", "dataset": "tasks", **kwargs})


def test_generation_stable_for_order_and_tokens_not_recomputed():
    first = prepare([row("b"), row("a")])
    second = prepare([row("a"), row("b")])
    assert first.generation == second.generation
    assert [record["id"] for record in first.records] == ["a", "b"]
    assert first.records[0]["revision"] == "9007199254740993"
    with pytest.raises(TypeError): first.records[0]["revision"] = "1"
    with pytest.raises(TypeError): first.records[0]["data"]["title"] = "changed"


@pytest.mark.parametrize("records", [[row("b")], [row("a"), row("b")], [row("a", title="Changed output")]])
def test_membership_and_output_changes_change_generation(records):
    assert prepare([row("a")]).generation != prepare(records).generation


def test_reporting_token_change_affects_generation_without_minimized_field_change():
    record = row()
    initial = prepare([record])
    record["revision"] = "9007199254740994"
    assert prepare([record]).generation != initial.generation


def test_input_mutation_cannot_change_captured_snapshot():
    record = row()
    captured = prepare([record])
    record["data"]["title"] = "later edit"
    assert captured.records[0]["data"]["title"] == "Synthetic task"


def test_queue_uses_exact_sample_identity_and_preserves_original_token():
    record = row("a" * 64, object_name="ro_lab_decision_queue", sample_id="sample-1")
    result = prepare([record], view="review", dataset="queue")
    assert result.records[0]["id"] == "sample-1"
    assert result.records[0]["revision"] == record["revision"]


@pytest.mark.parametrize("records", [
    [row("a" * 64, object_name="ro_lab_decision_queue")],
    [row("a" * 64, object_name="ro_lab_decision_queue", sample_id="sample-1"), row("b" * 64, object_name="ro_lab_decision_queue", sample_id="sample-1")],
])
def test_missing_or_duplicate_queue_identity_fails_entire_read(records):
    with pytest.raises(projection.SourceUnavailable): prepare(records, view="review", dataset="queue")


@pytest.mark.parametrize("flag", [None, "unknown", [], {"unexpected": True}, float("nan")])
def test_queue_unknown_flags_stay_pending_after_minimization(flag):
    record = row("a" * 64, object_name="ro_lab_decision_queue", sample_id="sample-1", review_status="closed", needs_review=flag)
    captured = prepare([record], view="review", dataset="queue")
    evidence = replace(EVIDENCE, before=captured.generation, after=captured.generation)
    assert len(page(captured.records, view="review", dataset="queue", evidence=evidence)["items"]) == 1
    assert page(captured.records, view="review", dataset="queue", state="completed", evidence=evidence)["items"] == []


@pytest.mark.parametrize("records", [[row(estate=OTHER)], [row(object_name="lab_reviews")], [row(), row()]])
def test_scope_or_duplicate_source_fails_instead_of_partial_success(records):
    with pytest.raises(projection.SourceUnavailable): prepare(records)


def test_non_queue_identity_must_match_source_primary_id():
    record = row(); record["data"]["id"] = "different"
    with pytest.raises(projection.SourceUnavailable): prepare([record])


def test_time_derived_value_changes_generation_but_no_event_time_is_fabricated():
    record = row(object_name="v_open_work", days_until_due=2)
    record["source_updated_at"] = None
    first = prepare([record], dataset="open")
    record["data"]["days_until_due"] = 1
    second = prepare([record], dataset="open")
    assert first.generation != second.generation
    assert second.records[0]["source_updated_at"] is None


def test_changes_between_pages_yield_snapshot_conflict():
    initial = prepare([row("a"), row("b")])
    evidence = replace(EVIDENCE, before=initial.generation, after=initial.generation)
    first = page(initial.records, evidence=evidence, limit=1)
    changed = prepare([row("a"), row("b", title="later edit")])
    with pytest.raises(projection.SnapshotChanged):
        page(changed.records, evidence=replace(evidence, before=changed.generation, after=changed.generation), cursor=first["next_cursor"])


def test_preparer_has_no_source_io_or_router_registration():
    source = Path(snapshot.__file__).read_text()
    for forbidden in ("from ..db", "fetch_all", "fetch_one", "transaction(", "APIRouter", "datetime.now", "reporting_row_revision("):
        assert forbidden not in source


def test_preparer_never_truncates_over_bound_input():
    with pytest.raises(projection.SourceUnavailable):
        prepare([row()] * (projection.MAX_INPUT_ROWS + 1))


@pytest.mark.parametrize("revision", [None, True, 1.5, "-1", "01"])
def test_preparer_refuses_missing_or_coerced_change_tokens(revision):
    record = row(); record["revision"] = revision
    with pytest.raises(projection.SourceUnavailable): prepare([record])
