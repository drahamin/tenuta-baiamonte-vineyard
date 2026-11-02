import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from launcher import main, prepare_login_assets


class LauncherTest(unittest.TestCase):
    def test_valid_assets_are_canonical_private_and_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = ["/static/icons/test.png", "/frontend_latest/test.js"]
            prepare_login_assets({"login_assets": assets + assets}, root)
            result = root / "login-assets.json"
            self.assertEqual(json.loads(result.read_text()), sorted(assets))
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(root.glob(".login-assets-*")), [])

    def test_invalid_option_cannot_use_a_stale_asset_file_or_start(self):
        invalid = [None, [], "abc", {}, [None], [123],
                   ["/local/secret"], ["/static/../secret"],
                   ["/static/" + "a" * 250], ["/static/a"] * 513]
        for assets in invalid:
            with self.subTest(assets_type=type(assets).__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / "login-assets.json").write_text('["/static/stale.js"]')
                    (root / "options.json").write_text(json.dumps({
                        "enabled": True, "tunnel_token": "fixture" * 20,
                        "login_assets": assets,
                    }))
                    with patch("launcher.subprocess.Popen") as process:
                        self.assertEqual(main(root), 1)
                        process.assert_not_called()
                    self.assertFalse((root / ".tunnel-token").exists())

    def test_disabled_start_does_not_materialize_assets_or_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "options.json").write_text(json.dumps({
                "enabled": False, "tunnel_token": "fixture" * 20,
                "login_assets": ["/static/test.js"],
            }))
            with patch("launcher.subprocess.Popen") as process:
                self.assertEqual(main(root), 0)
                process.assert_not_called()
            self.assertEqual([p.name for p in root.iterdir()], ["options.json"])


if __name__ == "__main__":
    unittest.main()
