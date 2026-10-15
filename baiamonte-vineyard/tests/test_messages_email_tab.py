from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dedicated_email_page_mounts_and_loads_the_complete_gmail_panel():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    messaging = (ROOT / "app/static/assets/messaging.js").read_text(encoding="utf-8")

    assert 'data-view="mail" data-admin' in html
    assert 'id="view-mail"' in html
    assert 'id="mailPageMount"' in html
    assert 'id="mailInboxSummary"' in html
    assert 'id="mailNewBanner"' in html
    assert 'id="openUnreadMail"' in html
    assert "mount.append(gmail)" in messaging
    assert "renderMailboxSummary" in messaging
    assert "unread_total" in (ROOT / "app/mailbox.py").read_text(encoding="utf-8")
    assert "function setupMailPage()" in messaging
    assert "if(view==='mail')" in (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    dashboard = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert "channel==='gmail'?'mail':'whatsapp'" in dashboard


def test_mail_dialog_controls_bind_from_the_feature_and_startup_paths():
    messaging = (ROOT / "app/static/assets/messaging.js").read_text(encoding="utf-8")
    app = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    bootstrap = (ROOT / "app/static/bootstrap.js").read_text(encoding="utf-8")

    assert "function bindMailDialog()" in messaging
    assert "dialog.dataset.mailBound==='1'" in messaging
    assert "setupMailPage(){bindMailDialog();" in messaging
    assert "bindMailDialog();$('mailDialog').showModal()" in messaging
    assert "if(typeof bindMailDialog==='function')bindMailDialog();" in app
    assert "if (typeof bindCommunications === 'function') bindCommunications();" in bootstrap
