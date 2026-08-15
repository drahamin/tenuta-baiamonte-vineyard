from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_finance_review_is_compact_collapsible_and_inventory_backed():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")

    assert 'id="financeReview"' in html
    assert html.count('class="panel finance-section"') >= 2
    assert 'id="financeInventory"' in html
    assert 'data-open="inventory"' in html
    assert "f.inventory||[]" in script
    assert "financeReceivable" in script
    assert "financePayable" in script
    assert "older than 90 days" in script


def test_finance_keeps_accounting_source_read_only():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert "Read-only accounting mirror" in html
    assert '"inventory": fetch_all("SELECT * FROM v_inventory_current' in main
