from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_finance_intake_routes_contractor_charges_and_deposits() -> None:
    source = (ROOT / "app" / "static" / "app.js").read_text()
    assert "function intakeFinanceAmount" in source
    assert "function normalizeIntakeSuggestion" in source
    assert "labor_entry_mode:'fixed_job'" in source
    assert "person_or_crew:isNunzio?'Nunzio Testa'" in source
    assert "other_cost_eur:amount" in source
    assert "amount_out:amount||0" in source
    assert "Reconcile summary" in source


def test_intake_prompt_requires_consistent_finance_fields_and_arithmetic() -> None:
    source = (ROOT / "app" / "intelligence.py").read_text()
    assert "other_cost_eur as one numeric EUR amount" in source
    assert "never add a deposit to the service cost" in source
    assert "verify their arithmetic against any declared total" in source
