from datetime import date
from pathlib import Path

from app.domains import bottling


ROOT = Path(__file__).resolve().parents[1]


def test_bottling_projection_includes_purchased_fruit_without_double_counting_estate_forecast(monkeypatch):
    forecasts = [
        {"vintage_year": 2026, "variety_name": "Grecanico", "grape_kg": 2200},
        {"vintage_year": 2026, "variety_name": "Grenache", "grape_kg": 399.25},
        {"vintage_year": 2026, "variety_name": "Nerello Mascalese", "grape_kg": 1047.95},
    ]
    received = [
        {"variety_name": "Grecanico", "estate_grape_kg": 2200, "purchased_grape_kg": 0},
        {"variety_name": "Grenache", "estate_grape_kg": 399.25, "purchased_grape_kg": 1078},
        {"variety_name": "Nerello Mascalese", "estate_grape_kg": 2239.13, "purchased_grape_kg": 0},
    ]
    calls = iter([forecasts, received])
    monkeypatch.setattr(bottling, "fetch_all", lambda *_args, **_kwargs: next(calls))
    monkeypatch.setattr(bottling, "fetch_one", lambda *_args, **_kwargs: {"expected_yield_l_per_kg": 0.7})
    monkeypatch.setattr(bottling, "adjust_production_forecasts", lambda rows, _year: rows)

    bottles, note = bottling._projected_bottle_equivalents(2026)

    assert bottles == 5522
    assert "4,838.4 kg estate" in note
    assert "1,078.0 kg purchased" in note
    assert "0.0 kg remaining estate forecast" in note


def test_fruit_projection_keeps_unharvested_estate_forecast_separate_from_purchase():
    result = bottling._fruit_projection_basis(
        [{"variety_name": "Grenache", "adjusted_grape_kg": 500}],
        [{"variety_name": "Alicante", "estate_grape_kg": 300, "purchased_grape_kg": 1078}],
    )

    assert result == {"estate_kg": 300.0, "purchased_kg": 1078.0, "remaining_estate_kg": 200.0, "total_kg": 1578.0}


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


def test_zero_volume_lot_rows_do_not_keep_completed_vintage_on_projection(monkeypatch):
    monkeypatch.setattr(bottling, "_projected_bottle_equivalents", lambda _year: (3404, "Working forecast"))
    basis = bottling._bottle_quantity_basis(
        date.today().year,
        [],
        [{"wine_lot_id": "closed-in-practice", "volume_l": 0}],
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
