from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TvAisDisplayTests(unittest.TestCase):
    def test_tv_has_bounded_stale_aware_vessel_fallback(self) -> None:
        html = (ROOT / "app" / "static" / "display.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")
        css = (ROOT / "app" / "static" / "display-extra.css").read_text(encoding="utf-8")
        self.assertIn('id="aisTrafficMap"', html)
        self.assertIn('id="aisMapNotice"', html)
        self.assertIn('timeout_minutes', javascript)
        self.assertIn('AIS positions are stale', javascript)
        self.assertIn('AIS data stale', javascript)
        self.assertIn("slice(0,isAircraft?160:80)", javascript)
        self.assertIn('trafficMap(kind,payload)', javascript)
        self.assertIn('.traffic-fallback-layer', css)
        self.assertIn('.traffic-marker.stale', css)


if __name__ == "__main__":
    unittest.main()
