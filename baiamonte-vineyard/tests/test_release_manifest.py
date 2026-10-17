import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_addon_manifest_matches_latest_changelog_release() -> None:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    manifest_match = re.search(r'^version:\s*"([^"]+)"', config, re.MULTILINE)
    changelog_match = re.search(r"^##\s+(\S+)", changelog, re.MULTILINE)

    assert manifest_match, "config.yaml must declare a quoted add-on version"
    assert changelog_match, "CHANGELOG.md must begin with a release heading"
    assert manifest_match.group(1) == changelog_match.group(1)
