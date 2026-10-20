from pathlib import Path


MIGRATION = Path(__file__).parents[1] / "db/migrations/221_remote_hospitality_reporting.sql"


def test_remote_hospitality_views_are_privacy_minimized() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").casefold()
    assert "create or replace view ro_hospitality_packages" in sql
    assert "create or replace view ro_hospitality_schedule" in sql
    for forbidden in (
        "guest_name", "guest_email", "guest_phone", "dietary_restrictions",
        "celebration_details", "guest_preferences", "public_notes", "internal_notes",
        "price_eur", "deposit_eur", "quoted_total_eur", "deposit_received_eur",
        "partner_id", "partner_referral_code", "commission", "payment",
    ):
        assert forbidden not in sql


def test_remote_hospitality_schedule_keeps_only_approved_operational_fields() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").casefold()
    for field in (
        "confirmation_code", "package_name", "experience_type", "status",
        "start_at", "end_at", "guest_count", "preferred_language", "source",
        "assigned_manager_entity",
    ):
        assert field in sql
