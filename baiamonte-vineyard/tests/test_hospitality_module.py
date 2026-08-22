from pathlib import Path
from decimal import Decimal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.domains.hospitality import calculate_partner_commission


def test_hospitality_navigation_and_workspace_are_present():
    html = (ROOT / "app/static/index.html").read_text()
    app_javascript = (ROOT / "app/static/app.js").read_text()
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    assert 'data-nav-mode="hospitality"' in html
    assert 'id="view-hospitality"' in html
    assert "One private guest party at a time" not in javascript  # supplied by the API, not invented in the client
    assert "loadHospitality" in javascript
    assert "hospitalityNewBooking" in javascript
    assert "button.onclick=()=>activateViewButton(button)" in app_javascript
    assert "storedHospitalityPanel()" in javascript
    assert 'data-hospitality-panel="${CSS.escape(storedHospitalityPanel())}"' in javascript


def test_hospitality_schema_supports_packages_guests_and_audit_history():
    migration = (ROOT / "db/migrations/062_hospitality_module.sql").read_text()
    for table in ("hospitality_packages", "hospitality_reservations", "hospitality_communications"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "dietary_restrictions" in migration
    assert "celebration_details" in migration
    assert "deposit_received_eur" in migration
    assert "Private Estate Dinner" in migration


def test_hospitality_inquiries_route_from_configurable_gmail_subjects():
    migration = (ROOT / "db/migrations/063_hospitality_inquiries.sql").read_text()
    inbox = (ROOT / "app/domains/hospitality_inbox.py").read_text()
    intelligence = (ROOT / "app/intelligence.py").read_text()
    assert "CREATE TABLE IF NOT EXISTS hospitality_inquiries" in migration
    assert "Inquiry about Reserve Tasting" in inbox
    assert "hospitality_subject_matches" in inbox
    assert "route_hospitality_inquiry(record_id)" in intelligence
    assert "not hospitality_message" in intelligence


def test_hospitality_inquiries_route_from_gmail_labels_and_revisit_saved_mail():
    inbox = (ROOT / "app/domains/hospitality_inbox.py").read_text()
    intelligence = (ROOT / "app/intelligence.py").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    migration = (ROOT / "db/migrations/113_hospitality_gmail_labels.sql").read_text()
    assert '"inbound_labels": ["Hospitality"]' in inbox
    assert "hospitality_message_matches" in inbox
    assert "_metadata_labels" in inbox
    assert "X-GM-LABELS BODY.PEEK[]" in intelligence
    assert "UPDATE intake_items SET source_metadata" in intelligence
    assert "route_hospitality_inquiry(primary_record_id)" in intelligence
    assert 'name="inbound_labels"' in html
    assert "data.inbound_labels" in javascript
    assert "ADD COLUMN IF NOT EXISTS source_metadata JSON" in migration


def test_hospitality_workspace_has_inquiry_conversion_admin_and_safe_dialogs():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    css = (ROOT / "app/static/assets/hospitality.css").read_text()
    assert 'data-hospitality-panel="inquiries"' in html
    assert 'data-hospitality-panel="admin"' in html
    assert 'id="hospitalitySettingsForm"' in html
    assert "convertHospitalityInquiry" in javascript
    assert "deleteHospitalityBooking" in javascript
    assert "100dvh" in css


def test_payroll_control_is_in_operations_control_not_docs():
    html = (ROOT / "app/static/index.html").read_text()
    enhancements = (ROOT / "app/static/assets/operations-enhancements.js").read_text()
    assert 'id="adminControlPayroll"' in html
    assert 'id="systemDocsPayroll"' not in html
    assert "state?.adminControl?.payroll" in enhancements


def test_hospitality_role_and_access_are_distinct():
    roles = (ROOT / "app/domains/people_roles.py").read_text()
    access = (ROOT / "app/access.py").read_text()
    people = (ROOT / "app/domains/people_roles.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    assert '"Hospitality Manager"' in roles
    assert "authorize_hospitality" in access
    assert "username in admin_usernames(settings)" in access
    assert 'level == "hospitality"' in people
    assert '"operations_workspace": operations' in people
    assert 'existing["username"]' in main


def test_hospitality_capacity_conflicts_are_enforced_server_side():
    source = (ROOT / "app/domains/hospitality.py").read_text()
    assert "ACTIVE_CAPACITY_STATUSES" in source
    assert "start_at<%s AND end_at>%s" in source
    assert "This overlaps confirmed booking" in source


def test_hospitality_messages_require_an_explicit_ui_action():
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    routes = (ROOT / "app/domains/hospitality_routes.py").read_text()
    assert "if(!confirm(label))return" in javascript
    assert "send_gmail_message" in routes
    assert "send_whatsapp_message" in routes
    assert "log_communication" in routes


def test_tv_work_plan_includes_scheduled_hospitality_without_guest_contact_data():
    backend = (ROOT / "app/display_data.py").read_text()
    display = (ROOT / "app/static/display.js").read_text()
    assert '"hospitality_events"' in backend
    assert "hospitalityRows" in display
    assert "tvHospitalityPlan" in display
    query = backend.split('"hospitality_events"', 1)[1].split('),', 1)[0]
    assert "guest_email" not in query
    assert "guest_phone" not in query


def test_tv_vintage_page_has_schedule_progress_and_output_context():
    html = (ROOT / "app/static/display.html").read_text()
    display = (ROOT / "app/static/display.js").read_text()
    assert 'id="tvVintageSchedule"' in html
    assert "HARVEST OUTLOOK" in display
    assert "15 kg crates" in display
    assert "750 ml bottles" in display


def test_partner_commission_rules_calculate_percentage_guest_and_booking_amounts():
    assert calculate_partner_commission(Decimal("1250"), 8, "percentage", Decimal("12")) == Decimal("150.00")
    assert calculate_partner_commission(Decimal("1250"), 8, "fixed_per_guest", Decimal("7.50")) == Decimal("60.00")
    assert calculate_partner_commission(Decimal("1250"), 8, "fixed_per_reservation", Decimal("85")) == Decimal("85.00")


def test_hospitality_partner_management_is_end_to_end_and_finance_visible():
    migration = (ROOT / "db/migrations/111_hospitality_partner_commissions.sql").read_text()
    routes = (ROOT / "app/domains/hospitality_routes.py").read_text()
    backend = (ROOT / "app/domains/hospitality.py").read_text()
    finance = (ROOT / "app/domains/finance.py").read_text()
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    for table in ("hospitality_partners", "hospitality_partner_commissions", "hospitality_partner_payments"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "partner_id" in migration
    assert 'router.get("/partners")' in routes
    assert 'router.post("/partner-commissions/{commission_id}/payments")' in routes
    assert "This reservation has partner payments; keep the partner assigned" in backend
    assert "Payment exceeds the remaining partner commission balance" in backend
    assert '"partner_payable_eur"' in finance
    assert 'data-hospitality-panel="partners"' in html
    assert 'id="hospitalityPartnerDialog"' in html
    assert "renderPartnerFinance" in javascript
    assert "deleteHospitalityPartnerPayment" in javascript
