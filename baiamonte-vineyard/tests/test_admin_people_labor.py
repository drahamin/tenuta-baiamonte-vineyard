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
        self.assertIn("Approve ${esc(worker||'employee')} only", javascript)
        self.assertIn("Check presence", javascript)
        self.assertIn("openLaborCorrection", javascript)
        self.assertIn("Vineyard Operations profile", javascript)
        self.assertIn("Track for hourly labor", javascript)


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
        self.assertIn('home_assistant_people()', source)
        self.assertIn('/api/v1/admin/people/{person_entity:path}/profile', source)
        self.assertIn('"reporter": item.get("sender_name")', source)
        self.assertNotIn("CURDATE()-INTERVAL 62 DAY", source)
        self.assertIn("ORDER BY work_date DESC,id DESC LIMIT 1000", source)

    def test_year_round_and_seasonal_labor_are_classified(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('"pay_model": "year_round_hourly"', source)
        self.assertGreaterEqual(source.count('"pay_model": "seasonal_hourly"'), 5)
        for name in ("Carmela Pafumi", "Mattia", "Nunzio", "Unidentified part-time worker 1", "Unidentified part-time worker 2"):
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
        self.assertIn("overflow-x:hidden", css)
        self.assertIn("person-access-card", css)

    def test_person_access_levels_do_not_expand_finance(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('profile_access_level(username)', source)
        self.assertIn('level in {"admin", "operations"}', source)
        self.assertIn('"finance": normalized in finance_usernames(settings)', source)
        self.assertNotIn('level == "admin" or normalized in finance_usernames', source)

    def test_home_assistant_people_and_timesheet_workers_stay_linked(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('attributes.get("friendly_name")', source)
        self.assertIn('spec["ha_person_synced"] = bool(ha_person)', source)
        self.assertIn("_match_home_assistant_person", source)
        self.assertIn('"ha_user_id": ha_attributes.get("user_id")', source)
        self.assertIn('attributes.get("friendly_name") or profile.get("name")', source)
        self.assertIn('"name": "Carmela Pafumi"', source)
        self.assertIn('timesheetWorkerOptions', javascript)
        self.assertIn('name="timesheet_worker"', javascript)
        self.assertIn('data-timesheet-worker-label', javascript)
