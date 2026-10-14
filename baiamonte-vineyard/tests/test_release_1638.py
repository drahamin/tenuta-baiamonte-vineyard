from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_variety_laboratory_standards_are_configurable_and_audited() -> None:
    migration = (ROOT / "db/migrations/208_variety_laboratory_standards.sql").read_text()
    routes = (ROOT / "app/domains/laboratory_routes.py").read_text()
    outlook = (ROOT / "app/domains/laboratory.py").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/lab-outlook.js").read_text()

    assert "CREATE TABLE IF NOT EXISTS variety_lab_standards" in migration
    assert "UNIQUE KEY uq_variety_lab_standard" in migration
    assert '@router.put("/api/v1/labs/variety-standards"' in routes
    assert "require_discipline_approval(request, \"enology\")" in routes
    assert 'audit(cursor, "approve_standard", "variety_lab_standard"' in routes
    assert "_apply_variety_lab_standards(rows, configured_standards)" in outlook
    assert 'id="labStandardDialog"' in html
    assert "Approve and save" in html
    assert "function openLabStandardEditor" in javascript
    assert "target_min:numeric('target_min')" in javascript


def test_release_version_is_1_10_51() -> None:
    assert 'version: "1.10.59"' in (ROOT / "config.yaml").read_text()
