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


def test_all_tv_pages_expand_their_primary_content_to_the_available_height():
    css = (STATIC / "display-extra.css").read_text(encoding="utf-8")
    for screen in range(12):
        if screen == 2:
            assert '.screen[data-screen="2"].active{display:flex' in css
        else:
            assert f'.screen[data-screen="{screen}"]' in css
    for primary in (
        ">.dashboard-grid",
        ">.split",
        ">.camera-wall",
        ">.traffic-shell",
        ">.planning-tv-grid",
        ">.cellar-tv-grid",
        ">.weather-tv-grid",
        ">.tv-etna-grid",
        ">.communications-tv-grid",
    ):
        assert primary in css
    assert "height:auto;min-height:0;flex:1 1 auto" in css


def test_sparse_operational_pages_add_live_context_instead_of_empty_filler():
    html = (STATIC / "display.html").read_text(encoding="utf-8")
    script = (STATIC / "display.js").read_text(encoding="utf-8")
    assert 'id="tvVintageContext"' in html
    assert 'id="tvPlanningContext"' in html
    assert "$('tvVintageContext').innerHTML" in script
    assert "$('tvPlanningContext').innerHTML" in script
    assert "Lead field pressure" in script
    assert "Estate readiness" in script


def test_large_today_screen_uses_available_weather_and_operational_context():
    html = (STATIC / "display.html").read_text(encoding="utf-8")
    script = (STATIC / "display.js").read_text(encoding="utf-8")
    css = (STATIC / "display-extra.css").read_text(encoding="utf-8")
    for element_id in ("tvTodayCondition", "tvTodayWeatherAge", "tvTodayWeatherDetail", "tvTodayForecast", "tvWorkContext", "tvDecisionContext"):
        assert f'id="{element_id}"' in html
    for marker in ("Dew point", "VPD", "24h range", "PEAK WIND", "planningStatus.calendar_connected"):
        assert marker in script
    assert "window.BaiamonteWeatherEffects?.derived" in script
    assert ".tv-today-weather-detail" in css
    assert ".tv-today-forecast" in css
    assert ".tv-card-facts" in css
    assert "minmax(300px,1.28fr)" in css
