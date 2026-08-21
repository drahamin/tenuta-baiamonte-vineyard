from pathlib import Path
from unittest.mock import patch

import pytest

from app.observation_catalog import phenology_stage, reference_catalog, scouting_issue
from app.quick_entry import _run_observation_pipelines


ROOT = Path(__file__).resolve().parents[1]


def test_hail_routes_to_damage_and_harvest_models():
    issue = scouting_issue("hail")
    assert issue["damage_type"] == "hail"
    assert issue["pipelines"] == ("damage_assessment", "treatment_followup", "harvest_prediction")


def test_hail_followup_requests_evidence_without_inventing_a_treatment():
    with (
        patch("app.quick_entry.refresh_scouting_damage_proposal") as damage,
        patch("app.prediction_refresh.request_harvest_refresh") as harvest,
    ):
        results = _run_observation_pipelines("scouting", "hail-1", scouting_issue("hail")["pipelines"])
    assert [row["code"] for row in results] == ["damage_assessment", "treatment_followup", "harvest_prediction"]
    assert results[1]["status"] == "review_required"
    assert "24–72" in results[1]["detail"]
    damage.assert_called_once_with("hail-1")
    harvest.assert_called_once()


def test_mold_routes_to_treatment_not_damage():
    issue = scouting_issue("powdery_mildew")
    assert issue["pipelines"] == ("treatment_prediction",)
    assert "damage_assessment" not in issue["pipelines"]


def test_combined_hail_and_rot_runs_multiple_pipelines():
    issue = scouting_issue("hail_mold_rot")
    assert issue["pipelines"] == ("damage_assessment", "treatment_prediction", "harvest_prediction")


def test_unknown_issue_is_held_for_review_instead_of_guessed():
    issue = scouting_issue("unrecognized leaf symptom")
    assert issue["code"] == "other"
    assert issue["pipelines"] == ("agronomy_review",)
    assert issue["legacy_detail"] == "unrecognized leaf symptom"


def test_growth_stage_is_controlled_and_gets_canonical_label():
    assert phenology_stage("fruit set") == ("fruit_set", "Fruit set")
    with pytest.raises(ValueError):
        phenology_stage("probably flowering")


def test_reference_catalog_explains_each_pipeline():
    catalog = reference_catalog()
    combined = next(row for row in catalog["scouting_issues"] if row["code"] == "hail_mold_rot")
    assert len(combined["pipelines"]) == 3
    assert all("→" in route["label"] for route in combined["pipelines"])


def test_mobile_forms_use_selects_and_show_route_preview():
    scouting = (ROOT / "app/static/assets/scouting.js").read_text()
    app = (ROOT / "app/static/app.js").read_text()
    assert '<select name="issue_type" required>' in scouting
    assert 'data-scouting-route-list' in scouting
    assert '<input name="issue_type"' not in scouting
    assert '<select name="stage_code" required>' in app
    assert '<input name="stage_code" required' not in app


def test_photo_damage_is_gated_by_controlled_route():
    source = (ROOT / "app/intelligence.py").read_text()
    assert 'damage_route and str(current.get("yield_impact_review_status")' in source
    assert '"damage_assessment" in scouting_issue(current.get("issue_type"))' in source


def test_saved_observation_returns_independent_pipeline_statuses():
    source = (ROOT / "app/quick_entry.py").read_text()
    assert "def _run_observation_pipelines" in source
    assert '"pipelines": pipeline_results' in source
    assert 'actor,action,entity_type,entity_id,after_data' in source


def test_combined_observation_executes_all_pipelines_independently():
    with (
        patch("app.quick_entry.refresh_scouting_damage_proposal") as damage,
        patch("app.intelligence.refresh_disease_pressure") as treatment,
        patch("app.prediction_refresh.request_harvest_refresh") as harvest,
    ):
        results = _run_observation_pipelines(
            "scouting", "observation-1", scouting_issue("hail_mold_rot")["pipelines"]
        )
    damage.assert_called_once_with("observation-1")
    treatment.assert_called_once_with()
    harvest.assert_called_once_with("scouting", "observation-1", "Routed field evidence saved")
    assert [row["code"] for row in results] == [
        "damage_assessment", "treatment_prediction", "harvest_prediction"
    ]
    assert [row["status"] for row in results] == ["processed", "processed", "queued"]


def test_pipeline_failure_is_reported_without_stopping_other_routes():
    with (
        patch("app.quick_entry.refresh_scouting_damage_proposal", side_effect=RuntimeError("damage offline")),
        patch("app.prediction_refresh.request_harvest_refresh") as harvest,
    ):
        results = _run_observation_pipelines(
            "scouting", "observation-2", ("damage_assessment", "harvest_prediction")
        )
    assert results[0]["status"] == "retry_required"
    assert results[1]["status"] == "queued"
    harvest.assert_called_once()
