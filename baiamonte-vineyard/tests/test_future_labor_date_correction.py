from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_future_gas_reimbursement_is_corrected_without_changing_payment():
    migration = (ROOT / "db/migrations/110_correct_future_gas_reimbursement_date.sql").read_text(encoding="utf-8")
    assert "2026-08-27" in migration
    assert "2026-07-27" in migration
    assert "other_cost_eur=20" in migration
    assert "amount and paid status unchanged" in migration
    assert "JSON_SET(extracted_data" in migration
    assert "Giancarlo — July 2026 labor hours (139 h)" in migration
    assert "UPDATE labor_invoice_payments" not in migration
