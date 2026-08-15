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

    def test_rain_uses_layered_motion_and_reduced_motion_fallback(self):
        css = (ROOT / "app" / "static" / "app.css").read_text()
        self.assertIn("baiamonteRainField", css)
        self.assertIn("baiamonteRainSplash", css)
        self.assertIn("baiamonteStormFlash", css)
        self.assertIn("prefers-reduced-motion:reduce", css)

    def test_tv_today_uses_the_same_live_condition_family(self):
        script = (ROOT / "app" / "static" / "display.js").read_text()
        css = (ROOT / "app" / "static" / "display-extra.css").read_text()
        self.assertIn("weather-scene-${scene}", script)
        self.assertIn("tvRainField", css)
        self.assertIn("tvStormFlash", css)


if __name__ == "__main__":
    unittest.main()
