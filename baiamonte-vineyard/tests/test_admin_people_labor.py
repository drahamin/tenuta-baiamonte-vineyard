from pathlib import Path
import unittest

from app.domains.payroll import consolidate_labor_people
from tests.source_helpers import backend_source, frontend_source


ROOT = Path(__file__).resolve().parents[1]


class AdminPeopleLaborTests(unittest.TestCase):
    def test_giancarlo_and_carmela_do_not_share_surname_identity_matching(self):
        source = backend_source(ROOT)
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        self.assertIn('"name_aliases": ("giancarlo", "giancarlo pafumi")', source)
        self.assertIn('"name_aliases": ("carmela", "carmella", "carmela pafumi")', source)
        self.assertNotIn('("giancarlo", "pafumi", "pefumi")', source)
        self.assertNotIn('("giancarlo", "pafumi", "pefumi")', intelligence)
        self.assertIn("LOWER(TRIM(person_or_crew)) = %s", source)
        self.assertNotIn("LOWER(person_or_crew) LIKE %s", source)

    def test_labor_endpoint_supports_fixed_jobs_and_expenses(self):
        quick_entry = (ROOT / "app" / "quick_entry.py").read_text(encoding="utf-8")
        self.assertIn('"expense_amount_eur"', quick_entry)
        self.assertIn('"expense_category"', quick_entry)
        self.assertIn('"expense_notes"', quick_entry)
        self.assertIn('"manual_job"', quick_entry)
        self.assertIn('"water_delivery"', quick_entry)
        self.assertIn('"contractor_job"', quick_entry)

    def test_invalid_labor_record_can_be_converted_to_one_multi_job_invoice(self):
        source = (ROOT / "app" / "domains" / "payroll.py").read_text(encoding="utf-8")
        route_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn('lines = payload.get("job_lines")', source)
        self.assertIn('"kind": "contractor_job_lines"', source)
        self.assertIn('"work_category": "one_off_charge"', source)
        self.assertIn("_normalize_contractor_job_lines(payload)", route_source)
        self.assertIn("Jobs billed in this record", javascript)
        self.assertIn("data-add-job-line", javascript)
        self.assertIn("laborJobLines", javascript)
        self.assertIn(".labor-job-line", css)

    def test_admin_correction_updates_exact_record_and_explicitly_releases_verification(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn("SELECT id record_id,work_date", source)
        self.assertIn('String(row.id)===String(day.record_id)', javascript)
        self.assertIn("Date needs correction", javascript)
        self.assertIn('resolve_verification = payload.get("resolve_verification") is True', source)
        self.assertIn('values["payment_status"] = "unpaid"', source)
        self.assertIn('"resolve_verification" if resolve_verification else "correct"', source)
        self.assertIn('name="resolve_verification"', javascript)

    def test_admin_can_delete_one_labor_record_with_audit_history(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn('@app.delete("/api/v1/admin/labor/{record_id}"', source)
        self.assertIn('audit(cursor, "delete", "labor", record_id', source)
        self.assertIn('DELETE FROM labor_entries WHERE id=%s AND estate_id=%s', source)
        self.assertIn("data-delete-labor", javascript)
        self.assertIn("Its prior contents remain in the administrator audit log", javascript)
        self.assertIn(".labor-correction-actions", css)

    def test_labor_correction_dialog_fits_and_scrolls_on_tablets(self):
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("#recordDialog:has(.labor-correction-form)", css)
        self.assertIn("grid-template-rows:auto minmax(0,1fr) auto", css)
        self.assertIn("#recordDialogList{min-width:0;min-height:0;overflow:auto", css)
        self.assertIn(".labor-correction-actions{position:sticky", css)

    def test_approved_worker_cards_use_a_compact_responsive_grid(self):
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("#adminLaborPeople.labor-reconciliation", css)
        self.assertIn("repeat(auto-fit,minmax(min(100%,300px),1fr))", css)
        self.assertIn(".labor-person-card .labor-days{max-height:260px;overflow:auto", css)

    def test_admin_people_and_labor_surfaces_are_present(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
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
        self.assertIn("openMonthlyLaborEntry", javascript)
        monthly_handler = javascript.split("function openMonthlyLaborEntry", 1)[1].split("\n", 1)[0]
        self.assertIn("monthly-labor-inline", monthly_handler)
        self.assertIn("data-month-choice", monthly_handler)
        self.assertNotIn("document.body.appendChild", monthly_handler)
        self.assertNotIn("monthly-labor-sheet-open", monthly_handler)
        self.assertNotIn("showModal", monthly_handler)
        self.assertIn("openLaborHistories", javascript)
        self.assertIn("baiamonte-timesheet-drafts", javascript)
        self.assertIn("hasTimesheetDrafts()", javascript)
        self.assertIn("Vineyard Operations profile", javascript)
        self.assertIn("Track for hourly labor", javascript)


    def test_admin_backend_returns_full_named_labor_history(self) -> None:
        source = backend_source(ROOT)
        self.assertIn('"people_directory": people_directory', source)
        self.assertIn('"years": years', source)
        self.assertIn('"entries": entries', source)
        self.assertIn('"labor_history": all_labor_entries', source)
        self.assertIn('"unassigned_labor": unassigned_labor', source)
        self.assertIn('"timesheet_reviews": timesheet_reviews', source)
        self.assertIn('/api/v1/admin/timesheets/{record_id}/approve', source)
        self.assertIn('/api/v1/admin/timesheets/{record_id}/presence', source)
        self.assertIn('/api/v1/admin/labor/{record_id}', source)
        self.assertIn('/api/v1/admin/labor/monthly', source)
        self.assertIn('Monthly total {month_text}', source)
        self.assertIn('"presence_evidence": presence', source)
        self.assertIn('person.giancarlo', source)
        self.assertIn('device_tracker.luca_iphone', source)
        self.assertIn('home_assistant_people()', source)
        self.assertIn('/api/v1/admin/people/{person_entity:path}/profile', source)
        self.assertIn('"reporter": item.get("sender_name")', source)
        self.assertNotIn("CURDATE()-INTERVAL 62 DAY", source)
        self.assertIn("ORDER BY work_date DESC,id DESC LIMIT 1000", source)

    def test_year_round_and_seasonal_labor_are_classified(self) -> None:
        source = backend_source(ROOT)
        javascript = frontend_source(ROOT)
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('"pay_model": "year_round_hourly"', source)
        self.assertGreaterEqual(source.count('"pay_model": "seasonal_hourly"'), 5)
        for name in ("Carmela Pafumi", "Mattia", "Nunzio", "Unidentified part-time worker 1", "Unidentified part-time worker 2"):
            self.assertIn(f'"name": "{name}"', source)
        self.assertIn("YEAR-ROUND HOURLY", javascript)
        self.assertIn("SEASONAL HOURLY", javascript)
        self.assertIn("Time & timesheet control", html)

    def test_person_detail_dialog_is_responsive_and_compact(self) -> None:
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("person-summary-grid", javascript)
        self.assertIn("person-technical-details", javascript)
        self.assertIn("#personDialog{width:min(760px,calc(100vw - 24px))", css)
        self.assertIn("max-height:90vh;overflow:auto", css)
        self.assertIn("position:sticky", css)
        self.assertIn("overflow-x:hidden", css)
        self.assertIn("person-access-card", css)

    def test_people_refresh_is_visible_strict_and_preserves_existing_data(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn('data-admin-refresh="people"', html)
        self.assertIn("async function refreshAdminControl", javascript)
        self.assertIn("const previous=state.adminControl", javascript)
        self.assertIn("state.adminControl=previous", javascript)
        self.assertIn("Home Assistant ${count===1?'person':'people'} refreshed", javascript)
        self.assertIn("Refresh failed:", javascript)
        self.assertIn("#view-admin-people,#view-admin-labor{width:100%", css)
        self.assertIn("@media(max-width:480px){.people-directory{grid-template-columns:1fr}", css)

    def test_person_access_levels_do_not_expand_finance(self) -> None:
        source = backend_source(ROOT)
        self.assertIn('profile_access_level(username)', source)
        self.assertIn('level in {"admin", "operations"}', source)
        self.assertIn('"finance": normalized in finance_usernames(settings)', source)
        self.assertNotIn('level == "admin" or normalized in finance_usernames', source)

    def test_home_assistant_people_and_timesheet_workers_stay_linked(self) -> None:
        source = backend_source(ROOT)
        javascript = frontend_source(ROOT)
        self.assertIn('attributes.get("friendly_name")', source)
        self.assertIn('spec["ha_person_synced"] = bool(ha_person)', source)
        self.assertIn("_match_home_assistant_person", source)
        self.assertIn('"ha_user_id": ha_attributes.get("user_id")', source)
        self.assertIn('attributes.get("friendly_name") or profile.get("name")', source)
        self.assertIn('"name": "Carmela Pafumi"', source)
        self.assertIn('timesheetWorkerOptions', javascript)
        self.assertIn('name="timesheet_worker"', javascript)
        self.assertIn('data-timesheet-worker-label', javascript)

    def test_home_assistant_full_name_replaces_seeded_short_worker_once(self) -> None:
        source = backend_source(ROOT)
        self.assertIn("def consolidate_labor_people", source)
        self.assertIn('raw_key.startswith(f"{normalized_key}_")', source)
        self.assertIn('existing["name"] = person.get("name")', source)
        self.assertIn("canonical_labor_keys", source)

    def test_payroll_identity_merge_keeps_ha_full_names_and_history_aliases(self) -> None:
        people = [
            {
                "key": "luca", "name": "Luca Schiliro Cognato",
                "name_aliases": ("luca", "schiliro", "cognato"),
                "pay_model": "year_round_hourly",
            },
            {
                "key": "nunzio", "name": "Nunzio",
                "name_aliases": ("nunzio",), "pay_model": "seasonal_hourly",
            },
            {
                "key": "nunzio_testa", "name": "Nunzio Testa",
                "person_entity": "person.nunzio_testa", "ha_person_synced": True,
                "name_aliases": ("nunzio testa", "nunzio", "testa"),
            },
        ]
        merged = consolidate_labor_people(people, {"luca", "nunzio"})
        self.assertEqual([person["key"] for person in merged], ["luca", "nunzio"])
        luca = merged[0]
        nunzio = merged[1]
        self.assertIn("luca schiliro cognato", luca["name_aliases"])
        self.assertEqual(nunzio["name"], "Nunzio Testa")
        self.assertEqual(nunzio["person_entity"], "person.nunzio_testa")
        self.assertTrue(nunzio["ha_person_synced"])
        self.assertIn("nunzio", nunzio["name_aliases"])
        self.assertIn("nunzio testa", nunzio["name_aliases"])

    def test_unidentified_workers_can_be_assigned_without_losing_history(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn('/api/v1/admin/labor/reassign-worker', source)
        self.assertIn('Unidentified part-time worker', source)
        self.assertIn('Identify worker', javascript)
        self.assertIn('records assigned to', javascript)
        self.assertIn('data-labor-person="${esc(person.key)}"', javascript)
        self.assertIn('people.find(item=>String(item.key)===String(card.dataset.laborPerson))', javascript)
        self.assertIn('person.identified!==false', javascript)
        self.assertNotIn('const person=people[index]', javascript)

    def test_timesheet_reimbursements_remain_separate_and_enter_payment_queue(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("def _normalize_timesheet_expenses", source)
        self.assertIn('"reimbursable_expenses": expenses', source)
        self.assertIn("'reimbursable_expense'", source)
        self.assertIn("'approved','unpaid'", source)
        self.assertIn("worker_accounts(settings)", source)
        self.assertIn("data-add-expense", javascript)
        self.assertIn("data-expense-row", javascript)
        self.assertIn("expenses_inserted", javascript)
        self.assertIn(".timesheet-reimbursements", css)
        self.assertIn(".expense-row", css)

    def test_timesheets_support_month_totals_and_an_audited_pay_step(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn('name="timesheet_period"', javascript)
        self.assertIn('Month total', javascript)
        self.assertIn('data-timesheet-grand-total', javascript)
        self.assertIn('Total payable:', javascript)
        self.assertIn('name="month_number"', javascript)
        self.assertIn('name="month_year"', javascript)
        self.assertNotIn('type="month"', javascript)
        self.assertIn('name="timesheet_month_part"', javascript)
        self.assertIn('name="timesheet_year_part"', javascript)
        self.assertIn('Mark paid', javascript)
        self.assertIn('data-worker-pay', javascript)
        self.assertIn("work_category = \"monthly_total\"", source)
        self.assertIn("payment_status IN ('unpaid','unknown','part_paid')", source)
        self.assertIn("worker_payment_holds", source)
        self.assertIn("Verification holds", javascript)
        self.assertIn(".timesheet-grand-total", css)

    def test_inbound_timesheets_remain_one_payment_block(self) -> None:
        source = backend_source(ROOT)
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("def worker_payment_batch_key", source)
        self.assertIn('/api/v1/admin/labor-payment-batches/pay', source)
        self.assertIn('mark_paid_batch', source)
        self.assertIn('groupWorkerPaymentQueue', javascript)
        self.assertIn('Mark block paid', javascript)
        self.assertIn('Included records', javascript)
        self.assertIn('data-worker-payment-ids', javascript)
        self.assertIn('.worker-payment-batch', css)

    def test_system_documentation_reports_exact_social_and_mac_requirements(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"name": "Mac / Codex intake"', source)
        self.assertIn("_configured(settings.api_key) or _configured(settings.mcp_server_token)", source)
        self.assertIn('"name": "Facebook"', source)
        self.assertIn("meta_page_access_token or settings.whatsapp_access_token", source)
        self.assertIn("facebook_page_id", source)
        self.assertIn('"name": "Instagram"', source)
        self.assertIn("instagram_business_account_id", source)

    def test_labor_invoices_accept_multiple_audited_payments(self) -> None:
        source = backend_source(ROOT)
        javascript = frontend_source(ROOT)
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        migration = (ROOT / "db" / "migrations" / "040_labor_invoice_payments.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS labor_invoice_payments", migration)
        self.assertIn("'part_paid'", migration)
        self.assertIn('payment_type ENUM(\'deposit\',\'payment\')', migration)
        self.assertIn('audit(cursor, "record_payment"', source)
        self.assertIn('"part_paid"', source)
        self.assertIn("workerPaymentControls", javascript)
        self.assertIn("Add payment or deposit", javascript)
        self.assertIn("Payment history", javascript)
        self.assertIn("balance_due_eur", javascript)
        self.assertIn(".worker-payment-progress", css)

    def test_paid_invoices_have_a_durable_ledger_and_cannot_reappear(self) -> None:
        source = backend_source(ROOT)
        payroll = (ROOT / "app" / "domains" / "payroll.py").read_text(encoding="utf-8")
        migration = (ROOT / "db" / "migrations" / "047_backfill_paid_labor_ledger.sql").read_text(encoding="utf-8")
        self.assertIn("MIGRATED-PAID-STATUS", migration)
        self.assertIn("paid.amount_paid>=ROUND", migration)
        self.assertIn("INSERT INTO labor_invoice_payments", source)
        self.assertIn("The complete approved payment block was not persisted", source)
        self.assertIn('"payment_integrity": payment_integrity', source)
        self.assertIn("The invoice payment status was not persisted", payroll)
        self.assertIn("reconcile_paid", payroll)

    def test_approved_worker_cards_sort_by_year_hours_descending(self) -> None:
        javascript = frontend_source(ROOT)
        self.assertIn("Number(b.totals?.year_hours||0)-Number(a.totals?.year_hours||0)", javascript)

    def test_payment_form_is_not_replaced_while_being_edited(self) -> None:
        javascript = frontend_source(ROOT)
        self.assertIn("function hasActiveWorkerPaymentEntry()", javascript)
        self.assertIn("form.contains(document.activeElement)", javascript)
        self.assertIn("!hasActiveWorkerPaymentEntry()", javascript)
