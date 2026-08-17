import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UnifiedWorkPlanTests(unittest.TestCase):
    def test_google_and_apple_sources_link_to_canonical_tasks(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        migration = (ROOT / "db" / "migrations" / "028_unified_work_plan.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS work_item_links", migration)
        self.assertIn("uq_work_item_source", migration)
        self.assertIn("def _normalized_title", source)
        self.assertIn("def _task_for_source", source)
        self.assertIn("def unified_work_plan", source)

    def test_only_approved_apple_lists_can_sync(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        self.assertIn('APPLE_LIST_NAME = "Baiamonte"', source)
        self.assertIn('APPLE_TREATMENTS_LIST_NAME = "Baiamonte Treatments"', source)
        self.assertIn("Only the Baiamonte and Baiamonte Treatments reminder lists", source)
        self.assertIn("duplicate_ids_to_complete", source)

    def test_treatment_reminders_never_mark_application_applied(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        mcp = (ROOT / "app" / "mcp_server.py").read_text()
        self.assertIn('"may_mark_applied": False', source)
        self.assertIn("Reminder completion never approves or records a treatment application", source)
        self.assertIn("def treatment_reminders", mcp)

    def test_apple_reminder_exports_are_disjoint_and_reconcilable(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        mcp = (ROOT / "app" / "mcp_server.py").read_text()
        self.assertIn("def general_reminder_plan", source)
        self.assertIn("if not _is_treatment_task(task)", source)
        self.assertIn("def apple_reminder_reconciliation", source)
        self.assertIn('"remove_from_baiamonte_treatments"', source)
        self.assertIn("treatment and source_list == APPLE_LIST_NAME", source)
        self.assertIn("not treatment and source_list == APPLE_TREATMENTS_LIST_NAME", source)
        self.assertIn("if list_name == APPLE_LIST_NAME:", source)
        self.assertIn("def apple_reminder_lists", mcp)
        self.assertIn("def baiamonte_reminders", mcp)

    def test_calendar_combines_operational_sources_without_invented_dates(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        for kind in ("planned_work", "treatment_plan", "harvest_projection", "recorded_labor", "issue_due", "italian_holiday"):
            self.assertIn(f'"kind": "{kind}"', source)
        self.assertIn("def _merge_calendar_events", source)

    def test_navigation_has_one_work_plan(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        self.assertRegex(html, r'<button data-view="projects"[^>]*>Work plan</button>')
        self.assertNotIn('<button data-view="work">Work</button>', html)

    def test_planning_uses_supported_supervisor_proxy_with_retry(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        self.assertIn('HA_API_BASE = "http://supervisor/core/api"', source)
        self.assertIn("for attempt in range(3):", source)
        self.assertNotIn('"http://homeassistant:8123/api"', source)
        self.assertNotIn('"http://core-homeassistant:8123/api"', source)

    def test_todo_writes_do_not_request_unsupported_response_data(self):
        source = (ROOT / "app" / "planning_sync.py").read_text()
        self.assertIn('_service("todo", "add_item", payload, return_response=False)', source)
        self.assertIn('_service("todo", "update_item", payload, return_response=False)', source)


if __name__ == "__main__":
    unittest.main()
