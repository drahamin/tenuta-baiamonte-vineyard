from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_observation_form_can_join_an_existing_event_or_issue() -> None:
    scouting = (ROOT / "app/static/assets/scouting.js").read_text()
    reference = (ROOT / "app/domains/reference_chains.py").read_text()
    assert 'name="existing_chain"' in scouting
    assert 'value": f"event:' in reference
    assert 'value": f"issue:' in reference


def test_scouting_save_validates_and_persists_chain_linkage() -> None:
    source = (ROOT / "app/quick_entry.py").read_text()
    assert 'values["damage_event_key"] = chain_id' in source
    assert 'values["linked_issue_id"] = chain_id' in source
    assert "Only a damage observation can be added to a damage-event chain" in source


def test_system_assessment_approval_uses_non_conflicting_action() -> None:
    backend = (ROOT / "app/domains/damage_routes.py").read_text()
    frontend = (ROOT / "app/static/assets/cellar.js").read_text()
    assert 'approve-system-proposal' in backend
    assert "data-approve-system-proposal" in frontend
    assert "Read-only chain calculation" in frontend
