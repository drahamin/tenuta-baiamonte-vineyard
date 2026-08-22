from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_tv_layout_keeps_every_card_visible_on_narrow_displays():
    css = (STATIC / "display.css").read_text(encoding="utf-8")
    assert ".dashboard-grid>*:last-child{display:none}" not in css
    assert ".split>*:last-child{display:none}" not in css
    assert "@media(max-aspect-ratio:1.4){.dashboard-grid{grid-template-columns:repeat(2,minmax(0,1fr))}" in css


def test_tv_styles_do_not_require_has_selector_support():
    html = (STATIC / "display.html").read_text(encoding="utf-8")
    css = (STATIC / "display-extra.css").read_text(encoding="utf-8")
    assert ":has(" not in css
    assert "intelligence-pressure-card" in html
    assert html.count("tv-chart-legend-card") == 2


def test_tv_helpers_load_before_main_display_bundle():
    html = (STATIC / "display.html").read_text(encoding="utf-8")
    vessels = html.index('src="assets/assets/wine-vessels.js')
    weather = html.index('src="assets/weather-effects.js')
    display = html.index('src="assets/display.js')
    assert vessels < weather < display


def test_tv_animation_and_overflow_work_are_throttled_for_embedded_browsers():
    script = (STATIC / "display.js").read_text(encoding="utf-8")
    assert "todayMarkerPulse+=.55;redraw()},500)" in script
    assert "scrollIntelligenceAlerts();scrollTvOverflowLists()},500)" in script
    assert "scrollIntelligenceAlerts();scrollTvOverflowLists()},100)" not in script
