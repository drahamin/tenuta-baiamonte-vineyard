import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "scripts/qualify_mobile_reporting_reads.py"
SPEC = importlib.util.spec_from_file_location("mobile_read_qualification", PATH)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class Connection:
    def __init__(self, missing=False):
        self.calls = []
        self.rollbacks = 0
        self.missing = missing

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()): self.calls.append((sql, params))
    def rollback(self): self.rollbacks += 1
    def fetchone(self): return {"name": "Synthetic"}
    def fetchall(self):
        if "SELECT table_name,column_name" in self.calls[-1][0]:
            if self.missing: return []
            rows = [{"table_name": table, "column_name": field} for table, fields in runner.REQUIRED.items() for field in fields.split()]
            return [*rows, {"table_name": "ro_lab_decision_queue", "column_name": "sample_id"}]
        return []


def module():
    obj = SimpleNamespace(fetch_all=None, fetch_one=None)
    def catalog(estate, year):
        obj.fetch_one("SELECT name FROM estates WHERE id=%s", (estate,))
        return {"varieties": obj.fetch_all("SELECT id FROM grape_varieties WHERE estate_id=%s LIMIT 50", (estate,)),
                "containers": obj.fetch_all("SELECT id FROM cellar_containers WHERE estate_id=%s LIMIT 100", (estate,))}
    obj.read_catalog = catalog
    obj.read_records = lambda kind, estate, year, limit: obj.fetch_all("SELECT id FROM tasks WHERE estate_id=%s LIMIT 100", (estate,))
    return obj


def test_qualification_is_select_only_rollback_and_redacted():
    connection, candidate = Connection(), module()
    result = runner.qualify(candidate, connection, "synthetic-estate", 2026)
    assert result["ok"] and result["schema_ready"] and len(result["reads"]) == 9
    assert connection.rollbacks == 1 and candidate.fetch_all is None
    assert connection.calls[:3] == [("SET SESSION max_statement_time=2", ()), ("SET TRANSACTION READ ONLY", ()), ("START TRANSACTION WITH CONSISTENT SNAPSHOT", ())]
    assert all(sql.startswith("SELECT ") for sql, _ in connection.calls[3:])
    assert "Synthetic" not in str(result) and "synthetic-estate" not in str(result)


def test_missing_schema_fails_before_candidate_reads():
    connection = Connection(missing=True)
    result = runner.qualify(module(), connection, "synthetic-estate", 2026)
    assert not result["schema_ready"] and result["reads"] == []
    assert connection.rollbacks == 1


@pytest.mark.parametrize("sql", ["UPDATE tasks SET status='done'", "SELECT id FROM payroll", "SELECT id FROM tasks; SELECT 1"])
def test_offscope_or_write_query_rejected_before_execution(sql):
    candidate, connection = module(), Connection()
    candidate.read_catalog = lambda *_: candidate.fetch_all(sql, ())
    with pytest.raises(runner.QualificationFailure):
        runner.qualify(candidate, connection, "synthetic-estate", 2026)
    assert not any(query == sql for query, _ in connection.calls)
    assert connection.rollbacks == 1


def test_latency_budget_failure_rolls_back():
    connection = Connection()
    ticks = iter([0.0, 6.0])
    with pytest.raises(runner.QualificationFailure):
        runner.qualify(module(), connection, "synthetic-estate", 2026, clock=lambda: next(ticks))
    assert connection.rollbacks == 1


@pytest.mark.parametrize("name,password", [("other_database", "synthetic"), ("baiamonte_vineyard", "")])
def test_uninitialized_or_wrong_database_environment_is_rejected(name, password):
    with pytest.raises(runner.QualificationFailure):
        runner.validate_runtime(SimpleNamespace(db_name=name, db_password=password))
