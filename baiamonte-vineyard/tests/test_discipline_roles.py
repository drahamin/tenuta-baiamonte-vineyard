from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_defines_separate_and_combined_professional_roles() -> None:
    source = (ROOT / "app/main.py").read_text()
    roles = (ROOT / "app/domains/people_roles.py").read_text()

    assert '"Agronomist"' in roles
    assert '"Enologist"' in roles
    assert '"Agronomist & Enologist"' in roles
    assert '"name": "Sebastiano Vinci"' in source
    assert '"role": "Agronomist & Enologist"' in source
    assert '"approval_permissions": role_approval_permissions' in source


def test_approval_gates_follow_the_responsible_discipline() -> None:
    source = (ROOT / "app/main.py").read_text()
    javascript = (ROOT / "app/static/app.js").read_text()

    assert 'require_discipline_approval(request, "agronomy")' in source
    assert 'require_discipline_approval(request, "enology")' in source
    assert 'state.session?.approval_permissions?.enology' in javascript
    assert "Agronomist approval is still required" in javascript
    assert "Sebastian approval is still required" not in javascript


def test_saved_sebastian_profile_is_migrated_to_combined_role() -> None:
    migration = (ROOT / "db/migrations/061_assign_enology_approval_role.sql").read_text()

    assert "JSON_SEARCH" in migration
    assert "sebastian" in migration
    assert "Agronomist & Enologist" in migration
