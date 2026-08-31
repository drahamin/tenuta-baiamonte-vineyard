"""Stateful, personalized assistant orchestration for the Meta WhatsApp channel."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import date
from typing import Any

from pymysql.err import IntegrityError

from ..config import get_settings
from ..db import fetch_one, transaction
from ..intelligence import (
    analyze_intake,
    control_home_assistant_manager_device,
    home_assistant_camera_snapshot,
    resolve_home_assistant_camera_request,
    resolve_home_assistant_control_request,
    run_named_process,
    save_intake_file,
    send_whatsapp_media,
    send_whatsapp_message,
    synthesize_whatsapp_voice,
    transcribe_whatsapp_voice,
    whatsapp_chatbot_reply,
)
from ..service import audit, estate_id
from ..whatsapp_blend import (
    active_calculator as _active_whatsapp_blend_calculator,
    begin_calculator as _begin_whatsapp_blend_calculator,
    continue_calculator as _continue_whatsapp_blend_calculator_flow,
    pending_action as _pending_whatsapp_action,
)
from ..whatsapp_intent import (
    capabilities as _whatsapp_capabilities,
    handoff_requested as _whatsapp_handoff_requested,
    is_submission as whatsapp_is_submission,
    language_preference as _whatsapp_language_preference,
    menu_route as _whatsapp_menu_route,
    prefers_italian as _whatsapp_is_italian,
)
from ..whatsapp_notices import (
    inbound_context as _whatsapp_inbound_context,
    mark_intervention_notice as _mark_whatsapp_intervention_notice,
    resolve_answered_notice as _resolve_answered_whatsapp_notice,
)
from ..whatsapp_observations import (
    active_submission as _active_whatsapp_submission,
    begin_submission as _begin_whatsapp_submission,
    continue_submission as _continue_whatsapp_submission_flow,
    submission_menu as _whatsapp_submission_menu,
)
from .communications_meta import sender_profile as _whatsapp_sender_profile
from .whatsapp_live import humanize_reply as _humanize_whatsapp_reply, live_snapshot as _whatsapp_live_snapshot
from .whatsapp_people import (
    MANAGER_TEXT_AND_AUDIO_ROUTES as _MANAGER_TEXT_AND_AUDIO_ROUTES,
    personalized_menu as _personalized_whatsapp_menu,
    personalize_live_snapshot as _personalize_whatsapp_live_snapshot,
    record_learning as _record_whatsapp_ivr_learning,
    set_language_preference as _set_whatsapp_language_preference,
    set_reply_preference as _set_whatsapp_reply_preference,
)


def _archive_routine_whatsapp_intake(
    record_id: str | None,
    route: str,
    related_record_ids: tuple[str, ...] = (),
) -> None:
    """Keep completed IVR exchanges out of Human Review without deleting evidence."""
    record_ids = tuple(dict.fromkeys(item for item in (record_id, *related_record_ids) if item))
    if not record_ids:
        return
    placeholders = ",".join(["%s"] * len(record_ids))
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE intake_items i SET i.review_status='archived',"
            "i.review_reason=%s,i.reviewed_by='WhatsApp IVR',i.reviewed_at=NOW(),i.archived_at=NOW() "
            f"WHERE i.estate_id=%s AND i.source='whatsapp' AND i.id IN ({placeholders}) "
            "AND i.review_status IN ('new','processing','ready_for_review') "
            "AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.estate_id=i.estate_id "
            "AND a.status IN ('open','acknowledged') "
            "AND JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intake_id'))=i.id "
            "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(a.metadata,'$.intervention_required')),'false')='true')",
            (f"Handled by WhatsApp IVR: {route}"[:2000], estate_id(), *record_ids),
        )
        if changed:
            audit(
                cursor,
                "archive",
                "intake",
                ",".join(record_ids),
                {"count": int(changed), "route": route, "rule": "completed WhatsApp IVR conversation"},
                "WhatsApp IVR",
            )

def _whatsapp_reply_preference(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    help_commands = {
        "reply settings", "reply options", "response settings",
        "impostazioni risposta", "opzioni risposta", "preferenze risposta",
    }
    if normalized in help_commands:
        return "help"
    english = re.fullmatch(r"(?:set )?(?:my )?(?:reply|replies|response)(?: mode)?(?: to)? (text|voice|audio|both|match|same)", normalized)
    italian = re.fullmatch(r"(?:imposta )?(?:la |le )?(?:risposta|risposte)(?: in| su| a)? (testo|voce|audio|entrambe|entrambi|stesso|come ricevuto)", normalized)
    selected = (english or italian).group(1) if english or italian else ""
    return {
        "text": "text", "testo": "text",
        "voice": "voice", "audio": "voice", "voce": "voice",
        "both": "both", "entrambe": "both", "entrambi": "both",
        "match": "match", "same": "match", "stesso": "match", "come ricevuto": "match",
    }.get(selected)


def _whatsapp_capabilities_requested(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return normalized in {"+", "plus", "più", "piu", "?", "menu", "start", "inizia", "help", "capabilities", "what can you do", "aiuto", "funzioni", "cosa puoi fare", "cosa sai fare"}


def _bounded_whatsapp_text(text: str, limit: int = 3900) -> str:
    """Keep replies below WhatsApp's message ceiling without splitting a data row."""
    if len(text) <= limit:
        return text
    clipped = text[: limit - 2]
    clipped = clipped.rsplit("\n", 1)[0] or clipped
    return clipped.rstrip() + "\n…"


async def _send_whatsapp_assistant_reply(
    sender: str,
    text: str,
    assignment: dict[str, Any],
    *,
    resolve_notice: bool = True,
    delivery_mode: str | None = None,
) -> None:
    text = _humanize_whatsapp_reply(
        text,
        _whatsapp_is_italian(text, str(assignment.get("language") or "auto"), sender),
    )
    text = _bounded_whatsapp_text(text)
    if not resolve_notice:
        await asyncio.to_thread(_mark_whatsapp_intervention_notice)
    contact = assignment.get("contact") or {}
    # Unless a contact explicitly selected text, voice, or both, answer in the
    # same medium that arrived. This avoids surprise audio for normal texts.
    reply_mode = str(delivery_mode or contact.get("reply_mode") or "match").lower()
    if reply_mode == "match":
        reply_mode = "voice" if assignment.get("incoming_mode") == "voice" else "text"
    if reply_mode == "both":
        await asyncio.to_thread(send_whatsapp_message, sender, text)
    if reply_mode in {"voice", "both"} and assignment.get("profile") in {"manager", "reporter", "reception"}:
        try:
            audio = await asyncio.to_thread(
                synthesize_whatsapp_voice, text, assignment.get("language") or "auto",
                contact.get("voice") or assignment.get("settings", {}).get("voice") or "marin",
            )
            disclosure = "Baiamonte AI voice"
            await asyncio.to_thread(send_whatsapp_media, sender, audio, "baiamonte-reply.mp3", "audio/mpeg", disclosure)
            if resolve_notice:
                await asyncio.to_thread(_resolve_answered_whatsapp_notice)
            return
        except Exception:
            if reply_mode == "both":
                return
    if reply_mode == "both":
        if resolve_notice:
            await asyncio.to_thread(_resolve_answered_whatsapp_notice)
        return
    await asyncio.to_thread(send_whatsapp_message, sender, text)
    if resolve_notice:
        await asyncio.to_thread(_resolve_answered_whatsapp_notice)


async def _handle_whatsapp_assistant(
    sender: str,
    body: str,
    message_id: str,
    record_id: str | None = None,
    group_id: str = "",
    incoming_mode: str = "text",
    related_record_ids: tuple[str, ...] = (),
) -> None:
    if group_id or not body:
        return
    _whatsapp_inbound_context.set((message_id, record_id))
    assignment = _whatsapp_sender_profile(sender)
    assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
    profile, language, options = assignment["profile"], assignment["language"], assignment["settings"]
    italian = _whatsapp_is_italian(body, language, sender)
    if (
        _whatsapp_capabilities_requested(body)
        and not await asyncio.to_thread(_active_whatsapp_submission, sender)
        and not await asyncio.to_thread(_active_whatsapp_blend_calculator, sender)
    ):
        menu = await asyncio.to_thread(
            _personalized_whatsapp_menu,
            _whatsapp_capabilities(profile, italian, assignment.get("administrator", False)), assignment, italian,
        )
        await _send_whatsapp_assistant_reply(sender, menu, assignment)
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "menu", related_record_ids)
        return
    language_preference = _whatsapp_language_preference(body)
    if language_preference and assignment.get("contact"):
        if language_preference == "help":
            reply = "Language / Lingua: reply ENGLISH, ITALIANO, or LANGUAGE AUTO."
        elif _set_whatsapp_language_preference(sender, language_preference):
            assignment = _whatsapp_sender_profile(sender)
            assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
            language = assignment["language"]
            italian = language_preference == "it"
            labels = {"en": "English", "it": "Italiano", "auto": "automatic / automatica"}
            reply = f"Lingua salvata: {labels[language_preference]}." if italian else f"Language saved: {labels[language_preference]}."
        else:
            reply = "Non è stato possibile salvare la lingua." if italian else "The language preference could not be saved."
        await _send_whatsapp_assistant_reply(sender, reply, assignment)
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "language_preference", related_record_ids)
        return
    preference = _whatsapp_reply_preference(body)
    if preference and assignment.get("contact"):
        if preference == "help":
            reply = (
                "Preferenze risposta: RISPONDI TESTO, RISPONDI VOCE, RISPONDI ENTRAMBI oppure RISPONDI COME RICEVUTO."
                if italian else
                "Reply preferences: REPLY TEXT, REPLY VOICE, REPLY BOTH, or REPLY MATCH."
            )
        elif _set_whatsapp_reply_preference(sender, preference):
            assignment = _whatsapp_sender_profile(sender)
            assignment["incoming_mode"] = "voice" if incoming_mode == "voice" else "text"
            names = {
                "text": ("testo", "text"), "voice": ("voce", "voice"),
                "both": ("testo e voce", "text and voice"),
                "match": ("lo stesso formato del messaggio ricevuto", "the same format as the incoming message"),
            }
            reply = f"Preferenza salvata: {names[preference][0]}." if italian else f"Preference saved: {names[preference][1]}."
        else:
            reply = "Non è stato possibile salvare la preferenza." if italian else "The reply preference could not be saved."
        await _send_whatsapp_assistant_reply(sender, reply, assignment)
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "reply_preference", related_record_ids)
        return
    if profile == "off" or profile == "reception" and not options["reception_enabled"] or profile in {"manager", "reporter"} and not options["manager_enabled"]:
        reason = "assistant_disabled" if profile != "off" else "review_only"
        reply = (
            "Messaggio ricevuto e conservato per la revisione dell'amministratore. Nessun dato operativo è stato modificato."
            if italian else
            "Message received and saved for administrator review. No operational data was changed."
        )
        try:
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            with transaction() as (_, cursor):
                cursor.execute(
                    "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','inbound_routing',%s,'processed',%s)",
                    (estate_id(), message_id[:190], json.dumps({"sender": sender, "profile": profile, "route": reason, "record_id": record_id})),
                )
        except Exception as error:
            with transaction() as (_, cursor):
                cursor.execute(
                    "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','inbound_routing',%s,'failed',%s,%s)",
                    (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "profile": profile, "route": reason, "record_id": record_id})),
                )
        return
    if await _continue_whatsapp_blend_calculator_flow(sender, body, assignment, italian, _send_whatsapp_assistant_reply):
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "blend_calculator", related_record_ids)
        return
    if await _continue_whatsapp_submission_flow(sender, body, assignment, italian, _send_whatsapp_assistant_reply):
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "field_entry_workflow", related_record_ids)
        return
    menu_route = _whatsapp_menu_route(profile, body, italian, assignment.get("administrator", False))
    if menu_route:
        route, routed_text = menu_route
        if options.get("ivr_learning_enabled", True):
            await asyncio.to_thread(
                _record_whatsapp_ivr_learning, sender, profile, route, message_id,
                str((assignment.get("contact") or {}).get("person_entity") or "") or None,
            )
        if route == "reply":
            is_menu = routed_text.startswith(("BAIAMONTE ·", "Menu ", "Manager menu", "Reporter menu", "Reception menu"))
            personalized = await asyncio.to_thread(_personalized_whatsapp_menu, routed_text, assignment, italian) if is_menu else routed_text
            await _send_whatsapp_assistant_reply(sender, personalized, assignment)
            await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "menu_reply", related_record_ids)
            return
        if route == "handoff":
            reply = (
                "Messaggio conservato per il team. Aggiungi ora il motivo, il tuo nome e il modo migliore per contattarti. Una persona lo esaminerà; non è ancora una conferma."
                if italian else
                "Your message is retained for the team. Now add the reason, your name, and the best way to contact you. A person will review it; this is not yet a confirmation."
            )
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            return
        if route == "observation_menu":
            state = {"kind": "select", "step": 0, "values": {}}
            await asyncio.to_thread(_begin_whatsapp_submission, sender, state, f"WhatsApp {sender}")
            await _send_whatsapp_assistant_reply(sender, _whatsapp_submission_menu(italian), assignment, resolve_notice=False)
            await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "field_entry_menu", related_record_ids)
            return
        if route == "blend_crate_calculator":
            await asyncio.to_thread(_begin_whatsapp_blend_calculator, sender, date.today().year)
            reply = (
                "Quante cassette di Nerello prevedi di raccogliere? Rispondi solo con il numero, per esempio 100."
                if italian else
                "How many Nerello crates do you plan to pick? Reply with only the number, for example 100."
            )
            await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
            await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "blend_calculator_start", related_record_ids)
            return
        if route.startswith("snapshot_"):
            try:
                reply = await asyncio.to_thread(
                    _whatsapp_live_snapshot,
                    route,
                    italian,
                    options["home_assistant_entities"],
                    assignment.get("administrator", False),
                    options["home_assistant_camera_entities"],
                )
                text_and_audio = profile == "manager" and route in _MANAGER_TEXT_AND_AUDIO_ROUTES
                if text_and_audio:
                    reply = _personalize_whatsapp_live_snapshot(reply, route, assignment, italian)
                if route == "snapshot_fox":
                    from .fox_watch import latest_fox_media
                    latest = await asyncio.to_thread(latest_fox_media)
                    if latest:
                        media, content = latest
                        await asyncio.to_thread(
                            send_whatsapp_media, sender, content, "baiamonte-fox.jpg",
                            str(media.get("content_type") or "image/jpeg"), reply,
                        )
                        await asyncio.to_thread(_resolve_answered_whatsapp_notice)
                        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, route, related_record_ids)
                        return
                await _send_whatsapp_assistant_reply(
                    sender,
                    reply,
                    assignment,
                    delivery_mode="both" if text_and_audio else None,
                )
                await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, route, related_record_ids)
            except Exception as error:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','live_menu_snapshot',%s,'failed',%s,%s)",
                        (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "route": route})),
                    )
                reply = "I dati operativi dal vivo non sono temporaneamente disponibili. Il messaggio è stato conservato." if italian else "Live operational data is temporarily unavailable. Your message was retained."
                await _send_whatsapp_assistant_reply(sender, reply, assignment)
            return
        body = routed_text
    if _whatsapp_handoff_requested(body):
        reply = (
            "Richiesta inoltrata per la revisione umana. Scrivi in un solo messaggio cosa ti serve, l'urgenza e il modo migliore per contattarti."
            if italian else
            "Your request has been flagged for human review. In one message, send what you need, the urgency, and the best way to contact you."
        )
        await _send_whatsapp_assistant_reply(sender, reply, assignment, resolve_notice=False)
        return
    analysis: dict[str, Any] = {}
    if record_id and profile in {"manager", "reporter"} and options["trusted_ingestion"] and get_settings().openai_api_key:
        try:
            analyzed = await asyncio.to_thread(analyze_intake, record_id)
            analysis = analyzed.get("analysis") or {}
        except Exception:
            pass
    approval = re.fullmatch(r"\s*(?:APPROVE|APPROVA)\s+(\d{4,8})\s*", body, re.I)
    rejection = re.fullmatch(r"\s*(?:REJECT|RIFIUTA)\s+(\d{4,8})(?:\s+(.{1,500}))?\s*", body, re.I)
    if profile == "manager" and (approval or rejection):
        code = (approval or rejection).group(1)
        pending = _pending_whatsapp_action(sender, code, "intake_approval_pending")
        if pending:
            status = "approved" if approval else "rejected"
            review_reason = None if approval else (rejection.group(2) or "Rejected through WhatsApp; no additional reason supplied").strip()
            with transaction() as (_, cursor):
                cursor.execute("UPDATE intake_items SET review_status=%s,review_reason=%s,reviewed_by=%s,reviewed_at=NOW() WHERE id=%s AND estate_id=%s", (status, review_reason, f"WhatsApp {sender}", pending.get("record_id"), estate_id()))
                cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (pending.get("_event_id"),))
            await _send_whatsapp_assistant_reply(sender, ("Informazione approvata e conservata nel registro di revisione." if italian else "Information approved and retained in the review record.") if approval else ("Informazione rifiutata." if italian else "Information rejected."), assignment)
            await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "review_decision", related_record_ids)
            return
    confirmation = re.fullmatch(r"\s*(?:CONFIRM|CONFERMA)\s+(\d{4,8})\s*", body, re.I)
    if profile == "manager" and confirmation:
        code = confirmation.group(1)
        pending = _pending_whatsapp_action(sender, code, "manager_control_pending")
        if pending and pending.get("process") in options["manager_controls"]:
            with transaction() as (_, cursor):
                claimed = cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (pending.get("_event_id"),))
            if not claimed:
                return
            try:
                await run_named_process(str(pending["process"]))
                await _send_whatsapp_assistant_reply(sender, "Aggiornamento completato." if italian else "System update completed.", assignment)
                await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "manager_process_confirmation", related_record_ids)
            except Exception:
                await _send_whatsapp_assistant_reply(sender, "Aggiornamento non riuscito. Controlla Operations Control." if italian else "System update failed. Check Operations Control.", assignment, resolve_notice=False)
            return
        device_pending = _pending_whatsapp_action(sender, code, "manager_device_control_pending")
        if device_pending:
            with transaction() as (_, cursor):
                claimed = cursor.execute("UPDATE integration_events SET status='processed' WHERE id=%s AND status='received'", (device_pending.get("_event_id"),))
            if not claimed:
                return
            try:
                result = await asyncio.to_thread(control_home_assistant_manager_device, str(device_pending.get("entity_id") or ""), str(device_pending.get("action") or ""), options["home_assistant_entities"])
                with transaction() as (_, cursor):
                    audit(cursor, "control", "home_assistant_entity", result["entity_id"], {"action": result["action"], "source": "whatsapp_manager"}, f"WhatsApp {sender}")
                action_text = "acceso" if result["action"] == "turn_on" else "spento"
                await _send_whatsapp_assistant_reply(sender, (f"{result['name']} {action_text}." if italian else f"{result['name']} turned {'on' if result['action']=='turn_on' else 'off'}.") , assignment)
                await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "manager_device_confirmation", related_record_ids)
            except Exception:
                await _send_whatsapp_assistant_reply(sender, "Controllo non riuscito. Verifica Home Assistant." if italian else "Device control failed. Check Home Assistant.", assignment, resolve_notice=False)
            return
    commands = {
        "full_refresh": ("refresh system", "aggiorna sistema", "aggiornamento completo"),
        "weather": ("refresh weather", "aggiorna meteo"),
        "cistern": ("check cistern", "controlla cisterna"),
        "disease": ("update disease", "aggiorna malattie", "pressione malattie"),
        "public_feed": ("publish website", "aggiorna sito", "pubblica sito"),
    }
    lowered = body.casefold()
    if profile == "manager":
        camera_request = await asyncio.to_thread(resolve_home_assistant_camera_request, body)
        if camera_request:
            cameras = camera_request.get("cameras") or []
            if camera_request.get("action") in {"list", "unavailable"}:
                if cameras:
                    names = "\n".join(f"• {item['name']}" for item in cameras[:20])
                    text = ("Telecamere disponibili:\n" if italian else "Available cameras:\n") + names
                else:
                    text = "Nessuna telecamera è disponibile per WhatsApp." if italian else "No cameras are available to WhatsApp."
                await _send_whatsapp_assistant_reply(sender, text, assignment)
                await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "camera_list", related_record_ids)
                return
            recent = fetch_one(
                "SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='manager_camera_snapshot' AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender'))=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 1 MINUTE)",
                (estate_id(), sender),
            ) or {}
            if int(recent.get("total") or 0) >= 3:
                await _send_whatsapp_assistant_reply(sender, "Attendi un momento prima di richiedere un'altra immagine." if italian else "Please wait a moment before requesting another camera image.", assignment)
                return
            camera = camera_request["camera"]
            try:
                captured = await asyncio.to_thread(home_assistant_camera_snapshot, camera["entity_id"])
                stale = bool(captured.get("stale"))
                age_minutes = max(1, int(captured.get("age_seconds") or 0) // 60) if stale else 0
                caption = (
                    f"{camera['name']} · ultima immagine disponibile ({age_minutes} min fa)" if italian and stale else
                    f"{camera['name']} · immagine attuale" if italian else
                    f"{camera['name']} · last available image ({age_minutes} min old)" if stale else
                    f"{camera['name']} · current image"
                )
                await asyncio.to_thread(send_whatsapp_media, sender, captured["data"], f"{camera['entity_id'].split('.',1)[-1]}.jpg", captured["content_type"], caption)
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','manager_camera_snapshot',%s,'processed',%s)",
                        (estate_id(), message_id[:190], json.dumps({"sender": sender, "entity_id": camera["entity_id"], "stale": stale})),
                    )
                    audit(cursor, "view", "home_assistant_camera", camera["entity_id"], {"source": "whatsapp_manager", "stale": stale}, f"WhatsApp {sender}")
                await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "camera_snapshot", related_record_ids)
            except Exception as error:
                with transaction() as (_, cursor):
                    cursor.execute(
                        "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','manager_camera_snapshot',%s,'failed',%s,%s)",
                        (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "entity_id": camera["entity_id"]})),
                    )
                await _send_whatsapp_assistant_reply(sender, "La telecamera non è disponibile e non esiste un'immagine recente." if italian else "The camera is unavailable and no recent image is cached.", assignment)
            return
    if profile == "manager" and options["home_assistant_entities"]:
        device_request = await asyncio.to_thread(resolve_home_assistant_control_request, body, options["home_assistant_entities"])
        if device_request:
            code = str(int(hashlib.sha256(f"{sender}:{message_id}:{device_request['entity_id']}:{device_request['action']}".encode()).hexdigest()[:8], 16))[-6:]
            with transaction() as (_, cursor):
                cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_device_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({**device_request, "sender": sender, "message_id": message_id})))
            action_name = "accendere" if device_request["action"] == "turn_on" else "spegnere"
            prompt = f"Conferma per {action_name} {device_request['name']}. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirm to turn {'on' if device_request['action']=='turn_on' else 'off'} {device_request['name']}. Reply CONFIRM {code} within 24 hours."
            await _send_whatsapp_assistant_reply(sender, prompt, assignment, resolve_notice=False)
            await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "manager_device_request", related_record_ids)
            return
    requested = next((process for process, phrases in commands.items() if process in options["manager_controls"] and any(phrase in lowered for phrase in phrases)), None)
    if profile == "manager" and requested:
        code = str(int(hashlib.sha256(f"{sender}:{message_id}:{requested}".encode()).hexdigest()[:8], 16))[-6:]
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','manager_control_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"process": requested, "sender": sender, "message_id": message_id})))
        await _send_whatsapp_assistant_reply(sender, (f"Conferma richiesta. Rispondi CONFERMA {code} entro 24 ore." if italian else f"Confirmation required. Reply CONFIRM {code} within 24 hours."), assignment, resolve_notice=False)
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "manager_process_request", related_record_ids)
        return
    if profile in {"manager", "reporter"} and options["trusted_ingestion"] and record_id:
        try:
            if whatsapp_is_submission(body, analysis):
                if profile == "reporter":
                    summary = str(analysis.get("summary") or "Information ready for review")[:700]
                    notice = "\n\nInviato per la revisione del manager." if italian else "\n\nSubmitted for manager review."
                    await _send_whatsapp_assistant_reply(sender, summary + notice, assignment, resolve_notice=False)
                    return
                code = str(int(hashlib.sha256(f"{sender}:{record_id}".encode()).hexdigest()[:8], 16))[-6:]
                with transaction() as (_, cursor):
                    cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','inbound','intake_approval_pending',%s,'received',%s)", (estate_id(), f"{sender}:{code}", json.dumps({"record_id": record_id, "sender": sender, "classification": analysis.get("classification")})))
                summary = str(analysis.get("summary") or "Information ready for review")[:700]
                prompt = f"\n\nRispondi APPROVA {code} o RIFIUTA {code}." if italian else f"\n\nReply APPROVE {code} or REJECT {code}."
                await _send_whatsapp_assistant_reply(sender, summary + prompt, assignment, resolve_notice=False)
                return
        except Exception:
            pass
    limit = options["reply_limit_unknown"] if profile == "reception" else options["reply_limit_manager"]
    count = fetch_one("SELECT COUNT(*) total FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='chatbot_reply' AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender'))=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR)", (estate_id(), sender)) or {}
    if int(count.get("total") or 0) >= limit:
        await _send_whatsapp_assistant_reply(sender, "Limite giornaliero raggiunto. Il messaggio è stato salvato per la revisione." if italian else "Daily assistant limit reached. Your message was saved for review.", assignment, resolve_notice=False)
        return
    if not options.get("ivr_ai_fallback_enabled", True):
        fallback = (
            "Non ho riconosciuto un comando locale. Il messaggio è stato conservato. Invia + per il menu o PERSONA per il team."
            if italian else
            "I did not match that to a local command. Your message was retained. Send + for the menu or HUMAN for the team."
        )
        await _send_whatsapp_assistant_reply(sender, fallback, assignment)
        return
    if options.get("ivr_learning_enabled", True):
        await asyncio.to_thread(
            _record_whatsapp_ivr_learning, sender, profile, "assistant_fallback", message_id,
            str((assignment.get("contact") or {}).get("person_entity") or "") or None,
        )
    try:
        result = await asyncio.to_thread(whatsapp_chatbot_reply, body, profile if profile in {"manager", "reporter"} else "reception", language, options["home_assistant_entities"] if profile == "manager" else [], assignment.get("administrator", False))
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','chatbot_reply',%s,'failed',%s,%s)", (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender, "profile": profile, "language": language})))
        fallback = (
            "Il servizio di risposta è temporaneamente non disponibile. Il messaggio è stato conservato. Rispondi MENU per le opzioni o PERSONA se serve l'intervento del team."
            if italian else
            "The assistant is temporarily unavailable. Your message was retained. Send + for the menu or HUMAN if the team needs to intervene."
        )
        await _send_whatsapp_assistant_reply(sender, fallback, assignment)
        return
    answer = str(result.get("answer") or result.get("message") or "")[:4096]
    if not result.get("configured") or not answer:
        answer = (
            "Non posso completare questa risposta in questo momento. Il messaggio è stato conservato. Rispondi MENU per richieste supportate o PERSONA per il team."
            if italian else
            "I cannot complete that answer right now. Your message was retained. Reply MENU for supported requests or HUMAN for the team."
        )
    await _send_whatsapp_assistant_reply(sender, answer, assignment)
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) VALUES (%s,'whatsapp-channel','outbound','chatbot_reply',%s,'processed',%s)", (estate_id(), message_id[:190], json.dumps({"sender": sender, "profile": profile, "language": language, "record_id": record_id})))
    if result.get("configured") and answer:
        await asyncio.to_thread(_archive_routine_whatsapp_intake, record_id, "assistant_answer", related_record_ids)


async def _handle_whatsapp_voice(
    sender: str,
    data: bytes,
    filename: str,
    message_id: str,
    sender_name: str,
    group_id: str = "",
    source_record_id: str | None = None,
) -> None:
    assignment = _whatsapp_sender_profile(sender)
    assignment["incoming_mode"] = "voice"
    if group_id:
        return
    if assignment["profile"] == "off":
        await _send_whatsapp_assistant_reply(sender, "Nota vocale ricevuta e salvata per la revisione." if assignment["language"] == "it" else "Voice note received and saved for review.", assignment)
        return
    try:
        transcript = await asyncio.to_thread(transcribe_whatsapp_voice, data, filename, assignment["language"])
        if not transcript:
            await _send_whatsapp_assistant_reply(sender, "Nota vocale ricevuta, ma non è stato possibile trascriverla. È stata conservata per la revisione." if assignment["language"] == "it" else "Voice note received, but it could not be transcribed. It was retained for review.", assignment)
            return
        record_id = save_intake_file(transcript.encode(), f"whatsapp-{message_id}-transcript.txt", "text/plain", "whatsapp", "WhatsApp voice transcript", transcript, message_id + ":transcript", sender_name, sender)
        related = (source_record_id,) if source_record_id else ()
        await _handle_whatsapp_assistant(sender, transcript, message_id, record_id, group_id, "voice", related)
    except IntegrityError:
        return
    except Exception as error:
        with transaction() as (_, cursor):
            cursor.execute("INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,error_message,payload) VALUES (%s,'whatsapp-channel','outbound','voice_routing',%s,'failed',%s,%s)", (estate_id(), message_id[:190], str(error)[:1000], json.dumps({"sender": sender})))
        await _send_whatsapp_assistant_reply(sender, "La nota vocale è stata salvata, ma l'elaborazione non è riuscita." if assignment["language"] == "it" else "The voice note was saved, but processing failed.", assignment)
