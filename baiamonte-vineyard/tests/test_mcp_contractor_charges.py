from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mcp_labor_record_accepts_fixed_price_charge_fields() -> None:
    source = (ROOT / "app" / "mcp_server.py").read_text()
    definition = source.split('"labor_entry":', 1)[1].split('\n', 1)[0]
    for field in (
        "work_category",
        "work_performed",
        "other_cost_eur",
        "expense_amount_eur",
        "expense_category",
        "approval_status",
        "entry_source",
    ):
        assert f'"{field}"' in definition
    assert '"defaults": {"approval_status": "approved"' in definition
