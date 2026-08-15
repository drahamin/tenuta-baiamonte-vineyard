import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseOneStabilityTests(unittest.TestCase):
    def test_home_assistant_inventory_uses_proxy_and_short_cache(self):
        source = (ROOT / "app" / "display_data.py").read_text()
        self.assertIn('_HA_CACHE_SECONDS = 10', source)
        self.assertIn('def _home_assistant_display_data(force: bool = False)', source)
        self.assertIn('for url in ("http://supervisor/core/api/states",):', source)
        self.assertNotIn('"http://homeassistant:8123/api/states"', source)
        self.assertNotIn('"http://core-homeassistant:8123/api/states"', source)

    def test_tv_pressure_grid_is_height_bounded(self):
        css = (ROOT / "app" / "static" / "display-extra.css").read_text()
        self.assertIn('.intelligence-grid #tvPressure{display:flex;min-height:0;flex:1', css)
        self.assertIn('grid-template-rows:repeat(2,minmax(0,1fr))', css)
        self.assertIn('.intelligence-grid .tv-pressure-roll{height:auto', css)

    def test_live_alerts_reuse_one_record_and_resolve_when_clear(self):
        source = (ROOT / "app" / "intelligence.py").read_text()
        self.assertIn('def upsert_condition_alert(', source)
        self.assertIn('def resolve_condition_alert(', source)
        self.assertIn('"cistern:low"', source)
        self.assertIn('"system:integration-failures"', source)
        self.assertIn('"cistern-camera-unavailable"', source)

    def test_whatsapp_health_check_retries_one_transient_failure(self):
        source = (ROOT / "app" / "intelligence.py").read_text()
        self.assertIn('for attempt in range(2):', source)
        self.assertIn('time.sleep(2)', source)

    def test_baiamonte_login_bypasses_stale_compressed_frontend_bundles(self):
        source = (ROOT / "custom_components" / "baiamonte_branding" / "brander.py").read_text()
        self.assertIn('FRESH_LOGIN_NAME = "baiamonte-login-20260815-v2.html"', source)
        self.assertIn('LATEST_ENTRY_NAME = "baiamonte-core-latest-20260815-v2.js"', source)
        self.assertIn('LEGACY_ENTRY_NAME = "baiamonte-core-legacy-20260815-v2.js"', source)
        self.assertIn('versioned_core_url = f"/local/{LATEST_ENTRY_NAME}"', source)
        self.assertIn('versioned_legacy_url = f"/local/{LEGACY_ENTRY_NAME}"', source)

    def test_tv_alerts_rotate_by_type_at_a_readable_speed(self):
        script = (ROOT / "app" / "static" / "display.js").read_text()
        css = (ROOT / "app" / "static" / "display-extra.css").read_text()
        self.assertIn("grouped=new Map", script)
        self.assertIn("tvUrgentRotationIndex%rows.length", script)
        self.assertIn("Math.max(45", script)
        self.assertIn("--tv-alert-ticker-seconds", css)


if __name__ == "__main__":
    unittest.main()
