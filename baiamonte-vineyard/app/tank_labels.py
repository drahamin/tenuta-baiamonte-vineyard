from __future__ import annotations

from datetime import date
from typing import Any

from .db import fetch_all, fetch_one, transaction
from .service import estate_id, json_ready, new_id


DENOMINATION_CLASSES = (
    "Vino",
    "IGP Terre Siciliane",
    "Sicilia DOC",
    "Etna DOC",
    "Other / Altro",
)
WINE_TYPES = ("Rosso", "Bianco", "Rosato", "Mosto", "Base vino", "Blend", "Altro")
WINE_COLORS = ("red", "white", "rose")
CELLAR_STAGES = (
    "empty", "receiving", "must", "fermentation", "maceration", "pressing", "malo",
    "settling", "transfer", "aging", "resting", "clarification", "stabilization",
    "bottling", "bottled", "storage", "closed",
)
WINE_LOT_STAGES = {"must", "fermentation", "malo", "aging", "bottled", "closed"}
PROCESSING_PHASES = (
    "Harvest reception", "Crushing / Destemming", "Maceration", "Alcoholic fermentation",
    "Pressing", "Malolactic fermentation", "Racking", "Settling", "Clarification",
    "Stabilization", "Aging", "Blending", "Bottling", "Storage", "Other / Altro",
)
LEGAL_PROFILE_DEFAULTS = {
    "legal_company_name": "Azienda Agricola Tenuta Baiamonte",
    "vat_number": "07276090482",
    "pec": "tenutabaiamonte@pec.it",
    "telephone": "+39 3397732042",
    "cantiniere": "Sebastiano Vinci",
}

_PHASE_BY_STAGE = {
    "receiving": "Harvest reception", "must": "Crushing / Destemming",
    "fermentation": "Alcoholic fermentation", "fermenting": "Alcoholic fermentation",
    "maceration": "Maceration", "pressing": "Pressing", "malo": "Malolactic fermentation",
    "settling": "Settling", "transfer": "Racking", "aging": "Aging",
    "clarification": "Clarification", "stabilization": "Stabilization",
    "bottling": "Bottling", "bottled": "Bottling", "storage": "Storage",
}


def processing_phase_for(stage: Any) -> str | None:
    return _PHASE_BY_STAGE.get(str(stage or "").casefold())


def ensure_tank_label(cursor: Any, container_id: str) -> None:
    cursor.execute(
        "INSERT IGNORE INTO cellar_tank_labels (id,estate_id,container_id,public_token,active) "
        "VALUES (%s,%s,%s,%s,1)",
        (new_id(), estate_id(), container_id, new_id()),
    )


def tank_label_rows(year: int, active: bool = True) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT c.id container_id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.location,c.status,"
        "tl.public_token,tl.active label_active,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,"
        "w.stage,w.volume_l,w.variety_summary,s.vintage_year,lp.wine_type,COALESCE(lp.wine_color,cp.wine_color) wine_color,lp.origin_country,"
        "lp.legal_company_name,lp.vat_number,lp.pec,lp.telephone,lp.cantiniere,"
        "lp.denomination_class,lp.denomination,lp.content_description,lp.processing_phase,"
        "lp.racking_history,lp.legal_notes,lp.confirmed_by,lp.confirmed_at,lp.updated_at legal_updated_at,"
        "(SELECT fo.next_check_at FROM fermentation_observations fo WHERE fo.estate_id=c.estate_id AND (fo.wine_lot_id=w.id OR fo.vessel_name=c.name) AND fo.next_check_at IS NOT NULL ORDER BY fo.observed_at DESC LIMIT 1) next_check_at "
        "FROM cellar_containers c "
        "JOIN cellar_tank_labels tl ON tl.container_id=c.id AND tl.estate_id=c.estate_id "
        "LEFT JOIN wine_lots w ON w.id=COALESCE("
        "(SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.estate_id=c.estate_id ORDER BY wx.started_at DESC LIMIT 1),"
        "(SELECT tr.wine_lot_id FROM cellar_lot_trace_records tr WHERE tr.container_id=c.id AND tr.estate_id=c.estate_id ORDER BY tr.transferred_at DESC LIMIT 1)) "
        "LEFT JOIN seasons s ON s.id=w.season_id "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "LEFT JOIN wine_lot_legal_profiles lp ON lp.wine_lot_id=w.id AND lp.estate_id=c.estate_id "
        "WHERE c.estate_id=%s AND c.active=%s AND tl.active=%s "
        "ORDER BY c.code,w.started_at DESC",
        (estate_id(), 1 if active else 0, 1 if active else 0),
    )
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        if row["container_id"] in seen:
            continue
        seen.add(row["container_id"])
        row["vintage_year"] = row.get("vintage_year") or year
        row["origin_country"] = row.get("origin_country") or "Italia"
        for key, value in LEGAL_PROFILE_DEFAULTS.items():
            row[key] = row.get(key) or value
        row["content_description"] = row.get("content_description") or row.get("variety_summary") or row.get("wine_lot_name")
        row["processing_phase"] = row.get("processing_phase") or processing_phase_for(row.get("stage"))
        row["capacity_hl"] = round(float(row.get("capacity_l") or 0) / 100, 2)
        row["label_url"] = f"/tank/{row['public_token']}"
        result.append(row)
    return json_ready(result)


def save_legal_profile(container_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    tank = fetch_one(
        "SELECT c.id,w.id wine_lot_id,s.vintage_year,w.variety_summary,w.stage "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.estate_id=c.estate_id "
        "LEFT JOIN seasons s ON s.id=w.season_id WHERE c.id=%s AND c.estate_id=%s AND c.active=1 "
        "ORDER BY w.started_at DESC LIMIT 1",
        (container_id, estate_id()),
    )
    if not tank:
        raise ValueError("Tank not found")
    wine_lot_id = str(payload.get("wine_lot_id") or tank.get("wine_lot_id") or "").strip()
    if not wine_lot_id:
        raise ValueError("Assign a cellar wine lot before saving legal wine data")
    lot = fetch_one("SELECT id FROM wine_lots WHERE id=%s AND estate_id=%s", (wine_lot_id, estate_id()))
    if not lot:
        raise ValueError("Wine lot not found")
    wine_type = str(payload.get("wine_type") or "").strip() or None
    wine_color = str(payload.get("wine_color") or "").strip().casefold() or None
    denomination_class = str(payload.get("denomination_class") or "").strip() or None
    if wine_type and wine_type not in WINE_TYPES:
        raise ValueError("Choose a supported wine type")
    if wine_color and wine_color not in WINE_COLORS:
        raise ValueError("Choose red, white or rosé")
    if denomination_class and denomination_class not in DENOMINATION_CLASSES:
        raise ValueError("Choose a supported denomination class")
    vintage = int(payload.get("vintage_year") or tank.get("vintage_year") or date.today().year)
    if vintage < 1900 or vintage > date.today().year + 1:
        raise ValueError("Enter a valid vintage")
    processing_phase = str(payload.get("processing_phase") or processing_phase_for(tank.get("stage")) or "").strip() or None
    if processing_phase and processing_phase not in PROCESSING_PHASES:
        raise ValueError("Choose a supported processing phase")
    values = {
        **{key: str(payload.get(key) or value).strip() or value for key, value in LEGAL_PROFILE_DEFAULTS.items()},
        "wine_type": wine_type,
        "wine_color": wine_color,
        "vintage_year": vintage,
        "origin_country": str(payload.get("origin_country") or "Italia").strip() or "Italia",
        "denomination_class": denomination_class,
        "denomination": str(payload.get("denomination") or "").strip() or None,
        "content_description": str(payload.get("content_description") or tank.get("variety_summary") or "").strip() or None,
        "processing_phase": processing_phase,
        "racking_history": str(payload.get("racking_history") or "").strip() or None,
        "legal_notes": str(payload.get("legal_notes") or "").strip() or None,
    }
    with transaction() as (_, cursor):
        ensure_tank_label(cursor, container_id)
        cursor.execute(
            "INSERT INTO wine_lot_legal_profiles "
            "(id,estate_id,wine_lot_id,legal_company_name,vat_number,pec,telephone,cantiniere,wine_type,wine_color,vintage_year,origin_country,denomination_class,denomination,content_description,processing_phase,racking_history,legal_notes,confirmed_by,confirmed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6)) "
            "ON DUPLICATE KEY UPDATE wine_type=VALUES(wine_type),wine_color=VALUES(wine_color),vintage_year=VALUES(vintage_year),origin_country=VALUES(origin_country),"
            "legal_company_name=VALUES(legal_company_name),vat_number=VALUES(vat_number),pec=VALUES(pec),telephone=VALUES(telephone),cantiniere=VALUES(cantiniere),"
            "denomination_class=VALUES(denomination_class),denomination=VALUES(denomination),content_description=VALUES(content_description),"
            "processing_phase=VALUES(processing_phase),racking_history=VALUES(racking_history),legal_notes=VALUES(legal_notes),"
            "confirmed_by=VALUES(confirmed_by),confirmed_at=VALUES(confirmed_at)",
            (new_id(), estate_id(), wine_lot_id, values["legal_company_name"], values["vat_number"], values["pec"], values["telephone"], values["cantiniere"], values["wine_type"], values["wine_color"], vintage, values["origin_country"], values["denomination_class"], values["denomination"], values["content_description"], values["processing_phase"], values["racking_history"], values["legal_notes"], actor),
        )
    return {"saved": True, "container_id": container_id, "wine_lot_id": wine_lot_id}


def tank_label_payload(token: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT c.id container_id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.location,c.status,c.active,c.sensor_entity_id,"
        "tl.active label_active,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,w.stage,w.volume_l,w.variety_summary,"
        "s.vintage_year,COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status,cp.manual_temp_c temp_c,cp.manual_density_sg density_sg,"
        "cp.manual_brix brix,cp.manual_ph ph,cp.manual_reading_at reading_at,lp.wine_type,COALESCE(lp.wine_color,cp.wine_color) wine_color,COALESCE(lp.origin_country,'Italia') origin_country,"
        "lp.legal_company_name,lp.vat_number,lp.pec,lp.telephone,lp.cantiniere,"
        "lp.denomination_class,lp.denomination,lp.content_description,lp.processing_phase,lp.racking_history,lp.legal_notes,"
        "(SELECT fo.next_check_at FROM fermentation_observations fo WHERE fo.estate_id=c.estate_id AND (fo.wine_lot_id=w.id OR fo.vessel_name=c.name) AND fo.next_check_at IS NOT NULL ORDER BY fo.observed_at DESC LIMIT 1) next_check_at,"
        "lp.confirmed_by,lp.confirmed_at,lp.updated_at legal_updated_at "
        "FROM cellar_tank_labels tl JOIN cellar_containers c ON c.id=tl.container_id AND c.estate_id=tl.estate_id "
        "LEFT JOIN wine_lots w ON w.current_container_id=c.id AND w.estate_id=c.estate_id "
        "LEFT JOIN seasons s ON s.id=w.season_id LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id "
        "LEFT JOIN wine_lot_legal_profiles lp ON lp.wine_lot_id=w.id "
        "WHERE tl.public_token=%s AND tl.estate_id=%s ORDER BY w.started_at DESC LIMIT 1",
        (token, estate_id()),
    )
    if not row:
        return None
    row["available"] = bool(row.get("active") and row.get("label_active"))
    row["capacity_hl"] = round(float(row.get("capacity_l") or 0) / 100, 2)
    row["level_pct"] = round(float(row.get("volume_l") or 0) / float(row["capacity_l"]) * 100, 1) if row.get("capacity_l") else None
    row["content_description"] = row.get("content_description") or row.get("variety_summary") or row.get("wine_lot_name")
    row["processing_phase"] = row.get("processing_phase") or processing_phase_for(row.get("stage"))
    for key, value in LEGAL_PROFILE_DEFAULTS.items():
        row[key] = row.get(key) or value
    row["wine_type"] = row.get("wine_type") or "—"
    row["denomination_display"] = " · ".join(value for value in (row.get("denomination_class"), row.get("denomination")) if value) or "—"
    row["transfers"] = fetch_all(
        "SELECT transferred_at,notes FROM cellar_lot_trace_records WHERE estate_id=%s AND wine_lot_id=%s ORDER BY transferred_at DESC LIMIT 8",
        (estate_id(), row.get("wine_lot_id")),
    ) if row.get("wine_lot_id") else []
    return json_ready(row)


def kiosk_rows(active: bool = True) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT k.id,k.name,k.public_token,k.container_id,k.active,k.notes,k.last_seen_at,k.created_at,k.updated_at,"
        "c.code tank_code,c.name tank_name,c.active tank_active,tl.public_token tank_token "
        "FROM cellar_label_kiosks k LEFT JOIN cellar_containers c ON c.id=k.container_id AND c.estate_id=k.estate_id "
        "LEFT JOIN cellar_tank_labels tl ON tl.container_id=c.id AND tl.estate_id=c.estate_id "
        "WHERE k.estate_id=%s AND k.active=%s ORDER BY k.name",
        (estate_id(), 1 if active else 0),
    )
    for row in rows:
        row["kiosk_url"] = f"/kiosk/{row['public_token']}"
    return json_ready(rows)


def create_kiosk(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Enter a tablet name")
    container_id = str(payload.get("container_id") or "").strip() or None
    if container_id and not fetch_one(
        "SELECT id FROM cellar_containers WHERE id=%s AND estate_id=%s AND active=1",
        (container_id, estate_id()),
    ):
        raise ValueError("Choose an active tank")
    kiosk_id, token = new_id(), new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cellar_label_kiosks (id,estate_id,name,public_token,container_id,notes) VALUES (%s,%s,%s,%s,%s,%s)",
            (kiosk_id, estate_id(), name, token, container_id, str(payload.get("notes") or "").strip() or None),
        )
    return {"created": True, "id": kiosk_id, "public_token": token, "kiosk_url": f"/kiosk/{token}"}


def update_kiosk(kiosk_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = fetch_one("SELECT * FROM cellar_label_kiosks WHERE id=%s AND estate_id=%s AND active=1", (kiosk_id, estate_id()))
    if not current:
        raise ValueError("Tablet not found")
    name = str(payload.get("name") or current.get("name") or "").strip()
    container_id = str(payload.get("container_id") or "").strip() or None
    if container_id and not fetch_one(
        "SELECT id FROM cellar_containers WHERE id=%s AND estate_id=%s AND active=1",
        (container_id, estate_id()),
    ):
        raise ValueError("Choose an active tank")
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_label_kiosks SET name=%s,container_id=%s,notes=%s WHERE id=%s AND estate_id=%s",
            (name, container_id, str(payload.get("notes") or "").strip() or None, kiosk_id, estate_id()),
        )
    return {"saved": True, "id": kiosk_id}


def retire_kiosk(kiosk_id: str) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_label_kiosks SET active=0,container_id=NULL WHERE id=%s AND estate_id=%s AND active=1",
            (kiosk_id, estate_id()),
        )
        if cursor.rowcount != 1:
            raise ValueError("Tablet not found")
    return {"retired": True, "id": kiosk_id}


def kiosk_payload(token: str) -> dict[str, Any] | None:
    kiosk = fetch_one(
        "SELECT id,name,container_id,active,notes FROM cellar_label_kiosks WHERE public_token=%s AND estate_id=%s",
        (token, estate_id()),
    )
    if not kiosk:
        return None
    if not kiosk.get("active") or not kiosk.get("container_id"):
        return json_ready({"kiosk": kiosk, "available": False})
    label = fetch_one(
        "SELECT public_token FROM cellar_tank_labels WHERE container_id=%s AND estate_id=%s",
        (kiosk["container_id"], estate_id()),
    )
    data = tank_label_payload(label["public_token"]) if label else None
    with transaction() as (_, cursor):
        cursor.execute("UPDATE cellar_label_kiosks SET last_seen_at=NOW(6) WHERE id=%s", (kiosk["id"],))
    return json_ready({"kiosk": kiosk, "available": bool(data and data.get("available")), "tank": data})
