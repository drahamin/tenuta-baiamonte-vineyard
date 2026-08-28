from __future__ import annotations

from datetime import date
import hashlib
import re
import secrets
from typing import Any

from .config import get_settings
from .db import fetch_all, fetch_one, transaction
from .domains.plaato import apply_plaato_readings, fetch_plaato_snapshot
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
    "legal_company_name": "Azienda Agricola Tenuta Baiamonte S.S.",
    "vat_number": "07276090482",
    "pec": "tenutabaiamonte@pec.it",
    "telephone": "+39 3397732042",
    "cantiniere": "Sebastiano Vinci",
}
CANTINIERE_TELEPHONE = "+39 340 9695752"

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


def legal_parcels_for_tank(container_id: str, wine_lot_id: str | None) -> list[dict[str, Any]]:
    """Return deduplicated cadastral provenance for the wine currently represented by a tank label."""
    if not wine_lot_id:
        return []
    rows = fetch_all(
        "SELECT DISTINCT p.id,p.municipality,p.cadastral_sheet,p.parcel_number,p.tenure,p.contract_protocol,"
        "p.cadastral_area_ha,p.conducted_area_ha,p.official_vineyard_area_ha "
        "FROM cellar_lot_trace_records tr "
        "JOIN harvest_lot_parcels hp ON hp.harvest_lot_id=tr.harvest_lot_id AND hp.estate_id=tr.estate_id "
        "JOIN cadastral_parcels p ON p.id=hp.parcel_id AND p.estate_id=tr.estate_id "
        "WHERE tr.estate_id=%s AND tr.container_id=%s AND tr.wine_lot_id=%s "
        "ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number",
        (estate_id(), container_id, wine_lot_id),
    )
    for parcel in rows:
        parcel["legal_reference"] = (
            f"{parcel.get('municipality') or '—'} · Foglio {parcel.get('cadastral_sheet') or '—'} "
            f"· Particella {parcel.get('parcel_number') or '—'}"
        )
        parcel["vineyard_area_ha"] = (
            parcel.get("official_vineyard_area_ha")
            or parcel.get("conducted_area_ha")
            or parcel.get("cadastral_area_ha")
        )
    return json_ready(rows)


def tank_label_rows(year: int, active: bool = True) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT c.id container_id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.location,c.status,"
        "tl.public_token,tl.active label_active,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,"
        "COALESCE(w.stage,cp.manual_stage) stage,COALESCE(w.volume_l,cp.manual_volume_l) volume_l,"
        "COALESCE(w.variety_summary,cp.manual_contents) variety_summary,s.vintage_year,lp.wine_type,COALESCE(lp.wine_color,cp.wine_color) wine_color,lp.origin_country,"
        "lp.legal_company_name,lp.vat_number,lp.pec,lp.telephone,lp.cantiniere,"
        "lp.denomination_class,lp.denomination,lp.content_description,lp.processing_phase,"
        "lp.racking_history,lp.legal_notes,lp.confirmed_by,lp.confirmed_at,lp.updated_at legal_updated_at,"
        "(SELECT fo.next_check_at FROM fermentation_observations fo WHERE fo.estate_id=c.estate_id AND (fo.wine_lot_id=w.id OR fo.vessel_name=c.name) AND fo.next_check_at IS NOT NULL ORDER BY fo.observed_at DESC LIMIT 1) next_check_at "
        "FROM cellar_containers c "
        "JOIN cellar_tank_labels tl ON tl.container_id=c.id AND tl.estate_id=c.estate_id "
        "LEFT JOIN wine_lots w ON w.id=COALESCE("
        "(SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.estate_id=c.estate_id "
        "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1),"
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
        row["cantiniere_telephone"] = CANTINIERE_TELEPHONE
        row["content_description"] = row.get("content_description") or row.get("variety_summary") or row.get("wine_lot_name")
        row["processing_phase"] = row.get("processing_phase") or processing_phase_for(row.get("stage"))
        row["capacity_hl"] = round(float(row.get("capacity_l") or 0) / 100, 2)
        row["label_url"] = f"/tank/{row['public_token']}"
        row["legal_parcels"] = legal_parcels_for_tank(str(row["container_id"]), row.get("wine_lot_id"))
        result.append(row)
    return json_ready(result)


def save_legal_profile(container_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    tank = fetch_one(
        "SELECT c.id,w.id wine_lot_id,s.vintage_year,w.variety_summary,w.stage "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.id=COALESCE("
        "(SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.estate_id=c.estate_id "
        "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1),"
        "(SELECT tr.wine_lot_id FROM cellar_lot_trace_records tr WHERE tr.container_id=c.id AND tr.estate_id=c.estate_id ORDER BY tr.transferred_at DESC LIMIT 1)) "
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
        "tl.active label_active,w.id wine_lot_id,w.code wine_lot_code,w.name wine_lot_name,"
        "COALESCE(w.stage,cp.manual_stage) stage,COALESCE(w.volume_l,cp.manual_volume_l) volume_l,"
        "COALESCE(w.variety_summary,cp.manual_contents) variety_summary,"
        "s.vintage_year,COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status,cp.manual_temp_c temp_c,cp.manual_density_sg density_sg,"
        "cp.manual_brix brix,cp.manual_ph ph,cp.manual_reading_at reading_at,lp.wine_type,COALESCE(lp.wine_color,cp.wine_color) wine_color,COALESCE(lp.origin_country,'Italia') origin_country,"
        "lp.legal_company_name,lp.vat_number,lp.pec,lp.telephone,lp.cantiniere,"
        "lp.denomination_class,lp.denomination,lp.content_description,lp.processing_phase,lp.racking_history,lp.legal_notes,"
        "(SELECT fo.next_check_at FROM fermentation_observations fo WHERE fo.estate_id=c.estate_id AND (fo.wine_lot_id=w.id OR fo.vessel_name=c.name) AND fo.next_check_at IS NOT NULL ORDER BY fo.observed_at DESC LIMIT 1) next_check_at,"
        "lp.confirmed_by,lp.confirmed_at,lp.updated_at legal_updated_at "
        "FROM cellar_tank_labels tl JOIN cellar_containers c ON c.id=tl.container_id AND c.estate_id=tl.estate_id "
        "LEFT JOIN wine_lots w ON w.id=COALESCE("
        "(SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.estate_id=c.estate_id "
        "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1),"
        "(SELECT tr.wine_lot_id FROM cellar_lot_trace_records tr WHERE tr.container_id=c.id AND tr.estate_id=c.estate_id ORDER BY tr.transferred_at DESC LIMIT 1)) "
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
    row["cantiniere_telephone"] = CANTINIERE_TELEPHONE
    row["wine_type"] = row.get("wine_type") or "—"
    row["denomination_display"] = " · ".join(value for value in (row.get("denomination_class"), row.get("denomination")) if value) or "—"
    row["legal_parcels"] = legal_parcels_for_tank(str(row["container_id"]), row.get("wine_lot_id"))
    row["transfers"] = fetch_all(
        "SELECT transferred_at,notes FROM cellar_lot_trace_records WHERE estate_id=%s AND wine_lot_id=%s ORDER BY transferred_at DESC LIMIT 8",
        (estate_id(), row.get("wine_lot_id")),
    ) if row.get("wine_lot_id") else []
    trend_rows = fetch_all(
        "SELECT observed_at,temp_c,density_sg,brix,ph FROM fermentation_observations "
        "WHERE estate_id=%s AND (wine_lot_id=%s OR vessel_name=%s) "
        "ORDER BY observed_at DESC LIMIT 12",
        (estate_id(), row.get("wine_lot_id"), row.get("name")),
    )
    row["trends"] = list(reversed(trend_rows))
    if row.get("reading_mode") == "auto":
        apply_plaato_readings([row], fetch_plaato_snapshot(get_settings()))
        plaato = row.get("plaato") or {}
        row["plato"] = plaato.get("plato")
        row["fermentation_rate_msg_h"] = plaato.get("fermentation_rate_msg_h")
        row["battery_pct"] = plaato.get("battery_pct")
        row["wifi_pct"] = plaato.get("wifi_pct")
        if plaato.get("history"):
            row["trends"] = [
                {"observed_at": item.get("time"), "temp_c": item.get("temperature_c"), "density_sg": item.get("density_sg")}
                for item in plaato["history"]
            ]
    return json_ready(row)


def kiosk_rows(active: bool = True) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT k.id,k.name,k.public_token,k.container_id,k.active,k.notes,k.last_seen_at,"
        "TIMESTAMPDIFF(SECOND,k.last_seen_at,NOW(6)) last_seen_seconds,k.created_at,k.updated_at,"
        "c.code tank_code,c.name tank_name,c.active tank_active,tl.public_token tank_token "
        "FROM cellar_label_kiosks k LEFT JOIN cellar_containers c ON c.id=k.container_id AND c.estate_id=k.estate_id "
        "LEFT JOIN cellar_tank_labels tl ON tl.container_id=c.id AND tl.estate_id=c.estate_id "
        "WHERE k.estate_id=%s AND k.active=%s ORDER BY k.name",
        (estate_id(), 1 if active else 0),
    )
    for row in rows:
        row["kiosk_url"] = f"/kiosk/{row['public_token']}"
    return _device_connection_status(rows)


def enrollment_rows() -> list[dict[str, Any]]:
    """Return live pairing requests without exposing the device identifier."""
    return json_ready(fetch_all(
        "SELECT id,device_hint,pairing_code,status,expires_at,last_seen_at,created_at "
        "FROM cellar_label_enrollments WHERE estate_id=%s AND status='pending' "
        "AND expires_at>NOW(6) ORDER BY created_at DESC",
        (estate_id(),),
    ))


def provisioned_device_rows() -> list[dict[str, Any]]:
    """List approved or declined devices for administration and reprovisioning."""
    rows = fetch_all(
        "SELECT e.id,e.device_hint,e.status,e.display_name,e.device_role,e.destination_url,"
        "COALESCE(k.last_seen_at,e.last_seen_at) last_seen_at,e.last_seen_at enrollment_last_seen_at,k.last_seen_at kiosk_last_seen_at,"
        "TIMESTAMPDIFF(SECOND,COALESCE(k.last_seen_at,e.last_seen_at),NOW(6)) last_seen_seconds,e.approved_at,e.approved_by,"
        "k.id kiosk_id,k.name,k.active kiosk_active,k.container_id,c.code tank_code,c.name tank_name "
        "FROM cellar_label_enrollments e "
        "LEFT JOIN cellar_label_kiosks k ON k.id=e.kiosk_id AND k.estate_id=e.estate_id "
        "LEFT JOIN cellar_containers c ON c.id=k.container_id AND c.estate_id=e.estate_id "
        "WHERE e.estate_id=%s AND e.status IN ('approved','rejected') ORDER BY e.updated_at DESC",
        (estate_id(),),
    )
    return _device_connection_status(rows)


def _device_connection_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply one consistent heartbeat rule to label-device administration rows."""
    for row in rows:
        age = row.get("last_seen_seconds")
        active = bool(row.get("active", row.get("kiosk_active", True)))
        online = active and age is not None and 0 <= int(age) <= 120
        row["connection_status"] = "online" if online else "offline"
        row["connection_label"] = "Up" if online else "Down"
    return json_ready(rows)


def _normalized_device_key(device_key: str) -> str:
    value = str(device_key or "").strip()
    if value in {"$deviceID", "%24deviceID"} or not 4 <= len(value) <= 190:
        raise ValueError("The kiosk did not provide a valid device identifier")
    if not re.fullmatch(r"[A-Za-z0-9._:@+-]+", value):
        raise ValueError("The kiosk device identifier contains unsupported characters")
    return value


def _device_key_hash(device_key: str) -> tuple[str, str]:
    value = _normalized_device_key(device_key)
    compact = re.sub(r"[^A-Za-z0-9]", "", value)
    hint = (compact[-8:] if compact else value[-8:]).upper()
    return hashlib.sha256(value.encode("utf-8")).hexdigest(), hint


def _new_pairing_code(cursor: Any) -> str:
    for _ in range(20):
        code = f"{secrets.randbelow(1_000_000):06d}"
        cursor.execute(
            "SELECT id FROM cellar_label_enrollments WHERE estate_id=%s AND pairing_code=%s "
            "AND status='pending' AND expires_at>NOW(6) LIMIT 1",
            (estate_id(), code),
        )
        if not cursor.fetchone():
            return code
    raise RuntimeError("Unable to allocate a tablet pairing code")


def request_kiosk_enrollment(device_key: str) -> dict[str, Any]:
    """Create or refresh a short-lived public pairing request for one device."""
    device_hash, device_hint = _device_key_hash(device_key)
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT e.*,k.public_token,k.active kiosk_active FROM cellar_label_enrollments e "
            "LEFT JOIN cellar_label_kiosks k ON k.id=e.kiosk_id AND k.estate_id=e.estate_id "
            "WHERE e.estate_id=%s AND e.device_key_hash=%s LIMIT 1 FOR UPDATE",
            (estate_id(), device_hash),
        )
        row = cursor.fetchone()
        if row and row.get("status") == "approved" and row.get("device_role") == "ipad" and row.get("destination_url"):
            cursor.execute(
                "UPDATE cellar_label_enrollments SET last_seen_at=NOW(6) WHERE id=%s",
                (row["id"],),
            )
            return {"status": "approved", "device_role": "ipad", "destination_url": row["destination_url"]}
        if row and row.get("status") == "approved" and row.get("kiosk_active") and row.get("public_token"):
            cursor.execute(
                "UPDATE cellar_label_enrollments SET last_seen_at=NOW(6) WHERE id=%s",
                (row["id"],),
            )
            return {"status": "approved", "kiosk_url": f"/kiosk/{row['public_token']}"}
        if row and row.get("status") == "rejected":
            cursor.execute(
                "UPDATE cellar_label_enrollments SET last_seen_at=NOW(6) WHERE id=%s",
                (row["id"],),
            )
            return {"status": "rejected", "message": "Enrollment was declined. Ask an administrator to reset this tablet request."}
        if row and row.get("status") == "pending" and row.get("expires_at"):
            cursor.execute(
                "SELECT expires_at>NOW(6) active FROM cellar_label_enrollments WHERE id=%s",
                (row["id"],),
            )
            if bool((cursor.fetchone() or {}).get("active")):
                cursor.execute(
                    "UPDATE cellar_label_enrollments SET last_seen_at=NOW(6) WHERE id=%s",
                    (row["id"],),
                )
                return {
                    "status": "pending", "pairing_code": row["pairing_code"],
                    "device_hint": row["device_hint"], "expires_at": row["expires_at"],
                }
        code = _new_pairing_code(cursor)
        if row:
            cursor.execute(
                "UPDATE cellar_label_enrollments SET device_hint=%s,pairing_code=%s,status='pending',"
                "display_name=NULL,device_role=NULL,destination_url=NULL,kiosk_id=NULL,"
                "expires_at=DATE_ADD(NOW(6),INTERVAL 15 MINUTE),last_seen_at=NOW(6),"
                "approved_at=NULL,approved_by=NULL WHERE id=%s",
                (device_hint, code, row["id"]),
            )
            enrollment_id = row["id"]
        else:
            enrollment_id = new_id()
            cursor.execute(
                "INSERT INTO cellar_label_enrollments "
                "(id,estate_id,device_key_hash,device_hint,pairing_code,status,expires_at,last_seen_at) "
                "VALUES (%s,%s,%s,%s,%s,'pending',DATE_ADD(NOW(6),INTERVAL 15 MINUTE),NOW(6))",
                (enrollment_id, estate_id(), device_hash, device_hint, code),
            )
    return {
        "status": "pending", "pairing_code": code, "device_hint": device_hint,
        "expires_in_seconds": 900, "enrollment_id": enrollment_id,
    }


def approve_device_enrollment(
    enrollment_id: str,
    payload: dict[str, Any],
    actor: str,
    ipad_dashboard_url: str,
) -> dict[str, Any]:
    device_role = str(payload.get("device_role") or "label").strip().casefold()
    if device_role not in {"label", "ipad"}:
        raise ValueError("Choose tank label or Vineyard Operations display")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Enter a tablet name")
    container_id = str(payload.get("container_id") or "").strip() or None
    if device_role == "ipad":
        container_id = None
    if container_id and not fetch_one(
        "SELECT id FROM cellar_containers WHERE id=%s AND estate_id=%s AND active=1",
        (container_id, estate_id()),
    ):
        raise ValueError("Choose an active tank")
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT * FROM cellar_label_enrollments WHERE id=%s AND estate_id=%s FOR UPDATE",
            (enrollment_id, estate_id()),
        )
        enrollment = cursor.fetchone()
        if not enrollment or enrollment.get("status") != "pending":
            raise ValueError("Tablet pairing request is no longer pending")
        cursor.execute(
            "SELECT expires_at>NOW(6) active FROM cellar_label_enrollments WHERE id=%s",
            (enrollment_id,),
        )
        if not bool((cursor.fetchone() or {}).get("active")):
            raise ValueError("Tablet pairing code expired; refresh the tablet to request a new code")
        if device_role == "ipad":
            destination = str(ipad_dashboard_url or "").strip()
            if not destination.startswith(("http://", "https://")):
                raise ValueError("Configure a valid Vineyard iPad dashboard URL")
            cursor.execute(
                "UPDATE cellar_label_enrollments SET status='approved',display_name=%s,device_role='ipad',destination_url=%s,"
                "kiosk_id=NULL,approved_at=NOW(6),approved_by=%s WHERE id=%s AND estate_id=%s",
                (name, destination, actor, enrollment_id, estate_id()),
            )
            return {"approved": True, "device_role": "ipad", "destination_url": destination}
        kiosk_id, token = new_id(), new_id()
        cursor.execute(
            "INSERT INTO cellar_label_kiosks (id,estate_id,name,public_token,container_id,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (kiosk_id, estate_id(), name, token, container_id, str(payload.get("notes") or "").strip() or None),
        )
        cursor.execute(
            "UPDATE cellar_label_enrollments SET status='approved',display_name=%s,device_role='label',destination_url=NULL,"
            "kiosk_id=%s,approved_at=NOW(6),approved_by=%s WHERE id=%s AND estate_id=%s",
            (name, kiosk_id, actor, enrollment_id, estate_id()),
        )
    return {"approved": True, "device_role": "label", "id": kiosk_id, "public_token": token, "kiosk_url": f"/kiosk/{token}"}


def reject_kiosk_enrollment(enrollment_id: str, actor: str) -> dict[str, Any]:
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_label_enrollments SET status='rejected',approved_by=%s "
            "WHERE id=%s AND estate_id=%s AND status='pending'",
            (actor, enrollment_id, estate_id()),
        )
        if cursor.rowcount != 1:
            raise ValueError("Tablet pairing request is no longer pending")
    return {"rejected": True, "id": enrollment_id}


def reprovision_device(enrollment_id: str, actor: str) -> dict[str, Any]:
    """Invalidate the old assignment and return a known device to short-code pairing."""
    with transaction() as (_, cursor):
        cursor.execute(
            "SELECT * FROM cellar_label_enrollments WHERE id=%s AND estate_id=%s FOR UPDATE",
            (enrollment_id, estate_id()),
        )
        enrollment = cursor.fetchone()
        if not enrollment:
            raise ValueError("Provisioned display not found")
        kiosk_id = enrollment.get("kiosk_id")
        if kiosk_id:
            cursor.execute(
                "UPDATE cellar_label_kiosks SET active=0,container_id=NULL,notes=CONCAT_WS(' · ',notes,%s) "
                "WHERE id=%s AND estate_id=%s AND active=1",
                (f"Reprovisioned by {actor}", kiosk_id, estate_id()),
            )
        code = _new_pairing_code(cursor)
        cursor.execute(
            "UPDATE cellar_label_enrollments SET pairing_code=%s,status='pending',display_name=NULL,device_role=NULL,destination_url=NULL,"
            "kiosk_id=NULL,expires_at=DATE_ADD(NOW(6),INTERVAL 15 MINUTE),approved_at=NULL,approved_by=NULL "
            "WHERE id=%s AND estate_id=%s",
            (code, enrollment_id, estate_id()),
        )
    return {"reprovisioning": True, "id": enrollment_id, "pairing_code": code, "expires_in_seconds": 900}


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
