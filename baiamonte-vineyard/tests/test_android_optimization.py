from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_dashboard_pages_support_android_webview_and_keyboard_resizing():
    for page in ("app/static/index.html", "app/static/crew.html", "app/static/display.html"):
        source = read(page)
        assert "interactive-widget=resizes-content" in source
        assert 'name="mobile-web-app-capable" content="yes"' in source
        assert 'name="application-name"' in source

    javascript = read("app/static/app.js")
    css = read("app/static/app.css")
    assert "window.visualViewport" in javascript
    assert "--app-visible-height" in javascript
    assert "android-webview" in javascript
    assert "ha-embedded" in javascript
    assert "Home Assistant Companion WebView" in css
    assert "html.ha-embedded .topbar" in css
    assert "(pointer:coarse)" in css
    assert "display-mode:standalone" in css


def test_android_pwa_has_native_maskable_icons():
    manifest = read("app/static/site.webmanifest")
    assert '"src": "android-icon-192.png"' in manifest
    assert '"sizes": "192x192"' in manifest
    assert '"src": "android-icon-512.png"' in manifest
    assert '"sizes": "512x512"' in manifest
    assert manifest.count('"purpose": "any maskable"') >= 3
    for name, size in (("android-icon-192.png", (192, 192)), ("android-icon-512.png", (512, 512))):
        with Image.open(ROOT / "app/static" / name) as image:
            assert image.size == size


def test_cellar_tablets_keep_full_data_in_android_landscape_and_portrait():
    server = read("app/tank_label_server.py")
    css = read("app/static/assets/tank-label.css")
    javascript = read("app/static/assets/tank-label.js")
    worker = read("app/static/assets/tank-label-sw.js")
    proxy = read("custom_components/baiamonte_branding/label_proxy.py")

    assert server.count("interactive-widget=resizes-content") == 3
    assert 'DISPLAY_ASSET_VERSION = "1.4.32"' in server
    assert '"sizes": "192x192"' in server
    assert '"sizes": "512x512"' in server
    assert '@display_app.get("/brand/icon-192.png")' in server
    assert '@display_app.get("/brand/icon-512.png")' in server
    assert "--label-visible-width" in javascript
    assert "android-display" in javascript
    assert "dedicated Fully Kiosk tablet sizing" in css
    assert "min-width:900px" in css and "max-height:900px" in css
    assert "min-width:600px" in css and "orientation:portrait" in css
    assert "white-space:normal" in css
    assert 'const VERSION = "1.4.32"' in worker
    assert "icon-(?:192|512)" in proxy


def test_today_hero_uses_live_weather_and_rome_day_night_artwork():
    html = read("app/static/index.html")
    javascript = read("app/static/app.js")
    weather_effects = read("app/static/weather-effects.js")
    css = read("app/static/app.css")

    assert 'class="today-weather-landscape"' in html
    assert 'class="today-weather-orb"' in html
    assert 'class="today-vine-rows"' in html
    assert "updateHeroPeriod:updateTodayHeroPeriod" in javascript
    assert "function updateHeroPeriod" in weather_effects
    assert "timeZone:'Europe/Rome'" in weather_effects
    assert "scene==='clear'&&night" in javascript
    assert "hero.classList.toggle('is-night',night)" in weather_effects
    assert ".today-hero.is-night .today-weather-orb" in css
    assert ".today-ridge" in css
    assert ".today-vine-rows" in css
