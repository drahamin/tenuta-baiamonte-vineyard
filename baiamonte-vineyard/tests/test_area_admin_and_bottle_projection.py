from datetime import date
from pathlib import Path

from app.domains import bottling


ROOT = Path(__file__).resolve().parents[1]


def test_current_vintage_uses_projection_while_cellar_output_remains(monkeypatch):
    monkeypatch.setattr(bottling, "_projected_bottle_equivalents", lambda _year: (3404, "Working forecast"))
    basis = bottling._bottle_quantity_basis(
        date.today().year,
        [],
        [{"volume_l": 225}],
        [{"id": "partial", "bottles_produced": 300, "bottle_size_ml": 750}],
    )
    assert basis["planned_bottles"] == 3404
    assert basis["bottle_quantity_source"] == "current_vintage_projection"
    assert basis["bottle_quantity_is_projection"] is True
    assert basis["actual_bottle_equivalents"] == 300


def test_current_vintage_switches_to_completed_output_when_no_wine_remains(monkeypatch):
    monkeypatch.setattr(bottling, "_projected_bottle_equivalents", lambda _year: (3404, "Working forecast"))
    basis = bottling._bottle_quantity_basis(
        date.today().year,
        [],
        [],
        [{"id": "complete", "bottles_produced": 3250, "bottle_size_ml": 750}],
    )
    assert basis["planned_bottles"] == 3250
    assert basis["bottle_quantity_source"] == "actual_bottled_output"
    assert basis["bottle_quantity_is_projection"] is False


def test_area_admin_tabs_are_separate_and_keep_authoritative_editors():
    html = (ROOT / "app/static/index.html").read_text()
    tools = (ROOT / "app/static/assets/treatment-tools.js").read_text()
    alerts = (ROOT / "app/static/assets/alerts.js").read_text()
    assert 'data-view="agronomy-admin"' in html
    assert 'id="view-agronomy-admin"' in html
    assert 'data-view="enology-admin"' in html
    assert 'id="view-enology-admin"' in html
    assert "treatmentSetupTools" in tools
    assert "enologyAdminThresholds" in alerts
    assert "node.innerHTML=thresholdForm+" not in alerts
