import unittest
from pathlib import Path
from unittest.mock import patch

from app.domains import advanced_learning


ROOT = Path(__file__).resolve().parents[1]


class AdvancedLearningTests(unittest.TestCase):
    def test_all_requested_processes_have_versioned_manifests(self):
        self.assertEqual(
            set(advanced_learning.MODEL_VERSIONS),
            {
                "disease_onset", "treatment_effectiveness", "product_duration",
                "resistance_rotation", "young_vine_nutrition", "data_quality",
                "block_disease_calibration", "spray_window",
            },
        )

    def test_recent_pressure_slope_is_directional(self):
        self.assertAlmostEqual(advanced_learning._slope([10, 12, 14, 16]), 2.0)
        self.assertAlmostEqual(advanced_learning._slope([16, 14, 12, 10]), -2.0)
        self.assertIsNone(advanced_learning._slope([10, 11]))

    def test_rotation_review_blocks_consecutive_frac_repeat(self):
        model = {"resistance_rotation": {"model_version": "rotation-test", "parameters_snapshot": {"last_groups": ["M01", "3"]}}}
        with patch.object(advanced_learning, "advanced_learning_statuses", return_value=model):
            result = advanced_learning.resistance_rotation_review(["M01", "7"])
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["repeated_groups"], ["M01"])

    def test_schema_contains_forecasts_quality_findings_and_manifests(self):
        migration = (ROOT / "db/migrations/123_advanced_operational_learning.sql").read_text()
        self.assertIn("advanced_learning_models", migration)
        self.assertIn("disease_onset_forecasts", migration)
        self.assertIn("learned_data_quality_findings", migration)


if __name__ == "__main__":
    unittest.main()
