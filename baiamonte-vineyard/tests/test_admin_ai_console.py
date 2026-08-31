import unittest
from pathlib import Path
from unittest.mock import patch

from app.domains import learning_monitor


ROOT = Path(__file__).resolve().parents[1]


class AdminAiConsoleTests(unittest.TestCase):
    def test_dedicated_ai_tab_contains_full_console(self):
        index = (ROOT / "app/static/index.html").read_text()
        script = (ROOT / "app/static/app.js").read_text() + (ROOT / "app/static/assets/operations-enhancements.js").read_text()
        self.assertIn('data-view="admin-ai"', index)
        self.assertIn('id="view-admin-ai"', index)
        self.assertIn('id="adminAiServiceLights"', index)
        self.assertIn('id="adminLearningModels"', index)
        self.assertIn("api/v1/admin/ai?_=${Date.now()}", script)

    def test_control_audit_is_six_rows_high_and_scrollable(self):
        css = (ROOT / "app/static/app.css").read_text()
        script = (ROOT / "app/static/app.js").read_text()
        self.assertIn("#adminProcessingLog{max-height:408px;overflow-y:auto", css)
        self.assertIn("rows.slice(0,100)", script)

    def test_one_failed_monitor_does_not_hide_other_models(self):
        healthy = {"code": "ok", "status": "validated"}
        with patch.object(learning_monitor, "_lab", return_value=healthy), \
             patch.object(learning_monitor, "_treatments", side_effect=RuntimeError("offline")), \
             patch.object(learning_monitor, "_harvest", return_value=healthy), \
             patch.object(learning_monitor, "_disease", return_value=healthy), \
             patch.object(learning_monitor, "_cistern", return_value=healthy), \
             patch.object(learning_monitor, "_vehicle_presence", return_value=healthy), \
             patch.object(learning_monitor, "_water_delivery", return_value=healthy), \
             patch.object(learning_monitor, "_advanced", return_value=healthy):
            result = learning_monitor.learning_monitor()
        self.assertEqual(len(result["models"]), 16)
        self.assertEqual(result["overall_status"], "attention")
        self.assertEqual(result["summary"]["unavailable"], 1)


if __name__ == "__main__":
    unittest.main()
