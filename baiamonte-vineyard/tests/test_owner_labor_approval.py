from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import ast
import json
from pathlib import Path
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access import authorize_admin
from app.domains import payroll, payroll_admin_routes


def owner_row(**changes):
    row = {
        "id": "owner-1", "estate_id": "estate-1",
        "entry_source": "owner_reconciliation",
        "source_labor_id": payroll.OWNER_LABOR_SOURCE_PREFIX + "-vincenzo-part-time",
        "worker_username": None, "person_or_crew": "Vincenzo (part-time)",
        "work_date": date(2026, 10, 1), "regular_hours": Decimal("45.00"),
        "overtime_hours": None, "hourly_rate_eur": Decimal("10.00"),
        "labor_cost_eur": Decimal("450.00"), "other_cost_eur": None,
        "expense_amount_eur": None, "pay_due_date": None,
        "approval_status": "draft", "payment_status": "unknown",
        "locked_at": None, "paid_at": None, "approved_by": None,
        "notes": "October monthly aggregate; overtime unknown", "payroll_scope": "part_time",
    }
    row.update(changes)
    return row


class OwnerCursor:
    def __init__(self, row, payment_count=0):
        self.row, self.payment_count = row, payment_count
        self.executed = []
        self.result = None

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if sql.startswith("SELECT * FROM labor_entries"):
            self.result = self.row
        elif sql.startswith("SELECT COUNT(*)"):
            self.result = {"payment_count": self.payment_count}
        elif sql.startswith("SELECT after_data"):
            self.result = getattr(self, "previous", None)

    def fetchone(self):
        return self.result


@pytest.fixture
def setup_approval(monkeypatch):
    def setup(row, payment_count=0):
        cursor, audits, events = OwnerCursor(row, payment_count), [], []

        @contextmanager
        def transaction():
            events.append("begin")
            try:
                yield None, cursor
            except Exception:
                events.append("rollback")
                raise
            else:
                events.append("commit")

        def audit(*args):
            assert events == ["begin"]
            audits.append(args)

        monkeypatch.setattr(payroll, "transaction", transaction)
        monkeypatch.setattr(payroll, "audit", audit)
        return cursor, audits, events
    return setup


def payload(row):
    return {"command_id": "12345678-1234-4234-8234-123456789012", "review_revision": payroll.owner_labor_review_revision(row),
            "verified_wages": True, "review_note": "Verified October source wages"}


def test_approval_only_locks_existing_wages_and_keeps_unknowns(setup_approval):
    row = owner_row()
    before = dict(row)
    cursor, audits, events = setup_approval(row)
    result = payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert result["payment_status"] == "unpaid"
    assert row == before
    assert cursor.executed[0][0].endswith("FOR UPDATE")
    writes = [(sql, params) for sql, params in cursor.executed if sql.startswith(("UPDATE", "INSERT"))]
    assert len(writes) == 1
    sql, params = writes[0]
    assert sql == ("UPDATE labor_entries SET approval_status='approved',approved_by=%s,locked_at=NOW(6),review_note=%s,payment_status='unpaid' "
                   "WHERE id=%s AND estate_id=%s")
    assert params == ("owner", payload(row)["review_note"], "owner-1", "estate-1")
    assert audits[0][0] is cursor
    assert audits[0][4]["before"]["overtime_hours"] is None
    assert events == ["begin", "commit"]


@pytest.mark.parametrize("changes", [
    {"person_or_crew": "Giancarlo Pafumi", "regular_hours": Decimal("157"), "hourly_rate_eur": None, "labor_cost_eur": None},
    {"labor_cost_eur": None}, {"labor_cost_eur": 0}, {"labor_cost_eur": -1},
    {"hourly_rate_eur": None}, {"regular_hours": None}, {"hourly_rate_eur": Decimal("NaN")},
    {"approval_status": "approved"}, {"approval_status": "rejected"},
    {"payment_status": "paid"}, {"payment_status": "verification_needed"},
    {"locked_at": "2026-11-02"}, {"paid_at": "2026-11-02"}, {"approved_by": "someone"},
    {"entry_source": "manual"}, {"source_labor_id": "OWNER-RECON-OCT2026-202611020-other"},
    {"worker_username": "worker"},
])
def test_ineligible_rows_fail_closed_without_writes(changes, setup_approval):
    row = owner_row(**changes)
    cursor, audits, events = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert not any(sql.startswith(("UPDATE", "INSERT")) for sql, _ in cursor.executed)
    assert audits == []
    assert events == ["begin", "rollback"]


@pytest.mark.parametrize("field,value", [("regular_hours", 44), ("notes", "changed"),
    ("other_cost_eur", 13), ("person_or_crew", "Vincenzo harvest"), ("overtime_hours", 0)])
def test_stale_review_rejects_any_changed_record(field, value, setup_approval):
    row = owner_row()
    reviewed = payload(row)
    row[field] = value
    cursor, audits, _ = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError, match="changed") as error:
        payroll.approve_owner_labor_record("owner-1", reviewed, "owner", "estate-1")
    assert error.value.status_code == 409
    assert len(cursor.executed) == 2
    assert not audits


def test_payment_history_blocks_approval(setup_approval):
    row = owner_row()
    cursor, audits, _ = setup_approval(row, payment_count=1)
    with pytest.raises(payroll.PayrollDomainError, match="payment history"):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.executed)
    assert not audits


@pytest.mark.parametrize("field", ["other_cost_eur", "expense_amount_eur"])
@pytest.mark.parametrize("amount", [Decimal("12"), Decimal("-1"), Decimal("NaN"), "invalid"])
def test_wages_only_command_rejects_unreviewed_expenses(field, amount, setup_approval):
    row = owner_row(**{field: amount})
    cursor, audits, events = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError, match="expenses require separate reconciliation"):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert row[field] == amount or str(row[field]) == str(amount)
    assert not any(sql.startswith(("UPDATE", "INSERT")) for sql, _ in cursor.executed)
    assert not audits
    assert events == ["begin", "rollback"]


def test_explicit_zero_expenses_are_preserved(setup_approval):
    row = owner_row(other_cost_eur=Decimal("0.00"), expense_amount_eur=Decimal("0.00"))
    _, audits, events = setup_approval(row)
    payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert audits[0][4]["before"]["other_cost_eur"] == 0
    assert events == ["begin", "commit"]


def test_missing_record_and_audit_failure_roll_back(setup_approval, monkeypatch):
    row = owner_row()
    cursor, _, events = setup_approval(None)
    with pytest.raises(payroll.PayrollDomainError) as error:
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert error.value.status_code == 404
    assert events == ["begin", "rollback"]
    cursor, _, events = setup_approval(row)
    def fail_audit(*args):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(payroll, "audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert events == ["begin", "rollback"]


@pytest.mark.parametrize("name,hours,amount,suffix", [
    ("Vincenzo (part-time)", 45, 450, "VINCENZO-PART-TIME"),
    ("Vincenzo (harvest)", 8, 80, "VINCENZO-HARVEST-20261027"),
    ("Carmela", 7, 70, "CARMELA-20261029"),
])
def test_distinct_workers_and_month_anchors_remain_intact(name, hours, amount, suffix, setup_approval):
    row = owner_row(person_or_crew=name, regular_hours=hours, labor_cost_eur=amount,
                    source_labor_id=payroll.OWNER_LABOR_SOURCE_PREFIX + "-" + suffix)
    cursor, audits, _ = setup_approval(row)
    payroll.approve_owner_labor_record("owner-1", payload(row), "owner", "estate-1")
    assert audits[0][4]["before"]["person_or_crew"] == name
    assert audits[0][4]["before"]["work_date"] == "2026-10-01"
    assert not any("app_settings" in sql or "worker_accounts" in sql for sql, _ in cursor.executed)


@pytest.mark.parametrize("extra", [{"verified_wages": False}, {"review_note": ""},
    {"review_revision": ""}, {"hourly_rate_eur": 10}, {"payment_status": "paid"}])
def test_requires_explicit_review_and_disallows_corrections(extra, setup_approval):
    row = owner_row()
    cursor, _, _ = setup_approval(row)
    with pytest.raises(payroll.PayrollDomainError):
        payroll.approve_owner_labor_record("owner-1", {**payload(row), **extra}, "owner", "estate-1")
    assert not cursor.executed


def test_review_returns_revision_of_exact_persisted_row(monkeypatch):
    row = owner_row()
    monkeypatch.setattr(payroll, "fetch_one", lambda sql, params: row)
    result = payroll.owner_labor_review("owner-1", "estate-1")
    assert result["review_revision"] == payload(row)["review_revision"]
    assert result["record"]["work_date"] == "2026-10-01"
    assert result["record"]["overtime_hours"] is None


def test_duplicate_command_returns_recorded_result_and_conflicts_on_change(setup_approval):
    row = owner_row()
    reviewed = payload(row)
    cursor, audits, _ = setup_approval(row)
    first = payroll.approve_owner_labor_record("owner-1", reviewed, "owner", "estate-1")
    assert first["command_id"] == reviewed["command_id"]
    assert first["command_timestamp"].endswith("+00:00")
    cursor.previous = {"after_data": audits[0][4]}
    row["approval_status"] = "approved"
    cursor.executed.clear()
    assert payroll.approve_owner_labor_record("owner-1", reviewed, "owner", "estate-1") == first
    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.executed)
    with pytest.raises(payroll.PayrollDomainError, match="different approval details"):
        payroll.approve_owner_labor_record("owner-1", {**reviewed, "review_note": "Different"}, "owner", "estate-1")
    with pytest.raises(payroll.PayrollDomainError, match="different approval details"):
        payroll.approve_owner_labor_record("owner-1", {**reviewed, "review_revision": "a" * 64}, "owner", "estate-1")


def test_routes_are_admin_only_and_translate_conflicts(monkeypatch):
    routes = [route for route in payroll_admin_routes.router.routes if "/owner-labor/" in route.path]
    assert len(routes) == 2
    assert all(authorize_admin in {dep.dependency for dep in route.dependencies} for route in routes)
    def fail(*args):
        raise payroll.PayrollDomainError("Reload review", 409)
    monkeypatch.setattr(payroll_admin_routes, "approve_owner_labor_record", fail)
    monkeypatch.setattr(payroll_admin_routes, "estate_id", lambda: "estate-1")
    app = FastAPI()
    app.include_router(payroll_admin_routes.router)
    app.dependency_overrides[authorize_admin] = lambda: None
    response = TestClient(app).post("/api/v1/admin/owner-labor/owner-1/approve", json={})
    assert response.status_code == 409
    assert response.json() == {"detail": "Reload review"}


def test_admin_owner_collection_uses_existing_drafts_separately():
    source = (Path(__file__).resolve().parents[1] / "app/main.py").read_text()
    assignment = next(node for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                      and target.id == "owner_labor_reviews" for target in node.targets))
    calls = []
    namespace = {"fetch_all": lambda sql, params: calls.append((sql, params)) or [owner_row()],
                 "estate_id": lambda: "estate-1", "OWNER_LABOR_SOURCE_PREFIX": payroll.OWNER_LABOR_SOURCE_PREFIX}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), "owner_collection", "exec"), namespace)
    sql, params = calls[0]
    assert "worker_username IS NULL AND approval_status='draft'" in sql
    assert "entry_source='owner_reconciliation'" in sql
    assert params == ("estate-1", payroll.OWNER_LABOR_SOURCE_PREFIX + "-%")
    assert namespace["owner_labor_reviews"][0]["overtime_hours"] is None
    assert '"owner_labor_reviews": owner_labor_reviews' in source


def test_owner_ui_monthly_shift_unknown_wages_and_explicit_controls():
    source = (Path(__file__).resolve().parents[1] / "app/static/app.js").read_text()
    functions = source[source.index("function ownerLaborReviewCard"):source.index("function syncAppViewport")]
    script = functions + """
const esc=value=>String(value??''),fmt=value=>String(value),eur=value=>'EUR '+value;
const monthly=ownerLaborReviewCard({id:'m',person_or_crew:'Vincenzo (part-time)',source_labor_id:'OWNER-RECON-OCT2026-20261102-VINCENZO-PART-TIME',work_date:'2026-10-01',regular_hours:45,overtime_hours:null,hourly_rate_eur:10,labor_cost_eur:450},'revision');
const shift=ownerLaborReviewCard({id:'s',person_or_crew:'Vincenzo (harvest)',source_labor_id:'OWNER-RECON-OCT2026-20261102-VINCENZO-HARVEST-20261027',work_date:'2026-10-27',regular_hours:8,overtime_hours:null,hourly_rate_eur:10,labor_cost_eur:80});
const worksheet=ownerLaborReviewCard({id:'g',person_or_crew:'Giancarlo Pafumi',source_labor_id:'OWNER-RECON-OCT2026-20261102-GIANCARLO',work_date:'2026-10-01',regular_hours:157,overtime_hours:null,hourly_rate_eur:null,labor_cost_eur:null},'revision');
const expenses=ownerLaborReviewCard({id:'e',person_or_crew:'Vincenzo',regular_hours:45,hourly_rate_eur:10,labor_cost_eur:450,expense_amount_eur:12},'revision');
console.log(JSON.stringify({monthly,shift,worksheet,expenses}));
"""
    rendered = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert "October 2026 month total" in rendered["monthly"]
    assert "month anchor" in rendered["monthly"]
    assert "Vincenzo (part-time)" in rendered["monthly"]
    assert "Actual shift date · 2026-10-27" in rendered["shift"]
    assert "Vincenzo (harvest)" in rendered["shift"]
    assert "overtime unknown" in rendered["monthly"]
    assert "157 regular hours" in rendered["worksheet"]
    assert "Validated wages unknown" in rendered["worksheet"]
    assert "Awaiting normal payroll worksheet review" in rendered["worksheet"]
    assert "data-owner-approve" not in rendered["worksheet"]
    assert "Additional expenses require separate reconciliation" in rendered["expenses"]
    assert "data-owner-approve" not in rendered["expenses"]
    assert 'data-owner-approve disabled' in rendered["monthly"]
    assert 'type="checkbox" data-owner-verified>' in rendered["monthly"]
    assert 'data-owner-note></textarea>' in rendered["monthly"]
    assert "data-worker-review" not in rendered["monthly"]
    assert "worker-labor/" not in functions
    assert "crypto.randomUUID()" in functions


def test_olive_volume_conversion_is_not_presented_as_mass_yield():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text()
    source = (root / "app/static/assets/olives-planning.js").read_text()
    render_metrics = next(line for line in source.splitlines() if "$('oliveKg').textContent" in line)
    script = """
const nodes={}; const $=id=>(nodes[id]??={}); const known=value=>value??'Unknown',fmt=value=>String(value);
let m={olives_kg:695,oil_liters:89.5,avg_yield_pct:12.9,labor_hours:70};
""" + render_metrics + "\nconsole.log(JSON.stringify(nodes));"
    rendered = json.loads(subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True).stdout)
    assert rendered["oliveYield"]["textContent"] == "12.9"
    assert 'Oil conversion</span><strong id="oliveYield"' in html
    assert "L/100 kg · recorded volume conversion" in html
    assert "recorded milling yield" not in html
    assert '<option value="avg_yield_pct">Oil conversion L/100 kg</option>' in html
    render_chart = next(line for line in source.splitlines() if "const measure=$('oliveMeasure')" in line)
    chart_script = """
const $=()=>({value:'avg_yield_pct'}),yearLabels=['2026'],history=[{avg_yield_pct:12.9}],numeric=Number;
const barChart=(...args)=>console.log(JSON.stringify(args));
""" + render_chart
    chart = json.loads(subprocess.run(["node", "-e", chart_script], check=True, capture_output=True, text=True).stdout)
    assert chart[2] == [12.9]
    assert chart[5] == "L/100 kg"
