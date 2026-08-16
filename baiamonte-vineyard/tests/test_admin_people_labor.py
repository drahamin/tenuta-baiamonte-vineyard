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
        self.assertIn('id="adminTimesheetReviews"', html)
        self.assertIn('data-admin-view="inbox"', html)
        self.assertIn("people_directory", javascript)
        self.assertIn("openAdminPerson", javascript)
        self.assertIn("openAdminLaborLog", javascript)
        self.assertIn("Daily history", javascript)
        self.assertIn("Approve timesheet", javascript)
        self.assertIn("Check presence", javascript)
        self.assertIn("openLaborCorrection", javascript)


    def test_admin_backend_returns_full_named_labor_history(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"people_directory": people_directory', source)
        self.assertIn('"years": years', source)
        self.assertIn('"entries": entries', source)
        self.assertIn('"labor_history": all_labor_entries', source)
        self.assertIn('"unassigned_labor": unassigned_labor', source)
        self.assertIn('"timesheet_reviews": timesheet_reviews', source)
        self.assertIn('/api/v1/admin/timesheets/{record_id}/approve', source)
        self.assertIn('/api/v1/admin/timesheets/{record_id}/presence', source)
        self.assertIn('/api/v1/admin/labor/{record_id}', source)
        self.assertIn('"presence_evidence": presence', source)
        self.assertIn('person.giancarlo', source)
        self.assertIn('device_tracker.luca_iphone', source)
        self.assertNotIn("CURDATE()-INTERVAL 62 DAY", source)
        self.assertIn("ORDER BY work_date DESC,id DESC LIMIT 1000", source)

    def test_year_round_and_seasonal_labor_are_classified(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('"pay_model": "year_round_hourly"', source)
        self.assertEqual(source.count('"pay_model": "seasonal_hourly"'), 5)
        for name in ("Carmella", "Mattia", "Nunzio", "Unidentified part-time worker 1", "Unidentified part-time worker 2"):
            self.assertIn(f'"name": "{name}"', source)
        self.assertIn("YEAR-ROUND HOURLY", javascript)
        self.assertIn("SEASONAL HOURLY", javascript)
        self.assertIn("Time & timesheet control", html)

    def test_person_detail_dialog_is_responsive_and_compact(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("person-summary-grid", javascript)
        self.assertIn("person-technical-details", javascript)
        self.assertIn("#personDialog{width:min(760px,calc(100vw - 24px))", css)
        self.assertIn("max-height:90vh;overflow:auto", css)
        self.assertIn("position:sticky", css)
