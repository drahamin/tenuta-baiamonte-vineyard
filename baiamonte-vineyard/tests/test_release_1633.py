from pathlib import Path

import pytest

from app.domains.projections import build_operational_projections


ROOT = Path(__file__).resolve().parents[1]


def test_purchased_fruit_schema_and_owner_record_are_explicit():
    migration = (ROOT / "db/migrations/203_purchased_fruit_reporting.sql").read_text()
    assert "source_type ENUM('estate_harvest','purchased')" in migration
    assert "supplier_name" in migration
    assert "source_plot_reference" in migration
    assert "Steph Yim" in migration and "1200 plot" in migration
    assert "estate yield/completion" in migration


def test_operational_projection_includes_purchase_without_calling_it_remaining_estate(monkeypatch):
    monkeypatch.setattr("app.domains.projections.adjust_production_forecasts", lambda rows, _year: rows)
    grapes = {
        "metrics": {"planned_kg": 4862.868, "harvested_kg": 5916.38},
        "vintages": [],
        "varieties": [],
    }
    operational = {
        "harvest_started": True,
        "nerello_kg": 2039.88,
        "grecanico_kg": 2399.25,
        "grenache_kg": 1477.25,
        "recorded_grape_kg": 5916.38,
        "estate_grape_kg": 4838.38,
        "purchased_grape_kg": 1078.0,
        "projected_remaining_kg": 0,
        "recorded_crates": 406,
        "projected_crates": 0,
        "wines": [
            {"finished_wine": "Grenache", "grape_kg": 1477.25, "wine_l": 1034.075,
             "recorded_grape_kg": 1477.25, "estate_grape_kg": 399.25,
             "purchased_grape_kg": 1078.0, "recorded_crates": 28,
             "projected_remaining_kg": 0, "projected_crates": 0, "crates": 28},
        ],
    }
    program = {
        "settings": {"expected_yield_l_per_kg": 0.7, "expected_yield_is_configured": True,
                     "expected_yield_source": "Current vintage configured planning yield",
                     "crate_weight_kg": 15},
        "planning": operational,
        "operational": operational,
    }
    result = build_operational_projections(
        2026, grapes, program, 0.7, {"recommended_scenario_range_pct": 15},
        [{"vintage_year": 2026, "variety_name": "Grenache", "grape_kg": 399.25}],
    )
    working = next(row for row in result["scenarios"] if row["name"] == "Working")
    assert working["grapes_kg"] == pytest.approx(5916.38)
    assert result["production_plan"]["estate_grapes_kg"] == pytest.approx(4838.38)
    assert result["production_plan"]["purchased_grapes_kg"] == pytest.approx(1078)
    assert result["production_plan"]["projected_remaining_kg"] == 0
    assert working["recorded_crates"] == 406
    assert working["crates_15kg"] == 406
    assert "purchased fruit" in result["basis"]


def test_ui_and_tv_explain_source_breakdown():
    app_js = (ROOT / "app/static/app.js").read_text()
    harvest_js = (ROOT / "app/static/assets/harvest.js").read_text()
    display_js = (ROOT / "app/static/display.js").read_text()
    assert "estate +" in app_js and "purchased separately" in app_js
    assert "Purchased fruit" in harvest_js and "Total fruit received" in harvest_js
    assert "purchased fruit increases production but never estate yield" in display_js
    assert "lot.source_type!=='purchased'" in app_js


def test_release_version_1_10_33():
    assert 'version: "1.10.38"' in (ROOT / "config.yaml").read_text()
