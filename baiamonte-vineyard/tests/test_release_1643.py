from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_winemaking_payments_are_structured_and_seeded() -> None:
    migration = (ROOT / "db/migrations/213_winemaking_payment_tracking.sql").read_text()
    backend = (ROOT / "app/domains/bottling.py").read_text()

    assert "amount_paid_eur DECIMAL(14,2)" in migration
    assert "amount_paid_eur=12500.00" in migration
    assert "planned_cost_eur=21500.00" in migration
    assert '"balance_due_eur": balance_due' in backend
    assert "paid > amount" in backend


def test_finance_includes_only_the_outstanding_winemaking_balance() -> None:
    finance = (ROOT / "app/domains/finance.py").read_text()
    frontend = (ROOT / "app/static/assets/bottling.js").read_text()

    assert 'winemaking_payable = 0 if actual_winemaking else float(cellar_plan.get("balance_due_eur") or 0)' in finance
    assert '"payable_eur": round(fic_payable + payroll_payable + partner_payable + winemaking_payable, 2)' in finance
    assert "Winemaking paid" in frontend
    assert "Winemaking due" in frontend
    assert "amount_paid_eur:Number" in frontend


def test_release_version() -> None:
    assert 'version: "1.10.70"' in (ROOT / "config.yaml").read_text()
