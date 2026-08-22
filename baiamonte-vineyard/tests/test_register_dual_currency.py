from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_register_migration_preserves_eur_base_and_collected_tender():
    migration = (ROOT / "db/migrations/109_register_module.sql").read_text(encoding="utf-8")
    assert "total_eur DECIMAL(16,2)" in migration
    assert "currency CHAR(3)" in migration
    assert "tender_total DECIMAL(16,2)" in migration
    assert "usd_per_eur DECIMAL(16,6)" in migration
    assert "paypal_account ENUM('us','it')" in migration
    assert "checkout_language ENUM('en','it')" in migration
    assert "payment_method ENUM('cash','paypal','paypal_pos','other')" in migration


def test_checkout_and_receipt_show_both_collected_and_eur_base_values():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert 'id="registerTenderCurrency"' in html
    assert 'value="EUR"' in html and 'value="USD"' in html
    assert "EUR base" in script
    assert "USD/EUR" in script
    assert "sale.tender_total" in script
    assert "sale.total_eur" in script


def test_ledger_and_csv_keep_dual_currency_audit_fields_and_payment_reference():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/register_routes.py").read_text(encoding="utf-8")
    assert "eur_tender_total" in backend
    assert "usd_tender_total" in backend
    for heading in ("Total EUR", "Tender currency", "Tender total", "USD per EUR", "PayPal account", "Language", "Payment reference"):
        assert heading in routes


def test_paypal_pos_is_explicitly_operator_confirmed_and_not_browser_verified():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert "operator_confirmed_pos" in backend
    assert "browser does not independently verify" in html
    assert "PayPal POS app on an NFC phone" in html
    assert "manual_card" not in (ROOT / "db/migrations/109_register_module.sql").read_text(encoding="utf-8")


def test_both_paypal_accounts_and_receipt_languages_are_selectable_and_recorded():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert "paypal_it_client_id" in backend
    assert 'id="registerPaypalAccount"' in html
    assert 'data-register-language="en"' in html and 'data-register-language="it"' in html
    assert "preferredPaypalAccount" in script
    assert "checkout_language:registerState.language" in script
    assert "locale=${locale}" in script


def test_fic_sales_posting_remains_disabled_for_local_ledger_release():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    assert 'result["fic_sales_posting_enabled"] = False' in backend
    assert '"sales_posting_enabled": False' in backend


def test_cash_requires_explicit_confirmation_and_preserves_tender_audit():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/register_routes.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert 'id="registerCashDialog"' in html
    assert "Confirm cash received" in html
    assert "Cash received is less than the amount due" in backend
    assert '"cash_received": str(received)' in backend
    assert '"change_given": str(change)' in backend
    assert "complete_cash_sale(sale_id, request_username(request), payload)" in routes
    assert "confirmCashPayment" in script


def test_paid_sales_can_be_corrected_or_audited_void_with_stock_restoration():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/register_routes.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert "def update_sale_payment" in backend
    assert "def void_sale" in backend
    assert "status='void'" in backend
    assert "s.status IN ('awaiting_payment','paid')" in backend
    assert '@router.post("/sales/{sale_id}/void"' in routes
    assert 'id="registerPaymentDialog"' in html
    assert "Payment voided; inventory restored" in script
    assert "Refund this captured payment in PayPal first" in backend


def test_register_daily_exchange_refresh_and_touch_dialogs_replace_native_prompts():
    intelligence = (ROOT / "app/intelligence.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert "refresh_exchange_rate_if_stale" in intelligence
    assert 'id="registerPaypalPosDialog"' in html
    assert "window.prompt" not in script
    assert "window.confirm" not in script


def test_home_assistant_network_receipt_printer_has_browser_fallback():
    backend = (ROOT / "app/domains/register.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/domains/register_routes.py").read_text(encoding="utf-8")
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/assets/register.js").read_text(encoding="utf-8")
    assert "def print_via_home_assistant" in backend
    assert "http://supervisor/core/api/services/" in backend
    assert '@router.post("/sales/{sale_id}/system-print")' in routes
    assert 'name="receipt_printer_service"' in html
    assert "opening browser print instead" in script
