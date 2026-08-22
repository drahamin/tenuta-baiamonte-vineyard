from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dedicated_email_page_mounts_and_loads_the_complete_gmail_panel():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    messaging = (ROOT / "app/static/assets/messaging.js").read_text(encoding="utf-8")

    assert 'data-view="mail" data-admin' in html
    assert 'id="view-mail"' in html
    assert 'id="mailPageMount"' in html
    assert "mount.append(gmail)" in messaging
    assert "function setupMailPage()" in messaging
    assert "if(view==='mail')" in (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    dashboard = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "channel==='gmail'?'mail':'whatsapp'" in dashboard
