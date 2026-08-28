"""Live, verified manager snapshots for the WhatsApp assistant."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo

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


ROME = ZoneInfo("Europe/Rome")
ITALIAN_WEEKDAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
ITALIAN_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
CONDITION_LABELS = {
    "clear-night": ("clear overnight", "sereno durante la notte"),
    "cloudy": ("cloudy", "nuvoloso"),
    "exceptional": ("unusual conditions", "condizioni insolite"),
    "fog": ("foggy", "nebbioso"),
    "hail": ("hail", "grandine"),
    "lightning": ("thunderstorms", "temporali"),
    "lightning-rainy": ("thunderstorms with rain", "temporali con pioggia"),
    "partlycloudy": ("partly cloudy", "parzialmente nuvoloso"),
    "pouring": ("heavy rain", "pioggia intensa"),
    "rainy": ("rainy", "piovoso"),
    "snowy": ("snowy", "nevoso"),
    "snowy-rainy": ("sleet", "nevischio"),
    "sunny": ("sunny", "soleggiato"),
    "windy": ("windy", "ventoso"),
    "windy-variant": ("windy with clouds", "ventoso con nuvole"),
}


def _parse_temporal(value: Any) -> tuple[datetime | None, bool]:
    """Parse database/HA dates; naive timestamps are stored as UTC."""
    if isinstance(value, datetime):
        parsed, date_only = value, False
    elif isinstance(value, date):
        parsed, date_only = datetime.combine(value, time()), True
    else:
        text = str(value or "").strip()
        if not text:
            return None, False
        date_only = len(text) <= 10
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None, date_only
    if date_only:
        return parsed, True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ROME), False


def _human_date(value: Any, italian: bool = False, *, include_time: bool = False, reference: datetime | None = None) -> str:
    parsed, date_only = _parse_temporal(value)
    if not parsed:
        return "data non disponibile" if italian else "date unavailable"
    local = parsed if date_only else parsed.astimezone(ROME)
    today = (reference or datetime.now(ROME)).astimezone(ROME).date()
    delta = (local.date() - today).days
    if delta == 0:
        day_text = "oggi" if italian else "today"
    elif delta == 1:
        day_text = "domani" if italian else "tomorrow"
    elif delta == -1:
        day_text = "ieri" if italian else "yesterday"
    elif italian:
        day_text = f"{ITALIAN_WEEKDAYS[local.weekday()]} {local.day} {ITALIAN_MONTHS[local.month - 1]}"
    else:
        day_text = f"{local.strftime('%A, %B')} {local.day}"
    if not include_time or date_only:
        return day_text
    if italian:
        return f"{day_text} alle {local:%H:%M}"
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{day_text} at {hour}:{local:%M} {local:%p}"


def _condition(value: Any, italian: bool = False) -> str:
    key = str(value or "").strip().casefold().replace("_", "-").replace(" ", "-")
    if key in CONDITION_LABELS:
        return CONDITION_LABELS[key][1 if italian else 0]
    if not key:
        return "non indicata" if italian else "not reported"
    return key.replace("-", " ")


def _natural_join(values: list[str], italian: bool = False) -> str:
    clean = [value.strip() for value in values if value and value.strip()]
    if len(clean) < 2:
        return clean[0] if clean else ""
    conjunction = " e " if italian else " and "
    return ", ".join(clean[:-1]) + conjunction + clean[-1]


ISO_TEMPORAL = re.compile(
    r"(?<![/=\w])(?P<value>\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?)(?![\w/?=&])"
)


def humanize_reply(text: str, italian: bool = False, *, reference: datetime | None = None) -> str:
    """Remove raw timestamps and compressed weather labels before delivery."""
    value = str(text or "")

    def temporal(match: re.Match[str]) -> str:
        raw = match.group("value")
        return _human_date(raw, italian, include_time=len(raw) > 10, reference=reference)

    value = ISO_TEMPORAL.sub(temporal, value)
    for key, labels in sorted(CONDITION_LABELS.items(), key=lambda item: -len(item[0])):
        value = re.sub(rf"(?<![\w/-]){re.escape(key)}(?![\w/-])", labels[1 if italian else 0], value, flags=re.I)
    return value


def live_snapshot(
    route: str,
    italian: bool,
    allowed_entities: list[str] | None = None,
    administrator: bool = False,
    allowed_cameras: list[str] | None = None,
) -> str:
    """Build a compact manager answer exclusively from current DB and HA data."""
    if route == "snapshot_help":
        status = system_status_payload()
        services = status.get("services") or []
        attention = [item for item in services if item.get("state") in {"red", "amber"}]
        live = "; ".join(f"{item.get('name')}: {item.get('detail')}" for item in attention[:4]) or (
            "tutti i servizi principali rispondono" if italian else "all core services are responding"
        )
        heading = (
            f"Aggiornamento di {_human_date(status.get('checked_at'), True, include_time=True)}: {live}."
            if italian else f"Here is the update from {_human_date(status.get('checked_at'), include_time=True)}: {live}."
        )
        return heading + "\n\n" + capabilities("manager", italian, administrator)

    if route == "snapshot_today":
        alerts = fetch_all(
            "SELECT title,severity,triggered_at FROM alerts WHERE estate_id=%s AND status IN ('open','acknowledged') "
            "ORDER BY FIELD(severity,'critical','high','warning','medium','low'),triggered_at DESC LIMIT 5",
            (estate_id(),),
        )
        alert_lines = [f"• {row.get('title')} ({row.get('severity') or 'attention'})" for row in alerts]
        work = live_snapshot("snapshot_work", italian, allowed_entities, administrator, allowed_cameras)
        if italian:
            return "Oggi: " + (f"{len(alerts)} avvisi da controllare.\n" + "\n".join(alert_lines) if alerts else "nessun avviso urgente aperto.") + "\n\n" + work
        return "Today: " + (f"{len(alerts)} alerts need review.\n" + "\n".join(alert_lines) if alerts else "there are no open urgent alerts.") + "\n\n" + work

    if route == "snapshot_operations":
        work = live_snapshot("snapshot_work", italian, allowed_entities, administrator, allowed_cameras)
        issues = fetch_all(
            "SELECT issue_text,priority,due_date,status FROM issues_decisions WHERE estate_id=%s "
            "AND status IN ('open','monitoring') ORDER BY FIELD(priority,'critical','high','medium','low'),due_date IS NULL,due_date LIMIT 5",
            (estate_id(),),
        )
        equipment = fetch_all(
            "SELECT asset_name,pre_use_status,released,next_due_date FROM equipment_service_events WHERE estate_id=%s "
            "ORDER BY event_date DESC,id DESC LIMIT 4",
            (estate_id(),),
        )
        issue_lines = [f"• {row.get('issue_text')} — {row.get('priority')}; {_human_date(row.get('due_date'), italian) if row.get('due_date') else ('senza scadenza' if italian else 'no due date')}" for row in issues]
        equipment_lines = [f"• {row.get('asset_name')}: {row.get('pre_use_status') or ('stato non registrato' if italian else 'status not recorded')} · {(('rilasciata' if italian else 'released') if row.get('released') else ('verifica richiesta' if italian else 'check required'))}" for row in equipment]
        if italian:
            return work + "\n\nProblemi aperti:\n" + ("\n".join(issue_lines) or "Nessun problema aperto.") + "\n\nAttrezzature recenti:\n" + ("\n".join(equipment_lines) or "Nessun controllo attrezzatura registrato.")
        return work + "\n\nOpen issues:\n" + ("\n".join(issue_lines) or "No open issues.") + "\n\nRecent equipment checks:\n" + ("\n".join(equipment_lines) or "No equipment checks recorded.")

    if route == "snapshot_agronomy":
        weather = live_snapshot("snapshot_weather", italian, allowed_entities, administrator, allowed_cameras)
        disease = live_snapshot("snapshot_disease", italian, allowed_entities, administrator, allowed_cameras)
        return ("AGRONOMIA CORRENTE\n" if italian else "CURRENT AGRONOMY\n") + weather + "\n\n" + disease

    if route == "snapshot_estate":
        wines = fetch_all(
            "SELECT name FROM products WHERE estate_id=%s AND active=1 AND LOWER(category_name)='vino' ORDER BY name LIMIT 12",
            (estate_id(),),
        )
        names = _natural_join([str(row.get("name") or "") for row in wines], italian)
        if italian:
            return "Tenuta Baiamonte è una tenuta vitivinicola sull’Etna. " + (f"I vini registrati disponibili sono {names}." if names else "Per disponibilità e degustazioni, lascia nome, data e numero di ospiti.")
        return "Tenuta Baiamonte is a wine estate on Mount Etna. " + (f"The currently recorded wines are {names}." if names else "For availability and tastings, leave your name, preferred date, and number of guests.")

    if route == "snapshot_hospitality_public":
        packages = fetch_all(
            "SELECT name,description,duration_minutes,min_guests,max_guests FROM hospitality_packages "
            "WHERE estate_id=%s AND active=1 ORDER BY sort_order,name LIMIT 8",
            (estate_id(),),
        )
        lines = [f"• {row.get('name')} — {row.get('duration_minutes')} min, {row.get('min_guests')}–{row.get('max_guests')} ospiti" if italian else f"• {row.get('name')} — {row.get('duration_minutes')} min, {row.get('min_guests')}–{row.get('max_guests')} guests" for row in packages]
        action = "Per richiedere una data, invia nome, giorno preferito, numero di ospiti, lingua e qualsiasi esigenza alimentare. La richiesta richiede conferma del team." if italian else "To request a date, send your name, preferred day, guest count, language, and any dietary needs. The team must confirm the request."
        heading = "Esperienze Baiamonte attualmente registrate:" if italian else "Currently registered Baiamonte experiences:"
        return heading + "\n" + ("\n".join(lines) or ("Informazioni in aggiornamento." if italian else "Experience information is being updated.")) + "\n\n" + action

    if route == "snapshot_weather":
        weather = weather_context_payload()
        current = weather.get("current") or {}
        forecasts = weather.get("forecast") or []
        advisories = weather.get("advisories") or []
        forecast_bits: list[str] = []
        for row in forecasts[:3]:
            when = _human_date(row.get("datetime") or row.get("date"), italian)
            condition = _condition(row.get("condition"), italian)
            high = row.get("temperature") if row.get("temperature") is not None else row.get("temp_max_c")
            low = row.get("templow") if row.get("templow") is not None else row.get("temp_min_c")
            forecast_bits.append(
                f"{when} sarà {condition}, con una minima di {_number(low)}°C e una massima di {_number(high)}°C"
                if italian else f"{when} will be {condition}, with a low of {_number(low)}°C and a high of {_number(high)}°C"
            )

        def advisory_text(item: Any) -> str:
            if isinstance(item, dict):
                return str(item.get("title") or item.get("message") or item.get("detail") or "")
            return str(item or "")

        advice = _natural_join(list(filter(None, (advisory_text(item) for item in advisories[:2]))), italian)
        observed = _human_date(current.get("observed_at"), italian, include_time=True)
        rain = _number(current.get("rain_mm"))
        rain_text = ("senza pioggia" if rain == "0" else f"con {rain} mm di pioggia") if italian else ("with no rain" if rain == "0" else f"with {rain} mm of rain")
        if italian:
            return (
                f"A Baiamonte, {observed}, il tempo era {_condition(current.get('condition'), True)}, con {_number(current.get('temp_c'))}°C. "
                f"L’umidità era del {_number(current.get('humidity_pct'), 0)}%, {rain_text} e vento a {_number(current.get('wind_kph'))} km/h.\n\n"
                + ("Per i prossimi giorni, " + "; ".join(forecast_bits) + "." if forecast_bits else "Le previsioni non sono disponibili.")
                + (f"\n\nDa tenere presente: {advice}." if advice else "\n\nNon ci sono avvisi meteo attivi.")
            )
        return (
            f"At Baiamonte, {observed}, it was {_condition(current.get('condition'))} and {_number(current.get('temp_c'))}°C. "
            f"Humidity was {_number(current.get('humidity_pct'), 0)}%, {rain_text}, and wind was {_number(current.get('wind_kph'))} km/h.\n\n"
            + ("Looking ahead, " + "; ".join(forecast_bits) + "." if forecast_bits else "The forecast is not available right now.")
            + (f"\n\nPlease note: {advice}." if advice else "\n\nThere are no active weather advisories.")
        )

    if route == "snapshot_work":
        rows = fetch_all(
            "SELECT title,category,status,priority,due_date FROM tasks WHERE estate_id=%s AND status IN ('planned','in_progress') "
            "ORDER BY FIELD(priority,'urgent','high','normal','low'),due_date IS NULL,due_date,title LIMIT 8",
            (estate_id(),),
        )
        lines = [f"• {row.get('title')} — {row.get('priority') or 'normal'}, due {_human_date(row.get('due_date'), italian)} ({str(row.get('status') or '').replace('_', ' ')})" for row in rows]
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
        plans = "; ".join(f"{row.get('purpose')} ({row.get('block_code') or 'estate'}, {_human_date(row.get('planned_application_date') or row.get('application_date'), italian)}, {'approved' if row.get('agronomist_approved') else 'review pending'})" for row in treatments) or ("nessun trattamento pianificato" if italian else "no planned treatments")
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
            lines.append(f"• {row.get('variety')}: {_human_date(date_value, italian)} — {status}, {row.get('confidence') or 'confidence not set'}{details}")
        if italian:
            return "Previsione vendemmia live (le date restano stime):\n" + ("\n".join(lines) or "Nessuna previsione attiva.")
        return "Live harvest forecast (dates remain estimates):\n" + ("\n".join(lines) or "No active projections.")

    if route == "snapshot_olives":
        summary = (fetch_all(
            "SELECT record_year,COALESCE(SUM(olives_harvested_kg),0) olives_kg,COALESCE(SUM(oil_liters),0) oil_l,AVG(yield_pct) yield_pct "
            "FROM olive_records WHERE estate_id=%s GROUP BY record_year ORDER BY record_year DESC LIMIT 1",
            (estate_id(),),
        ) or [{}])[0]
        recent = fetch_all(
            "SELECT record_date,mill_date,activity,status,olives_harvested_kg,oil_liters,yield_pct FROM olive_records "
            "WHERE estate_id=%s ORDER BY COALESCE(record_date,mill_date) DESC,id DESC LIMIT 5",
            (estate_id(),),
        )
        year = summary.get("record_year") or ("annata non disponibile" if italian else "year unavailable")
        lines = [f"• {_human_date(row.get('record_date') or row.get('mill_date'), italian)}: {row.get('activity') or ('attività' if italian else 'activity')} — {_number(row.get('olives_harvested_kg'), 0)} kg olive, {_number(row.get('oil_liters'))} L olio" if italian else f"• {_human_date(row.get('record_date') or row.get('mill_date'))}: {row.get('activity') or 'activity'} — {_number(row.get('olives_harvested_kg'), 0)} kg olives, {_number(row.get('oil_liters'))} L oil" for row in recent]
        if italian:
            return f"Olive {year}: {_number(summary.get('olives_kg'), 0)} kg raccolti, {_number(summary.get('oil_l'))} L olio, resa media {_number(summary.get('yield_pct'))}%.\n" + ("\n".join(lines) or "Nessun record olive disponibile.")
        return f"Olives {year}: {_number(summary.get('olives_kg'), 0)} kg harvested, {_number(summary.get('oil_l'))} L oil, {_number(summary.get('yield_pct'))}% average yield.\n" + ("\n".join(lines) or "No olive records available.")

    if route == "snapshot_cellar":
        lots = fetch_all(
            "SELECT w.code,w.name,w.stage,COALESCE(w.volume_l,w.initial_l,0) volume_l,c.code container_code "
            "FROM wine_lots w LEFT JOIN cellar_containers c ON c.id=w.current_container_id "
            "WHERE w.estate_id=%s AND w.lot_status='active' ORDER BY w.started_at DESC,w.code LIMIT 8",
            (estate_id(),),
        )
        latest_lab = (fetch_all(
            "SELECT sample_name,lab_date,needs_review FROM lab_samples WHERE estate_id=%s ORDER BY lab_date DESC,id DESC LIMIT 1",
            (estate_id(),),
        ) or [{}])[0]
        review_count = (fetch_all(
            "SELECT COUNT(*) total FROM lab_samples WHERE estate_id=%s AND needs_review=1",
            (estate_id(),),
        ) or [{}])[0].get("total") or 0
        lot_lines = [
            f"• {row.get('container_code') or 'No tank'}: {row.get('name') or row.get('code')} — {row.get('stage') or 'stage not recorded'}, {_number(row.get('volume_l'), 0)} L"
            for row in lots
        ]
        lab_name = latest_lab.get("sample_name") or ("nessun rapporto" if italian else "no report")
        lab_date = _human_date(latest_lab.get("lab_date"), italian) if latest_lab.get("lab_date") else ("data non disponibile" if italian else "date unavailable")
        if italian:
            return "Cantina live:\n" + ("\n".join(lot_lines) or "Nessun lotto attivo.") + f"\n\nUltimo laboratorio: {lab_name}, {lab_date}. Campioni da revisionare: {review_count}."
        return "Live cellar:\n" + ("\n".join(lot_lines) or "No active wine lots.") + f"\n\nLatest lab report: {lab_name}, {lab_date}. Samples awaiting review: {review_count}."

    if route == "snapshot_enology":
        cellar = live_snapshot("snapshot_cellar", italian, allowed_entities, administrator, allowed_cameras)
        observations = fetch_all(
            "SELECT COALESCE(c.code,f.vessel_name,'Tank') container_code,f.observed_at,f.temp_c,f.density_sg,f.brix,f.ph "
            "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id "
            "LEFT JOIN cellar_containers c ON c.id=w.current_container_id WHERE f.estate_id=%s ORDER BY f.observed_at DESC LIMIT 5",
            (estate_id(),),
        )
        bottling = fetch_all(
            "SELECT run_code,wine_name,bottled_at,bottles_produced,status,legal_review_status FROM bottling_runs "
            "WHERE estate_id=%s ORDER BY bottled_at DESC LIMIT 4",
            (estate_id(),),
        )
        sensor_lines = [f"• {row.get('container_code')}: {_number(row.get('temp_c'))}°C · SG {_number(row.get('density_sg'), 3)} · {_human_date(row.get('observed_at'), italian, include_time=True)}" for row in observations]
        bottle_lines = [f"• {row.get('run_code')}: {row.get('wine_name')} · {_number(row.get('bottles_produced'), 0)} bottiglie · {row.get('status')} / {row.get('legal_review_status')}" if italian else f"• {row.get('run_code')}: {row.get('wine_name')} · {_number(row.get('bottles_produced'), 0)} bottles · {row.get('status')} / {row.get('legal_review_status')}" for row in bottling]
        if italian:
            return cellar + "\n\nTank Sensor · ultime letture:\n" + ("\n".join(sensor_lines) or "Nessuna lettura disponibile.") + "\n\nImbottigliamento:\n" + ("\n".join(bottle_lines) or "Nessuna tiratura registrata.") + "\n\nOgni decisione di processo richiede conferma dell'enologo."
        return cellar + "\n\nTank Sensor · latest readings:\n" + ("\n".join(sensor_lines) or "No readings available.") + "\n\nBottling:\n" + ("\n".join(bottle_lines) or "No bottling runs recorded.") + "\n\nEvery process decision requires enologist confirmation."

    if route == "snapshot_cameras":
        cameras = [str(value).removeprefix("camera.").replace("_", " ") for value in (allowed_cameras or [])]
        listed = ", ".join(cameras[:12])
        events = fetch_all(
            "SELECT camera_name,event_type,detected_at,ended_at FROM camera_security_events WHERE estate_id=%s "
            "AND detected_at>=NOW()-INTERVAL 24 HOUR ORDER BY detected_at DESC LIMIT 5",
            (estate_id(),),
        )
        event_lines = [
            f"• {row.get('camera_name')}: {str(row.get('event_type') or 'activity').replace('_', ' ')} — {_human_date(row.get('detected_at'), italian, include_time=True)}"
            for row in events
        ]
        if italian:
            recent = "\n\nAttività recente:\n" + "\n".join(event_lines) if event_lines else "\n\nNessuna attività della telecamera registrata nelle ultime 24 ore."
            return ("Telecamere disponibili: " + listed + ".\n" if listed else "Nessuna telecamera è autorizzata nel menu.\n") + recent + "\n\nPer ricevere un'immagine, scrivi o pronuncia INVIA FOTO seguito dal nome della telecamera."
        recent = "\n\nRecent activity:\n" + "\n".join(event_lines) if event_lines else "\n\nNo camera activity was recorded in the last 24 hours."
        return ("Available cameras: " + listed + ".\n" if listed else "No cameras are authorized in this menu.\n") + recent + "\n\nTo receive an image, type or say SEND followed by the camera name and PHOTO."

    if route == "snapshot_cistern":
        level = latest_cistern_level()
        percent = float(level.get("level_percent") or 0)
        confidence = float(level.get("confidence") or 0)
        if confidence <= 1:
            confidence *= 100
        observed = _human_date(level.get("observed_at"), italian, include_time=True)
        action = percent < 10
        shadow = level.get("shadow_learning") or {}
        comparison = shadow.get("comparison") or {}
        learned = comparison.get("predicted_level_percent")
        shadow_note = (f" Il modello locale in prova stimava {float(learned):.1f}%; non controlla ancora gli avvisi." if learned is not None else "") if italian else (f" The local shadow model estimated {float(learned):.1f}%; it does not control alerts yet." if learned is not None else "")
        if italian:
            return f"Cisterna: {percent:.1f}% (stima da telecamera, confidenza {confidence:.0f}%). Aggiornata: {observed}." + shadow_note + " " + ("Azione richiesta: livello molto basso." if action else "Nessuna azione urgente per il livello.")
        return f"Cistern: {percent:.1f}% (camera estimate, {confidence:.0f}% confidence). Updated: {observed}." + shadow_note + " " + ("Action required: critically low level." if action else "No urgent level action required.")

    if route == "snapshot_presence":
        if not administrator:
            return "Le presenze sono disponibili solo agli amministratori." if italian else "Team presence is available only to administrators."
        people = home_assistant_manager_presence()
        lines = [f"• {row.get('name')}: {row.get('presence')} — {row.get('evidence')}; updated {_human_date(row.get('last_updated'), italian, include_time=True)}" for row in people]
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

    if route == "snapshot_hospitality":
        reservations = fetch_all(
            "SELECT r.start_at,r.status,r.guest_count,p.name package_name FROM hospitality_reservations r "
            "LEFT JOIN hospitality_packages p ON p.id=r.package_id WHERE r.estate_id=%s AND r.start_at>=NOW() "
            "AND r.status NOT IN ('cancelled','declined','no_show') ORDER BY r.start_at LIMIT 6",
            (estate_id(),),
        )
        inquiry = (fetch_all(
            "SELECT COUNT(*) total FROM hospitality_inquiries WHERE estate_id=%s AND status IN ('new','responded')",
            (estate_id(),),
        ) or [{}])[0]
        sales = (fetch_all(
            "SELECT COUNT(*) transactions,COALESCE(SUM(total_eur),0) gross_eur FROM register_sales WHERE estate_id=%s "
            "AND status='paid' AND completed_at>=DATE_FORMAT(CURDATE(),'%%Y-%%m-01')",
            (estate_id(),),
        ) or [{}])[0]
        lines = [f"• {_human_date(row.get('start_at'), italian, include_time=True)} · {row.get('package_name') or ('esperienza' if italian else 'experience')} · {row.get('guest_count')} ospiti · {row.get('status')}" if italian else f"• {_human_date(row.get('start_at'), include_time=True)} · {row.get('package_name') or 'experience'} · {row.get('guest_count')} guests · {row.get('status')}" for row in reservations]
        if italian:
            return f"Ospitalità: {len(reservations)} prossime prenotazioni mostrate; {int(inquiry.get('total') or 0)} richieste da seguire.\n" + ("\n".join(lines) or "Nessuna prenotazione futura attiva.") + f"\n\nRegistro vendite del mese: {int(sales.get('transactions') or 0)} vendite pagate, €{_number(sales.get('gross_eur'), 2)} lordi. Nessun contatto ospite è incluso in WhatsApp."
        return f"Hospitality: {len(reservations)} upcoming reservations shown; {int(inquiry.get('total') or 0)} inquiries need follow-up.\n" + ("\n".join(lines) or "No active future reservations.") + f"\n\nThis month's sales register: {int(sales.get('transactions') or 0)} paid sales, €{_number(sales.get('gross_eur'), 2)} gross. No guest contact details are included in WhatsApp."

    if route == "snapshot_estate_systems":
        cistern = live_snapshot("snapshot_cistern", italian, allowed_entities, administrator, allowed_cameras)
        power = live_snapshot("snapshot_power", italian, allowed_entities, administrator, allowed_cameras)
        traffic = live_snapshot("snapshot_traffic", italian, allowed_entities, administrator, allowed_cameras)
        camera_events = (fetch_all(
            "SELECT COUNT(*) total FROM camera_security_events WHERE estate_id=%s AND detected_at>=NOW()-INTERVAL 24 HOUR",
            (estate_id(),),
        ) or [{}])[0]
        camera_line = f"Telecamere autorizzate: {len(allowed_cameras or [])}; eventi nelle ultime 24 ore: {int(camera_events.get('total') or 0)}. Scrivi INVIA FOTO [nome] per un'immagine corrente." if italian else f"Authorized cameras: {len(allowed_cameras or [])}; events in the last 24 hours: {int(camera_events.get('total') or 0)}. Send SEND [name] PHOTO for a current image."
        heading = "SISTEMI TENUTA" if italian else "ESTATE SYSTEMS"
        return f"{heading}\n{cistern}\n\n{camera_line}\n\n{power}\n\n{traffic}"

    if route == "snapshot_admin":
        if not administrator:
            return "Team e finanza sono disponibili solo agli amministratori." if italian else "Team and finance are available only to administrators."
        presence = live_snapshot("snapshot_presence", italian, allowed_entities, administrator, allowed_cameras)
        documents = (fetch_all(
            "SELECT COUNT(*) total,COALESCE(SUM(taxable_amount+vat_amount),0) amount_eur FROM financial_documents "
            "WHERE estate_id=%s AND payment_status IN ('unpaid','part_paid','unknown') AND status NOT IN ('void','draft')",
            (estate_id(),),
        ) or [{}])[0]
        cash = (fetch_all(
            "SELECT COALESCE(SUM(amount_in),0) amount_in,COALESCE(SUM(amount_out),0) amount_out,SUM(reconciliation_status IN ('unmatched','part_matched','review')) review_count "
            "FROM cash_transactions WHERE estate_id=%s AND transaction_date>=DATE_FORMAT(CURDATE(),'%%Y-%%m-01')",
            (estate_id(),),
        ) or [{}])[0]
        commissions = (fetch_all(
            "SELECT COUNT(*) total,COALESCE(SUM(commission_amount_eur),0) amount_eur FROM hospitality_partner_commissions "
            "WHERE estate_id=%s AND status IN ('due','approved','partially_paid')",
            (estate_id(),),
        ) or [{}])[0]
        if italian:
            return presence + f"\n\nFinanza · revisione: {int(documents.get('total') or 0)} documenti aperti (€{_number(documents.get('amount_eur'), 2)} lordi registrati). Flussi del mese: €{_number(cash.get('amount_in'), 2)} entrate, €{_number(cash.get('amount_out'), 2)} uscite; {int(cash.get('review_count') or 0)} movimenti da riconciliare. Commissioni partner aperte: {int(commissions.get('total') or 0)} (€{_number(commissions.get('amount_eur'), 2)}). Valori informativi: verificare in Finanza prima di agire."
        return presence + f"\n\nFinance review: {int(documents.get('total') or 0)} open documents (€{_number(documents.get('amount_eur'), 2)} recorded gross). This month's flows: €{_number(cash.get('amount_in'), 2)} in, €{_number(cash.get('amount_out'), 2)} out; {int(cash.get('review_count') or 0)} movements need reconciliation. Open partner commissions: {int(commissions.get('total') or 0)} (€{_number(commissions.get('amount_eur'), 2)}). Informational values: verify in Finance before acting."

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
        "Answer briefly, warmly, and conversationally. Preserve the live quantities, but express dates and times as natural spoken phrases in Europe/Rome time. "
        "Never expose ISO dates, database timestamps, underscored status codes, or machine-style field labels. "
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
