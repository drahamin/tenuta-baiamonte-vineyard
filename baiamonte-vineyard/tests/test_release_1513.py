import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Release1513Tests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
