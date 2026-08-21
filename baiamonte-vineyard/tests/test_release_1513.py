import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Release1513Tests(unittest.TestCase):
    def test_total_open_balances_are_prominent_and_use_selected_year(self):
        backend = (ROOT / "app/domains/finance.py").read_text()
        html = (ROOT / "app/static/index.html").read_text()
        js = (ROOT / "app/static/app.js").read_text()
        self.assertIn('"total_open_balances": total_open_balances', backend)
        self.assertIn('"AND YEAR(document_date)=%s "', backend)
        self.assertIn("Total receivable", html)
        self.assertIn("Total payable", html)
        self.assertIn("finance-balance-strip", html)
        self.assertIn("f.total_open_balances", js)

    def test_authoritative_lab_manifest_has_all_reports_and_samples(self):
        source = (ROOT / "app/lab_authoritative_manifest.py").read_text()
        namespace = {}
        exec(compile(source, "lab_authoritative_manifest.py", "exec"), namespace)
        reports = namespace["AUTHORITATIVE_LAB_REPORTS"]
        self.assertEqual(len(reports), 26)
        self.assertEqual(sum(len(report[3]) for report in reports), 58)
        self.assertIn(("2025-04-24", 2023, "wine"), [(row[0], row[1], row[2]) for row in reports])

    def test_lab_review_splits_samples_and_preserves_annata(self):
        review = (ROOT / "app/static/assets/intake-review.js").read_text()
        intelligence = (ROOT / "app/intelligence.py").read_text()
        self.assertIn("normalizedIntakeSuggestions", review)
        self.assertIn("intakeLabVintage", review)
        self.assertIn("Annata means the wine vintage", intelligence)

    def test_admin_and_inventory_fallbacks_are_present(self):
        bootstrap = (ROOT / "app/static/bootstrap.js").read_text()
        treatments = (ROOT / "app/domains/treatment_routes.py").read_text()
        self.assertIn("loadAdminControl", bootstrap)
        self.assertIn("/api/v1/treatments/inventory-issue", treatments)
        self.assertIn("not_needed_this_season", treatments)

    def test_patch_release_keeps_core_module_under_limit(self):
        self.assertLess((ROOT / "app/main.py").stat().st_size, 400_000)

    def test_winemaking_invoice_is_matched_to_vintage_provider(self):
        bottling = (ROOT / "app/domains/bottling.py").read_text()
        finance = (ROOT / "app/domains/finance.py").read_text()
        interface = (ROOT / "app/static/assets/bottling.js").read_text()
        self.assertIn("source_year + 1", bottling)
        self.assertIn("provider_key", bottling)
        self.assertIn("actual_documents", bottling)
        self.assertIn("seen_documents", bottling)
        self.assertIn("len(actual_documents) == 2", bottling)
        self.assertIn('"documents": actual_documents', bottling)
        self.assertIn('bottling_plan.get("winemaking")', finance)
        self.assertIn("invoice_vintage_year", interface)
        self.assertIn("invoiceEvidence", interface)

    def test_lab_audit_ignores_non_lab_messages(self):
        source = (ROOT / "app/domains/laboratory.py").read_text()
        self.assertIn('source.get("classification") != "lab_report"', source)

    def test_admin_presence_attributes_are_initialized_per_worker(self):
        source = (ROOT / "app/main.py").read_text()
        person_item = source.index('person_item = labor_ha_states.get(person.get("person_entity", ""))')
        attributes = source.index('person_attributes = person_item.get("attributes") or {}', person_item)
        source_entity = source.index('source_entity = str(person_attributes.get("source") or "")', person_item)
        self.assertLess(attributes, source_entity)

    def test_admin_directory_does_not_assert_stale_or_zero_location(self):
        source = (ROOT / "app/main.py").read_text()
        start = source.index("people_directory = []")
        directory = source[start:source.index('return json_ready({', start)]
        self.assertIn("source_is_stale", directory)
        self.assertIn("gps_is_fresh", directory)
        self.assertIn("person_presence = None if source_is_stale", directory)
        self.assertIn("not (float(latitude) == 0 and float(longitude) == 0)", directory)

    def test_finance_exposes_net_all_in_cost_per_bottle(self):
        backend = (ROOT / "app/domains/finance.py").read_text()
        frontend = (ROOT / "app/static/assets/bottling.js").read_text()
        self.assertIn("fic_purchase_cost + labor_cost + unbilled_winemaking", backend)
        self.assertIn("profit_loss = fic_receivables - all_in_cost", backend)
        self.assertIn('"all_in_cost_per_bottle_eur"', backend)
        self.assertIn('"profit_loss_per_bottle_eur"', backend)
        self.assertIn("All-in cost / 750 ml bottle", frontend)
        self.assertIn("Profit / loss per bottle", frontend)

    def test_giancarlo_imported_hours_are_ten_euros_per_hour(self):
        migration = (ROOT / "db/migrations/101_giancarlo_imported_hourly_rate.sql").read_text()
        live_migration = (ROOT / "db/migrations/102_giancarlo_historical_monthly_rate.sql").read_text()
        source = (ROOT / "app/main.py").read_text()
        self.assertIn("hourly_rate_eur=10.00", migration)
        self.assertIn("COALESCE(regular_hours,0)+COALESCE(overtime_hours,0)>0", migration)
        self.assertIn('"giancarlo" in worker.casefold()', source)
        self.assertIn("rate = 10.0", source)
        self.assertIn("HISTORICAL-GIANCARLO-%-MONTHLY", live_migration)
        self.assertIn("hourly_rate_eur=10.00", live_migration)

    def test_tv_act_now_titles_use_two_lines(self):
        css = (ROOT / "app/static/display-extra.css").read_text()
        self.assertIn(".planning-tv-grid .planning-now .row b", css)
        self.assertIn("-webkit-line-clamp:2", css)

    def test_finance_exposes_prior_year_vat_position(self):
        backend = (ROOT / "app/domains/finance.py").read_text()
        frontend = (ROOT / "app/static/app.js").read_text()
        self.assertIn('"vat_position": vat_position', backend)
        self.assertIn('"prior_years_balance"', backend)
        self.assertIn('"combined_balance"', backend)
        self.assertIn("Prior-years VAT balance", frontend)
        self.assertIn("Combined VAT position", frontend)

    def test_worker_cards_show_ledger_paid_and_due_totals(self):
        backend = (ROOT / "app/domains/payroll.py").read_text()
        frontend = (ROOT / "app/static/app.js").read_text()
        self.assertIn("paid_this_year", backend)
        self.assertIn("year_paid_eur", backend)
        self.assertIn("year_due_eur", backend)
        self.assertIn("Paid this year", frontend)
        self.assertIn("Total due", frontend)

    def test_edit_tank_opens_the_reading_panel(self):
        frontend = (ROOT / "app/static/assets/cellar.js").read_text()
        self.assertIn("const panel=reading.closest('details')", frontend)
        self.assertIn("if(panel)panel.open=true", frontend)

    def test_tank_details_are_separate_from_readings_without_duplicates(self):
        domain = (ROOT / "app/domains/cellar.py").read_text()
        frontend = (ROOT / "app/static/assets/cellar.js").read_text()
        self.assertIn("def update_tank_details", domain)
        self.assertIn("Capacity cannot be below", domain)
        self.assertIn("Tank details", frontend)
        self.assertIn("Reading update", frontend)
        self.assertIn("reading.elements.container_id.closest('label').hidden=true", frontend)
        self.assertIn("Permanent tank notes", frontend)

    def test_fatture_balances_use_exact_external_payments(self):
        ingestion = (ROOT / "app/fattureincloud.py").read_text()
        migration = (ROOT / "db/migrations/103_finance_open_balance_status.sql").read_text()
        finance = (ROOT / "app/domains/finance.py").read_text()
        self.assertIn("def _paid_amount", ingestion)
        self.assertIn("source_paid_amount=VALUES(source_paid_amount)", ingestion)
        self.assertIn("GREATEST(d.source_paid_amount", migration)
        self.assertIn("CASE WHEN d.payment_status='paid' THEN 0", migration)
        self.assertIn("YEAR(document_date)=%s", finance)
        self.assertIn("payment_status IN ('unpaid','part_paid','unknown')", finance)
        self.assertIn('"nexi payments" in supplier_name', ingestion)

    def test_payroll_paid_backfill_and_fic_expense_chart(self):
        payroll = (ROOT / "app/domains/payroll.py").read_text()
        migration = (ROOT / "db/migrations/104_giancarlo_paid_ledger_backfill.sql").read_text()
        finance = (ROOT / "app/domains/finance.py").read_text()
        html = (ROOT / "app/static/index.html").read_text()
        javascript = (ROOT / "app/static/app.js").read_text()
        self.assertIn("GIANCARLO-PAID-THROUGH-2026-07-31", migration)
        self.assertIn("l.payment_status<>'paid'", payroll)
        self.assertIn('"fic_expenses_monthly": fic_expenses_monthly', finance)
        self.assertIn("financeFicExpenseChart", html)
        self.assertIn("Spese da Fatture in Cloud", html)
        self.assertIn("fic_expenses_monthly", javascript)

    def test_bottle_value_labor_stats_and_invoice_lists(self):
        migration = (ROOT / "db/migrations/105_bottle_stock_value.sql").read_text()
        routes = (ROOT / "app/domains/finance_inventory_routes.py").read_text()
        html = (ROOT / "app/static/index.html").read_text()
        javascript = (ROOT / "app/static/app.js").read_text()
        self.assertIn("average_sales_price=12.00", migration)
        finished = (ROOT / "db/migrations/106_finished_bottle_value.sql").read_text()
        self.assertIn("LOWER(TRIM(p.category_name))='vino'", finished)
        self.assertIn('router.patch("/{product_id}/stock-value"', routes)
        self.assertIn("financeLaborCost", html)
        self.assertIn("financeLaborPaid", html)
        self.assertIn("financeLaborDue", html)
        self.assertIn("financeSalesInvoices", html)
        self.assertIn("financePurchaseInvoices", html)
        self.assertIn("data-bottle-value", javascript)


if __name__ == "__main__":
    unittest.main()
