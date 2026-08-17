from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Release111CellarSeasonTests(unittest.TestCase):
    def test_agronomy_routes_use_string_season_id(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        start = source.index('def agronomy_dashboard(')
        end = source.index('@app.get("/api/v1/olives/dashboard"', start)
        agronomy_routes = source[start:end]

        self.assertNotIn('season["id"]', agronomy_routes)
        self.assertIn('(estate_id(), season)', agronomy_routes)


if __name__ == "__main__":
    unittest.main()
