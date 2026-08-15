from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


PATH = Path(__file__).parents[1] / "custom_components/baiamonte_branding/brander.py"
SPEC = spec_from_file_location("baiamonte_branding_test", PATH)
brander = module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = brander
SPEC.loader.exec_module(brander)

STOCK = '<html><head><title>Home Assistant</title><link rel="icon" href="/static/icons/favicon.ico"></head><body><div class="content"><div class="header"><img src="/static/icons/favicon-192x192.png" alt="Home Assistant"></div><ha-authorize></ha-authorize></div></body></html>'


def test_keeps_real_authorize_component_untouched():
    page = brander.render(STOCK)
    assert page.count("<ha-authorize></ha-authorize>") == 1
    assert "baiamonte-login-card" in page
    assert "Tenuta Baiamonte" in page
    assert "no-store, no-cache, must-revalidate" in page
    assert brander.render(page) == page


def test_rejects_an_unknown_vendor_layout():
    try:
        brander.render("<html><head><title>Changed</title></head></html>")
    except brander.BrandingError as error:
        assert "stock was preserved" in str(error)
    else:
        raise AssertionError("unknown layout was not rejected")
