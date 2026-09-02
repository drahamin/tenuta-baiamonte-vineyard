from pathlib import Path

import pytest

from app.wine_conversion import wine_mass_kg, yield_disclosure


ROOT = Path(__file__).resolve().parents[1]


def test_red_wine_yield_disclosure_is_directional_and_transparent():
    detail = yield_disclosure(0.70, "Current vintage configured planning yield")
    assert detail["factor_l_per_kg"] == 0.70
    assert detail["inverse_kg_grapes_per_l"] == pytest.approx(1.428571)
    assert detail["typical_min_l_per_kg"] == 0.67
    assert detail["typical_max_l_per_kg"] == 0.70
    assert detail["is_estimate"] is True
    assert "grape kg" in detail["formula"]
    assert "not a litre-to-kilogram mass conversion" in detail["mass_warning"]


def test_actual_wine_mass_requires_measured_density():
    assert wine_mass_kg(100, None) is None
    assert wine_mass_kg(100, 0) is None
    assert wine_mass_kg(100, 0.995) == pytest.approx(99.5)


def test_conversion_disclosure_is_visible_where_projected_outputs_are_shown():
    harvest = (ROOT / "app/static/assets/harvest.js").read_text()
    display = (ROOT / "app/static/display.js").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    app_js = (ROOT / "app/static/app.js").read_text()
    assert "1 kg grapes ×" in harvest
    assert "actual measured volume replaces estimate" in harvest
    assert "wine_yield_conversion" in display
    assert "Actual harvest and cellar volume replace estimates" in display
    assert "Typical red wine: 0.67–0.70 L/kg" in html
    assert "Typical red wine: 0.67–0.70 L/kg" in app_js
