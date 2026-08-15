from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import unittest


PATH = Path(__file__).parents[1] / "custom_components/baiamonte_branding/brander.py"
SPEC = spec_from_file_location("baiamonte_branding_test", PATH)
brander = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = brander
SPEC.loader.exec_module(brander)

STOCK = '<html><head><title>Home Assistant</title><link rel="icon" href="/static/icons/favicon.ico"></head><body><div class="content"><div class="header"><img src="/static/icons/favicon-192x192.png" alt="Home Assistant"></div><ha-authorize></ha-authorize></div></body></html>'


class LoginBrandingTests(unittest.TestCase):
    def test_keeps_real_authorize_component_untouched(self):
        page = brander.render(STOCK)
        self.assertEqual(page.count("<ha-authorize></ha-authorize>"), 1)
        self.assertIn("baiamonte-login-card", page)
        self.assertIn("Tenuta Baiamonte", page)
        self.assertIn("no-store, no-cache, must-revalidate", page)
        self.assertIn("--ha-card-background: transparent", page)
        self.assertIn("#d2ad4f", page)
        self.assertIn('font-family: Georgia, "Times New Roman", serif', page)
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
