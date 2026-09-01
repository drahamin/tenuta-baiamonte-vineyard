"""Twilio WhatsApp, PSTN and SIP calling webhook for the Baiamonte IVR."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from ..access import authorize_admin
from ..config import Settings, get_settings
from ..db import transaction
from ..service import estate_id
from ..whatsapp_intent import menu_route
from .communications_meta import sender_profile
from .whatsapp_live import humanize_reply, live_snapshot


router = APIRouter(tags=["communications"])


def _split_sids(value: Any, prefix: str) -> list[str]:
    return [item for item in re.split(r"[\s,]+", str(value or "").strip()) if item.startswith(prefix)]


def _twilio_api_auth(settings: Settings) -> tuple[str, str, str]:
    if settings.twilio_api_key_sid and settings.twilio_api_key_secret:
        return settings.twilio_api_key_sid, settings.twilio_api_key_secret, "api_key"
    return settings.twilio_account_sid, settings.twilio_auth_token, "auth_token"


def _twilio_json(settings: Settings, url: str) -> dict[str, Any]:
    username, password, _ = _twilio_api_auth(settings)
    if not settings.twilio_account_sid or not username or not password:
        raise HTTPException(503, "Twilio API credentials are not configured")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = UrlRequest(url, headers={"Authorization": f"Basic {token}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode())
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode()).get("message")
        except Exception:
            detail = None
        raise HTTPException(502, f"Twilio API rejected the request: {detail or error.reason}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(502, "Twilio API is temporarily unavailable") from error


def _twilio_form(settings: Settings, url: str, values: dict[str, str]) -> dict[str, Any]:
    """Post a protected form to Twilio; used only by an authenticated admin action."""
    username, password, _ = _twilio_api_auth(settings)
    if not settings.twilio_account_sid or not username or not password:
        raise HTTPException(503, "Twilio API credentials are not configured")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = UrlRequest(
        url,
        data=urlencode(values).encode(),
        headers={"Authorization": f"Basic {token}", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode()).get("message")
        except Exception:
            detail = None
        raise HTTPException(502, f"Twilio API rejected the outbound call: {detail or error.reason}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise HTTPException(502, "Twilio outbound calling is temporarily unavailable") from error


def verify_twilio_resources(settings: Settings) -> dict[str, Any]:
    """Read back the configured Twilio resources without exposing credentials or changing them."""
    _, _, auth_mode = _twilio_api_auth(settings)
    result: dict[str, Any] = {"checked": True, "authentication": auth_mode}
    if settings.twilio_voice_application_sid:
        app = _twilio_json(
            settings,
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.twilio_account_sid}/Applications/{settings.twilio_voice_application_sid}.json",
        )
        configured_url = str(settings.twilio_voice_webhook_url or "").rstrip("/")
        result["voice_application"] = {
            "found": str(app.get("sid") or "") == settings.twilio_voice_application_sid,
            "friendly_name": app.get("friendly_name"),
            "voice_method": app.get("voice_method"),
            "voice_url_matches": str(app.get("voice_url") or "").rstrip("/") == configured_url,
            "status_callback_matches": str(app.get("status_callback") or "").rstrip("/") == configured_url + "/status",
        }
    else:
        result["voice_application"] = {"found": False, "reason": "not configured"}
    if settings.twilio_whatsapp_sender_sid:
        sender = _twilio_json(
            settings,
            f"https://messaging.twilio.com/v2/Channels/Senders/{settings.twilio_whatsapp_sender_sid}",
        )
        configuration = sender.get("configuration") or {}
        result["whatsapp_sender"] = {
            "found": str(sender.get("sid") or "") == settings.twilio_whatsapp_sender_sid,
            "status": sender.get("status"),
            "sender": sender.get("sender_id") or sender.get("sender"),
            "voice_application_matches": configuration.get("voice_application_sid") == settings.twilio_voice_application_sid,
        }
    else:
        result["whatsapp_sender"] = {"found": False, "reason": "not configured"}
    pstn_numbers = []
    for sid in _split_sids(getattr(settings, "twilio_pstn_phone_number_sids", ""), "PN"):
        number = _twilio_json(
            settings,
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.twilio_account_sid}/IncomingPhoneNumbers/{sid}.json",
        )
        pstn_numbers.append({
            "sid": sid,
            "found": str(number.get("sid") or "") == sid,
            "friendly_name": number.get("friendly_name"),
            "phone_number_suffix": str(number.get("phone_number") or "")[-4:] or None,
            "voice_capable": bool((number.get("capabilities") or {}).get("voice")),
            "voice_application_matches": number.get("voice_application_sid") == settings.twilio_voice_application_sid,
            "trunk_sid": number.get("trunk_sid"),
        })
    result["pstn_numbers"] = pstn_numbers
    sip_domains = []
    configured_url = str(settings.twilio_voice_webhook_url or "").rstrip("/")
    for sid in _split_sids(getattr(settings, "twilio_sip_domain_sids", ""), "SD"):
        domain = _twilio_json(
            settings,
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{settings.twilio_account_sid}/SIP/Domains/{sid}.json",
        )
        sip_domains.append({
            "sid": sid,
            "found": str(domain.get("sid") or "") == sid,
            "friendly_name": domain.get("friendly_name"),
            "domain_name": domain.get("domain_name"),
            "authentication": domain.get("auth_type"),
            "voice_url_matches": str(domain.get("voice_url") or "").rstrip("/") == configured_url,
        })
    result["sip_domains"] = sip_domains
    app_ready = bool(result["voice_application"].get("found") and result["voice_application"].get("voice_url_matches"))
    channel_checks = {
        "whatsapp": not bool(getattr(settings, "twilio_voice_enabled", False)) or bool(
            app_ready and result["whatsapp_sender"].get("found") and result["whatsapp_sender"].get("voice_application_matches")
        ),
        "pstn": not bool(getattr(settings, "twilio_pstn_enabled", False)) or bool(
            app_ready and pstn_numbers and all(item["found"] and item["voice_capable"] and item["voice_application_matches"] for item in pstn_numbers)
        ),
        "sip": not bool(getattr(settings, "twilio_sip_enabled", False)) or bool(
            sip_domains and all(item["found"] and item["voice_url_matches"] and item["authentication"] for item in sip_domains)
        ),
    }
    result["channels"] = channel_checks
    enabled_any = bool(
        getattr(settings, "twilio_voice_enabled", False)
        or getattr(settings, "twilio_pstn_enabled", False)
        or getattr(settings, "twilio_sip_enabled", False)
    )
    result["ready"] = bool(enabled_any and all(channel_checks.values()))
    return result


def twilio_voice_status(settings: Settings) -> dict[str, Any]:
    """Return secret-free readiness for the administrator and installer."""
    webhook_url = str(settings.twilio_voice_webhook_url or "").strip()
    valid_webhook = webhook_url.startswith("https://") and webhook_url.rstrip("/").endswith("/webhooks/twilio/voice")
    whatsapp_ready = bool(
        settings.twilio_voice_enabled and settings.twilio_voice_application_sid
        and settings.twilio_whatsapp_sender_sid and valid_webhook
    )
    pstn_sids = _split_sids(getattr(settings, "twilio_pstn_phone_number_sids", ""), "PN")
    pstn_ready = bool(getattr(settings, "twilio_pstn_enabled", False) and pstn_sids and settings.twilio_voice_application_sid and valid_webhook)
    sip_sids = _split_sids(getattr(settings, "twilio_sip_domain_sids", ""), "SD")
    sip_ready = bool(getattr(settings, "twilio_sip_enabled", False) and sip_sids and valid_webhook)
    any_channel_enabled = bool(settings.twilio_voice_enabled or getattr(settings, "twilio_pstn_enabled", False) or getattr(settings, "twilio_sip_enabled", False))
    channels = {
        "whatsapp": {"enabled": bool(settings.twilio_voice_enabled), "configured": whatsapp_ready, "lines": 1 if settings.twilio_whatsapp_sender_sid else 0},
        "pstn": {"enabled": bool(getattr(settings, "twilio_pstn_enabled", False)), "configured": pstn_ready, "lines": len(pstn_sids)},
        "sip": {"enabled": bool(getattr(settings, "twilio_sip_enabled", False)), "configured": sip_ready, "lines": len(sip_sids)},
    }
    enabled_channels_ready = all(item["configured"] for item in channels.values() if item["enabled"])
    return {
        "enabled": bool(settings.twilio_voice_enabled),
        "service_enabled": any_channel_enabled,
        "account_configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
        "api_access_configured": bool(settings.twilio_account_sid and settings.twilio_api_key_sid and settings.twilio_api_key_secret),
        "voice_application_configured": bool(settings.twilio_voice_application_sid),
        "whatsapp_sender_linked": bool(settings.twilio_whatsapp_sender_sid),
        "webhook_configured": valid_webhook,
        "webhook_url": webhook_url or None,
        "status_callback_url": webhook_url.rstrip("/") + "/status" if valid_webhook else None,
        "ready": bool(
            any_channel_enabled
            and settings.twilio_account_sid
            and settings.twilio_auth_token
            and valid_webhook
            and enabled_channels_ready
        ),
        "channels": channels,
        "outbound": {
            "enabled": bool(getattr(settings, "twilio_outbound_enabled", False)),
            "caller_id_configured": bool(getattr(settings, "twilio_outbound_caller_id", "")),
            "ready": bool(getattr(settings, "twilio_outbound_enabled", False) and getattr(settings, "twilio_outbound_caller_id", "") and settings.twilio_account_sid),
        },
        "forwarding": {
            "enabled": bool(getattr(settings, "twilio_forwarding_enabled", False)),
            "target_configured": bool(getattr(settings, "twilio_forwarding_target", "")),
            "target_type": "sip" if str(getattr(settings, "twilio_forwarding_target", "")).lower().startswith("sip:") else "pstn" if getattr(settings, "twilio_forwarding_target", "") else None,
            "ready": bool(getattr(settings, "twilio_forwarding_enabled", False) and getattr(settings, "twilio_forwarding_target", "") and getattr(settings, "twilio_outbound_caller_id", "")),
        },
        "provider": "Twilio Programmable Voice",
        "messaging_separate": True,
    }


def _signature_url(request: Request, settings: Settings, status: bool = False) -> str:
    configured = str(settings.twilio_voice_webhook_url or "").strip().rstrip("/")
    if configured:
        if status:
            return configured + "/status"
        if str(request.url.path).rstrip("/").endswith("/outbound"):
            return configured + "/outbound"
        if str(request.url.path).rstrip("/").endswith("/menu"):
            return configured + "/menu"
        return configured
    return str(request.url)


def _twilio_signature(url: str, params: list[tuple[str, str]], auth_token: str) -> str:
    """Implement Twilio's form-webhook HMAC-SHA1 validation algorithm."""
    material = url + "".join(key + value for key, value in sorted(params, key=lambda pair: (pair[0], pair[1])))
    digest = hmac.new(auth_token.encode(), material.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _validate_twilio(request: Request, params: list[tuple[str, str]], settings: Settings, *, status: bool = False) -> None:
    service_enabled = bool(
        settings.twilio_voice_enabled
        or getattr(settings, "twilio_pstn_enabled", False)
        or getattr(settings, "twilio_sip_enabled", False)
    )
    if not service_enabled or not settings.twilio_auth_token:
        raise HTTPException(503, "Baiamonte Twilio voice calling is not enabled")
    supplied = str(request.headers.get("X-Twilio-Signature") or "")
    expected = _twilio_signature(_signature_url(request, settings, status), params, settings.twilio_auth_token)
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(403, "Invalid Twilio webhook signature")


def _clean_number(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _call_channel(values: dict[str, Any]) -> str:
    caller = str(values.get("From") or "").lower()
    called = str(values.get("To") or "").lower()
    if caller.startswith("whatsapp:") or called.startswith("whatsapp:"):
        return "whatsapp"
    if values.get("SipDomainSid") or caller.startswith("sip:") or called.startswith("sip:"):
        return "sip"
    return "pstn"


def _channel_enabled(channel: str, settings: Settings) -> bool:
    return {
        "whatsapp": bool(settings.twilio_voice_enabled),
        "pstn": bool(getattr(settings, "twilio_pstn_enabled", False)),
        "sip": bool(getattr(settings, "twilio_sip_enabled", False)),
    }.get(channel, False)


def _caller_lookup_key(caller: str, channel: str) -> str:
    if channel != "sip":
        return _clean_number(caller)
    match = re.match(r"sip:\+?(\d+)@", caller, re.I)
    return match.group(1) if match else ""


def _valid_call_address(value: str, *, allow_sip: bool = True) -> bool:
    target = str(value or "").strip()
    if re.fullmatch(r"\+[1-9]\d{7,14}", target):
        return True
    return bool(allow_sip and re.fullmatch(r"sip:[^\s<>@]+@[^\s<>@]+", target, re.I))


def _forward_choice(profile: str, choice: str) -> bool:
    return choice == {"reception": "5", "reporter": "9", "manager": "13"}.get(profile)


def _voice_language(assignment: dict[str, Any], caller: str) -> tuple[bool, str]:
    configured = str(assignment.get("language") or "auto")
    if not assignment.get("contact"):
        configured = str((assignment.get("settings") or {}).get("calling_guest_language") or configured)
    italian = configured == "it" or (configured == "auto" and _clean_number(caller).startswith("39"))
    return italian, "it-IT" if italian else "en-US"


def _spoken_menu(profile: str, italian: bool, administrator: bool) -> str:
    if profile == "manager":
        admin = " 9, team and finance." if administrator and not italian else " 9, team e finanza." if administrator else ""
        transfer = " 13, chiama la reception." if italian else " 13, call reception."
        return (
            "Menu Baiamonte. Premi 1 per oggi, 2 per operazioni, 3 per agronomia, 4 per annata, "
            "5 per enologia, 6 per olive, 7 per i sistemi della tenuta, 8 per ospitalità,"
            + admin + " 12 per le volpi," + transfer + " Oppure 0 per ripetere."
            if italian else
            "Baiamonte menu. Press 1 for today, 2 for operations, 3 for agronomy, 4 for vintage, "
            "5 for enology, 6 for olives, 7 for estate systems, 8 for hospitality,"
            + admin + " 12 for foxes," + transfer + " Or 0 to repeat."
        )
    if profile == "reporter":
        return (
            "Menu Baiamonte. Premi 1 per il lavoro di oggi, 2 per meteo e campo, 3 per trattamenti, "
            "4 per annata, 5 per cantina, 6 per olive, 9 per chiamare la reception, oppure 0 per ripetere."
            if italian else
            "Baiamonte menu. Press 1 for today's work, 2 for weather and field, 3 for treatments, "
            "4 for vintage, 5 for cellar, 6 for olives, 9 to call reception, or 0 to repeat."
        )
    return (
        "Benvenuto a Tenuta Baiamonte, sul versante nord dell'Etna. Premi 1 per conoscere la tenuta e i vini, "
        "2 per degustazioni ed esperienze, 3 per il meteo della visita, 4 per l'annata corrente, 5 per parlare con il team, "
        "oppure 0 per ripetere il menu. Per una richiesta personale, puoi continuare nella chat WhatsApp dopo la chiamata."
        if italian else
        "Welcome to Tenuta Baiamonte, on the north side of Mount Etna. Press 1 to hear about the estate and wines, "
        "2 for tastings and experiences, 3 for visit weather, 4 for the current vintage, 5 to speak with the team, "
        "or 0 to repeat the menu. For a personal request, you can continue in the WhatsApp chat after the call."
    )


def _xml_response(body: str) -> PlainTextResponse:
    return PlainTextResponse(body, media_type="application/xml")


def _say(text: str, language: str) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return f'<Say voice="alice" language="{language}">{escape(clean)}</Say>'


def _forward_twiml(settings: Settings, italian: bool, language: str) -> str:
    target = str(getattr(settings, "twilio_forwarding_target", "") or "").strip()
    caller_id = str(getattr(settings, "twilio_outbound_caller_id", "") or "").strip()
    if not getattr(settings, "twilio_forwarding_enabled", False) or not _valid_call_address(target) or not _valid_call_address(caller_id, allow_sip=False):
        message = "La reception telefonica non è disponibile. Invia un messaggio WhatsApp al team." if italian else "Telephone reception is not available. Please send the team a WhatsApp message."
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{_say(message, language)}<Hangup/></Response>'
    destination = f"<Sip>{escape(target)}</Sip>" if target.lower().startswith("sip:") else f"<Number>{escape(target)}</Number>"
    introduction = "Ti metto in contatto con il team Baiamonte." if italian else "I will connect you with the Baiamonte team."
    unavailable = "Nessuno ha risposto. Invia un messaggio WhatsApp e ti ricontatteremo." if italian else "No one answered. Please send a WhatsApp message and the team will call you back."
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>' + _say(introduction, language)
        + f'<Dial callerId="{escape(caller_id)}" timeout="25" answerOnBridge="true">{destination}</Dial>'
        + _say(unavailable, language) + '<Hangup/></Response>'
    )


def _menu_twiml(action_url: str, profile: str, italian: bool, administrator: bool, language: str, greeting: bool = True) -> str:
    intro = (
        "Ciao. Hai chiamato l'assistente di Tenuta Baiamonte. " if italian else
        "Hello. You have reached the Tenuta Baiamonte assistant. "
    ) if greeting else ""
    prompt = intro + _spoken_menu(profile, italian, administrator)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>"
        f'<Gather input="dtmf speech" numDigits="2" timeout="6" speechTimeout="auto" action="{escape(action_url)}" method="POST">'
        f"{_say(prompt, language)}</Gather>"
        f"{_say('Non ho ricevuto una scelta.' if italian else 'I did not receive a choice.', language)}"
        f'<Redirect method="POST">{escape(action_url)}</Redirect></Response>'
    )


def _record_call_event(event_type: str, call_sid: str, caller: str, details: dict[str, Any], status: str = "processed", direction: str = "inbound") -> None:
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                "VALUES (%s,'twilio-voice',%s,%s,%s,%s,%s)",
                (estate_id(), direction, event_type, call_sid[:190] or None, status, json.dumps({"caller_suffix": _clean_number(caller)[-4:], **details})),
            )
    except Exception:
        # A voice call must still receive TwiML during a temporary database issue.
        pass


async def _voice_params(request: Request) -> list[tuple[str, str]]:
    form = await request.form()
    return [(str(key), str(value)) for key, value in form.multi_items()]


@router.get("/api/v1/communications/twilio/voice", dependencies=[Depends(authorize_admin)])
def communication_twilio_voice_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return twilio_voice_status(settings)


@router.post("/api/v1/communications/twilio/voice/verify", dependencies=[Depends(authorize_admin)])
def communication_twilio_voice_verify(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return verify_twilio_resources(settings)


@router.post("/api/v1/communications/twilio/voice/calls", dependencies=[Depends(authorize_admin)])
def start_twilio_outbound_call(payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Start one administrator-requested PSTN or SIP call; never accepts a caller-ID override."""
    destination = str(payload.get("destination") or "").strip()
    caller_id = str(getattr(settings, "twilio_outbound_caller_id", "") or "").strip()
    webhook = str(settings.twilio_voice_webhook_url or "").strip().rstrip("/")
    if not getattr(settings, "twilio_outbound_enabled", False):
        raise HTTPException(409, "Twilio outbound calling is disabled")
    if not _valid_call_address(destination):
        raise HTTPException(422, "Enter a valid E.164 telephone number or SIP URI")
    if not _valid_call_address(caller_id, allow_sip=False) or not webhook.startswith("https://"):
        raise HTTPException(409, "A verified Twilio caller ID and signed HTTPS webhook are required")
    result = _twilio_form(
        settings,
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Calls.json",
        {
            "To": destination,
            "From": caller_id,
            "Url": webhook + "/outbound",
            "Method": "POST",
            "StatusCallback": webhook + "/status",
            "StatusCallbackMethod": "POST",
            "StatusCallbackEvent": "initiated ringing answered completed",
        },
    )
    destination_type = "sip" if destination.lower().startswith("sip:") else "pstn"
    _record_call_event(
        "voice_outbound_requested", str(result.get("sid") or ""), destination,
        {"destination_type": destination_type, "twilio_status": result.get("status")}, direction="outbound",
    )
    return {"started": bool(result.get("sid")), "call_sid": result.get("sid"), "status": result.get("status"), "destination_type": destination_type}


@router.post("/webhooks/twilio/voice/outbound")
async def receive_twilio_outbound_voice(request: Request, settings: Settings = Depends(get_settings)) -> PlainTextResponse:
    params = await _voice_params(request)
    _validate_twilio(request, params, settings)
    action_url = str(settings.twilio_voice_webhook_url or "").strip().rstrip("/") + "/menu"
    prompt = "This is Tenuta Baiamonte calling. " + _spoken_menu("reception", False, False)
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf speech" numDigits="2" timeout="6" speechTimeout="auto" action="{escape(action_url)}" method="POST">'
        f'{_say(prompt, "en-US")}</Gather><Hangup/></Response>'
    )


@router.post("/webhooks/twilio/voice")
async def receive_twilio_voice(request: Request, settings: Settings = Depends(get_settings)) -> PlainTextResponse:
    params = await _voice_params(request)
    _validate_twilio(request, params, settings)
    values = dict(params)
    caller = str(values.get("From") or "")
    call_sid = str(values.get("CallSid") or "")
    channel = _call_channel(values)
    if not _channel_enabled(channel, settings):
        _record_call_event("voice_call_rejected", call_sid, caller, {"reason": "channel_disabled", "channel": channel})
        return _xml_response('<?xml version="1.0" encoding="UTF-8"?><Response><Say>The requested Baiamonte calling channel is not enabled.</Say><Hangup/></Response>')
    assignment = sender_profile(_caller_lookup_key(caller, channel))
    profile = str(assignment.get("profile") or "off")
    calling_options = assignment.get("settings") or {}
    if profile == "off" and not assignment.get("contact") and settings.twilio_public_reception_enabled and calling_options.get("calling_public_reception", True):
        profile = "reception"
    italian, language = _voice_language(assignment, caller)
    action_url = _signature_url(request, settings).rstrip("/") + "/menu"
    if profile == "off":
        _record_call_event("voice_call_rejected", call_sid, caller, {"reason": "caller_not_authorized", "channel": channel})
        message = (
            "Questo numero non è ancora abilitato per l'assistente vocale Baiamonte. Invia un messaggio WhatsApp al team."
            if italian else
            "This number is not yet enabled for the Baiamonte voice assistant. Please send the team a WhatsApp message."
        )
        return _xml_response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{_say(message, language)}<Hangup/></Response>')
    _record_call_event("voice_call_started", call_sid, caller, {"profile": profile, "channel": channel})
    return _xml_response(_menu_twiml(action_url, profile, italian, bool(assignment.get("administrator")), language))


@router.post("/webhooks/twilio/voice/menu")
async def receive_twilio_voice_menu(request: Request, settings: Settings = Depends(get_settings)) -> PlainTextResponse:
    params = await _voice_params(request)
    _validate_twilio(request, params, settings)
    values = dict(params)
    caller = str(values.get("From") or "")
    call_sid = str(values.get("CallSid") or "")
    channel = _call_channel(values)
    outbound_call = str(values.get("Direction") or "").lower().startswith("outbound") and bool(getattr(settings, "twilio_outbound_enabled", False))
    if not _channel_enabled(channel, settings) and not outbound_call:
        return _xml_response('<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>')
    assignment = {"profile": "reception", "language": "auto", "contact": None, "administrator": False, "settings": {"calling_live_estate_data": True}} if outbound_call else sender_profile(_caller_lookup_key(caller, channel))
    profile = str(assignment.get("profile") or "off")
    calling_options = assignment.get("settings") or {}
    if profile == "off" and not assignment.get("contact") and settings.twilio_public_reception_enabled and calling_options.get("calling_public_reception", True):
        profile = "reception"
    italian, language = _voice_language(assignment, caller)
    action_url = _signature_url(request, settings)
    if profile == "off":
        return _xml_response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{_say("Accesso non autorizzato." if italian else "Access is not authorized.", language)}<Hangup/></Response>')
    choice = str(values.get("Digits") or values.get("SpeechResult") or "").strip()
    if not choice or choice == "0":
        return _xml_response(_menu_twiml(action_url, profile, italian, bool(assignment.get("administrator")), language, False))
    if _forward_choice(profile, choice):
        target_type = "sip" if str(getattr(settings, "twilio_forwarding_target", "")).lower().startswith("sip:") else "pstn"
        _record_call_event("voice_call_forwarded", call_sid, caller, {"profile": profile, "channel": channel, "destination_type": target_type})
        return _xml_response(_forward_twiml(settings, italian, language))
    route = menu_route(profile, choice, italian, bool(assignment.get("administrator")))
    if not route:
        reply = "Non ho riconosciuto quella scelta." if italian else "I did not recognize that choice."
        _record_call_event("voice_menu_unmatched", call_sid, caller, {"profile": profile, "channel": channel})
    else:
        route_name, routed_text = route
        if route_name.startswith("snapshot_") and (profile != "reception" or calling_options.get("calling_live_estate_data", True)):
            try:
                reply = live_snapshot(route_name, italian, administrator=bool(assignment.get("administrator")))
                reply = humanize_reply(reply, italian)[:3400]
            except Exception:
                reply = "I dati dal vivo non sono temporaneamente disponibili." if italian else "Live information is temporarily unavailable."
        elif route_name.startswith("snapshot_"):
            reply = "Le informazioni dal vivo non sono abilitate per le chiamate pubbliche." if italian else "Live estate information is not enabled for public calls."
        elif route_name == "reply":
            reply = routed_text
        else:
            reply = (
                "Questa funzione richiede testo, foto o una nota vocale nella chat WhatsApp."
                if italian else
                "That function needs text, a photo, or a voice note in the WhatsApp chat."
            )
        _record_call_event("voice_menu_choice", call_sid, caller, {"profile": profile, "route": route_name, "channel": channel})
    return _xml_response(
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        + _say(reply, language)
        + _say(" Premi 0 per il menu, oppure termina la chiamata." if italian else " Press 0 for the menu, or hang up.", language)
        + f'<Gather input="dtmf" numDigits="1" timeout="5" action="{escape(action_url)}" method="POST"></Gather>'
        + "<Hangup/></Response>"
    )


@router.post("/webhooks/twilio/voice/status")
async def receive_twilio_voice_status(request: Request, settings: Settings = Depends(get_settings)) -> Response:
    params = await _voice_params(request)
    _validate_twilio(request, params, settings, status=True)
    values = dict(params)
    channel = _call_channel(values)
    _record_call_event(
        "voice_call_status", str(values.get("CallSid") or ""), str(values.get("From") or ""),
        {"call_status": str(values.get("CallStatus") or "unknown")[:60], "duration_seconds": str(values.get("CallDuration") or "")[:20], "channel": channel},
    )
    return Response(status_code=204)
