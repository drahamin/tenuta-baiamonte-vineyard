from pathlib import Path

from app.domains.olives import calculate_cost_analysis


ROOT = Path(__file__).resolve().parents[1]


def supplied_2024_model(**overrides):
    model = {
        "press_rate_eur_per_kg": 0.20,
        "bottle_volume_ml": 500,
        "bottle_count": 220,
        "bottle_unit_cost_eur": 2.30,
        "supplier_net_eur": 751,
        "vat_rate_pct": 22,
        "supplier_includes_press_bottling": 1,
        "annual_labor_eur": 1000,
        "harvest_labor_eur": 540,
        "harvest_included_in_annual": 1,
        "harvest_rate_eur_per_tree": 7,
    }
    model.update(overrides)
    return model


def test_2024_olive_cost_math_is_formula_driven_and_exact():
    result = calculate_cost_analysis({"olives_kg": 332, "oil_liters": 40}, supplied_2024_model())

    assert result["kg_per_liter"] == 8.3
    assert result["oil_yield_pct"] == 12.048
    assert result["press_cost_eur"] == 66.40
    assert result["bottling_cost_eur"] == 506.00
    assert result["supplier_vat_eur"] == 165.22
    assert result["supplier_gross_eur"] == 916.22
    assert result["labor_cost_eur"] == 1000.00
    assert result["supplier_remainder_eur"] == 178.60
    assert result["total_cost_eur"] == 1916.22
    assert result["cost_per_liter_eur"] == 47.91
    assert result["cost_per_actual_bottle_eur"] == 23.95
    assert sum(item["amount_eur"] for item in result["breakdown"]) == result["total_cost_eur"]
    assert result["actual_bottle_equivalents"] == 80
    assert result["planned_bottle_liters"] == 110
    assert result["bottle_volume_gap_liters"] == -70
    assert result["estimated_harvest_trees"] == 77.14


def test_harvest_labor_is_only_added_when_not_included_in_annual_total():
    result = calculate_cost_analysis(
        {"olives_kg": 332, "oil_liters": 40},
        supplied_2024_model(harvest_included_in_annual=0),
    )

    assert result["harvest_cost_added_eur"] == 540
    assert result["labor_cost_eur"] == 1540
    assert result["total_cost_eur"] == 2456.22


def test_separate_supplier_invoice_can_be_added_without_reconciliation():
    result = calculate_cost_analysis(
        {"olives_kg": 332, "oil_liters": 40},
        supplied_2024_model(supplier_includes_press_bottling=0),
    )

    assert result["total_cost_eur"] == 2488.62


def test_unsaved_year_preserves_yield_but_does_not_report_zero_costs():
    result = calculate_cost_analysis({"olives_kg": 500, "oil_liters": 75}, None)

    assert result["has_cost_model"] is False
    assert result["kg_per_liter"] == 6.667
    assert result["actual_bottle_equivalents"] == 150
    assert result["total_cost_eur"] is None
    assert result["cost_per_liter_eur"] is None
    assert result["breakdown"] == []


def test_migration_and_dashboard_retain_authoritative_2024_inputs_and_yoy_charts():
    migration = (ROOT / "db" / "migrations" / "059_olive_cost_model.sql").read_text(encoding="utf-8")
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    javascript = "\n".join(
        (ROOT / "app" / "static" / path).read_text(encoding="utf-8")
        for path in ("app.js", "assets/olives-planning.js")
    )
    backend = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

    assert "olives_harvested_kg=332.000" in migration
    assert "oil_liters=40.000" in migration
    assert "fk_olive_cost_model_estate" in migration
    assert "INSERT INTO olive_cost_models" not in migration
    assert "00000000-0000-0000-0000-000000000001" not in migration
    assert "estate_id=(SELECT id FROM estates WHERE slug='tenuta-baiamonte' LIMIT 1)" in migration
    repair = (ROOT / "db" / "migrations" / "060_repair_olive_authority.sql").read_text(encoding="utf-8")
    assert "INSERT INTO olive_records" in repair
    assert "INSERT IGNORE INTO olive_cost_models" in repair
    assert "WHERE e.slug='tenuta-baiamonte'" in repair
    assert "ON DUPLICATE KEY UPDATE" in repair
    for chart_id in ["oliveKgYoyChart", "oliveOilYoyChart", "oliveConversionYoyChart", "oliveCostYoyChart"]:
        assert f'id="{chart_id}"' in markup
        assert chart_id in javascript
    assert 'id="oliveCostForm"' in markup
    assert "api/v1/olives/cost-model/" in javascript
    assert '"bottle_count": 220 if supplied_2024 else None' in backend
    assert '"year": row_year' in backend
    assert '"has_cost_model": effective_model is not None' in backend
    assert "Known cost subtotal" in javascript


def test_current_workflow_keeps_missing_costs_unknown_until_reconciled():
    result = calculate_cost_analysis(
        {"olives_kg": 695, "oil_liters": 89.5},
        {
            "cost_model_version": "workflow_v2",
            "bottle_volume_ml": 500,
            "package_500ml_count": 118,
            "package_3l_count": 10,
            "labor_hourly_rate_eur": 10,
        },
    )

    assert result["kg_per_liter"] == 7.765
    assert result["planned_bottle_liters"] == 89
    assert result["bottle_volume_gap_liters"] == 0.5
    assert result["cost_complete"] is False
    assert result["known_cost_eur"] == 0
    assert result["total_cost_eur"] is None
    assert result["cost_per_liter_eur"] is None
    assert "harvest labor hours or invoice" in result["missing_cost_inputs"]
    assert "mill invoice or rate" in result["missing_cost_inputs"]


def test_current_workflow_calculates_final_unit_cost_only_when_every_stage_is_explicit():
    result = calculate_cost_analysis(
        {"olives_kg": 695, "oil_liters": 89.5},
        {
            "cost_model_version": "workflow_v2",
            "bottle_volume_ml": 500,
            "harvest_labor_hours": 80,
            "labor_hourly_rate_eur": 10,
            "mill_cost_eur": 150,
            "transport_cost_eur": 40,
            "filtering_cost_eur": 0,
            "equipment_allocation_eur": 75,
            "package_500ml_count": 118,
            "package_500ml_unit_cost_eur": 1.2,
            "package_3l_count": 10,
            "package_3l_unit_cost_eur": 3.5,
            "packaging_other_eur": 20,
            "analysis_storage_eur": 0,
            "other_cost_eur": 0,
        },
    )

    assert result["cost_complete"] is True
    assert result["missing_cost_inputs"] == []
    assert result["labor_cost_eur"] == 800
    assert result["total_cost_eur"] == 1261.6
    assert result["cost_per_liter_eur"] == 14.1


def test_olive_dashboard_labor_rate_uses_real_labor_entry_columns():
    backend = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    query_start = backend.index('"SELECT person_or_crew,hourly_rate_eur,work_date,approved_by FROM labor_entries "')
    query_end = backend.index("(estate_id(),)", query_start)
    labor_rate_query = backend[query_start:query_end]

    assert "ORDER BY work_date DESC,id DESC LIMIT 1" in labor_rate_query
    assert "updated_at" not in labor_rate_query
