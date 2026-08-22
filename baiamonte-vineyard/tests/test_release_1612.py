from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_messaging_social_and_tv_start_independently():
    javascript = (ROOT / "app/static/app.js").read_text()
    assert "initializeFeature('communications',bindCommunications)" in javascript
    assert "initializeFeature('social',bindSocial)" in javascript
    assert "initializeFeature('TV configuration',bindTvConfig)" in javascript
    assert "function loadViewFeature(view)" in javascript
    assert "Promise.resolve(loadSocial()).catch" in javascript
    assert "Promise.resolve(loadTvConfig()).catch" in javascript


def test_bootstrap_has_independent_page_load_fallbacks():
    javascript = (ROOT / "app/static/bootstrap.js").read_text()
    assert "inbox: () => window.loadCommunications?.(true)" in javascript
    assert "social: () => window.loadSocial?.()" in javascript
    assert "'tv-config': () => window.loadTvConfig?.()" in javascript
    assert "fallback load failed" in javascript


def test_hospitality_dashboard_rechecks_downloaded_gmail_messages():
    hospitality = (ROOT / "app/domains/hospitality.py").read_text()
    routes = (ROOT / "app/domains/hospitality_routes.py").read_text()
    assert "def dashboard(" in hospitality
    dashboard_body = hospitality.split("def dashboard(", 1)[1].split("def ", 1)[0]
    assert "sync_hospitality_inquiries()" in dashboard_body
    assert "downloaded = poll_gmail_once()" in routes
    assert "routed = sync_hospitality_inquiries()" in routes
