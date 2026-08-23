"""Small, deterministic WhatsApp intent guards used before AI replies."""

from __future__ import annotations

import re
from typing import Any


def is_submission(body: str, analysis: dict[str, Any]) -> bool:
    """Return true only for deliberate operational record submissions."""
    text = " ".join(str(body or "").strip().split())
    if not text or analysis.get("contains_question") or "?" in text:
        return False
    if re.match(
        r"^(?:what|when|where|why|who|how|is|are|can|could|would|will|show|tell|give|check|weather|forecast|status|"
        r"cosa|quando|dove|perch[eé]|chi|come|[eè]|sono|puoi|potresti|mostra|dimmi|meteo|previsioni|stato)\b",
        text,
        re.I,
    ):
        return False
    explicit_report = re.search(
        r"\b(?:record|log|report|add|save|worked|completed|finished|applied|treated|harvested|picked|received|observed|"
        r"registra|annota|segnala|aggiungi|salva|lavorat[oaie]|completat[oaie]|finit[oaie]|applicat[oaie]|trattat[oaie]|"
        r"raccolt[oaie]|ricevut[oaie]|osservat[oaie])\b",
        text,
        re.I,
    )
    measured_report = re.search(
        r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hours?|ore|min|kg|g|l|ml|mm|cm|m|%|°c|c|crates?|cassette?)\b",
        text,
        re.I,
    )
    classification = str(analysis.get("classification") or "other")
    return classification != "other" and bool(explicit_report or measured_report)


def language_preference(text: str) -> str | None:
    """Recognize only explicit bilingual self-service language commands."""
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    if normalized in {"language", "language settings", "lingua", "impostazioni lingua"}:
        return "help"
    if normalized in {"english", "language english", "set language english", "lingua inglese", "imposta lingua inglese"}:
        return "en"
    if normalized in {"italiano", "italian", "language italian", "set language italian", "lingua italiana", "imposta lingua italiana"}:
        return "it"
    if normalized in {"language automatic", "language auto", "automatic language", "lingua automatica", "lingua auto"}:
        return "auto"
    return None


def handoff_requested(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return bool(re.fullmatch(
        r"(?:human|person|administrator|admin|team|contact the team|speak to (?:a )?(?:person|human|manager)|"
        r"persona|amministratore|squadra|team|contatta (?:il )?team|parlare con (?:una )?persona|parlare con (?:un )?responsabile)",
        normalized,
    ))


def capabilities(profile: str, italian: bool, administrator: bool = False) -> str:
    menus = {
        "manager": (
            "Menu Manager — rispondi con un numero\n1 Oggi e allerte urgenti\n2 Meteo e previsioni\n3 Piano di lavoro e calendario\n4 Malattie e trattamenti\n5 Vendemmia, quantità e blend\n6 Cantina, vasche e laboratorio\n7 Cisterna\n8 Telecamere\n9 Presenze del team\n10 Solare, energia e dispositivi\n11 AIS, ADS-B, terremoti ed Etna\n12 Invia rilievo o record operativo (testo o voce)\n13 Calcolatore cassette Nerello / Grenache\n0 Aiuto e impostazioni\n\nScorciatoie: * Indietro · + Menu · = Annulla. Puoi anche dire REGISTRA, INVIA FOTO [nome], PREFERENZE RISPOSTA, LINGUA o PERSONA.",
            "Manager menu — reply with a number\n1 Today and urgent alerts\n2 Weather and forecast\n3 Work plan and calendar\n4 Disease and treatments\n5 Harvest, quantities and blend\n6 Cellar, tanks and labs\n7 Cistern\n8 Cameras\n9 Team presence\n10 Solar, power and devices\n11 AIS, ADS-B, earthquakes and Etna\n12 Submit field or operational record (text or voice)\n13 Nerello / Grenache crate calculator\n0 Help and settings\n\nShortcuts: * Back · + Menu · = Cancel. You can also say RECORD, SEND [camera name] PHOTO, REPLY SETTINGS, LANGUAGE, or HUMAN.",
        ),
        "reporter": (
            "Menu Reporter — rispondi con un numero\n1 Lavoro di oggi e calendario\n2 Meteo\n3 Vendemmia prevista\n4 Trattamenti e sopralluoghi pianificati\n5 Invia rilievo o record operativo (testo o voce)\n0 Aiuto e impostazioni\n\nTutti i moduli mostrano un riepilogo e richiedono SALVA. Scorciatoie: * Indietro · + Menu · = Annulla.",
            "Reporter menu — reply with a number\n1 Today's work and calendar\n2 Weather\n3 Harvest projections\n4 Planned treatments and scouting\n5 Submit field or operational record (text or voice)\n0 Help and settings\n\nEvery form shows a summary and requires SAVE. Shortcuts: * Back · + Menu · = Cancel.",
        ),
        "reception": (
            "Menu Reception — rispondi con un numero\n1 Tenuta e vini\n2 Meteo\n3 Informazioni pubbliche sulla vendemmia\n4 Lascia un messaggio al team\n5 Invia foto, documento o nota vocale\n0 Aiuto e impostazioni\n\nComandi: PREFERENZE RISPOSTA, LINGUA, PERSONA.",
            "Reception menu — reply with a number\n1 Estate and wines\n2 Weather\n3 Public harvest information\n4 Leave a message for the team\n5 Send a photo, document or voice note\n0 Help and settings\n\nCommands: REPLY SETTINGS, LANGUAGE, HUMAN.",
        ),
    }
    if profile in menus:
        menu = menus[profile][0 if italian else 1]
        if profile == "manager" and not administrator:
            menu = "\n".join(line for line in menu.splitlines() if not line.startswith("9 "))
        return menu
    return "Invia un messaggio per la revisione dell'amministratore. Digita PREFERENZE RISPOSTA per il formato delle risposte." if italian else "Send a message for administrator review. Type REPLY SETTINGS for reply-format choices."


def menu_route(profile: str, text: str, italian: bool, administrator: bool = False) -> tuple[str, str] | None:
    """Translate a numbered IVR choice into a safe question or direct response."""
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    if profile in {"manager", "reporter"} and normalized in {
        "record", "entry", "report", "log", "submit", "registra", "invia", "rilievo",
    }:
        return ("observation_menu", "OBSERVATION_FORMS")
    local_topics = {
        "weather": "snapshot_weather", "forecast": "snapshot_weather", "meteo": "snapshot_weather", "previsioni": "snapshot_weather",
        "work": "snapshot_work", "work plan": "snapshot_work", "tasks": "snapshot_work", "lavoro": "snapshot_work", "attività": "snapshot_work", "attivita": "snapshot_work",
        "disease": "snapshot_disease", "treatments": "snapshot_disease", "malattie": "snapshot_disease", "trattamenti": "snapshot_disease",
        "harvest": "snapshot_harvest", "vendemmia": "snapshot_harvest",
        "cellar": "snapshot_cellar", "tanks": "snapshot_cellar", "labs": "snapshot_cellar", "cantina": "snapshot_cellar", "vasche": "snapshot_cellar", "laboratorio": "snapshot_cellar",
        "cistern": "snapshot_cistern", "cisterna": "snapshot_cistern",
        "cameras": "snapshot_cameras", "camera": "snapshot_cameras", "telecamere": "snapshot_cameras", "telecamera": "snapshot_cameras",
        "power": "snapshot_power", "solar": "snapshot_power", "energia": "snapshot_power", "solare": "snapshot_power",
        "traffic": "snapshot_traffic", "etna": "snapshot_traffic", "earthquakes": "snapshot_traffic", "traffico": "snapshot_traffic", "terremoti": "snapshot_traffic",
    }
    local_route = local_topics.get(normalized)
    if local_route:
        manager_only = {"snapshot_cistern", "snapshot_cameras", "snapshot_power", "snapshot_traffic"}
        if profile == "manager" or local_route not in manager_only and profile in {"reporter", "reception"}:
            return (local_route, normalized)
    if profile == "manager" and normalized in {"today", "alerts", "oggi", "allerte"}:
        return ("snapshot_today", normalized)
    if profile == "manager" and administrator and normalized in {"presence", "team presence", "presenze", "presenze team"}:
        return ("snapshot_presence", normalized)
    match = re.fullmatch(r"(?:menu\s*)?(\d{1,2})", normalized)
    if not match:
        return None
    choice = int(match.group(1))
    if choice == 0 and profile != "manager":
        return ("reply", capabilities(profile, italian, administrator))
    if profile == "manager" and choice == 9 and not administrator:
        return ("reply", "Le presenze sono disponibili solo agli amministratori." if italian else "Team presence is available only to administrators.")
    routes = {
        "manager": {
            1: "What needs attention today? Summarize urgent alerts and the next decisions.",
            0: "Show the live system status together with help and settings.",
            2: "Give me current Baiamonte weather, today's rain, forecast, and severe-weather advice.",
            3: "Give me the current work plan, priorities, deadlines, projects, tasks, and calendar.",
            4: "Give me current disease and stress pressure, planned treatments, and required reviews.",
            5: "Give me harvest readiness, projected dates for every grape, quantities, crates, and blend plan.",
            6: "Give me cellar tank status, stages, next checks, latest lab information, and suggestions requiring enologist review.",
            7: "Give me the latest cistern level, evidence time, confidence, and whether action is needed.",
            8: "CAMERAS",
            9: "Who is currently at Baiamonte? Include evidence freshness and do not infer presence.",
            10: "Give me solar production, forecast, power status, and approved-device status.",
            11: "Give me live AIS and ADS-B status plus current earthquake and Etna alerts.",
            12: "OBSERVATION_FORMS",
            13: "BLEND_CRATE_CALCULATOR",
        },
        "reporter": {
            1: "Give me today's work plan, priorities, deadlines, and calendar.",
            2: "Give me current Baiamonte weather, today's rain, and the forecast.",
            3: "Give me harvest readiness and projected dates for every grape.",
            4: "Give me planned treatments and scouting work, clearly marked as pending review.",
            5: "OBSERVATION_FORMS",
        },
        "reception": {
            1: "ESTATE_AND_WINES",
            2: "Give me the latest public Baiamonte weather and forecast information available.",
            3: "Give me the latest public harvest information available.",
            4: "I would like to leave a message for the Baiamonte team.",
            5: "MEDIA_HELP",
        },
    }
    prompt = routes.get(profile, {}).get(choice)
    if not prompt:
        return ("reply", "Scelta non valida. Invia + per vedere il menu." if italian else "That choice is not available. Send + to see the menu.")
    if profile == "reception" and choice == 4:
        return ("handoff", prompt)
    if profile == "reception" and choice == 1:
        return ("snapshot_estate", prompt)
    if profile == "reception" and choice == 5:
        return (
            "reply",
            "Puoi inviare qui una foto, un documento o una nota vocale. Aggiungi nome, motivo e data; il team la esaminerà prima di confermare qualsiasi richiesta."
            if italian else
            "Send a photo, document, or voice note here. Add your name, the reason, and the date; the team will review it before confirming any request.",
        )
    if profile in {"manager", "reporter"} and prompt == "OBSERVATION_FORMS":
        return ("observation_menu", prompt)
    if profile == "manager" and prompt == "BLEND_CRATE_CALCULATOR":
        return ("blend_crate_calculator", prompt)
    manager_live_routes = {
        0: "snapshot_help",
        1: "snapshot_today",
        2: "snapshot_weather",
        3: "snapshot_work",
        4: "snapshot_disease",
        5: "snapshot_harvest",
        6: "snapshot_cellar",
        7: "snapshot_cistern",
        8: "snapshot_cameras",
        9: "snapshot_presence",
        10: "snapshot_power",
        11: "snapshot_traffic",
    }
    if profile == "manager" and choice in manager_live_routes:
        return (manager_live_routes[choice], prompt)
    reporter_live_routes = {1: "snapshot_work", 2: "snapshot_weather", 3: "snapshot_harvest", 4: "snapshot_disease"}
    if profile == "reporter" and choice in reporter_live_routes:
        return (reporter_live_routes[choice], prompt)
    reception_live_routes = {2: "snapshot_weather", 3: "snapshot_harvest"}
    if profile == "reception" and choice in reception_live_routes:
        return (reception_live_routes[choice], prompt)
    return ("prompt", prompt + (" Rispondi in italiano." if italian else ""))


def prefers_italian(text: str, configured: str, sender: str = "") -> bool:
    """Resolve reply language from preference, message wording, then country code."""
    if configured == "it":
        return True
    if configured == "en":
        return False
    if re.search(r"\b(ciao|grazie|per favore|aggiorna|controlla|conferma|approva|rifiuta|vigneto|cantina|oggi)\b", text, re.I):
        return True
    if re.search(r"\b(hello|thanks|please|update|check|confirm|approve|reject|vineyard|cellar|today)\b", text, re.I):
        return False
    number = re.sub(r"\D", "", str(sender or ""))
    return number.startswith("39")
