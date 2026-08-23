"""Deterministic WhatsApp forms for vineyard field observations.

The conversational form deliberately collects database fields without asking an
AI model to invent identifiers or normalize measurements.  Saving remains a
separate, explicit confirmation handled by the WhatsApp channel.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime
from typing import Any, Awaitable, Callable

from .db import fetch_all, fetch_one, transaction
from .domains.messaging import event_payload
from .observation_catalog import PHENOLOGY_STAGES, SCOUTING_ISSUES, scouting_issue
from .prediction_refresh import request_harvest_refresh
from .quick_entry import save_quick_entry
from .service import audit, estate_id


KINDS = {
    "scouting", "phenology", "treatment", "work_activity", "labor", "issue",
    "maturity_sample", "fermentation", "cellar_operation", "equipment_event", "freeform_report",
}
SEVERITIES = ("trace", "low", "medium", "high", "critical")
MATURITY_DECISIONS = ("monitor", "resample", "hold", "ready", "picked")
ESTATE_SCOPE_KINDS = {"scouting", "treatment", "work_activity"}
ESTATE_CHOICE = {"id": None, "code": "ENTIRE ESTATE", "name": "All vineyard blocks", "estate_scope": True}

ReplySender = Callable[..., Awaitable[None]]


def expire_pending_states() -> int:
    """Close abandoned conversational state so an old session cannot capture a later reply."""
    with transaction() as (_, cursor):
        changed = cursor.execute(
            "UPDATE integration_events SET status='ignored',error_message='Expired after 24 hours without confirmation' "
            "WHERE estate_id=%s AND integration_name='whatsapp-channel' AND status='received' "
            "AND event_type IN ('structured_submission_pending','blend_crate_calculator_pending',"
            "'manager_device_control_pending','manager_control_pending','intake_approval_pending') "
            "AND occurred_at<DATE_SUB(NOW(),INTERVAL 24 HOUR)",
            (estate_id(),),
        )
    return int(changed or 0)


def ivr_status(voice_entry: bool) -> dict[str, Any]:
    """Return compact operational health for the Admin WhatsApp IVR panel."""
    expire_pending_states()
    session = fetch_one(
        "SELECT COUNT(*) active_sessions,"
        "SUM(CASE WHEN occurred_at<DATE_SUB(NOW(),INTERVAL 2 HOUR) THEN 1 ELSE 0 END) stalled_sessions "
        "FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='structured_submission_pending' AND status='received' "
        "AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR)", (estate_id(),),
    ) or {}
    activity = fetch_one(
        "SELECT COUNT(*) started_24h,SUM(status='processed') completed_24h,"
        "SUM(status='ignored') cancelled_24h,SUM(status='failed') failed_24h "
        "FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='structured_submission_pending' AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR)",
        (estate_id(),),
    ) or {}
    stalled, failed = int(session.get("stalled_sessions") or 0), int(activity.get("failed_24h") or 0)
    return {
        "health": "attention" if stalled or failed else "ready",
        "active_sessions": int(session.get("active_sessions") or 0), "stalled_sessions": stalled,
        "started_24h": int(activity.get("started_24h") or 0),
        "completed_24h": int(activity.get("completed_24h") or 0),
        "cancelled_24h": int(activity.get("cancelled_24h") or 0), "failed_24h": failed,
        "voice_entry": voice_entry,
        "workflows": [
            {"domain": "Agronomy / field", "items": ["Scouting and treatment follow-up", "Phenology", "Treatment field report"]},
            {"domain": "Operations", "items": ["Completed work", "Labor hours", "Issue / needed task", "Equipment / service"]},
            {"domain": "Enology field / cellar", "items": ["Fruit maturity", "Fermentation / tank check", "Cellar operation"]},
        ],
        "commands": ["RECORD / REGISTRA", "* BACK / INDIETRO", "SAVE / SALVA", "= CANCEL / ANNULLA", "+ MENU"],
    }


def submission_menu(italian: bool) -> str:
    if italian:
        return (
            "REGISTRA — rispondi con un numero o una nota vocale\n\n"
            "AGRONOMIA / CAMPO\n1 Sopralluogo (anche prima/dopo trattamento)\n2 Fenologia\n3 Rapporto trattamento\n\n"
            "OPERAZIONI\n4 Lavoro completato\n5 Ore di lavoro\n6 Problema o attività necessaria\n7 Attrezzatura / manutenzione\n\n"
            "ENOLOGIA SUL CAMPO / CANTINA\n8 Maturità dell'uva\n9 Controllo fermentazione / vasca\n10 Operazione di cantina\n\n"
            "11 Rapporto complesso con una sola nota vocale\n0 Annulla\n\n"
            "In ogni modulo: * Indietro · + Menu · = Annulla. Nessuna approvazione è automatica."
        )
    return (
        "RECORD — reply with a number or a voice note\n\n"
        "AGRONOMY / FIELD\n1 Field scouting (including pre/post treatment)\n2 Growth stage\n3 Treatment field report\n\n"
        "OPERATIONS\n4 Completed work\n5 Labor hours\n6 Issue or needed task\n7 Equipment / service\n\n"
        "ENOLOGY FIELD / CELLAR\n8 Fruit maturity\n9 Fermentation / tank check\n10 Cellar operation\n\n"
        "11 Complicated report in one voice note\n0 Cancel\n\n"
        "In every form: * Back · + Menu · = Cancel. Nothing is automatically approved."
    )


def submission_choice(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    choices = {
        "1": "scouting", "scouting": "scouting", "field scouting": "scouting", "sopralluogo": "scouting",
        "2": "phenology", "phenology": "phenology", "fenologia": "phenology", "growth stage": "phenology",
        "3": "treatment", "treatment": "treatment", "trattamento": "treatment",
        "4": "work_activity", "work": "work_activity", "completed work": "work_activity", "lavoro": "work_activity",
        "5": "labor", "labor": "labor", "hours": "labor", "ore": "labor",
        "6": "issue", "issue": "issue", "task": "issue", "problema": "issue", "attività": "issue", "attivita": "issue",
        "7": "equipment_event", "equipment": "equipment_event", "service": "equipment_event", "attrezzatura": "equipment_event",
        "8": "maturity_sample", "maturity": "maturity_sample", "fruit maturity": "maturity_sample", "maturità": "maturity_sample", "maturita": "maturity_sample",
        "9": "fermentation", "fermentation": "fermentation", "tank": "fermentation", "fermentazione": "fermentation", "vasca": "fermentation",
        "10": "cellar_operation", "cellar": "cellar_operation", "cellar operation": "cellar_operation", "cantina": "cellar_operation",
        "11": "freeform_report", "voice report": "freeform_report", "complex report": "freeform_report", "rapporto complesso": "freeform_report",
    }
    return choices.get(normalized)


def other_submission_choice(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return {
        "11": "voice_report", "0": "cancel",
    }.get(normalized)


def other_submission_guidance(kind: str, italian: bool) -> str:
    messages = {
        "labor": (
            "Invia un solo messaggio con: nome lavoratore/appaltatore, data o mese, ore oppure costo fisso, lavoro/servizio, luogo, spese e stato pagamento. Allega foto se disponibile. Sarà separato per persona e revisionato prima dell'approvazione.",
            "Send one message with worker/contractor name, day or month, hours or fixed job cost, work/service, location, expenses, and payment status. Attach evidence if available. It will be separated per person and reviewed before approval.",
        ),
        "completed_work": (
            "Invia lavoro svolto, data/ora, blocco o luogo, persona, quantità, costo e foto. Non dichiarare completato ciò che richiede ancora conferma.",
            "Send work performed, date/time, block or location, person, quantities, cost, and photo. Do not mark anything complete if confirmation is still required.",
        ),
        "harvest": (
            "Invia varietà, blocco, data/ora, peso lordo/tara/netto, cassette, temperatura, destinazione e foto. Le decisioni di raccolta restano da approvare.",
            "Send variety, block, date/time, gross/tare/net weight, crates, fruit temperature, destination, and photo. Harvest decisions remain subject to approval.",
        ),
        "cellar": (
            "Invia lotto, vasca, data/ora, operazione o fase, volume, temperatura, densità/Brix/pH, aggiunte con quantità, responsabile, prossimo controllo e foto.",
            "Send lot, tank, date/time, operation or stage, volume, temperature, density/Brix/pH, additions and quantities, responsible person, next check, and photo.",
        ),
        "treatment": (
            "Invia data, blocco, scopo, area, acqua, ogni prodotto con dose e totale, operatore, attrezzatura, meteo e note. Resta pianificato finché etichetta, PHI, REI, DPI, meteo e approvazione agronomica non sono confermati.",
            "Send date, block, purpose, area, water, every product with dose and total, operator, equipment, weather, and notes. It remains planned until label, PHI, REI, PPE, weather, and agronomist approvals are confirmed.",
        ),
        "inventory_finance": (
            "Invia prodotto/fornitore, data, quantità e unità, lotto, documento, costo, stato pagamento e foto della ricevuta/fattura. Le fatture ufficiali restano riconciliate con Fatture in Cloud.",
            "Send product/vendor, date, quantity and unit, lot, document number, cost, payment status, and receipt/invoice photo. Official invoices remain reconciled with Fatture in Cloud.",
        ),
        "voice_report": (
            "Invia ora una sola nota vocale. Di': tipo di lavoro o problema, data/ora, luogo o blocco, persone, quantità o letture e cosa serve dopo. La trascrizione e gli allegati saranno conservati per la revisione. Puoi anche scriverlo.",
            "Send one voice note now. Say: the work or issue, date/time, location or block, people, quantities or readings, and what is needed next. The transcript and attachments will be retained for review. You may type it instead.",
        ),
    }
    return messages[kind][0 if italian else 1]


def new_state(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError("Unsupported observation form")
    return {"kind": kind, "step": 0, "values": {}}


def _optional(text: str) -> bool:
    return re.sub(r"\s+", " ", text.strip()).casefold() in {"skip", "none", "no", "salta", "nessuno", "nessuna", "-"}


def _number(text: str, minimum: float, maximum: float) -> float:
    value = float(text.strip().replace(",", "."))
    if value < minimum or value > maximum:
        raise ValueError(f"Enter a value from {minimum:g} to {maximum:g}")
    return value


def _choice(text: str, options: tuple[str, ...]) -> str:
    normalized = text.strip().casefold().replace(" ", "_")
    if normalized.isdigit() and 1 <= int(normalized) <= len(options):
        return options[int(normalized) - 1]
    if normalized in options:
        return normalized
    raise ValueError("Choose one of the listed options")


def _catalog_choice(text: str, rows: list[dict[str, Any]], *, allow_skip: bool = False) -> dict[str, Any] | None:
    if allow_skip and _optional(text):
        return None
    normalized = re.sub(r"\s+", " ", text.strip()).casefold()
    if normalized.isdigit() and 1 <= int(normalized) <= len(rows):
        return rows[int(normalized) - 1]
    for row in rows:
        names = {str(row.get("code") or "").casefold(), str(row.get("name") or "").casefold()}
        if row.get("estate_scope"):
            names.update({"entire estate", "all estate", "whole estate", "intera tenuta", "tutta la tenuta"})
        if normalized in names:
            return row
    raise ValueError("Choose a number or exact name from the list")


def _block_choices(kind: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Offer a real estate scope only to record types whose storage supports it."""
    return [ESTATE_CHOICE, *blocks] if kind in ESTATE_SCOPE_KINDS else blocks


def _field_block_label(row: dict[str, Any], italian: bool) -> str:
    """Keep phone menus recognizable without repeating cadastral descriptions."""
    if row.get("estate_scope"):
        return "Intera tenuta" if italian else "Entire estate"
    code = str(row.get("code") or "").strip()
    name = str(row.get("name") or "").strip()
    variety = next(
        (label for prefix, label in (("GRC", "Grecanico"), ("GRN", "Grenache"), ("NM", "Nerello Mascalese")) if code.upper().startswith(prefix)),
        "",
    )
    young = "24" in code or "2024" in name
    age = ("viti giovani" if italian else "young vines") if young else ("viti adulte" if italian else "mature vines")
    if variety:
        return f"{variety} — {age} ({code})"
    concise_name = re.split(r"\s+[—-]\s+|\s+AGEA\b|\s+parcels?\b", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return f"{concise_name or code} ({code})" if concise_name and concise_name.casefold() != code.casefold() else code


def _date_value(text: str, *, with_time: bool) -> str:
    normalized = text.strip().casefold()
    if normalized in {"now", "adesso", "ora"}:
        return datetime.now().replace(microsecond=0).isoformat(sep=" ") if with_time else date.today().isoformat()
    if normalized in {"today", "oggi"}:
        return datetime.combine(date.today(), datetime.min.time()).isoformat(sep=" ") if with_time else date.today().isoformat()
    try:
        return datetime.fromisoformat(text.strip()).replace(microsecond=0).isoformat(sep=" ") if with_time else date.fromisoformat(text.strip()).isoformat()
    except ValueError as error:
        raise ValueError("Use YYYY-MM-DD" + (" HH:MM, TODAY, or NOW" if with_time else " or TODAY")) from error


def _steps(kind: str) -> list[str]:
    if kind == "scouting":
        return ["block", "observed_at", "issue_type", "severity", "incidence_pct", "location_note", "action_required", "notes"]
    if kind == "phenology":
        return ["block", "variety", "observed_date", "stage", "percent_complete", "notes"]
    if kind == "treatment":
        return ["block", "application_date", "purpose", "area_ha", "water_volume_l", "operator_name", "equipment_name", "product_plan", "weather_note", "notes"]
    if kind == "work_activity":
        return ["block_optional", "activity_date", "title", "labor_hours", "worker_count", "notes"]
    if kind == "labor":
        return ["work_date", "person_or_crew", "work_performed", "location_text", "regular_hours", "notes"]
    if kind == "issue":
        return ["issue_text", "priority", "owner_text", "due_date", "notes"]
    if kind == "fermentation":
        return ["vessel_name", "observed_at", "temp_c", "density_sg", "brix", "ph", "sensory_observation", "next_check_at"]
    if kind == "cellar_operation":
        return ["cellar_reference", "operation_at", "operation_type", "amount", "unit", "temp_c", "notes"]
    if kind == "equipment_event":
        return ["event_date", "asset_name", "pre_use_status", "maintenance_action", "next_due_date", "notes"]
    if kind == "freeform_report":
        return ["report_body"]
    return ["block", "variety_required", "sampled_at", "brix", "ph", "ta_g_l", "fruit_temp_c", "disease_pct", "condition_notes", "decision", "notes"]


def prompt(state: dict[str, Any], blocks: list[dict[str, Any]], varieties: list[dict[str, Any]], italian: bool) -> str:
    steps = _steps(str(state["kind"]))
    step = int(state.get("step") or 0)
    if step >= len(steps):
        return summary(state, italian) + ("\n\nSALVA per registrare · * Indietro · = Annulla" if italian else "\n\nSAVE to record · * Back · = Cancel")
    field = steps[step]
    block_rows = _block_choices(str(state["kind"]), blocks)
    block_list = "\n".join(f"{i}. {_field_block_label(row, italian)}" for i, row in enumerate(block_rows, 1))
    variety_list = "\n".join(f"{i}. {row.get('name')}" for i, row in enumerate(varieties, 1))
    stage_list = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(PHENOLOGY_STAGES, 1))
    issue_list = "\n".join(f"{i}. {row['label']}" for i, row in enumerate(SCOUTING_ISSUES, 1))
    options = {
        "block": (f"Dove? Rispondi o pronuncia il numero:\n{block_list}", f"Where? Reply or say the number:\n{block_list}"),
        "block_optional": (f"Dove? Rispondi o pronuncia il numero, oppure SALTA:\n{block_list}", f"Where? Reply or say the number, or SKIP:\n{block_list}"),
        "variety": (f"Scegli la varietà oppure SALTA:\n{variety_list}", f"Choose the grape variety or SKIP:\n{variety_list}"),
        "variety_required": (f"Scegli la varietà:\n{variety_list}", f"Choose the grape variety:\n{variety_list}"),
        "observed_at": ("Data e ora osservazione: ADESSO oppure AAAA-MM-GG HH:MM.", "Observation date and time: NOW or YYYY-MM-DD HH:MM."),
        "observed_date": ("Data osservazione: OGGI oppure AAAA-MM-GG.", "Observation date: TODAY or YYYY-MM-DD."),
        "sampled_at": ("Data e ora campione: ADESSO oppure AAAA-MM-GG HH:MM.", "Sample date and time: NOW or YYYY-MM-DD HH:MM."),
        "application_date": ("Data trattamento: OGGI oppure AAAA-MM-GG.", "Treatment date: TODAY or YYYY-MM-DD."),
        "activity_date": ("Data lavoro: OGGI oppure AAAA-MM-GG.", "Work date: TODAY or YYYY-MM-DD."),
        "work_date": ("Data lavoro: OGGI oppure AAAA-MM-GG.", "Work date: TODAY or YYYY-MM-DD."),
        "event_date": ("Data controllo/manutenzione: OGGI oppure AAAA-MM-GG.", "Equipment check/service date: TODAY or YYYY-MM-DD."),
        "operation_at": ("Data e ora operazione: ADESSO oppure AAAA-MM-GG HH:MM.", "Operation date and time: NOW or YYYY-MM-DD HH:MM."),
        "issue_type": (f"Cosa hai osservato? Scegli un numero:\n{issue_list}", f"What did you observe? Choose a number:\n{issue_list}"),
        "severity": ("Gravità: 1 traccia, 2 bassa, 3 media, 4 alta, 5 critica.", "Severity: 1 trace, 2 low, 3 medium, 4 high, 5 critical."),
        "incidence_pct": ("Incidenza stimata 0–100%, oppure SALTA.", "Estimated incidence 0–100%, or SKIP."),
        "location_note": ("Posizione precisa nel blocco, oppure SALTA.", "Specific location within the block, or SKIP."),
        "action_required": ("Serve un intervento? SÌ o NO. Questo non approva un trattamento.", "Is action needed? YES or NO. This does not approve a treatment."),
        "stage": (f"Scegli la fase:\n{stage_list}", f"Choose the growth stage:\n{stage_list}"),
        "percent_complete": ("Completamento della fase 0–100%, oppure SALTA.", "Stage completion 0–100%, or SKIP."),
        "berry_count": ("Numero di acini nel campione, oppure SALTA.", "Berry count in the sample, or SKIP."),
        "sample_kg": ("Peso campione in kg, oppure SALTA.", "Sample weight in kg, or SKIP."),
        "brix": ("Brix, oppure SALTA.", "Brix, or SKIP."),
        "ph": ("pH, oppure SALTA.", "pH, or SKIP."),
        "ta_g_l": ("Acidità totale g/L, oppure SALTA.", "Total acidity g/L, or SKIP."),
        "yan_mg_l": ("Azoto assimilabile YAN mg/L, oppure SALTA.", "YAN assimilable nitrogen mg/L, or SKIP."),
        "fruit_temp_c": ("Temperatura frutto °C, oppure SALTA.", "Fruit temperature °C, or SKIP."),
        "disease_pct": ("Frutti colpiti 0–100%, oppure SALTA.", "Affected fruit 0–100%, or SKIP."),
        "condition_notes": ("Condizione del frutto, oppure SALTA.", "Fruit condition, or SKIP."),
        "decision": ("Valutazione: 1 monitorare, 2 ricampionare, 3 attendere, 4 pronto, 5 raccolto. Non conferma la vendemmia.", "Assessment: 1 monitor, 2 resample, 3 hold, 4 ready, 5 picked. This does not confirm a harvest decision."),
        "provisional_pick_date": ("Data raccolta provvisoria AAAA-MM-GG, oppure SALTA.", "Provisional pick date YYYY-MM-DD, or SKIP."),
        "sampler": ("Nome di chi ha prelevato il campione, oppure SALTA.", "Name of sampler, or SKIP."),
        "notes": ("Note finali, oppure SALTA.", "Final notes, or SKIP."),
        "purpose": ("Scopo del trattamento (malattia/problema).", "Treatment purpose (disease/problem)."),
        "area_ha": ("Area trattata in ettari, oppure SALTA.", "Area treated in hectares, or SKIP."),
        "water_volume_l": ("Acqua totale in litri, oppure SALTA.", "Total water in liters, or SKIP."),
        "operator_name": ("Nome operatore, oppure SALTA.", "Operator name, or SKIP."),
        "equipment_name": ("Attrezzatura usata, oppure SALTA.", "Equipment used, or SKIP."),
        "product_plan": ("Elenca solo i prodotti realmente usati o richiesti, con dose e totale. Puoi inviare una nota vocale.", "List only products actually used or directed, with dose and total. You may send a voice note."),
        "weather_note": ("Meteo durante/dopo: vento, pioggia, temperatura, oppure SALTA.", "Weather during/after: wind, rain, temperature, or SKIP."),
        "title": ("Che lavoro è stato completato?", "What work was completed?"),
        "labor_hours": ("Ore totali impiegate, oppure SALTA.", "Total labor hours, or SKIP."),
        "worker_count": ("Numero lavoratori, oppure SALTA.", "Number of workers, or SKIP."),
        "person_or_crew": ("Nome persona, squadra o appaltatore.", "Person, crew, or contractor name."),
        "work_performed": ("Lavoro svolto.", "Work performed."),
        "location_text": ("Blocco o luogo, oppure SALTA.", "Block or location, or SKIP."),
        "regular_hours": ("Ore lavorate (massimo 24).", "Hours worked (maximum 24)."),
        "issue_text": ("Descrivi il problema o l'attività necessaria. Puoi usare una nota vocale.", "Describe the issue or needed task. You may use a voice note."),
        "priority": ("Priorità: 1 bassa, 2 media, 3 alta, 4 critica.", "Priority: 1 low, 2 medium, 3 high, 4 critical."),
        "owner_text": ("Chi deve occuparsene, oppure SALTA.", "Who should handle it, or SKIP."),
        "due_date": ("Scadenza AAAA-MM-GG, OGGI oppure SALTA.", "Due date YYYY-MM-DD, TODAY, or SKIP."),
        "vessel_name": ("Nome o numero vasca/recipiente.", "Tank or vessel name/number."),
        "temp_c": ("Temperatura °C, oppure SALTA.", "Temperature °C, or SKIP."),
        "density_sg": ("Densità SG, oppure SALTA.", "Density SG, or SKIP."),
        "sensory_observation": ("Osservazione, azione o condizione, oppure SALTA.", "Observation, action, or condition, or SKIP."),
        "next_check_at": ("Prossimo controllo AAAA-MM-GG HH:MM, oppure SALTA.", "Next check YYYY-MM-DD HH:MM, or SKIP."),
        "operation_type": ("Tipo operazione (es. travaso, aggiunta, controllo).", "Operation type (for example racking, addition, check)."),
        "cellar_reference": ("Nome/codice del lotto, vasca o recipiente.", "Wine lot, tank, or vessel name/code."),
        "amount": ("Quantità, oppure SALTA.", "Amount, or SKIP."),
        "unit": ("Unità della quantità, oppure SALTA.", "Amount unit, or SKIP."),
        "asset_name": ("Nome attrezzatura.", "Equipment name."),
        "pre_use_status": ("Condizione prima dell'uso, oppure SALTA.", "Condition before use, or SKIP."),
        "maintenance_action": ("Pulizia, manutenzione o azione svolta, oppure SALTA.", "Cleaning, service, or action performed, or SKIP."),
        "next_due_date": ("Prossima scadenza AAAA-MM-GG, oppure SALTA.", "Next due date YYYY-MM-DD, or SKIP."),
        "report_body": ("Invia una sola nota vocale o un messaggio con: cosa è successo o è stato fatto, quando, dove, chi, quantità/letture e cosa serve dopo.", "Send one voice note or message with: what happened or was done, when, where, who, quantities/readings, and what is needed next."),
    }
    return options[field][0 if italian else 1] + ("\n\nPuoi scrivere o parlare. * Indietro · + Menu · = Annulla" if italian else "\n\nType or speak. * Back · + Menu · = Cancel")


def apply_answer(state: dict[str, Any], text: str, blocks: list[dict[str, Any]], varieties: list[dict[str, Any]]) -> dict[str, Any]:
    updated = {**state, "values": dict(state.get("values") or {})}
    steps = _steps(str(updated["kind"]))
    field = steps[int(updated.get("step") or 0)]
    values = updated["values"]
    if field in {"block", "block_optional"}:
        row = _catalog_choice(text, _block_choices(str(updated["kind"]), blocks), allow_skip=field == "block_optional")
        if row:
            if row.get("estate_scope"):
                values.pop("block_id", None)
                values["_block"] = "Entire estate"
                if updated["kind"] == "scouting":
                    values.update({"damage_scope": "estate", "representative_survey": 1})
            else:
                values.update({"block_id": row["id"], "_block": row.get("code") or row.get("name")})
                if updated["kind"] == "scouting":
                    values.update({"damage_scope": "block", "representative_survey": 0})
    elif field in {"variety", "variety_required"}:
        row = _catalog_choice(text, varieties, allow_skip=field == "variety")
        if row:
            values.update({"variety_id": row["id"], "_variety": row.get("name")})
    elif field in {"observed_at", "sampled_at", "operation_at", "next_check_at"}:
        if not _optional(text):
            values[field] = _date_value(text, with_time=True)
    elif field in {"observed_date", "application_date", "activity_date", "work_date", "event_date", "due_date", "next_due_date"}:
        if not _optional(text):
            values[field] = _date_value(text, with_time=False)
    elif field == "severity":
        values[field] = _choice(text, SEVERITIES)
    elif field == "stage":
        codes = tuple(code for code, _ in PHENOLOGY_STAGES)
        code = _choice(text, codes)
        values.update({"stage_code": code, "stage_name": dict(PHENOLOGY_STAGES)[code]})
    elif field == "decision":
        values[field] = _choice(text, MATURITY_DECISIONS)
    elif field == "priority":
        values[field] = _choice(text, ("low", "medium", "high", "critical"))
    elif field == "action_required":
        normalized = text.strip().casefold()
        if normalized in {"yes", "y", "si", "sì", "1"}:
            values[field] = 1
        elif normalized in {"no", "n", "0"}:
            values[field] = 0
        else:
            raise ValueError("Reply YES or NO")
    elif field in {"incidence_pct", "percent_complete", "disease_pct"}:
        if not _optional(text): values[field] = _number(text, 0, 100)
    elif field in {"area_ha", "water_volume_l", "labor_hours", "amount"}:
        if not _optional(text): values[field] = _number(text, 0, 1000000)
    elif field == "worker_count":
        if not _optional(text): values[field] = int(_number(text, 1, 1000))
    elif field == "regular_hours":
        values[field] = _number(text, 0.01, 24)
    elif field == "berry_count":
        if not _optional(text): values[field] = int(_number(text, 1, 100000))
    elif field == "sample_kg":
        if not _optional(text): values[field] = _number(text, 0.001, 1000)
    elif field == "brix":
        if not _optional(text): values[field] = _number(text, 0, 40)
    elif field == "ph":
        if not _optional(text): values[field] = _number(text, 0, 14)
    elif field == "ta_g_l":
        if not _optional(text): values[field] = _number(text, 0, 100)
    elif field == "yan_mg_l":
        if not _optional(text): values[field] = _number(text, 0, 1000)
    elif field in {"fruit_temp_c", "temp_c"}:
        if not _optional(text): values[field] = _number(text, -20, 70)
    elif field == "density_sg":
        if not _optional(text): values[field] = _number(text, 0.5, 2)
    elif field == "provisional_pick_date":
        if not _optional(text): values[field] = _date_value(text, with_time=False)
    elif field in {
        "location_note", "condition_notes", "sampler", "notes", "purpose", "operator_name",
        "equipment_name", "product_plan", "weather_note", "title", "person_or_crew",
        "work_performed", "location_text", "issue_text", "owner_text", "vessel_name",
        "sensory_observation", "operation_type", "unit", "asset_name", "pre_use_status",
        "maintenance_action", "cellar_reference",
        "report_body",
    }:
        if not _optional(text):
            values[field] = text.strip()[:4000 if field in {"condition_notes", "notes", "issue_text", "report_body", "sensory_observation"} else 255]
    elif field == "issue_type":
        rows = [{"code": row["code"], "name": row["label"]} for row in SCOUTING_ISSUES]
        try:
            row = _catalog_choice(text, rows)
        except ValueError:
            normalized = re.sub(r"\s+", " ", text.strip()).casefold()
            matches = [row for row in rows if str(row["name"]).casefold().startswith(normalized)]
            if len(matches) != 1:
                raise
            row = matches[0]
        issue = scouting_issue(row["code"])
        values.update({field: issue["code"], "_issue": issue["label"]})
    updated["step"] = int(updated.get("step") or 0) + 1
    return updated


def completed(state: dict[str, Any]) -> bool:
    return int(state.get("step") or 0) >= len(_steps(str(state["kind"])))


def previous_state(state: dict[str, Any]) -> dict[str, Any]:
    """Move back one question, or return to record selection from the first question."""
    current_step = int(state.get("step") or 0)
    if current_step <= 0:
        return {"kind": "select", "step": 0, "values": {}}
    previous = {**state, "values": dict(state.get("values") or {}), "step": current_step - 1}
    field = _steps(str(state["kind"]))[int(previous["step"])]
    storage_keys = {
        "block": ("block_id", "_block", "damage_scope", "representative_survey"),
        "block_optional": ("block_id", "_block", "damage_scope", "representative_survey"),
        "variety": ("variety_id", "_variety"),
        "variety_required": ("variety_id", "_variety"),
        "stage": ("stage_code", "stage_name"),
        "issue_type": ("issue_type", "_issue"),
    }.get(field, (field,))
    for key in storage_keys:
        previous["values"].pop(key, None)
    return previous


def summary(state: dict[str, Any], italian: bool) -> str:
    labels = {
        "scouting": ("Sopralluogo", "Field scouting"),
        "phenology": ("Fenologia", "Phenology"),
        "treatment": ("Rapporto trattamento — da approvare", "Treatment field report — approval required"),
        "work_activity": ("Lavoro completato", "Completed work"),
        "labor": ("Ore di lavoro", "Labor hours"),
        "issue": ("Problema / attività", "Issue / needed task"),
        "maturity_sample": ("Maturità uva", "Fruit maturity"),
        "fermentation": ("Controllo fermentazione", "Fermentation check"),
        "cellar_operation": ("Operazione di cantina", "Cellar operation"),
        "equipment_event": ("Attrezzatura / manutenzione", "Equipment / service"),
        "freeform_report": ("Rapporto vocale complesso", "Complicated voice report"),
    }
    values = state.get("values") or {}
    hidden = {"block_id", "variety_id"}
    names = {
        "observed_at": "Observed", "observed_date": "Observed", "sampled_at": "Sampled",
        "issue_type": "Issue", "severity": "Severity", "incidence_pct": "Incidence %",
        "location_note": "Location", "action_required": "Action needed", "stage_name": "Stage",
        "percent_complete": "Complete %", "berry_count": "Berries", "sample_kg": "Sample kg",
        "brix": "Brix", "ph": "pH", "ta_g_l": "TA g/L", "yan_mg_l": "YAN mg/L", "fruit_temp_c": "Fruit °C",
        "disease_pct": "Affected %", "condition_notes": "Condition", "decision": "Assessment",
        "provisional_pick_date": "Provisional pick", "sampler": "Sampler", "notes": "Notes",
        "_block": "Block", "_variety": "Variety", "_issue": "Observation", "stage_code": "Stage code",
        "application_date": "Treatment date", "purpose": "Purpose", "area_ha": "Area ha", "water_volume_l": "Water L",
        "operator_name": "Operator", "equipment_name": "Equipment", "product_plan": "Products/doses", "weather_note": "Weather",
        "activity_date": "Work date", "title": "Work", "labor_hours": "Hours", "worker_count": "Workers",
        "work_date": "Work date", "person_or_crew": "Person/crew", "work_performed": "Work", "location_text": "Location", "regular_hours": "Hours",
        "issue_text": "Issue/task", "priority": "Priority", "owner_text": "Owner", "due_date": "Due",
        "vessel_name": "Tank/vessel", "temp_c": "Temperature °C", "density_sg": "Density SG", "sensory_observation": "Observation", "next_check_at": "Next check",
        "operation_at": "Operation time", "operation_type": "Operation", "amount": "Amount", "unit": "Unit",
        "cellar_reference": "Lot/tank",
        "event_date": "Event date", "asset_name": "Equipment", "pre_use_status": "Condition", "maintenance_action": "Action", "next_due_date": "Next due",
        "report_body": "Report",
    }
    rows = [f"{names.get(key, key)}: {('yes' if value else 'no') if key == 'action_required' else value}" for key, value in values.items() if key not in hidden and value not in (None, "")]
    title = labels[str(state["kind"])][0 if italian else 1]
    return title + "\n" + "\n".join(rows)


def values_for_save(state: dict[str, Any]) -> dict[str, Any]:
    kind = str(state.get("kind") or "")
    values = {key: value for key, value in (state.get("values") or {}).items() if not key.startswith("_")}
    if kind == "treatment":
        details = []
        if values.pop("product_plan", None):
            details.append("Products and doses reported by field: " + str(state["values"]["product_plan"]))
        if values.pop("weather_note", None):
            details.append("Field weather: " + str(state["values"]["weather_note"]))
        if values.get("notes"):
            details.append(str(values["notes"]))
        values["notes"] = "\n".join(details) or "WhatsApp field report; Agronomist review required."
        values.update({"crop_scope": "vineyard", "status": "planned"})
    elif kind == "labor":
        values.update({"role": "Field worker", "work_category": "field_work", "entry_source": "whatsapp_labor", "payment_status": "unpaid", "payroll_scope": "contractor"})
    elif kind == "issue":
        values.update({"issue_type": "Operations", "status": "open", "opened_date": date.today().isoformat()})
    elif kind == "freeform_report":
        report = str(values.pop("report_body", "") or "").strip()
        values = {
            "opened_date": date.today().isoformat(), "subject_ref": "WhatsApp voice/text field report",
            "issue_type": "Operations", "priority": "medium", "issue_text": report,
            "evidence_summary": "Submitted through the guided WhatsApp complex-report workflow; any original voice transcript remains in intake evidence.",
            "owner_text": "Operations review", "status": "open",
        }
    elif kind == "cellar_operation":
        reference = str(values.pop("cellar_reference", "") or "").strip()
        existing_notes = str(values.get("notes") or "").strip()
        values["notes"] = f"Reported lot/tank: {reference}" + (f"\n{existing_notes}" if existing_notes else "")
    return values


def active_submission(sender: str) -> dict[str, Any] | None:
    expire_pending_states()
    row = fetch_one(
        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='structured_submission_pending' AND external_id=%s AND status='received' "
        "AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR) ORDER BY occurred_at DESC LIMIT 1",
        (estate_id(), sender),
    )
    return {**event_payload(row.get("payload")), "_event_id": row.get("id")} if row else None


def submission_catalogs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocks = fetch_all(
        "SELECT id,code,name FROM vineyard_blocks WHERE estate_id=%s AND active=1 ORDER BY code",
        (estate_id(),),
    )
    varieties = fetch_all(
        "SELECT id,name FROM grape_varieties WHERE estate_id=%s AND active=1 "
        "AND LOWER(name) NOT IN ('blend','other') ORDER BY name",
        (estate_id(),),
    )
    return blocks, varieties


def begin_submission(sender: str, state: dict[str, Any], actor: str) -> int:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET status='ignored' WHERE estate_id=%s AND integration_name='whatsapp-channel' "
            "AND event_type='structured_submission_pending' AND external_id=%s AND status='received'",
            (estate_id(), sender),
        )
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,'whatsapp-channel','inbound','structured_submission_pending',%s,'received',%s)",
            (estate_id(), sender, json.dumps(state)),
        )
        event_id = int(cursor.lastrowid)
        audit(cursor, "start", "whatsapp_structured_submission", str(event_id), {"kind": state.get("kind")}, actor)
    return event_id


def update_submission(event_id: int, state: dict[str, Any], *, status: str = "received") -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET payload=%s,status=%s,error_message=NULL WHERE id=%s AND estate_id=%s "
            "AND event_type='structured_submission_pending'",
            (json.dumps(state), status, event_id, estate_id()),
        )


def cancel_submission(event_id: int, sender: str) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET status='ignored' WHERE id=%s AND estate_id=%s AND status='received'",
            (event_id, estate_id()),
        )
        audit(cursor, "cancel", "whatsapp_structured_submission", str(event_id), {}, f"WhatsApp {sender}")


async def continue_submission(
    sender: str,
    body: str,
    assignment: dict[str, Any],
    italian: bool,
    send_reply: ReplySender,
) -> bool:
    """Advance a bounded WhatsApp form and save only after explicit confirmation."""
    active = active_submission(sender)
    if not active:
        return False
    event_id = int(active.pop("_event_id"))
    normalized = re.sub(r"\s+", " ", body.strip()).casefold()
    if normalized in {"+", "plus", "più", "piu", "menu", "home", "start", "inizio"}:
        await asyncio.to_thread(cancel_submission, event_id, sender)
        from .whatsapp_intent import capabilities
        await send_reply(
            sender,
            capabilities(str(assignment.get("profile") or "reporter"), italian, bool(assignment.get("administrator"))),
            assignment,
            resolve_notice=False,
        )
        return True
    if normalized in {"=", "equals", "uguale", "cancel", "annulla", "stop", "0"}:
        await asyncio.to_thread(cancel_submission, event_id, sender)
        reply = ("Invio annullato. Nessun record è stato creato. Invia + per tornare al menu." if italian else "Submission cancelled. No record was created. Send + to return to the menu.")
        await send_reply(sender, reply, assignment)
        return True

    if active.get("kind") == "select":
        observation_kind = submission_choice(body)
        if observation_kind:
            state = new_state(observation_kind)
            blocks, varieties = await asyncio.to_thread(submission_catalogs)
            needs_blocks = observation_kind in {"scouting", "phenology", "treatment", "maturity_sample"}
            needs_varieties = observation_kind in {"phenology", "maturity_sample"}
            if needs_blocks and not blocks or needs_varieties and not varieties:
                await asyncio.to_thread(update_submission, event_id, state, status="failed")
                reply = (
                    "Il modulo non è disponibile perché mancano blocchi o varietà configurati. Il messaggio resta in revisione."
                    if italian else
                    "This form is unavailable because configured blocks or grape varieties are missing. Your message remains in review."
                )
                await send_reply(sender, reply, assignment, resolve_notice=False)
                return True
            await asyncio.to_thread(update_submission, event_id, state)
            await send_reply(sender, prompt(state, blocks, varieties, italian), assignment, resolve_notice=False)
            return True
        other_kind = other_submission_choice(body)
        if other_kind and other_kind != "cancel":
            await asyncio.to_thread(update_submission, event_id, active, status="processed")
            await send_reply(sender, other_submission_guidance(other_kind, italian), assignment, resolve_notice=False)
            return True
        await send_reply(sender, submission_menu(italian), assignment, resolve_notice=False)
        return True

    kind = str(active.get("kind") or "")
    blocks, varieties = await asyncio.to_thread(submission_catalogs)
    if normalized in {"*", "star", "asterisk", "asterisco", "back", "indietro", "previous", "precedente"}:
        previous = previous_state(active)
        await asyncio.to_thread(update_submission, event_id, previous)
        reply = submission_menu(italian) if previous["kind"] == "select" else prompt(previous, blocks, varieties, italian)
        await send_reply(sender, reply, assignment, resolve_notice=False)
        return True
    if completed(active):
        if normalized not in {"save", "salva", "confirm", "conferma"}:
            await send_reply(sender, prompt(active, blocks, varieties, italian), assignment, resolve_notice=False)
            return True
        try:
            save_kind = "issue" if kind == "freeform_report" else kind
            saved = await asyncio.to_thread(save_quick_entry, save_kind, values_for_save(active))
            if kind == "maturity_sample":
                await asyncio.to_thread(request_harvest_refresh, kind, str(saved["id"]), "Structured WhatsApp field evidence saved")
            await asyncio.to_thread(update_submission, event_id, active, status="processed")
            with transaction() as (_, cursor):
                audit(cursor, "create", kind, str(saved["id"]), {"source": "whatsapp_guided_form", "submission_event_id": event_id}, f"WhatsApp {sender}")
            labels = {
                "scouting": ("Sopralluogo", "Field scouting"),
                "phenology": ("Fenologia", "Phenology"),
                "treatment": ("Rapporto trattamento pianificato", "Planned treatment field report"),
                "work_activity": ("Lavoro completato", "Completed work"),
                "labor": ("Ore di lavoro", "Labor hours"),
                "issue": ("Problema / attività", "Issue / needed task"),
                "maturity_sample": ("Maturità uva", "Fruit maturity"),
                "fermentation": ("Controllo fermentazione", "Fermentation check"),
                "cellar_operation": ("Operazione di cantina", "Cellar operation"),
                "equipment_event": ("Controllo attrezzatura", "Equipment check"),
                "freeform_report": ("Rapporto complesso", "Complicated report"),
            }
            label = labels[kind][0 if italian else 1]
            reply = (
                f"✓ {label} registrato. Non approva trattamenti o decisioni di vendemmia. Rispondi REGISTRA per un altro o + per il menu."
                if italian else
                f"✓ {label} saved. It does not approve a treatment or harvest decision. Reply RECORD for another or + for the menu."
            )
            await send_reply(sender, reply, assignment)
        except Exception as error:
            await send_reply(sender, ("Salvataggio non riuscito: " if italian else "Could not save: ") + str(error)[:240], assignment, resolve_notice=False)
        return True

    try:
        updated = apply_answer(active, body, blocks, varieties)
        await asyncio.to_thread(update_submission, event_id, updated)
        await send_reply(sender, prompt(updated, blocks, varieties, italian), assignment, resolve_notice=False)
    except (TypeError, ValueError) as error:
        retry = ("Valore non valido: " if italian else "Invalid value: ") + str(error)
        await send_reply(sender, retry + "\n\n" + prompt(active, blocks, varieties, italian), assignment, resolve_notice=False)
    return True
