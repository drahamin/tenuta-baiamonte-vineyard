from pathlib import Path

import pytest

from app.domains import mobile_reporting_reads as reads


ESTATE = "11111111-1111-4111-8111-111111111111"


def fake_database(monkeypatch, *, columns=()):
    calls = []
    def all_rows(sql, params):
        calls.append((sql, params))
        if "information_schema.columns" in sql:
            return [{"column_name": name} for name in columns]
        return []
    def one_row(sql, params):
        calls.append((sql, params))
        return {"name": "Synthetic estate"}
    monkeypatch.setattr(reads, "fetch_all", all_rows)
    monkeypatch.setattr(reads, "fetch_one", one_row)
    return calls


def test_catalog_requires_only_three_scoped_selects(monkeypatch):
    calls = fake_database(monkeypatch)
    data = reads.read_catalog(ESTATE, 2026)
    assert len(calls) == 3 and data["estate"]["year"] == 2026
    for sql, params in calls:
        assert sql.startswith("SELECT ") and ESTATE in params and "SELECT *" not in sql
    assert calls[1][1][-1] == 50 and calls[2][1][-1] == 100


@pytest.mark.parametrize("kind", sorted(reads.OBJECTS))
def test_reporting_reads_are_bounded_and_do_not_touch_excluded_sources(monkeypatch, kind):
    calls = fake_database(monkeypatch, columns={"sample_id", "estate_id", "sample_type", "flagged_results", "review_status", "lab_date"})
    assert reads.read_records(kind, ESTATE, 2026, 7) == []
    assert 1 <= len(calls) <= 2
    for sql, params in calls:
        assert sql.startswith("SELECT ") and "SELECT *" not in sql
        for forbidden in ("v_lab_decision_queue", "intake_items", "payroll", "security", "integration_events", "app_settings"):
            assert forbidden not in sql
        if "information_schema.columns" not in sql:
            assert ESTATE in params and params[-1] == 7 and "LIMIT %s" in sql


@pytest.mark.parametrize("columns", [(), ("id",), ("sample_id", "estate_id")])
def test_unverified_lab_view_schema_never_falls_back_to_underlying_view(monkeypatch, columns):
    calls = fake_database(monkeypatch, columns=columns)
    with pytest.raises(reads.ReportingSourceUnavailable):
        reads.read_records("labs", ESTATE, 2026, 5)
    assert len(calls) == 1 and "information_schema.columns" in calls[0][0]


@pytest.mark.parametrize("identifier", ["id", "sample_id"])
def test_lab_identifier_is_closed_and_private_fields_not_selected(monkeypatch, identifier):
    calls = fake_database(monkeypatch, columns={identifier, "estate_id", "sample_type", "flagged_results", "review_status", "lab_date", "private_notes"})
    reads.read_records("labs", ESTATE, 2026, 5)
    assert f"SELECT {identifier} id" in calls[1][0]
    assert "private_notes" not in calls[1][0]


@pytest.mark.parametrize("kind,estate,year,limit", [
    ("finance", ESTATE, 2026, 5), ("tasks", "not-an-estate", 2026, 5),
    ("tasks", ESTATE, True, 5), ("tasks", ESTATE, 2026, 101), ("tasks", ESTATE, 2026, True),
])
def test_bad_scope_or_object_rejected_before_database(monkeypatch, kind, estate, year, limit):
    calls = fake_database(monkeypatch)
    with pytest.raises(ValueError):
        reads.read_records(kind, estate, year, limit)
    assert calls == []


def test_cellar_uses_only_unambiguous_estate_season_lot_links(monkeypatch):
    calls = fake_database(monkeypatch)
    reads.read_records("cellar", ESTATE, 2026, 5)
    sql, params = calls[0]
    assert "wx.current_container_id=c.id" in sql and "wx.estate_id=c.estate_id" in sql
    assert "s.vintage_year=%s" in sql and params == (2026, ESTATE, 5)
    assert "HAVING COUNT(*)=1" in sql
    assert "fermentation_observations" not in sql and "cellar_control_profiles" not in sql
    assert "NULL observed_at" in sql and "ELSE NULL END fill_pct" in sql


@pytest.mark.parametrize("lot_count", [0, 1, 2])
def test_exact_cellar_query_rejects_duplicate_moved_and_manual_evidence(monkeypatch, lot_count):
    import sqlite3
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE cellar_containers(id TEXT,estate_id TEXT,code TEXT,name TEXT,capacity_l REAL,status TEXT,active INTEGER);
        CREATE TABLE seasons(id TEXT,estate_id TEXT,vintage_year INTEGER);
        CREATE TABLE wine_lots(id TEXT,estate_id TEXT,season_id TEXT,current_container_id TEXT,stage TEXT,volume_l REAL);
        CREATE TABLE fermentation_observations(wine_lot_id TEXT,vessel_name TEXT,temp_c REAL,observed_at TEXT);
        CREATE TABLE cellar_control_profiles(container_id TEXT,manual_volume_l REAL,manual_temp_c REAL,manual_reading_at TEXT);
    """)
    connection.execute("INSERT INTO cellar_containers VALUES ('c',?,'C1','Synthetic',1000,'active',1)", (ESTATE,))
    connection.execute("INSERT INTO seasons VALUES ('s',?,2026)", (ESTATE,))
    for index in range(lot_count):
        connection.execute("INSERT INTO wine_lots VALUES (?,?,'s','c','fermenting',?)", (str(index), ESTATE, 600 + index * 100))
    # Neither a different-vessel observation nor an old/unlinked manual profile
    # may become this container's current measurement or fallback volume.
    connection.execute("INSERT INTO fermentation_observations VALUES ('0','Other vessel',25,'2026-11-03T12:00:00Z')")
    connection.execute("INSERT INTO cellar_control_profiles VALUES ('c',999,31,'2026-11-02T12:00:00Z')")
    monkeypatch.setattr(reads, "fetch_all", lambda sql, params: [dict(row) for row in connection.execute(sql.replace('%s', '?'), params)])
    try:
        row = reads.read_records("cellar", ESTATE, 2026, 5)[0]
        assert row["volume_l"] == (600 if lot_count == 1 else None)
        assert row["stage"] == ("fermenting" if lot_count == 1 else None)
        assert row["fill_pct"] == (60 if lot_count == 1 else None)
        assert all(row[field] is None for field in ("temperature_c", "density_sg", "brix", "ph", "observed_at"))
    finally:
        connection.close()


def test_grape_sums_are_season_estate_scoped_with_unknowns_preserved(monkeypatch):
    calls = fake_database(monkeypatch)
    reads.read_records("grapes", ESTATE, 2026, 9)
    sql, params = calls[0]
    assert params == (ESTATE, 2026, ESTATE, 2026, ESTATE, 9)
    assert "h.estate_harvested_kg IS NOT NULL" in sql


def test_repository_has_no_tv_network_controls_or_time_fabrication():
    source = Path(reads.__file__).read_text()
    for forbidden in ("display_payload", "intelligence", "home_assistant", "urlopen", "requests.", "httpx", "INSERT ", "UPDATE ", "DELETE ", "datetime.now", "season_for_year"):
        assert forbidden not in source
