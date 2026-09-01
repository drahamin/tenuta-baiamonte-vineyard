import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app.domains.cistern_learning import cistern_volume_projection, predict_from_history, release_gate
from app.intelligence import (
    _capture_cistern_image,
    _capture_rtsp_frame,
    _cistern_camera_light,
    _cistern_event_image_entity,
    _start_cistern_camera_stream,
    current_cistern_camera_entity,
    visual_rtsp_source_health,
)


def reading(index: int, level: float, *, confidence: float = 0.9) -> dict:
    return {
        "id": str(index),
        "observed_at": datetime(2026, 1, 1) + timedelta(hours=index),
        "level_percent": level,
        "confidence": confidence,
    }


class CisternLearningTests(unittest.TestCase):
    def test_retired_cistern_camera_is_migrated_to_current_eufy_entity(self):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.192_168_0_54"})()
        self.assertEqual(current_cistern_camera_entity(settings), "camera.cisterna")

    def test_custom_cistern_camera_source_is_preserved(self):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.custom_cistern"})()
        self.assertEqual(current_cistern_camera_entity(settings), "camera.custom_cistern")

    @patch("app.intelligence.time.sleep")
    @patch("app.intelligence._ha_post")
    def test_cistern_light_uses_bridge_device_relationship(self, post, sleep):
        settings = type("Settings", (), {
            "cistern_camera_entity": "camera.cisterna",
            "cistern_camera_light_entity": "",
        })()
        states = [
            {"entity_id": "camera.cisterna", "state": "idle", "attributes": {"baiamonte_device_key": "T8442"}},
            {"entity_id": "switch.renamed_utility_lamp", "state": "off", "attributes": {"baiamonte_device_key": "T8442", "baiamonte_property": "light"}},
        ]
        self.assertEqual(_cistern_camera_light(settings, states), ("switch.renamed_utility_lamp", True))
        post.assert_called_once_with("/services/switch/turn_on", {"entity_id": "switch.renamed_utility_lamp"})
        sleep.assert_called_once_with(2.5)

    @patch("app.intelligence.time.sleep")
    @patch("app.intelligence._ha_post")
    def test_streaming_cistern_camera_is_woken_before_capture(self, post, sleep):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.cisterna"})()
        states = [{"entity_id": "camera.cisterna", "attributes": {"capabilities": {"streaming": True}}}]
        self.assertTrue(_start_cistern_camera_stream(settings, states))
        post.assert_called_once_with("/services/eufy_security/start_p2p_livestream", {"entity_id": "camera.cisterna"})
        sleep.assert_called_once_with(2.5)

    @patch("app.intelligence.time.sleep")
    @patch("app.intelligence._ha_post")
    def test_always_streaming_cistern_camera_is_not_restarted(self, post, sleep):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.cisterna"})()
        states = [
            {"entity_id": "camera.cisterna", "attributes": {"baiamonte_device_key": "T8442", "capabilities": {"streaming": True}}},
            {"entity_id": "sensor.renamed_stream_state", "state": "StreamStatus.STREAMING", "attributes": {"baiamonte_device_key": "T8442", "baiamonte_property": "stream_status"}},
        ]
        self.assertFalse(_start_cistern_camera_stream(settings, states))
        post.assert_not_called()
        sleep.assert_not_called()

    def test_cistern_event_image_uses_bridge_device_relationship(self):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.cisterna"})()
        states = [
            {"entity_id": "camera.cisterna", "attributes": {"baiamonte_device_key": "T8442"}},
            {"entity_id": "image.renamed_still", "attributes": {"baiamonte_device_key": "T8442", "baiamonte_property": "event_image"}},
            {"entity_id": "image.other_event_image", "attributes": {"baiamonte_device_key": "OTHER", "baiamonte_property": "event_image"}},
        ]
        self.assertEqual(_cistern_event_image_entity(settings, states), "image.renamed_still")

    @patch("app.intelligence._home_assistant_image", return_value=(b"still", "image/jpeg"))
    @patch("app.intelligence.time.sleep")
    @patch("app.intelligence._ha_post")
    def test_cistern_capture_prefers_generated_still_without_starting_stream(self, post, sleep, image):
        settings = type("Settings", (), {"cistern_camera_entity": "camera.cisterna"})()
        states = [
            {"entity_id": "camera.cisterna", "attributes": {"baiamonte_device_key": "T8442", "capabilities": {"streaming": True}}},
            {"entity_id": "image.cisterna_event_image", "attributes": {"baiamonte_device_key": "T8442", "baiamonte_property": "event_image"}},
        ]
        self.assertEqual(
            _capture_cistern_image(settings, states, "token"),
            (b"still", "image/jpeg", False, "image.cisterna_event_image"),
        )
        post.assert_called_once_with("/services/eufy_security/generate_image", {"entity_id": "camera.cisterna"})
        sleep.assert_called_once_with(4.0)
        image.assert_called_once_with("token", "image.cisterna_event_image", image_entity=True, timeout=25)

    @patch("app.intelligence._capture_rtsp_frame", return_value=(b"rtsp", "image/jpeg"))
    @patch("app.intelligence._ha_post")
    def test_cistern_capture_prefers_always_on_local_rtsp(self, post, rtsp):
        settings = type("Settings", (), {
            "cistern_camera_entity": "camera.cisterna",
            "cistern_rtsp_url": "rtsp://private-camera/live0",
        })()
        self.assertEqual(
            _capture_cistern_image(settings, [], "token"),
            (b"rtsp", "image/jpeg", False, "local_rtsp"),
        )
        rtsp.assert_called_once_with("rtsp://private-camera/live0")
        post.assert_not_called()

    @patch("app.intelligence.subprocess.run")
    def test_rtsp_capture_uses_bounded_tcp_frame_extraction(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = b"jpeg"
        self.assertEqual(_capture_rtsp_frame("rtsp://private/live", timeout=7), (b"jpeg", "image/jpeg"))
        command = run.call_args.args[0]
        self.assertIn("-rtsp_transport", command)
        self.assertIn("-timeout", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 4)

    @patch("app.intelligence.subprocess.run")
    def test_rtsp_capture_falls_back_to_udp(self, run):
        failed = type("Completed", (), {"returncode": 1, "stdout": b"", "stderr": b"unavailable"})()
        passed = type("Completed", (), {"returncode": 0, "stdout": b"jpeg", "stderr": b""})()
        run.side_effect = [failed, passed]
        self.assertEqual(_capture_rtsp_frame("rtsp://private/live"), (b"jpeg", "image/jpeg"))
        self.assertIn("tcp", run.call_args_list[0].args[0])
        self.assertIn("udp", run.call_args_list[1].args[0])

    @patch("app.intelligence.subprocess.run")
    def test_rtsp_authentication_error_is_sanitized(self, run):
        run.return_value.returncode = 8
        run.return_value.stdout = b""
        run.return_value.stderr = b"method DESCRIBE failed: 401 Unauthorized rtsp://user:secret@camera/live"
        with self.assertRaisesRegex(RuntimeError, "authentication was rejected") as raised:
            _capture_rtsp_frame("rtsp://user:secret@camera/live")
        self.assertNotIn("secret", str(raised.exception))

    @patch("app.intelligence._capture_rtsp_frame")
    @patch("app.intelligence.get_settings")
    def test_rtsp_health_never_returns_protected_urls(self, settings, capture):
        settings.return_value = type("Settings", (), {
            "cistern_rtsp_url": "rtsp://user:secret@camera/live0",
            "vineyard_north_rtsp_url": "",
        })()
        capture.return_value = (b"jpeg", "image/jpeg")
        result = visual_rtsp_source_health()
        self.assertTrue(result["sources"]["cistern"]["captured"])
        self.assertFalse(result["sources"]["vineyard_north"]["configured"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("rtsp://", str(result))

    @patch("app.intelligence.home_assistant_camera_snapshot")
    @patch("app.intelligence._capture_rtsp_frame")
    @patch("app.intelligence.get_settings")
    def test_vineyard_health_uses_fresh_home_assistant_fallback(self, settings, capture, snapshot):
        settings.return_value = type("Settings", (), {
            "cistern_rtsp_url": "",
            "vineyard_north_rtsp_url": "rtsp://user:secret@offline/live6",
        })()
        capture.side_effect = RuntimeError("Local RTSP frame is unavailable")
        snapshot.return_value = {
            "data": b"fresh-jpeg", "content_type": "image/jpeg", "fresh": True,
        }
        result = visual_rtsp_source_health()
        vineyard = result["sources"]["vineyard_north"]
        self.assertTrue(vineyard["captured"])
        self.assertEqual(vineyard["capture_source"], "home_assistant_proxy")
        self.assertNotIn("secret", str(result))

    @patch("app.intelligence.home_assistant_camera_snapshot")
    @patch("app.intelligence._capture_rtsp_frame")
    @patch("app.intelligence.get_settings")
    def test_vineyard_health_rejects_cached_fallback(self, settings, capture, snapshot):
        settings.return_value = type("Settings", (), {
            "cistern_rtsp_url": "",
            "vineyard_north_rtsp_url": "rtsp://user:secret@offline/live6",
        })()
        capture.side_effect = RuntimeError("Local RTSP frame is unavailable")
        snapshot.return_value = {
            "data": b"old-jpeg", "content_type": "image/jpeg", "fresh": False,
        }
        result = visual_rtsp_source_health()
        vineyard = result["sources"]["vineyard_north"]
        self.assertFalse(vineyard["captured"])
        self.assertIn("fallback unavailable", vineyard["detail"])

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

    @patch("app.domains.cistern_learning.fetch_all")
    def test_liters_use_confirmed_delivery_capacity_calibration(self, fetch_all):
        fetch_all.return_value = [{"implied_cistern_capacity_l": 20000, "delivery_volume_l": 5000}]
        result = cistern_volume_projection(50, 0.9)
        self.assertEqual(result["estimated_liters"], 10000)
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["reference_delivery_l"], 5000)

    @patch("app.domains.cistern_learning.fetch_all", return_value=[])
    def test_liters_are_not_invented_without_physical_delivery_calibration(self, _fetch_all):
        result = cistern_volume_projection(88, 0.9)
        self.assertIsNone(result["estimated_liters"])
        self.assertEqual(result["status"], "learning")

    def test_high_repeat_accuracy_does_not_pass_information_gate(self):
        score = {"cases": 363, "mae_points": 0.17, "within_five_points_pct": 99.7}
        live = {"cases": 20, "mae_points": 0, "within_five_points_pct": 100}
        quality = {"changed_observations": 1, "live_changed_observations": 0, "distinct_levels": 2, "live_unique_image_frames": 20}
        ready, issues = release_gate(score, live, quality)
        self.assertFalse(ready)
        self.assertTrue(any("stable repeats" in issue for issue in issues))

    def test_repeated_camera_frame_does_not_pass_information_gate(self):
        score = {"cases": 30, "mae_points": 1, "within_five_points_pct": 100}
        quality = {"changed_observations": 6, "live_changed_observations": 3, "distinct_levels": 4, "live_unique_image_frames": 1}
        ready, issues = release_gate(score, score, quality)
        self.assertFalse(ready)
        self.assertTrue(any("unique camera frames" in issue for issue in issues))

    def test_camera_agreement_cannot_claim_accuracy_without_physical_references(self):
        score = {"cases": 363, "mae_points": 0.2, "within_five_points_pct": 99.8}
        quality = {
            "changed_observations": 15,
            "live_changed_observations": 14,
            "distinct_levels": 14,
            "live_unique_image_frames": 51,
            "physical_reference_labels": 0,
        }
        ready, issues = release_gate(score, score, quality)
        self.assertFalse(ready)
        self.assertTrue(any("owner-verified physical level references" in issue for issue in issues))

    def test_cistern_prompt_uses_owner_confirmed_door_reference(self):
        source = (Path(__file__).parents[1] / "app/intelligence.py").read_text()
        self.assertIn("100% reference", source)
        self.assertIn("TOP INNER WALL LEDGE", source)
        self.assertIn("access door is immediately", source)
        self.assertIn("diagonal only because of perspective", source)
        self.assertIn("waterline_height_fraction", source)
        self.assertIn('parsed["calibration_reference"] = "cistern-door-full-v1"', source)


if __name__ == "__main__":
    unittest.main()
