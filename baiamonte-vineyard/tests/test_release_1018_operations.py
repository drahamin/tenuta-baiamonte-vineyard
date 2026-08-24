from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Release1018OperationsTests(unittest.TestCase):
    def test_treatments_can_be_completed_with_audited_notes(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('/api/v1/treatments/{treatment_id}/complete', source)
        self.assertIn('This treatment is already complete', source)
        self.assertIn('Completion note', source)
        self.assertIn('openTreatmentCompletion', javascript)
        self.assertIn('Mark complete', javascript)

    def test_hourly_profile_controls_personal_clock_page(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"hourly_worker": hourly_worker', source)
        self.assertIn('track_hourly_labor', source)
        self.assertIn('node.hidden=!hourlyWorker', javascript)
        self.assertIn('worker&&hourlyWorker&&!write', javascript)

    def test_estate_roles_are_central_and_cellar_redraws_when_visible(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        roles = (ROOT / "app" / "domains" / "people_roles.py").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('ESTATE_ROLES = (', roles)
        self.assertIn('from .domains.people_roles import ESTATE_ROLES', source)
        self.assertIn('"estate_roles": list(ESTATE_ROLES)', source)
        self.assertIn("state.adminControl?.estate_roles", javascript)
        self.assertIn("if(view==='cellar')", javascript)
        self.assertIn("closest('details')?.addEventListener('toggle'", javascript)

    def test_camera_cache_refreshes_one_oldest_camera_per_run(self) -> None:
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        controls = (ROOT / "app" / "process_control.py").read_text(encoding="utf-8")
        display_server = (ROOT / "app" / "display_server.py").read_text(encoding="utf-8")
        display_javascript = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
        self.assertIn('def refresh_camera_snapshot_cache()', intelligence)
        self.assertIn('"strategy": "one_oldest_per_run"', intelligence)
        self.assertIn('"cameras": ("camera-snapshot-cache", refresh_camera_snapshot_cache)', intelligence)
        self.assertIn('"cameras": "Camera snapshot cache"', controls)
        self.assertIn('"cameras": 2', controls)
        self.assertIn('"interval_minutes": PROCESS_MINUTES["cameras"]', controls)
        self.assertIn('"deferred": True', intelligence)
        self.assertIn('retained last good image and deferred retry', intelligence)
        self.assertIn('http://127.0.0.1:8101/api/camera/', intelligence)
        self.assertIn('if entity_id in tv_entities:', intelligence)
        self.assertIn('"updated": bool(captured.get("fresh"))', intelligence)
        self.assertIn('"cache_state": "saved-fallback"', intelligence)
        self.assertIn('time.sleep(0.35)', intelligence)
        self.assertIn('CAMERA_CACHE_SECONDS = 5 * 60', display_server)
        self.assertIn('CAMERA_STALE_SECONDS = 30 * 60', display_server)
        self.assertIn('"X-Baiamonte-Camera": "scheduled-cache"', display_server)
        self.assertIn('cameraRefreshSeconds=Math.max(900,refreshSeconds)', display_javascript)
        self.assertIn("if(!image.dataset.objectUrl)image.src='assets/baiamonte-logo.png'", display_javascript)
        self.assertNotIn('http://homeassistant:8123/api', intelligence)
        self.assertNotIn('http://core-homeassistant:8123/api', intelligence)


if __name__ == "__main__":
    unittest.main()
