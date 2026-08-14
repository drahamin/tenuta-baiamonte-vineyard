from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AdminPeopleLaborTests(unittest.TestCase):
    def test_admin_people_and_labor_surfaces_are_present(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="adminPeopleDirectory"', html)
        self.assertIn('id="personDialog"', html)
        self.assertIn('data-admin-labor-log', html)
        self.assertIn('data-admin-view="inbox"', html)
        self.assertIn("people_directory", javascript)
        self.assertIn("openAdminPerson", javascript)
        self.assertIn("openAdminLaborLog", javascript)
        self.assertIn("All daily history", javascript)


    def test_admin_backend_returns_full_named_labor_history(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"people_directory": people_directory', source)
        self.assertIn('"years": years', source)
        self.assertIn('"entries": entries', source)
        self.assertNotIn("CURDATE()-INTERVAL 62 DAY", source)
        self.assertIn("ORDER BY work_date DESC,id DESC LIMIT 1000", source)
