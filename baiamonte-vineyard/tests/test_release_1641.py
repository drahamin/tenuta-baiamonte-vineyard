from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_2024_mamma_fiamma_blend_is_reconciled_without_inventing_components():
    sql = (ROOT / "db/migrations/210_reconcile_2024_mamma_fiamma_blend.sql").read_text()
    assert "Mamma Fiamma · Nerello Mascalese / Grenache blend" in sql
    assert "combined_grapes_kg',1558" in sql
    assert "'finished_wine_l',881" in sql
    assert "'component_split','unknown'" in sql
    assert "exclude from single-variety yield learning" in sql


def test_release_1641_is_current():
    assert 'version: "1.10.71"' in (ROOT / "config.yaml").read_text()
    assert "## 1.10.61" in (ROOT / "CHANGELOG.md").read_text()
