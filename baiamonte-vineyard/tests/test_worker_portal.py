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
        self.assertIn('id="workerPrivateName"', html)
        self.assertIn('id="workerPrivatePending"', html)
        self.assertIn('id="workerPrivateDue"', html)
        self.assertIn('id="workerPrivatePaid"', html)
        self.assertIn('Your hours & pay · Ore e compensi', html)
        self.assertIn('Assigned to you · Assegnato a te', html)
        self.assertIn('Edit time, work, expenses and photos before approval', html)

    def test_worker_portal_is_compact_and_mobile_safe(self) -> None:
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("env(safe-area-inset-bottom)", css)
        self.assertIn("-webkit-text-size-adjust:100%", css)
        self.assertIn("font-size:16px!important", css)
        self.assertIn("touch-action:manipulation", css)

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
        self.assertNotIn('request.query_params.get("worker")', source)
        self.assertIn('l.worker_username=%s', source)
        self.assertIn('Approve one employee at a time', source)

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
        self.assertIn('carmela:Carmela Pafumi', config)
        self.assertIn('giancarlo:Giancarlo Pafumi', config)
        self.assertIn('luca:Luca Schiliro Cognato', config)
        self.assertIn('worker_usernames', addon)
        self.assertIn('dedicated_worker_usernames: "mattia,carmela,carmella"', addon)
        self.assertIn('admin_usernames: "rahamin,creque"', addon)

    def test_mattia_and_carmela_are_locked_to_the_minimal_worker_dashboard(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('{"mattia", "carmela", "carmella"}', source)
        self.assertIn('"dedicated_worker": dedicated_worker', source)
        self.assertIn('and not dedicated_worker', source)
        self.assertIn("if(worker&&hourlyWorker&&!write)", javascript)
        self.assertIn("node.hidden=!hourlyWorker", javascript)

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
