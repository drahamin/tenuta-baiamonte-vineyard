from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "app.js"


def test_open_dashboard_does_not_force_reload_for_a_new_release():
    source = APP_JS.read_text(encoding="utf-8")

    asset_check = source.split("function ensureCurrentAssetVersion", 1)[1].split("\n", 1)[0]
    assert "location.reload" not in asset_check
    assert "refresh when convenient" in asset_check
    assert "sessionStorage[key]" in asset_check
