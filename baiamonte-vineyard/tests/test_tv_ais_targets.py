import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TvAisTargetTests(unittest.TestCase):
    def test_missing_iframe_identifiers_do_not_discard_scoped_ais_payload(self):
        script = (ROOT / "app" / "static" / "display.js").read_text(encoding="utf-8")

        self.assertIn("if(!identified.length||!visibleMmsi.size)return payload", script)
        self.assertNotIn("if(!list)return{...payload,vessels:[]}", script)
        self.assertIn("catch(_error){return payload}", script)


if __name__ == "__main__":
    unittest.main()
