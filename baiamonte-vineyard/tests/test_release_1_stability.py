import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseOneStabilityTests(unittest.TestCase):
    def test_home_assistant_inventory_uses_proxy_and_short_cache(self):
        source = (ROOT / "app" / "display_data.py").read_text()
        self.assertIn('_HA_CACHE_SECONDS = 30', source)
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
        self.assertIn('def resolve_inactive_condition_alerts(', source)
        self.assertIn('"cistern:low"', source)
        self.assertIn('"system:integration-failures"', source)
        self.assertIn('"cistern-camera-unavailable"', source)
        self.assertIn('source_id = f"{alert_type}:{tank_key}"', source)
        self.assertIn('source_id = f"pressure:{item[\'disease_code\']}"', source)
        self.assertNotIn('f"{alert_type}:{today}:{tank_key}"', source)
        self.assertNotIn('f"pressure:{now.date()}:{item[\'disease_code\']}"', source)

    def test_condition_resolution_clears_home_assistant_notifications(self):
        source = (ROOT / "app" / "intelligence.py").read_text()
        helper = source[source.index('def resolve_inactive_condition_alerts('):source.index('def resolve_expired_condition_alerts(')]
        self.assertIn("status='resolved',resolved_at=NOW()", helper)
        self.assertIn('_dismiss_ha_alert_notification(alert_type, row.get("source_id"))', helper)
        self.assertIn('resolve_condition_alert("ai_service")', source)

    def test_whatsapp_health_check_retries_one_transient_failure(self):
        source = (ROOT / "app" / "intelligence.py").read_text()
        self.assertIn('for attempt in range(2):', source)
        self.assertIn('time.sleep(2)', source)

    def test_baiamonte_login_preserves_native_frontend_paths(self):
        source = (ROOT / "custom_components" / "baiamonte_branding" / "brander.py").read_text()
        self.assertIn('FRESH_LOGIN_NAME = "baiamonte-login-20260815-v4.html"', source)
        self.assertIn('ENTRY_VERSION = "baiamonte-native-20260815-v4"', source)
        self.assertIn("def _restore_native_entry_flow", source)
        self.assertIn("previous_core_url", source)
        self.assertIn("previous_legacy_url", source)
        self.assertIn('versioned_core_url = f"{core_url}?{ENTRY_VERSION}"', source)
        self.assertIn('versioned_legacy_url = f"{legacy_url}?{ENTRY_VERSION}"', source)
        self.assertNotIn('versioned_core_url = f"/local/', source)

    def test_tv_alerts_rotate_by_type_at_a_readable_speed(self):
        script = (ROOT / "app" / "static" / "display.js").read_text()
        css = (ROOT / "app" / "static" / "display-extra.css").read_text()
        self.assertIn("grouped=new Map", script)
        self.assertIn("tvUrgentRotationIndex%rows.length", script)
        self.assertIn("Math.max(45", script)
        self.assertIn("--tv-alert-ticker-seconds", css)

    def test_operations_weather_surfaces_full_station_context(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        script = (ROOT / "app" / "static" / "app.js").read_text()
        effects = (ROOT / "app" / "static" / "weather-effects.js").read_text()
        self.assertIn('id="currentCondition"', html)
        self.assertIn('id="weatherFreshness"', html)
        self.assertIn('id="currentWind"', html)
        self.assertIn('id="currentSoil"', html)
        self.assertIn('id="currentUv"', html)
        self.assertIn("function derived", effects)
        self.assertIn("['Dew point'", script)
        self.assertIn("['VPD'", script)
        self.assertIn("todayWeatherAdvice", script)

    def test_database_is_only_operational_authority(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        backend = (ROOT / "app" / "main.py").read_text()
        self.assertNotIn('id="weatherImportForm"', html)
        self.assertNotIn("Google Drive CSV", html)
        self.assertNotIn('/api/v1/weather/import-history', backend)
        self.assertNotIn('import_baiamonte_weather_csv', backend)
        self.assertIn("No workbook or uploaded file is authoritative", html)
        for name in ("import_workbook.py", "import_finance_workbooks.py", "import_legacy_costs.py"):
            source = (ROOT / "scripts" / name).read_text()
            self.assertIn("parser.error", source)
            self.assertIn("access is retired", source)


if __name__ == "__main__":
    unittest.main()
