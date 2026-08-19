from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hospitality_navigation_and_workspace_are_present():
    html = (ROOT / "app/static/index.html").read_text()
    javascript = (ROOT / "app/static/assets/hospitality.js").read_text()
    assert 'data-nav-mode="hospitality"' in html
    assert 'id="view-hospitality"' in html
    assert "One private guest party at a time" not in javascript  # supplied by the API, not invented in the client
    assert "loadHospitality" in javascript
    assert "hospitalityNewBooking" in javascript


def test_hospitality_schema_supports_packages_guests_and_audit_history():
    migration = (ROOT / "db/migrations/062_hospitality_module.sql").read_text()
    for table in ("hospitality_packages", "hospitality_reservations", "hospitality_communications"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "dietary_restrictions" in migration
    assert "celebration_details" in migration
    assert "deposit_received_eur" in migration
    assert "Private Estate Dinner" in migration


def test_hospitality_role_and_access_are_distinct():
    roles = (ROOT / "app/domains/people_roles.py").read_text()
    access = (ROOT / "app/access.py").read_text()
    people = (ROOT / "app/domains/people_roles.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    assert '"Hospitality Manager"' in roles
    assert "authorize_hospitality" in access
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
