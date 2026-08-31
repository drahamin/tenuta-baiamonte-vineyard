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
            "BAIAMONTE · MANAGER\nRispondi con un numero. Ogni riepilogo usa gli ultimi dati verificati.\n\n1 Oggi · allerte e decisioni\n2 Operazioni · lavoro, problemi e attrezzature\n3 Agronomia · meteo, campo e trattamenti\n4 Annata · vendemmia, quantità e blend\n5 Enologia · Tank Sensor, cantina, laboratorio e imbottigliamento\n6 Olive · raccolta, frantoio e olio\n7 Sistemi tenuta · cisterna, telecamere, energia, sicurezza ed Etna\n8 Ospitalità e registro vendite\n9 Team e finanza · solo amministratore\n10 Registra / invia dati (testo, foto o voce)\n11 Calcolatore cassette Nerello / Grenache\n12 Volpi del mese 🦊 · ultimo avvistamento e foto\n0 Aiuto, lingua e formato risposta\n\nComandi rapidi: + Menu · REGISTRA · INVIA FOTO [nome] · VOLPE · PREFERENZE RISPOSTA · LINGUA · PERSONA.",
            "BAIAMONTE · MANAGER\nReply with one number. Every summary uses the latest verified data.\n\n1 Today · alerts and decisions\n2 Operations · work, issues and equipment\n3 Agronomy · weather, field and treatments\n4 Vintage · harvest, quantities and blend\n5 Enology · Tank Sensor, cellar, laboratory and bottling\n6 Olives · harvest, mill and oil\n7 Estate systems · cistern, cameras, energy, security and Etna\n8 Hospitality and sales register\n9 Team and finance · administrator only\n10 Record / submit data (text, photo or voice)\n11 Nerello / Grenache crate calculator\n12 Foxes this month 🦊 · latest sighting and photo\n0 Help, language and reply format\n\nQuick commands: + Menu · RECORD · SEND [camera name] PHOTO · FOX · REPLY SETTINGS · LANGUAGE · HUMAN.",
        ),
        "reporter": (
            "BAIAMONTE · REPORTER\nRispondi con un numero.\n\n1 Lavoro di oggi, problemi e attrezzature\n2 Meteo e condizioni del campo\n3 Trattamenti e sopralluoghi\n4 Annata e vendemmia\n5 Tank Sensor e cantina\n6 Olive\n7 Registra / invia dati (testo, foto o voce)\n0 Aiuto, lingua e formato risposta\n\nOgni modulo richiede SALVA. Comandi: * Indietro · + Menu · = Annulla.",
            "BAIAMONTE · REPORTER\nReply with one number.\n\n1 Today's work, issues and equipment\n2 Weather and field conditions\n3 Treatments and scouting\n4 Vintage and harvest\n5 Tank Sensor and cellar\n6 Olives\n7 Record / submit data (text, photo or voice)\n0 Help, language and reply format\n\nEvery form requires SAVE. Commands: * Back · + Menu · = Cancel.",
        ),
        "reception": (
            "BAIAMONTE · OSPITI\nRispondi con un numero.\n\n1 Tenuta e vini\n2 Esperienze, degustazioni e richieste di prenotazione\n3 Meteo per la visita\n4 Informazioni pubbliche sull'annata\n5 Lascia un messaggio al team\n6 Invia foto, documento o nota vocale\n0 Aiuto, lingua e formato risposta\n\nComandi: PREFERENZE RISPOSTA · LINGUA · PERSONA.",
            "BAIAMONTE · GUESTS\nReply with one number.\n\n1 Estate and wines\n2 Experiences, tastings and reservation requests\n3 Weather for your visit\n4 Public vintage information\n5 Leave a message for the team\n6 Send a photo, document or voice note\n0 Help, language and reply format\n\nCommands: REPLY SETTINGS · LANGUAGE · HUMAN.",
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
        "operations": "snapshot_operations", "operazioni": "snapshot_operations", "issues": "snapshot_operations", "problemi": "snapshot_operations", "equipment": "snapshot_operations", "attrezzature": "snapshot_operations",
        "agronomy": "snapshot_agronomy", "agronomia": "snapshot_agronomy", "field": "snapshot_agronomy", "campo": "snapshot_agronomy",
        "enology": "snapshot_enology", "enologia": "snapshot_enology", "tank sensor": "snapshot_enology", "bottling": "snapshot_enology", "imbottigliamento": "snapshot_enology",
        "olives": "snapshot_olives", "olive": "snapshot_olives", "oil": "snapshot_olives", "olio": "snapshot_olives", "frantoio": "snapshot_olives",
        "estate systems": "snapshot_estate_systems", "sistemi tenuta": "snapshot_estate_systems", "security": "snapshot_estate_systems", "sicurezza": "snapshot_estate_systems",
        "hospitality": "snapshot_hospitality", "ospitalità": "snapshot_hospitality", "ospitalita": "snapshot_hospitality", "reservations": "snapshot_hospitality", "prenotazioni": "snapshot_hospitality", "register": "snapshot_hospitality", "registro vendite": "snapshot_hospitality",
        "finance": "snapshot_admin", "finanza": "snapshot_admin", "admin summary": "snapshot_admin", "riepilogo admin": "snapshot_admin",
        "fox": "snapshot_fox", "foxes": "snapshot_fox", "fox update": "snapshot_fox", "volpe": "snapshot_fox", "volpi": "snapshot_fox", "aggiornamento volpi": "snapshot_fox",
    }
    local_route = local_topics.get(normalized)
    if local_route:
        if profile == "reception" and local_route == "snapshot_hospitality":
            return ("snapshot_hospitality_public", normalized)
        manager_only = {"snapshot_cistern", "snapshot_cameras", "snapshot_power", "snapshot_traffic", "snapshot_estate_systems", "snapshot_hospitality", "snapshot_admin"}
        if profile == "manager" or local_route not in manager_only and profile in {"reporter", "reception"}:
            if local_route == "snapshot_admin" and not administrator:
                return ("reply", "Team e finanza sono disponibili solo agli amministratori." if italian else "Team and finance are available only to administrators.")
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
        return ("reply", "Team e finanza sono disponibili solo agli amministratori." if italian else "Team and finance are available only to administrators.")
    routes = {
        "manager": {
            1: "What needs attention today? Summarize urgent alerts and the next decisions.",
            0: "Show the live system status together with help and settings.",
            2: "Give me current operations, work, open issues, deadlines, and equipment checks.",
            3: "Give me current agronomy, weather, disease pressure, treatments, and required reviews.",
            4: "Give me harvest readiness, projected dates, quantities, crates, and blend status.",
            5: "Give me current Tank Sensor, cellar, laboratory, and bottling status.",
            6: "Give me current olive harvest, mill, oil output, and yield status.",
            7: "Give me current cistern, cameras, solar, devices, security, AIS, ADS-B, earthquake, and Etna status.",
            8: "Give me current hospitality, reservations, inquiries, and sales-register status without exposing guest contact details.",
            9: "Give me the administrator-only team, finance, payment, and review summary.",
            10: "OBSERVATION_FORMS",
            11: "BLEND_CRATE_CALCULATOR",
            12: "Give me this month's friendly fox update and the latest confirmed picture.",
        },
        "reporter": {
            1: "Give me today's work, open issues, deadlines, and equipment checks.",
            2: "Give me current Baiamonte weather and field conditions.",
            3: "Give me treatments, disease pressure, and scouting work, clearly marked as pending review.",
            4: "Give me vintage and harvest readiness with projected dates.",
            5: "Give me Tank Sensor and cellar status.",
            6: "Give me current olive harvest, mill, oil output, and yield status.",
            7: "OBSERVATION_FORMS",
        },
        "reception": {
            1: "ESTATE_AND_WINES",
            2: "HOSPITALITY_PUBLIC",
            3: "Give me the latest public Baiamonte weather and forecast information available.",
            4: "Give me the latest public vintage information available.",
            5: "I would like to leave a message for the Baiamonte team.",
            6: "MEDIA_HELP",
        },
    }
    prompt = routes.get(profile, {}).get(choice)
    if not prompt:
        return ("reply", "Scelta non valida. Invia + per vedere il menu." if italian else "That choice is not available. Send + to see the menu.")
    if profile == "reception" and choice == 5:
        return ("handoff", prompt)
    if profile == "reception" and choice == 1:
        return ("snapshot_estate", prompt)
    if profile == "reception" and choice == 2:
        return ("snapshot_hospitality_public", prompt)
    if profile == "reception" and choice == 6:
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
        2: "snapshot_operations",
        3: "snapshot_agronomy",
        4: "snapshot_harvest",
        5: "snapshot_enology",
        6: "snapshot_olives",
        7: "snapshot_estate_systems",
        8: "snapshot_hospitality",
        9: "snapshot_admin",
        12: "snapshot_fox",
    }
    if profile == "manager" and choice in manager_live_routes:
        return (manager_live_routes[choice], prompt)
    reporter_live_routes = {1: "snapshot_operations", 2: "snapshot_weather", 3: "snapshot_disease", 4: "snapshot_harvest", 5: "snapshot_enology", 6: "snapshot_olives"}
    if profile == "reporter" and choice in reporter_live_routes:
        return (reporter_live_routes[choice], prompt)
    reception_live_routes = {3: "snapshot_weather", 4: "snapshot_harvest"}
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
