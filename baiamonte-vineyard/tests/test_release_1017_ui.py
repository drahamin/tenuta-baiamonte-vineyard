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
        self.assertIn("if($('view-blocks')?.classList.contains('active'))renderEstateMap()", javascript)
        self.assertIn("new ResizeObserver(refreshEstateMapSize)", javascript)
        self.assertIn("window.addEventListener('orientationchange'", javascript)
        self.assertIn("invalidateSize({pan:false,animate:false})", javascript)

    def test_atlas_failure_cannot_blank_alert_settings(self) -> None:
        javascript = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function renderSafely(section,callback)", javascript)
        self.assertIn("renderSafely('atlas',renderBlocks)", javascript)
        self.assertIn("renderSafely('alert settings',renderAlertSettings)", javascript)
        self.assertIn("view==='alert-settings'", javascript)


if __name__ == "__main__":
    unittest.main()
