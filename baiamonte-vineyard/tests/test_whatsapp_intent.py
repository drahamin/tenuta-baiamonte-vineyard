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
        self.assertIn("manager_camera_snapshot", main)
        self.assertIn('audit(cursor, "view", "home_assistant_camera"', main)


if __name__ == "__main__":
    unittest.main()
