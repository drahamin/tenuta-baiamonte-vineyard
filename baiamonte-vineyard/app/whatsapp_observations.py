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


KINDS = {"scouting", "phenology", "maturity_sample"}
SEVERITIES = ("trace", "low", "medium", "high", "critical")
MATURITY_DECISIONS = ("monitor", "resample", "hold", "ready", "picked")

ReplySender = Callable[..., Awaitable[None]]


def submission_menu(italian: bool) -> str:
    if italian:
        return (
            "Invia un rilievo — rispondi con un numero\n"
            "1 Sopralluogo in campo\n2 Fenologia / fase di crescita\n3 Maturità dell'uva\n"
            "4 Ore o servizio appaltatore\n5 Lavoro completato o attività\n"
            "6 Vendemmia o ricezione uva\n7 Cantina\n8 Trattamento\n9 Inventario, acquisto o spesa\n0 Annulla\n\n"
            "Le opzioni 1–3 sono moduli completi. Le altre acquisiscono il messaggio e gli allegati per la revisione appropriata."
        )
    return (
        "Submit a record — reply with a number\n"
        "1 Field scouting\n2 Phenology / growth stage\n3 Fruit maturity\n"
        "4 Labor or contractor service\n5 Completed work or task\n"
        "6 Harvest or grape receipt\n7 Cellar\n8 Treatment\n"
        "9 Inventory, purchase, or expense\n0 Cancel\n\n"
        "Choices 1–3 are complete guided forms. Other choices retain the message and attachments for the appropriate review."
    )


def submission_choice(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    choices = {
        "1": "scouting", "scouting": "scouting", "field scouting": "scouting", "sopralluogo": "scouting",
        "2": "phenology", "phenology": "phenology", "fenologia": "phenology", "growth stage": "phenology",
        "3": "maturity_sample", "maturity": "maturity_sample", "fruit maturity": "maturity_sample", "maturità": "maturity_sample", "maturita": "maturity_sample",
    }
    return choices.get(normalized)


def other_submission_choice(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return {
        "4": "labor", "5": "completed_work", "6": "harvest", "7": "cellar",
        "8": "treatment", "9": "inventory_finance", "0": "cancel",
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
        if normalized in names:
            return row
    raise ValueError("Choose a number or exact name from the list")


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
    return ["block", "variety_required", "sampled_at", "berry_count", "sample_kg", "brix", "ph", "ta_g_l", "yan_mg_l", "fruit_temp_c", "disease_pct", "condition_notes", "decision", "provisional_pick_date", "sampler", "notes"]


def prompt(state: dict[str, Any], blocks: list[dict[str, Any]], varieties: list[dict[str, Any]], italian: bool) -> str:
    steps = _steps(str(state["kind"]))
    step = int(state.get("step") or 0)
    if step >= len(steps):
        return summary(state, italian) + ("\n\nRispondi SALVA per registrare o ANNULLA." if italian else "\n\nReply SAVE to record it or CANCEL.")
    field = steps[step]
    block_list = "\n".join(f"{i}. {row.get('code')} — {row.get('name')}" for i, row in enumerate(blocks, 1))
    variety_list = "\n".join(f"{i}. {row.get('name')}" for i, row in enumerate(varieties, 1))
    stage_list = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(PHENOLOGY_STAGES, 1))
    issue_list = "\n".join(f"{i}. {row['label']}" for i, row in enumerate(SCOUTING_ISSUES, 1))
    options = {
        "block": (f"Scegli il blocco:\n{block_list}", f"Choose the vineyard block:\n{block_list}"),
        "variety": (f"Scegli la varietà oppure SALTA:\n{variety_list}", f"Choose the grape variety or SKIP:\n{variety_list}"),
        "variety_required": (f"Scegli la varietà:\n{variety_list}", f"Choose the grape variety:\n{variety_list}"),
        "observed_at": ("Data e ora osservazione: ADESSO oppure AAAA-MM-GG HH:MM.", "Observation date and time: NOW or YYYY-MM-DD HH:MM."),
        "observed_date": ("Data osservazione: OGGI oppure AAAA-MM-GG.", "Observation date: TODAY or YYYY-MM-DD."),
        "sampled_at": ("Data e ora campione: ADESSO oppure AAAA-MM-GG HH:MM.", "Sample date and time: NOW or YYYY-MM-DD HH:MM."),
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
    }
    return options[field][0 if italian else 1] + ("\n\nANNULLA per uscire." if italian else "\n\nCANCEL to exit.")


def apply_answer(state: dict[str, Any], text: str, blocks: list[dict[str, Any]], varieties: list[dict[str, Any]]) -> dict[str, Any]:
    updated = {**state, "values": dict(state.get("values") or {})}
    steps = _steps(str(updated["kind"]))
    field = steps[int(updated.get("step") or 0)]
    values = updated["values"]
    if field == "block":
        row = _catalog_choice(text, blocks)
        values.update({"block_id": row["id"], "_block": row.get("code") or row.get("name")})
    elif field in {"variety", "variety_required"}:
        row = _catalog_choice(text, varieties, allow_skip=field == "variety")
        if row:
            values.update({"variety_id": row["id"], "_variety": row.get("name")})
    elif field in {"observed_at", "sampled_at"}:
        values[field] = _date_value(text, with_time=True)
    elif field == "observed_date":
        values[field] = _date_value(text, with_time=False)
    elif field == "severity":
        values[field] = _choice(text, SEVERITIES)
    elif field == "stage":
        codes = tuple(code for code, _ in PHENOLOGY_STAGES)
        code = _choice(text, codes)
        values.update({"stage_code": code, "stage_name": dict(PHENOLOGY_STAGES)[code]})
    elif field == "decision":
        values[field] = _choice(text, MATURITY_DECISIONS)
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
    elif field == "fruit_temp_c":
        if not _optional(text): values[field] = _number(text, -20, 70)
    elif field == "provisional_pick_date":
        if not _optional(text): values[field] = _date_value(text, with_time=False)
    elif field in {"location_note", "condition_notes", "sampler", "notes"}:
        if not _optional(text): values[field] = text.strip()[:2000 if field in {"condition_notes", "notes"} else 255]
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


def summary(state: dict[str, Any], italian: bool) -> str:
    labels = {
        "scouting": ("Sopralluogo", "Field scouting"),
        "phenology": ("Fenologia", "Phenology"),
        "maturity_sample": ("Maturità uva", "Fruit maturity"),
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
    }
    rows = [f"{names.get(key, key)}: {('yes' if value else 'no') if key == 'action_required' else value}" for key, value in values.items() if key not in hidden and value not in (None, "")]
    title = labels[str(state["kind"])][0 if italian else 1]
    return title + "\n" + "\n".join(rows)


def values_for_save(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in (state.get("values") or {}).items() if not key.startswith("_")}


def active_submission(sender: str) -> dict[str, Any] | None:
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
    if normalized in {"cancel", "annulla", "stop", "0"}:
        await asyncio.to_thread(cancel_submission, event_id, sender)
        reply = "Invio annullato. Nessun record è stato creato." if italian else "Submission cancelled. No record was created."
        await send_reply(sender, reply, assignment)
        return True

    if active.get("kind") == "select":
        observation_kind = submission_choice(body)
        if observation_kind:
            state = new_state(observation_kind)
            blocks, varieties = await asyncio.to_thread(submission_catalogs)
            if not blocks or observation_kind == "maturity_sample" and not varieties:
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
            suffix = (
                "\n\nInvia ora tutto in un solo messaggio con eventuali foto. Sarà conservato per la revisione; nessuna approvazione è automatica."
                if italian else
                "\n\nNow send everything in one message with any photos. It will be retained for review; nothing is approved automatically."
            )
            await send_reply(sender, other_submission_guidance(other_kind, italian) + suffix, assignment, resolve_notice=False)
            return True
        await send_reply(sender, submission_menu(italian), assignment, resolve_notice=False)
        return True

    kind = str(active.get("kind") or "")
    blocks, varieties = await asyncio.to_thread(submission_catalogs)
    if completed(active):
        if normalized not in {"save", "salva", "confirm", "conferma"}:
            await send_reply(sender, prompt(active, blocks, varieties, italian), assignment, resolve_notice=False)
            return True
        try:
            saved = await asyncio.to_thread(save_quick_entry, kind, values_for_save(active))
            if kind == "maturity_sample":
                await asyncio.to_thread(request_harvest_refresh, kind, str(saved["id"]), "Structured WhatsApp field evidence saved")
            await asyncio.to_thread(update_submission, event_id, active, status="processed")
            with transaction() as (_, cursor):
                audit(cursor, "create", kind, str(saved["id"]), {"source": "whatsapp_guided_form", "submission_event_id": event_id}, f"WhatsApp {sender}")
            labels = {
                "scouting": ("Sopralluogo", "Field scouting"),
                "phenology": ("Fenologia", "Phenology"),
                "maturity_sample": ("Maturità uva", "Fruit maturity"),
            }
            label = labels[kind][0 if italian else 1]
            reply = (
                f"{label} registrato come evidenza. Non approva trattamenti o decisioni di vendemmia."
                if italian else
                f"{label} saved as evidence. It does not approve a treatment or harvest decision."
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
