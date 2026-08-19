import unittest
from pathlib import Path

from tests.source_helpers import BACKEND_SOURCES, FRONTEND_SOURCES, frontend_source


ROOT = Path(__file__).resolve().parents[1]


class ModuleBoundaryTests(unittest.TestCase):
    def test_frontend_modules_are_loaded_and_core_stays_below_budget(self):
        html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        for source in FRONTEND_SOURCES[1:]:
            browser_path = source.removeprefix("app/static/")
            self.assertIn(browser_path, html)
        self.assertLess((ROOT / FRONTEND_SOURCES[0]).stat().st_size, 300_000)

    def test_backend_domain_modules_exist_and_main_stays_below_budget(self):
        for source in BACKEND_SOURCES[1:]:
            self.assertTrue((ROOT / source).is_file(), source)
        self.assertLess((ROOT / BACKEND_SOURCES[0]).stat().st_size, 400_000)

    def test_access_and_finance_logic_live_outside_the_route_module(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        access = (ROOT / "app/access.py").read_text(encoding="utf-8")
        finance = (ROOT / "app/domains/finance.py").read_text(encoding="utf-8")
        self.assertIn("def authorize_admin", access)
        self.assertIn("def worker_accounts", access)
        self.assertNotIn("def authorize_admin", main)
        self.assertNotIn("def worker_accounts", main)
        self.assertIn("def dashboard_payload", finance)
        self.assertIn("return _finance_dashboard_payload(year, payroll_summary)", main)

    def test_payroll_month_editors_avoid_native_month_inputs(self):
        source = frontend_source(ROOT)
        self.assertNotIn('type="month"', source)
        self.assertIn("monthlyLaborPeriodFields", source)
        self.assertIn("timesheetMonthFields", source)

    def test_extracted_module_headers_end_before_runtime_code(self):
        for source in FRONTEND_SOURCES[1:]:
            text = (ROOT / source).read_text(encoding="utf-8")
            self.assertFalse(text.startswith("//") and "\\nfunction " in text.splitlines()[0], source)


if __name__ == "__main__":
    unittest.main()
