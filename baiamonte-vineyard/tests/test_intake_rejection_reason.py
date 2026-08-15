from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IntakeRejectionReasonTests(unittest.TestCase):
    def test_migration_adds_auditable_reason(self):
        migration = (ROOT / "db/migrations/026_intake_review_reason.sql").read_text()
        self.assertIn("review_reason TEXT", migration)

    def test_api_requires_and_saves_rejection_reason(self):
        source = (ROOT / "app/main.py").read_text()
        self.assertIn('if status == "rejected" and not review_reason', source)
        self.assertIn("SET review_status=%s,review_reason=%s,reviewed_by=%s", source)
        self.assertIn("review_reason,reviewed_by,reviewed_at", source)

    def test_communications_explain_rejections(self):
        script = (ROOT / "app/static/app.js").read_text()
        self.assertIn("WHY REJECTED", script)
        self.assertIn("Why is this item being rejected?", script)
        self.assertIn("No rejection reason was recorded for this earlier item.", script)


if __name__ == "__main__":
    unittest.main()
