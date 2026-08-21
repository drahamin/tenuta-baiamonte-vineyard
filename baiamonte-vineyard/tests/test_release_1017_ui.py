from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Release1017UiTests(unittest.TestCase):
    def test_treatments_separate_forecast_completed_and_inactive(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="treatmentPlannedList"', html)
        self.assertIn('id="treatmentCompletedList"', html)
        self.assertIn("completedStatuses", javascript)
        self.assertIn("inactiveStatuses", javascript)
        self.assertIn("excluded from the forecast", javascript)

    def test_tv_camera_selector_and_etna_svg_are_present(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        display = (ROOT / "app" / "static" / "display.html").read_text(encoding="utf-8")
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('id="tvCameraSelector"', html)
        self.assertIn('id="tvCameraSearch"', html)
        self.assertIn('"available_cameras": home_assistant_manager_camera_catalog()', source)
        self.assertIn('class="tv-etna-volcano"', display)
        self.assertIn('<svg viewBox="0 0 160 120"', display)

    def test_today_cistern_card_opens_latest_snapshot(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="cisternMetric"', html)
        self.assertIn('openCisternSnapshot', javascript)
        self.assertIn('api/v1/cistern/snapshot', javascript)

    def test_mobile_atlas_map_reflows_after_becoming_visible(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function refreshEstateMapSize()", javascript)
        self.assertIn("view==='blocks'", javascript)
        self.assertIn(".setView(estateCenter,18)", javascript)
        self.assertIn("estateLeafletMap?refreshEstateMapSize():renderEstateMap()", javascript)
        self.assertIn("new ResizeObserver(refreshEstateMapSize)", javascript)
        self.assertIn("window.addEventListener('orientationchange'", javascript)
        self.assertIn("invalidateSize({pan:false,animate:false})", javascript)
        self.assertIn("currentEstateMapSignature", javascript)
        self.assertIn("estateMapDataSignature!==currentEstateMapSignature()", javascript)
        self.assertIn("{renderEstateMap();return}", javascript)

    def test_atlas_view_and_layers_persist_without_refresh_jumps(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("baiamonte-estate-map-view-v1", javascript)
        self.assertIn("function readEstateMapPreferences()", javascript)
        self.assertIn("function writeEstateMapPreferences(map,baseLayers,overlays)", javascript)
        self.assertIn("savedView?.center||estateCenter", javascript)
        self.assertIn("if(!savedView)fitLand()", javascript)
        self.assertIn("baselayerchange overlayadd overlayremove", javascript)

    def test_verified_atlas_geometry_is_map_anchored_and_always_visible(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("map.createPane('verifiedLandPane')", javascript)
        self.assertIn("window.L.canvas({pane:'verifiedLandPane'", javascript)
        self.assertIn("name==='Verified parcels & blocks'", javascript)
        self.assertIn("map.on('move zoom viewreset resize',redrawVerifiedLand)", javascript)

    def test_treatment_water_control_does_not_repeat_sprayer_name(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        control = javascript[javascript.index("function treatmentWaterControl"):javascript.index("function renderTreatments")]
        self.assertNotIn("sprayerName", control)
        self.assertIn("Recalculate recipe", control)
        self.assertIn("Total carrier volume", control)

    def test_atlas_failure_cannot_blank_alert_settings(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function renderSafely(section,callback)", javascript)
        self.assertIn("renderSafely('atlas',renderBlocks)", javascript)
        self.assertIn("renderSafely('alert settings',renderAlertSettings)", javascript)
        self.assertIn("view==='alert-settings'", javascript)

    def test_treatments_redraw_independently_when_opened(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("renderSafely('treatments',renderTreatments)", javascript)
        self.assertIn("view==='treatments'", javascript)

    def test_tv_admin_uses_compact_collapsible_groups(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count('class="panel tv-config-section"'), 3)
        self.assertIn("Maps & traffic", html)
        self.assertIn("Service addresses", html)
        self.assertIn(".tv-config-section>summary", css)
        self.assertIn(".tv-config-actions{position:sticky", css)


if __name__ == "__main__":
    unittest.main()
