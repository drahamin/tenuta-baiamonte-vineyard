import pathlib
import unittest

from app.whatsapp_observations import (
    PHENOLOGY_STAGES,
    apply_answer,
    completed,
    new_state,
    other_submission_choice,
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

    def test_menu_exposes_three_complete_field_forms(self):
        menu = submission_menu(False)
        self.assertIn("1 Field scouting", menu)
        self.assertIn("2 Phenology", menu)
        self.assertIn("3 Fruit maturity", menu)
        self.assertEqual(submission_choice("1"), "scouting")
        self.assertEqual(submission_choice("fenologia"), "phenology")
        self.assertEqual(submission_choice("fruit maturity"), "maturity_sample")
        self.assertEqual(other_submission_choice("8"), "treatment")

    def test_scouting_collects_required_and_review_fields(self):
        values = self._complete(
            "scouting",
            ["1", "2026-08-20 09:30", "Downy mildew", "2", "12", "lower rows", "YES", "photo to follow"],
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
            ["1", "1", "2026-08-20 10:00", "100", "1.5", "21.4", "3.25", "6.8", "145", "24", "2", "Healthy", "4", "2026-09-20", "Sebastiano", "SKIP"],
        )
        self.assertEqual(values["variety_id"], "variety-1")
        self.assertEqual(values["brix"], 21.4)
        self.assertEqual(values["yan_mg_l"], 145)
        self.assertEqual(values["decision"], "ready")
        self.assertNotIn("approved", values)

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
        self.assertIn("save_quick_entry, kind", source)
        self.assertIn("request_harvest_refresh", source)
        self.assertIn('normalized not in {"save", "salva", "confirm", "conferma"}', source)
        self.assertIn("_continue_whatsapp_submission_flow", wiring)


if __name__ == "__main__":
    unittest.main()
