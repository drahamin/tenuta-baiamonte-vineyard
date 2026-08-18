from pathlib import Path
import unittest

from tests.source_helpers import frontend_source


ROOT = Path(__file__).resolve().parents[1]


class WhatsappAlertDeliveryTests(unittest.TestCase):
    def test_alerts_respect_the_conversation_window_and_record_receipts(self) -> None:
        intelligence = (ROOT / "app" / "intelligence.py").read_text(encoding="utf-8")
        self.assertIn("conversation_window_open", intelligence)
        self.assertIn("outside 24-hour window; approved operational-alert template required", intelligence)
        self.assertIn("accepted; awaiting receipt", intelligence)
        self.assertIn("event_metadata=metadata", intelligence)
        self.assertIn("template_parameters=[title[:200], message[:900]]", intelligence)

    def test_only_two_field_operational_templates_are_offered(self) -> None:
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        javascript = frontend_source(ROOT)
        self.assertIn("if variable_count == 2", source)
        self.assertIn("Proactive WhatsApp template", javascript)
        self.assertIn("alert title and details", javascript)

    def test_alert_template_fields_are_migrated_and_saved(self) -> None:
        migration = (ROOT / "db" / "migrations" / "031_whatsapp_alert_templates.sql").read_text(encoding="utf-8")
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("whatsapp_template_name", migration)
        self.assertIn("whatsapp_template_language", migration)
        self.assertIn("whatsapp_template_name=VALUES(whatsapp_template_name)", source)

    def test_agronomy_work_areas_are_compact_and_expandable(self) -> None:
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count('class="panel agronomy-panel'), 4)
        self.assertIn(".agronomy-panel>summary", css)
        self.assertIn("Harvest lot → tank", html)

    def test_tv_barrel_and_demijohn_have_distinct_physical_shapes(self) -> None:
        css = (ROOT / "app" / "static" / "display-extra.css").read_text(encoding="utf-8")
        self.assertIn("a horizontal oak barrel", css)
        self.assertIn("width:78px;height:54px", css)
        self.assertIn("narrow-necked glass demijohn", css)
        self.assertIn("clip-path:polygon(36% 0,64% 0", css)

    def test_every_supported_vessel_has_a_unique_dashboard_and_tv_shape(self) -> None:
        dashboard_css = (ROOT / "app" / "static" / "app.css").read_text(encoding="utf-8")
        tv_css = (ROOT / "app" / "static" / "display-extra.css").read_text(encoding="utf-8")
        vessel_types = ("tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other")
        for vessel in vessel_types:
            self.assertIn(f".tank-gauge.vessel-{vessel}", dashboard_css)
            self.assertIn(f".tv-tank-vessel.vessel-{vessel}", tv_css)
        for stage in ("fermenting", "aging", "settling", "transfer", "resting"):
            self.assertIn(f".stage-{stage}", dashboard_css)
            self.assertIn(f".stage-{stage}", tv_css)

    def test_other_vessels_do_not_fall_back_to_stainless_tanks(self) -> None:
        for filename in ("app.js", "display.js"):
            javascript = (ROOT / "app" / "static" / filename).read_text(encoding="utf-8")
            self.assertIn("if(/other|custom|unknown/.test(physical))return'other'", javascript)

    def test_tv_today_has_a_samsung_safe_area_and_compact_harvest_dates(self) -> None:
        css = (ROOT / "app" / "static" / "display-extra.css").read_text(encoding="utf-8")
        self.assertIn('Today-screen safe area for 1080p Samsung panels', css)
        self.assertIn('.today-tv-metrics .metric:nth-child(4) strong', css)
        self.assertIn('.screen[data-screen="0"].has-urgent .dashboard-grid{height:36.5vh}', css)


if __name__ == "__main__":
    unittest.main()
