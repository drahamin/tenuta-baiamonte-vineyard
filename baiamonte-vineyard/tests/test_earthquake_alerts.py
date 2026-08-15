from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EarthquakeAlertTests(unittest.TestCase):
    def test_seismic_feed_uses_national_ingv_service_and_normalizes_time(self) -> None:
        source = (ROOT / "app/etna.py").read_text()
        self.assertIn('INGV_EVENTS = "https://webservices.ingv.it/fdsnws/event/1/query"', source)
        self.assertIn('"minlatitude": 37.3', source)
        self.assertIn('"format": "geojson"', source)
        self.assertIn("datetime.fromtimestamp(event_time / 1000, timezone.utc).isoformat()", source)


    def test_etna_alert_job_has_nearby_earthquake_guardrails(self) -> None:
        source = (ROOT / "app/intelligence.py").read_text()
        self.assertIn('"etna-earthquake-" + event_id', source)
        self.assertIn("magnitude >= 3.0 and distance_km <= 50", source)
        self.assertIn("event_time < now - timedelta(hours=24)", source)

    def test_current_alerts_have_sirens_and_scrolling_text(self) -> None:
        app_html = (ROOT / "app/static/index.html").read_text()
        tv_html = (ROOT / "app/static/display.html").read_text()
        app_js = (ROOT / "app/static/app.js").read_text()
        tv_js = (ROOT / "app/static/display.js").read_text()
        self.assertIn('id="etnaTicker"', app_html)
        self.assertIn('id="tvEtnaTicker"', tv_html)
        self.assertIn("urgent-alert-ticker", app_js)
        self.assertIn("tv-urgent-ticker", tv_js)
        self.assertIn("SEISMIC ALERT", app_js)
        self.assertIn("SEISMIC ALERT", tv_js)

    def test_etna_alerts_resolve_when_official_condition_clears(self) -> None:
        source = (ROOT / "app/intelligence.py").read_text()
        self.assertIn("active_source_ids: set[str]", source)
        self.assertIn("status='resolved',resolved_at=NOW()", source)
        self.assertIn("source_id NOT IN", source)

    def test_tv_today_keeps_three_animated_findings_visible(self) -> None:
        display_data = (ROOT / "app/display_data.py").read_text()
        tv_js = (ROOT / "app/static/display.js").read_text()
        tv_css = (ROOT / "app/static/display-extra.css").read_text()
        self.assertIn("SELECT id,alert_type,severity,title,message,source_id,status,triggered_at,resolved_at FROM alerts", display_data)
        self.assertIn("alert_type='etna' AND triggered_at>=CURDATE()", display_data)
        self.assertIn("CASE WHEN alert_type='etna' AND triggered_at>=CURDATE() THEN 0 ELSE 1 END", display_data)
        self.assertIn("tvUrgentFindings.slice(0,3)", tv_js)
        self.assertIn("tv-urgent-rail", tv_js)
        self.assertNotIn("tvUrgentFindingTimer=setInterval", tv_js)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", tv_css)
        self.assertIn("RECENT EVENT", tv_js)
        self.assertIn("'TODAY'", tv_js)

    def test_tv_pressure_shows_lead_risk_action_and_progression(self) -> None:
        tv_js = (ROOT / "app/static/display.js").read_text()
        tv_css = (ROOT / "app/static/display-extra.css").read_text()
        self.assertIn("LEAD CURRENT RISK", tv_js)
        self.assertIn("suggested_action", tv_js)
        self.assertIn("Sebastian review pending", tv_js)
        self.assertIn("tv-pressure-grid", tv_css)
        self.assertIn("tv-pressure-roll.rising", tv_css)
        self.assertIn("urgent-earthquake", tv_css)
        self.assertIn("urgent-etna", tv_css)
