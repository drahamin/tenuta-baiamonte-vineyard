import unittest
from pathlib import Path

from app.main import app

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
        main_routes = [route for route in app.routes if getattr(getattr(route, "endpoint", None), "__module__", "") == "app.main"]
        self.assertLessEqual(len(main_routes), 68)

    def test_access_and_finance_logic_live_outside_the_route_module(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        access = (ROOT / "app/access.py").read_text(encoding="utf-8")
        finance = (ROOT / "app/domains/finance.py").read_text(encoding="utf-8")
        self.assertIn("def authorize_admin", access)
        self.assertIn("def worker_accounts", access)
        self.assertNotIn("def authorize_admin", main)
        self.assertNotIn("def worker_accounts", main)
        self.assertIn("def dashboard_payload", finance)
        self.assertIn("return _finance_dashboard_payload(year, lambda selected_year: _payroll_summary", main)

    def test_payroll_month_editors_avoid_native_month_inputs(self):
        source = frontend_source(ROOT)
        self.assertNotIn('type="month"', source)
        self.assertIn("monthlyLaborPeriodFields", source)
        self.assertIn("timesheetMonthFields", source)

    def test_composition_root_uses_focused_operational_routers(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        modules = {
            "worker_portal_router": "app/domains/worker_portal_routes.py",
            "payroll_admin_router": "app/domains/payroll_admin_routes.py",
            "cellar_router": "app/domains/cellar_routes.py",
            "dashboard_router": "app/domains/dashboard_routes.py",
            "alerts_intake_router": "app/domains/alerts_intake_routes.py",
            "public_router": "app/domains/public_routes.py",
            "intelligence_router": "app/domains/intelligence_routes.py",
        }
        for router_name, path in modules.items():
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn(f"app.include_router({router_name})", main)
            self.assertNotIn("from app.main", source)
            self.assertNotIn("from ..main", source)

    def test_domain_services_do_not_raise_http_transport_errors(self):
        presence = (ROOT / "app/domains/payroll_presence.py").read_text(encoding="utf-8")
        payroll = (ROOT / "app/domains/payroll.py").read_text(encoding="utf-8")
        self.assertNotIn("from fastapi", presence)
        self.assertNotIn("HTTPException", presence)
        self.assertNotIn("from fastapi", payroll)
        self.assertNotIn("HTTPException", payroll)

    def test_repaired_routes_delegate_storage_and_worker_review(self):
        worker_routes = (ROOT / "app/domains/worker_portal_routes.py").read_text(encoding="utf-8")
        alert_routes = (ROOT / "app/domains/alerts_intake_routes.py").read_text(encoding="utf-8")
        payroll_routes = (ROOT / "app/domains/payroll_admin_routes.py").read_text(encoding="utf-8")
        self.assertIn("store_attachment(", worker_routes)
        self.assertIn("store_attachment(", alert_routes)
        self.assertNotIn(".write_bytes(", worker_routes)
        self.assertNotIn(".write_bytes(", alert_routes)
        self.assertIn("review_worker_labor_record(", payroll_routes)
        self.assertNotIn("UPDATE labor_entries SET approval_status=%s", payroll_routes)

    def test_extracted_module_headers_end_before_runtime_code(self):
        for source in FRONTEND_SOURCES[1:]:
            text = (ROOT / source).read_text(encoding="utf-8")
            self.assertFalse(text.startswith("//") and "\\nfunction " in text.splitlines()[0], source)


if __name__ == "__main__":
    unittest.main()
