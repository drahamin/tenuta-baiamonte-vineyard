"""Cellar dashboard, tank lifecycle, traceability, and label-device routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pymysql.err import IntegrityError

from ..access import authorize, authorize_write
from ..cellar_demo import (
    apply_live_sensor_readings,
    cellar_guardrails,
    demo_cellar,
    demo_enabled,
    evaluate_cellar_tanks,
    live_sensor_entity_ids,
    live_sensor_tank_keys,
)
from ..config import Settings, get_settings, runtime_option
from ..db import fetch_all, fetch_one, transaction
from ..display_provisioning import cellar_label_origin, url_qr
from ..historical_dashboard import (
    FIRST_ESTATE_VINTAGE,
    all_vintage_rows,
    historical_cellar_summary,
    merge_cellar_history,
    variety_vintage_history,
)
from ..intelligence import home_assistant_state_map
from ..service import audit, estate_id, json_ready, new_id, season_for_year
from ..tank_labels import (
    CELLAR_STAGES,
    WINE_COLORS,
    WINE_LOT_STAGES,
    approve_device_enrollment,
    create_kiosk,
    ensure_tank_label,
    reject_kiosk_enrollment,
    reprovision_device,
    retire_kiosk,
    save_legal_profile,
    update_kiosk,
)
from .cellar import manual_tank_definitions, update_tank_details
from .laboratory import cellar_laboratory_evidence
from .people_roles import require_discipline_approval
from .plaato import apply_plaato_readings, fetch_plaato_snapshot, plaato_tank_keys


router = APIRouter(tags=["cellar"])


@router.get("/api/v1/cellar/dashboard", dependencies=[Depends(authorize)])
def cellar_dashboard(year: int = Query(default_factory=lambda: date.today().year, ge=FIRST_ESTATE_VINTAGE)) -> dict[str, Any]:
    settings = get_settings()
    if demo_enabled(settings):
        result = demo_cellar(settings, year)
        result["history"] = fetch_all(
            "SELECT s.vintage_year,w.lot_count,w.volume_l,w.fruit_kg,co.operation_count,co.latest_operation_at "
            "FROM seasons s LEFT JOIN (SELECT season_id,COUNT(*) lot_count,SUM(COALESCE(volume_l,initial_l)) volume_l,SUM(fruit_kg) fruit_kg FROM wine_lots GROUP BY season_id) w ON w.season_id=s.id "
            "LEFT JOIN (SELECT season_id,COUNT(*) operation_count,MAX(operation_at) latest_operation_at FROM cellar_operations GROUP BY season_id) co ON co.season_id=s.id "
            "WHERE s.estate_id=%s AND s.vintage_year>=%s ORDER BY s.vintage_year",
            (estate_id(), FIRST_ESTATE_VINTAGE),
        )
        return json_ready(result)
    return _live_cellar_dashboard(year, settings)


def _live_cellar_dashboard(year: int, settings: Settings) -> dict[str, Any]:
    season = fetch_one("SELECT id FROM seasons WHERE estate_id=%s AND vintage_year=%s", (estate_id(), year)) or {}
    season_id = season.get("id", "")
    tanks = fetch_all(
        "SELECT c.id,c.code,c.name,c.container_type,c.material,c.capacity_l,c.location,c.notes,c.sensor_entity_id,c.status,"
        "w.id wine_lot_id,w.code lot_code,w.name lot_name,COALESCE(w.stage,cp.manual_stage) stage,COALESCE(w.volume_l,cp.manual_volume_l) volume_l,COALESCE(w.variety_summary,cp.manual_contents) variety_summary,cp.wine_color,w.started_at,"
        "COALESCE((SELECT f.temp_c FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_temp_c) temp_c,"
        "COALESCE((SELECT f.density_sg FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_density_sg) density_sg,"
        "COALESCE((SELECT f.brix FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_brix) brix,"
        "COALESCE((SELECT f.ph FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_ph) ph,"
        "COALESCE((SELECT f.observed_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1),cp.manual_reading_at) reading_at,"
        "(SELECT f.next_check_at FROM fermentation_observations f WHERE f.wine_lot_id=w.id ORDER BY f.observed_at DESC LIMIT 1) next_check_at,"
        "COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status,"
        "cp.last_maintenance_at,cp.next_maintenance_at,cp.maintenance_notes "
        "FROM cellar_containers c LEFT JOIN wine_lots w ON w.id=("
        "SELECT wx.id FROM wine_lots wx WHERE wx.current_container_id=c.id AND wx.season_id=%s "
        "AND COALESCE(wx.volume_l,wx.initial_l,0)>0 ORDER BY wx.started_at DESC,wx.id DESC LIMIT 1) "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.estate_id=%s AND c.active=1 ORDER BY c.code",
        (season_id, estate_id()),
    )
    for tank in tanks:
        capacity = float(tank.get("capacity_l") or 0)
        volume = float(tank.get("volume_l") or 0)
        tank["level_pct"] = round(volume / capacity * 100, 1) if capacity else None
        tank["source"] = "Manual record"
        tank["vintage_year"] = year if tank.get("wine_lot_id") else None
    configured_keys = live_sensor_tank_keys(settings)
    for tank in tanks:
        tank["sensor_configured"] = bool(
            tank.get("sensor_entity_id")
            or str(tank.get("code") or "").casefold() in configured_keys
            or str(tank.get("name") or "").casefold() in configured_keys
        )
        if tank.get("reading_mode") == "sensor":
            tank["sensor_status"] = "configured" if tank["sensor_configured"] else "not_configured"
    try:
        sensor_tanks = [tank for tank in tanks if tank.get("reading_mode") == "sensor" and tank.get("sensor_configured")]
        apply_live_sensor_readings(sensor_tanks, settings, home_assistant_state_map(live_sensor_entity_ids(settings)))
        for tank in sensor_tanks:
            tank["sensor_status"] = "fault" if tank.get("sensor_issues") else "live"
    except Exception:
        for tank in tanks:
            if tank.get("reading_mode") == "sensor" and tank.get("sensor_configured"):
                tank["sensor_status"] = "fault"
    plaato = {"configured": False, "connected": False, "status": "Not configured", "tanks": {}}
    # Demo credentials make an automatic Tank Sensor selectable without a
    # physical mapping, but they must never turn manual vessels into simulated
    # live vessels. Reading mode is the authoritative per-tank boundary.
    auto_tanks = [tank for tank in tanks if tank.get("reading_mode") == "auto"]
    if auto_tanks:
        plaato = fetch_plaato_snapshot(settings)
        apply_plaato_readings(auto_tanks, plaato)
        for tank in auto_tanks:
            if not tank.get("plaato"):
                tank["sensor_status"] = "fault" if plaato.get("configured") else "not_configured"
                tank["sensor_issues"] = [plaato.get("status") or "Tank Sensor mapping unavailable"]
    cellar_laboratory_evidence(tanks, year)
    guard_alerts = evaluate_cellar_tanks(tanks, settings)
    process_history = fetch_all(
        "SELECT f.id,f.wine_lot_id,f.observed_at,f.vessel_name,f.stage,f.temp_c,f.density_sg,f.brix,f.ph,f.cap_management,f.addition_action,f.sensory_observation,f.owner_text,f.next_check_at,f.status,w.code lot_code,w.name lot_name "
        "FROM fermentation_observations f LEFT JOIN wine_lots w ON w.id=f.wine_lot_id WHERE f.estate_id=%s "
        "AND (w.season_id=%s OR w.season_id IS NULL) ORDER BY f.observed_at DESC LIMIT 500",
        (estate_id(), season_id),
    )
    for tank in tanks:
        tank_keys = {str(tank.get("code") or "").strip().casefold(), str(tank.get("name") or "").strip().casefold()}
        tank["fermentation_process"] = [
            row for row in process_history
            if (tank.get("wine_lot_id") and row.get("wine_lot_id") == tank.get("wine_lot_id"))
            or str(row.get("vessel_name") or "").strip().casefold() in tank_keys
        ]
    processes = process_history[:30]
    if year != date.today().year:
        tanks = [tank for tank in tanks if tank.get("wine_lot_id")]
        processes = [process for process in processes if process.get("lot_code")]
        guard_alerts = evaluate_cellar_tanks(tanks, settings)
    history = fetch_all(
        "SELECT s.vintage_year,w.lot_count,w.volume_l,w.fruit_kg,co.operation_count,co.latest_operation_at "
        "FROM seasons s LEFT JOIN (SELECT season_id,COUNT(*) lot_count,SUM(COALESCE(volume_l,initial_l)) volume_l,SUM(fruit_kg) fruit_kg FROM wine_lots GROUP BY season_id) w ON w.season_id=s.id "
        "LEFT JOIN (SELECT season_id,COUNT(*) operation_count,MAX(operation_at) latest_operation_at FROM cellar_operations GROUP BY season_id) co ON co.season_id=s.id "
        "WHERE s.estate_id=%s AND s.vintage_year>=%s ORDER BY s.vintage_year",
        (estate_id(), FIRST_ESTATE_VINTAGE),
    )
    all_vintage_summaries = all_vintage_rows()
    for tank in tanks:
        tank["wine_history"] = variety_vintage_history(tank.get("variety_summary"), all_vintage_summaries)
    history = merge_cellar_history(history, all_vintage_summaries)
    selected_rows = [row for row in all_vintage_summaries if int(row["vintage_year"]) == year]
    return json_ready({"year": year, "demo": False, "tanks": tanks, "processes": processes, "guardrails": cellar_guardrails(settings), "guard_alerts": guard_alerts, "history": history, "historical_summary": historical_cellar_summary(year, selected_rows), "plaato": {key: value for key, value in plaato.items() if key != "tanks"}})


def _cellar_container(container_id: str) -> dict[str, Any]:
    row = fetch_one(
        "SELECT c.*,COALESCE(cp.reading_mode,'manual') reading_mode,COALESCE(cp.sensor_status,'not_configured') sensor_status "
        "FROM cellar_containers c LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.id=%s AND c.estate_id=%s AND c.active=1",
        (container_id, estate_id()),
    )
    if not row:
        raise HTTPException(404, "Cellar tank not found")
    return row


def _ensure_current_manual_tanks(settings: Settings) -> None:
    raw = str(runtime_option("cellar_demo_tanks", settings.cellar_demo_tanks) or settings.cellar_demo_tanks)
    definitions = manual_tank_definitions(raw)
    with transaction() as (_, cursor):
        for index, parts in enumerate(definitions, start=1):
            name = parts[0] if parts and parts[0] else f"Tank {index}"
            try:
                capacity = max(1.0, float(parts[1]))
            except (IndexError, TypeError, ValueError):
                capacity = 750.0
            try:
                level = min(100.0, max(0.0, float(parts[4])))
            except (IndexError, TypeError, ValueError):
                level = 0.0
            stage = parts[3] if len(parts) > 3 and parts[3] else None
            contents = parts[2] if len(parts) > 2 and parts[2] else None
            def configured_number(position: int) -> float | None:
                try:
                    return float(parts[position]) if parts[position] else None
                except (IndexError, TypeError, ValueError):
                    return None
            temp = configured_number(5)
            density = configured_number(6)
            brix = configured_number(7)
            ph = configured_number(8)
            container_type = "barrel" if str(stage or "").casefold() == "aging" else "tank"
            cursor.execute("SELECT id FROM cellar_containers WHERE estate_id=%s AND (name=%s OR code=%s) LIMIT 1", (estate_id(), name, f"T-{index:02d}"))
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    "INSERT IGNORE INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) "
                    "VALUES (%s,%s,%s,'manual','not_configured',%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6),'startup-import')",
                    (new_id(), estate_id(), existing["id"], contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph),
                )
                cursor.execute(
                    "UPDATE cellar_control_profiles SET manual_contents=COALESCE(manual_contents,%s),manual_volume_l=COALESCE(manual_volume_l,%s),manual_stage=COALESCE(manual_stage,%s),"
                    "manual_temp_c=COALESCE(manual_temp_c,%s),manual_density_sg=COALESCE(manual_density_sg,%s),manual_brix=COALESCE(manual_brix,%s),manual_ph=COALESCE(manual_ph,%s),"
                    "manual_reading_at=COALESCE(manual_reading_at,NOW(6)),manual_updated_at=COALESCE(manual_updated_at,NOW(6)) WHERE estate_id=%s AND container_id=%s",
                    (contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph, estate_id(), existing["id"]),
                )
                continue
            container_id = new_id()
            cursor.execute(
                "INSERT INTO cellar_containers (id,estate_id,code,name,container_type,capacity_l,status,notes,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1)",
                (container_id, estate_id(), f"T-{index:02d}", name, container_type, capacity, "in_use" if level else "empty", "Imported from the prior configured tank list"),
            )
            cursor.execute(
                "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) VALUES (%s,%s,%s,'manual','not_configured',%s,%s,%s,%s,%s,%s,%s,NOW(6),NOW(6),'startup-import')",
                (new_id(), estate_id(), container_id, contents, round(capacity * level / 100, 3), stage, temp, density, brix, ph),
            )
            audit(cursor, "import", "cellar_container", container_id, {"source": "configured tank list", "reading_mode": "manual"}, "startup")

        cursor.execute(
            "SELECT id FROM cellar_containers WHERE estate_id=%s AND active=1",
            (estate_id(),),
        )
        for tank in cursor.fetchall():
            ensure_tank_label(cursor, tank["id"])


@router.post("/api/v1/agronomy/tanks", dependencies=[Depends(authorize_write)])
def create_manual_tank(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload.get("code") or "").strip()
    name = str(payload.get("name") or "").strip()
    container_type = str(payload.get("container_type") or "tank").strip().casefold()
    if not code or not name:
        raise HTTPException(422, "Enter a tank code and name")
    if container_type not in {"tank", "fermenter", "aging", "barrel", "amphora", "demijohn", "bin", "press", "other"}:
        raise HTTPException(422, "Choose a supported container type")
    capacity = float(payload.get("capacity_l") or 0)
    if not 0 < capacity <= 1000000:
        raise HTTPException(422, "Enter a valid capacity in liters")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    container_id = new_id()
    try:
        with transaction() as (_, cursor):
            cursor.execute(
                "INSERT INTO cellar_containers (id,estate_id,code,name,container_type,material,capacity_l,location,status,notes,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'empty',%s,1)",
                (container_id, estate_id(), code, name, container_type, str(payload.get("material") or "").strip() or None, capacity, str(payload.get("location") or "").strip() or None, str(payload.get("notes") or "").strip() or None),
            )
            cursor.execute("INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,updated_by) VALUES (%s,%s,%s,'manual','not_configured',%s)", (new_id(), estate_id(), container_id, actor))
            ensure_tank_label(cursor, container_id)
            audit(cursor, "create", "cellar_container", container_id, {"code": code, "name": name, "capacity_l": capacity, "reading_mode": "manual"}, actor)
    except IntegrityError as exc:
        raise HTTPException(409, "A tank with that code already exists") from exc
    return {"saved": True, "id": container_id, "reading_mode": "manual"}

@router.put("/api/v1/agronomy/tanks/{container_id}/legal-label", dependencies=[Depends(authorize_write)])
def update_tank_legal_label(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    require_discipline_approval(request, "enology")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = save_legal_profile(container_id, payload, actor)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "update", "tank_legal_label", container_id, {"wine_lot_id": result["wine_lot_id"]}, actor)
    return result


@router.post("/api/v1/agronomy/label-kiosks", dependencies=[Depends(authorize_write)])
def add_tank_label_kiosk(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = create_kiosk(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "create", "cellar_label_kiosk", result["id"], {"name": payload.get("name"), "container_id": payload.get("container_id")}, actor)
    return result


@router.put("/api/v1/agronomy/label-kiosks/{kiosk_id}", dependencies=[Depends(authorize_write)])
def edit_tank_label_kiosk(kiosk_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = update_kiosk(kiosk_id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "update", "cellar_label_kiosk", kiosk_id, {"name": payload.get("name"), "container_id": payload.get("container_id")}, actor)
    return result


@router.get("/api/v1/agronomy/label-kiosks/{kiosk_id}/qr", dependencies=[Depends(authorize_write)])
def tank_label_kiosk_qr(kiosk_id: str) -> Response:
    kiosk = fetch_one(
        "SELECT public_token FROM cellar_label_kiosks WHERE id=%s AND estate_id=%s AND active=1",
        (kiosk_id, estate_id()),
    )
    if not kiosk:
        raise HTTPException(404, "Tablet not found")
    origin = cellar_label_origin(get_settings())
    return url_qr(f"{origin}/kiosk/{kiosk['public_token']}")


@router.delete("/api/v1/agronomy/label-kiosks/{kiosk_id}", dependencies=[Depends(authorize_write)])
def delete_tank_label_kiosk(kiosk_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = retire_kiosk(kiosk_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "retire", "cellar_label_kiosk", kiosk_id, {}, actor)
    return result


@router.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/approve", dependencies=[Depends(authorize_write)])
def approve_tank_label_enrollment(enrollment_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = approve_device_enrollment(
            enrollment_id,
            payload,
            actor,
            get_settings().cellar_ipad_dashboard_url,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "approve", "cellar_label_enrollment", enrollment_id, {
            "device_role": result.get("device_role"),
            "kiosk_id": result.get("id"),
            "container_id": payload.get("container_id"),
        }, actor)
    return result


@router.delete("/api/v1/agronomy/label-enrollments/{enrollment_id}", dependencies=[Depends(authorize_write)])
def reject_tank_label_enrollment(enrollment_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = reject_kiosk_enrollment(enrollment_id, actor)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "reject", "cellar_label_enrollment", enrollment_id, {}, actor)
    return result


@router.post("/api/v1/agronomy/label-enrollments/{enrollment_id}/reprovision", dependencies=[Depends(authorize_write)])
def reprovision_tank_label_device(enrollment_id: str, request: Request) -> dict[str, Any]:
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        result = reprovision_device(enrollment_id, actor)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with transaction() as (_, cursor):
        audit(cursor, "reprovision", "cellar_label_enrollment", enrollment_id, {
            "expires_in_seconds": result["expires_in_seconds"],
        }, actor)
    return result


@router.post("/api/v1/agronomy/tanks/{container_id}/lot-transfer", dependencies=[Depends(authorize_write)])
def save_harvest_lot_transfer(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    year = int(payload.get("year") or date.today().year)
    season = season_for_year(year)
    harvest_lot_id = str(payload.get("harvest_lot_id") or "").strip()
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip()
    harvest_lot = fetch_one("SELECT * FROM harvest_lots WHERE id=%s AND estate_id=%s AND season_id=%s", (harvest_lot_id, estate_id(), season))
    wine_lot = fetch_one("SELECT * FROM wine_lots WHERE id=%s AND estate_id=%s AND season_id=%s", (wine_lot_id, estate_id(), season))
    if not harvest_lot or not wine_lot:
        raise HTTPException(422, "Choose a harvest lot and cellar lot from this vintage")
    parcel_rows = fetch_all(
        "SELECT p.id,p.municipality,p.cadastral_sheet,p.parcel_number FROM harvest_lot_parcels hp "
        "JOIN cadastral_parcels p ON p.id=hp.parcel_id AND p.estate_id=hp.estate_id "
        "WHERE hp.estate_id=%s AND hp.harvest_lot_id=%s ORDER BY p.municipality,p.cadastral_sheet,p.parcel_number",
        (estate_id(), harvest_lot_id),
    )

    def optional_number(key: str) -> float | None:
        raw = payload.get(key)
        if raw in (None, ""):
            return None
        value = float(raw)
        if value < 0:
            raise HTTPException(422, f"{key} cannot be negative")
        return value
    fruit_kg = optional_number("fruit_kg")
    must_l = optional_number("must_l")
    transferred_at = payload.get("transferred_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    actor = request.headers.get("X-Remote-User-Name") or "api"
    trace_id = new_id()
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cellar_lot_trace_records (id,estate_id,season_id,harvest_lot_id,wine_lot_id,container_id,transferred_at,fruit_kg,must_l,notes,recorded_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (trace_id, estate_id(), season, harvest_lot_id, wine_lot_id, container_id, transferred_at, fruit_kg, must_l, str(payload.get("notes") or "").strip() or None, actor),
        )
        cursor.execute(
            "UPDATE wine_lots SET current_container_id=%s,harvest_lot_reference=%s,"
            "fruit_kg=CASE WHEN %s IS NULL THEN fruit_kg ELSE COALESCE(fruit_kg,0)+%s END,"
            "initial_l=CASE WHEN %s IS NULL THEN initial_l ELSE COALESCE(initial_l,0)+%s END,"
            "volume_l=CASE WHEN %s IS NULL THEN volume_l ELSE COALESCE(volume_l,0)+%s END "
            "WHERE id=%s AND estate_id=%s",
            (container_id, harvest_lot_id, fruit_kg, fruit_kg, must_l, must_l, must_l, must_l, wine_lot_id, estate_id()),
        )
        cursor.execute("UPDATE cellar_containers SET status='in_use' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "transfer", "harvest_lot_to_tank", trace_id, {"harvest_lot_id": harvest_lot_id, "wine_lot_id": wine_lot_id, "container_id": container_id, "fruit_kg": fruit_kg, "must_l": must_l, "tank": tank.get("code"), "parcel_ids": [row["id"] for row in parcel_rows]}, actor)
    return {"saved": True, "id": trace_id, "legal_parcels_carried_to_tank": len(parcel_rows)}


@router.put("/api/v1/agronomy/tanks/{container_id}/mode", dependencies=[Depends(authorize_write)])
def set_agronomy_tank_mode(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    settings = get_settings()
    actor = request.headers.get("X-Remote-User-Name") or "api"
    try:
        return update_tank_details(tank, payload, actor, live_sensor_tank_keys(settings), plaato_tank_keys(settings))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except IntegrityError as error:
        raise HTTPException(409, "Another tank already uses that code") from error


@router.post("/api/v1/agronomy/tanks/{container_id}/reading", dependencies=[Depends(authorize_write)])
def save_manual_tank_reading(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    if tank.get("reading_mode") in {"sensor", "auto"}:
        raise HTTPException(409, "This tank is in automatic sensor mode. Switch it to manual mode before entering a manual reading")
    wine_lot_id = str(payload.get("wine_lot_id") or "").strip() or None
    lot = None
    if wine_lot_id:
        lot = fetch_one("SELECT w.* FROM wine_lots w JOIN seasons s ON s.id=w.season_id WHERE w.id=%s AND w.estate_id=%s AND s.vintage_year=%s", (wine_lot_id, estate_id(), int(payload.get("year") or date.today().year)))
        if not lot:
            raise HTTPException(422, "Choose a wine lot from this vintage")
    def number(key: str, minimum: float, maximum: float) -> float | None:
        raw = payload.get(key)
        if raw in (None, ""):
            return None
        value = float(raw)
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{key} must be between {minimum:g} and {maximum:g}")
        return value
    volume = number("volume_l", 0, max(float(tank.get("capacity_l") or 100000) * 1.05, 1))
    temp = number("temp_c", -20, 60)
    density = number("density_sg", 0.8, 1.5)
    brix = number("brix", -5, 50)
    ph = number("ph", 0, 14)
    stage = str(payload.get("stage") or (lot or {}).get("stage") or "").strip().casefold() or None
    stage = {"fermenting": "fermentation"}.get(stage, stage)
    if stage and stage not in CELLAR_STAGES:
        raise HTTPException(422, "Choose a supported cellar stage")
    contents = str(payload.get("contents") or (lot or {}).get("variety_summary") or "").strip() or None
    wine_color = str(payload.get("wine_color") or "").strip().casefold() or None
    if wine_color and wine_color not in WINE_COLORS:
        raise HTTPException(422, "Choose red, white or rosé")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    observed = payload.get("observed_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    next_check = str(payload.get("next_check_at") or "").strip() or None
    if next_check and len(next_check) == 10:
        next_check = f"{next_check} 09:00:00"
    reading_id = new_id()
    with transaction() as (_, cursor):
        if lot:
            lot_stage = stage if stage in WINE_LOT_STAGES else None
            cursor.execute("UPDATE wine_lots SET current_container_id=%s,volume_l=COALESCE(%s,volume_l),stage=COALESCE(%s,stage) WHERE id=%s AND estate_id=%s", (container_id, volume, lot_stage, wine_lot_id, estate_id()))
            cursor.execute("UPDATE cellar_containers SET status='in_use' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,manual_contents,wine_color,manual_volume_l,manual_stage,manual_temp_c,manual_density_sg,manual_brix,manual_ph,manual_reading_at,manual_updated_at,updated_by) "
            "VALUES (%s,%s,%s,'manual',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(6),%s) ON DUPLICATE KEY UPDATE manual_contents=VALUES(manual_contents),wine_color=VALUES(wine_color),manual_volume_l=VALUES(manual_volume_l),manual_stage=VALUES(manual_stage),manual_temp_c=VALUES(manual_temp_c),manual_density_sg=VALUES(manual_density_sg),manual_brix=VALUES(manual_brix),manual_ph=VALUES(manual_ph),manual_reading_at=VALUES(manual_reading_at),manual_updated_at=VALUES(manual_updated_at),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), container_id, tank.get("sensor_status") or "not_configured", contents, wine_color, volume, stage, temp, density, brix, ph, observed, actor),
        )
        cursor.execute(
            "INSERT INTO fermentation_observations (id,estate_id,wine_lot_id,observed_at,vessel_name,stage,temp_c,density_sg,brix,ph,sensory_observation,owner_text,next_check_at,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual')",
            (reading_id, estate_id(), wine_lot_id, observed, tank.get("name") or tank.get("code"), stage, temp, density, brix, ph, str(payload.get("notes") or "").strip() or None, actor, next_check),
        )
        audit(cursor, "manual_reading", "cellar_container", container_id, {"reading_id": reading_id, "wine_lot_id": wine_lot_id, "volume_l": volume, "stage": stage, "wine_color": wine_color}, actor)
    return {"saved": True, "id": reading_id, "container_id": container_id, "reading_mode": "manual"}


@router.post("/api/v1/agronomy/tanks/{container_id}/empty", dependencies=[Depends(authorize_write)])
def mark_tank_empty(container_id: str, request: Request) -> dict[str, Any]:
    """Clear current display state without deleting the vessel or its history."""
    tank = _cellar_container(container_id)
    assigned = fetch_one(
        "SELECT id,code,name,COALESCE(volume_l,initial_l,0) volume_l FROM wine_lots "
        "WHERE estate_id=%s AND current_container_id=%s AND COALESCE(volume_l,initial_l,0)>0 "
        "ORDER BY started_at DESC,id DESC LIMIT 1",
        (estate_id(), container_id),
    )
    if assigned:
        label = assigned.get("code") or assigned.get("name") or assigned.get("id")
        raise HTTPException(409, f"Tank still contains linked wine lot {label}; transfer or close that lot first")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute(
            "UPDATE cellar_containers SET status='empty' WHERE id=%s AND estate_id=%s",
            (container_id, estate_id()),
        )
        cursor.execute(
            "UPDATE cellar_control_profiles SET manual_contents=NULL,wine_color=NULL,manual_volume_l=0,"
            "manual_stage='empty',manual_temp_c=NULL,manual_density_sg=NULL,manual_brix=NULL,manual_ph=NULL,"
            "manual_reading_at=NULL,manual_updated_at=NOW(6),updated_by=%s WHERE container_id=%s AND estate_id=%s",
            (actor, container_id, estate_id()),
        )
        audit(cursor, "mark_empty", "cellar_container", container_id, {
            "code": tank.get("code"),
            "preserved_history": True,
            "reading_mode": tank.get("reading_mode") or "manual",
        }, actor)
    return {
        "saved": True,
        "container_id": container_id,
        "status": "empty",
        "volume_l": 0,
        "history_preserved": True,
    }


@router.delete("/api/v1/agronomy/tanks/{container_id}", dependencies=[Depends(authorize_write)])
def delete_manual_tank(container_id: str, request: Request) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    if tank.get("reading_mode") != "manual":
        raise HTTPException(409, "Switch this tank to manual mode before removing it")
    assigned = fetch_one(
        "SELECT id,code,name FROM wine_lots WHERE estate_id=%s AND current_container_id=%s LIMIT 1",
        (estate_id(), container_id),
    )
    if assigned:
        raise HTTPException(409, f"Move wine lot {assigned.get('code') or assigned.get('name')} out of this tank before removing it")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    with transaction() as (_, cursor):
        cursor.execute("UPDATE cellar_containers SET active=0,status='retired' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        cursor.execute("UPDATE cellar_tank_labels SET active=0,retired_at=NOW(6) WHERE container_id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "retire", "cellar_container", container_id, {"code": tank.get("code"), "reading_mode": "manual"}, actor)
    return {"saved": True, "container_id": container_id, "active": False, "status": "retired"}


@router.post("/api/v1/agronomy/tanks/{container_id}/maintenance", dependencies=[Depends(authorize_write)])
def save_tank_maintenance(container_id: str, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    tank = _cellar_container(container_id)
    status = str(payload.get("status") or "completed").casefold()
    if status not in {"planned", "in_progress", "completed"}:
        raise HTTPException(422, "Choose planned, in progress or completed")
    maintenance_type = str(payload.get("maintenance_type") or "").strip()
    if not maintenance_type:
        raise HTTPException(422, "Enter the maintenance type")
    actor = request.headers.get("X-Remote-User-Name") or "api"
    record_id = new_id()
    occurred = payload.get("maintenance_at") or datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
    with transaction() as (_, cursor):
        cursor.execute(
            "INSERT INTO cellar_maintenance_records (id,estate_id,container_id,maintenance_at,maintenance_type,status,performed_by,next_due_at,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (record_id, estate_id(), container_id, occurred, maintenance_type, status, actor, payload.get("next_due_at") or None, str(payload.get("notes") or "").strip() or None),
        )
        sensor_status = "maintenance" if status == "in_progress" else tank.get("sensor_status")
        cursor.execute(
            "INSERT INTO cellar_control_profiles (id,estate_id,container_id,reading_mode,sensor_status,last_maintenance_at,next_maintenance_at,maintenance_notes,updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE sensor_status=VALUES(sensor_status),last_maintenance_at=VALUES(last_maintenance_at),next_maintenance_at=VALUES(next_maintenance_at),maintenance_notes=VALUES(maintenance_notes),updated_by=VALUES(updated_by)",
            (new_id(), estate_id(), container_id, tank.get("reading_mode") or "manual", sensor_status, occurred, payload.get("next_due_at") or None, str(payload.get("notes") or "").strip() or None, actor),
        )
        if status == "in_progress":
            cursor.execute("UPDATE cellar_containers SET status='maintenance' WHERE id=%s AND estate_id=%s", (container_id, estate_id()))
        audit(cursor, "maintenance", "cellar_container", container_id, {"record_id": record_id, "type": maintenance_type, "status": status}, actor)
    return {"saved": True, "id": record_id}
