from types import SimpleNamespace

from app.domains.communications_twilio_voice_routes import (
    _call_channel,
    _forward_choice,
    _spoken_menu,
    _twilio_api_auth,
    _twilio_signature,
    _valid_call_address,
    twilio_voice_status,
    verify_twilio_resources,
)


def test_twilio_signature_is_deterministic_and_parameter_order_independent():
    url = "https://example.ui.nabu.casa/webhooks/twilio/voice"
    first = _twilio_signature(url, [("From", "whatsapp:+3901"), ("CallSid", "CA123")], "secret")
    second = _twilio_signature(url, [("CallSid", "CA123"), ("From", "whatsapp:+3901")], "secret")
    assert first == second
    assert first


def test_voice_readiness_never_exposes_credentials():
    settings = SimpleNamespace(
        twilio_voice_enabled=True,
        twilio_pstn_enabled=True,
        twilio_pstn_phone_number_sids="PN123, PN456",
        twilio_sip_enabled=True,
        twilio_sip_domain_sids="SD123",
        twilio_outbound_enabled=True,
        twilio_outbound_caller_id="+3900000000",
        twilio_forwarding_enabled=True,
        twilio_forwarding_target="sip:reception@example.sip.twilio.com",
        twilio_account_sid="AC123",
        twilio_auth_token="private-auth-token",
        twilio_api_key_sid="SK123",
        twilio_api_key_secret="private-api-secret",
        twilio_voice_application_sid="AP123",
        twilio_whatsapp_sender_sid="XE123",
        twilio_voice_webhook_url="https://example.ui.nabu.casa/webhooks/twilio/voice",
    )
    status = twilio_voice_status(settings)
    assert status["ready"] is True
    assert status["api_access_configured"] is True
    assert "private-auth-token" not in str(status)
    assert "private-api-secret" not in str(status)
    assert status["status_callback_url"].endswith("/voice/status")
    assert status["channels"]["pstn"]["lines"] == 2
    assert status["channels"]["sip"]["lines"] == 1
    assert status["forwarding"]["target_type"] == "sip"
    assert "reception@example" not in str(status)


def test_company_reception_ivr_is_branded_and_clear_in_both_languages():
    english = _spoken_menu("reception", False, False)
    italian = _spoken_menu("reception", True, False)
    assert "Tenuta Baiamonte" in english
    assert "Mount Etna" in english
    assert "WhatsApp chat" in english
    assert "Tenuta Baiamonte" in italian
    assert "Etna" in italian
    assert "chat WhatsApp" in italian


def test_manager_ivr_preserves_admin_only_choice():
    assert "9, team and finance" not in _spoken_menu("manager", False, False)
    assert "9, team and finance" in _spoken_menu("manager", False, True)
    assert "13, call reception" in _spoken_menu("manager", False, True)


def test_twilio_call_channels_are_classified_without_guessing():
    assert _call_channel({"From": "whatsapp:+3901"}) == "whatsapp"
    assert _call_channel({"From": "+3901", "To": "+1202"}) == "pstn"
    assert _call_channel({"From": "sip:worker@baiamonte.sip.twilio.com", "SipDomainSid": "SD123"}) == "sip"


def test_forwarding_choices_and_addresses_are_bounded():
    assert _forward_choice("reception", "5")
    assert _forward_choice("reporter", "9")
    assert _forward_choice("manager", "13")
    assert _valid_call_address("+3900000000")
    assert _valid_call_address("sip:reception@example.sip.twilio.com")
    assert not _valid_call_address("3900000000")
    assert not _valid_call_address("https://example.com")


def test_twilio_api_prefers_revocable_api_key():
    settings = SimpleNamespace(
        twilio_account_sid="AC123", twilio_auth_token="account-token",
        twilio_api_key_sid="SK123", twilio_api_key_secret="key-secret",
    )
    assert _twilio_api_auth(settings) == ("SK123", "key-secret", "api_key")


def test_twilio_resource_verification_matches_app_and_sender(monkeypatch):
    settings = SimpleNamespace(
        twilio_account_sid="AC123", twilio_auth_token="account-token",
        twilio_api_key_sid="SK123", twilio_api_key_secret="key-secret",
        twilio_voice_application_sid="AP123", twilio_whatsapp_sender_sid="XE123",
        twilio_voice_enabled=True, twilio_pstn_enabled=True, twilio_pstn_phone_number_sids="PN123",
        twilio_sip_enabled=True, twilio_sip_domain_sids="SD123",
        twilio_voice_webhook_url="https://example.test/webhooks/twilio/voice",
    )

    def fake_json(_, url):
        if "Applications" in url:
            return {
                "sid": "AP123", "friendly_name": "Baiamonte Company IVR", "voice_method": "POST",
                "voice_url": settings.twilio_voice_webhook_url,
                "status_callback": settings.twilio_voice_webhook_url + "/status",
            }
        if "IncomingPhoneNumbers" in url:
            return {"sid": "PN123", "friendly_name": "Baiamonte PSTN", "phone_number": "+3900000000", "capabilities": {"voice": True}, "voice_application_sid": "AP123"}
        if "/SIP/Domains/" in url:
            return {"sid": "SD123", "domain_name": "baiamonte.sip.twilio.com", "auth_type": "CREDENTIAL_LIST", "voice_url": settings.twilio_voice_webhook_url}
        return {"sid": "XE123", "status": "ONLINE", "configuration": {"voice_application_sid": "AP123"}}

    monkeypatch.setattr("app.domains.communications_twilio_voice_routes._twilio_json", fake_json)
    result = verify_twilio_resources(settings)
    assert result["ready"] is True
    assert result["authentication"] == "api_key"
    assert result["channels"] == {"whatsapp": True, "pstn": True, "sip": True}
