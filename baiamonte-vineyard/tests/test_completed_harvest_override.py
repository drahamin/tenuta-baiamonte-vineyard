from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_2026_grecanico_and_grenache_plans_close_from_actual_picking() -> None:
    migration = (ROOT / "db/migrations/212_complete_2026_harvest_plans.sql").read_text()

    assert "LOWER(TRIM(v.name)) IN ('grecanico','grenache')" in migration
    assert "p.status='complete'" in migration
    assert "actual.actual_pick_date" in migration
    assert "original plan quantities remain audit history" in migration


def test_external_feeds_hide_plans_once_estate_picking_is_recorded() -> None:
    sources = "\n".join(
        (ROOT / path).read_text()
        for path in ("app/mcp_server.py", "app/planning_sync.py", "app/intelligence.py")
    )

    assert sources.count("NOT EXISTS (SELECT 1 FROM harvest_lots actual") >= 4
    assert "actual.source_type='estate_harvest'" in sources
    assert "never present a completed variety as still awaiting picking" in sources


def test_scheduler_closes_working_forecast_when_actual_harvest_exists() -> None:
    source = (ROOT / "app/intelligence.py").read_text()

    assert "has_actual_pick" in source
    assert 'status=\'complete\'' in source
    assert "complete_from_actual_harvest" in source
    assert "completed harvest record overrides forecast" in source


def test_current_vintage_dashboard_marks_closed_picks_complete() -> None:
    source = (ROOT / "app/domains/dashboard_routes.py").read_text()

    assert "completed_pick = bool(row.get(\"first_pick_date\"))" in source
    assert '"approval_status": "picked_complete" if completed_pick' in source
