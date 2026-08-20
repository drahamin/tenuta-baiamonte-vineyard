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
    assert "cancelAnimationFrame(todayScrollFrame)" in javascript
    assert "todayActive&&hasScrollableList" in javascript
    assert 'button[data-view="today"]' in javascript


def test_today_alert_ticker_crosses_the_full_screen_without_early_clipping():
    css = (ROOT / "app/static/control-center.css").read_text(encoding="utf-8")
    assert "@keyframes todayAlertTicker{from{transform:translateX(100vw)}to{transform:translateX(-100%)}}" in css
    assert "animation-name:todayAlertTicker" in css


def test_today_alerts_use_the_complete_live_database_feed():
    backend = (ROOT / "app/main.py").read_text(encoding="utf-8")
    alerts = (ROOT / "app/static/assets/alerts.js").read_text(encoding="utf-8")
    application = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    dashboard_query = backend.split('"alerts": fetch_all(', 1)[1].split(", (estate_id(),)", 1)[0]
    assert "LIMIT 8" not in dashboard_query
    assert "const all=state.alerts||[]" in alerts
    assert "all.slice(0,3)" not in alerts
    assert "const shown=id==='alertList'?rows:all" in alerts
    assert "ORDER BY FIELD(severity,'critical','warning','info'),triggered_at DESC LIMIT 250" in backend
    assert "urgent=(state.alerts||[])" in application
    assert "$('openAlerts').textContent=state.alerts.length" in application


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
    assert "activeAlerts=(dash.alerts||[]).filter(" in javascript
    assert "rows.find(row=>row.offsetTop>node.scrollTop+2)" in javascript
    assert "node.scrollTop=next?next.offsetTop:0" in javascript
    assert "intelligenceAlertScrollInitialized" in javascript
    assert 'id="tvAlertCycleStatus"' in markup
    assert ".intelligence-alert-card #tvAlerts" in css


def test_tv_lab_card_is_a_compact_decision_brief():
    markup = (ROOT / "app/static/display.html").read_text(encoding="utf-8")
    javascript = (ROOT / "app/static/display.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/display-extra.css").read_text(encoding="utf-8")
    assert "Latest lab decision" in markup
    assert "function labDecisionBrief(labs={})" in javascript
    assert "NO ACTION FLAGGED" in javascript
    assert "NEXT ACTION" in javascript
    assert "more awaiting review" in javascript
    assert ".lab-decision-body" in css


def test_tv_overflow_lists_scroll_on_today_intelligence_planning_etna_and_communications():
    javascript = (ROOT / "app/static/display.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/display-extra.css").read_text(encoding="utf-8")
    assert "0:['tvTasks']" in javascript
    assert "2:['tvLabs']" not in javascript
    assert "7:['tvPriorityTasks','tvUpcomingPlan','tvHospitalityPlan','tvCalendar']" in javascript
    assert "10:['tvEtnaNotices']" in javascript
    assert "11:['tvRecentCommunications','tvCommunicationReview','tvCommunicationAlerts']" in javascript
    assert "function scrollTvOverflowLists()" in javascript
    assert "replaceTvOverflowList('tvTasks',nextWork.map(" in javascript
    assert "todayCanonicalTasks=d.system_status?.planning?.work_items?.length" in javascript
    assert "replaceTvOverflowList('tvUpcomingPlan',upcoming.map(" in javascript
    assert "replaceTvOverflowList('tvEtnaNotices',notices.length?notices.map(" in javascript
    assert "replaceTvOverflowList('tvRecentCommunications',recent.map(" in javascript
    assert "$('tvLabs').innerHTML=labDecisionBrief(d.labs)" in javascript
    assert "nextWork.slice(0,8)" not in javascript
    assert "upcoming.slice(0,8)" not in javascript
    assert "notices.slice(0,5)" not in javascript
    assert "recent.slice(0,7)" not in javascript
    assert "if(item.signature!==content)" in javascript
    assert "rows.find(row=>row.offsetTop-node.offsetTop>node.scrollTop+2)" in javascript
    assert "node.scrollTop=target" in javascript
    assert "item.nextAdvance=now+(next?5500:3200)" in javascript
    assert ".planning-tv-grid .rows{display:block;height:calc(100% - 2.7vh);min-height:0;overflow:hidden}" in css
    assert ".tv-etna-grid #tvEtnaNotices,.communications-tv-grid .tv-communications-list{height:calc(100% - 3vh);min-height:0;overflow:hidden}" in css
    assert ".intelligence-bottom #tvLabs{height:calc(100% - 3.2vh);min-height:0;overflow:hidden}" in css


def test_tv_communications_hide_message_details_and_use_compact_rows():
    javascript = (ROOT / "app/static/display.js").read_text(encoding="utf-8")
    css = (ROOT / "app/static/display-extra.css").read_text(encoding="utf-8")
    row_source = javascript.split("function communicationRow", 1)[1].split("function renderCommunicationsDisplay", 1)[0]
    assert "item.summary" not in row_source
    assert "<small>" not in row_source
    assert "grid-template-columns:1.65vw minmax(0,1fr) auto" in css
