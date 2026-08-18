from pathlib import Path
import unittest

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class IntakeReviewControlTests(unittest.TestCase):
    def test_initial_route_is_only_applied_once(self):
        source = frontend_source(ROOT)
        self.assertIn(
            "function activateRequestedView(){if(requestedRouteApplied)return;requestedRouteApplied=true;",
            source,
        )

    def test_incoming_items_have_a_direct_reject_action(self):
        source = frontend_source(ROOT)
        self.assertIn('data-intake-reject="${row.id}"', source)
        self.assertIn("openIntakeRejection(reject.dataset.intakeReject", source)

    def test_rejection_uses_an_audited_reason_form(self):
        html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        source = frontend_source(ROOT)
        self.assertIn('id="rejectIntakeDialog"', html)
        self.assertIn('id="rejectIntakeForm"', html)
        self.assertIn("submitIntakeRejection", source)
        self.assertIn("review_reason:reason", source)

    def test_entry_form_reports_save_progress_and_failure(self):
        html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        source = frontend_source(ROOT)
        self.assertIn('id="entryStatus"', html)
        self.assertIn("Saving review…", source)
        self.assertIn("The review was not saved.", source)


if __name__ == "__main__":
    unittest.main()
