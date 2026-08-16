from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkerPortalTests(unittest.TestCase):
    def test_bilingual_worker_portal_and_actions_are_present(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="view-worker"', html)
        self.assertIn('Clock in · Entrata', html)
        self.assertIn('Clock out & submit · Uscita e invia', html)
        self.assertIn('Photos / Foto', html)
        self.assertIn('Expense / Spesa', html)
        self.assertIn("submitWorkerClockIn", javascript)
        self.assertIn("submitWorkerClockOut", javascript)
        self.assertIn("Time edited · Orario modificato", javascript)

    def test_worker_records_are_owned_reviewed_and_locked(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        migration = (ROOT / "db" / "migrations" / "029_worker_portal.sql").read_text(encoding="utf-8")
        self.assertIn('/api/v1/worker-portal/clock-in', source)
        self.assertIn('/api/v1/worker-portal/clock-out', source)
        self.assertIn('worker_username=%s', source)
        self.assertIn('Approved records are locked', source)
        self.assertIn('/api/v1/admin/worker-labor/{record_id}/review', source)
        self.assertIn('/api/v1/admin/worker-labor/{record_id}/pay', source)
        self.assertIn('payment_status=\'paid\'', source)
        self.assertIn('payment_status=IF(%s=\'approved\',\'unpaid\'', source)
        self.assertIn('audit(cursor, "worker_time_edit"', source)
        self.assertIn("approval_status ENUM('draft','submitted','approved','rejected')", migration)
        self.assertIn('time_adjusted_by_worker', migration)

    def test_presence_is_supporting_evidence_with_confidence(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('confidence_percent', source)
        self.assertIn('GPS/person presence', source)
        self.assertIn('camera recognition', source)
        self.assertIn('supporting evidence only', source)
        self.assertIn('evidence confidence', javascript)

    def test_existing_home_assistant_accounts_are_configurable(self) -> None:
        config = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
        addon = (ROOT / "config.yaml").read_text(encoding="utf-8")
        self.assertIn('mattia:Mattia', config)
        self.assertIn('carmela:Carmella', config)
        self.assertIn('giancarlo:Giancarlo Pefumi', config)
        self.assertIn('luca:Luca Schiliro Cognato', config)
        self.assertIn('worker_usernames', addon)
        self.assertIn('admin_usernames: "rahamin,creque"', addon)

    def test_admin_and_operations_navigation_preserves_payroll_access(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data-nav-mode="operations"', html)
        self.assertIn('data-nav-mode="admin"', html)
        self.assertIn('Payroll & labor', html)
        self.assertIn('System control', html)
        self.assertIn('Mark paid', javascript)
        self.assertIn('Approved · queued for payment', javascript)


if __name__ == "__main__":
    unittest.main()
