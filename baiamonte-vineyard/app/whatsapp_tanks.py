"""Deterministic, audited WhatsApp commands for cellar tank readings."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .db import fetch_all, fetch_one, transaction
from .service import audit, estate_id, new_id


_LIST_COMMANDS = {
    "list tanks", "tanks", "tank list", "show tanks", "cellar tanks",
    "elenca vasche", "lista vasche", "vasche", "mostra vasche", "serbatoi", "lista serbatoi",
}
_UPDATE = re.compile(
    r"^\s*(?:update|set|record|log|aggiorna|imposta|registra)\s+"
    r"(?:(?:tank|vasca|serbatoio)\s+)?([a-z0-9][a-z0-9_-]{0,59})\b(.*)$",
    re.I,
)
_HISTORY = re.compile(
    r"^\s*(?:history|storico|letture)\s+(?:(?:tank|vasca|serbatoio)\s+)?"
    r"([a-z0-9][a-z0-9_-]{0,59})(?:\s+(?:last|ultimi|ultime)?\s*(\d{1,2})\s*(?:days?|giorni))?\s*$",
    re.I,
)
_QUICK_HISTORY = re.compile(
    r"^\s*(?:(?:last|recent|latest|ultim[ei])(?:\s+(?:readings?|letture))?\s+)?"
    r"(?:(?:tank|vasca|serbatoio)\s+)?([a-z][a-z0-9]*-\d+)\s+"
    r"(?:last|recent|latest|history|storico|ultim[ei])\s*$|"
    r"^\s*(?:last|recent|latest|ultim[ei])(?:\s+(?:readings?|letture))?\s+"
    r"(?:(?:tank|vasca|serbatoio)\s+)?([a-z][a-z0-9]*-\d+)\s*$",
    re.I,
)
_QUICK_UPDATE = re.compile(
    r"^\s*(?:(?:tank|vasca|serbatoio)\s+)?([a-z][a-z0-9]*-\d+)\s+"
    r"(-?\d+(?:[.,]\d+)?)\s+(-?\d+(?:[.,]\d+)?)"
    r"(?:\s+(-?\d+(?:[.,]\d+)?)(?:\s*(?:l|litri|liters?))?)?\s*$",
    re.I,
)


def _number(text: str, labels: str) -> float | None:
    match = re.search(rf"(?:^|\s)(?:{labels})\s*(?:=|:)?\s*(-?\d+(?:[.,]\d+)?)\b", text, re.I)
    return float(match.group(1).replace(",", ".")) if match else None


def parse_tank_command(text: str) -> dict[str, Any] | None:
    """Parse only explicit list/update commands; never infer unlabeled readings."""
    normalized = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    if normalized in _LIST_COMMANDS:
        return {"action": "list"}
    history = _HISTORY.fullmatch(str(text or ""))
    if history:
        return {"action": "history", "tank_code": history.group(1).upper(), "days": int(history.group(2) or 3)}
    quick_history = _QUICK_HISTORY.fullmatch(str(text or ""))
    if quick_history:
        return {"action": "history", "tank_code": (quick_history.group(1) or quick_history.group(2)).upper(), "days": 3}
    quick = _QUICK_UPDATE.fullmatch(str(text or ""))
    if quick:
        number = lambda value: float(value.replace(",", ".")) if value is not None else None
        return {
            "action": "update", "tank_code": quick.group(1).upper(),
            "babo": number(quick.group(2)), "temp_c": number(quick.group(3)),
            "volume_l": number(quick.group(4)),
        }
    match = _UPDATE.fullmatch(str(text or ""))
    if not match:
        return None
    remainder = match.group(2)
    result = {
        "action": "update",
        "tank_code": match.group(1).upper(),
        "babo": _number(remainder, r"babo|babbo|°\s*babo"),
        "temp_c": _number(remainder, r"temp(?:erature|eratura)?|temperatura"),
        "volume_l": _number(remainder, r"volume|vol(?:ume)?"),
    }
    if all(result[key] is None for key in ("babo", "temp_c", "volume_l")):
        return {**result, "error": "missing_reading"}
    return result


def list_tanks(italian: bool = False) -> str:
    rows = fetch_all(
        "SELECT c.code,c.name,c.capacity_l,cp.reading_mode,"
        "COALESCE(w.volume_l,cp.manual_volume_l) volume_l,"
        "COALESCE((SELECT f.babo FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_babo) babo,"
        "COALESCE((SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_temp_c) temp_c,"
        "COALESCE((SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_reading_at) reading_at,"
        "w.code lot_code FROM cellar_containers c "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "LEFT JOIN wine_lots w ON w.id=(SELECT wx.id FROM wine_lots wx WHERE wx.estate_id=c.estate_id "
        "AND wx.current_container_id=c.id AND wx.lot_status='active' ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1) "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (estate_id(),),
    )
    lines = []
    for row in rows:
        readings = []
        if row.get("volume_l") is not None:
            readings.append(f"{float(row['volume_l']):g}/{float(row.get('capacity_l') or 0):g} L")
        if row.get("babo") is not None:
            readings.append(f"Babo {float(row['babo']):g}°")
        if row.get("temp_c") is not None:
            readings.append(f"{float(row['temp_c']):g}°C")
        details = " · ".join(readings) or ("nessuna lettura" if italian else "no reading")
        lot = row.get("lot_code") or ("nessun lotto" if italian else "no lot")
        lines.append(f"• {row['code']} — {row.get('name') or row['code']} · {lot} · {details} · {row.get('reading_mode') or 'manual'}")
    heading = "Vasche attive:" if italian else "Active tanks:"
    help_text = (
        "Aggiorna con: AGGIORNA T-06 BABO 16,9 TEMP 18,4 VOLUME 1069,8 L"
        if italian else "Update with: UPDATE T-06 BABO 16.9 TEMP 18.4 VOLUME 1069.8 L"
    )
    return heading + "\n" + ("\n".join(lines) or ("Nessuna vasca configurata." if italian else "No tanks configured.")) + "\n\n" + help_text


def tank_history(code: str, days: int = 3, italian: bool = False) -> str:
    code = str(code or "").strip().upper()
    days = int(days)
    if not 1 <= days <= 14:
        raise ValueError("History window must be between 1 and 14 days.")
    tank = fetch_one(
        "SELECT id,code,name FROM cellar_containers WHERE estate_id=%s AND active=1 AND UPPER(code)=%s",
        (estate_id(), code),
    )
    if not tank:
        raise ValueError(f"Tank {code} was not found. Send LIST TANKS for exact codes.")
    rows = fetch_all(
        "SELECT f.observed_at,f.babo,f.temp_c,f.status FROM fermentation_observations f "
        "LEFT JOIN wine_lots w ON w.id=f.wine_lot_id AND w.estate_id=f.estate_id "
        "WHERE f.estate_id=%s AND f.observed_at>=DATE_SUB(NOW(),INTERVAL %s DAY) "
        "AND (w.current_container_id=%s OR LOWER(f.vessel_name) IN (LOWER(%s),LOWER(%s))) "
        "AND (f.babo IS NOT NULL OR f.temp_c IS NOT NULL) ORDER BY f.observed_at DESC LIMIT 50",
        (estate_id(), days, tank["id"], tank.get("code"), tank.get("name")),
    )
    lines = []
    for row in rows:
        observed = row.get("observed_at")
        stamp = observed.strftime("%d/%m %H:%M") if hasattr(observed, "strftime") else str(observed)[:16]
        values = []
        if row.get("babo") is not None:
            values.append(f"Babo {float(row['babo']):g}°")
        if row.get("temp_c") is not None:
            values.append(f"{float(row['temp_c']):g}°C")
        lines.append(f"• {stamp} · {' · '.join(values)}")
    heading = f"{code} · ultimi {days} giorni:" if italian else f"{code} · last {days} days:"
    empty = "Nessuna lettura Babo o temperatura nel periodo." if italian else "No Babo or temperature readings in this period."
    return heading + "\n" + ("\n".join(lines) or empty)


def latest_tank_readings(code: str, italian: bool = False, limit: int = 3) -> str:
    """Return a compact post-save receipt showing the latest recorded readings."""
    code = str(code or "").strip().upper()
    tank = fetch_one(
        "SELECT id,code,name FROM cellar_containers WHERE estate_id=%s AND active=1 AND UPPER(code)=%s",
        (estate_id(), code),
    )
    if not tank:
        return ""
    rows = fetch_all(
        "SELECT f.observed_at,f.babo,f.temp_c FROM fermentation_observations f "
        "LEFT JOIN wine_lots w ON w.id=f.wine_lot_id AND w.estate_id=f.estate_id "
        "WHERE f.estate_id=%s AND (w.current_container_id=%s OR LOWER(f.vessel_name) IN (LOWER(%s),LOWER(%s))) "
        "AND (f.babo IS NOT NULL OR f.temp_c IS NOT NULL) ORDER BY f.observed_at DESC LIMIT %s",
        (estate_id(), tank["id"], tank.get("code"), tank.get("name"), max(1, min(int(limit), 5))),
    )
    lines = []
    for row in rows:
        observed = row.get("observed_at")
        stamp = observed.strftime("%d/%m %H:%M") if hasattr(observed, "strftime") else str(observed)[:16]
        values = []
        if row.get("babo") is not None:
            values.append(f"Babo {float(row['babo']):g}°")
        if row.get("temp_c") is not None:
            values.append(f"{float(row['temp_c']):g}°C")
        lines.append(f"• {stamp} · {' · '.join(values)}")
    heading = "Ultime letture:" if italian else "Latest readings:"
    return heading + "\n" + ("\n".join(lines) or ("Nessuna lettura precedente." if italian else "No previous readings."))


def save_tank_update(command: dict[str, Any], actor: str) -> dict[str, Any]:
    code = str(command.get("tank_code") or "").upper()
    tank = fetch_one(
        "SELECT c.*,COALESCE(cp.reading_mode,'manual') reading_mode,cp.sensor_status FROM cellar_containers c "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.estate_id=%s AND c.active=1 AND UPPER(c.code)=%s",
        (estate_id(), code),
    )
    if not tank:
        raise ValueError(f"Tank {code} was not found. Send LIST TANKS for exact codes.")
    if tank.get("reading_mode") in {"sensor", "auto"}:
        raise ValueError(f"Tank {code} is in automatic sensor mode; change it to manual before a WhatsApp reading.")
    lot = fetch_one(
        "SELECT id,code,stage,variety_summary FROM wine_lots WHERE estate_id=%s AND current_container_id=%s "
        "AND lot_status='active' ORDER BY started_at DESC,id DESC LIMIT 1",
        (estate_id(), tank["id"]),
    )
    babo, temp, volume = command.get("babo"), command.get("temp_c"), command.get("volume_l")
    if babo is not None and not 0 <= float(babo) <= 40:
        raise ValueError("Babo must be between 0 and 40 °Babo.")
    if temp is not None and not -20 <= float(temp) <= 60:
        raise ValueError("Temperature must be between -20 and 60 °C.")
    maximum = max(float(tank.get("capacity_l") or 100000) * 1.05, 1)
    if volume is not None and not 0 <= float(volume) <= maximum:
        raise ValueError(f"Volume must be between 0 and {maximum:g} L for tank {code}.")
    observed = datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    reading_id = new_id()
    with transaction() as (_, cursor):
        if lot and volume is not None:
            cursor.execute("UPDATE wine_lots SET volume_l=%s WHERE id=%s AND estate_id=%s", (volume, lot["id"], estate_id()))
        if volume is not None:
            cursor.execute("UPDATE cellar_containers SET status=%s WHERE id=%s AND estate_id=%s", ("empty" if float(volume) == 0 else "in_use", tank["id"], estate_id()))
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_temp_c,manual_babo,manual_reading_at,manual_updated_at,updated_by) "
            "VALUES (%s,%s,%s,'manual',%s,%s,%s,%s,%s,%s,%s,NOW(6),%s) "
            "ON DUPLICATE KEY UPDATE manual_contents=COALESCE(VALUES(manual_contents),manual_contents),manual_volume_l=COALESCE(VALUES(manual_volume_l),manual_volume_l),"
            "manual_stage=COALESCE(VALUES(manual_stage),manual_stage),manual_temp_c=COALESCE(VALUES(manual_temp_c),manual_temp_c),manual_babo=COALESCE(VALUES(manual_babo),manual_babo),"
            "manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), tank["id"], tank.get("sensor_status") or "not_configured", (lot or {}).get("variety_summary"), volume, (lot or {}).get("stage"), temp, babo, observed, actor),
        )
        cursor.execute(
            "INSERT INTO fermentation_observations (id,estate_id,wine_lot_id,observed_at,vessel_name,stage,temp_c,babo,owner_text,status,sensory_observation) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'whatsapp','Structured WhatsApp tank reading')",
            (reading_id, estate_id(), (lot or {}).get("id"), observed, tank.get("name") or code, (lot or {}).get("stage"), temp, babo, actor),
        )
        details = {"source": "whatsapp", "reading_id": reading_id, "tank_code": code, "wine_lot_id": (lot or {}).get("id"), "babo": babo, "temp_c": temp, "volume_l": volume}
        audit(cursor, "whatsapp_tank_reading", "cellar_container", tank["id"], details, actor)
        cursor.execute(
            "INSERT INTO integration_events (estate_id,integration_name,direction,event_type,external_id,status,payload) "
            "VALUES (%s,'enology-prediction-refresh','inbound','tank_reading_changed',%s,'received',%s)",
            (estate_id(), reading_id, json.dumps(details)),
        )
    return {"reading_id": reading_id, "tank_code": code, "tank_name": tank.get("name") or code, "lot_code": (lot or {}).get("code"), "babo": babo, "temp_c": temp, "volume_l": volume, "observed_at": observed}
