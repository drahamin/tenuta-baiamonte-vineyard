import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from app import intelligence
from app.domains import fox_watch


ROOT = Path(__file__).resolve().parents[1]


class FoxWatchTests(unittest.TestCase):
    def test_west_etna_pet_event_is_selected_without_other_cameras(self):
        payload = {"cameras": [
            {"entity_id": "camera.west_etna_view", "name": "West Etna View", "event_image_available": True,
             "event_image_entity_id": "image.west_etna_view_camera", "detections": {"pet": {"active": True, "last_changed": "2026-08-31T01:00:00Z"}}},
            {"entity_id": "camera.rear_gate", "name": "Rear Gate", "event_image_available": True,
             "event_image_entity_id": "image.rear_gate_camera", "detections": {"pet": {"active": True, "last_changed": "2026-08-31T01:00:00Z"}}},
        ]}
        result = intelligence._wildlife_event_triggers(payload)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["camera_entity_id"], "camera.west_etna_view")
        self.assertEqual(result[0]["event_types"], ["pet"])

    @patch.object(fox_watch, "fox_watch_summary")
    def test_monthly_ivr_update_is_cute_and_evidence_based(self, summary):
        summary.return_value = {
            "month_sightings": 2,
            "latest": {"observed_at": datetime(2026, 8, 31, 1, 15), "activity": "sniffing", "grape_risk": "low"},
        }
        message = fox_watch.monthly_fox_update(False)
        self.assertIn("🦊 Fox update", message)
        self.assertIn("2 confirmed sightings", message)
        self.assertIn("sniffing", message)
        self.assertIn("watching the bunches", message)

    def test_release_contains_durable_fox_pipeline_and_dashboard(self):
        migration = (ROOT / "db/migrations/136_fox_wildlife_watch.sql").read_text()
        camera = (ROOT / "app/static/assets/cameras.js").read_text()
        assistant = (ROOT / "app/domains/communications_whatsapp_assistant.py").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS wildlife_observations", migration)
        self.assertIn("renderFoxWatch", camera)
        self.assertIn("latest_fox_media", assistant)


if __name__ == "__main__":
    unittest.main()
