import unittest
from datetime import datetime, timedelta

from app.domains.cistern_learning import predict_from_history, release_gate


def reading(index: int, level: float, *, confidence: float = 0.9) -> dict:
    return {
        "id": str(index),
        "observed_at": datetime(2026, 1, 1) + timedelta(hours=index),
        "level_percent": level,
        "confidence": confidence,
    }


class CisternLearningTests(unittest.TestCase):
    def test_prediction_uses_only_evidence_before_target(self):
        history = [reading(0, 50), reading(1, 49.5), reading(2, 49)]
        target = datetime(2026, 1, 1, 3)
        first = predict_from_history(history, target)
        # A future observation must not alter an earlier walk-forward prediction.
        second = predict_from_history(history + [reading(9, 99)], target)
        self.assertEqual(first, second)
        self.assertEqual(first["prior_observation_count"], 3)
        self.assertLess(first["predicted_level_percent"], 49)
        self.assertLess(first["evidence_through"], target)

    def test_low_confidence_evidence_is_not_used(self):
        prediction = predict_from_history([reading(0, 40), reading(1, 5, confidence=0.2)], datetime(2026, 1, 1, 2))
        self.assertEqual(prediction["predicted_level_percent"], 40)
        self.assertEqual(prediction["prior_observation_count"], 1)

    def test_release_requires_new_live_evidence_even_with_strong_history(self):
        historical = {"cases": 100, "mae_points": 0.5, "within_five_points_pct": 100}
        ready, issues = release_gate(historical, {"cases": 0, "mae_points": None, "within_five_points_pct": None})
        self.assertFalse(ready)
        self.assertTrue(any("new forward/live" in issue for issue in issues))

    def test_release_gate_accepts_both_good_scores(self):
        score = {"cases": 30, "mae_points": 2.0, "within_five_points_pct": 95}
        live = {"cases": 12, "mae_points": 2.5, "within_five_points_pct": 91}
        self.assertEqual(release_gate(score, live), (True, []))

    def test_high_repeat_accuracy_does_not_pass_information_gate(self):
        score = {"cases": 363, "mae_points": 0.17, "within_five_points_pct": 99.7}
        live = {"cases": 20, "mae_points": 0, "within_five_points_pct": 100}
        quality = {"changed_observations": 1, "live_changed_observations": 0, "distinct_levels": 2}
        ready, issues = release_gate(score, live, quality)
        self.assertFalse(ready)
        self.assertTrue(any("stable repeats" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
