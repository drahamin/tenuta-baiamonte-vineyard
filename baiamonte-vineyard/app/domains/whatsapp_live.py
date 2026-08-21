"""Live, verified manager snapshots for the WhatsApp assistant."""
from __future__ import annotations

import asyncio
from typing import Any

from ..db import fetch_all
from ..display_data import system_status_payload, weather_context_payload
from ..intelligence import (
    home_assistant_manager_context,
    home_assistant_manager_presence,
    latest_cistern_level,
    whatsapp_chatbot_reply,
    whatsapp_manager_traffic_context,
)
from ..service import estate_id, public_harvest_feed
from ..whatsapp_intent import capabilities


def _number(value: Any, decimals: int = 1) -> str:
    try:
        rendered = f"{float(value):.{decimals}f}"
        return rendered.rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


def _short_date(value: Any) -> str:
    return str(value or "—").replace("T", " ")[:16]


def live_snapshot(route: str, italian: bool, allowed_entities: list[str] | None = None, administrator: bool = False) -> str:
    """Build a compact manager answer exclusively from current DB and HA data."""
    if route == "snapshot_help":
        status = system_status_payload()
        services = status.get("services") or []
        attention = [item for item in services if item.get("state") in {"red", "amber"}]
        live = "; ".join(f"{item.get('name')}: {item.get('detail')}" for item in attention[:4]) or (
            "tutti i servizi principali rispondono" if italian else "all core services are responding"
        )
        heading = (
            f"Stato live ({status.get('checked_at') or 'ora'}): {live}."
            if italian else f"Live status ({status.get('checked_at') or 'now'}): {live}."
        )
        return heading + "\n\n" + capabilities("manager", italian, administrator)

    if route == "snapshot_weather":
        weather = weather_context_payload()
        current = weather.get("current") or {}
        forecasts = weather.get("forecast") or []
        advisories = weather.get("advisories") or []
        forecast_bits = []
        for row in forecasts[:3]:
            when = _short_date(row.get("datetime") or row.get("date"))[:10]
            condition = row.get("condition") or "—"
            high = row.get("temperature") if row.get("temperature") is not None else row.get("temp_max_c")
            low = row.get("templow") if row.get("templow") is not None else row.get("temp_min_c")
            forecast_bits.append(f"{when}: {condition}, {_number(low)}–{_number(high)}°C")

        def advisory_text(item: Any) -> str:
            if isinstance(item, dict):
                return str(item.get("title") or item.get("message") or item.get("detail") or "")
            return str(item or "")

        advice = "; ".join(filter(None, (advisory_text(item) for item in advisories[:2])))
        observed = _short_date(current.get("observed_at"))
        if italian:
            return (
                f"Meteo live Baiamonte ({observed}): {_number(current.get('temp_c'))}°C, umidità {_number(current.get('humidity_pct'), 0)}%, "
                f"pioggia {_number(current.get('rain_mm'))} mm, vento {_number(current.get('wind_kph'))} km/h, "
                f"condizione {current.get('condition') or 'non indicata'}. Previsioni: "
                + ("; ".join(forecast_bits) or "non disponibili")
                + (f". Avvisi: {advice}" if advice else ". Nessun avviso meteo attivo.")
            )
        return (
            f"Live Baiamonte weather ({observed}): {_number(current.get('temp_c'))}°C, humidity {_number(current.get('humidity_pct'), 0)}%, "
            f"rain {_number(current.get('rain_mm'))} mm, wind {_number(current.get('wind_kph'))} km/h, "
            f"condition {current.get('condition') or 'not reported'}. Forecast: "
            + ("; ".join(forecast_bits) or "unavailable")
            + (f". Advisories: {advice}" if advice else ". No active weather advisory.")
        )

    if route == "snapshot_work":
        rows = fetch_all(
            "SELECT title,category,status,priority,due_date FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
            "ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date,title LIMIT 8",
            (estate_id(),),
        )
        lines = [f"• {row.get('title')} · {row.get('priority') or 'normal'} · {_short_date(row.get('due_date'))[:10]} · {row.get('status')}" for row in rows]
        if italian:
            return f"Piano di lavoro live: {len(rows)} priorità mostrate.\n" + ("\n".join(lines) or "Nessun lavoro pianificato o in corso.")
        return f"Live work plan: {len(rows)} priorities shown.\n" + ("\n".join(lines) or "No planned or in-progress work.")

    if route == "snapshot_disease":
        pressure = fetch_all(
            "SELECT disease_name,risk_score,risk_level,assessment_date,suggested_action,agronomist_status FROM disease_pressure_assessments "
            "WHERE estate_id=%s AND assessment_date=(SELECT MAX(assessment_date) FROM disease_pressure_assessments WHERE estate_id=%s) "
            "ORDER BY risk_score DESC LIMIT 4",
            (estate_id(), estate_id()),
        )
        treatments = fetch_all(
            "SELECT purpose,block_code,planned_application_date,application_date,agronomist_approved FROM v_treatment_history "
            "WHERE estate_id=%s AND status='planned' ORDER BY COALESCE(planned_application_date,application_date) LIMIT 4",
            (estate_id(),),
        )
        risks = "; ".join(f"{row.get('disease_name')}: {_number(row.get('risk_score'))}/100 {row.get('risk_level') or ''}" for row in pressure) or ("nessuna valutazione" if italian else "no assessment")
        plans = "; ".join(f"{row.get('purpose')} ({row.get('block_code') or 'estate'}, {_short_date(row.get('planned_application_date') or row.get('application_date'))[:10]}, {'approved' if row.get('agronomist_approved') else 'review pending'})" for row in treatments) or ("nessun trattamento pianificato" if italian else "no planned treatments")
        guardrail = "Decisione e applicazione richiedono revisione dell’agronomo." if italian else "Any decision or application still requires agronomist review."
        return f"Pressione live: {risks}. Trattamenti: {plans}. {guardrail}" if italian else f"Live pressure: {risks}. Treatments: {plans}. {guardrail}"

    if route == "snapshot_harvest":
        rows = (public_harvest_feed().get("items") or [])[:3]
        lines = []
        for row in rows:
            date_value = row.get("predicted_date") or row.get("plan_date")
            harvested = row.get("total_kg")
            status = "harvested" if row.get("first_pick_date") else row.get("status") or "provisional"
            details = f" · {_number(harvested, 0)} kg recorded" if harvested is not None else ""
            lines.append(f"• {row.get('variety')}: {_short_date(date_value)[:10]} · {status} · {row.get('confidence') or 'confidence not set'}{details}")
        if italian:
            return "Previsione vendemmia live (le date restano stime):\n" + ("\n".join(lines) or "Nessuna previsione attiva.")
        return "Live harvest forecast (dates remain estimates):\n" + ("\n".join(lines) or "No active projections.")

    if route == "snapshot_cistern":
        level = latest_cistern_level()
        percent = float(level.get("level_percent") or 0)
        confidence = float(level.get("confidence") or 0)
        if confidence <= 1:
            confidence *= 100
        observed = level.get("observed_at") or "unknown"
        action = percent < 10
        if italian:
            return f"Cisterna: {percent:.1f}% (stima da telecamera, confidenza {confidence:.0f}%). Aggiornata: {observed}. " + ("Azione richiesta: livello molto basso." if action else "Nessuna azione urgente per il livello.")
        return f"Cistern: {percent:.1f}% (camera estimate, {confidence:.0f}% confidence). Updated: {observed}. " + ("Action required: critically low level." if action else "No urgent level action required.")

    if route == "snapshot_presence":
        if not administrator:
            return "Le presenze sono disponibili solo agli amministratori." if italian else "Team presence is available only to administrators."
        people = home_assistant_manager_presence()
        lines = [f"• {row.get('name')}: {row.get('presence')} · {row.get('evidence')} · {_short_date(row.get('last_updated'))}" for row in people]
        prefix = "Presenze live (nessuna inferenza da dati vecchi):" if italian else "Live presence (no inference from stale data):"
        return prefix + "\n" + "\n".join(lines)

    if route == "snapshot_power":
        status = system_status_payload()
        solar = status.get("solar") or {}
        power = status.get("power") or []
        ha = home_assistant_manager_context(allowed_entities or [])
        power_bits = [f"{item.get('name')}: {item.get('state')} {item.get('unit') or ''}".strip() for item in power[:5]]
        device_bits = [f"{item.get('name')}: {item.get('state')}" for item in (ha.get("allowed_devices") or [])[:6]]
        if italian:
            return f"Solare live: {_number(solar.get('current_power'), 0)} W ora, {_number(solar.get('energy_today'))} kWh oggi, previsione {_number(solar.get('forecast_energy_today'))} kWh oggi e {_number(solar.get('forecast_energy_tomorrow'))} kWh domani. Energia: {'; '.join(power_bits) or 'nessun indicatore disponibile'}. Dispositivi autorizzati: {'; '.join(device_bits) or 'nessuno configurato'}."
        return f"Live solar: {_number(solar.get('current_power'), 0)} W now, {_number(solar.get('energy_today'))} kWh today, forecast {_number(solar.get('forecast_energy_today'))} kWh today and {_number(solar.get('forecast_energy_tomorrow'))} kWh tomorrow. Power: {'; '.join(power_bits) or 'no indicators available'}. Allowed devices: {'; '.join(device_bits) or 'none configured'}."

    if route != "snapshot_traffic":
        raise ValueError(f"Unknown live WhatsApp route: {route}")
    traffic = whatsapp_manager_traffic_context()
    ais, adsb = traffic.get("ais") or {}, traffic.get("adsb") or {}
    alerts = fetch_all(
        "SELECT title,severity,triggered_at FROM alerts WHERE estate_id=%s AND status IN ('open','acknowledged') "
        "AND (LOWER(alert_type) IN ('etna','earthquake','seismic') OR LOWER(title) LIKE '%%etna%%' OR LOWER(title) LIKE '%%earthquake%%' OR LOWER(title) LIKE '%%terremoto%%') "
        "ORDER BY triggered_at DESC LIMIT 3",
        (estate_id(),),
    )
    vessel_count = int(ais.get("active_targets") or 0) if ais.get("available") else 0
    aircraft_count = int(adsb.get("active_targets") or 0) if adsb.get("available") else 0
    ais_state = f"{vessel_count} vessels" if ais.get("available") else "unavailable"
    adsb_state = f"{aircraft_count} aircraft" if adsb.get("available") else "unavailable"
    alert_text = "; ".join(str(row.get("title") or "Geological alert") for row in alerts) or ("nessun allarme Etna/terremoto attivo" if italian else "no active Etna/earthquake alerts")
    return f"Traffico e geologia: AIS {ais_state}; ADS-B {adsb_state}. {alert_text}." if italian else f"Traffic and geology: AIS {ais_state}; ADS-B {adsb_state}. {alert_text}."


async def live_assisted_snapshot(route: str, request_text: str, italian: bool, allowed_entities: list[str] | None = None, administrator: bool = False) -> str:
    """Explain verified live data with AI, retaining a deterministic fallback."""
    snapshot = await asyncio.to_thread(live_snapshot, route, italian, allowed_entities or [], administrator)
    if route == "snapshot_help":
        return snapshot
    prompt = (
        f"{request_text}\n\nVERIFIED CURRENT SNAPSHOT:\n{snapshot}\n\n"
        "Answer briefly and helpfully. Preserve the live quantities and timestamps. "
        "You may explain implications from the supplied live context, but clearly label estimates and never invent missing data. "
        f"Reply only in {'Italian' if italian else 'English'}."
    )
    try:
        result = await asyncio.to_thread(whatsapp_chatbot_reply, prompt, "manager", "it" if italian else "en", allowed_entities or [], administrator)
        answer = str(result.get("answer") or "").strip()
        if result.get("configured") and answer:
            return answer[:4096]
    except Exception:
        pass
    return snapshot
