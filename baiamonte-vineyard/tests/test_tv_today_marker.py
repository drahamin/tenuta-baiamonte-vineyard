from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_intelligence_charts_show_vineyard_local_animated_today_marker() -> None:
    source = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")

    assert "function vineyardTodayPosition()" in source
    assert "timeZone:displayTimeZone" in source
    assert "todayPosition=vineyardTodayPosition()" in source
    assert source.count("todayPosition})") >= 2
    assert "ctx.fillText('TODAY'" in source
    assert "screen!==2" in source
    assert "todayMarkerPulse+=.55" in source
