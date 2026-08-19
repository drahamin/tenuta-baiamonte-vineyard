import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CleanupPassTests(unittest.TestCase):
    def test_api_version_matches_installed_release(self):
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn('version="1.3.7"', main)

    def test_placeholder_grapes_are_not_operational_harvest_dates(self):
        main = (ROOT / "app" / "main.py").read_text()
        display = (ROOT / "app" / "display_data.py").read_text()
        planning = (ROOT / "app" / "planning_sync.py").read_text()
        javascript = (ROOT / "app" / "static" / "app.js").read_text()
        exclusion = "LOWER(v.name) NOT IN ('blend','other')"
        for source in (main, display, planning):
            self.assertIn(exclusion, source)
        self.assertIn("filter(row=>!['blend','other'].includes(String(row.name||'').toLowerCase()))", javascript)

    def test_scheduled_master_refresh_only_recovers_stale_jobs(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        self.assertIn("stale_codes = {", intelligence)
        self.assertIn('interval_minutes"] * 2', intelligence)
        self.assertIn("only_codes=stale_codes", intelligence)
        self.assertIn('"mode": "stale_only" if only_codes is not None else "complete"', intelligence)


if __name__ == "__main__":
    unittest.main()
