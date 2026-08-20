from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_review_acknowledges_live_alerts_instead_of_resolving_them():
    source = (ROOT / "app/static/assets/alerts.js").read_text(encoding="utf-8")
    assert "data-alert-acknowledge" in source
    assert "JSON.stringify({status:'acknowledged'})" in source
    assert "data-alert-resolve" not in source


def test_today_and_issues_describe_distinct_active_workflows():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert '<span>Active alerts</span><strong id="openAlerts">' in html
    assert "<h2>Active alerts</h2>" in html
    assert "Active issues &amp; follow-up" in html
    assert "Monitoring remains active until follow-up is complete." in html
    assert 'id="issueList" class="list empty" tabindex="0"' in html


def test_issue_lifecycle_closes_terminal_states_and_clears_closure_when_reopened():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert 'values.get("status") in {"resolved", "deferred"}' in source
    assert 'values.get("status") in {"open", "monitoring"}' in source
    assert 'values["closed_date"] = None' in source
    assert "status IN ('resolved','deferred')" in source
    assert "closed_date IS NULL AND opened_date BETWEEN %s AND %s" in source
