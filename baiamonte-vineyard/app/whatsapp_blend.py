from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from typing import Any, Awaitable, Callable

from .db import fetch_one, transaction
from .domains.harvest import calculate_grenache_crate_target
from .domains.messaging import event_payload
from .service import audit, estate_id

ReplySender = Callable[..., Awaitable[None]]


def pending_action(sender: str, code: str, event_type: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' AND event_type=%s AND external_id=%s AND status='received' AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR) ORDER BY occurred_at DESC LIMIT 1",
        (estate_id(), event_type, f"{sender}:{code}"),
    )
    return {**event_payload(row.get("payload")), "_event_id": row.get("id")} if row else None


def current_settings(year: int) -> dict[str, float]:
    row = fetch_one(
        "SELECT grenache_pct,crate_weight_kg FROM blend_program_settings WHERE estate_id=%s AND vintage_year=%s",
        (estate_id(), year),
    ) or {}
    return {"grenache_pct": float(row.get("grenache_pct") or 6.5), "crate_weight_kg": float(row.get("crate_weight_kg") or 15)}


def parse_crate_count(text: str) -> float:
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold().replace(",", ".")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:crates?|cassette?|casse)?", normalized)
    if not match:
        raise ValueError("Enter only the Nerello crate count")
    value = float(match.group(1))
    if not 0 < value <= 100000:
        raise ValueError("Nerello crates must be greater than zero")
    return value


def active_calculator(sender: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT id,payload FROM integration_events WHERE estate_id=%s AND integration_name='whatsapp-channel' "
        "AND event_type='blend_crate_calculator_pending' AND external_id=%s AND status='received' "
        "AND occurred_at>=DATE_SUB(NOW(),INTERVAL 24 HOUR) ORDER BY occurred_at DESC LIMIT 1",
        (estate_id(), sender),
    )
    return {**event_payload(row.get("payload")), "_event_id": row.get("id")} if row else None


def begin_calculator(sender: str, year: int) -> int:
    state = {"vintage_year": year}
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET status='ignored' WHERE estate_id=%s AND integration_name='whatsapp-channel' "
            "AND event_type='blend_crate_calculator_pending' AND external_id=%s AND status='received'",
            (estate_id(), sender),
        )
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,'whatsapp-channel','inbound','blend_crate_calculator_pending',%s,'received',%s)",
            (estate_id(), sender, json.dumps(state)),
        )
        event_id = int(cursor.lastrowid)
        audit(cursor, "start", "whatsapp_blend_crate_calculator", str(event_id), state, f"WhatsApp {sender}")
    return event_id


def finish_calculator(event_id: int, sender: str, status: str, payload: dict[str, Any]) -> None:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE integration_events SET payload=%s,status=%s,error_message=NULL WHERE id=%s AND estate_id=%s "
            "AND event_type='blend_crate_calculator_pending' AND status='received'",
            (json.dumps(payload), status, event_id, estate_id()),
        )
        audit(cursor, status, "whatsapp_blend_crate_calculator", str(event_id), payload, f"WhatsApp {sender}")


async def continue_calculator(sender: str, body: str, assignment: dict[str, Any], italian: bool, send_reply: ReplySender) -> bool:
    active = active_calculator(sender)
    if not active:
        return False
    event_id = int(active.pop("_event_id"))
    normalized = re.sub(r"\s+", " ", body.strip()).casefold()
    if normalized in {"cancel", "annulla", "stop", "0"}:
        await asyncio.to_thread(finish_calculator, event_id, sender, "ignored", active)
        await send_reply(sender, "Calcolatore annullato." if italian else "Calculator cancelled.", assignment)
        return True
    try:
        nerello_crates = parse_crate_count(body)
        year = int(active.get("vintage_year") or date.today().year)
        settings = await asyncio.to_thread(current_settings, year)
        result = calculate_grenache_crate_target(nerello_crates, settings["grenache_pct"])
        completed = {**active, **result, "crate_weight_kg": settings["crate_weight_kg"]}
        await asyncio.to_thread(finish_calculator, event_id, sender, "processed", completed)
        if italian:
            reply = (
                f"Raccogli {result['whole_grenache_crates']} cassette di Grenache per {result['nerello_crates']:g} cassette di Nerello.\n"
                f"Obiettivo Grenache {result['grenache_pct']:g}%: calcolo esatto {result['exact_grenache_crates']:g}, arrotondato in eccesso. Peso configurato: {settings['crate_weight_kg']:g} kg/cassetta."
            )
        else:
            reply = (
                f"Pick {result['whole_grenache_crates']} Grenache crates for {result['nerello_crates']:g} Nerello crates.\n"
                f"Grenache target {result['grenache_pct']:g}%: exact result {result['exact_grenache_crates']:g}, rounded up. Configured crate weight: {settings['crate_weight_kg']:g} kg."
            )
        await send_reply(sender, reply, assignment)
    except (TypeError, ValueError):
        retry = "Inserisci solo il numero di cassette di Nerello, per esempio 100. ANNULLA per uscire." if italian else "Enter only the number of Nerello crates, for example 100. Reply CANCEL to exit."
        await send_reply(sender, retry, assignment, resolve_notice=False)
    return True
