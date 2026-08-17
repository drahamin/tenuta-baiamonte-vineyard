import unittest
from pathlib import Path

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class WhatsappSenderStateTests(unittest.TestCase):
    def test_runtime_settings_are_merged_instead_of_replaced(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("current.update(loaded)", source)
        self.assertIn("current.update(values)", source)
        self.assertIn("json.dumps(current", source)

    def test_inbound_and_outbound_health_are_sender_scoped(self) -> None:
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        frontend = frontend_source(ROOT)
        self.assertIn('details.get("phone_number_id")', main)
        self.assertIn('"phone_number_id": receiver_phone_number_id or None', main)
        self.assertGreaterEqual(intelligence.count('"phone_number_id": phone_number_id'), 2)
        self.assertIn('class="channel-status-lights"', frontend)
        self.assertNotIn("outbound sent", frontend)


if __name__ == "__main__":
    unittest.main()
