"""Per-person WhatsApp IVR configuration, statistics, and local personalization."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException

from ..db import fetch_all, fetch_one, transaction
from ..intelligence import home_assistant_people
from ..service import audit, estate_id
from .messaging import event_payload

logger = logging.getLogger(__name__)

MANAGER_TEXT_AND_AUDIO_ROUTES = {
    "snapshot_today", "snapshot_operations", "snapshot_agronomy", "snapshot_harvest",
    "snapshot_enology", "snapshot_olives", "snapshot_hospitality",
}


def personalize_live_snapshot(text: str, route: str, assignment: dict[str, Any], italian: bool) -> str:
    """Give high-value Manager summaries a natural, person-specific opening."""
    raw_name = re.sub(r"\s+", " ", str((assignment.get("contact") or {}).get("name") or "").strip())
    first_name = raw_name.split(" ", 1)[0] if raw_name and re.search(r"[A-Za-zÀ-ÿ]", raw_name) else ""
    openings = {
        "snapshot_today": ("ecco cosa richiede attenzione oggi.", "here's what needs attention today."),
        "snapshot_weather": ("ecco il quadro meteo più recente a Baiamonte.", "here's the latest weather picture at Baiamonte."),
        "snapshot_work": ("ecco come si presenta il lavoro in questo momento.", "here's how the work picture looks right now."),
        "snapshot_disease": ("ecco l'ultimo quadro su malattie e trattamenti.", "here's the latest disease and treatment picture."),
        "snapshot_harvest": ("ecco l'ultimo quadro della vendemmia.", "here's the latest harvest picture."),
        "snapshot_cellar": ("ecco l'aggiornamento più recente su cantina e laboratorio.", "here's the latest cellar and laboratory update."),
        "snapshot_cistern": ("ecco l'ultimo aggiornamento sulla cisterna.", "here's the latest cistern update."),
        "snapshot_power": ("ecco il quadro attuale di energia e dispositivi.", "here's the current power and device picture."),
        "snapshot_traffic": ("ecco l'ultimo quadro su Etna, terremoti e traffico.", "here's the latest Etna, earthquake, and traffic picture."),
        "snapshot_operations": ("ecco il quadro operativo corrente.", "here's the current operations picture."),
        "snapshot_agronomy": ("ecco il quadro agronomico corrente.", "here's the current agronomy picture."),
        "snapshot_enology": ("ecco l'aggiornamento su Tank Sensor, cantina e imbottigliamento.", "here's the Tank Sensor, cellar, and bottling update."),
        "snapshot_olives": ("ecco l'ultimo quadro di olive e olio.", "here's the latest olives and oil picture."),
        "snapshot_hospitality": ("ecco il quadro corrente di ospitalità e registro vendite.", "here's the current hospitality and sales-register picture."),
    }
    opening = openings.get(route, ("ecco l'ultimo aggiornamento.", "here's the latest update."))[0 if italian else 1]
    greeting = f"{first_name}, {opening}" if first_name else opening[:1].upper() + opening[1:]
    return f"{greeting}\n\n{text}"


def sender_is_allowed(sender: str, configured_allowlist: set[str], assignment: dict[str, Any]) -> bool:
    """Honor either the legacy allowlist or an explicit Admin address-book role."""
    return (
        not configured_allowlist
        or sender in configured_allowlist
        or str(assignment.get("profile") or "off") in {"reception", "reporter", "manager"}
    )


def contact_book() -> dict[str, Any]:
    row = fetch_one(
        "SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts'",
        (estate_id(),),
    ) or {}
    book = event_payload(row.get("setting_value"))
    return {"contacts": list(book.get("contacts") or []), "groups": list(book.get("groups") or [])}


def person_ivr(person_entity: str, person_name: str) -> dict[str, Any]:
    """Return privacy-limited IVR configuration and activity for one estate person."""
    normalized_name = re.sub(r"\s+", " ", str(person_name or "").strip()).casefold()
    contact = next((item for item in contact_book()["contacts"] if str(item.get("person_entity") or "") == person_entity or re.sub(r"\s+", " ", str(item.get("name") or "").strip()).casefold() == normalized_name), None)
    if not contact:
        return {
            "linked": False, "assistant": "off", "language": "auto", "reply_mode": "match",
            "voice": "marin", "learning_enabled": True, "personalized_menu_enabled": True,
            "same_location_enabled": True, "ai_fallback_enabled": True, "minimum_history": 1,
            "stats": {"routed_30d": 0, "local_routes_30d": 0, "ai_fallbacks_30d": 0, "local_route_pct": None, "started_30d": 0, "completed_30d": 0, "completion_pct": None, "last_activity": None},
        }
    contact = dict(contact)
    if contact.get("reply_mode") == "both" and not contact.get("reply_mode_explicit"):
        contact["reply_mode"] = "match"
    number = re.sub(r"\D", "", str(contact.get("number") or ""))
    suffix = number[-4:]
    route = fetch_one(
        "SELECT COUNT(*) routed_30d,SUM(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.route')) LIKE 'snapshot_%%') local_routes_30d,"
        "SUM(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.route'))='assistant_fallback') ai_fallbacks_30d,MAX(occurred_at) last_activity "
        "FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='ivr_route_learning' "
        "AND occurred_at>=DATE_SUB(NOW(),INTERVAL 30 DAY) AND (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.person_entity'))=%s OR "
        "(JSON_EXTRACT(payload,'$.person_entity') IS NULL AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender_suffix'))=%s))",
        (estate_id(), person_entity, suffix),
    ) or {}
    submissions = fetch_one(
        "SELECT COUNT(*) started_30d,SUM(status='processed') completed_30d,MAX(occurred_at) last_activity FROM integration_events "
        "WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type='structured_submission_pending' "
        "AND external_id=%s AND occurred_at>=DATE_SUB(NOW(),INTERVAL 30 DAY)",
        (estate_id(), number),
    ) or {}
    routed, local = int(route.get("routed_30d") or 0), int(route.get("local_routes_30d") or 0)
    started, completed = int(submissions.get("started_30d") or 0), int(submissions.get("completed_30d") or 0)
    activity_times = [value for value in (route.get("last_activity"), submissions.get("last_activity")) if value]
    return {
        "linked": True, "number": number, "number_masked": f"•••• {suffix}" if suffix else "Linked",
        "assistant": str(contact.get("assistant") or "off"), "language": str(contact.get("language") or "auto"),
        "reply_mode": str(contact.get("reply_mode") or "match"), "voice": str(contact.get("voice") or "marin"),
        "learning_enabled": bool(contact.get("ivr_learning_enabled", True)),
        "personalized_menu_enabled": bool(contact.get("ivr_personalized_menu_enabled", True)),
        "same_location_enabled": bool(contact.get("ivr_same_location_enabled", True)),
        "ai_fallback_enabled": bool(contact.get("ivr_ai_fallback_enabled", True)),
        "minimum_history": min(10, max(1, int(contact.get("ivr_learning_min_completed") or 1))),
        "stats": {"routed_30d": routed, "local_routes_30d": local, "ai_fallbacks_30d": int(route.get("ai_fallbacks_30d") or 0), "local_route_pct": round(local / routed * 100, 1) if routed else None, "started_30d": started, "completed_30d": completed, "completion_pct": round(completed / started * 100, 1) if started else None, "last_activity": max(activity_times) if activity_times else None},
    }


def sender_profile(number: str, base_settings: dict[str, Any]) -> dict[str, Any]:
    clean = re.sub(r"\D", "", number or "")
    contact = next((item for item in contact_book()["contacts"] if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
    contact = dict(contact) if contact else None
    if contact and contact.get("reply_mode") == "both" and not contact.get("reply_mode_explicit"):
        contact["reply_mode"] = "match"
    settings = {
        **base_settings,
        "ivr_learning_enabled": bool((contact or {}).get("ivr_learning_enabled", True)),
        "ivr_personalized_menu_enabled": bool((contact or {}).get("ivr_personalized_menu_enabled", True)),
        "ivr_same_location_enabled": bool((contact or {}).get("ivr_same_location_enabled", True)),
        "ivr_ai_fallback_enabled": bool((contact or {}).get("ivr_ai_fallback_enabled", True)),
        "ivr_learning_min_completed": min(10, max(1, int((contact or {}).get("ivr_learning_min_completed") or 1))),
    }
    assigned = str((contact or {}).get("assistant") or "").lower()
    if (contact or {}).get("auto_unknown"):
        profile = "reception" if settings["unknown_reception"] else "off"
    else:
        profile = assigned if assigned in {"reception", "manager", "reporter", "off"} else ("reception" if not contact and settings["unknown_reception"] else "off")
    language = str((contact or {}).get("language") or "auto").lower()
    role = str((contact or {}).get("role") or "").strip().casefold()
    administrator = bool((contact or {}).get("administrator")) or role in {"admin", "administrator", "amministratore"}
    return {"profile": profile, "language": language if language in {"auto", "en", "it"} else "auto", "contact": contact, "administrator": administrator, "settings": settings}


def save_person_ivr(person_entity: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    person_entity = person_entity.strip()
    if not person_entity.startswith("person."):
        raise HTTPException(422, "Choose a Home Assistant Person")
    ha_person = next((item for item in home_assistant_people() if item.get("entity_id") == person_entity), None)
    if not ha_person:
        raise HTTPException(404, "Home Assistant Person not found")
    name = str((ha_person.get("attributes") or {}).get("friendly_name") or payload.get("name") or "").strip()[:180]
    number = re.sub(r"\D", "", str(payload.get("number") or ""))
    assistant, language = str(payload.get("assistant") or "off").casefold(), str(payload.get("language") or "auto").casefold()
    reply_mode, voice = str(payload.get("reply_mode") or "match").casefold(), str(payload.get("voice") or "marin").casefold()
    if len(number) < 8 or len(number) > 18:
        raise HTTPException(422, "Enter the person's full international WhatsApp number")
    if assistant not in {"off", "reception", "reporter", "manager"}:
        raise HTTPException(422, "Choose a valid IVR access level")
    if language not in {"auto", "en", "it"} or reply_mode not in {"text", "voice", "both", "match"}:
        raise HTTPException(422, "Choose valid language and reply settings")
    if voice not in {"marin", "coral", "shimmer", "nova"}:
        raise HTTPException(422, "Choose a valid WhatsApp voice")
    book = contact_book()
    contacts = [dict(item) for item in book["contacts"]]
    duplicate = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == number and str(item.get("person_entity") or person_entity) != person_entity), None)
    if duplicate:
        raise HTTPException(409, "That WhatsApp number is linked to another person")
    contact = next((item for item in contacts if str(item.get("person_entity") or "") == person_entity or re.sub(r"\D", "", str(item.get("number") or "")) == number), None)
    if not contact:
        contact = {}
        contacts.append(contact)
    contact.update({
        "name": name, "number": number, "person_entity": person_entity, "role": str(payload.get("role") or contact.get("role") or "").strip()[:180],
        "assistant": assistant, "language": language, "reply_mode": reply_mode, "reply_mode_explicit": True, "voice": voice,
        "administrator": bool(payload.get("administrator", contact.get("administrator", False))),
        "ivr_learning_enabled": bool(payload.get("ivr_learning_enabled", True)),
        "ivr_personalized_menu_enabled": bool(payload.get("ivr_personalized_menu_enabled", True)),
        "ivr_same_location_enabled": bool(payload.get("ivr_same_location_enabled", True)),
        "ivr_ai_fallback_enabled": bool(payload.get("ivr_ai_fallback_enabled", True)),
        "ivr_learning_min_completed": min(10, max(1, int(payload.get("ivr_learning_min_completed") or 1))),
    })
    stored = {"contacts": contacts, "groups": book["groups"], "updated_by": actor}
    with transaction() as (_, cursor):
        cursor.execute("INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (estate_id(), json.dumps(stored, ensure_ascii=False)))
        audit(cursor, "update", "person_whatsapp_ivr", person_entity, {key: contact[key] for key in ("assistant", "language", "reply_mode", "voice", "ivr_learning_enabled", "ivr_personalized_menu_enabled", "ivr_same_location_enabled", "ivr_ai_fallback_enabled", "ivr_learning_min_completed")}, actor)
    return {"saved": True, "person_entity": person_entity, "whatsapp_ivr": person_ivr(person_entity, name)}


def personalized_menu(menu: str, assignment: dict[str, Any], italian: bool) -> str:
    """Append this person's most-used safe local routes without changing permissions."""
    contact, settings = assignment.get("contact") or {}, assignment.get("settings") or {}
    if not contact or not settings.get("ivr_learning_enabled", True) or not settings.get("ivr_personalized_menu_enabled", True):
        return menu
    person_entity, suffix = str(contact.get("person_entity") or ""), re.sub(r"\D", "", str(contact.get("number") or ""))[-4:]
    rows = fetch_all(
        "SELECT JSON_UNQUOTE(JSON_EXTRACT(payload,'$.route')) route,COUNT(*) uses FROM integration_events WHERE estate_id=%s "
        "AND integration_name='whatsapp-channel' AND event_type='ivr_route_learning' AND occurred_at>=DATE_SUB(NOW(),INTERVAL 30 DAY) "
        "AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.route')) LIKE 'snapshot_%%' AND (JSON_UNQUOTE(JSON_EXTRACT(payload,'$.person_entity'))=%s "
        "OR (JSON_EXTRACT(payload,'$.person_entity') IS NULL AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.sender_suffix'))=%s)) GROUP BY route ORDER BY uses DESC,route LIMIT 3",
        (estate_id(), person_entity, suffix),
    )
    numbers = {"manager": {"snapshot_today": 1, "snapshot_operations": 2, "snapshot_agronomy": 3, "snapshot_harvest": 4, "snapshot_enology": 5, "snapshot_olives": 6, "snapshot_estate_systems": 7, "snapshot_hospitality": 8, "snapshot_admin": 9}, "reporter": {"snapshot_operations": 1, "snapshot_weather": 2, "snapshot_disease": 3, "snapshot_harvest": 4, "snapshot_enology": 5, "snapshot_olives": 6}, "reception": {"snapshot_estate": 1, "snapshot_hospitality_public": 2, "snapshot_weather": 3, "snapshot_harvest": 4}}.get(str(assignment.get("profile") or ""), {})
    labels = {"snapshot_today": ("Oggi", "Today"), "snapshot_operations": ("Operazioni", "Operations"), "snapshot_agronomy": ("Agronomia", "Agronomy"), "snapshot_weather": ("Meteo", "Weather"), "snapshot_disease": ("Trattamenti", "Treatments"), "snapshot_harvest": ("Annata", "Vintage"), "snapshot_enology": ("Enologia", "Enology"), "snapshot_olives": ("Olive", "Olives"), "snapshot_estate_systems": ("Sistemi tenuta", "Estate systems"), "snapshot_hospitality": ("Ospitalità", "Hospitality"), "snapshot_admin": ("Team e finanza", "Team and finance"), "snapshot_estate": ("Tenuta e vini", "Estate and wines"), "snapshot_hospitality_public": ("Esperienze", "Experiences")}
    favorites = [f"{numbers[route]} {labels[route][0 if italian else 1]}" for row in rows if (route := str(row.get("route") or "")) in numbers and route in labels]
    return menu if not favorites else menu + f"\n\n{'Le tue scelte abituali' if italian else 'Your usual choices'}: " + " · ".join(favorites)


def record_learning(sender: str, profile: str, route: str, message_id: str, person_entity: str | None = None) -> None:
    """Measure local-first routing without retaining the worker's message content."""
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
                "VALUES (%s,'whatsapp-channel','inbound','ivr_route_learning',%s,'processed',%s)",
                (estate_id(), message_id[:190], json.dumps({"sender_suffix": re.sub(r"\D", "", sender)[-4:], "profile": profile, "route": route, "person_entity": person_entity or None})),
            )
    except Exception:
        logger.exception("Could not record WhatsApp IVR learning telemetry")


def set_reply_preference(number: str, reply_mode: str) -> bool:
    clean = re.sub(r"\D", "", number or "")
    if reply_mode not in {"text", "voice", "both", "match"}:
        return False
    with transaction() as (_, cursor):
        cursor.execute("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE", (estate_id(),))
        row = cursor.fetchone() or {}
        book = event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        contact = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
        if not contact:
            return False
        contact["reply_mode"] = reply_mode
        contact["reply_mode_explicit"] = True
        stored = {**book, "contacts": contacts[:100], "groups": list(book.get("groups") or [])[:30], "updated_by": f"WhatsApp {clean}"}
        cursor.execute("INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (estate_id(), json.dumps(stored)))
        audit(cursor, "update", "whatsapp_reply_preference", clean, {"reply_mode": reply_mode, "source": "self_service"}, f"WhatsApp {clean}")
    return True


def set_language_preference(number: str, language: str) -> bool:
    clean = re.sub(r"\D", "", number or "")
    if language not in {"auto", "en", "it"}:
        return False
    with transaction() as (_, cursor):
        cursor.execute("SELECT setting_value FROM app_settings WHERE estate_id=%s AND setting_key='whatsapp_contacts' FOR UPDATE", (estate_id(),))
        row = cursor.fetchone() or {}
        book = event_payload(row.get("setting_value"))
        contacts = list(book.get("contacts") or [])
        contact = next((item for item in contacts if re.sub(r"\D", "", str(item.get("number") or "")) == clean), None)
        if not contact:
            return False
        contact["language"] = language
        stored = {**book, "contacts": contacts[:100], "groups": list(book.get("groups") or [])[:30], "updated_by": f"WhatsApp {clean}"}
        cursor.execute("INSERT INTO app_settings (estate_id,setting_key,setting_value) VALUES (%s,'whatsapp_contacts',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (estate_id(), json.dumps(stored)))
        audit(cursor, "update", "whatsapp_language_preference", clean, {"language": language, "source": "self_service"}, f"WhatsApp {clean}")
    return True
