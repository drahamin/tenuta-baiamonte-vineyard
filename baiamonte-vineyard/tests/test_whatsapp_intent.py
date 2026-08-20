import pathlib
import unittest
from unittest.mock import patch

from app.intelligence import current_home_assistant_presence, home_assistant_manager_presence
from app.whatsapp_intent import capabilities, handoff_requested, is_submission, language_preference, menu_route, prefers_italian
from tests.source_helpers import frontend_source


class WhatsappIntentTests(unittest.TestCase):
    def test_unchanged_home_assistant_person_state_remains_current_presence(self):
        self.assertEqual(current_home_assistant_presence({"state": "home", "last_changed": "2026-01-01T00:00:00Z"}), "on_site")
        self.assertEqual(current_home_assistant_presence({"state": "not_home", "last_changed": "2026-01-01T00:00:00Z"}), "away")
        self.assertIsNone(current_home_assistant_presence({"state": "unavailable"}))

    def test_manager_presence_uses_live_person_state_even_when_last_changed_is_old(self):
        states = [{
            "entity_id": "person.david_rahamin_2",
            "state": "home",
            "last_changed": "2026-01-01T00:00:00Z",
            "last_updated": "2026-01-01T00:00:00Z",
            "attributes": {"friendly_name": "David Rahamin"},
        }]
        with patch("app.intelligence._ha_get", return_value=states):
            david = home_assistant_manager_presence()[0]
        self.assertEqual(david["presence"], "at_baiamonte")
        self.assertEqual(david["evidence"], "current Home Assistant Person/GPS state")

    def test_automatic_language_uses_words_then_country_code(self):
        self.assertTrue(prefers_italian("7", "auto", "+39 339 773 2052"))
        self.assertFalse(prefers_italian("7", "auto", "+1 305 218 7450"))
        self.assertFalse(prefers_italian("weather today", "auto", "+39 339 773 2052"))
        self.assertTrue(prefers_italian("meteo oggi", "auto", "+1 305 218 7450"))
        self.assertFalse(prefers_italian("ciao", "en", "+39 339 773 2052"))
        self.assertTrue(prefers_italian("hello", "it", "+1 305 218 7450"))

    def test_language_commands_are_explicit_and_bilingual(self):
        self.assertEqual(language_preference("ENGLISH"), "en")
        self.assertEqual(language_preference("Italiano"), "it")
        self.assertEqual(language_preference("lingua automatica"), "auto")
        self.assertEqual(language_preference("language"), "help")
        self.assertIsNone(language_preference("Italian weather"))

    def test_human_handoff_is_bilingual_but_not_triggered_by_normal_questions(self):
        self.assertTrue(handoff_requested("HUMAN"))
        self.assertTrue(handoff_requested("parlare con una persona"))
        self.assertFalse(handoff_requested("Who is the cellar manager?"))

    def test_manager_numbered_menu_routes_to_safe_operational_prompts(self):
        self.assertEqual(menu_route("manager", "8", False), ("prompt", "CAMERAS"))
        expected = {
            0: "snapshot_help",
            2: "snapshot_weather",
            3: "snapshot_work",
            4: "snapshot_disease",
            5: "snapshot_harvest",
            7: "snapshot_cistern",
            9: "snapshot_presence",
            10: "snapshot_power",
            11: "snapshot_traffic",
        }
        for choice, route in expected.items():
            with self.subTest(choice=choice):
                self.assertEqual(menu_route("manager", str(choice), False)[0], route)
        self.assertEqual(menu_route("manager", "13", False)[0], "blend_crate_calculator")

    def test_reception_handoff_and_invalid_choices_are_direct_responses(self):
        self.assertEqual(menu_route("reception", "4", False)[0], "handoff")
        invalid = menu_route("reporter", "12", False)
        self.assertEqual(invalid[0], "reply")
        self.assertIn("Reply MENU", invalid[1])

    def test_capabilities_are_role_specific(self):
        self.assertIn("12 Submit field or operational record", capabilities("manager", False))
        self.assertIn("13 Nerello / Grenache crate calculator", capabilities("manager", False))
        self.assertIn("5 Invia rilievo o record operativo", capabilities("reporter", True))
        self.assertIn("Public harvest information", capabilities("reception", False))

    def test_manager_and_reporter_can_open_structured_field_forms(self):
        self.assertEqual(menu_route("manager", "12", False), ("observation_menu", "OBSERVATION_FORMS"))
        self.assertEqual(menu_route("reporter", "5", True), ("observation_menu", "OBSERVATION_FORMS"))

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

    def test_manager_camera_selector_receives_the_live_catalog(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        main = (root / "app" / "main.py").read_text()
        html = (root / "app" / "static" / "index.html").read_text()
        javascript = frontend_source(root)
        self.assertIn('assistant_settings["home_assistant_camera_catalog"] = home_assistant_manager_camera_catalog()', main)
        self.assertIn('id="managerCameraChoices"', html)
        self.assertIn('id="selectManagerCameras"', html)
        self.assertIn("data-recommended", javascript)
        self.assertIn("selectManagerCameras", javascript)

    def test_every_direct_inbound_type_has_a_saved_route_and_response(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (
            (root / "app" / "main.py").read_text()
            + (root / "app" / "whatsapp_intent.py").read_text()
            + (root / "app" / "domains" / "whatsapp_live.py").read_text()
        )
        self.assertIn("Message received and saved for administrator review", source)
        self.assertIn("Daily assistant limit reached. Your message was saved for review.", source)
        self.assertIn("Attachment received, but download failed. The error was logged.", source)
        self.assertIn("Voice note received and saved for review.", source)
        self.assertIn('message_id + ":unsupported"', source)
        self.assertIn("'message_received'", source)
        self.assertIn('reply_mode == "match"', source)
        self.assertIn('contact.get("reply_mode") or "match"', source)
        self.assertIn('incoming_mode == "voice"', source)
        self.assertIn("def _whatsapp_reply_preference", source)
        self.assertIn('"reply settings", "reply options"', source)
        self.assertIn('"source": "self_service"', source)
        self.assertIn('normalized in {"?", "menu", "help", "capabilities"', source)
        self.assertIn("Manager menu", source)
        self.assertIn("def menu_route", source)
        self.assertIn("Manager menu — reply with a number", source)
        self.assertIn("1 Today and urgent alerts", source)
        self.assertIn("11 AIS, ADS-B, earthquakes and Etna", source)
        self.assertIn('if route.startswith("snapshot_")', source)
        self.assertIn("def live_snapshot", source)
        self.assertIn("async def live_assisted_snapshot", source)
        self.assertIn("VERIFIED CURRENT SNAPSHOT", source)
        self.assertIn('"it" if italian else "en"', source)
        self.assertIn('return number.startswith("39")', source)
        self.assertIn("public_harvest_feed().get(\"items\")", source)
        self.assertIn("Reporter menu — reply with a number", source)
        self.assertIn("Reception menu — reply with a number", source)
        self.assertIn('body = routed_text', source)
        self.assertIn("def handoff_requested", source)
        self.assertIn("Reply MENU for options or HUMAN", source)
        frontend = (root / "app" / "static" / "app.js").read_text()
        self.assertIn("Address book saved · status refresh delayed", frontend)
        process_control = (root / "app" / "process_control.py").read_text()
        self.assertIn('"whatsapp": "WhatsApp connection & catalogs"', process_control)
        self.assertNotIn('if allowed and sender not in allowed and sender_assignment["profile"] == "off":\n                    continue', source)

    def test_whatsapp_supports_bilingual_self_service_language_and_format(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "app" / "main.py").read_text() + (root / "app" / "whatsapp_intent.py").read_text()
        self.assertIn("def language_preference", source)
        self.assertIn("def _set_whatsapp_language_preference", source)
        self.assertIn('"english", "language english"', source)
        self.assertIn('"italiano", "italian"', source)
        self.assertIn('"language automatic", "language auto"', source)
        self.assertIn('"whatsapp_language_preference"', source)
        self.assertIn("Language / Lingua: reply ENGLISH, ITALIANO, or LANGUAGE AUTO.", source)

    def test_manager_can_read_intelligence_traffic_cistern_and_current_presence(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = (root / "app" / "main.py").read_text()
        intent = (root / "app" / "whatsapp_intent.py").read_text()
        self.assertIn("def whatsapp_manager_traffic_context", intelligence)
        self.assertIn("def home_assistant_manager_presence", intelligence)
        self.assertIn('"cistern": latest_cistern_level()', intelligence)
        self.assertIn('"next_treatment_review": predict_next_treatment', intelligence)
        self.assertIn('"traffic": whatsapp_manager_traffic_context()', intelligence)
        self.assertIn('"team_presence": presence', intelligence)
        self.assertIn("never turn unknown or stale presence into an on-site claim", intelligence)
        self.assertIn("9 Team presence", intent)
        self.assertIn("9 Presenze del team", intent)
        self.assertIn("Who is currently at Baiamonte?", intent)

    def test_whatsapp_covers_the_unified_operating_system(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = (root / "app" / "main.py").read_text()
        intent = (root / "app" / "whatsapp_intent.py").read_text()
        self.assertIn("planning_view, sync_google_planning, treatment_reminder_plan, unified_work_plan", intelligence)
        self.assertIn('"unified_work_plan"', intelligence)
        self.assertIn('"operational_calendar"', intelligence)
        self.assertIn('"harvest_projections"', intelligence)
        self.assertIn('"recorded_contractor_hours"', intelligence)
        self.assertIn('"treatment_reminders"', intelligence)
        self.assertIn("task_or_project", intelligence)
        self.assertIn("3 Work plan and calendar", intent)
        self.assertIn("3 Piano di lavoro e calendario", intent)
        self.assertIn("Give me the current work plan, priorities, deadlines, projects, tasks, and calendar.", intent)
        self.assertIn("A treatment reminder is only a plan", intelligence)

    def test_whatsapp_registration_diagnostic_does_not_invent_failure(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        self.assertIn('"registration_state": "confirmed"', intelligence)
        self.assertIn('else None', intelligence)
        self.assertIn('if registered is False:', intelligence)
        main = (root / "app" / "main.py").read_text()
        frontend = frontend_source(root)
        self.assertIn('diagnostics.get("registered") is not False', main)
        self.assertIn("wa.connected&&wa.registered!==false", frontend)
        self.assertIn("The sender details are saved, but the live Meta check did not complete", frontend)


if __name__ == "__main__":
    unittest.main()
