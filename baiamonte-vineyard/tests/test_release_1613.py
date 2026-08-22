from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_messaging_page_owns_and_restores_its_tab_state():
    messaging = (ROOT / "app/static/assets/messaging.js").read_text()
    assert "function activateMessagingPanel(name='contacts')" in messaging
    assert "setupWhatsappPage();if(withMailbox" in messaging
    assert "view.querySelectorAll('[data-communication]')" in messaging
    assert "activateMessagingPanel(view?.querySelector" in messaging


def test_cached_communications_are_rendered_when_messaging_opens():
    javascript = (ROOT / "app/static/app.js").read_text()
    loader = javascript.split("function loadViewFeature(view)", 1)[1].split("initializeFeature", 1)[0]
    assert "if(view==='whatsapp')" in loader
    assert "if(state.communications)" in loader
    assert "renderSafely('messaging',renderCommunications)" in loader
    assert "activateMessagingPanel(selected)" in loader


def test_review_tabs_do_not_override_messaging_tabs():
    javascript = (ROOT / "app/static/app.js").read_text()
    binder = javascript.split("function bindCommunications()", 1)[1].split("function socialPost", 1)[0]
    assert "button.closest('#view-whatsapp')" in binder
    assert "activateMessagingPanel(button.dataset.communication);return" in binder


def test_late_analytics_bundle_does_not_stop_messaging_initialization():
    javascript = (ROOT / "app/static/app.js").read_text()
    assert "onchange=()=>window.renderGrapeHistory?.()" in javascript
    assert "onchange=()=>window.renderCellarHistory?.()" in javascript
    startup_tail = javascript.split("onchange=()=>window.renderGrapeHistory?.()", 1)[1]
    assert "loadEtna(false)" in startup_tail
    assert "initializeFeature('WhatsApp page',setupWhatsappPage)" in startup_tail
