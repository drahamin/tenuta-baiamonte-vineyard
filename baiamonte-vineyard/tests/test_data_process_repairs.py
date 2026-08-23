import unittest
from pathlib import Path
from tests.source_helpers import backend_source


ROOT = Path(__file__).resolve().parents[1]


class DataProcessRepairTests(unittest.TestCase):
    def test_forecasting_imports_reconciliation_helper(self):
        source = (ROOT / "app" / "domains" / "dashboard_routes.py").read_text()
        self.assertIn("reconciled_vintage_values", source)

    def test_completed_treatment_closes_matching_work_task(self):
        source = backend_source(ROOT)
        migration = (ROOT / "db" / "migrations" / "050_repair_data_work_processes.sql").read_text()
        self.assertIn("reconcile_completed_treatment", source)
        self.assertIn("completed_task_ids", source)
        self.assertIn("publish_task_to_google(task_id)", source)
        self.assertIn("UPDATE tasks t", migration)
        self.assertIn("s.status IN ('completed','applied')", migration)

    def test_treatment_action_history_collapses_duplicate_audit_events(self):
        source = (ROOT / "app" / "domains" / "treatment_routes.py").read_text()
        self.assertIn("seen_record_actions", source)
        self.assertIn("action_key in seen_record_actions", source)

    def test_future_reimbursements_are_rejected(self):
        source = backend_source(ROOT)
        self.assertIn("A reimbursable expense cannot be dated in the future", source)

    def test_unreviewed_labs_are_excluded_from_harvest_model_inputs(self):
        source = (ROOT / "app" / "intelligence.py").read_text()
        self.assertGreaterEqual(source.count("s.sample_type='grape' AND s.needs_review=0"), 3)


if __name__ == "__main__":
    unittest.main()
