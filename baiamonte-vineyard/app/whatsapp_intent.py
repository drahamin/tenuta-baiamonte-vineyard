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


def capabilities(profile: str, italian: bool) -> str:
    menus = {
        "manager": (
            "Menu Manager — rispondi con un numero\n1 Oggi e allerte urgenti\n2 Meteo e previsioni\n3 Piano di lavoro e calendario\n4 Malattie e trattamenti\n5 Vendemmia, quantità e blend\n6 Cantina, vasche e laboratorio\n7 Cisterna\n8 Telecamere\n9 Presenze del team\n10 Solare, energia e dispositivi\n11 AIS, ADS-B, terremoti ed Etna\n12 Invia aggiornamento / revisione\n0 Aiuto e impostazioni\n\nComandi: INVIA FOTO [nome], ACCENDI/SPEGNI [dispositivo] (con conferma), PREFERENZE RISPOSTA, LINGUA, PERSONA.",
            "Manager menu — reply with a number\n1 Today and urgent alerts\n2 Weather and forecast\n3 Work plan and calendar\n4 Disease and treatments\n5 Harvest, quantities and blend\n6 Cellar, tanks and labs\n7 Cistern\n8 Cameras\n9 Team presence\n10 Solar, power and devices\n11 AIS, ADS-B, earthquakes and Etna\n12 Submit update / review\n0 Help and settings\n\nCommands: SEND [camera name] PHOTO, TURN ON/OFF [device] (with confirmation), REPLY SETTINGS, LANGUAGE, HUMAN.",
        ),
        "reporter": (
            "Menu Reporter — rispondi con un numero\n1 Lavoro di oggi e calendario\n2 Meteo\n3 Vendemmia prevista\n4 Trattamenti e sopralluoghi pianificati\n5 Invia ore, lavoro, foto o nota vocale\n0 Aiuto e impostazioni\n\nTutto ciò che invii resta in revisione. Comandi: PREFERENZE RISPOSTA, LINGUA, PERSONA.",
            "Reporter menu — reply with a number\n1 Today's work and calendar\n2 Weather\n3 Harvest projections\n4 Planned treatments and scouting\n5 Submit hours, work, photo or voice note\n0 Help and settings\n\nEverything you submit remains in review. Commands: REPLY SETTINGS, LANGUAGE, HUMAN.",
        ),
        "reception": (
            "Menu Reception — rispondi con un numero\n1 Tenuta e vini\n2 Meteo\n3 Informazioni pubbliche sulla vendemmia\n4 Lascia un messaggio al team\n5 Invia foto, documento o nota vocale\n0 Aiuto e impostazioni\n\nComandi: PREFERENZE RISPOSTA, LINGUA, PERSONA.",
            "Reception menu — reply with a number\n1 Estate and wines\n2 Weather\n3 Public harvest information\n4 Leave a message for the team\n5 Send a photo, document or voice note\n0 Help and settings\n\nCommands: REPLY SETTINGS, LANGUAGE, HUMAN.",
        ),
    }
    if profile in menus:
        return menus[profile][0 if italian else 1]
    return "Invia un messaggio per la revisione dell'amministratore. Digita PREFERENZE RISPOSTA per il formato delle risposte." if italian else "Send a message for administrator review. Type REPLY SETTINGS for reply-format choices."


def menu_route(profile: str, text: str, italian: bool) -> tuple[str, str] | None:
    """Translate a numbered IVR choice into a safe question or direct response."""
    match = re.fullmatch(r"(?:menu\s*)?(\d{1,2})", re.sub(r"\s+", " ", str(text or "").strip()).casefold())
    if not match:
        return None
    choice = int(match.group(1))
    if choice == 0:
        return ("reply", capabilities(profile, italian))
    routes = {
        "manager": {
            1: "What needs attention today? Summarize urgent alerts and the next decisions.",
            2: "Give me current Baiamonte weather, today's rain, forecast, and severe-weather advice.",
            3: "Give me the current work plan, priorities, deadlines, projects, tasks, and calendar.",
            4: "Give me current disease and stress pressure, planned treatments, and required reviews.",
            5: "Give me harvest readiness, projected dates for every grape, quantities, crates, and blend plan.",
            6: "Give me cellar tank status, stages, next checks, latest lab information, and suggestions requiring enologist review.",
            7: "Give me the latest cistern level, confidence, age, and any required action.",
            8: "CAMERAS",
            9: "Who is currently at Baiamonte? Include evidence freshness and do not infer presence.",
            10: "Give me solar production, forecast, power status, and approved-device status.",
            11: "Give me AIS, ADS-B, Catania airspace, earthquake, and Mount Etna status and alerts.",
            12: "Explain how to submit an operational update and how review and approval work.",
        },
        "reporter": {
            1: "Give me today's work plan, priorities, deadlines, and calendar.",
            2: "Give me current Baiamonte weather, today's rain, and the forecast.",
            3: "Give me harvest readiness and projected dates for every grape.",
            4: "Give me planned treatments and scouting work, clearly marked as pending review.",
            5: "Explain how to submit hours, completed work, observations, photos, documents, or a voice note for review.",
        },
        "reception": {
            1: "Tell me about Tenuta Baiamonte and its wines using only public information.",
            2: "Give me the latest public Baiamonte weather and forecast information available.",
            3: "Give me the latest public harvest information available.",
            4: "I would like to leave a message for the Baiamonte team.",
            5: "Explain how I can send a photo, document, or voice note to the team.",
        },
    }
    prompt = routes.get(profile, {}).get(choice)
    if not prompt:
        return ("reply", "Scelta non valida. Rispondi MENU per vedere le opzioni." if italian else "That choice is not available. Reply MENU to see the options.")
    if profile == "reception" and choice == 4:
        return ("handoff", prompt)
    return ("prompt", prompt + (" Rispondi in italiano." if italian else ""))
