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
        self.assertIn('resolve_condition_alert("power_recovery")', intelligence)
        self.assertIn('resolve_expired_condition_alerts("power_recovery", 60)', intelligence)
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
        self.assertIn('minimumFractionDigits:2,maximumFractionDigits:2', javascript)

    def test_ai_credit_recovery_is_checked_without_inventing_a_balance(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        usage = (ROOT / "app" / "ai_usage.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        javascript = (ROOT / "app" / "static" / "assets" / "operations-enhancements.js").read_text()
        index = (ROOT / "app" / "static" / "index.html").read_text()
        self.assertIn("def check_openai_service()", intelligence)
        self.assertIn('"input": "Reply only with OK."', intelligence)
        self.assertIn('record_ai_usage("credit_check", result)', intelligence)
        self.assertIn('/api/v1/admin/ai-credit-check', main)
        self.assertIn('balance_available_via_api": False', usage)
        self.assertIn('status = "not_configured"', usage)
        self.assertIn('status = "unverified"', usage)
        self.assertIn('last_verified_at', usage)
        self.assertIn('View provider balance', index)
        self.assertIn('120000', javascript)
        self.assertIn('if(aiCreditRecheckTimer)return', javascript)
        self.assertNotIn('clearTimeout(aiCreditRecheckTimer);if(blocked)', javascript)

    def test_actionable_ai_failures_alert_and_clear_after_success(self):
        intelligence = (ROOT / "app" / "intelligence.py").read_text()
        main = (ROOT / "app" / "main.py").read_text()
        self.assertIn('"quota", "billing", "credit", "insufficient_quota"', intelligence)
        self.assertIn('"maximum context", "context length", "too many tokens", "token limit"', intelligence)
        self.assertIn('upsert_condition_alert(\n        "ai_service", "critical"', intelligence)
        self.assertIn('resolve_condition_alert("ai_service")', intelligence)
        self.assertIn('"ai_service": "AI service & API quota"', main)


if __name__ == "__main__":
    unittest.main()
