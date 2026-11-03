from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domains import mobile_work_review_projection as projection


ESTATE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
EVIDENCE = projection.SnapshotEvidence(
    before="synthetic-generation", after="synthetic-generation",
    permitted_objects=frozenset(value[0] for value in projection.DATASETS.values()),
    source_generated_at="2026-11-03T11:59:00Z", last_success_at="2026-11-03T11:59:10Z",
)


def row(identifier="a", *, object_name="tasks", estate=ESTATE, **data):
    return {"object": object_name, "id": identifier, "revision": "9007199254740993",
            "source_updated_at": "2020-01-01T12:00:00Z",
            "data": {"estate_id": estate, "status": "planned", "title": "Synthetic task", **data}}


def page(records=(), **kwargs):
    return projection.project_page(records, **{
        "estate_id": ESTATE, "principal_scope": "synthetic-admin-policy-v1", "role": "admin",
        "capabilities": frozenset({"work", "review", *projection.DATASET_CAPABILITIES.values()}), "view": "work", "dataset": "tasks",
        "now": NOW, "evidence": EVIDENCE, **kwargs,
    })


@pytest.mark.parametrize("role,capabilities", [("worker", {"work"}), ("enologist", {"review"}), ("operator", {"work"}), ("admin", set())])
def test_denied_before_inspecting_records(role, capabilities):
    class Unreadable:
        def __len__(self): pytest.fail("denied records accessed")
        def __iter__(self): pytest.fail("denied records accessed")
    with pytest.raises(projection.ProjectionForbidden):
        page(Unreadable(), role=role, capabilities=frozenset(capabilities))


def test_existing_parent_grants_do_not_authorize_new_datasets():
    with pytest.raises(projection.ProjectionForbidden):
        page(capabilities=frozenset({"work", "review"}))
    from app.domains import mobile_site_routes
    existing = set().union(*mobile_site_routes._ROLE_CAPABILITIES.values())
    assert not existing.intersection(projection.DATASET_CAPABILITIES.values())


def test_scope_allowlist_lossless_revision_and_clock_separation():
    result = page([row("a", labor_cost_eur=900, owner="private", notes="private", payload={"x": 1}, estimated_hours=0),
                   row("b", estate=OTHER), row("c", object_name="lab_reviews")])
    assert result["available"] and len(result["items"]) == 1
    item = result["items"][0]
    assert item["revision"] == "9007199254740993"
    assert item["data"] == {"title": "Synthetic task", "status": "planned", "estimated_hours": 0}
    assert item["source_updated_at"] == "2020-01-01T12:00:00Z"
    assert result["source"]["source_generated_at"] == "2026-11-03T11:59:00Z"
    assert result["source"]["data_age_seconds"] == 60


@pytest.mark.parametrize("view,dataset", sorted(projection.DATASETS))
def test_all_six_closed_datasets(view, dataset):
    object_name, fields = projection.DATASETS[view, dataset]
    result = page([row(object_name=object_name, **{fields[0]: "Synthetic"})], view=view, dataset=dataset, state="all")
    assert result["dataset"] == dataset and len(result["items"]) == 1


@pytest.mark.parametrize("status,flag,complete", [
    ("closed", False, True), ("closed", True, False), ("closed", "unknown", False),
    ("closed", None, False), ("closed", "0", True), ("future_state", False, False),
    ("unreviewed", False, False), ("reviewing", False, False), ("monitoring", False, False),
])
def test_lab_only_explicit_closed_with_clear_flag_completes(status, flag, complete):
    records = [row(object_name="ro_lab_decision_queue", review_status=status, needs_review=flag)]
    assert bool(page(records, view="review", dataset="queue", state="completed")["items"]) is complete
    assert bool(page(records, view="review", dataset="queue", state="pending")["items"]) is not complete


def test_cursor_is_binary_sorted_and_bound_to_generation_filters_estate_and_principal():
    records = [row("c"), row("a"), row("b")]
    first = page(records, limit=1)
    cursor = first["next_cursor"]
    assert len(cursor) <= 512 and first["items"][0]["id"] == "a"
    assert page(records, limit=1, cursor=cursor)["items"][0]["id"] == "b"
    for kwargs in ({"principal_scope": "different"}, {"estate_id": OTHER},
                   {"evidence": replace(EVIDENCE, before="new", after="new")}):
        with pytest.raises(projection.SnapshotChanged): page(records, cursor=cursor, **kwargs)
    for kwargs in ({"dataset": "activities"}, {"state": "completed"}, {"view": "review", "dataset": "queue"}):
        with pytest.raises(ValueError): page(records, cursor=cursor, **kwargs)


@pytest.mark.parametrize("cursor", ["", "!invalid", "a" * 513, "bnVsbA", "W10", "e30"])
def test_malformed_cursors_fail_closed(cursor):
    with pytest.raises(ValueError): page(cursor=cursor)


def test_snapshot_changed_and_missing_source_never_yield_false_empty_current():
    with pytest.raises(projection.SnapshotChanged):
        page(evidence=replace(EVIDENCE, after="changed"))
    result = page(evidence=projection.SnapshotEvidence())
    assert result["available"] is False and result["items"] == [] and result["source"]["state"] == "unavailable"
    result = page(evidence=replace(EVIDENCE, permitted_objects=frozenset()))
    assert result["available"] is False


@pytest.mark.parametrize("source_time", [None, "invalid", "2026-11-03", "2026-11-03 11:59:00", "2099-01-01T00:00:00Z"])
def test_missing_naive_date_only_future_clock_is_never_ready(source_time):
    result = page(evidence=replace(EVIDENCE, source_generated_at=source_time))
    assert result["source"]["state"] == "degraded"
    assert result["source"]["data_age_seconds"] is None


@pytest.mark.parametrize("last_success", [None, "2099-01-01T00:00:00Z", "2026-11-03T11:00:00Z"])
def test_unverified_or_inconsistent_success_clock_is_not_ready(last_success):
    result = page(evidence=replace(EVIDENCE, last_success_at=last_success))
    assert result["source"]["state"] == "degraded"


def test_stale_snapshot_does_not_rewrite_old_item_time():
    result = page([row()], evidence=replace(EVIDENCE, source_generated_at="2026-11-01T12:00:00Z"))
    assert result["source"]["state"] == "degraded"
    assert result["items"][0]["source_updated_at"] == "2020-01-01T12:00:00Z"


@pytest.mark.parametrize("revision", [True, 1.0, -1, "01", "1e3", "1" * 21])
def test_invalid_revisions_are_not_coerced(revision):
    record = row(); record["revision"] = revision
    with pytest.raises(projection.SourceUnavailable): page([record])


def test_duplicates_input_bound_and_unknown_fields_fail_safe():
    with pytest.raises(projection.SourceUnavailable): page([row(), row()])
    with pytest.raises(projection.SourceUnavailable): page([row()] * (projection.MAX_INPUT_ROWS + 1))
    item = page([row(estimated_hours=float("nan"), block_id=None, category=["untrusted"])])["items"][0]
    assert item["data"] == {"title": "Synthetic task", "status": "planned"}


@pytest.mark.parametrize("kwargs", [{"limit": True}, {"limit": 101}, {"dataset": "finance"}, {"state": "pending"}])
def test_request_validation(kwargs):
    with pytest.raises(ValueError): page(**kwargs)


def test_projection_remains_unregistered_and_has_no_io():
    root = Path(projection.__file__).parents[1]
    for name in ("main.py", "domains/mobile_site_routes.py"):
        assert "mobile_work_review_projection" not in (root / name).read_text()
    source = Path(projection.__file__).read_text()
    for forbidden in ("from ..db", "fetch_all", "fetch_one", "transaction(", "requests.", "httpx", "APIRouter", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in source


def test_sanitized_native_contract_fixture():
    import json
    fixture = Path(__file__).parent / "fixtures/mobile_work_review_snapshot_v1.json"
    assert page([row()]) == json.loads(fixture.read_text())
    assert page([row()])["ok"] is True
    assert page(evidence=projection.SnapshotEvidence())["ok"] is True
