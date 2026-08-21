from decimal import Decimal
from pathlib import Path

from app.inventory import convert_inventory_quantity, total_used_unit


ROOT = Path(__file__).resolve().parents[1]


def test_historical_year_cannot_reopen_a_current_stock_shortage() -> None:
    source = (ROOT / "app/domains/treatment_routes.py").read_text()
    migration = (ROOT / "db/migrations/107_audit_issue_scope_and_labels.sql").read_text()
    assert "if year != date.today().year" in source
    assert '"status": "historical_year"' in source
    assert "treatment-inventory-shortage:2025:vineyard" in migration
    assert "status='resolved'" in migration
    assert "ISSUE-2026-015" in migration
    assert "issue_type='Cellar'" in migration


def test_treatment_total_units_are_read_from_rate_units() -> None:
    assert total_used_unit("g/100 L") == "g"
    assert total_used_unit("ml/100 L") == "ml"
    assert total_used_unit("kg/ha") == "kg"
    assert total_used_unit(None) is None


def test_inventory_converts_only_within_the_same_physical_dimension() -> None:
    assert convert_inventory_quantity(400, "g", "kg") == Decimal("0.400")
    assert convert_inventory_quantity(1500, "ml", "L") == Decimal("1.500")
    assert convert_inventory_quantity(2, "kg", "g") == Decimal("2000")
    assert convert_inventory_quantity(200, "ml", "kg") is None
    assert convert_inventory_quantity(2250, "g", "L") is None


def test_inventory_uses_verified_density_for_cross_dimension_conversion() -> None:
    assert convert_inventory_quantity(2000, "g", "L", "1.40").quantize(Decimal("0.001")) == Decimal("1.429")
    assert convert_inventory_quantity(1, "L", "kg", "1.40") == Decimal("1.40")
    assert convert_inventory_quantity(2000, "g", "L", 0) is None


def test_ossiclor_density_migration_preserves_range_and_midpoint() -> None:
    sql = (ROOT / "db/migrations/084_ossiclor_density_reconciliation.sql").read_text(encoding="utf-8")
    assert "density_min_kg_l=1.35000" in sql
    assert "density_kg_l=1.40000" in sql
    assert "density_max_kg_l=1.45000" in sql
    assert "(i.total_used/1000)/1.40000" in sql
    assert "must not be represented as an exact lot measurement" in sql


def test_historical_migration_posts_only_confirmed_safe_use_totals() -> None:
    sql = (ROOT / "db/migrations/074_treatment_inventory_usage.sql").read_text(encoding="utf-8")
    assert "reference_type='spray_application_item'" in sql
    assert "i.total_used IS NOT NULL" in sql
    assert "i.total_used/1000" in sql
    assert "cross_dimension_policy" in sql
    assert "LOWER(TRIM(purpose))='treatment 3'" in sql
    assert "water_volume_l=500" in sql
    assert "LOWER(TRIM(a.purpose)) IN ('treatment 2','treatment 4')" in sql
    assert "source_water_text='400 L · owner confirmed 2026-08-20'" in sql
    assert "WHEN 'GEL DI SILICE' THEN 1800" in sql


def test_silica_gel_receipt_and_label_are_volume_based() -> None:
    stock = (ROOT / "app/fattureincloud.py").read_text(encoding="utf-8")
    migration = (ROOT / "db/migrations/074_treatment_inventory_usage.sql").read_text(encoding="utf-8")
    assert '("GEL DI SILICE", "GEL DI SILICE", Decimal("5"), "L"' in stock
    assert "Lot 26271001E2" in migration
    assert "pe.package_unit='L',pe.quantity_unit='L'" in migration


def test_impulsive_label_repairs_historical_units_without_inventing_density() -> None:
    migration = (ROOT / "db/migrations/086_impulsive_liquid_evidence.sql").read_text(encoding="utf-8")
    intelligence = (ROOT / "app/intelligence.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/treatment_routes.py").read_text(encoding="utf-8")
    assert "i.dose_unit='ml/100 L'" in migration
    assert "2,3,'L/ha'" in migration
    assert "r.density_kg_l=NULL,r.density_source=NULL" in migration
    assert "No density is inferred" in migration
    assert "i.total_used/1000" in migration
    source_text_repair = (ROOT / "db/migrations/087_impulsive_source_text_units.sql").read_text(encoding="utf-8")
    assert "2,250 ml total" in source_text_repair
    assert "2,250 g total" in source_text_repair
    assert "product_label" in intelligence
    assert "Keep mass and volume separate" in intelligence
    assert 'id="productLabelIntakeForm"' in html
    assert "/api/v1/treatments/product-evidence/intake/{record_id}/approve" in routes
    assert "authorization, inventory and treatment rules are not silently granted" in routes
    assert "created_product" in routes
    catalog = (ROOT / "app/main.py").read_text(encoding="utf-8")
    tools = (ROOT / "app/static/assets/treatment-tools.js").read_text(encoding="utf-8")
    assert "treatment_reference" in catalog
    assert "['plant_protection','fertilizer']" in tools
    assert "Boolean(row.treatment_reference)" not in tools
    assert "088_treatment_catalog_categories.sql" in {
        path.name for path in (ROOT / "db/migrations").glob("*.sql")
    }


def test_completion_and_quick_entry_share_the_inventory_chain() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    quick_entry = (ROOT / "app/quick_entry.py").read_text(encoding="utf-8")
    assert "inventory_sync = sync_treatment_inventory_use(cursor, treatment_id)" in main
    assert "sync_treatment_inventory_use(cursor, record_id)" in quick_entry


def test_purchase_advice_is_blocked_when_completed_use_is_unreconciled() -> None:
    source = (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
    assert 'inventory_reconciliation["complete"]' in source
    assert "purchase advice is provisional" in source
    assert 'purchase_state == "receipt_pending"' in source
    assert 'purchase_state == "stock_unreconciled"' in source
    assert "delayed purchase invoice or receipt" in source


def test_negative_stock_remains_visible_until_delayed_receipt_nets_it() -> None:
    source = (ROOT / "app/domains/treatments.py").read_text(encoding="utf-8")
    assert "SUM(i.quantity_delta) stock_on_hand" in source
    assert "GREATEST(0,SUM(i.quantity_delta)) stock_on_hand" not in source
    assert 'ledger_balance = _number(candidate_stock.get("ledger_balance")) or 0' in source
    assert 'stock_balance = _number(candidate_stock.get("stock_on_hand")) or 0' in source
    assert '"receipt_pending" if ledger_balance < 0' in source
    assert "ledger will net automatically when it arrives" in source
