from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_bottling_projection_includes_recorded_purchased_fruit() -> None:
    source = (ROOT / "app/domains/bottling.py").read_text()
    assert "def _fruit_projection_basis" in source
    assert "purchased fruit is always additional" in source
    assert "h.source_type='purchased'" in source
    assert "remaining_estate_kg" in source
    assert "kg purchased" in source


def test_release_version_is_1_10_52() -> None:
    assert 'version: "1.10.71"' in (ROOT / "config.yaml").read_text()
