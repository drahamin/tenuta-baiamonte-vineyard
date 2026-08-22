from pathlib import Path
from unittest.mock import patch

import pytest

from app.observation_catalog import PHENOLOGY_PIPELINES, PHENOLOGY_STAGES, phenology_stage, reference_catalog, scouting_issue
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


def test_maturity_observations_wait_for_photo_evidence_before_harvest_refresh():
    for code in ("fruit_maturity", "uneven_ripening", "healthy_normal"):
        assert scouting_issue(code)["pipelines"] == ("harvest_evidence_review",)
    with patch("app.prediction_refresh.request_harvest_refresh") as harvest:
        result = _run_observation_pipelines(
            "scouting", "ripening-1", scouting_issue("fruit_maturity")["pipelines"]
        )
    assert result[0]["status"] == "evidence_required"
    harvest.assert_not_called()


def test_growth_stage_routes_only_to_harvest_not_treatment():
    source = (ROOT / "app/quick_entry.py").read_text()
    assert PHENOLOGY_PIPELINES == ("phenology_model", "harvest_prediction")
    assert "PHENOLOGY_PIPELINES if record_type == \"phenology\"" in source
    assert "treatment_prediction" not in PHENOLOGY_PIPELINES


def test_every_scouting_and_phenology_choice_has_an_explicit_route():
    catalog = reference_catalog()
    assert catalog["scouting_issues"]
    assert all(row["pipelines"] for row in catalog["scouting_issues"])
    assert len(catalog["phenology_stages"]) == len(PHENOLOGY_STAGES)
    assert all(row["pipelines"] for row in catalog["phenology_stages"])


def test_phenology_runs_stage_assimilation_then_harvest_refresh():
    with patch("app.prediction_refresh.request_harvest_refresh") as harvest:
        results = _run_observation_pipelines("phenology", "stage-1", PHENOLOGY_PIPELINES)
    assert [row["code"] for row in results] == ["phenology_model", "harvest_prediction"]
    assert [row["status"] for row in results] == ["processed", "queued"]
    harvest.assert_called_once_with("phenology", "stage-1", "Routed field evidence saved")


def test_combined_hail_and_rot_runs_multiple_pipelines():
    issue = scouting_issue("hail_mold_rot")
    assert issue["pipelines"] == ("damage_assessment", "treatment_prediction", "harvest_prediction")


def test_unknown_issue_is_held_for_review_instead_of_guessed():
    issue = scouting_issue("unrecognized leaf symptom")
    assert issue["code"] == "other"
    assert issue["pipelines"] == ("agronomy_review",)
    assert issue["legacy_detail"] == "unrecognized leaf symptom"


def test_agronomy_review_route_creates_a_durable_human_queue_item():
    source = (ROOT / "app/quick_entry.py").read_text()
    assert 'f"scouting-review:{record_id}"' in source
    assert "INSERT INTO issues_decisions" in source
    assert "Classify field scouting observation" in source


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
    assert '<select name="variety_id" required>' in app


def test_photo_damage_is_gated_by_controlled_route():
    source = (ROOT / "app/intelligence.py").read_text()
    assert 'damage_route and str(current.get("yield_impact_review_status")' in source
    assert '"damage_assessment" in scouting_issue(current.get("issue_type"))' in source


def test_saved_observation_returns_independent_pipeline_statuses():
    source = (ROOT / "app/quick_entry.py").read_text()
    assert "def _run_observation_pipelines" in source
    assert '"pipelines": pipeline_results' in source
    assert 'actor,action,entity_type,entity_id,after_data' in source


def test_all_input_channels_use_the_same_observation_router():
    quick = (ROOT / "app/quick_entry.py").read_text()
    mcp = (ROOT / "app/mcp_server.py").read_text()
    whatsapp = (ROOT / "app/whatsapp_observations.py").read_text()
    assert "def route_saved_observation" in quick
    assert "route_saved_observation(record_type, record_id" in mcp
    assert "save_quick_entry, save_kind" in whatsapp
    assert '"variety_id"' in mcp.split('"phenology":', 1)[1].split("},", 1)[0]


def test_photo_completion_is_queryable_and_refreshes_the_dashboard():
    routes = (ROOT / "app/domains/observation_routes.py").read_text()
    javascript = (ROOT / "app/static/app.js").read_text() + (ROOT / "app/static/assets/scouting.js").read_text()
    assert '@router.get("/{entity_type}/{entity_id}"' in routes
    assert 'audit(cursor, "photo_route"' in (ROOT / "app/intelligence.py").read_text()
    assert "monitorObservationAnalysis" in javascript
    assert "Photo analyzed" in javascript


def test_scope_aware_scouting_display_does_not_use_storage_anchor_as_scope():
    harvest = (ROOT / "app/domains/harvest.py").read_text()
    assert "sds.damage_scope='estate'" in harvest
    assert "sds.damage_scope='variety'" in harvest
    assert "COALESCE(sds.damage_scope,'block') IN ('block','zone')" in harvest


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
