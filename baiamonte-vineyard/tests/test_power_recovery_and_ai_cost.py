import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PowerRecoveryAndAiCostTests(unittest.TestCase):
    def test_power_recovery_is_deduplicated_and_planned_restarts_are_ignored(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn('POWER_RECOVERY_GAP_SECONDS = 180', intelligence)
        self.assertIn('"graceful_stop": True', intelligence)
        self.assertIn('"graceful_stop": False', intelligence)
        self.assertIn('"power-recovery:" + last_seen', intelligence)
        self.assertIn('create_alert_once(\n            "power_recovery"', intelligence)
        self.assertIn('mark_power_monitor_stopped()', main)
        self.assertIn('power_continuity_heartbeat()', main)

    def test_power_recovery_defaults_to_email_and_manager_whatsapp(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn('power_recovery = alert_type == "power_recovery"', intelligence)
        self.assertIn('settings.gmail_address if power_recovery', intelligence)
        self.assertIn('contact.get("assistant") or "").casefold() == "manager"', intelligence)
        self.assertIn('"power_recovery": "Power restored"', main)

    def test_ai_cost_control_includes_today_and_compact_efficiency_detail(self):
        usage = (ROOT / "app" / "ai_usage.py").read_text()
        javascript = (ROOT / "app" / "static" / "app.js").read_text()
        css = (ROOT / "app" / "static" / "app.css").read_text()
        self.assertIn('"today": today', usage)
        self.assertIn('DATE_ADD(CURDATE(),INTERVAL 1 DAY)', usage)
        self.assertIn('<span>Today</span>', javascript)
        self.assertIn('<span>Efficiency</span>', javascript)
        self.assertIn('repeat(4,minmax(0,1fr))', css)


if __name__ == "__main__":
    unittest.main()
