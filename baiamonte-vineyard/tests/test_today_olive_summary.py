from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_today_page_has_compact_database_backed_olive_summary():
    markup = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/assets/operations-enhancements.js").read_text(encoding="utf-8")
    assert 'id="todayOlivePanel"' in markup
    assert 'data-jump="olives"' in markup
    for node_id in ("todayOliveStrategy", "todayOliveDate", "todayOliveWindow", "todayOliveSeason", "todayOliveGuidance"):
        assert f'id="{node_id}"' in markup
    assert "const olives=state.olives" in javascript
    assert "harvest_preference" in javascript
    assert "harvest_forecast" in javascript
    assert "training_samples" in javascript
    assert "metrics.olives_kg" in javascript


def test_today_olive_summary_has_missing_data_and_readiness_guardrails():
    javascript = (ROOT / "app/static/assets/operations-enhancements.js").read_text(encoding="utf-8")
    assert "if(!olives)" in javascript
    assert "The olive dashboard did not load" in javascript
    assert "representative fruit maturity" in javascript
    assert "same-day mill capacity" in javascript


def test_today_lists_scroll_only_when_their_content_overflows():
    css = (ROOT / "app/static/control-center.css").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/assets/operations-enhancements.js").read_text(encoding="utf-8")
    assert "#view-today .list{max-height:" in css
    assert "node.scrollHeight>node.clientHeight+2" in javascript
    assert "stepTodayAutoScroll" in javascript
    assert "prefers-reduced-motion: reduce" in javascript
    assert "touchstart" in javascript


def test_today_alert_ticker_crosses_the_full_screen_without_early_clipping():
    css = (ROOT / "app/static/control-center.css").read_text(encoding="utf-8")
    assert "@keyframes todayAlertTicker{from{transform:translateX(100vw)}to{transform:translateX(-100%)}}" in css
    assert "animation-name:todayAlertTicker" in css


def test_today_alerts_use_the_complete_database_dashboard_feed():
    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    alerts = (ROOT / "app/static/assets/alerts.js").read_text(encoding="utf-8")
    application = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    dashboard_query = backend.split('"alerts": fetch_all(', 1)[1].split(", (estate_id(),)", 1)[0]
    assert "LIMIT 8" not in dashboard_query
    assert "today=state.dashboard?.alerts||[]" in alerts
    assert "all.slice(0,3)" not in alerts
    assert "urgent=(state.dashboard?.alerts||[])" in application


def test_today_uses_estate_timezone_and_explains_historical_context():
    application = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/assets/operations-enhancements.js").read_text(encoding="utf-8")
    assert "const estateYear=Number(new Intl.DateTimeFormat('en',{timeZone:'Europe/Rome'" in application
    assert "state={year:estateYear" in application
    assert "function renderTodayContext()" in javascript
    assert "timeZone:'Europe/Rome'" in javascript
    assert "vintage review · estate systems below remain live" in javascript


def test_only_the_intelligence_alert_list_auto_scrolls():
    markup = (ROOT / "app/static/display.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/display.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/display-extra.css").read_text(encoding="utf-8")
    assert 'class="card intelligence-alert-card"' in markup
    assert "function scrollIntelligenceAlerts()" in javascript
    assert "const node=$('tvAlerts')" in javascript
    assert "(dash.alerts||[]).map(" in javascript
    assert ".intelligence-alert-card #tvAlerts" in css
