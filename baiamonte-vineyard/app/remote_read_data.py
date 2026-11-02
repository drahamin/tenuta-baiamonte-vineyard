"""Explicit SELECT-only projections; never reuse mutating local display GETs."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import HTTPException

from .db import fetch_all, fetch_one
from .remote_access import RemoteProfile
from .service import estate_id, json_ready


def tank(profile: RemoteProfile, container_id: str) -> dict:
    profile.require("tank_ids", container_id)
    row = fetch_one(
        "SELECT c.id,c.code,c.name,c.container_type,c.capacity_l,c.status,"
        "cp.manual_volume_l volume_l,cp.manual_stage stage,cp.manual_contents contents,"
        "cp.manual_temp_c temp_c,cp.manual_density_sg density_sg,cp.manual_brix brix,"
        "cp.manual_babo babo,cp.manual_ph ph,cp.manual_reading_at observed_at,cp.updated_at "
        "FROM cellar_containers c JOIN cellar_tank_labels tl ON tl.container_id=c.id AND tl.estate_id=c.estate_id "
        "LEFT JOIN cellar_control_profiles cp ON cp.container_id=c.id AND cp.estate_id=c.estate_id "
        "WHERE c.estate_id=%s AND c.id=%s AND c.active=1 AND tl.active=1 LIMIT 1",
        (estate_id(), container_id),
    )
    if not row:
        raise HTTPException(404, "not found")
    # Manual measurements retain their actual date (including NULL). Do not
    # overlay live/simulated sensor data, legal/person defaults or other tanks.
    return json_ready({"tank": row, "source": "cellar_control_profiles/manual", "projection": "manual_label_v1", "live_sensor_data": False})


def kiosk(profile: RemoteProfile, kiosk_id: str) -> dict:
    profile.require("kiosk_ids", kiosk_id)
    row = fetch_one(
        "SELECT id,name,container_id FROM cellar_label_kiosks WHERE estate_id=%s AND id=%s AND active=1 LIMIT 1",
        (estate_id(), kiosk_id),
    )
    if not row:
        raise HTTPException(404, "not found")
    # Both kiosk AND its current tank must remain explicitly allowed. A kiosk
    # reassignment outside the device's scope fails closed, without last_seen writes.
    result = tank(profile, str(row["container_id"]))
    return json_ready({"kiosk": {"id": row["id"], "name": row["name"]}, **result})


def field_tasks(profile: RemoteProfile) -> dict:
    ids = sorted(profile.resources.get("task_ids", ()))
    rows = fetch_all(
        "SELECT id,title,category,status,priority,due_date,updated_at FROM tasks WHERE estate_id=%s AND id IN ("
        + ",".join(["%s"] * len(ids)) + ") ORDER BY due_date,id LIMIT 128",
        (estate_id(), *ids),
    ) if ids else []
    return json_ready({"tasks": rows, "projection": "assigned_task_read_v1"})


def pos_catalog(profile: RemoteProfile) -> dict:
    ids = sorted(profile.resources.get("catalog_ids", ()))
    rows = fetch_all(
        "SELECT id,name,sku,unit,updated_at FROM register_catalog_items WHERE estate_id=%s AND sellable=1 AND id IN ("
        + ",".join(["%s"] * len(ids)) + ") ORDER BY name,id LIMIT 128",
        (estate_id(), *ids),
    ) if ids else []
    # Selling availability needs committed-stock aggregation across financial
    # tables. That scope is NOT authorized here: unknown is not source stock/zero.
    return json_ready({"catalog": [{**row, "available_quantity": None} for row in rows], "projection": "catalog_identity_read_v1", "inventory_status": "not_authorized"})


def envelope(payload: dict) -> dict:
    return {"read_only": True, "generated_at": datetime.now(timezone.utc).isoformat(), "offline_cache": False, **payload}
