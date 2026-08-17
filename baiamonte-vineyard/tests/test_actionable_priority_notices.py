from pathlib import Path
import unittest

from tests.source_helpers import frontend_source


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
        self.assertIn("The assistant is temporarily unavailable", source)

    def test_completed_legacy_notices_are_reconciled(self):
        source = (ROOT / "app/main.py").read_text()
        self.assertIn("def _reconcile_answered_whatsapp_notices", source)
        self.assertIn("i.review_status IN ('approved','rejected','archived')", source)
        self.assertIn("intervention_required", source)
        self.assertIn("'chatbot_reply','manager_camera_snapshot','inbound_routing'", source)
        self.assertIn("important-intake:gmail", source)

    def test_reconciliation_failure_does_not_hide_stored_alerts(self):
        source = (ROOT / "app/main.py").read_text()
        endpoint = source[source.index('def list_alerts'):source.index('@app.patch("/api/v1/alerts/{alert_id}"')]
        self.assertIn("try:", endpoint)
        self.assertIn("except Exception:", endpoint)
        self.assertIn("returning stored alerts", endpoint)
        self.assertIn("SELECT * FROM alerts", endpoint)

        frontend = frontend_source(ROOT)
        self.assertIn("Alerts could not refresh", frontend)
        self.assertIn("delete state.loadErrors[path]", frontend)

    def test_non_vineyard_email_questions_do_not_create_priority_notices(self):
        source = (ROOT / "app/intelligence.py").read_text()
        self.assertIn("question_requires_review", source)
        self.assertIn('classification != "other"', source)


if __name__ == "__main__":
    unittest.main()
