from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app import display_data, season_rollover, service
from app.estate_time import estate_year


ROOT = Path(__file__).resolve().parents[1]


def test_estate_year_changes_at_rome_midnight():
    assert estate_year(datetime(2026, 12, 31, 22, 59, tzinfo=timezone.utc)) == 2026
    assert estate_year(datetime(2026, 12, 31, 23, 1, tzinfo=timezone.utc)) == 2027


def test_gui_follows_current_year_without_reload():
    source = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "function checkYearRollover()" in source
    assert "state.year===estateYear" in source
    assert "visibilitychange" in source


def test_display_cache_keys_implicit_requests_by_resolved_year(monkeypatch):
    display_data.clear_display_cache()
    years = iter((2026, 2027))
    monkeypatch.setattr(display_data, "estate_year", lambda: next(years))
    monkeypatch.setattr(display_data, "_build_display_payload", lambda year: {"year": year})
    assert display_data.display_payload() == {"year": 2026}
    assert display_data.display_payload() == {"year": 2027}


def test_season_creation_is_safe_when_another_process_wins(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return {"id": "winner-season"}

    cursor = Cursor()

    @contextmanager
    def fake_transaction():
        yield None, cursor

    monkeypatch.setattr(service, "fetch_one", lambda *_: None)
    monkeypatch.setattr(service, "transaction", fake_transaction)
    monkeypatch.setattr(service, "estate_id", lambda: "estate")
    assert service.season_for_year(2027) == "winner-season"
    assert "INSERT IGNORE INTO seasons" in cursor.calls[0][0]


def test_rollover_builds_planning_records_without_copying_actuals(monkeypatch):
    class Cursor:
        rowcount = 1

        def __init__(self):
            self.sql = []

        def execute(self, sql, params):
            self.sql.append(sql)
            self.rowcount = 1

        def fetchone(self):
            return {"setting_value": {"vintage_year": 2026}}

    cursor = Cursor()

    @contextmanager
    def fake_transaction():
        yield None, cursor

    monkeypatch.setattr(season_rollover, "transaction", fake_transaction)
    monkeypatch.setattr(season_rollover, "season_for_year", lambda year: f"season-{year}")
    monkeypatch.setattr(season_rollover, "estate_id", lambda: "estate")
    result = season_rollover.ensure_annual_rollover(2027)
    combined = "\n".join(cursor.sql)
    assert result["year_advanced"] is True
    assert result["season_id"] == "season-2027"
    assert "varietal_program_settings" in combined
    assert "production_forecasts" in combined
    assert "grape_allocation_plans" in combined
    assert "wine_output_plans" in combined
    assert "harvest_lots" not in combined
    assert "phenology_observations" not in combined
