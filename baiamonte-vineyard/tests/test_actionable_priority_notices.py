from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ActionablePriorityNoticeTests(unittest.TestCase):
    def test_successful_whatsapp_reply_resolves_question_notice(self):
        source = (ROOT / "app/main.py").read_text()
        self.assertIn("def _resolve_answered_whatsapp_notice", source)
        self.assertIn("important-intake:whatsapp:{message_id}", source)
        self.assertIn("if resolve_notice:", source)

    def test_pending_and_failed_actions_keep_notice_open(self):
        source = (ROOT / "app/main.py").read_text()
        self.assertGreaterEqual(source.count("resolve_notice=False"), 6)
        self.assertIn("def _mark_whatsapp_intervention_notice", source)
        self.assertIn("'$.intervention_required',TRUE", source)
        self.assertIn("Confirmation required", source)
        self.assertIn("The assistant could not answer", source)

    def test_completed_legacy_notices_are_reconciled(self):
        source = (ROOT / "app/main.py").read_text()
        self.assertIn("def _reconcile_answered_whatsapp_notices", source)
        self.assertIn("i.review_status IN ('approved','rejected','archived')", source)
        self.assertIn("intervention_required", source)
        self.assertIn("'chatbot_reply','manager_camera_snapshot','inbound_routing'", source)


if __name__ == "__main__":
    unittest.main()
