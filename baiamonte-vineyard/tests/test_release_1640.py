from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def test_public_feed_advances_to_next_vintage_after_estate_harvest() -> None:
    source = (ROOT / "app/service.py").read_text()
    assert "def _public_vintage_year" in source
    assert "h.source_type='estate_harvest'" in source
    assert "PUBLIC_HARVEST_VARIETIES.issubset(harvested)" in source
    assert 'row["status"] = "complete"' in source
    assert 'row["status"] = "planning"' in source


def test_public_website_uses_the_feed_vintage() -> None:
    source = (REPOSITORY_ROOT / "website/about.php").read_text()
    assert "'year'       => $payload['year'] ?? $harvest_year" in source
    assert "$published_harvest_year = (int)$harvest['year'];" in source
    assert "$harvest_year = $published_harvest_year;" in source


def test_release_version() -> None:
    assert 'version: "1.10.70"' in (ROOT / "config.yaml").read_text()
