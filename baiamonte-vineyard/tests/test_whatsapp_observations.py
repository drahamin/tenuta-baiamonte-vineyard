import pathlib
import unittest
from unittest.mock import patch

from app.whatsapp_observations import (
    PHENOLOGY_STAGES,
    apply_answer,
    completed,
    learned_submission_default,
    new_state,
    other_submission_choice,
    previous_state,
    prompt,
    submission_choice,
    submission_menu,
    values_for_save,
)


BLOCKS = [{"id": "block-1", "code": "B1", "name": "North"}]
VARIETIES = [{"id": "variety-1", "name": "Nerello Mascalese"}]


class WhatsappObservationFormTests(unittest.TestCase):
    def _complete(self, kind, answers):
        state = new_state(kind)
        for answer in answers:
            state = apply_answer(state, answer, BLOCKS, VARIETIES)
        self.assertTrue(completed(state))
        return values_for_save(state)

    def test_menu_exposes_complete_field_operations_and_enology_forms(self):
        menu = submission_menu(False)
        self.assertIn("1 Field scouting", menu)
        self.assertIn("2 Growth stage", menu)
        self.assertIn("3 Treatment field report", menu)
        self.assertIn("4 Completed work", menu)
        self.assertIn("8 Fruit maturity", menu)
        self.assertIn("voice note", menu)
        self.assertIn("* Back · + Menu · = Cancel", menu)
        self.assertEqual(submission_choice("1"), "scouting")
        self.assertEqual(submission_choice("fenologia"), "phenology")
        self.assertEqual(submission_choice("fruit maturity"), "maturity_sample")
        self.assertEqual(submission_choice("10"), "cellar_operation")
        self.assertEqual(submission_choice("11"), "freeform_report")

    def test_scouting_collects_required_and_review_fields(self):
        values = self._complete(
            "scouting",
            ["2", "2026-08-20 09:30", "Downy mildew", "2", "12", "lower rows", "YES", "photo to follow"],
        )
        self.assertEqual(values["block_id"], "block-1")
        self.assertEqual(values["severity"], "low")
        self.assertEqual(values["action_required"], 1)
        self.assertEqual(values["incidence_pct"], 12)

    def test_phenology_uses_fixed_animation_compatible_stage_codes(self):
        veraison_number = next(index for index, item in enumerate(PHENOLOGY_STAGES, 1) if item[0] == "veraison")
        values = self._complete("phenology", ["1", "1", "2026-08-20", str(veraison_number), "75", "SKIP"])
        self.assertEqual(values["stage_code"], "veraison")
        self.assertEqual(values["stage_name"], "Veraison")
        self.assertEqual(values["percent_complete"], 75)

    def test_maturity_collects_sample_metrics_and_decision_without_approval(self):
        values = self._complete(
            "maturity_sample",
            ["1", "1", "2026-08-20 10:00", "21.4", "3.25", "6.8", "24", "2", "Healthy", "4", "SKIP"],
        )
        self.assertEqual(values["variety_id"], "variety-1")
        self.assertEqual(values["brix"], 21.4)
        self.assertEqual(values["decision"], "ready")
        self.assertNotIn("approved", values)

    def test_treatment_report_is_always_planned_and_unapproved(self):
        values = self._complete(
            "treatment",
            ["2", "2026-08-22", "downy mildew", "2.5", "400", "Giancarlo", "carrier", "copper 1 kg", "calm, dry", "SKIP"],
        )
        self.assertEqual(values["status"], "planned")
        self.assertEqual(values["crop_scope"], "vineyard")
        self.assertNotIn("agronomist_approved", values)
        self.assertIn("copper 1 kg", values["notes"])

    def test_operations_and_enology_forms_save_canonical_quick_entries(self):
        work = self._complete("work_activity", ["2", "2026-08-22", "Mowed rows", "6", "2", "SKIP"])
        fermentation = self._complete("fermentation", ["T-04", "2026-08-22 14:00", "24", "1.030", "8", "3.4", "clean", "SKIP"])
        cellar = self._complete("cellar_operation", ["T-04", "2026-08-22 15:00", "Racking", "100", "L", "18", "Clean transfer"])
        self.assertEqual(work["title"], "Mowed rows")
        self.assertEqual(fermentation["vessel_name"], "T-04")
        self.assertEqual(fermentation["density_sg"], 1.03)
        self.assertIn("Reported lot/tank: T-04", cellar["notes"])

    def test_issue_priority_matches_database_enum(self):
        values = self._complete("issue", ["Broken irrigation valve", "4", "SKIP", "SKIP", "SKIP"])
        self.assertEqual(values["priority"], "critical")

    def test_complicated_voice_report_becomes_a_reviewable_open_issue(self):
        values = self._complete("freeform_report", ["Finished the north rows today; two workers; irrigation leak needs repair tomorrow."])
        self.assertEqual(values["status"], "open")
        self.assertEqual(values["owner_text"], "Operations review")
        self.assertIn("irrigation leak", values["issue_text"])

    def test_scouting_can_cover_the_entire_estate(self):
        state = new_state("scouting")
        menu = prompt(state, BLOCKS, VARIETIES, False)
        self.assertIn("Where? Reply or say the number", menu)
        self.assertIn("1. Entire estate", menu)
        self.assertIn("2. North (B1)", menu)
        state = apply_answer(state, "1", BLOCKS, VARIETIES)
        self.assertNotIn("block_id", state["values"])
        self.assertEqual(state["values"]["damage_scope"], "estate")
        self.assertEqual(state["values"]["representative_survey"], 1)
        self.assertEqual(state["values"]["_block"], "Entire estate")
        spoken = apply_answer(new_state("scouting"), "intera tenuta", BLOCKS, VARIETIES)
        self.assertEqual(spoken["values"]["damage_scope"], "estate")

    def test_back_from_first_question_returns_to_record_menu(self):
        state = previous_state(new_state("scouting"))
        self.assertEqual(state, {"kind": "select", "step": 0, "values": {}})

    def test_back_from_later_question_moves_one_step_and_clears_answer(self):
        state = apply_answer(new_state("scouting"), "2", BLOCKS, VARIETIES)
        state = previous_state(state)
        self.assertEqual(state["kind"], "scouting")
        self.assertEqual(state["step"], 0)
        self.assertNotIn("block_id", state["values"])

    @patch("app.whatsapp_observations.fetch_all")
    def test_ivr_learns_last_saved_location_but_requires_explicit_same(self, fetch_all_mock):
        fetch_all_mock.return_value = [{"payload": {
            "kind": "scouting", "step": 8,
            "values": {"block_id": "block-1", "_block": "B1"},
        }}]
        learned = learned_submission_default("13055551212", "scouting")
        self.assertEqual(learned, {"block_id": "block-1", "label": "B1"})
        state = {**new_state("scouting"), "learned_location": learned}
        self.assertIn("S. Same as last time: B1", prompt(state, BLOCKS, VARIETIES, False))
        state = apply_answer(state, "S", BLOCKS, VARIETIES)
        self.assertEqual(state["values"]["block_id"], "block-1")

    @patch("app.whatsapp_observations.fetch_all")
    def test_ivr_learning_can_require_repeated_matching_history(self, fetch_all_mock):
        fetch_all_mock.return_value = [
            {"payload": {"kind": "scouting", "values": {"block_id": "block-1", "_block": "B1"}}},
            {"payload": {"kind": "scouting", "values": {"block_id": "block-1", "_block": "B1"}}},
        ]
        self.assertEqual(
            learned_submission_default("13055551212", "scouting", 2),
            {"block_id": "block-1", "label": "B1"},
        )
        self.assertIsNone(learned_submission_default("13055551212", "scouting", 3))

    def test_invalid_values_keep_the_form_on_the_same_step(self):
        state = new_state("scouting")
        state = apply_answer(state, "1", BLOCKS, VARIETIES)
        before = state["step"]
        with self.assertRaises(ValueError):
            apply_answer(state, "not-a-date", BLOCKS, VARIETIES)
        self.assertEqual(state["step"], before)
        self.assertIn("Observation date", prompt(state, BLOCKS, VARIETIES, False))

    def test_main_wires_explicit_save_and_prediction_refresh(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "app" / "whatsapp_observations.py").read_text()
        wiring = (root / "app" / "main.py").read_text()
        self.assertIn("structured_submission_pending", source)
        self.assertIn("completed(active)", source)
        self.assertIn("save_quick_entry, save_kind", source)
        self.assertIn("request_harvest_refresh", source)
        self.assertIn("expire_pending_states()", source)
        self.assertIn('normalized not in {"save", "salva", "confirm", "conferma"}', source)
        self.assertIn("_continue_whatsapp_submission_flow", wiring)


if __name__ == "__main__":
    unittest.main()
