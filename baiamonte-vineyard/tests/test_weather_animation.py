import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WeatherAnimationTests(unittest.TestCase):
    def test_operations_today_maps_live_conditions_to_distinct_scenes(self):
        source = (ROOT / "app" / "static" / "app.js").read_text()
        for scene in (
            "storm",
            "pouring",
            "sleet",
            "hail",
            "snow",
            "drizzle",
            "rain",
            "fog",
            "partly-cloudy",
            "cloudy",
            "clear-night",
            "clear",
            "windy",
        ):
            self.assertIn(f"return'{scene}'", source)
        self.assertIn("weather-scene-${scene}", source)

    def test_rain_uses_depth_based_canvas_and_reduced_motion_fallback(self):
        css = (ROOT / "app" / "static" / "app.css").read_text()
        script = (ROOT / "app" / "static" / "weather-effects.js").read_text()
        html = (ROOT / "app" / "static" / "index.html").read_text()
        self.assertIn("weather-canvas", script)
        self.assertIn("devicePixelRatio", script)
        self.assertIn("canvas-rain::before{display:none", css)
        self.assertIn("baiamonteStormFlash", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("weather-effects.js", html)

    def test_tv_today_uses_the_same_live_condition_family(self):
        script = (ROOT / "app" / "static" / "display.js").read_text()
        css = (ROOT / "app" / "static" / "display-extra.css").read_text()
        html = (ROOT / "app" / "static" / "display.html").read_text()
        self.assertIn("weather-scene-${scene}", script)
        self.assertIn("BaiamonteWeatherEffects", script)
        self.assertIn("canvas-rain::before{display:none", css)
        self.assertIn("tvStormFlash", css)
        self.assertIn("weather-effects.js", html)

    def test_tv_weather_page_has_animated_icons_and_scene(self):
        markup = (ROOT / "app" / "static" / "display.html").read_text()
        script = (ROOT / "app" / "static" / "display.js").read_text()
        styles = (ROOT / "app" / "static" / "display-extra.css").read_text()
        self.assertIn('id="tvWeatherPageMotion"', markup)
        self.assertIn('id="tvWeatherCurrent"', markup)
        self.assertIn("function weatherIcon", script)
        self.assertIn("weather-forecast-icon", script)
        self.assertIn("@keyframes weatherIconFloat", styles)
        self.assertIn("prefers-reduced-motion:reduce", styles)

    def test_tv_remote_supports_samsung_key_paths_and_focus_recovery(self):
        script = (ROOT / "app" / "static" / "display.js").read_text()
        for token in (
            "registerKeyBatch",
            "MediaTrackPrevious",
            "MediaTrackNext",
            "document.addEventListener('keydown',handleSamsungRemote,true)",
            "document.addEventListener('keyup',handleSamsungRemote,true)",
            "restoreTvFocus()",
        ):
            self.assertIn(token, script)


if __name__ == "__main__":
    unittest.main()
