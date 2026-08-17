import unittest
from pathlib import Path

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class SmallTeamMessageFlowTests(unittest.TestCase):
    def test_whatsapp_message_failures_are_not_estate_service_failures(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        display = (ROOT / "app" / "display_data.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn("current_event.integration_name<>'whatsapp-channel'", intelligence)
        self.assertIn("current_event.integration_name<>'whatsapp-channel'", display)
        self.assertIn("current_event.integration_name<>'whatsapp-channel'", main)

    def test_routine_whatsapp_has_fast_audited_cleanup(self):
        main = (ROOT / "app" / "main.py").read_text()
        javascript = frontend_source(ROOT)
        html = (ROOT / "app" / "static" / "index.html").read_text()
        self.assertIn('/api/v1/intake/clear-routine-whatsapp', main)
        self.assertIn("No database action required", main)
        self.assertIn("clearRoutineWhatsapp", javascript)
        self.assertIn("Clear routine WhatsApp", html)

    def test_mail_actions_use_dialog_feedback_and_delegation(self):
        javascript = frontend_source(ROOT)
        html = (ROOT / "app" / "static" / "index.html").read_text()
        self.assertIn("mailActionStatus", javascript)
        self.assertIn("event.target.closest('[data-mail-action]')", javascript)
        self.assertIn('id="mailActionStatus"', html)

    def test_recurring_conditions_use_one_live_alert_each(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        for source_id in ("weather:{code}", "laboratory:review", "tasks:overdue", "cellar_checks:overdue"):
            self.assertIn(source_id, intelligence)
        self.assertIn("error_acknowledgements acknowledged", intelligence)

    def test_home_assistant_notification_follows_alert_lifecycle(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn('"notification_id": _ha_alert_notification_id(alert_type, source_id)', intelligence)
        self.assertIn('"/services/persistent_notification/dismiss"', intelligence)
        self.assertIn('resolve_condition_alert("system", "system:integration-failures")', main)


if __name__ == "__main__":
    unittest.main()
