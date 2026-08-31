import pathlib
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from app.domains.whatsapp_live import _condition, _human_date, humanize_reply
from app.domains.whatsapp_people import MANAGER_TEXT_AND_AUDIO_ROUTES, personalize_live_snapshot, sender_profile
from app.intelligence import current_home_assistant_presence, home_assistant_manager_presence
from app.whatsapp_intent import capabilities, handoff_requested, is_submission, language_preference, menu_route, prefers_italian
from app.domains.communications_whatsapp_assistant import _archive_routine_whatsapp_intake
from tests.source_helpers import frontend_source


def whatsapp_backend_source(root: pathlib.Path) -> str:
    return "\n".join(
        (root / path).read_text()
        for path in (
            "app/main.py",
            "app/domains/communications_meta.py",
            "app/domains/communications_meta_routes.py",
            "app/domains/communications_meta_webhook_routes.py",
            "app/domains/communications_whatsapp_assistant.py",
        )
    )


class WhatsappIntentTests(unittest.TestCase):
    @patch("app.domains.communications_whatsapp_assistant.audit")
    @patch("app.domains.communications_whatsapp_assistant.transaction")
    def test_completed_ivr_messages_are_archived_without_deleting_evidence(self, transaction_mock, audit_mock):
        cursor = MagicMock()
        cursor.execute.return_value = 2
        transaction_mock.return_value.__enter__.return_value = (None, cursor)

        _archive_routine_whatsapp_intake("text-record", "snapshot_weather", ("voice-record",))

        sql, parameters = cursor.execute.call_args.args
        self.assertIn("review_status='archived'", sql)
        self.assertIn("intervention_required", sql)
        self.assertEqual(parameters[-2:], ("text-record", "voice-record"))
        audit_mock.assert_called_once()

    @patch("app.domains.communications_whatsapp_assistant.transaction")
    def test_empty_ivr_record_is_not_written(self, transaction_mock):
        _archive_routine_whatsapp_intake(None, "menu")
        transaction_mock.assert_not_called()

    def test_manager_information_audio_routes_are_personalized(self):
        expected = {
            "snapshot_today", "snapshot_operations", "snapshot_agronomy", "snapshot_harvest",
            "snapshot_enology", "snapshot_olives", "snapshot_hospitality",
        }
        self.assertEqual(MANAGER_TEXT_AND_AUDIO_ROUTES, expected)
        self.assertNotIn("snapshot_cameras", MANAGER_TEXT_AND_AUDIO_ROUTES)
        self.assertNotIn("snapshot_presence", MANAGER_TEXT_AND_AUDIO_ROUTES)
        self.assertNotIn("snapshot_estate_systems", MANAGER_TEXT_AND_AUDIO_ROUTES)
        reply = personalize_live_snapshot(
            "Tank Sensor is stable.", "snapshot_enology",
            {"contact": {"name": "Wendy Creque"}}, False,
        )
        self.assertEqual(reply, "Wendy, here's the Tank Sensor, cellar, and bottling update.\n\nTank Sensor is stable.")

    @patch("app.domains.whatsapp_people.contact_book")
    def test_legacy_both_reply_mode_defaults_to_matching_the_sender(self, contact_book_mock):
        contact_book_mock.return_value = {"contacts": [{"number": "393123456789", "assistant": "manager", "reply_mode": "both"}], "groups": []}
        profile = sender_profile("393123456789", {"unknown_reception": False})
        self.assertEqual(profile["contact"]["reply_mode"], "match")
        contact_book_mock.return_value["contacts"][0]["reply_mode_explicit"] = True
        profile = sender_profile("393123456789", {"unknown_reception": False})
        self.assertEqual(profile["contact"]["reply_mode"], "both")

    def test_ivr_dates_times_and_weather_conditions_are_human_readable(self):
        reference = datetime(2026, 8, 23, 14, 0, tzinfo=ZoneInfo("Europe/Rome"))
        self.assertEqual(_human_date("2026-08-23 11:22", reference=reference, include_time=True), "today at 1:22 PM")
        self.assertEqual(_human_date("2026-08-23 11:22", True, reference=reference, include_time=True), "oggi alle 13:22")
        self.assertEqual(_human_date("2026-08-24", reference=reference), "tomorrow")
        self.assertEqual(_condition("partlycloudy"), "partly cloudy")
        self.assertEqual(_condition("clear-night", True), "sereno durante la notte")
        self.assertEqual(
            humanize_reply("Observed 2026-08-23 11:22; tomorrow is partlycloudy.", reference=reference),
            "Observed today at 1:22 PM; tomorrow is partly cloudy.",
        )
        self.assertEqual(humanize_reply("https://example.test/2026-08-23"), "https://example.test/2026-08-23")

    def test_ivr_prompts_require_conversational_not_database_language(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        live = (root / "app" / "domains" / "whatsapp_live.py").read_text()
        intelligence = (root / "app" / "intelligence.py").read_text()
        self.assertIn("Never expose ISO dates", live)
        self.assertIn("Write like a helpful person, not a database or machine", intelligence)
        self.assertIn("Read dates and times as natural spoken phrases", intelligence)
        self.assertIn("_humanize_whatsapp_reply", whatsapp_backend_source(root))

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
        expected = {
            0: "snapshot_help",
            1: "snapshot_today",
            2: "snapshot_operations",
            3: "snapshot_agronomy",
            4: "snapshot_harvest",
            5: "snapshot_enology",
            6: "snapshot_olives",
            7: "snapshot_estate_systems",
            8: "snapshot_hospitality",
        }
        for choice, route in expected.items():
            with self.subTest(choice=choice):
                self.assertEqual(menu_route("manager", str(choice), False)[0], route)
        self.assertEqual(menu_route("manager", "9", False)[0], "reply")
        self.assertEqual(menu_route("manager", "9", False, True)[0], "snapshot_admin")
        self.assertEqual(menu_route("manager", "10", False)[0], "observation_menu")
        self.assertEqual(menu_route("manager", "11", False)[0], "blend_crate_calculator")
        self.assertEqual(menu_route("manager", "12", False)[0], "snapshot_fox")

    def test_reporter_numbered_menu_does_not_depend_on_ai(self):
        expected = {1: "snapshot_operations", 2: "snapshot_weather", 3: "snapshot_disease", 4: "snapshot_harvest", 5: "snapshot_enology", 6: "snapshot_olives"}
        for choice, route in expected.items():
            with self.subTest(choice=choice):
                self.assertEqual(menu_route("reporter", str(choice), False)[0], route)

    def test_common_spoken_topics_route_locally_without_ai(self):
        self.assertEqual(menu_route("manager", "cellar", False)[0], "snapshot_cellar")
        self.assertEqual(menu_route("manager", "power", False)[0], "snapshot_power")
        self.assertEqual(menu_route("reporter", "weather", False)[0], "snapshot_weather")
        self.assertEqual(menu_route("reception", "harvest", False)[0], "snapshot_harvest")
        self.assertEqual(menu_route("reception", "1", False)[0], "snapshot_estate")
        self.assertEqual(menu_route("reception", "2", False)[0], "snapshot_hospitality_public")
        self.assertEqual(menu_route("reception", "6", False)[0], "reply")

    def test_reception_handoff_and_invalid_choices_are_direct_responses(self):
        self.assertEqual(menu_route("reception", "5", False)[0], "handoff")
        invalid = menu_route("reporter", "12", False)
        self.assertEqual(invalid[0], "reply")
        self.assertIn("Send +", invalid[1])

    def test_capabilities_are_role_specific(self):
        self.assertIn("10 Record / submit data", capabilities("manager", False))
        self.assertIn("11 Nerello / Grenache crate calculator", capabilities("manager", False))
        self.assertIn("12 Foxes this month", capabilities("manager", False))
        self.assertIn("7 Registra / invia dati", capabilities("reporter", True))
        self.assertIn("Public vintage information", capabilities("reception", False))

    def test_manager_and_reporter_can_open_structured_field_forms(self):
        self.assertEqual(menu_route("manager", "10", False), ("observation_menu", "OBSERVATION_FORMS"))
        self.assertEqual(menu_route("reporter", "7", True), ("observation_menu", "OBSERVATION_FORMS"))

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
        main = whatsapp_backend_source(root)
        self.assertIn("resolve_home_assistant_camera_request", intelligence)
        self.assertIn("telecamera|telecamere", intelligence)
        self.assertIn("home_assistant_camera_snapshot", intelligence)
        self.assertIn("home_assistant_manager_camera_catalog", intelligence)
        self.assertIn("home_assistant_camera_entities", main)
        self.assertIn("manager_camera_snapshot", main)
        self.assertIn('audit(cursor, "view", "home_assistant_camera"', main)

    def test_manager_camera_selector_receives_the_live_catalog(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        main = whatsapp_backend_source(root)
        html = (root / "app" / "static" / "index.html").read_text()
        javascript = frontend_source(root)
        self.assertIn('assistants["home_assistant_camera_catalog"] = home_assistant_manager_camera_catalog()', main)
        self.assertIn('id="managerCameraChoices"', html)
        self.assertIn('id="selectManagerCameras"', html)
        self.assertIn("data-recommended", javascript)
        self.assertIn("selectManagerCameras", javascript)

    def test_every_direct_inbound_type_has_a_saved_route_and_response(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (
            whatsapp_backend_source(root)
            + (root / "app" / "whatsapp_intent.py").read_text()
            + (root / "app" / "domains" / "whatsapp_live.py").read_text()
            + (root / "app" / "domains" / "whatsapp_people.py").read_text()
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
        self.assertIn('normalized in {"+", "plus", "più", "piu", "?", "menu", "start", "inizia", "help", "capabilities"', source)
        self.assertIn("Manager menu", source)
        self.assertIn("def menu_route", source)
        self.assertIn("BAIAMONTE · MANAGER", source)
        self.assertIn("1 Today · alerts and decisions", source)
        self.assertIn("7 Estate systems · cistern, cameras, energy, security and Etna", source)
        self.assertIn('if route.startswith("snapshot_")', source)
        self.assertIn("def live_snapshot", source)
        self.assertIn("async def live_assisted_snapshot", source)
        self.assertIn("snapshot_enology", source)
        self.assertIn("snapshot_olives", source)
        self.assertIn("snapshot_hospitality_public", source)
        self.assertIn("snapshot_today", source)
        self.assertIn("ivr_route_learning", source)
        self.assertIn("assistant_fallback", source)
        self.assertIn("def personalized_menu", source)
        self.assertIn("Your usual choices", source)
        self.assertIn("person_entity", source)
        self.assertIn("VERIFIED CURRENT SNAPSHOT", source)
        self.assertIn('"it" if italian else "en"', source)
        self.assertIn('return number.startswith("39")', source)
        self.assertIn("public_harvest_feed().get(\"items\")", source)
        self.assertIn("BAIAMONTE · REPORTER", source)
        self.assertIn("BAIAMONTE · GUESTS", source)
        self.assertIn('body = routed_text', source)
        self.assertIn("def handoff_requested", source)
        self.assertIn("Send + for the menu or HUMAN", source)
        frontend = (root / "app" / "static" / "app.js").read_text()
        self.assertIn("Address book saved · status refresh delayed", frontend)
        process_control = (root / "app" / "process_control.py").read_text()
        self.assertIn('"whatsapp": "WhatsApp connection & catalogs"', process_control)
        self.assertNotIn('if allowed and sender not in allowed and sender_assignment["profile"] == "off":\n                    continue', source)

    def test_whatsapp_supports_bilingual_self_service_language_and_format(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = whatsapp_backend_source(root) + (root / "app" / "whatsapp_intent.py").read_text() + (root / "app" / "domains" / "whatsapp_people.py").read_text()
        self.assertIn("def language_preference", source)
        self.assertIn("def set_language_preference", source)
        self.assertIn('"english", "language english"', source)
        self.assertIn('"italiano", "italian"', source)
        self.assertIn('"language automatic", "language auto"', source)
        self.assertIn('"whatsapp_language_preference"', source)
        self.assertIn("Language / Lingua: reply ENGLISH, ITALIANO, or LANGUAGE AUTO.", source)

    def test_manager_can_read_intelligence_traffic_cistern_and_current_presence(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = whatsapp_backend_source(root)
        intent = (root / "app" / "whatsapp_intent.py").read_text()
        self.assertIn("def whatsapp_manager_traffic_context", intelligence)
        self.assertIn("def home_assistant_manager_presence", intelligence)
        self.assertIn('"cistern": latest_cistern_level()', intelligence)
        self.assertIn('"next_treatment_review": predict_next_treatment', intelligence)
        self.assertIn('"traffic": whatsapp_manager_traffic_context()', intelligence)
        self.assertIn('manager_intelligence["team_presence"]', intelligence)
        self.assertIn("Only discuss team presence when team_presence is explicitly included", intelligence)
        self.assertIn("and not administrator", intent)
        self.assertIn("9 Team and finance · administrator only", intent)
        self.assertIn("9 Team e finanza · solo amministratore", intent)
        self.assertIn("administrator-only team, finance, payment, and review summary", intent)

    def test_whatsapp_covers_the_unified_operating_system(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        main = whatsapp_backend_source(root)
        intent = (root / "app" / "whatsapp_intent.py").read_text()
        self.assertIn("planning_view, sync_google_planning, treatment_reminder_plan, unified_work_plan", intelligence)
        self.assertIn('"unified_work_plan"', intelligence)
        self.assertIn('"operational_calendar"', intelligence)
        self.assertIn('"harvest_projections"', intelligence)
        self.assertIn('"recorded_contractor_hours"', intelligence)
        self.assertIn('"treatment_reminders"', intelligence)
        self.assertIn("task_or_project", intelligence)
        self.assertIn("2 Operations · work, issues and equipment", intent)
        self.assertIn("2 Operazioni · lavoro, problemi e attrezzature", intent)
        self.assertIn("Give me current operations, work, open issues, deadlines, and equipment checks.", intent)
        self.assertIn("A treatment reminder is only a plan", intelligence)

    def test_whatsapp_registration_diagnostic_does_not_invent_failure(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        intelligence = (root / "app" / "intelligence.py").read_text()
        self.assertIn('"registration_state": "confirmed"', intelligence)
        self.assertIn('else None', intelligence)
        self.assertIn('if registered is False:', intelligence)
        main = whatsapp_backend_source(root)
        frontend = frontend_source(root)
        self.assertIn('diagnostics.get("registered") is not False', main)
        self.assertIn("wa.connected&&wa.registered!==false", frontend)
        self.assertIn("The sender details are saved, but the live Meta check did not complete", frontend)


if __name__ == "__main__":
    unittest.main()
