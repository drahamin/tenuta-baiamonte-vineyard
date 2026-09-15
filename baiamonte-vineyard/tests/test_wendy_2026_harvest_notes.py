from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/155_wendy_2026_harvest_cellar_notes.sql"


def test_wendy_note_preserves_harvest_weights_tare_and_undefined_notation():
    migration = MIGRATION.read_text()
    assert "2588.08" in migration
    assert "288.55" in migration
    assert "2299.53" in migration
    assert "450.00" in migration
    assert "50.75" in migration
    assert "399.25" in migration
    assert '"60% must 769.68"' in migration
    assert "without interpreting its basis" in migration


def test_wendy_note_routes_every_tank_reading_and_punchdown_to_exact_lots():
    migration = MIGRATION.read_text()
    for source_id in (
        "wendy-2026-grc-t44-0912",
        "wendy-2026-grc-t03-0912",
        "wendy-2026-grc-t03-0913-first",
        "wendy-2026-grc-t44-0913-first",
        "wendy-2026-grc-t03-0913-1235",
        "wendy-2026-grenache-0911-noon",
        "wendy-2026-grenache-0911-evening",
        "wendy-2026-grenache-0912-0939",
        "wendy-2026-grenache-0912-1214",
        "wendy-2026-grenache-0912-1834",
        "wendy-2026-grenache-0913-0905",
    ):
        assert source_id in migration
    assert "wendy_source_note_date_only" in migration
    assert "wendy_source_note_approx_time" in migration
    assert "Punch down - one full circuit" in migration


def test_current_white_tank_readings_and_lab_requests_are_release_managed():
    migration = MIGRATION.read_text()
    assert "small white Tank #44, Babo 2.2 and 26 C" in migration
    assert "big white Tank #3 (system T-06), Babo 12.2 and 18 C" in migration
    assert "owner-2026-grc-t44-0915" in migration
    assert "owner-2026-grc-t03-0915" in migration
    assert "green bottle for catechins; panna bottle for catechins and NTU" in migration
    assert "JSON_ARRAY('catechins','turbidity')" in migration


def test_unconfirmed_instructions_are_not_promoted_to_completed_actions():
    migration = MIGRATION.read_text()
    assert "'EnartisFerm ES181','yeast','planned'" in migration
    assert "'Unspecified yeast - Wendy note','yeast','planned'" in migration
    assert "unit and product not stated" in migration
    assert "regular_hours is intentionally blank" in migration
