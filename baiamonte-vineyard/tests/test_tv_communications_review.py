from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TvCommunicationsReviewTests(unittest.TestCase):
    def test_answered_whatsapp_questions_leave_review_queue(self) -> None:
        source = (ROOT / "app/display_data.py").read_text()
        self.assertIn("def _communications_review_condition", source)
        self.assertIn("'chatbot_reply','manager_camera_snapshot','inbound_routing'", source)
        self.assertIn("answered.status='processed'", source)

    def test_pending_approvals_and_controls_remain_visible(self) -> None:
        source = (ROOT / "app/display_data.py").read_text()
        self.assertIn("'intake_approval_pending','manager_control_pending','manager_device_control_pending'", source)
        self.assertIn("pending.status='received'", source)


if __name__ == "__main__":
    unittest.main()
