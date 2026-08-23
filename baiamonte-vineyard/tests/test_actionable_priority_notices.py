from pathlib import Path
import unittest

from tests.source_helpers import backend_source, frontend_source


ROOT = Path(__file__).resolve().parents[1]


class ActionablePriorityNoticeTests(unittest.TestCase):
    @staticmethod
    def _notice_source():
        return (ROOT / "app/whatsapp_notices.py").read_text()

    @staticmethod
    def _assistant_source():
        return (ROOT / "app/domains/communications_whatsapp_assistant.py").read_text()

    def test_successful_whatsapp_reply_resolves_question_notice(self):
        source = self._notice_source()
        wiring = self._assistant_source()
        self.assertIn("def resolve_answered_notice", source)
        self.assertIn("resolve_answered_notice as _resolve_answered_whatsapp_notice", wiring)
        self.assertIn("important-intake:whatsapp:{message_id}", source)
        self.assertIn("if resolve_notice:", wiring)

    def test_pending_and_failed_actions_keep_notice_open(self):
        source = self._notice_source()
        wiring = self._assistant_source()
        self.assertGreaterEqual(wiring.count("resolve_notice=False"), 6)
        self.assertIn("def mark_intervention_notice", source)
        self.assertIn("mark_intervention_notice as _mark_whatsapp_intervention_notice", wiring)
        self.assertIn("'$.intervention_required',TRUE", source)
        self.assertIn("Confirmation required", wiring)
        self.assertIn("The assistant is temporarily unavailable", wiring)

    def test_completed_legacy_notices_are_reconciled(self):
        source = self._notice_source()
        wiring = (ROOT / "app/main.py").read_text()
        self.assertIn("def reconcile_answered_notices", source)
        self.assertIn("reconcile_answered_notices as _reconcile_answered_whatsapp_notices", wiring)
        self.assertIn("i.review_status IN ('approved','rejected','archived')", source)
        self.assertIn("intervention_required", source)
        self.assertIn("'chatbot_reply','manager_camera_snapshot','inbound_routing'", source)
        self.assertIn("important-intake:gmail", source)

    def test_reconciliation_failure_does_not_hide_stored_alerts(self):
        source = (ROOT / "app/domains/alerts_intake_routes.py").read_text()
        endpoint = source[source.index('def list_alerts'):source.index('@router.patch("/api/v1/alerts/{alert_id}"')]
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
