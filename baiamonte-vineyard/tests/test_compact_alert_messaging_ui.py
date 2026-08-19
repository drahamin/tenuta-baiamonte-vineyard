from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alert_and_messaging_secondary_tools_are_compact_and_expandable():
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "control-center.css").read_text(encoding="utf-8")

    assert 'class="panel communication-hub compact-hub"' in markup
    assert 'class="inbox-utility-grid"' in markup
    assert 'class="panel message-settings-panel"' in markup
    assert '.compact-section-summary' in styles
    assert '.inbox-utility-grid{display:grid;grid-template-columns:1fr 1fr' in styles


def test_alert_delivery_rules_use_responsive_columns_without_hiding_fields():
    markup = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "app" / "static" / "control-center.css").read_text(encoding="utf-8")
    alert_source = (ROOT / "app" / "static" / "assets" / "alerts.js").read_text(encoding="utf-8")

    assert 'id="alertRules"' in markup
    assert '#view-alert-settings .alert-rules{grid-template-columns:' in styles
    assert 'name="email_recipients"' in alert_source
    assert 'name="whatsapp_recipients"' in alert_source
    assert 'name="whatsapp_template_name"' in alert_source
