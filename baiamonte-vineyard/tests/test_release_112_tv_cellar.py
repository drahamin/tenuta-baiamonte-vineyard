from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Release112TvCellarTests(unittest.TestCase):
    def test_tv_uses_three_authoritative_harvest_dates_and_readable_pressure_lines(self) -> None:
        javascript = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "display-extra.css").read_text(encoding="utf-8")

        self.assertIn("function tvHarvestSchedule", javascript)
        self.assertIn("recommended_pick_date", javascript)
        self.assertIn("forecast.final_forecast_date", javascript)
        self.assertIn("GDD & HARVEST FORECAST", javascript)
        self.assertIn("function tvHarvestGdd", javascript)
        self.assertIn("GW2000", javascript)
        self.assertIn("function pressureSparkline", javascript)
        self.assertIn('viewBox="0 0 100 34"', javascript)
        self.assertIn(".tv-harvest-three", css)
        self.assertIn(".tv-pressure-roll svg", css)

    def test_physical_vessel_type_and_process_stage_are_independent(self) -> None:
        dashboard = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        display = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

        for javascript in (dashboard, display):
            self.assertIn("function vesselType(type,stage)", javascript)
            self.assertIn("function cellarStageClass(stage)", javascript)
            self.assertIn("vessel-${vesselType", javascript)
            self.assertIn("stage-${cellarStageClass", javascript)
        self.assertIn('name="container_type"', html)
        self.assertIn("Save vessel & mode", html)
        self.assertIn('"container_type": container_type', source)


if __name__ == "__main__":
    unittest.main()
