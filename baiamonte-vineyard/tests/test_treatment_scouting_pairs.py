from datetime import datetime
from unittest.mock import patch

import pytest

from app.domains.treatment_scouting import auto_link_observation, treatment_scouting_workflows, validate_observation_pair


def _application_query(sql, _params):
    if "FROM spray_applications" in sql:
        return {"id": "t1", "application_date": "2026-08-22", "block_id": "b1", "crop_scope": "vineyard", "status": "completed", "purpose": "Downy mildew"}
    return None


def test_pair_validation_requires_same_target_block_and_window():
    values = {"treatment_application_id": "t1", "treatment_observation_phase": "pre", "treatment_target_code": "downy_mildew",
              "observed_at": "2026-08-20T12:00", "block_id": "b1", "issue_type": "downy_mildew"}
    with patch("app.domains.treatment_scouting.fetch_one", side_effect=_application_query), patch(
        "app.domains.treatment_scouting._targets", return_value=[{"target_code": "downy_mildew", "target_name": "Downy mildew"}]
    ):
        assert validate_observation_pair(values) == {"application_id": "t1", "phase": "pre", "target_code": "downy_mildew"}
        with pytest.raises(ValueError, match="vineyard block"):
            validate_observation_pair({**values, "block_id": "b2"})
        with pytest.raises(ValueError, match="within 14 days before"):
            validate_observation_pair({**values, "observed_at": "2026-07-01T12:00"})


def test_workflow_marks_completed_treatment_followup_due():
    application = {"id": "t1", "application_date": "2026-08-20", "purpose": "Downy mildew", "status": "completed", "block_id": "b1", "block_code": "GRC-01"}

    def rows(sql, _params):
        if "FROM spray_applications a" in sql:
            return [application]
        if "FROM treatment_scouting_links" in sql:
            return [{"phase": "pre", "target_code": "downy_mildew", "observation_id": "s1", "observed_at": datetime(2026, 8, 19, 12), "issue_type": "downy_mildew", "severity": "low", "incidence_pct": 2}]
        return []

    with patch("app.domains.treatment_scouting.fetch_all", side_effect=rows), patch(
        "app.domains.treatment_scouting._targets", return_value=[{"target_code": "downy_mildew", "target_name": "Downy mildew"}]
    ):
        workflow = treatment_scouting_workflows(2026)[0]
    assert workflow["workflow_status"] in {"followup_due", "followup_overdue"}
    assert workflow["next_phase"] == "post"
    assert workflow["pre_count"] == 1
    assert workflow["post_count"] == 0


def test_automatic_pairing_links_only_one_unambiguous_match():
    applications = [{"id": "t1", "application_date": "2026-08-22"}]
    cursor = type("Cursor", (), {"execute": lambda self, *_args: 1})()
    context = type("Context", (), {"__enter__": lambda self: (None, cursor), "__exit__": lambda self, *_args: None})()
    with patch("app.domains.treatment_scouting.fetch_all", return_value=applications), patch(
        "app.domains.treatment_scouting._targets", return_value=[{"target_code": "downy_mildew", "target_name": "Downy mildew"}]
    ), patch("app.domains.treatment_scouting.transaction", return_value=context):
        result = auto_link_observation({"observed_at": "2026-08-20T12:00", "block_id": "b1", "issue_type": "downy_mildew"}, "s1")
    assert result == {"application_id": "t1", "phase": "pre", "target_code": "downy_mildew"}


def test_automatic_pairing_refuses_ambiguous_treatments():
    applications = [{"id": "t1", "application_date": "2026-08-22"}, {"id": "t2", "application_date": "2026-08-23"}]
    with patch("app.domains.treatment_scouting.fetch_all", return_value=applications), patch(
        "app.domains.treatment_scouting._targets", return_value=[{"target_code": "downy_mildew", "target_name": "Downy mildew"}]
    ):
        result = auto_link_observation({"observed_at": "2026-08-20T12:00", "block_id": "b1", "issue_type": "downy_mildew"}, "s1")
    assert result is None
