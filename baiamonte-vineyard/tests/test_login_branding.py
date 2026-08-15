from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import tempfile
import unittest


PATH = Path(__file__).parents[1] / "custom_components/baiamonte_branding/brander.py"
INTEGRATION = PATH.parent
SPEC = spec_from_file_location("baiamonte_branding_test", PATH)
brander = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = brander
SPEC.loader.exec_module(brander)

STOCK = '<html><head><title>Home Assistant</title><link rel="icon" href="/static/icons/favicon.ico"></head><body><div class="content"><div class="header"><img src="/static/icons/favicon-192x192.png" alt="Home Assistant"></div><ha-authorize></ha-authorize></div></body></html>'


class LoginBrandingTests(unittest.TestCase):
    def test_integration_detail_has_local_brand_artwork(self):
        self.assertTrue((INTEGRATION / "brand" / "icon.png").is_file())
        self.assertTrue((INTEGRATION / "brand" / "logo.png").is_file())

    def test_keeps_real_authorize_component_untouched(self):
        page = brander.render(STOCK)
        self.assertEqual(page.count("<ha-authorize></ha-authorize>"), 1)
        self.assertIn("baiamonte-login-card", page)
        self.assertIn("Tenuta Baiamonte", page)
        self.assertIn("no-store, no-cache, must-revalidate", page)
        self.assertIn("--ha-card-background: transparent", page)
        self.assertIn("#d2ad4f", page)
        self.assertIn('font-family: Georgia, "Times New Roman", serif', page)
        self.assertIn(f"logon-logo.png?v={brander.ASSET_VERSION}", page)
        self.assertEqual(brander.render(page), page)

    def test_rejects_an_unknown_vendor_layout(self):
        with self.assertRaises(brander.BrandingError) as context:
            brander.render("<html><head><title>Changed</title></head></html>")
        self.assertIn("stock was preserved", str(context.exception))

    def test_existing_branding_style_is_upgraded_in_place(self):
        previous = brander.render(STOCK).replace("#d2ad4f", "#00aabb")
        upgraded = brander.render(previous)
        self.assertNotIn("#00aabb", upgraded)
        self.assertIn("#d2ad4f", upgraded)
        self.assertEqual(upgraded.count("<ha-authorize></ha-authorize>"), 1)

    def test_browser_is_branded_without_replacing_native_frontend_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            frontend = root / "frontend"
            assets = config / "www" / "baiamonte-branding"
            assets.mkdir(parents=True)
            (assets / "logon-logo.png").write_bytes(b"logo")
            (assets / "favicon.png").write_bytes(b"icon")
            (frontend / "frontend_latest").mkdir(parents=True)
            (frontend / "frontend_es5").mkdir(parents=True)
            (frontend / "authorize.html").write_text(STOCK, encoding="utf-8")
            (frontend / "index.html").write_text(
                '<script src="/frontend_latest/core.abc123.js"></script>'
                '<link rel="modulepreload" href="/frontend_latest/core.abc123.js">'
                '<script nomodule src="/frontend_es5/core.def456.js"></script>',
                encoding="utf-8",
            )
            stock_bundle = 'const login="/auth/authorize?response_type=code";'
            (frontend / "frontend_latest" / "core.abc123.js").write_text(
                stock_bundle, encoding="utf-8"
            )
            (frontend / "frontend_es5" / "core.def456.js").write_text(
                stock_bundle, encoding="utf-8"
            )

            first = brander.apply_branding(config, frontend)
            second = brander.apply_branding(config, frontend)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIn(
                "/auth/authorize?response_type=code",
                (frontend / "frontend_latest" / "core.abc123.js").read_text(),
            )
            self.assertIn(
                "/auth/authorize?response_type=code",
                (frontend / "frontend_es5" / "core.def456.js").read_text(),
            )
            self.assertIn(
                f"/frontend_latest/core.abc123.js?{brander.ENTRY_VERSION}",
                (frontend / "index.html").read_text(),
            )
            self.assertIn(
                f"/frontend_es5/core.def456.js?{brander.ENTRY_VERSION}",
                (frontend / "index.html").read_text(),
            )
            fresh = config / "www" / brander.FRESH_LOGIN_NAME
            self.assertIn("Tenuta Baiamonte", fresh.read_text())

            previous_login = "/local/baiamonte-login-20260815-v3.html?response_type=code"
            for bundle in (
                frontend / "frontend_latest" / "core.abc123.js",
                frontend / "frontend_es5" / "core.def456.js",
            ):
                bundle.write_text(bundle.read_text().replace(
                    "/auth/authorize?response_type=code", previous_login
                ))
            old_index = (frontend / "index.html").read_text()
            old_index = old_index.replace(
                f"/frontend_latest/core.abc123.js?{brander.ENTRY_VERSION}",
                "/local/baiamonte-core-latest-20260815-v3.js",
            )
            old_index = old_index.replace(
                f"/frontend_es5/core.def456.js?{brander.ENTRY_VERSION}",
                "/local/baiamonte-core-legacy-20260815-v3.js",
            )
            (frontend / "index.html").write_text(old_index)
            old_authorize = (frontend / "authorize.html").read_text().replace(
                brander.ASSET_VERSION, "20260815-2"
            )
            (frontend / "authorize.html").write_text(old_authorize)

            upgraded = brander.apply_branding(config, frontend)
            upgraded_index = (frontend / "index.html").read_text()
            upgraded_authorize = (frontend / "authorize.html").read_text()

            self.assertTrue(upgraded.changed)
            self.assertIn(
                f"/frontend_latest/core.abc123.js?{brander.ENTRY_VERSION}", upgraded_index
            )
            self.assertIn(
                f"/frontend_es5/core.def456.js?{brander.ENTRY_VERSION}", upgraded_index
            )
            self.assertNotIn("/local/baiamonte-core-", upgraded_index)
            for bundle in (
                frontend / "frontend_latest" / "core.abc123.js",
                frontend / "frontend_es5" / "core.def456.js",
            ):
                self.assertIn("/auth/authorize?response_type=code", bundle.read_text())
                self.assertNotIn("/local/baiamonte-login-", bundle.read_text())
            self.assertIn(f"logon-logo.png?v={brander.ASSET_VERSION}", upgraded_authorize)
            self.assertIn(f"favicon.png?v={brander.ASSET_VERSION}", upgraded_authorize)
