import pathlib
import unittest

from app.whatsapp_intent import is_submission


class WhatsappIntentTests(unittest.TestCase):
    def test_topic_prompt_is_a_question_not_an_update(self):
        self.assertFalse(is_submission("Vineyard weather", {"classification": "weather_observation", "contains_question": False}))

    def test_italian_topic_prompt_is_a_question_not_an_update(self):
        self.assertFalse(is_submission("Meteo vigneto", {"classification": "weather_observation", "contains_question": False}))

    def test_explicit_labor_report_is_an_update(self):
        self.assertTrue(is_submission("Record 5 hours worked today", {"classification": "labor", "contains_question": False}))

    def test_measured_weather_report_is_an_update(self):
        self.assertTrue(is_submission("Rain observed 2.4 mm", {"classification": "weather_observation", "contains_question": False}))

    def test_question_mark_always_preserves_chat(self):
        self.assertFalse(is_submission("Record 5 hours?", {"classification": "labor", "contains_question": False}))

    def test_manager_camera_backend_is_bilingual_and_audited(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = (root / "app" / "main.py").read_text()
        self.assertIn("resolve_home_assistant_camera_request", intelligence)
        self.assertIn("telecamera|telecamere", intelligence)
        self.assertIn("home_assistant_camera_snapshot", intelligence)
        self.assertIn("home_assistant_manager_camera_catalog", intelligence)
        self.assertIn("home_assistant_camera_entities", main)
        self.assertIn("manager_camera_snapshot", main)
        self.assertIn('audit(cursor, "view", "home_assistant_camera"', main)

    def test_every_direct_inbound_type_has_a_saved_route_and_response(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "app" / "main.py").read_text()
        self.assertIn("Message received and saved for administrator review", source)
        self.assertIn("Daily assistant limit reached. Your message was saved for review.", source)
        self.assertIn("Attachment received, but download failed. The error was logged.", source)
        self.assertIn("Voice note received and saved for review.", source)
        self.assertIn('message_id + ":unsupported"', source)
        self.assertIn("'message_received'", source)
        self.assertIn('reply_mode == "match"', source)
        self.assertIn('incoming_mode == "voice"', source)
        self.assertIn("def _whatsapp_reply_preference", source)
        self.assertIn('"reply settings", "reply options"', source)
        self.assertIn('"source": "self_service"', source)
        self.assertIn('normalized in {"?", "menu", "help", "capabilities"', source)
        self.assertIn("Manager menu", source)
        process_control = (root / "app" / "process_control.py").read_text()
        self.assertIn('"whatsapp": "WhatsApp connection & catalogs"', process_control)
        self.assertNotIn('if allowed and sender not in allowed and sender_assignment["profile"] == "off":\n                    continue', source)

    def test_manager_can_read_intelligence_traffic_cistern_and_current_presence(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = (root / "app" / "main.py").read_text()
        self.assertIn("def whatsapp_manager_traffic_context", intelligence)
        self.assertIn("def home_assistant_manager_presence", intelligence)
        self.assertIn('"cistern": latest_cistern_level()', intelligence)
        self.assertIn('"next_treatment_review": predict_next_treatment', intelligence)
        self.assertIn('"traffic": whatsapp_manager_traffic_context()', intelligence)
        self.assertIn('"team_presence": presence', intelligence)
        self.assertIn("never turn unknown or stale presence into an on-site claim", intelligence)
        self.assertIn("Ask who is currently at Baiamonte", main)
        self.assertIn("Chiedi chi è attualmente a Baiamonte", main)


if __name__ == "__main__":
    unittest.main()
