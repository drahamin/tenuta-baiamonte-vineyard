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

    def test_retired_imessage_channel_cannot_break_tv_and_tv_alias_exists(self) -> None:
        payload_source = (ROOT / "app/display_data.py").read_text()
        server_source = (ROOT / "app/display_server.py").read_text()
        self.assertNotIn("imessage_bridge_url", payload_source)
        self.assertNotIn("imessage-channel", payload_source)
        self.assertIn('@display_app.get("/tv")', server_source)


if __name__ == "__main__":
    unittest.main()
