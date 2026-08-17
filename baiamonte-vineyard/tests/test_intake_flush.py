from pathlib import Path
import unittest

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class IntakeFlushTests(unittest.TestCase):
    def test_completed_intake_can_be_archived_without_deletion(self) -> None:
        migration = (ROOT / "db/migrations/027_intake_archive.sql").read_text()
        api = (ROOT / "app/main.py").read_text()
        self.assertIn("'archived'", migration)
        self.assertIn("archived_at DATETIME(6)", migration)
        self.assertIn('@app.post("/api/v1/intake/flush-completed"', api)
        self.assertIn("source files and audit history were retained", api)
        self.assertNotIn("DELETE FROM intake_items", api)


    def test_tv_and_inbox_hide_only_archived_items(self) -> None:
        display = (ROOT / "app/display_data.py").read_text()
        script = frontend_source(ROOT)
        self.assertIn("review_status<>'archived'", display)
        self.assertIn("filter==='archived'", script)
        self.assertIn("Flush completed", (ROOT / "app/static/index.html").read_text())
